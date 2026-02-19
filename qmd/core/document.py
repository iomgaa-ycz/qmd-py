"""
文档检索辅助函数

提供各种文档查找、模糊匹配和 docid 相关的工具函数。
移植自原版 qmd 的 store.ts。
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

from qmd.core.db import Database


# =============================================================================
# Docid 工具函数
# =============================================================================


def normalize_docid(docid: str) -> str:
    """
    规范化 docid 输入，去除引号和 # 前缀

    处理以下格式: "#abc123", 'abc123', "abc123", #abc123, abc123
    返回纯十六进制字符串

    Args:
        docid: 输入的 docid 字符串

    Returns:
        规范化后的十六进制字符串
    """
    normalized = docid.strip()

    # 去除引号（单引号或双引号）
    if (normalized.startswith('"') and normalized.endswith('"')) or \
       (normalized.startswith("'") and normalized.endswith("'")):
        normalized = normalized[1:-1]

    # 去除 # 前缀
    if normalized.startswith('#'):
        normalized = normalized[1:]

    return normalized


def is_docid(input_str: str) -> bool:
    """
    检查字符串是否为 docid 格式

    接受: #abc123, abc123, "#abc123", "abc123", '#abc123', 'abc123'
    规范化后必须是 6+ 位的十六进制字符串

    Args:
        input_str: 输入字符串

    Returns:
        如果是有效 docid 返回 True
    """
    normalized = normalize_docid(input_str)
    # 至少 6 个十六进制字符
    return len(normalized) >= 6 and bool(re.match(r'^[a-f0-9]+$', normalized, re.IGNORECASE))


def find_document_by_docid(
    db: Database,
    docid: str
) -> dict[str, str] | None:
    """
    通过 docid（hash 前 6 位）查找文档

    Args:
        db: 数据库实例
        docid: docid 字符串（支持多种格式）

    Returns:
        包含 filepath 和 hash 的字典，如果未找到返回 None
    """
    short_hash = normalize_docid(docid)

    if not short_hash:
        return None

    # 查找 hash 以 short_hash 开头的文档
    row = db.conn.execute(
        """
        SELECT 'qmd://' || d.collection || '/' || d.path as filepath, d.hash
        FROM documents d
        WHERE d.hash LIKE ? AND d.active = 1
        LIMIT 1
        """,
        (f"{short_hash}%",)
    ).fetchone()

    if row:
        return {"filepath": row["filepath"], "hash": row["hash"]}
    return None


# =============================================================================
# Levenshtein 距离计算（用于模糊匹配）
# =============================================================================


def find_similar_files(
    db: Database,
    query: str,
    min_similarity: float = 0.6,
    limit: int = 5
) -> list[str]:
    """
    查找与查询字符串相似的文件路径（使用 difflib 相似度）

    Args:
        db: 数据库实例
        query: 查询字符串
        min_similarity: 最小相似度（0.0-1.0），默认 0.6
        limit: 返回结果数量限制

    Returns:
        相似文件路径列表（按相似度降序）
    """
    # 获取所有文档路径
    rows = db.conn.execute(
        "SELECT path FROM documents WHERE active = 1"
    ).fetchall()

    query_lower = query.lower()

    # 计算相似度并排序
    scored = []
    for row in rows:
        path = row["path"]
        similarity = difflib.SequenceMatcher(None, path.lower(), query_lower).ratio()
        if similarity >= min_similarity:
            scored.append({"path": path, "similarity": similarity})

    # 按相似度降序排序并限制数量
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return [item["path"] for item in scored[:limit]]


# =============================================================================
# Glob 模式匹配
# =============================================================================


def match_files_by_glob(
    db: Database,
    pattern: str
) -> list[dict[str, Any]]:
    """
    通过 glob 模式匹配文件

    Args:
        db: 数据库实例
        pattern: glob 模式（例如: "**/*.md", "2024/**"）

    Returns:
        匹配的文件列表，每个包含 filepath, displayPath, bodyLength
    """
    from fnmatch import fnmatch

    # 获取所有文档
    rows = db.conn.execute(
        """
        SELECT
            'qmd://' || d.collection || '/' || d.path as filepath,
            d.path as displayPath,
            length(c.doc) as bodyLength
        FROM documents d
        JOIN content c ON c.hash = d.hash
        WHERE d.active = 1
        """
    ).fetchall()

    # 使用 fnmatch 进行 glob 匹配
    results = []
    for row in rows:
        display_path = row["displayPath"]
        if fnmatch(display_path, pattern):
            results.append({
                "filepath": row["filepath"],
                "displayPath": display_path,
                "bodyLength": row["bodyLength"]
            })

    return results


# =============================================================================
# Index Health 检查
# =============================================================================


def get_index_health(db: Database) -> dict[str, Any]:
    """
    获取索引健康状态

    Returns:
        包含 needs_embedding, total_docs, days_stale 的字典
    """
    # 获取需要 embedding 的文档数量
    needs_embedding_count = len(db.get_hashes_for_embedding())

    # 获取总文档数
    total_docs_row = db.conn.execute(
        "SELECT COUNT(*) as cnt FROM documents WHERE active = 1"
    ).fetchone()
    total_docs = total_docs_row["cnt"] if total_docs_row else 0

    # 获取最旧文档的修改时间（简化实现，不计算天数）
    oldest_row = db.conn.execute(
        "SELECT modified_at FROM documents WHERE active = 1 ORDER BY modified_at ASC LIMIT 1"
    ).fetchone()

    # days_stale: 暂时返回 None（可以根据需要实现）
    days_stale = None

    return {
        "needs_embedding": needs_embedding_count,
        "total_docs": total_docs,
        "days_stale": days_stale
    }


def get_status(db: Database) -> dict[str, Any]:
    """
    获取完整的索引状态信息

    Returns:
        包含 total_documents, needs_embedding, has_vector_index, collections 的字典
    """
    # 检查 vectors_vec 表是否存在
    vec_table_exists = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='vectors_vec'"
    ).fetchone()
    has_vector_index = vec_table_exists is not None

    # 获取每个 collection 的统计
    collection_rows = db.conn.execute(
        """
        SELECT
            d.collection,
            COUNT(*) as doc_count
        FROM documents d
        WHERE d.active = 1
        GROUP BY d.collection
        """
    ).fetchall()

    collections = []
    for row in collection_rows:
        collections.append({
            "name": row["collection"],
            "doc_count": row["doc_count"]
        })

    # 总文档数
    total_docs_row = db.conn.execute(
        "SELECT COUNT(*) as cnt FROM documents WHERE active = 1"
    ).fetchone()
    total_documents = total_docs_row["cnt"] if total_docs_row else 0

    # 需要 embedding 的数量
    needs_embedding = len(db.get_hashes_for_embedding())

    return {
        "total_documents": total_documents,
        "needs_embedding": needs_embedding,
        "has_vector_index": has_vector_index,
        "collections": collections
    }


# =============================================================================
# Cleanup 操作
# =============================================================================


def cleanup_orphaned_vectors(db: Database) -> int:
    """
    清理孤立的向量（没有对应 active 文档的向量）

    Returns:
        删除的向量数量
    """
    # 删除 content_vectors 中没有对应 active 文档的记录
    deleted_cv = db.conn.execute(
        """
        DELETE FROM content_vectors
        WHERE hash NOT IN (
            SELECT DISTINCT hash FROM documents WHERE active = 1
        )
        """
    ).rowcount

    # 删除 vectors_vec 中没有对应 content_vectors 的记录
    deleted_vec = 0
    try:
        deleted_vec = db.conn.execute(
            """
            DELETE FROM vectors_vec
            WHERE hash_seq NOT IN (
                SELECT hash || '_' || seq FROM content_vectors
            )
            """
        ).rowcount
    except Exception:
        # vectors_vec 表可能不存在
        pass

    db.conn.commit()

    return deleted_cv + deleted_vec


def delete_inactive_documents(db: Database) -> int:
    """
    删除所有 active=0 的文档记录

    Returns:
        删除的文档数量
    """
    deleted = db.conn.execute(
        "DELETE FROM documents WHERE active = 0"
    ).rowcount

    db.conn.commit()

    return deleted


def vacuum_database(db: Database) -> None:
    """
    执行 VACUUM 压缩数据库
    """
    db.conn.execute("VACUUM")
