"""
混合检索引擎

实现 QMD 的核心检索算法：
- BM25 全文检索（FTS5）
- 向量语义检索（sqlite-vec）
- Reciprocal Rank Fusion (RRF) 融合
- LLM Query Expansion + Reranking
- Position-Aware Blending
"""

import struct
from dataclasses import dataclass
from typing import Any

from loguru import logger

from qmd.core.chunking import chunk_document
from qmd.core.config import find_context_for_path
from qmd.core.db import Database
from qmd.llm.base import LLMBackend, RerankDocument

# =============================================================================
# 常量
# =============================================================================

# 强信号检测阈值（跳过 query expansion）
STRONG_SIGNAL_MIN_SCORE = 0.85
STRONG_SIGNAL_MIN_GAP = 0.15

# RRF 融合参数
RRF_K = 60

# Rerank 候选数量限制
RERANK_CANDIDATE_LIMIT = 40


# =============================================================================
# 数据结构
# =============================================================================


@dataclass
class SearchResult:
    """检索结果"""

    file: str  # 文件路径（相对于集合）
    title: str  # 文档标题
    body: str  # 文档内容
    score: float  # 相关性分数 [0, 1]
    collection: str  # 所属集合
    hash: str  # 内容哈希
    pos: int = 0  # 最佳 chunk 的位置
    context: str | None = None  # 层级继承的上下文（global + path-specific）


@dataclass
class RankedResult:
    """排序结果（用于 RRF）"""

    file: str  # 文件路径
    title: str  # 文档标题
    body: str  # 文档内容
    score: float  # 分数


# =============================================================================
# BM25 全文检索
# =============================================================================


def build_fts5_query(query: str) -> str:
    """
    构建 FTS5 查询字符串

    Args:
        query: 原始查询

    Returns:
        FTS5 MATCH 子句
    """
    # 简化实现：直接使用查询文本
    # TODO: 可以添加更复杂的查询处理（OR、AND、phrase 等）
    return query.strip()


def bm25_search(
    db: Database, query: str, collection: str | None = None, limit: int = 20
) -> list[SearchResult]:
    """
    BM25 全文检索

    使用 SQLite FTS5 的 BM25 算法进行全文检索。

    Args:
        db: 数据库实例
        query: 查询文本
        collection: 集合名称（可选，用于过滤）
        limit: 结果数量限制

    Returns:
        检索结果列表（按 BM25 分数降序）
    """
    fts_query = build_fts5_query(query)
    if not fts_query:
        return []

    # 构建 SQL 查询
    sql = """
        SELECT
            d.collection || '/' || d.path as filepath,
            d.title,
            content.doc as body,
            d.hash,
            d.collection,
            bm25(documents_fts, 10.0, 1.0) as bm25_score
        FROM documents_fts f
        JOIN documents d ON d.id = f.rowid
        JOIN content ON content.hash = d.hash
        WHERE documents_fts MATCH ? AND d.active = 1
    """
    params: list[str | int] = [fts_query]

    if collection:
        sql += " AND d.collection = ?"
        params.append(collection)

    # BM25 分数越低越好（负数），升序排序
    sql += " ORDER BY bm25_score ASC LIMIT ?"
    params.append(limit)

    try:
        rows = db.conn.execute(sql, params).fetchall()
    except Exception as e:
        logger.error(f"BM25 检索失败: {e}")
        return []

    results = []
    for row in rows:
        # 转换 BM25 分数：|x| / (1 + |x|) → [0, 1)
        # FTS5 BM25 分数是负数：强匹配≈-10，弱匹配≈-2
        bm25_score = row["bm25_score"]
        score = abs(bm25_score) / (1 + abs(bm25_score))

        # 提取 collection 和 相对路径
        filepath = row["filepath"]
        coll = row["collection"]
        # filepath 格式是 "collection/path"，提取 path 部分
        rel_path = filepath.split("/", 1)[1] if "/" in filepath else filepath

        # 获取层级继承的 context
        ctx = find_context_for_path(coll, rel_path)

        results.append(
            SearchResult(
                file=filepath,
                title=row["title"],
                body=row["body"],
                score=score,
                collection=coll,
                hash=row["hash"],
                context=ctx,
            )
        )

    return results


