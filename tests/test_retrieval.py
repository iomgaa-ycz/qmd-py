"""
测试混合检索引擎 (Retrieval)

使用真实的 sentence-transformers 后端进行集成测试。
"""

import sqlite3
from pathlib import Path

import pytest

from qmd.core.config import NamedCollection
from qmd.core.db import Database, ensure_vec_table, init_schema, open_database
from qmd.core.retrieval import (
    RankedResult,
    SearchResult,
    bm25_search,
    reciprocal_rank_fusion,
    search,
    vector_search,
)
from qmd.core.store import Store
from qmd.llm.sentence_tf import SentenceTransformerBackend


class TestBM25Search:
    """BM25 全文检索测试"""

    @pytest.fixture
    def tmp_db(self, tmp_path: Path) -> Database:
        """创建临时数据库"""
        db_path = tmp_path / "test.db"
        conn = open_database(str(db_path))
        init_schema(conn)
        return Database(conn)

    @pytest.fixture
    def indexed_db(self, tmp_db: Database, tmp_path: Path) -> Database:
        """创建已索引文档的数据库"""
        store = Store(tmp_db)

        # 创建测试文档
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(exist_ok=True)

        doc1 = docs_dir / "python.md"
        doc1.write_text(
            "# Python Programming\n\nPython is a high-level programming language.",
            encoding="utf-8",
        )

        doc2 = docs_dir / "javascript.md"
        doc2.write_text(
            "# JavaScript Guide\n\nJavaScript is used for web development.",
            encoding="utf-8",
        )

        doc3 = docs_dir / "rust.md"
        doc3.write_text(
            "# Rust Tutorial\n\nRust is a systems programming language with memory safety.",
            encoding="utf-8",
        )

        # 索引文档
        collection = NamedCollection(
            name="test", path=str(docs_dir), pattern="**/*.md"
        )
        store.update_collection(collection)

        return tmp_db

    def test_bm25_search_basic(self, indexed_db: Database):
        """测试基础 BM25 检索"""
        results = bm25_search(indexed_db, "Python programming", limit=10)

        # 应该找到 Python 文档
        assert len(results) > 0
        assert any("python.md" in r.file for r in results)

        # 检查结果格式
        first = results[0]
        assert isinstance(first, SearchResult)
        assert first.file
        assert first.title
        assert first.body
        assert 0 <= first.score <= 1
        assert first.collection == "test"

    def test_bm25_search_keyword_matching(self, indexed_db: Database):
        """测试关键词匹配能力"""
        results = bm25_search(indexed_db, "JavaScript web", limit=10)

        # JavaScript 文档应该排在前面
        assert len(results) > 0
        assert "javascript.md" in results[0].file

    def test_bm25_search_multiple_keywords(self, indexed_db: Database):
        """测试多关键词匹配"""
        results = bm25_search(indexed_db, "memory safety", limit=10)

        # Rust 文档应该匹配
        assert len(results) > 0
        assert any("rust.md" in r.file for r in results)

    def test_bm25_search_no_results(self, indexed_db: Database):
        """测试无匹配结果"""
        results = bm25_search(indexed_db, "nonexistent keyword xyz", limit=10)
        assert len(results) == 0

    def test_bm25_search_empty_query(self, indexed_db: Database):
        """测试空查询"""
        results = bm25_search(indexed_db, "", limit=10)
        # FTS5 空查询应该返回空结果
        assert len(results) == 0

    def test_bm25_search_collection_filter(self, tmp_db: Database, tmp_path: Path):
        """测试集合过滤"""
        store = Store(tmp_db)

        # 创建两个集合
        coll1_dir = tmp_path / "coll1"
        coll1_dir.mkdir()
        (coll1_dir / "doc.md").write_text("# Collection 1 Document", encoding="utf-8")

        coll2_dir = tmp_path / "coll2"
        coll2_dir.mkdir()
        (coll2_dir / "doc.md").write_text("# Collection 2 Document", encoding="utf-8")

        coll1 = NamedCollection(name="coll1", path=str(coll1_dir), pattern="**/*.md")
        coll2 = NamedCollection(name="coll2", path=str(coll2_dir), pattern="**/*.md")

        store.update_collection(coll1)
        store.update_collection(coll2)

        # 只搜索 coll1
        results = bm25_search(tmp_db, "Collection Document", collection="coll1", limit=10)
        assert len(results) > 0
        assert all(r.collection == "coll1" for r in results)

    def test_bm25_search_limit(self, indexed_db: Database):
        """测试结果数量限制"""
        results = bm25_search(indexed_db, "programming language", limit=2)
        assert len(results) <= 2

    def test_bm25_search_score_range(self, indexed_db: Database):
        """测试分数范围"""
        results = bm25_search(indexed_db, "Python", limit=10)
        for result in results:
            assert 0 <= result.score <= 1


