"""SqliteCollection — 真实 SQLite 后端的 Collection Protocol 实现。

线程安全：所有方法包在单一 threading.Lock 里。
事务：add_document 在单一 BEGIN/COMMIT 内完成 delete-old + upsert-doc + insert-chunks。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from qmd.core.chunking import chunk_document
from qmd.core.config import QmdConfig
from qmd.core.embedding import Embedder
from qmd.core.retrieval import rrf_fuse
from qmd.models import ChunkRef, CollectionInfo, SearchResult

def _vec_to_sqlite_literal(vec: list[float]) -> str:
    """sqlite-vec 的 MATCH 接受 JSON array 字符串。"""
    return json.dumps(vec)


class SqliteCollection:
    """实现 qmd.models.Collection Protocol。"""

    def __init__(
        self,
        conn: sqlite3.Connection,
        name: str,
        lock: threading.Lock,
        embedder: Embedder,
        config: QmdConfig,
    ) -> None:
        self.name = name
        self._conn = conn
        self._lock = lock
        self._embedder = embedder
        self.config = config

    # --- mutations ---

    def add_document(
        self,
        document_id: str,
        markdown: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """新增或更新文档（幂等 upsert）。先删旧 chunks 再插新 chunks。"""
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        now = int(time.time() * 1000)
        chunks = chunk_document(markdown, size=self.config.chunking.size, overlap=self.config.chunking.overlap)

        embeddings: list[list[float]] = []
        if chunks:
            embeddings = self._embedder.embed([c.text for c in chunks])

        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute("BEGIN")
                self._delete_chunks_locked(cur, document_id)
                cur.execute(
                    """
                    INSERT INTO documents(collection, id, markdown, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(collection, id) DO UPDATE SET
                        markdown=excluded.markdown,
                        metadata=excluded.metadata,
                        updated_at=excluded.updated_at
                    """,
                    (self.name, document_id, markdown, meta_json, now, now),
                )
                for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                    cur.execute(
                        """
                        INSERT INTO chunks(collection, document_id, chunk_index, text, char_start, char_end)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (self.name, document_id, idx, chunk.text, chunk.char_start, chunk.char_end),
                    )
                    rowid = cur.lastrowid
                    cur.execute("INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)", (rowid, chunk.text))
                    cur.execute(
                        "INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)",
                        (rowid, _vec_to_sqlite_literal(emb)),
                    )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def add_documents(self, docs: list[dict]) -> None:
        """批量新增或更新文档（原子事务）。

        fail-fast 全检 → 批内去重（后写覆盖）→ 锁外分块 + 单次大 batch embedding
        → 加锁 → BEGIN → 每个文档 upsert + 删旧 chunks + executemany 插入 chunks/fts/vec
        → COMMIT 或 ROLLBACK。
        """
        if not docs:
            return

        # fail-fast 全检（在加锁前执行，避免持锁做无谓校验）
        for i, d in enumerate(docs):
            if not isinstance(d, dict):
                raise ValueError(f"docs[{i}] 必须是 dict，实际是 {type(d).__name__}")
            # 必填字段
            for key in ("document_id", "markdown"):
                if key not in d:
                    raise ValueError(f"docs[{i}] 缺少字段 '{key}'")
            if not isinstance(d["document_id"], str):
                raise ValueError(
                    f"docs[{i}]['document_id'] 类型错: 期望 str, 实际 {type(d['document_id']).__name__}"
                )
            if not isinstance(d["markdown"], str):
                raise ValueError(
                    f"docs[{i}]['markdown'] 类型错: 期望 str, 实际 {type(d['markdown']).__name__}"
                )
            # 可选字段
            if "metadata" in d and not isinstance(d["metadata"], dict):
                raise ValueError(
                    f"docs[{i}]['metadata'] 类型错: 期望 dict, 实际 {type(d['metadata']).__name__}"
                )

        # 批内同 id 去重：后写覆盖前写
        deduped: dict[str, dict] = {}
        for d in docs:
            deduped[d["document_id"]] = d
        ordered = list(deduped.values())

        now = int(time.time() * 1000)

        # 所有文档先分块，收集所有 chunk 文本，做单次大 batch embedding
        per_doc_chunks = []
        for d in ordered:
            chunks = chunk_document(
                d["markdown"],
                size=self.config.chunking.size,
                overlap=self.config.chunking.overlap,
            )
            per_doc_chunks.append(chunks)

        all_texts = [c.text for chunks in per_doc_chunks for c in chunks]
        if all_texts:
            all_embeddings = self._embedder.embed(all_texts)
        else:
            all_embeddings = []

        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute("BEGIN")

                emb_offset = 0
                for d, chunks in zip(ordered, per_doc_chunks):
                    document_id = d["document_id"]
                    markdown = d["markdown"]
                    meta_json = json.dumps(d.get("metadata") or {}, ensure_ascii=False)

                    # upsert document 行
                    cur.execute(
                        """
                        INSERT INTO documents(collection, id, markdown, metadata, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(collection, id) DO UPDATE SET
                            markdown=excluded.markdown,
                            metadata=excluded.metadata,
                            updated_at=excluded.updated_at
                        """,
                        (self.name, document_id, markdown, meta_json, now, now),
                    )

                    # 删旧 chunks（fts/vec 影子一并删）
                    self._delete_chunks_locked(cur, document_id)

                    # 插入新 chunks：逐行 INSERT 以获取 lastrowid，然后 executemany fts+vec
                    fts_rows: list[tuple] = []
                    vec_rows: list[tuple] = []
                    n = len(chunks)
                    embeddings = all_embeddings[emb_offset : emb_offset + n]
                    emb_offset += n

                    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                        cur.execute(
                            """
                            INSERT INTO chunks(collection, document_id, chunk_index, text, char_start, char_end)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (self.name, document_id, idx, chunk.text, chunk.char_start, chunk.char_end),
                        )
                        rowid = cur.lastrowid
                        fts_rows.append((rowid, chunk.text))
                        vec_rows.append((rowid, _vec_to_sqlite_literal(emb)))

                    if fts_rows:
                        cur.executemany(
                            "INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)", fts_rows
                        )
                    if vec_rows:
                        cur.executemany(
                            "INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)", vec_rows
                        )

                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def delete_document(self, document_id: str) -> None:
        """删除指定文档及其所有 chunks。不存在时静默 no-op。"""
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute("BEGIN")
                self._delete_chunks_locked(cur, document_id)
                cur.execute(
                    "DELETE FROM documents WHERE collection=? AND id=?",
                    (self.name, document_id),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def _delete_chunks_locked(self, cur: sqlite3.Cursor, document_id: str) -> None:
        """删除该文档的所有 chunks（含 fts/vec 影子）。调用者须持锁 + 在事务内。"""
        rows = cur.execute(
            "SELECT rowid FROM chunks WHERE collection=? AND document_id=?",
            (self.name, document_id),
        ).fetchall()
        rowids = [r[0] for r in rows]
        for rowid in rowids:
            cur.execute("DELETE FROM chunks_fts WHERE rowid=?", (rowid,))
            cur.execute("DELETE FROM chunks_vec WHERE rowid=?", (rowid,))
        cur.execute(
            "DELETE FROM chunks WHERE collection=? AND document_id=?",
            (self.name, document_id),
        )

    # --- reads ---

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        """取回文档全文与元数据。不存在时返回 None。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT markdown, metadata FROM documents WHERE collection=? AND id=?",
                (self.name, document_id),
            ).fetchone()
            if row is None:
                return None
            markdown, meta_json = row
            chunk_count = self._conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE collection=? AND document_id=?",
                (self.name, document_id),
            ).fetchone()[0]
            return {
                "id": document_id,
                "markdown": markdown,
                "metadata": json.loads(meta_json),
                "chunk_count": chunk_count,
            }

    def list_documents(self) -> list[str]:
        """列出所有 document_id，按字母序排列。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM documents WHERE collection=? ORDER BY id",
                (self.name,),
            ).fetchall()
            return [r[0] for r in rows]

    def info(self) -> CollectionInfo:
        """返回本 collection 的元信息（文档数、chunk 数、embedding 维度）。"""
        with self._lock:
            doc_count = self._conn.execute(
                "SELECT COUNT(*) FROM documents WHERE collection=?", (self.name,)
            ).fetchone()[0]
            chunk_count = self._conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE collection=?", (self.name,)
            ).fetchone()[0]
            return CollectionInfo(
                name=self.name,
                document_count=doc_count,
                chunk_count=chunk_count,
                embedding_dim=Embedder.DIM if chunk_count else None,
            )

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        rerank: bool = False,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """混合检索（BM25 + 向量 + RRF），rerank=True 时接入 Reranker 重排序。"""
        if not query.strip() or top_k <= 0:
            return []
        query_vec = self._embedder.embed([query])[0]

        # rerank=True 时先拿 top_k_candidates 个候选，再重排取 top_k
        rrf_limit = self.config.rerank.top_k_candidates if rerank else top_k

        with self._lock:
            filter_sql, filter_params = self._build_filter_clause(filters)

            bm25_sql = f"""
                SELECT c.rowid FROM chunks_fts f
                JOIN chunks c ON c.rowid = f.rowid
                JOIN documents d ON d.collection = c.collection AND d.id = c.document_id
                WHERE c.collection = ? AND f.text MATCH ?{filter_sql}
                ORDER BY rank LIMIT ?
            """
            bm25_rows = self._conn.execute(
                bm25_sql,
                (self.name, query, *filter_params, self.config.retrieval.bm25_top_k),
            ).fetchall()
            bm25_ids = [r[0] for r in bm25_rows]

            vec_sql = f"""
                SELECT c.rowid FROM chunks_vec v
                JOIN chunks c ON c.rowid = v.rowid
                JOIN documents d ON d.collection = c.collection AND d.id = c.document_id
                WHERE c.collection = ? AND v.embedding MATCH ? AND k = ?{filter_sql}
                ORDER BY distance
            """
            vec_rows = self._conn.execute(
                vec_sql,
                (self.name, _vec_to_sqlite_literal(query_vec), self.config.retrieval.vector_top_k, *filter_params),
            ).fetchall()
            vec_ids = [r[0] for r in vec_rows]

            fused = rrf_fuse([bm25_ids, vec_ids], k=self.config.retrieval.rrf_k)[:rrf_limit]
            if not fused:
                return []

            rowid_to_score = dict(fused)
            placeholders = ",".join("?" for _ in fused)
            detail_rows = self._conn.execute(
                f"""
                SELECT c.rowid, c.document_id, c.chunk_index, c.text, c.char_start, c.char_end, d.metadata
                FROM chunks c
                JOIN documents d ON d.collection = c.collection AND d.id = c.document_id
                WHERE c.rowid IN ({placeholders})
                """,
                tuple(rowid for rowid, _ in fused),
            ).fetchall()

        # 按 RRF 顺序重建 candidates（rowid 顺序即 RRF 排名顺序）
        rowid_to_detail: dict[int, tuple] = {
            row[0]: row for row in detail_rows
        }
        candidates: list[SearchResult] = []
        for rowid, rrf_score in fused:
            if rowid not in rowid_to_detail:
                continue
            _, doc_id, chunk_idx, text, cs, ce, meta_json = rowid_to_detail[rowid]
            candidates.append(
                SearchResult(
                    chunk_ref=ChunkRef(
                        document_id=doc_id, chunk_index=chunk_idx,
                        char_start=cs, char_end=ce,
                    ),
                    text=text,
                    score=rrf_score,
                    bm25_score=None,
                    vector_score=None,
                    rerank_score=None,
                    metadata=json.loads(meta_json),
                )
            )

        if rerank:
            from qmd.core.rerank import Reranker
            scores = Reranker().score(query, [c.text for c in candidates])
            for c, s in zip(candidates, scores):
                c.rerank_score = s
            candidates.sort(key=lambda c: c.rerank_score, reverse=True)  # type: ignore[arg-type]
        else:
            for c in candidates:
                c.rerank_score = None

        return candidates[:top_k]

    def _build_filter_clause(self, filters: dict[str, Any] | None) -> tuple[str, list[Any]]:
        """把 filters dict 转成 WHERE 片段。MVP 仅支持精确相等。"""
        if not filters:
            return "", []
        parts: list[str] = []
        params: list[Any] = []
        for key, val in filters.items():
            parts.append(" AND json_extract(d.metadata, ?) = ?")
            params.append(f"$.{key}")
            params.append(val)
        return "".join(parts), params
