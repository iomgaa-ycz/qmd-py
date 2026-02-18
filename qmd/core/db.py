"""SQLite 数据库抽象层。

忠实移植 qmd (TypeScript) 的存储 schema。
负责：数据库连接管理、sqlite-vec 加载、FTS5 初始化、所有表的创建。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from loguru import logger

# ---------------------------------------------------------------------------
# 路径管理
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_DIR = Path.home() / ".config" / "qmd"


def get_db_path(config_dir: Path | None = None) -> Path:
    """返回默认数据库路径 ~/.config/qmd/qmd.db"""
    d = config_dir or _DEFAULT_CONFIG_DIR
    return d / "qmd.db"


def ensure_db_dir(config_dir: Path | None = None) -> None:
    """确保数据库目录存在。"""
    d = config_dir or _DEFAULT_CONFIG_DIR
    d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 连接管理
# ---------------------------------------------------------------------------


def open_database(path: str | Path = ":memory:") -> sqlite3.Connection:
    """打开 SQLite 数据库，加载 sqlite-vec 扩展，设置 WAL 模式。

    Args:
        path: 数据库路径，默认内存数据库。

    Returns:
        已配置好的 sqlite3.Connection。
    """
    conn = sqlite3.connect(str(path))
    conn.enable_load_extension(True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # 加载 sqlite-vec
    try:
        import sqlite_vec

        sqlite_vec.load(conn)
        logger.debug("sqlite-vec 扩展已加载")
    except Exception as e:
        logger.warning(f"sqlite-vec 加载失败: {e}")

    return conn


# ---------------------------------------------------------------------------
# Schema 初始化
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
-- 内容寻址存储 —— 文档内容的唯一真相源
CREATE TABLE IF NOT EXISTS content (
    hash TEXT PRIMARY KEY,
    doc TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 文档元数据 —— 文件系统层，将虚拟路径映射到内容哈希
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    modified_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (hash) REFERENCES content(hash) ON DELETE CASCADE,
    UNIQUE(collection, path)
);

CREATE INDEX IF NOT EXISTS idx_documents_collection
    ON documents(collection, active);
CREATE INDEX IF NOT EXISTS idx_documents_hash
    ON documents(hash);
CREATE INDEX IF NOT EXISTS idx_documents_path
    ON documents(path, active);

-- LLM 缓存表
CREATE TABLE IF NOT EXISTS llm_cache (
    hash TEXT PRIMARY KEY,
    result TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 向量 chunk 到文档的映射
CREATE TABLE IF NOT EXISTS content_vectors (
    hash TEXT NOT NULL,
    seq INTEGER NOT NULL DEFAULT 0,
    pos INTEGER NOT NULL DEFAULT 0,
    model TEXT NOT NULL,
    embedded_at TEXT NOT NULL,
    PRIMARY KEY (hash, seq)
);

-- FTS5 全文索引（filepath、title、body）
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    filepath, title, body,
    tokenize='porter unicode61'
);

-- 触发器：INSERT 时同步 FTS
CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents
WHEN new.active = 1
BEGIN
    INSERT INTO documents_fts(rowid, filepath, title, body)
    SELECT
        new.id,
        new.collection || '/' || new.path,
        new.title,
        (SELECT doc FROM content WHERE hash = new.hash)
    WHERE new.active = 1;
END;

-- 触发器：DELETE 时同步 FTS
CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents
BEGIN
    DELETE FROM documents_fts WHERE rowid = old.id;
END;

-- 触发器：UPDATE 时同步 FTS
CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents
BEGIN
    DELETE FROM documents_fts WHERE rowid = old.id AND new.active = 0;
    INSERT OR REPLACE INTO documents_fts(rowid, filepath, title, body)
    SELECT
        new.id,
        new.collection || '/' || new.path,
        new.title,
        (SELECT doc FROM content WHERE hash = new.hash)
    WHERE new.active = 1;
END;
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """创建所有核心表、索引和触发器。

    不包括 vectors_vec（维度需运行时确定，由 ensure_vec_table 处理）。
    """
    conn.executescript(_SCHEMA_SQL)
    logger.debug("数据库 schema 初始化完成")


def ensure_vec_table(conn: sqlite3.Connection, dimensions: int = 768) -> None:
    """创建或重建 sqlite-vec 虚拟表。

    如果已存在但维度或配置不匹配，会先 DROP 再重建。

    Args:
        conn: 数据库连接（需已加载 sqlite-vec）。
        dimensions: 向量维度，默认 768（embeddinggemma-300M）。
    """
    # 检查是否已存在
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='vectors_vec'"
    ).fetchone()

    if row:
        sql_text: str = row["sql"] or ""
        # 检查维度和配置是否匹配
        expected_fragment = f"float[{dimensions}]"
        has_hash_seq = "hash_seq" in sql_text
        has_cosine = "cosine" in sql_text
        has_dims = expected_fragment in sql_text
        if has_hash_seq and has_cosine and has_dims:
            return  # 已存在且配置正确
        # 配置不匹配，重建
        logger.info(f"vectors_vec 配置不匹配，重建（维度={dimensions}）")
        conn.execute("DROP TABLE IF EXISTS vectors_vec")

    conn.execute(
        f"CREATE VIRTUAL TABLE vectors_vec USING vec0("
        f"hash_seq TEXT PRIMARY KEY, "
        f"embedding float[{dimensions}] distance_metric=cosine"
        f")"
    )
    logger.debug(f"vectors_vec 已创建（维度={dimensions}）")
