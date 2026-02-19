"""
qmd - 基于 RAG 的智能文档查询系统

提供轻量工厂函数，供 CLI 和 MCP 直接调用 store+retrieval。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from loguru import logger

from qmd.core.config import NamedCollection, load_config
from qmd.core.db import Database, ensure_db_dir, get_db_path, init_schema, open_database
from qmd.core.retrieval import SearchResult, search
from qmd.core.store import Store
from qmd.llm.base import LLMBackend

# Backend 类型
BackendType = Literal["auto", "llama_cpp", "sentence_tf"]


def create_store(db_path: str | Path | None = None) -> tuple[Database, Store]:
    """
    创建 store 实例（对标原版 createStore()）

    Args:
        db_path: 数据库路径，None 使用默认路径 ~/.config/qmd/qmd.db

    Returns:
        (Database, Store) 元组
    """
    if db_path is None:
        ensure_db_dir()
        db_path = get_db_path()
    elif isinstance(db_path, str):
        db_path = Path(db_path)

    logger.info(f"使用数据库: {db_path}")
    conn = open_database(db_path)
    init_schema(conn)
    db = Database(conn)
    store = Store(db)

    return db, store


def create_llm_backend(backend_type: BackendType = "auto") -> LLMBackend | None:
    """
    创建 LLM 后端（auto/llama_cpp/sentence_tf）

    Args:
        backend_type: LLM 后端选择
            - "auto": 优先 llama_cpp，fallback 到 sentence_tf
            - "llama_cpp": 强制使用 LlamaCppBackend
            - "sentence_tf": 强制使用 SentenceTransformerBackend

    Returns:
        LLM 后端实例或 None
    """
    if backend_type == "auto":
        # 优先尝试 llama_cpp
        try:
            from qmd.llm.llama_cpp import LlamaCppBackend
            logger.info("使用 LlamaCppBackend")
            return LlamaCppBackend()
        except ImportError as e:
            logger.warning(f"llama-cpp-python 不可用: {e}")

        # Fallback 到 sentence_tf
        try:
            from qmd.llm.sentence_tf import SentenceTransformerBackend
            logger.info("使用 SentenceTransformerBackend (fallback)")
            return SentenceTransformerBackend()
        except ImportError as e:
            logger.warning(f"sentence-transformers 不可用: {e}")

        logger.warning("没有可用的 LLM 后端，某些功能受限")
        return None

    elif backend_type == "llama_cpp":
        from qmd.llm.llama_cpp import LlamaCppBackend
        logger.info("使用 LlamaCppBackend")
        return LlamaCppBackend()

    elif backend_type == "sentence_tf":
        from qmd.llm.sentence_tf import SentenceTransformerBackend
        logger.info("使用 SentenceTransformerBackend")
        return SentenceTransformerBackend()

    else:
        raise ValueError(f"未知的 backend 类型: {backend_type}")


__all__ = [
    "create_store",
    "create_llm_backend",
    "Database",
    "Store",
    "SearchResult",
    "search",
    "NamedCollection",
    "load_config",
    "BackendType",
    "LLMBackend",
]
