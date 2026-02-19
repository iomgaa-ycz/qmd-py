"""
端到端验证测试 (E2E)

使用 tests/fixtures/ 中的通用测试数据进行完整流程测试。

重要注意事项：
1. QMD 的 config_path 参数不生效，总是读写全局 ~/.config/qmd/index.yml
2. 必须在 fixture 中备份/恢复全局 config，防止测试污染
3. 使用 db_path=tmp_path 做数据库隔离
4. 跳过 CLI 和 FlagEmbedding 测试（见 implementation_plan.md）
"""

import shutil
import time
from pathlib import Path

import pytest

from qmd.core.config import NamedCollection
from qmd.core.db import Database, init_schema, open_database
from qmd.core.retrieval import search
from qmd.core.store import Store
from qmd.llm.sentence_tf import SentenceTransformerBackend


class TestE2E:
    """端到端验证测试"""

    @pytest.fixture(scope="class")
    def fixtures_path(self) -> Path:
        """E2E 测试数据路径（通用夹具）"""
        return Path(__file__).parent / "fixtures"

    @pytest.fixture(scope="class")
    def llm_backend(self) -> SentenceTransformerBackend:
        """创建 LLM 后端（使用多语言模型）"""
        return SentenceTransformerBackend(
            model_name="paraphrase-multilingual-MiniLM-L12-v2", device="cpu"
        )

    @pytest.fixture
    def tmp_db(self, tmp_path: Path) -> Database:
        """创建临时数据库"""
        db_path = tmp_path / "e2e_test.db"
        conn = open_database(str(db_path))
        init_schema(conn)
        return Database(conn)

    @pytest.fixture(autouse=True)
    def isolate_config(self, tmp_path: Path):
        """隔离配置环境，防止测试污染全局配置

        重要：QMD 的 config_path 参数不生效，必须备份/恢复全局 ~/.config/qmd/index.yml
        """
        config_path = Path.home() / ".config/qmd/index.yml"
        backup = None

        # 备份现有 config
        if config_path.exists():
            backup = config_path.read_text(encoding="utf-8")

        # 测试执行
        yield

        # 恢复 config
        if backup is not None:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(backup, encoding="utf-8")
        elif config_path.exists():
            # 测试前不存在，测试后删除
            config_path.unlink()

    # =========================================================================
    # 1. Chunking 测试
    # =========================================================================

    def test_chunking_chinese_long_document(self, fixtures_path: Path):
        """测试中文长文档 chunking"""
        from qmd.core.chunking import chunk_document

        # 使用中英混合的 tutorial.md (机器学习教程)
        tutorial_file = fixtures_path / "docs/tutorial.md"
        assert tutorial_file.exists(), f"夹具文件不存在: {tutorial_file}"

        content = tutorial_file.read_text(encoding="utf-8")
        chunks = chunk_document(content, max_chars=3600, overlap_chars=540)

        # 验证切分结果
        assert len(chunks) > 0
        assert all(len(chunk.text) <= 3600 for chunk in chunks)

        # 验证重叠
        if len(chunks) > 1:
            for i in range(len(chunks) - 1):
                chunk1_end = chunks[i].pos + len(chunks[i].text)
                chunk2_start = chunks[i + 1].pos
                # 应该有重叠
                assert chunk2_start < chunk1_end

    def test_chunking_english_document(self, fixtures_path: Path):
        """测试英文文档 chunking"""
        from qmd.core.chunking import chunk_document

        # 使用英文的 guide.md (Python 编程指南)
        guide_file = fixtures_path / "docs/guide.md"
        assert guide_file.exists(), f"夹具文件不存在: {guide_file}"

        content = guide_file.read_text(encoding="utf-8")
        chunks = chunk_document(content, max_chars=3600, overlap_chars=540)

        assert len(chunks) > 0

    def test_chunking_code_block_protection(self, fixtures_path: Path):
        """测试代码块保护（代码围栏不被从中间切断）"""
        from qmd.core.chunking import chunk_document, find_code_fences

        # 使用包含代码块的 tutorial.md
        tutorial_file = fixtures_path / "docs/tutorial.md"
        assert tutorial_file.exists(), f"夹具文件不存在: {tutorial_file}"

        content = tutorial_file.read_text(encoding="utf-8")
        fences = find_code_fences(content)

        # 如果有代码块
        if fences:
            chunks = chunk_document(content, max_chars=3600, overlap_chars=540)

            # 验证没有切分点在代码块内部
            for fence in fences:
                for i, chunk in enumerate(chunks):
                    if i > 0:
                        # 前一块的结束位置
                        prev_end = chunks[i - 1].pos + len(chunks[i - 1].text)
                        # 不应该在代码块内部切分（不包括边界）
                        assert not (fence.start < prev_end < fence.end), \
                            f"切分点 {prev_end} 在代码块内部 ({fence.start}, {fence.end})"

    def test_chunking_empty_content(self):
        """测试空内容返回空列表"""
        from qmd.core.chunking import chunk_document

        assert chunk_document("") == []
        assert chunk_document("   ") == []
        assert chunk_document("\n\n") == []

    def test_chunking_short_content(self):
        """测试短内容返回 1 chunk"""
        from qmd.core.chunking import chunk_document

        short_text = "这是一篇短文档。"
        chunks = chunk_document(short_text, max_chars=1000)

        assert len(chunks) == 1
        assert chunks[0].text == short_text
        assert chunks[0].pos == 0

    # =========================================================================
    # 2. 索引测试
    # =========================================================================

    def test_indexing_first_time(
        self, tmp_db: Database, fixtures_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试首次索引 fixtures 目录"""
        store = Store(tmp_db)

        # 索引 fixtures 目录
        collection = NamedCollection(
            name="docs", path=str(fixtures_path), pattern="**/*.md"
        )

        stats = store.update_collection(collection)

        # 验证索引统计（fixtures 有 6 个 md 文件）
        assert stats["indexed"] > 0  # 应该有新索引的文档
        assert stats["indexed"] >= 6  # 至少 6 个文件
        assert stats["updated"] == 0
        assert stats["unchanged"] == 0

        # 生成向量
        embed_stats = store.embed_documents(llm_backend)
        assert embed_stats["embedded"] > 0

    def test_indexing_unchanged(
        self, tmp_db: Database, fixtures_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试再次 update，验证全部 unchanged"""
        store = Store(tmp_db)

        collection = NamedCollection(
            name="docs", path=str(fixtures_path), pattern="**/*.md"
        )

        # 第一次索引
        store.update_collection(collection)
        store.embed_documents(llm_backend)

        # 第二次索引
        stats = store.update_collection(collection)

        # 验证全部 unchanged
        assert stats["indexed"] == 0
        assert stats["updated"] == 0
        assert stats["unchanged"] > 0

    def test_indexing_incremental(
        self, tmp_db: Database, tmp_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试增量索引：新增文件后 update"""
        store = Store(tmp_db)

        # 创建测试目录
        test_dir = tmp_path / "test_docs"
        test_dir.mkdir()

        # 初始文档
        (test_dir / "doc1.md").write_text("# Document 1\n\nInitial content.", encoding="utf-8")

        collection = NamedCollection(
            name="test", path=str(test_dir), pattern="**/*.md"
        )

        # 第一次索引
        stats1 = store.update_collection(collection)
        assert stats1["indexed"] == 1

        # 新增文件
        (test_dir / "doc2.md").write_text("# Document 2\n\nNew content.", encoding="utf-8")

        # 第二次索引
        stats2 = store.update_collection(collection)
        assert stats2["indexed"] == 1  # 新增 1 个
        assert stats2["unchanged"] == 1  # doc1 不变

    # =========================================================================
    # 3. 中文搜索测试
    # =========================================================================

    def test_chinese_search_machine_learning(
        self, tmp_db: Database, fixtures_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试中文搜索：机器学习"""
        store = Store(tmp_db)

        collection = NamedCollection(
            name="docs", path=str(fixtures_path), pattern="**/*.md"
        )

        store.update_collection(collection)
        store.embed_documents(llm_backend)

        # 搜索机器学习相关内容
        results = search(
            tmp_db, "机器学习算法", collection="docs", limit=5, llm_backend=llm_backend
        )

        # 应该命中 tutorial.md
        assert len(results) > 0
        assert any("tutorial" in r.file.lower() for r in results)

    def test_chinese_search_meeting(
        self, tmp_db: Database, fixtures_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试中文搜索：会议记录"""
        store = Store(tmp_db)

        collection = NamedCollection(
            name="notes", path=str(fixtures_path / "notes"), pattern="**/*.md"
        )

        store.update_collection(collection)
        store.embed_documents(llm_backend)

        # 搜索会议相关内容
        results = search(tmp_db, "项目会议 技术方案", collection="notes", limit=5, llm_backend=llm_backend)

        # 应该命中 meeting 笔记
        assert len(results) > 0
        assert any("meeting" in r.file.lower() for r in results)

    def test_chinese_search_bm25_algorithm(
        self, tmp_db: Database, fixtures_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试中文搜索：BM25 算法"""
        store = Store(tmp_db)

        collection = NamedCollection(
            name="notes", path=str(fixtures_path / "notes"), pattern="**/*.md"
        )

        store.update_collection(collection)
        store.embed_documents(llm_backend)

        # 搜索 BM25 算法
        results = search(tmp_db, "BM25 算法 全文检索", collection="notes", limit=5, llm_backend=llm_backend)

        # 应该命中研究笔记
        assert len(results) > 0
        assert any("research" in r.file.lower() for r in results)

    # =========================================================================
    # 4. 英文搜索测试
    # =========================================================================

    def test_english_search_api_documentation(
        self, tmp_db: Database, fixtures_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试英文搜索：API 文档"""
        store = Store(tmp_db)

        collection = NamedCollection(
            name="docs", path=str(fixtures_path / "docs"), pattern="**/*.md"
        )

        store.update_collection(collection)
        store.embed_documents(llm_backend)

        # 搜索 API 相关内容
        results = search(
            tmp_db, "REST API authentication", collection="docs", limit=5, llm_backend=llm_backend
        )

        # 应该命中 api-reference.md
        assert len(results) > 0
        assert any("api-reference" in r.file.lower() for r in results)

    def test_english_search_python_programming(
        self, tmp_db: Database, fixtures_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试英文搜索：Python 编程"""
        store = Store(tmp_db)

        collection = NamedCollection(
            name="docs", path=str(fixtures_path / "docs"), pattern="**/*.md"
        )

        store.update_collection(collection)
        store.embed_documents(llm_backend)

        # 搜索 Python 编程
        results = search(
            tmp_db, "Python programming functions", collection="docs", limit=5, llm_backend=llm_backend
        )

        # 应该命中 guide.md
        assert len(results) > 0
        assert any("guide" in r.file.lower() for r in results)

    # =========================================================================
    # 5. 多 Collection 测试
    # =========================================================================

    def test_multiple_collections(
        self, tmp_db: Database, tmp_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试创建多个 collection 并跨 collection 搜索"""
        store = Store(tmp_db)

        # 创建 3 个不同的 collection
        coll1_dir = tmp_path / "coll1"
        coll1_dir.mkdir()
        (coll1_dir / "doc1.md").write_text("# Collection 1\n\nPython programming", encoding="utf-8")

        coll2_dir = tmp_path / "coll2"
        coll2_dir.mkdir()
        (coll2_dir / "doc2.md").write_text("# Collection 2\n\nJavaScript development", encoding="utf-8")

        coll3_dir = tmp_path / "coll3"
        coll3_dir.mkdir()
        (coll3_dir / "doc3.md").write_text("# Collection 3\n\nRust systems programming", encoding="utf-8")

        # 索引所有 collection
        for i, coll_dir in enumerate([coll1_dir, coll2_dir, coll3_dir], 1):
            collection = NamedCollection(
                name=f"coll{i}", path=str(coll_dir), pattern="**/*.md"
            )
            store.update_collection(collection)
            store.embed_documents(llm_backend)

        # 跨 collection 搜索（不指定 collection）
        results = search(tmp_db, "programming", limit=10, llm_backend=llm_backend)

        # 应该能搜到来自不同 collection 的结果
        collections_found = {r.collection for r in results}
        assert len(collections_found) >= 1  # 至少命中 1 个 collection

    def test_global_search(
        self, tmp_db: Database, tmp_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试全局搜索（不指定 collection）"""
        store = Store(tmp_db)

        # 创建 2 个 collection
        for i in range(1, 3):
            coll_dir = tmp_path / f"coll{i}"
            coll_dir.mkdir()
            (coll_dir / "doc.md").write_text(
                f"# Collection {i}\n\nDocument content {i}", encoding="utf-8"
            )

            collection = NamedCollection(
                name=f"coll{i}", path=str(coll_dir), pattern="**/*.md"
            )
            store.update_collection(collection)
            store.embed_documents(llm_backend)

        # 全局搜索
        results = search(tmp_db, "content", limit=10, llm_backend=llm_backend)

        # 应该有结果
        assert len(results) > 0

    # =========================================================================
    # 6. 删除测试
    # =========================================================================

    def test_delete_document_then_search(
        self, tmp_db: Database, tmp_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试删除文档后搜索不再命中"""
        store = Store(tmp_db)

        # 创建测试文档
        test_dir = tmp_path / "test_docs"
        test_dir.mkdir()
        (test_dir / "unique_doc.md").write_text(
            "# Unique Document\n\nThis is a very unique document with special keywords.",
            encoding="utf-8"
        )

        collection = NamedCollection(
            name="test", path=str(test_dir), pattern="**/*.md"
        )

        # 索引
        store.update_collection(collection)
        store.embed_documents(llm_backend)

        # 搜索确认能命中
        results_before = search(tmp_db, "unique special", collection="test", limit=5, llm_backend=llm_backend)
        assert len(results_before) > 0
        assert any("unique_doc.md" in r.file for r in results_before)

        # 删除文档
        success = store.remove_document("test", "unique_doc.md")
        assert success is True

        # 再次搜索，不应命中
        results_after = search(tmp_db, "unique special", collection="test", limit=5, llm_backend=llm_backend)
        assert not any("unique_doc.md" in r.file for r in results_after)

    def test_delete_collection(
        self, tmp_db: Database, tmp_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试删除 collection"""
        store = Store(tmp_db)

        # 创建 collection
        test_dir = tmp_path / "test_docs"
        test_dir.mkdir()
        (test_dir / "doc.md").write_text("# Test Document", encoding="utf-8")

        collection = NamedCollection(
            name="test", path=str(test_dir), pattern="**/*.md"
        )

        store.update_collection(collection)

        # 验证文档数量 > 0
        assert store.get_document_count("test") > 0

        # 删除 collection（通过删除所有文档）
        for file in store.get_indexed_files("test"):
            store.remove_document("test", file)

        # 验证文档数量 = 0
        assert store.get_document_count("test") == 0

    # =========================================================================
    # 8. 性能基准测试
    # =========================================================================

    def test_performance_full_indexing(
        self, tmp_db: Database, fixtures_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试全量索引性能：6 个夹具文件应在合理时间内完成"""
        store = Store(tmp_db)

        collection = NamedCollection(
            name="docs", path=str(fixtures_path), pattern="**/*.md"
        )

        # 索引
        start_time = time.time()
        stats = store.update_collection(collection)
        index_time = time.time() - start_time

        # 生成向量
        start_embed = time.time()
        store.embed_documents(llm_backend)
        embed_time = time.time() - start_embed

        # 验证索引时间（夹具文件较少，应该很快）
        print(f"\n索引耗时: {index_time:.2f}s, 向量生成耗时: {embed_time:.2f}s")
        assert index_time < 60  # 索引应该快速完成
        # 向量生成时间不做严格要求（取决于机器性能）

    def test_performance_search_latency(
        self, tmp_db: Database, fixtures_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试搜索延迟：平均应 < 5s"""
        store = Store(tmp_db)

        collection = NamedCollection(
            name="docs", path=str(fixtures_path), pattern="**/*.md"
        )

        store.update_collection(collection)
        store.embed_documents(llm_backend)

        # 执行多次搜索
        queries = ["机器学习", "API documentation", "Python programming", "BM25 algorithm", "会议记录"]
        latencies = []

        for query in queries:
            start_time = time.time()
            search(tmp_db, query, collection="docs", limit=5, llm_backend=llm_backend)
            latency = time.time() - start_time
            latencies.append(latency)

        avg_latency = sum(latencies) / len(latencies)
        print(f"\n平均搜索延迟: {avg_latency:.2f}s")

        # 延迟要求宽松一些（包含模型加载时间）
        assert avg_latency < 5  # 平均 < 5s

    # =========================================================================
    # 9. 边界条件测试
    # =========================================================================

    def test_edge_case_empty_file(
        self, tmp_db: Database, tmp_path: Path
    ):
        """测试空文件不报错"""
        store = Store(tmp_db)

        test_dir = tmp_path / "test_docs"
        test_dir.mkdir()
        (test_dir / "empty.md").write_text("", encoding="utf-8")

        collection = NamedCollection(
            name="test", path=str(test_dir), pattern="**/*.md"
        )

        # 索引空文件
        stats = store.update_collection(collection)

        # 应该跳过空文件
        assert stats["indexed"] == 0 or stats["skipped"] > 0

    def test_edge_case_chinese_filename(
        self, tmp_db: Database, tmp_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试中文文件名不报错"""
        store = Store(tmp_db)

        test_dir = tmp_path / "test_docs"
        test_dir.mkdir()
        (test_dir / "中文文件名.md").write_text("# 中文标题\n\n内容", encoding="utf-8")

        collection = NamedCollection(
            name="test", path=str(test_dir), pattern="**/*.md"
        )

        # 索引中文文件名
        stats = store.update_collection(collection)
        assert stats["indexed"] >= 1

    def test_edge_case_empty_query(
        self, tmp_db: Database, llm_backend: SentenceTransformerBackend
    ):
        """测试空字符串搜索不崩溃"""
        # 空查询搜索
        results = search(tmp_db, "", limit=5, llm_backend=llm_backend)

        # 应该返回空结果或不崩溃
        assert isinstance(results, list)

    def test_edge_case_very_long_line(
        self, tmp_db: Database, tmp_path: Path
    ):
        """测试超长单行不报错"""
        store = Store(tmp_db)

        test_dir = tmp_path / "test_docs"
        test_dir.mkdir()

        # 创建超长单行（10000 字符）
        long_line = "a" * 10000
        (test_dir / "long_line.md").write_text(f"# Title\n\n{long_line}", encoding="utf-8")

        collection = NamedCollection(
            name="test", path=str(test_dir), pattern="**/*.md"
        )

        # 索引超长行
        stats = store.update_collection(collection)
        assert stats["indexed"] >= 1
