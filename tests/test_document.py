"""
测试文档检索辅助函数
"""

from pathlib import Path

import pytest

from qmd.core.db import Database, init_schema, open_database
from qmd.core.document import (
    cleanup_orphaned_vectors,
    delete_inactive_documents,
    find_document_by_docid,
    find_similar_files,
    get_index_health,
    get_status,
    is_docid,
    match_files_by_glob,
    normalize_docid,
    vacuum_database,
)


@pytest.fixture
def test_db(tmp_path: Path) -> Database:
    """创建测试数据库"""
    db_path = tmp_path / "test.db"
    conn = open_database(db_path)
    init_schema(conn)
    db = Database(conn)

    # 插入测试数据
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    # 插入 content
    db.insert_content("abc123def456", "Test document 1", now)
    db.insert_content("xyz789ghi012", "Test document 2", now)
    db.insert_content("orphan123456", "Orphaned content", now)

    # 插入 documents
    db.insert_document("docs", "file1.md", "File 1", "abc123def456", now, now)
    db.insert_document("docs", "file2.md", "File 2", "xyz789ghi012", now, now)
    db.insert_document("notes", "note.md", "Note", "abc123def456", now, now)

    # 插入一个 inactive 文档
    db.conn.execute(
        """
        INSERT INTO documents (collection, path, title, hash, created_at, modified_at, active)
        VALUES ('docs', 'inactive.md', 'Inactive', 'abc123def456', ?, ?, 0)
        """,
        (now, now)
    )
    db.conn.commit()

    return db


class TestDocidFunctions:
    """测试 docid 相关函数"""

    def test_normalize_docid(self):
        """测试 docid 规范化"""
        assert normalize_docid("#abc123") == "abc123"
        assert normalize_docid("abc123") == "abc123"
        assert normalize_docid('"#abc123"') == "abc123"
        assert normalize_docid("'abc123'") == "abc123"
        assert normalize_docid('"abc123"') == "abc123"
        assert normalize_docid("  #abc123  ") == "abc123"

    def test_is_docid(self):
        """测试 docid 格式检查"""
        assert is_docid("#abc123") is True
        assert is_docid("abc123") is True
        assert is_docid('"abc123"') is True
        assert is_docid("abcdef0123456789") is True

        # 无效格式
        assert is_docid("abc") is False  # 太短
        assert is_docid("xyz") is False  # 太短且非十六进制
        assert is_docid("hello world") is False  # 非十六进制
        assert is_docid("") is False

    def test_find_document_by_docid(self, test_db: Database):
        """测试通过 docid 查找文档"""
        # 查找存在的文档
        result = find_document_by_docid(test_db, "#abc123")
        assert result is not None
        assert result["hash"] == "abc123def456"
        assert "qmd://" in result["filepath"]

        # 查找不存在的 docid
        result = find_document_by_docid(test_db, "#ffffff")
        assert result is None

        # 空 docid
        result = find_document_by_docid(test_db, "")
        assert result is None


class TestFileFinding:
    """测试文件查找函数"""

    def test_find_similar_files(self, test_db: Database):
        """测试相似文件查找（使用 difflib 相似度）"""
        # 查找与 "file1.md" 相似的文件
        results = find_similar_files(test_db, "file1.md", min_similarity=0.5, limit=5)
        assert "file1.md" in results
        assert "file2.md" in results

        # 查找与 "note" 相似的文件
        results = find_similar_files(test_db, "note", min_similarity=0.3, limit=5)
        assert "note.md" in results

    def test_match_files_by_glob(self, test_db: Database):
        """测试 glob 模式匹配"""
        # 匹配所有 .md 文件
        results = match_files_by_glob(test_db, "*.md")
        assert len(results) >= 3

        # 匹配特定文件
        results = match_files_by_glob(test_db, "file?.md")
        file_names = [r["displayPath"] for r in results]
        assert "file1.md" in file_names
        assert "file2.md" in file_names


class TestIndexHealth:
    """测试索引健康检查"""

    def test_get_index_health(self, test_db: Database):
        """测试获取索引健康状态"""
        health = get_index_health(test_db)

        assert "needs_embedding" in health
        assert "total_docs" in health
        assert "days_stale" in health

        # 应该有 3 个 active 文档
        assert health["total_docs"] == 3

    def test_get_status(self, test_db: Database):
        """测试获取完整状态"""
        status = get_status(test_db)

        assert "total_documents" in status
        assert "needs_embedding" in status
        assert "has_vector_index" in status
        assert "collections" in status

        # 应该有 3 个 active 文档
        assert status["total_documents"] == 3

        # 应该有 2 个 collections
        assert len(status["collections"]) == 2

        # 检查 collection 统计
        coll_names = [c["name"] for c in status["collections"]]
        assert "docs" in coll_names
        assert "notes" in coll_names


class TestCleanup:
    """测试清理操作"""

    def test_cleanup_orphaned_vectors(self, test_db: Database):
        """测试清理孤立向量"""
        # 插入一些孤立的 content_vectors
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        test_db.conn.execute(
            "INSERT INTO content_vectors (hash, seq, pos, model, embedded_at) VALUES (?, ?, ?, ?, ?)",
            ("orphan123456", 0, 0, "test", now)
        )
        test_db.conn.commit()

        # 清理孤立向量
        deleted = cleanup_orphaned_vectors(test_db)
        assert deleted >= 1

    def test_delete_inactive_documents(self, test_db: Database):
        """测试删除 inactive 文档"""
        # 应该有 1 个 inactive 文档
        deleted = delete_inactive_documents(test_db)
        assert deleted == 1

        # 再次删除应该返回 0
        deleted = delete_inactive_documents(test_db)
        assert deleted == 0

    def test_vacuum_database(self, test_db: Database):
        """测试 VACUUM 操作"""
        # VACUUM 应该正常执行（不抛出异常）
        vacuum_database(test_db)