# =============================================================================
# 向量语义检索
# =============================================================================


def vector_search(
    db: Database,
    query_embedding: list[float],
    collection: str | None = None,
    limit: int = 20,
) -> list[SearchResult]:
    """
    向量语义检索

    使用 sqlite-vec 进行 KNN 查询。

    Args:
        db: 数据库实例
        query_embedding: 查询向量
        collection: 集合名称（可选）
        limit: 结果数量限制

    Returns:
        检索结果列表（按余弦相似度降序）
    """
    # 检查 vectors_vec 表是否存在
    table_exists = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='vectors_vec'"
    ).fetchone()

    if not table_exists:
        return []

    # 将 embedding 转换为字节（sqlite-vec 需要）
    embedding_bytes = struct.pack(f"{len(query_embedding)}f", *query_embedding)

    # Step 1: 从 vectors_vec 获取匹配（避免 JOIN 导致挂起）
    try:
        vec_results = db.conn.execute(
            "SELECT hash_seq, distance FROM vectors_vec WHERE embedding MATCH ? AND k = ?",
            (embedding_bytes, limit * 3),
        ).fetchall()
    except Exception as e:
        logger.error(f"向量检索失败: {e}")
        return []

    if not vec_results:
        return []

    # 构建距离映射
    distance_map = {row["hash_seq"]: row["distance"] for row in vec_results}

    # Step 2: 获取文档数据
    hash_seqs = [row["hash_seq"] for row in vec_results]
    placeholders = ",".join("?" * len(hash_seqs))

    doc_sql = f"""
        SELECT
            cv.hash || '_' || cv.seq as hash_seq,
            cv.hash,
            cv.pos,
            d.collection || '/' || d.path as filepath,
            d.title,
            content.doc as body,
            d.collection
        FROM content_vectors cv
        JOIN documents d ON d.hash = cv.hash AND d.active = 1
        JOIN content ON content.hash = d.hash
        WHERE cv.hash || '_' || cv.seq IN ({placeholders})
    """
    params: list[str] = list(hash_seqs)

    if collection:
        doc_sql += " AND d.collection = ?"
        params.append(collection)

    try:
        doc_rows = db.conn.execute(doc_sql, params).fetchall()
    except Exception as e:
        logger.error(f"文档查询失败: {e}")
        return []

    # 去重：同一文档取最佳距离的 chunk
    seen: dict[str, dict[str, Any]] = {}
    for row in doc_rows:
        hash_seq = row["hash_seq"]
        distance = distance_map.get(hash_seq, 1.0)
        filepath = row["filepath"]

        existing = seen.get(filepath)
        if not existing or distance < existing["distance"]:
            seen[filepath] = {
                "filepath": filepath,
                "title": row["title"],
                "body": row["body"],
                "hash": row["hash"],
                "collection": row["collection"],
                "pos": row["pos"],
                "distance": distance,
            }

    # 排序并转换为 SearchResult
    sorted_results = sorted(seen.values(), key=lambda x: x["distance"])[:limit]

    results = []
    for item in sorted_results:
        # 余弦相似度 = 1 - 距离
        score = 1 - item["distance"]

        # 提取 collection 和 相对路径
        filepath = item["filepath"]
        coll = item["collection"]
        # filepath 格式是 "collection/path"，提取 path 部分
        rel_path = filepath.split("/", 1)[1] if "/" in filepath else filepath

        # 获取层级继承的 context
        ctx = find_context_for_path(coll, rel_path)

        results.append(
            SearchResult(
                file=filepath,
                title=item["title"],
                body=item["body"],
                score=score,
                collection=coll,
                hash=item["hash"],
                pos=item["pos"],
                context=ctx,
            )
        )

    return results


