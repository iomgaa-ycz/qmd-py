"""FakeQmdClient：纯内存实现，供下游单测和 M0 CLI 使用。

实现约束：
- 不依赖 SQLite / sqlite-vec
- embedding 复用 qmd.core.embedding.Embedder 单例（Qwen3-Embedding-0.6B，1024 维）
- BM25 用 rank_bm25（纯 Python）
- char_start/char_end 精确指向原始 markdown 的字符位置
"""
from __future__ import annotations

import copy
import hashlib
import threading
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from loguru import logger
from rank_bm25 import BM25Okapi

from qmd.core.embedding import Embedder
from qmd.models import ChunkRef, CollectionInfo, SearchResult

_EMBEDDING_DIM = 1024  # Qwen3-Embedding-0.6B
_RRF_K = 60


def _fake_rerank_score(query: str, text: str) -> float:
    """基于 sha256 的稳定伪 rerank_score，范围 [0, 1]。

    不依赖真实 reranker，仅用于 Fake 实现保持接口契约一致。
    """
    h = hashlib.sha256(f"{query}||{text}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


@dataclass
class _ChunkRecord:
    document_id: str
    chunk_index: int
    text: str
    char_start: int
    char_end: int
    embedding: np.ndarray | None = None  # 懒填充


@dataclass
class _DocRecord:
    markdown: str
    metadata: dict[str, Any]
    chunk_indices: list[int] = field(default_factory=list)


def _simple_chunk(markdown: str) -> list[tuple[str, int, int]]:
    """按 \\n\\n 切段，返回 [(text, char_start, char_end), ...]，char_end 闭区间。

    保证 markdown[char_start:char_end+1] == text。空段跳过。
    """
    chunks: list[tuple[str, int, int]] = []
    cursor = 0
    for segment in markdown.split("\n\n"):
        start = markdown.find(segment, cursor) if segment else cursor
        if segment.strip():
            end = start + len(segment) - 1
            chunks.append((segment, start, end))
        cursor = start + len(segment) + 2  # +2 跳过 \n\n
    # 边界：全文无 \n\n 且非空 → 整个文档一个 chunk
    if not chunks and markdown.strip():
        chunks.append((markdown, 0, len(markdown) - 1))
    return chunks


def _tokenize(text: str) -> list[str]:
    """BM25 tokenization：小写 + 空格切分。Fake 不做中文分词。"""
    return text.lower().split()


class FakeCollection:
    """Fake 的单 collection 实现，满足 qmd.models.Collection Protocol。"""

    def __init__(self, name: str, embedder: Embedder) -> None:
        self.name = name
        self._docs: dict[str, _DocRecord] = {}
        self._chunks: list[_ChunkRecord] = []
        self._lock = threading.RLock()
        self._bm25: BM25Okapi | None = None
        self._bm25_dirty = True
        self._embedder = embedder

    def add_document(
        self,
        document_id: str,
        markdown: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            if document_id in self._docs:
                self._delete_document_locked(document_id)
            chunks = _simple_chunk(markdown)
            chunk_indices: list[int] = []
            for i, (text, start, end) in enumerate(chunks):
                rec = _ChunkRecord(
                    document_id=document_id,
                    chunk_index=i,
                    text=text,
                    char_start=start,
                    char_end=end,
                )
                chunk_indices.append(len(self._chunks))
                self._chunks.append(rec)
            self._docs[document_id] = _DocRecord(
                markdown=markdown,
                metadata=dict(metadata or {}),
                chunk_indices=chunk_indices,
            )
            self._bm25_dirty = True

    def delete_document(self, document_id: str) -> None:
        with self._lock:
            if document_id not in self._docs:
                return
            self._delete_document_locked(document_id)

    def _delete_document_locked(self, document_id: str) -> None:
        """调用者须持锁。重建 _chunks 与其他 doc 的 chunk_indices。"""
        self._docs.pop(document_id, None)
        self._chunks = [c for c in self._chunks if c.document_id != document_id]
        # 重建 chunk_indices（按 _chunks 当前顺序）
        for rec in self._docs.values():
            rec.chunk_indices = []
        for idx, c in enumerate(self._chunks):
            self._docs[c.document_id].chunk_indices.append(idx)
        self._bm25_dirty = True

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._docs.get(document_id)
            if rec is None:
                return None
            return {
                "id": document_id,
                "markdown": rec.markdown,
                "metadata": dict(rec.metadata),
                "chunk_count": len(rec.chunk_indices),
            }

    def list_documents(self) -> list[str]:
        with self._lock:
            return list(self._docs.keys())

    def add_documents(self, docs: list[dict]) -> None:
        """批量新增或更新文档（原子事务 + fail-fast 全检）。"""
        if not docs:
            return

        # fail-fast 全检：入库前全部验证，任一失败即抛
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

        with self._lock:
            # deepcopy snapshot 用于失败回滚（_lock 为 RLock，可重入）
            snapshot_docs = copy.deepcopy(self._docs)
            snapshot_chunks = copy.deepcopy(self._chunks)
            snapshot_dirty = self._bm25_dirty
            try:
                for d in docs:
                    self.add_document(d["document_id"], d["markdown"], d.get("metadata") or {})
            except Exception:
                self._docs = snapshot_docs
                self._chunks = snapshot_chunks
                self._bm25_dirty = snapshot_dirty
                raise

    def info(self) -> CollectionInfo:
        with self._lock:
            return CollectionInfo(
                name=self.name,
                document_count=len(self._docs),
                chunk_count=len(self._chunks),
                embedding_dim=_EMBEDDING_DIM if self._chunks else None,
            )

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        rerank: bool = False,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        with self._lock:
            if not self._chunks:
                return []
            # 过滤
            candidate_indices = [
                i for i, c in enumerate(self._chunks)
                if self._match_filters(c, filters)
            ]
            if not candidate_indices:
                return []
            # 确保 embeddings 就位
            self._ensure_embeddings(candidate_indices)
            # BM25 通道
            bm25_ranks = self._bm25_rank(query, candidate_indices)
            # 向量通道
            vec_ranks = self._vector_rank(query, candidate_indices)
            # RRF 融合
            fused = self._rrf_fuse(bm25_ranks, vec_ranks)
            # 构建结果列表（先按 RRF 分降序取候选，再决定是否 rerank 排序）
            fused_sorted = sorted(fused.items(), key=lambda kv: -kv[1]["score"])
            results: list[SearchResult] = []
            for chunk_idx, info in fused_sorted:
                c = self._chunks[chunk_idx]
                meta = self._docs[c.document_id].metadata
                result = SearchResult(
                    chunk_ref=ChunkRef(
                        document_id=c.document_id,
                        chunk_index=c.chunk_index,
                        char_start=c.char_start,
                        char_end=c.char_end,
                    ),
                    text=c.text,
                    score=info["score"],
                    bm25_score=info.get("bm25"),
                    vector_score=info.get("vector"),
                    rerank_score=None,
                    metadata=dict(meta),
                )
                results.append(result)
            # rerank 填充稳定伪分 + 排序
            if rerank:
                for r in results:
                    r.rerank_score = _fake_rerank_score(query, r.text)
                results.sort(key=lambda r: r.rerank_score, reverse=True)  # type: ignore[arg-type]
            return results[:top_k]

    def _match_filters(
        self, chunk: _ChunkRecord, filters: dict[str, Any] | None
    ) -> bool:
        if not filters:
            return True
        meta = self._docs[chunk.document_id].metadata
        return all(meta.get(k) == v for k, v in filters.items())

    def _ensure_embeddings(self, indices: list[int]) -> None:
        missing = [i for i in indices if self._chunks[i].embedding is None]
        if not missing:
            return
        texts = [self._chunks[i].text for i in missing]
        vectors = self._embedder.embed(texts)
        for i, vec in zip(missing, vectors, strict=True):
            self._chunks[i].embedding = np.asarray(vec, dtype=np.float32)

    def _bm25_rank(
        self, query: str, candidate_indices: list[int]
    ) -> list[tuple[int, float]]:
        """返回 [(chunk_idx, bm25_score), ...]，取 top 20。"""
        corpus = [_tokenize(self._chunks[i].text) for i in candidate_indices]
        if not any(corpus):
            return []
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(_tokenize(query))
        pairs = [
            (candidate_indices[j], float(scores[j])) for j in range(len(scores))
        ]
        pairs.sort(key=lambda kv: -kv[1])
        return pairs[:20]

    def _vector_rank(
        self, query: str, candidate_indices: list[int]
    ) -> list[tuple[int, float]]:
        q_vec = np.asarray(
            self._embedder.embed([query])[0], dtype=np.float32
        )
        pairs: list[tuple[int, float]] = []
        for i in candidate_indices:
            c = self._chunks[i]
            if c.embedding is None:
                continue
            cos = float(np.dot(q_vec, c.embedding))
            pairs.append((i, cos))
        pairs.sort(key=lambda kv: -kv[1])
        return pairs[:20]

    def _rrf_fuse(
        self,
        bm25_ranks: list[tuple[int, float]],
        vec_ranks: list[tuple[int, float]],
    ) -> dict[int, dict[str, float]]:
        """RRF(k=60) 融合。返回 {chunk_idx: {score, bm25, vector}}。"""
        out: dict[int, dict[str, float]] = {}
        for rank, (idx, score) in enumerate(bm25_ranks):
            out.setdefault(idx, {"score": 0.0})
            out[idx]["score"] += 1.0 / (_RRF_K + rank + 1)
            out[idx]["bm25"] = score
        for rank, (idx, score) in enumerate(vec_ranks):
            out.setdefault(idx, {"score": 0.0})
            out[idx]["score"] += 1.0 / (_RRF_K + rank + 1)
            out[idx]["vector"] = score
        return out


class FakeQmdClient:
    """Fake QmdClient 实现。纯内存，进程内线程安全。"""

    def __init__(self) -> None:
        self._collections: dict[str, FakeCollection] = {}
        self._lock = threading.Lock()
        self._embedder = Embedder()

    def collection(self, name: str) -> FakeCollection:
        with self._lock:
            if name not in self._collections:
                self._collections[name] = FakeCollection(name, self._embedder)
            return self._collections[name]

    def list_collections(self) -> list[CollectionInfo]:
        with self._lock:
            return [col.info() for col in self._collections.values()]

    def delete_collection(self, name: str) -> None:
        with self._lock:
            self._collections.pop(name, None)

    def close(self) -> None:
        pass
