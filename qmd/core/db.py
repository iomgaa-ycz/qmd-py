"""SQLite 数据库抽象层。

忠实移植 qmd (TypeScript) 的存储 schema。
负责：数据库连接管理、sqlite-vec 加载、FTS5 初始化、所有表的创建。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

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
    # check_same_thread=False 允许跨线程使用（watcher 需要）
    # 注意：需要通过锁或其他机制确保线程安全
    conn = sqlite3.connect(str(path), check_same_thread=False)
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
    metadata TEXT NOT NULL DEFAULT '{}',
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
    # 旧库迁移：补充 metadata 列
    cols = {row[1] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
    if "metadata" not in cols:
        conn.execute("ALTER TABLE documents ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
        conn.commit()
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


# ---------------------------------------------------------------------------
# Database 类 —— 封装所有数据库操作
# ---------------------------------------------------------------------------


class Database:
    """数据库操作封装类

    提供文档、内容、向量的 CRUD 操作。
    """

    def __init__(self, conn: sqlite3.Connection):
        """初始化数据库实例

        Args:
            conn: SQLite 连接
        """
        self.conn = conn

    # === Content 操作 ===

    def get_content_by_hash(self, content_hash: str) -> str | None:
        """根据哈希获取文档内容

        Args:
            content_hash: 内容 SHA256 哈希

        Returns:
            文档内容，如果不存在返回 None
        """
        row = self.conn.execute(
            "SELECT doc FROM content WHERE hash = ?", (content_hash,)
        ).fetchone()
        return row["doc"] if row else None

    def insert_content(self, content_hash: str, content: str, created_at: str) -> None:
        """插入内容（content-addressable 存储）

        使用 INSERT OR IGNORE，重复 hash 会被跳过。

        Args:
            content_hash: 内容 SHA256 哈希
            content: 文档内容
            created_at: 创建时间（ISO 8601）
        """
        self.conn.execute(
            "INSERT OR IGNORE INTO content (hash, doc, created_at) VALUES (?, ?, ?)",
            (content_hash, content, created_at),
        )
        self.conn.commit()

    # === Document 操作 ===

    def insert_document(
        self,
        collection: str,
        path: str,
        title: str,
        content_hash: str,
        created_at: str,
        modified_at: str,
        metadata: str = "{}",
    ) -> None:
        """插入文档记录

        使用 UPSERT（ON CONFLICT ... DO UPDATE），冲突时更新。

        Args:
            collection: 集合名称
            path: 文档路径（normalized）
            title: 文档标题
            content_hash: 内容哈希
            created_at: 创建时间
            modified_at: 修改时间
            metadata: JSON 字符串形式的附加元数据
        """
        self.conn.execute(
            """
            INSERT INTO documents (collection, path, title, hash, created_at, modified_at, active, metadata)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(collection, path) DO UPDATE SET
                title = excluded.title,
                hash = excluded.hash,
                modified_at = excluded.modified_at,
                active = 1,
                metadata = excluded.metadata
            """,
            (collection, path, title, content_hash, created_at, modified_at, metadata),
        )
        self.conn.commit()

    def find_active_document(
        self, collection: str, path: str
    ) -> dict[str, Any] | None:
        """查找活跃文档

        Args:
            collection: 集合名称
            path: 文档路径

        Returns:
            文档字典（包含 id, hash, title）或 None
        """
        row = self.conn.execute(
            "SELECT id, hash, title FROM documents WHERE collection = ? AND path = ? AND active = 1",
            (collection, path),
        ).fetchone()

        if row:
            return {"id": row["id"], "hash": row["hash"], "title": row["title"]}
        return None

    def update_document_title(
        self, document_id: int, title: str, modified_at: str
    ) -> None:
        """更新文档标题

        Args:
            document_id: 文档 ID
            title: 新标题
            modified_at: 修改时间
        """
        self.conn.execute(
            "UPDATE documents SET title = ?, modified_at = ? WHERE id = ?",
            (title, modified_at, document_id),
        )
        self.conn.commit()

    def update_document(
        self, document_id: int, title: str, content_hash: str, modified_at: str
    ) -> None:
        """更新文档（hash + title）

        Args:
            document_id: 文档 ID
            title: 新标题
            content_hash: 新内容哈希
            modified_at: 修改时间
        """
        self.conn.execute(
            "UPDATE documents SET title = ?, hash = ?, modified_at = ? WHERE id = ?",
            (title, content_hash, modified_at, document_id),
        )
        self.conn.commit()

    def deactivate_document(self, collection: str, path: str) -> None:
        """停用文档（标记为 inactive）

        Args:
            collection: 集合名称
            path: 文档路径
        """
        self.conn.execute(
            "UPDATE documents SET active = 0 WHERE collection = ? AND path = ? AND active = 1",
            (collection, path),
        )
        self.conn.commit()

    def get_active_document_paths(self, collection: str) -> list[str]:
        """获取集合中所有活跃文档路径

        Args:
            collection: 集合名称

        Returns:
            路径列表
        """
        rows = self.conn.execute(
            "SELECT path FROM documents WHERE collection = ? AND active = 1",
            (collection,),
        ).fetchall()
        return [row["path"] for row in rows]

    def get_document_count(self, collection: str, filters: dict | None = None) -> int:
        """获取集合中活跃文档数量

        Args:
            collection: 集合名称
            filters: metadata 过滤条件（可选）

        Returns:
            文档数量
        """
        import json
        where_clauses = ["collection = ?", "active = 1"]
        params: list[Any] = [collection]
        for key, value in (filters or {}).items():
            where_clauses.append(f"json_extract(metadata, '$.{key}') = ?")
            params.append(value)
        sql = f"SELECT COUNT(*) as cnt FROM documents WHERE {' AND '.join(where_clauses)}"
        row = self.conn.execute(sql, params).fetchone()
        return row["cnt"] if row else 0

    def delete_documents(self, collection: str, filters: dict) -> int:
        """按 metadata 条件删除活跃文档（标记为 inactive）。

        Args:
            collection: 集合名称
            filters: metadata 过滤条件（必填）

        Returns:
            标记为 inactive 的文档数
        """
        where_clauses = ["collection = ?", "active = 1"]
        params: list[Any] = [collection]
        for key, value in filters.items():
            where_clauses.append(f"json_extract(metadata, '$.{key}') = ?")
            params.append(value)
        sql = f"UPDATE documents SET active = 0 WHERE {' AND '.join(where_clauses)}"
        cursor = self.conn.execute(sql, params)
        self.conn.commit()
        return cursor.rowcount

    # === Embedding 操作 ===

    def insert_embedding(
        self,
        content_hash: str,
        seq: int,
        pos: int,
        embedding: list[float],
        model: str,
        embedded_at: str,
    ) -> None:
        """插入 embedding

        插入到 content_vectors 和 vectors_vec 两张表。

        Args:
            content_hash: 内容哈希
            seq: chunk 序号
            pos: chunk 在文档中的位置
            embedding: 向量（float 列表）
            model: 模型名称
            embedded_at: 生成时间
        """
        import struct

        hash_seq = f"{content_hash}_{seq}"

        # 插入 content_vectors
        self.conn.execute(
            "INSERT OR REPLACE INTO content_vectors (hash, seq, pos, model, embedded_at) VALUES (?, ?, ?, ?, ?)",
            (content_hash, seq, pos, model, embedded_at),
        )

        # 将 list[float] 转换为字节（sqlite-vec 需要 blob）
        embedding_bytes = struct.pack(f"{len(embedding)}f", *embedding)

        # 插入 vectors_vec
        self.conn.execute(
            "DELETE FROM vectors_vec WHERE hash_seq = ?",
            (hash_seq,),
        )
        self.conn.execute(
            "INSERT INTO vectors_vec (hash_seq, embedding) VALUES (?, ?)",
            (hash_seq, embedding_bytes),
        )

        self.conn.commit()

    def get_hashes_for_embedding(self) -> list[dict[str, Any]]:
        """获取需要 embedding 的 content hash

        返回所有活跃文档中，尚未生成 embedding 的 content。

        Returns:
            字典列表，每个包含 hash、content、path
        """
        rows = self.conn.execute(
            """
            SELECT c.hash, c.doc as content, MIN(d.path) as path
            FROM content c
            JOIN documents d ON c.hash = d.hash
            LEFT JOIN content_vectors cv ON c.hash = cv.hash
            WHERE d.active = 1 AND cv.hash IS NULL
            GROUP BY c.hash, c.doc
            """
        ).fetchall()

        return [
            {"hash": row["hash"], "content": row["content"], "path": row["path"]}
            for row in rows
        ]

    def clear_all_embeddings(self) -> None:
        """清空所有 embedding（强制重新生成）"""
        self.conn.execute("DELETE FROM content_vectors")
        self.conn.execute("DELETE FROM vectors_vec")
        self.conn.commit()

    # === 清理操作 ===

    def cleanup_orphaned_content(self) -> int:
        """清理孤立的 content（没有任何活跃文档引用）

        Returns:
            删除的 content 数量
        """
        cursor = self.conn.execute(
            """
            DELETE FROM content
            WHERE hash NOT IN (
                SELECT DISTINCT hash FROM documents WHERE active = 1
            )
            """
        )
        self.conn.commit()
        return cursor.rowcount

    # === LLM Cache 操作 ===

    def get_cached_result(self, cache_key: str) -> str | None:
        """从 llm_cache 表读取缓存结果

        Args:
            cache_key: 缓存键（SHA-256 hash）

        Returns:
            缓存的结果字符串，如果不存在返回 None
        """
        row = self.conn.execute(
            "SELECT result FROM llm_cache WHERE hash = ?", (cache_key,)
        ).fetchone()
        return row["result"] if row else None

    def set_cached_result(self, cache_key: str, result: str) -> None:
        """写入缓存结果到 llm_cache 表

        Args:
            cache_key: 缓存键（SHA-256 hash）
            result: 要缓存的结果字符串
        """
        from datetime import datetime, timezone

        self.conn.execute(
            "INSERT OR REPLACE INTO llm_cache (hash, result, created_at) VALUES (?, ?, ?)",
            (cache_key, result, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def clear_cache(self) -> int:
        """清空所有缓存

        Returns:
            删除的缓存条目数
        """
        cursor = self.conn.execute("DELETE FROM llm_cache")
        self.conn.commit()
        return cursor.rowcount


# ---------------------------------------------------------------------------
# LLM Cache 工具函数
# ---------------------------------------------------------------------------


def get_cache_key(operation: str, params: dict[str, Any]) -> str:
    """生成缓存 key（SHA-256 hash of operation + sorted params JSON）

    参考原版 getCacheKey():
    - key = SHA-256(operation + JSON.stringify(params, sorted keys))

    Args:
        operation: 操作名称（如 "expandQuery", "rerank"）
        params: 参数字典

    Returns:
        SHA-256 hash 字符串（64 个十六进制字符）
    """
    import hashlib
    import json

    raw = operation + json.dumps(params, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()
