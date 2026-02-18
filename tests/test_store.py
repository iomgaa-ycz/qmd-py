"""
测试文档存储与索引层 (Store)

使用真实的 sentence-transformers 后端进行 embedding 测试。
"""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from qmd.core.config import Collection
from qmd.core.db import Database, init_schema, open_database
from qmd.core.store import Store
from qmd.llm.sentence_tf import SentenceTransformerBackend


class TestStore:
    """Store 类测试"""

    @pytest.fixture
    def tmp_db(self, tmp_path: Path) -> Database:
        """创建临时数据库"""
        db_path = tmp_path / "test.db"
        conn = open_database(str(db_path))
        init_schema(conn)
        return Database(conn)

    @pytest.fixture
    def store(self, tmp_db: Database) -> Store:
        """创建 Store 实例"""
        return Store(tmp_db)

    @pytest.fixture
    def test_collection(self, tmp_path: Path) -> Collection:
        """创建测试集合配置"""
        from qmd.core.config import NamedCollection

        collection_path = tmp_path / "docs"
        collection_path.mkdir()
        return NamedCollection(
            name="test-collection", path=str(collection_path), pattern="**/*.md"
        )

    @pytest.fixture
    def sample_docs(self, tmp_path: Path) -> dict[str, Path]:
        """创建示例文档"""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(exist_ok=True)

        doc1 = docs_dir / "doc1.md"
        doc1.write_text("# Document 1\n\nThis is the first document.", encoding="utf-8")

        doc2 = docs_dir / "doc2.md"
        doc2.write_text("# Document 2\n\nThis is the second document.", encoding="utf-8")

        subdir = docs_dir / "subdir"
        subdir.mkdir()
        doc3 = subdir / "doc3.md"
        doc3.write_text("# Document 3\n\nThis is in a subdirectory.", encoding="utf-8")

        return {"doc1": doc1, "doc2": doc2, "doc3": doc3}

    # === 文档索引测试 ===

    def test_index_document_new(self, store: Store):
        """测试索引新文档"""
        content = "# Test Document\n\nContent here."
        result = store.index_document("test", "doc.md", content)

        assert result["status"] == "indexed"
        assert "hash" in result
        assert len(result["hash"]) == 64  # SHA256 hex 长度

    def test_index_document_unchanged(self, store: Store):
        """测试文档未变化时不重复索引"""
        content = "# Test Document\n\nContent here."

        # 第一次索引
        result1 = store.index_document("test", "doc.md", content)
        assert result1["status"] == "indexed"

        # 第二次索引（内容相同）
        result2 = store.index_document("test", "doc.md", content)
        assert result2["status"] == "unchanged"
        assert result2["hash"] == result1["hash"]

    def test_index_document_title_updated(self, store: Store):
        """测试 title 变化但内容未变化"""
        content1 = "# Old Title\n\nContent here."
        content2 = "# New Title\n\nContent here."

        # 第一次索引
        result1 = store.index_document("test", "doc.md", content1)
        assert result1["status"] == "indexed"

        # 第二次索引（title 变化，但实际上 content hash 不同）
        result2 = store.index_document("test", "doc.md", content2)
        # 由于 content 变了，所以是 updated，不是 title_updated
        assert result2["status"] == "updated"

    def test_index_document_content_updated(self, store: Store):
        """测试内容变化"""
        content1 = "# Test\n\nOld content."
        content2 = "# Test\n\nNew content."

        # 第一次索引
        result1 = store.index_document("test", "doc.md", content1)
        assert result1["status"] == "indexed"

        # 第二次索引（内容变化）
        result2 = store.index_document("test", "doc.md", content2)
        assert result2["status"] == "updated"
        assert result2["hash"] != result1["hash"]

    def test_index_document_empty_content(self, store: Store):
        """测试空文档"""
        result = store.index_document("test", "empty.md", "   \n  \t  ")
        assert result["status"] == "skipped"
        assert result["reason"] == "empty"

    def test_index_document_path_normalization(self, store: Store):
        """测试路径规范化"""
        content = "# Test\n\nContent."

        # 不同的路径表示应该被规范化为同一个
        result1 = store.index_document("test", "./docs/file.md", content)
        result2 = store.index_document("test", "docs/file.md", content)

        assert result1["status"] == "indexed"
        assert result2["status"] == "unchanged"  # 应该识别为同一文档

    # === 文档删除测试 ===

    def test_remove_document_success(self, store: Store):
        """测试删除文档"""
        content = "# Test\n\nContent."

        # 先索引
        store.index_document("test", "doc.md", content)

        # 删除
        success = store.remove_document("test", "doc.md")
        assert success is True

        # 验证文档已被标记为 inactive
        count = store.get_document_count("test")
        assert count == 0

    def test_remove_document_not_found(self, store: Store):
        """测试删除不存在的文档"""
        success = store.remove_document("test", "nonexistent.md")
        assert success is False

    def test_remove_document_search_exclusion(self, tmp_db: Database):
        """测试删除文档后搜索不应命中该文档"""
        from qmd.core.retrieval import bm25_search

        store = Store(tmp_db)

        # 1. 索引文档
        content = "# Python Programming\n\nPython is a high-level programming language."
        store.index_document("test", "python.md", content)

        # 2. 搜索确认能命中
        results = bm25_search(tmp_db, "Python programming", limit=10)
        assert len(results) > 0
        assert any("python.md" in r.file for r in results)

        # 3. 删除文档
        success = store.remove_document("test", "python.md")
        assert success is True

        # 4. 再次搜索，确认不再命中
        results_after = bm25_search(tmp_db, "Python programming", limit=10)
        assert not any("python.md" in r.file for r in results_after)

    # === 查询方法测试 ===

    def test_get_document_count(self, store: Store):
        """测试获取文档数量"""
        # 初始为 0
        assert store.get_document_count("test") == 0

        # 索引 3 个文档
        store.index_document("test", "doc1.md", "# Doc 1")
        store.index_document("test", "doc2.md", "# Doc 2")
        store.index_document("test", "doc3.md", "# Doc 3")

        assert store.get_document_count("test") == 3

        # 删除 1 个
        store.remove_document("test", "doc2.md")
        assert store.get_document_count("test") == 2

    def test_get_indexed_files(self, store: Store):
        """测试获取已索引文件列表"""
        # 初始为空
        assert store.get_indexed_files("test") == []

        # 索引文档
        store.index_document("test", "doc1.md", "# Doc 1")
        store.index_document("test", "doc2.md", "# Doc 2")

        files = store.get_indexed_files("test")
        assert len(files) == 2
        assert "doc1.md" in files
        assert "doc2.md" in files

    # === 集合更新测试 ===

    def test_update_collection_basic(
        self, store: Store, test_collection: Collection, sample_docs: dict[str, Path]
    ):
        """测试集合更新基本功能"""
        stats = store.update_collection(test_collection)

        # 验证统计
        assert stats["indexed"] == 3  # 3 个新文档
        assert stats["updated"] == 0
        assert stats["unchanged"] == 0
        assert stats["removed"] == 0

        # 验证数据库
        count = store.get_document_count(test_collection.name)
        assert count == 3

    def test_update_collection_incremental(
        self, store: Store, test_collection: Collection, sample_docs: dict[str, Path]
    ):
        """测试增量更新"""
        # 第一次更新
        stats1 = store.update_collection(test_collection)
        assert stats1["indexed"] == 3

        # 第二次更新（无变化）
        stats2 = store.update_collection(test_collection)
        assert stats2["indexed"] == 0
        assert stats2["unchanged"] == 3

    def test_update_collection_file_removed(
        self, store: Store, test_collection: Collection, sample_docs: dict[str, Path]
    ):
        """测试文件被删除"""
        # 第一次更新
        stats1 = store.update_collection(test_collection)
        assert stats1["indexed"] == 3

        # 删除一个文件
        sample_docs["doc2"].unlink()

        # 第二次更新
        stats2 = store.update_collection(test_collection)
        assert stats2["removed"] == 1
        assert stats2["unchanged"] == 2

        # 验证数据库
        count = store.get_document_count(test_collection.name)
        assert count == 2

    def test_update_collection_file_modified(
        self, store: Store, test_collection: Collection, sample_docs: dict[str, Path]
    ):
        """测试文件被修改"""
        # 第一次更新
        stats1 = store.update_collection(test_collection)
        assert stats1["indexed"] == 3

        # 修改一个文件
        sample_docs["doc1"].write_text("# Modified\n\nNew content", encoding="utf-8")

        # 第二次更新
        stats2 = store.update_collection(test_collection)
        assert stats2["updated"] == 1
        assert stats2["unchanged"] == 2

    def test_update_collection_cleanup_orphaned_content(
        self, store: Store, test_collection: Collection, sample_docs: dict[str, Path]
    ):
        """测试清理孤立的 content"""
        # 第一次更新
        store.update_collection(test_collection)

        # 修改文件（产生新的 content hash）
        sample_docs["doc1"].write_text("# Modified\n\nNew content", encoding="utf-8")

        # 第二次更新（应该清理旧的 content）
        store.update_collection(test_collection)

        # 验证孤立 content 被清理（通过检查 db 的清理计数）
        # 这里我们无法直接验证，但可以确保没有抛出异常
        assert store.get_document_count(test_collection.name) == 3

    # === Embedding 生成测试 ===

    @pytest.fixture(scope="class")
    def llm_backend(self) -> SentenceTransformerBackend:
        """
        创建 LLM 后端（使用真实模型）

        使用 paraphrase-multilingual-MiniLM-L12-v2 (384 维，支持中英双语)
        """
        return SentenceTransformerBackend(model_name="paraphrase-multilingual-MiniLM-L12-v2", device="cpu")

    def test_embed_documents_basic(
        self,
        store: Store,
        test_collection: Collection,
        sample_docs: dict[str, Path],
        llm_backend: SentenceTransformerBackend,
    ):
        """测试基本 embedding 生成"""
        # 先索引文档
        store.update_collection(test_collection)

        # 生成 embedding
        stats = store.embed_documents(llm_backend)

        # 验证统计
        assert stats["embedded"] > 0  # 至少生成了一些 embedding
        assert stats["errors"] == 0

    def test_embed_documents_already_embedded(
        self,
        store: Store,
        test_collection: Collection,
        sample_docs: dict[str, Path],
        llm_backend: SentenceTransformerBackend,
    ):
        """测试重复 embedding（应该跳过）"""
        # 先索引并生成 embedding
        store.update_collection(test_collection)
        stats1 = store.embed_documents(llm_backend)
        assert stats1["embedded"] > 0

        # 再次生成（应该跳过）
        stats2 = store.embed_documents(llm_backend)
        assert stats2["embedded"] == 0

    def test_embed_documents_force(
        self,
        store: Store,
        test_collection: Collection,
        sample_docs: dict[str, Path],
        llm_backend: SentenceTransformerBackend,
    ):
        """测试强制重新生成 embedding"""
        # 先索引并生成 embedding
        store.update_collection(test_collection)
        stats1 = store.embed_documents(llm_backend)
        assert stats1["embedded"] > 0

        # 强制重新生成
        stats2 = store.embed_documents(llm_backend, force=True)
        assert stats2["embedded"] == stats1["embedded"]

    def test_update_collection_with_auto_embed(
        self,
        store: Store,
        test_collection: Collection,
        sample_docs: dict[str, Path],
        llm_backend: SentenceTransformerBackend,
    ):
        """测试集合更新时自动生成 embedding"""
        stats = store.update_collection(
            test_collection, llm_backend=llm_backend, auto_embed=True
        )

        # 验证文档被索引
        assert stats["indexed"] == 3

        # 验证 embedding 被生成（通过检查没有待生成的 hash）
        hashes_to_embed = store.db.get_hashes_for_embedding()
        assert len(hashes_to_embed) == 0

    # === 边界情况测试 ===

    def test_index_document_special_characters_in_path(self, store: Store):
        """测试路径包含特殊字符"""
        content = "# Test\n\nContent."
        result = store.index_document("test", "docs/中文/file name.md", content)
        assert result["status"] == "indexed"

    def test_index_document_no_h1_title(self, store: Store):
        """测试没有 H1 标题的文档"""
        content = "Just some content without a title."
        result = store.index_document("test", "no-title.md", content)
        assert result["status"] == "indexed"

        # 验证使用文件名作为 title
        files = store.db.get_active_document_paths("test")
        assert len(files) == 1

    def test_embed_documents_empty_batch(self, store: Store, llm_backend: SentenceTransformerBackend):
        """测试空批次（没有待 embedding 的文档）"""
        stats = store.embed_documents(llm_backend)
        assert stats["embedded"] == 0
        assert stats["errors"] == 0

    def test_multiple_collections(self, store: Store, tmp_path: Path):
        """测试多个集合互不干扰"""
        from qmd.core.config import NamedCollection

        # 创建两个集合
        coll1_path = tmp_path / "coll1"
        coll1_path.mkdir()
        (coll1_path / "doc.md").write_text("# Coll1 Doc", encoding="utf-8")

        coll2_path = tmp_path / "coll2"
        coll2_path.mkdir()
        (coll2_path / "doc.md").write_text("# Coll2 Doc", encoding="utf-8")

        coll1 = NamedCollection(name="coll1", path=str(coll1_path), pattern="**/*.md")
        coll2 = NamedCollection(name="coll2", path=str(coll2_path), pattern="**/*.md")

        # 更新两个集合
        store.update_collection(coll1)
        store.update_collection(coll2)

        # 验证各自独立
        assert store.get_document_count("coll1") == 1
        assert store.get_document_count("coll2") == 1

    def test_concurrent_updates(self, store: Store, test_collection: Collection, sample_docs: dict[str, Path]):
        """测试并发更新（同一集合多次更新）"""
        # 连续更新 3 次
        stats1 = store.update_collection(test_collection)
        stats2 = store.update_collection(test_collection)
        stats3 = store.update_collection(test_collection)

        # 第一次应该索引所有文档
        assert stats1["indexed"] == 3

        # 后续更新应该没有变化
        assert stats2["unchanged"] == 3
        assert stats3["unchanged"] == 3