class TestVectorSearch:
    """向量语义检索测试"""

    @pytest.fixture(scope="class")
    def llm_backend(self) -> SentenceTransformerBackend:
        """创建 LLM 后端（使用真实模型）"""
        return SentenceTransformerBackend(model_name="all-MiniLM-L6-v2", device="cpu")

    @pytest.fixture
    def tmp_db(self, tmp_path: Path) -> Database:
        """创建临时数据库"""
        db_path = tmp_path / "test.db"
        conn = open_database(str(db_path))
        init_schema(conn)
        return Database(conn)

    @pytest.fixture
    def indexed_db_with_vectors(
        self, tmp_db: Database, tmp_path: Path, llm_backend: SentenceTransformerBackend
    ) -> Database:
        """创建已索引并生成向量的数据库"""
        store = Store(tmp_db)

        # 创建测试文档
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(exist_ok=True)

        doc1 = docs_dir / "python.md"
        doc1.write_text(
            "# Python Programming\n\nPython is a versatile high-level programming language.",
            encoding="utf-8",
        )

        doc2 = docs_dir / "javascript.md"
        doc2.write_text(
            "# JavaScript Tutorial\n\nJavaScript is essential for modern web development.",
            encoding="utf-8",
        )

        doc3 = docs_dir / "cooking.md"
        doc3.write_text(
            "# Cooking Tips\n\nLearn how to cook delicious pasta dishes.",
            encoding="utf-8",
        )

        # 索引文档并生成 embedding
        collection = NamedCollection(
            name="test", path=str(docs_dir), pattern="**/*.md"
        )
        store.update_collection(collection, llm_backend=llm_backend, auto_embed=True)

        return tmp_db

    def test_vector_search_basic(
        self, indexed_db_with_vectors: Database, llm_backend: SentenceTransformerBackend
    ):
        """测试基础向量检索"""
        # 查询：编程语言
        query_embedding = llm_backend.embed("programming language").embedding

        results = vector_search(indexed_db_with_vectors, query_embedding, limit=10)

        # 应该找到编程相关文档
        assert len(results) > 0
        assert any("python.md" in r.file or "javascript.md" in r.file for r in results)

        # 检查结果格式
        first = results[0]
        assert isinstance(first, SearchResult)
        assert first.file
        assert first.title
        assert first.body
        assert 0 <= first.score <= 1
        assert first.collection == "test"

    def test_vector_search_semantic_similarity(
        self, indexed_db_with_vectors: Database, llm_backend: SentenceTransformerBackend
    ):
        """测试语义相似性"""
        # 查询：编程（应该匹配 Python/JavaScript，不匹配烹饪）
        query_embedding = llm_backend.embed("coding and software development").embedding

        results = vector_search(indexed_db_with_vectors, query_embedding, limit=10)

        # 编程文档应该排在前面
        assert len(results) > 0
        top_files = [r.file for r in results[:2]]
        assert any("python.md" in f or "javascript.md" in f for f in top_files)

        # 烹饪文档应该不在顶部
        if len(results) > 1:
            assert "cooking.md" not in results[0].file

    def test_vector_search_no_vectors(self, tmp_db: Database):
        """测试数据库中没有向量时的行为"""
        query_embedding = [0.1] * 384  # 假的 embedding

        # 应该返回空结果（没有 vectors_vec 表）
        results = vector_search(tmp_db, query_embedding, limit=10)
        assert len(results) == 0

    def test_vector_search_empty_embedding(self, indexed_db_with_vectors: Database):
        """测试空 embedding"""
        results = vector_search(indexed_db_with_vectors, [], limit=10)
        assert len(results) == 0

    def test_vector_search_collection_filter(
        self, tmp_db: Database, tmp_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试集合过滤"""
        store = Store(tmp_db)

        # 创建两个集合
        coll1_dir = tmp_path / "coll1"
        coll1_dir.mkdir()
        (coll1_dir / "doc.md").write_text(
            "# Programming Guide", encoding="utf-8"
        )

        coll2_dir = tmp_path / "coll2"
        coll2_dir.mkdir()
        (coll2_dir / "doc.md").write_text(
            "# Cooking Recipe", encoding="utf-8"
        )

        coll1 = NamedCollection(name="coll1", path=str(coll1_dir), pattern="**/*.md")
        coll2 = NamedCollection(name="coll2", path=str(coll2_dir), pattern="**/*.md")

        store.update_collection(coll1, llm_backend=llm_backend, auto_embed=True)
        store.update_collection(coll2, llm_backend=llm_backend, auto_embed=True)

        # 只搜索 coll1
        query_embedding = llm_backend.embed("programming").embedding
        results = vector_search(tmp_db, query_embedding, collection="coll1", limit=10)

        assert len(results) > 0
        assert all(r.collection == "coll1" for r in results)

    def test_vector_search_limit(
        self, indexed_db_with_vectors: Database, llm_backend: SentenceTransformerBackend
    ):
        """测试结果数量限制"""
        query_embedding = llm_backend.embed("programming").embedding
        results = vector_search(indexed_db_with_vectors, query_embedding, limit=2)
        assert len(results) <= 2

    def test_vector_search_deduplication(
        self, indexed_db_with_vectors: Database, llm_backend: SentenceTransformerBackend
    ):
        """测试去重逻辑（同一文档的多个 chunk）"""
        query_embedding = llm_backend.embed("programming").embedding
        results = vector_search(indexed_db_with_vectors, query_embedding, limit=10)

        # 检查没有重复的文件
        files = [r.file for r in results]
        assert len(files) == len(set(files))


class TestReciprocalRankFusion:
    """RRF 融合算法测试"""

    def test_reciprocal_rank_fusion_basic(self):
        """测试基础 RRF 融合"""
        list1 = [
            RankedResult(file="doc1.md", title="Doc 1", body="Body 1", score=0.9),
            RankedResult(file="doc2.md", title="Doc 2", body="Body 2", score=0.8),
        ]

        list2 = [
            RankedResult(file="doc2.md", title="Doc 2", body="Body 2", score=0.95),
            RankedResult(file="doc3.md", title="Doc 3", body="Body 3", score=0.7),
        ]

        fused = reciprocal_rank_fusion([list1, list2], k=60)

        # doc2 出现在两个列表中，应该排第一
        assert len(fused) == 3
        assert fused[0].file == "doc2.md"

    def test_reciprocal_rank_fusion_math(self):
        """测试 RRF 数学正确性"""
        # 单个列表
        list1 = [
            RankedResult(file="doc1.md", title="Doc 1", body="Body 1", score=0.9),
            RankedResult(file="doc2.md", title="Doc 2", body="Body 2", score=0.8),
        ]

        fused = reciprocal_rank_fusion([list1], k=60)

        # RRF score = 1 / (k + rank + 1)
        # doc1: rank=0 -> 1/(60+0+1) = 1/61 + 0.05 (top rank bonus) ≈ 0.0664
        # doc2: rank=1 -> 1/(60+1+1) = 1/62 + 0.02 (top 3 bonus) ≈ 0.0361

        assert len(fused) == 2
        assert fused[0].file == "doc1.md"
        assert fused[1].file == "doc2.md"

        # 验证分数计算
        doc1_expected = 1 / (60 + 0 + 1) + 0.05
        doc2_expected = 1 / (60 + 1 + 1) + 0.02

        assert abs(fused[0].score - doc1_expected) < 0.001
        assert abs(fused[1].score - doc2_expected) < 0.001

    def test_reciprocal_rank_fusion_top_rank_bonus(self):
        """测试 top rank bonus"""
        # rank 0 应该得到 +0.05 bonus
        list1 = [
            RankedResult(file="doc1.md", title="Doc 1", body="Body 1", score=0.9),
        ]

        fused = reciprocal_rank_fusion([list1], k=60)
        expected_score = 1 / (60 + 0 + 1) + 0.05

        assert abs(fused[0].score - expected_score) < 0.001

        # rank 1-2 应该得到 +0.02 bonus
        list2 = [
            RankedResult(file="doc_x.md", title="X", body="X", score=1.0),
            RankedResult(file="doc2.md", title="Doc 2", body="Body 2", score=0.8),
        ]

        fused = reciprocal_rank_fusion([list2], k=60)
        expected_score_rank1 = 1 / (60 + 1 + 1) + 0.02

        assert abs(fused[1].score - expected_score_rank1) < 0.001

    def test_reciprocal_rank_fusion_weights(self):
        """测试权重"""
        list1 = [
            RankedResult(file="doc1.md", title="Doc 1", body="Body 1", score=0.9),
        ]

        list2 = [
            RankedResult(file="doc2.md", title="Doc 2", body="Body 2", score=0.8),
        ]

        # 给 list1 更高的权重
        fused = reciprocal_rank_fusion([list1, list2], weights=[2.0, 1.0], k=60)

        # doc1 应该因为权重更高而排在前面
        assert fused[0].file == "doc1.md"

        # 验证分数
        doc1_expected = 2.0 / (60 + 0 + 1) + 0.05
        doc2_expected = 1.0 / (60 + 0 + 1) + 0.05

        assert abs(fused[0].score - doc1_expected) < 0.001
        assert abs(fused[1].score - doc2_expected) < 0.001

    def test_reciprocal_rank_fusion_empty_lists(self):
        """测试空列表"""
        fused = reciprocal_rank_fusion([])
        assert len(fused) == 0

        fused = reciprocal_rank_fusion([[]])
        assert len(fused) == 0

    def test_reciprocal_rank_fusion_deduplication(self):
        """测试去重（保留最好的 rank）"""
        list1 = [
            RankedResult(file="doc1.md", title="Doc 1", body="Body 1", score=0.9),
            RankedResult(file="doc2.md", title="Doc 2", body="Body 2", score=0.8),
        ]

        list2 = [
            RankedResult(file="doc1.md", title="Doc 1", body="Body 1", score=0.95),
        ]

        fused = reciprocal_rank_fusion([list1, list2], k=60)

        # doc1 出现两次，应该合并
        assert len(fused) == 2
        assert fused[0].file == "doc1.md"


class TestSearch:
    """完整混合检索流程测试"""

    @pytest.fixture(scope="class")
    def llm_backend(self) -> SentenceTransformerBackend:
        """创建 LLM 后端"""
        return SentenceTransformerBackend(model_name="all-MiniLM-L6-v2", device="cpu")

    @pytest.fixture
    def tmp_db(self, tmp_path: Path) -> Database:
        """创建临时数据库"""
        db_path = tmp_path / "test.db"
        conn = open_database(str(db_path))
        init_schema(conn)
        return Database(conn)

    @pytest.fixture
    def indexed_db(
        self, tmp_db: Database, tmp_path: Path, llm_backend: SentenceTransformerBackend
    ) -> Database:
        """创建已索引的数据库"""
        store = Store(tmp_db)

        # 创建测试文档
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(exist_ok=True)

        doc1 = docs_dir / "python.md"
        doc1.write_text(
            "# Python Programming\n\nPython is a high-level programming language used for web development, data science, and automation.",
            encoding="utf-8",
        )

        doc2 = docs_dir / "javascript.md"
        doc2.write_text(
            "# JavaScript Guide\n\nJavaScript is the language of the web, essential for frontend and backend development.",
            encoding="utf-8",
        )

        doc3 = docs_dir / "rust.md"
        doc3.write_text(
            "# Rust Tutorial\n\nRust is a systems programming language focused on safety, speed, and concurrency.",
            encoding="utf-8",
        )

        doc4 = docs_dir / "cooking.md"
        doc4.write_text(
            "# Cooking Recipes\n\nLearn how to make delicious Italian pasta and pizza at home.",
            encoding="utf-8",
        )

        # 索引并生成向量
        collection = NamedCollection(
            name="test", path=str(docs_dir), pattern="**/*.md"
        )
        store.update_collection(collection, llm_backend=llm_backend, auto_embed=True)

        return tmp_db

    def test_search_end_to_end(
        self, indexed_db: Database, llm_backend: SentenceTransformerBackend
    ):
        """测试完整检索流程"""
        results = search(indexed_db, "programming language", limit=10, llm_backend=llm_backend)

        # 应该找到编程相关文档
        assert len(results) > 0
        assert any("python.md" in r.file or "javascript.md" in r.file or "rust.md" in r.file for r in results)

        # 烹饪文档不应该排在前面
        top_files = [r.file for r in results[:2]]
        assert not any("cooking.md" in f for f in top_files)

        # 检查结果格式
        first = results[0]
        assert isinstance(first, SearchResult)
        assert first.file
        assert first.title
        assert first.body
        assert first.score > 0
        assert first.collection == "test"

    def test_search_bm25_only(self, indexed_db: Database):
        """测试纯 BM25 检索（无 LLM backend）"""
        results = search(indexed_db, "Python programming", limit=10, llm_backend=None)

        # 应该找到 Python 文档
        assert len(results) > 0
        assert "python.md" in results[0].file

    def test_search_strong_signal_detection(
        self, indexed_db: Database, llm_backend: SentenceTransformerBackend
    ):
        """测试强信号检测（跳过查询扩展）"""
        # 精确关键词应该触发强信号
        results = search(indexed_db, "Python programming language", limit=10, llm_backend=llm_backend)

        assert len(results) > 0
        # Python 文档应该排第一
        assert "python.md" in results[0].file

    def test_search_semantic_matching(
        self, indexed_db: Database, llm_backend: SentenceTransformerBackend
    ):
        """测试语义匹配"""
        # 语义查询（不包含精确关键词）
        results = search(indexed_db, "web frontend development", limit=10, llm_backend=llm_backend)

        # JavaScript 应该匹配
        assert len(results) > 0
        assert any("javascript.md" in r.file for r in results)

    def test_search_empty_database(
        self, tmp_db: Database, llm_backend: SentenceTransformerBackend
    ):
        """测试空数据库"""
        results = search(tmp_db, "test query", limit=10, llm_backend=llm_backend)
        assert len(results) == 0

    def test_search_empty_query(
        self, indexed_db: Database, llm_backend: SentenceTransformerBackend
    ):
        """测试空查询"""
        results = search(indexed_db, "", limit=10, llm_backend=llm_backend)
        assert len(results) == 0

    def test_search_no_vectors(self, tmp_db: Database, tmp_path: Path):
        """测试没有向量时降级到 BM25"""
        store = Store(tmp_db)

        # 索引文档但不生成向量
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(exist_ok=True)

        doc = docs_dir / "test.md"
        doc.write_text("# Test Document\n\nPython programming.", encoding="utf-8")

        collection = NamedCollection(
            name="test", path=str(docs_dir), pattern="**/*.md"
        )
        store.update_collection(collection, auto_embed=False)

        # 搜索应该使用 BM25
        results = search(tmp_db, "Python programming", limit=10, llm_backend=None)

        assert len(results) > 0
        assert "test.md" in results[0].file

    def test_search_limit(
        self, indexed_db: Database, llm_backend: SentenceTransformerBackend
    ):
        """测试结果数量限制"""
        results = search(indexed_db, "programming", limit=2, llm_backend=llm_backend)
        assert len(results) <= 2

    def test_search_collection_filter(
        self, tmp_db: Database, tmp_path: Path, llm_backend: SentenceTransformerBackend
    ):
        """测试集合过滤"""
        store = Store(tmp_db)

        # 创建两个集合
        coll1_dir = tmp_path / "coll1"
        coll1_dir.mkdir()
        (coll1_dir / "doc.md").write_text(
            "# Programming Guide\n\nPython programming tutorial.", encoding="utf-8"
        )

        coll2_dir = tmp_path / "coll2"
        coll2_dir.mkdir()
        (coll2_dir / "doc.md").write_text(
            "# Cooking Recipe\n\nHow to cook pasta.", encoding="utf-8"
        )

        coll1 = NamedCollection(name="coll1", path=str(coll1_dir), pattern="**/*.md")
        coll2 = NamedCollection(name="coll2", path=str(coll2_dir), pattern="**/*.md")

        store.update_collection(coll1, llm_backend=llm_backend, auto_embed=True)
        store.update_collection(coll2, llm_backend=llm_backend, auto_embed=True)

        # 只搜索 coll1
        results = search(tmp_db, "programming", collection="coll1", limit=10, llm_backend=llm_backend)

        assert len(results) > 0
        assert all(r.collection == "coll1" for r in results)

    def test_search_ranking_quality(
        self, indexed_db: Database, llm_backend: SentenceTransformerBackend
    ):
        """测试排序质量"""
        # 精确匹配应该排在前面
        results = search(indexed_db, "Rust systems programming", limit=10, llm_backend=llm_backend)

        assert len(results) > 0
        # Rust 文档应该排第一或第二
        top_files = [r.file for r in results[:2]]
        assert any("rust.md" in f for f in top_files)

    def test_search_score_monotonicity(
        self, indexed_db: Database, llm_backend: SentenceTransformerBackend
    ):
        """测试分数单调性（结果应该按分数降序排列）"""
        results = search(indexed_db, "programming", limit=10, llm_backend=llm_backend)

        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].score >= results[i + 1].score


# === 边界情况测试 ===


class TestEdgeCases:
    """边界情况测试"""

    @pytest.fixture
    def tmp_db(self, tmp_path: Path) -> Database:
        """创建临时数据库"""
        db_path = tmp_path / "test.db"
        conn = open_database(str(db_path))
        init_schema(conn)
        return Database(conn)

    def test_bm25_search_special_characters(self, tmp_db: Database, tmp_path: Path):
        """测试特殊字符查询"""
        store = Store(tmp_db)

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "test.md").write_text("# Test\n\nC++ programming", encoding="utf-8")

        collection = NamedCollection(name="test", path=str(docs_dir), pattern="**/*.md")
        store.update_collection(collection)

        # FTS5 应该能处理特殊字符
        results = bm25_search(tmp_db, "C++", limit=10)
        # 可能返回空或有结果，不应该崩溃
        assert isinstance(results, list)

    def test_vector_search_dimension_mismatch(
        self, tmp_db: Database, tmp_path: Path
    ):
        """测试维度不匹配"""
        # 创建 384 维的 vectors_vec 表
        ensure_vec_table(tmp_db.conn, dimensions=384)

        # 查询 512 维（维度不匹配）
        query_embedding = [0.1] * 512

        # 应该捕获异常或返回空结果
        try:
            results = vector_search(tmp_db, query_embedding, limit=10)
            # 如果没有抛出异常，应该返回空结果
            assert len(results) == 0
        except Exception:
            # 允许抛出异常
            pass

    def test_search_very_long_query(
        self, tmp_db: Database, tmp_path: Path
    ):
        """测试超长查询"""
        store = Store(tmp_db)

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "test.md").write_text("# Test\n\nShort content", encoding="utf-8")

        collection = NamedCollection(name="test", path=str(docs_dir), pattern="**/*.md")
        store.update_collection(collection)

        # 超长查询（1000 个词）
        long_query = " ".join(["word"] * 1000)

        # 不应该崩溃
        results = search(tmp_db, long_query, limit=10, llm_backend=None)
        assert isinstance(results, list)

    def test_rrf_many_lists(self):
        """测试大量列表的 RRF 融合"""
        # 创建 100 个列表
        lists = []
        for i in range(100):
            lists.append([
                RankedResult(file=f"doc{i}.md", title=f"Doc {i}", body=f"Body {i}", score=0.9)
            ])

        # 不应该崩溃
        fused = reciprocal_rank_fusion(lists, k=60)
        assert len(fused) == 100