# =============================================================================
# Reciprocal Rank Fusion (RRF)
# =============================================================================


def rrf_fuse(
    rankings: list[list[int]],
    k: int = 60,
) -> list[tuple[int, float]]:
    """融合多个排序列表（纯函数版本）。

    参数：
        rankings: 多个按相关度降序的 rowid 列表。同一 rowid 可能出现在多个列表里。
        k: RRF 常数，默认 60。

    返回：(rowid, rrf_score) 列表，按 rrf_score 降序；打平时按 rowid 升序（稳定）。
    rrf_score = Σ_i 1 / (k + rank_i(rowid))，rank 从 0 开始。
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, rowid in enumerate(ranking):
            scores[rowid] = scores.get(rowid, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))


def reciprocal_rank_fusion(
    result_lists: list[list[RankedResult]],
    weights: list[float] | None = None,
    k: int = RRF_K,
) -> list[RankedResult]:
    """
    Reciprocal Rank Fusion (RRF) 融合算法

    将多个排序列表融合为一个统一的排序。

    Args:
        result_lists: 多个排序结果列表
        weights: 每个列表的权重（可选，默认全为 1.0）
        k: RRF 参数（默认 60）

    Returns:
        融合后的排序结果
    """
    if weights is None:
        weights = [1.0] * len(result_lists)

    # 计算 RRF 分数
    scores: dict[str, dict[str, Any]] = {}

    for list_idx, result_list in enumerate(result_lists):
        weight = weights[list_idx] if list_idx < len(weights) else 1.0

        for rank, result in enumerate(result_list):
            rrf_contribution = weight / (k + rank + 1)

            if result.file in scores:
                scores[result.file]["rrf_score"] += rrf_contribution
                scores[result.file]["top_rank"] = min(
                    scores[result.file]["top_rank"], rank
                )
            else:
                scores[result.file] = {
                    "result": result,
                    "rrf_score": rrf_contribution,
                    "top_rank": rank,
                }

    # Top-rank bonus
    for entry in scores.values():
        if entry["top_rank"] == 0:
            entry["rrf_score"] += 0.05
        elif entry["top_rank"] <= 2:
            entry["rrf_score"] += 0.02

    # 排序并返回
    sorted_results = sorted(
        scores.values(), key=lambda x: x["rrf_score"], reverse=True
    )

    return [
        RankedResult(
            file=entry["result"].file,
            title=entry["result"].title,
            body=entry["result"].body,
            score=entry["rrf_score"],
        )
        for entry in sorted_results
    ]


# =============================================================================
# 完整检索流程
# =============================================================================


def search(
    db: Database,
    query: str,
    collection: str | None = None,
    limit: int = 10,
    llm_backend: LLMBackend | None = None,
) -> list[SearchResult]:
    """
    完整的混合检索流程

    混合 BM25 + 向量检索，使用 RRF 融合，支持 Query Expansion 和 Reranking。

    流程：
    1. BM25 强信号探测
    2. Query Expansion (如果没有强信号)
    3. 并行执行 BM25 + Vector 检索
    4. RRF 融合
    5. 分块并选择最佳 chunk
    6. Rerank (如果有 LLM)
    7. Position-Aware Blending
    8. 去重 + 过滤

    Args:
        db: 数据库实例
        query: 查询文本
        collection: 集合名称（可选）
        limit: 返回结果数量
        llm_backend: LLM 后端（可选，用于 embedding/rerank）

    Returns:
        检索结果列表
    """
    if not query.strip():
        return []

    ranked_lists: list[list[RankedResult]] = []

    # Step 1: BM25 强信号探测
    initial_fts = bm25_search(db, query, collection, 20)
    top_score = initial_fts[0].score if initial_fts else 0
    second_score = initial_fts[1].score if len(initial_fts) > 1 else 0

    has_strong_signal = (
        len(initial_fts) > 0
        and top_score >= STRONG_SIGNAL_MIN_SCORE
        and (top_score - second_score) >= STRONG_SIGNAL_MIN_GAP
    )

    if has_strong_signal:
        logger.debug(f"检测到强信号 (score={top_score:.3f}), 跳过 query expansion")

    # 添加初始 FTS 结果
    if initial_fts:
        ranked_lists.append(
            [
                RankedResult(
                    file=r.file, title=r.title, body=r.body, score=r.score
                )
                for r in initial_fts
            ]
        )

    # Step 2: Query Expansion（如果需要）
    expanded_queries = []
    if not has_strong_signal and llm_backend:
        try:
            expanded = llm_backend.expand_query(query)
            expanded_queries = expanded
            logger.debug(f"Query expansion 生成了 {len(expanded)} 个变体")
        except Exception as e:
            logger.warning(f"Query expansion 失败: {e}")

    # Step 3: 执行扩展查询的检索
    for exp_query in expanded_queries:
        if exp_query.type == "lex":
            # 词法扩展 → FTS
            fts_results = bm25_search(db, exp_query.text, collection, 20)
            if fts_results:
                ranked_lists.append(
                    [
                        RankedResult(
                            file=r.file,
                            title=r.title,
                            body=r.body,
                            score=r.score,
                        )
                        for r in fts_results
                    ]
                )
        elif exp_query.type in ("vec", "hyde") and llm_backend:
            # 语义扩展 → Vector
            try:
                embed_result = llm_backend.embed(exp_query.text, is_query=True)
                if embed_result:
                    vec_results = vector_search(
                        db, embed_result.embedding, collection, 20
                    )
                    if vec_results:
                        ranked_lists.append(
                            [
                                RankedResult(
                                    file=r.file,
                                    title=r.title,
                                    body=r.body,
                                    score=r.score,
                                )
                                for r in vec_results
                            ]
                        )
            except Exception as e:
                logger.warning(f"向量检索失败: {e}")

    # 如果有 LLM 后端，也对原查询执行向量检索
    if llm_backend and not has_strong_signal:
        try:
            embed_result = llm_backend.embed(query, is_query=True)
            if embed_result:
                vec_results = vector_search(db, embed_result.embedding, collection, 20)
                if vec_results:
                    ranked_lists.append(
                        [
                            RankedResult(
                                file=r.file,
                                title=r.title,
                                body=r.body,
                                score=r.score,
                            )
                            for r in vec_results
                        ]
                    )
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")

    if not ranked_lists:
        return []

    # Step 4: RRF 融合
    # 前两个列表（原查询的 FTS + Vec）权重 2x
    weights = [2.0 if i < 2 else 1.0 for i in range(len(ranked_lists))]
    fused = reciprocal_rank_fusion(ranked_lists, weights)

    candidates = fused[:RERANK_CANDIDATE_LIMIT]

    if not candidates:
        return []

    # Step 5: 分块并选择最佳 chunk（基于关键词覆盖度）
    query_terms = [t for t in query.lower().split() if len(t) > 2]
    chunks_to_rerank: list[RerankDocument] = []
    doc_chunk_map: dict[str, dict[str, Any]] = {}

    for cand in candidates:
        chunks = chunk_document(cand.body)
        if not chunks:
            continue

        # 选择关键词覆盖度最高的 chunk
        best_idx = 0
        best_score = -1
        for i, chunk in enumerate(chunks):
            chunk_lower = chunk.text.lower()
            keyword_score = sum(
                1 for term in query_terms if term in chunk_lower
            )
            if keyword_score > best_score:
                best_score = keyword_score
                best_idx = i

        chunks_to_rerank.append(
            RerankDocument(file=cand.file, text=chunks[best_idx].text)
        )
        doc_chunk_map[cand.file] = {
            "chunks": chunks,
            "best_idx": best_idx,
        }

    # Step 6: Rerank（如果有 LLM）
    if llm_backend and chunks_to_rerank:
        try:
            rerank_result = llm_backend.rerank(query, chunks_to_rerank)
            reranked = rerank_result.results if rerank_result else []
            logger.debug(f"Rerank 处理了 {len(chunks_to_rerank)} 个 chunk")
        except Exception as e:
            logger.warning(f"Rerank 失败: {e}")
            reranked = []
    else:
        reranked = []

    # Step 7: Position-Aware Blending
    if reranked:
        candidate_map = {c.file: c for c in candidates}
        rrf_rank_map = {c.file: i + 1 for i, c in enumerate(candidates)}

        blended_results = []
        for rerank_item in reranked:
            rrf_rank = rrf_rank_map.get(rerank_item.file, RERANK_CANDIDATE_LIMIT)

            # Position-aware weights
            if rrf_rank <= 3:
                rrf_weight = 0.75
            elif rrf_rank <= 10:
                rrf_weight = 0.60
            else:
                rrf_weight = 0.40

            rrf_score = 1 / rrf_rank
            blended_score = rrf_weight * rrf_score + (1 - rrf_weight) * rerank_item.score

            candidate = candidate_map.get(rerank_item.file)
            if not candidate:
                continue

            chunk_info = doc_chunk_map.get(rerank_item.file, {})
            best_idx = chunk_info.get("best_idx", 0)
            chunks = chunk_info.get("chunks", [])
            best_chunk_pos = chunks[best_idx].pos if best_idx < len(chunks) else 0

            # 从原始检索结果中获取完整元数据
            original_result = None
            for result_list in ranked_lists:
                for r in result_list:
                    if r.file == rerank_item.file:
                        original_result = r
                        break
                if original_result:
                    break

            # 获取 collection 和 hash
            collection_name = ""
            content_hash = ""
            if "/" in rerank_item.file:
                parts = rerank_item.file.split("/", 1)
                collection_name = parts[0]

            # 查询数据库获取 hash
            try:
                row = db.conn.execute(
                    "SELECT hash FROM documents WHERE collection = ? AND path = ? AND active = 1",
                    (collection_name, parts[1] if len(parts) > 1 else rerank_item.file),
                ).fetchone()
                if row:
                    content_hash = row["hash"]
            except:
                pass

            # 获取 context
            rel_path = parts[1] if len(parts) > 1 else ""
            ctx = find_context_for_path(collection_name, rel_path) if collection_name else None

            blended_results.append(
                SearchResult(
                    file=rerank_item.file,
                    title=candidate.title,
                    body=candidate.body,
                    score=blended_score,
                    collection=collection_name,
                    hash=content_hash,
                    pos=best_chunk_pos,
                    context=ctx,
                )
            )

        blended_results.sort(key=lambda x: x.score, reverse=True)
    else:
        # 没有 rerank，直接使用 RRF 结果
        blended_results = []
        for cand in candidates:
            collection_name = ""
            content_hash = ""
            if "/" in cand.file:
                parts = cand.file.split("/", 1)
                collection_name = parts[0]

            try:
                row = db.conn.execute(
                    "SELECT hash FROM documents WHERE collection = ? AND path = ? AND active = 1",
                    (collection_name, parts[1] if len(parts) > 1 else cand.file),
                ).fetchone()
                if row:
                    content_hash = row["hash"]
            except:
                pass

            # 获取 context
            rel_path = parts[1] if len(parts) > 1 else ""
            ctx = find_context_for_path(collection_name, rel_path) if collection_name else None

            blended_results.append(
                SearchResult(
                    file=cand.file,
                    title=cand.title,
                    body=cand.body,
                    score=cand.score,
                    collection=collection_name,
                    hash=content_hash,
                    context=ctx,
                )
            )

    # Step 8: 去重 + 限制数量
    seen_files: set[str] = set()
    final_results = []
    for result in blended_results:
        if result.file in seen_files:
            continue
        seen_files.add(result.file)
        final_results.append(result)

        if len(final_results) >= limit:
            break

    return final_results
