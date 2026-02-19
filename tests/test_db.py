"""db.py 单元测试。"""

import sqlite3

import pytest

from qmd.core.db import (
    Database,
    ensure_db_dir,
    ensure_vec_table,
    get_cache_key,
    get_db_path,
    init_schema,
    open_database,
)


class TestOpenDatabase:
    """数据库连接测试。"""

    def test_open_memory(self) -> None:
        """内存数据库可正常打开。"""
        conn = open_database(":memory:")
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_row_factory(self) -> None:
        """row_factory 设置为 sqlite3.Row。"""
        conn = open_database(":memory:")
        conn.execute("CREATE TABLE t (a TEXT)")
        conn.execute("INSERT INTO t VALUES ('hello')")
        row = conn.execute("SELECT a FROM t").fetchone()
        assert row["a"] == "hello"
        conn.close()

    def test_sqlite_vec_loaded(self) -> None:
        """sqlite-vec 扩展成功加载。"""
        conn = open_database(":memory:")
        # vec_version() 是 sqlite-vec 提供的函数
        row = conn.execute("SELECT vec_version()").fetchone()
        assert row is not None
        conn.close()


class TestInitSchema:
    """Schema 初始化测试。"""

    def test_tables_created(self) -> None:
        """所有核心表被创建。"""
        conn = open_database(":memory:")
        init_schema(conn)

        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger')"
            ).fetchall()
        }
        assert "content" in tables
        assert "documents" in tables
        assert "llm_cache" in tables
        assert "content_vectors" in tables
        assert "documents_fts" in tables
        # 触发器
        assert "documents_ai" in tables
        assert "documents_ad" in tables
        assert "documents_au" in tables
        conn.close()

    def test_idempotent(self) -> None:
        """init_schema 可重复执行。"""
        conn = open_database(":memory:")
        init_schema(conn)
        init_schema(conn)  # 第二次不报错
        conn.close()


class TestFTS5:
    """FTS5 全文索引测试。"""

    def test_fts_insert_via_trigger(self) -> None:
        """通过触发器自动同步 FTS。"""
        conn = open_database(":memory:")
        init_schema(conn)

        # 插入 content
        conn.execute(
            "INSERT INTO content (hash, doc, created_at) VALUES (?, ?, ?)",
            ("abc123", "这是一篇关于机器学习的文档", "2026-02-18"),
        )
        # 插入 document（触发器会自动写 FTS）
        conn.execute(
            "INSERT INTO documents (collection, path, title, hash, created_at, modified_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("notes", "ml.md", "机器学习笔记", "abc123", "2026-02-18", "2026-02-18"),
        )
        conn.commit()

        # FTS 搜索（用英文路径验证触发器，porter tokenizer 对中文分词有限）
        results = conn.execute(
            "SELECT filepath, title FROM documents_fts WHERE documents_fts MATCH ?",
            ("ml",),
        ).fetchall()
        assert len(results) >= 1
        assert results[0]["filepath"] == "notes/ml.md"
        conn.close()

    def test_fts_bm25(self) -> None:
        """BM25 评分可用。"""
        conn = open_database(":memory:")
        init_schema(conn)

        conn.execute(
            "INSERT INTO content (hash, doc, created_at) VALUES (?, ?, ?)",
            ("h1", "深度学习是机器学习的子领域", "2026-02-18"),
        )
        conn.execute(
            "INSERT INTO documents (collection, path, title, hash, created_at, modified_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("notes", "dl.md", "深度学习", "h1", "2026-02-18", "2026-02-18"),
        )
        conn.commit()

        results = conn.execute(
            "SELECT filepath, bm25(documents_fts, 10.0, 1.0, 1.0) as score "
            "FROM documents_fts WHERE documents_fts MATCH ?",
            ("深度学习",),
        ).fetchall()
        assert len(results) >= 1
        assert results[0]["score"] < 0  # BM25 返回负分（越低越好）
        conn.close()


class TestVecTable:
    """sqlite-vec 向量表测试。"""

    def test_ensure_vec_table(self) -> None:
        """向量虚拟表创建成功。"""
        conn = open_database(":memory:")
        init_schema(conn)
        ensure_vec_table(conn, dimensions=768)

        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "vectors_vec" in tables
        conn.close()

    def test_ensure_vec_table_idempotent(self) -> None:
        """重复调用不报错。"""
        conn = open_database(":memory:")
        init_schema(conn)
        ensure_vec_table(conn, 768)
        ensure_vec_table(conn, 768)  # 第二次不报错
        conn.close()


class TestPaths:
    """路径工具测试。"""

    def test_get_db_path(self) -> None:
        """默认路径包含 qmd.db。"""
        p = get_db_path()
        assert p.name == "qmd.db"
        assert "qmd" in str(p)

    def test_ensure_db_dir(self, tmp_path: object) -> None:
        """确保目录创建。"""
        from pathlib import Path

        d = Path(str(tmp_path)) / "test_qmd"
        ensure_db_dir(d)
        assert d.exists()


class TestLLMCache:
    """LLM Cache 功能测试。"""

    def test_get_cache_key_deterministic(self) -> None:
        """相同参数生成相同 cache key。"""
        params = {"query": "test query", "limit": 10}
        key1 = get_cache_key("expandQuery", params)
        key2 = get_cache_key("expandQuery", params)
        assert key1 == key2
        assert len(key1) == 64  # SHA-256 生成 64 个十六进制字符

    def test_get_cache_key_different_params(self) -> None:
        """不同参数生成不同 cache key。"""
        key1 = get_cache_key("expandQuery", {"query": "test"})
        key2 = get_cache_key("expandQuery", {"query": "test2"})
        key3 = get_cache_key("rerank", {"query": "test"})
        assert key1 != key2
        assert key1 != key3
        assert key2 != key3

    def test_set_and_get_cached_result(self) -> None:
        """写入缓存后可以读取。"""
        conn = open_database(":memory:")
        init_schema(conn)
        db = Database(conn)

        cache_key = get_cache_key("test", {"a": 1})
        db.set_cached_result(cache_key, "result123")

        result = db.get_cached_result(cache_key)
        assert result == "result123"
        conn.close()

    def test_get_cached_result_miss(self) -> None:
        """不存在的 key 返回 None。"""
        conn = open_database(":memory:")
        init_schema(conn)
        db = Database(conn)

        result = db.get_cached_result("nonexistent_key")
        assert result is None
        conn.close()

    def test_clear_cache(self) -> None:
        """清空缓存后所有 key 都 miss。"""
        conn = open_database(":memory:")
        init_schema(conn)
        db = Database(conn)

        # 写入多个缓存
        key1 = get_cache_key("op1", {"a": 1})
        key2 = get_cache_key("op2", {"b": 2})
        db.set_cached_result(key1, "result1")
        db.set_cached_result(key2, "result2")

        # 清空
        count = db.clear_cache()
        assert count == 2

        # 验证都 miss
        assert db.get_cached_result(key1) is None
        assert db.get_cached_result(key2) is None
        conn.close()
