"""SQLite 连接管理 + schema 初始化。

- 启动时检查 SQLite >= 3.34（FTS5 trigram tokenizer 需要）。
- 加载 sqlite-vec 扩展。
- 执行幂等 schema。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec

from qmd.core.embedding import Embedder


_MIN_SQLITE = (3, 34, 0)


SCHEMA_SQL: str = f"""
CREATE TABLE IF NOT EXISTS collections (
    name       TEXT PRIMARY KEY,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    collection  TEXT NOT NULL,
    id          TEXT NOT NULL,
    markdown    TEXT NOT NULL,
    metadata    TEXT NOT NULL,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL,
    PRIMARY KEY (collection, id),
    FOREIGN KEY (collection) REFERENCES collections(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chunks (
    rowid       INTEGER PRIMARY KEY AUTOINCREMENT,
    collection  TEXT NOT NULL,
    document_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text        TEXT NOT NULL,
    char_start  INTEGER NOT NULL,
    char_end    INTEGER NOT NULL,
    FOREIGN KEY (collection, document_id)
        REFERENCES documents(collection, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(collection, document_id);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    tokenize='trigram'
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
    embedding FLOAT[{Embedder.DIM}]
);
"""


def _check_sqlite_version() -> None:
    if sqlite3.sqlite_version_info < _MIN_SQLITE:
        raise RuntimeError(
            f"qmd 需要 SQLite >= 3.34（FTS5 trigram 分词器），"
            f"当前版本 {sqlite3.sqlite_version}"
        )


def open_connection(db_path: str | Path) -> sqlite3.Connection:
    """打开连接、加载 sqlite-vec、执行 schema。幂等。"""
    _check_sqlite_version()
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None：autocommit，事务由调用方（collection.py）显式 BEGIN/COMMIT
    # check_same_thread=False：允许多线程使用；sqlite3 自身的串行化由 collection.py 的 Lock 保障
    conn = sqlite3.connect(str(p), isolation_level=None, check_same_thread=False)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn
