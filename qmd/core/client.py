"""SqliteQmdClient — 真实 SQLite 后端的 QmdClient Protocol 实现。"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from qmd.core.collection import SqliteCollection
from qmd.core.db import open_connection
from qmd.core.embedding import Embedder
from qmd.models import CollectionInfo


class SqliteQmdClient:
    """基于 SQLite + sqlite-vec 的 QmdClient 实现。

    线程安全：所有写操作通过共享 Lock 串行化。
    连接生命周期：构造时打开，close() 后不可再用。
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection = open_connection(self._db_path)
        self._lock = threading.Lock()
        self._embedder = Embedder()
        self._collections: dict[str, SqliteCollection] = {}

    def collection(self, name: str) -> SqliteCollection:
        """取得指定 collection；不存在时自动创建。"""
        with self._lock:
            if name not in self._collections:
                self._conn.execute(
                    "INSERT OR IGNORE INTO collections(name, created_at) VALUES (?, ?)",
                    (name, int(time.time() * 1000)),
                )
                self._conn.commit()
                self._collections[name] = SqliteCollection(
                    conn=self._conn,
                    name=name,
                    lock=self._lock,
                    embedder=self._embedder,
                )
            return self._collections[name]

    def list_collections(self) -> list[CollectionInfo]:
        """列出所有 collection 的元信息，按名称字母序排列。"""
        with self._lock:
            names = [
                r[0]
                for r in self._conn.execute(
                    "SELECT name FROM collections ORDER BY name"
                ).fetchall()
            ]
        return [self.collection(n).info() for n in names]

    def delete_collection(self, name: str) -> None:
        """删除 collection 及其所有文档和 chunks。不存在时静默 no-op。"""
        with self._lock:
            rowids = [
                r[0]
                for r in self._conn.execute(
                    "SELECT rowid FROM chunks WHERE collection=?", (name,)
                ).fetchall()
            ]
            cur = self._conn.cursor()
            try:
                cur.execute("BEGIN")
                for rowid in rowids:
                    cur.execute("DELETE FROM chunks_fts WHERE rowid=?", (rowid,))
                    cur.execute("DELETE FROM chunks_vec WHERE rowid=?", (rowid,))
                # collections 级联删除 → documents 级联删除 → chunks
                cur.execute("DELETE FROM collections WHERE name=?", (name,))
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            self._collections.pop(name, None)

    def close(self) -> None:
        """关闭 SQLite 连接，释放所有资源。"""
        with self._lock:
            self._conn.close()
            self._collections.clear()
