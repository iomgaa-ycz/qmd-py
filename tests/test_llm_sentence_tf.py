"""
测试 sentence-transformers 后端实现

使用真实的 sentence-transformers 模型进行测试（paraphrase-multilingual-MiniLM-L12-v2，支持中英双语）。
"""

import numpy as np
import pytest

from qmd.llm.base import RerankDocument
from qmd.llm.sentence_tf import SentenceTransformerBackend


class TestSentenceTransformerBackend:
    """SentenceTransformerBackend 测试类"""

    @pytest.fixture(scope="class")
    def backend(self):
        """
        创建共享的 backend 实例（减少模型加载次数）

        Returns:
            SentenceTransformerBackend 实例
        """
        # 使用默认多语言模型 paraphrase-multilingual-MiniLM-L12-v2（384 维，支持中英双语）
        return SentenceTransformerBackend(model_name="paraphrase-multilingual-MiniLM-L12-v2", device="cpu")

    def test_init(self):
        """测试初始化"""
        backend = SentenceTransformerBackend(model_name="paraphrase-multilingual-MiniLM-L12-v2")
        assert backend.model_name == "paraphrase-multilingual-MiniLM-L12-v2"
        assert backend.device in ["cuda", "mps", "cpu"]
        assert backend._model is None  # 懒加载，初始为 None

    def test_init_with_custom_device(self):
        """测试自定义设备"""
        backend = SentenceTransformerBackend(device="cpu")
        assert backend.device == "cpu"

    def test_auto_detect_device(self):
        """测试自动设备检测"""
        backend = SentenceTransformerBackend()
        device = backend._auto_detect_device()
        assert device in ["cuda", "mps", "cpu"]

    def test_get_embedding_dimensions(self, backend: SentenceTransformerBackend):
        """测试获取向量维度"""
        dim = backend.get_embedding_dimensions()
        # paraphrase-multilingual-MiniLM-L12-v2 的维度是 384
        assert dim == 384

    def test_embed_success(self, backend: SentenceTransformerBackend):
        """测试单个 embedding"""
        result = backend.embed("This is a test sentence.")

        assert result is not None
        assert result.model == "paraphrase-multilingual-MiniLM-L12-v2"
        assert len(result.embedding) == 384
        # 验证向量不是全零
        assert not all(v == 0 for v in result.embedding)
        # 验证向量值在合理范围内
        assert all(-10 < v < 10 for v in result.embedding)

    def test_embed_query_vs_document(self, backend: SentenceTransformerBackend):
        """测试查询和文档的 embedding"""
        query_result = backend.embed("search query", is_query=True)
        doc_result = backend.embed("search query", is_query=False, title="Test")

        assert query_result is not None
        assert doc_result is not None

        # 由于 sentence-transformers 不区分 query/document，
        # 相同文本应该产生相同的向量
        assert len(query_result.embedding) == len(doc_result.embedding)

        # 计算余弦相似度应该接近 1
        q_vec = np.array(query_result.embedding)
        d_vec = np.array(doc_result.embedding)
        cosine_sim = np.dot(q_vec, d_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(d_vec))
        assert cosine_sim > 0.99  # 应该非常接近

    def test_embed_empty_string(self, backend: SentenceTransformerBackend):
        """测试空字符串 embedding"""
        result = backend.embed("")

        assert result is not None
        assert len(result.embedding) == 384

    def test_embed_batch_success(self, backend: SentenceTransformerBackend):
        """测试批量 embedding"""
        texts = [
            "First sentence",
            "Second sentence",
            "Third sentence",
        ]

        results = backend.embed_batch(texts)

        assert len(results) == 3
        assert all(r is not None for r in results)
        assert all(len(r.embedding) == 384 for r in results if r)
        assert all(r.model == "paraphrase-multilingual-MiniLM-L12-v2" for r in results if r)

        # 验证不同文本产生不同向量
        vec1 = np.array(results[0].embedding)
        vec2 = np.array(results[1].embedding)
        cosine_sim = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
        # 不同句子的相似度应该小于 1
        assert cosine_sim < 0.99

    def test_embed_batch_empty(self, backend: SentenceTransformerBackend):
        """测试空批次"""
        results = backend.embed_batch([])
        assert results == []

    def test_embed_batch_with_titles(self, backend: SentenceTransformerBackend):
        """测试带标题的批量 embedding"""
        texts = ["Text 1", "Text 2"]
        titles = ["Title 1", "Title 2"]

        results = backend.embed_batch(texts, titles)

        assert len(results) == 2
        assert all(r is not None for r in results)

    def test_embed_batch_consistency(self, backend: SentenceTransformerBackend):
        """测试批量和单个 embedding 的一致性"""
        text = "Test consistency"

        # 单个 embedding
        single_result = backend.embed(text)

        # 批量 embedding
        batch_results = backend.embed_batch([text])

        assert single_result is not None
        assert len(batch_results) == 1
        assert batch_results[0] is not None

        # 向量应该非常接近（可能有微小的数值误差）
        single_vec = np.array(single_result.embedding)
        batch_vec = np.array(batch_results[0].embedding)

        # 使用较小的容差检查
        np.testing.assert_allclose(single_vec, batch_vec, rtol=1e-5, atol=1e-5)

    def test_rerank_success(self, backend: SentenceTransformerBackend):
        """测试 rerank 成功"""
        query = "machine learning algorithms"

        documents = [
            RerankDocument(
                file="doc1.md",
                text="Machine learning is a subset of artificial intelligence.",
            ),
            RerankDocument(
                file="doc2.md", text="Python is a popular programming language."
            ),
            RerankDocument(
                file="doc3.md",
                text="Deep learning algorithms use neural networks for pattern recognition.",
            ),
        ]

        result = backend.rerank(query, documents)

        assert result is not None
        assert len(result.results) == 3
        assert result.model == "paraphrase-multilingual-MiniLM-L12-v2"

        # 验证排序：doc3 和 doc1 应该比 doc2 更相关
        scores = {r.file: r.score for r in result.results}
        assert scores["doc3.md"] > scores["doc2.md"]
        assert scores["doc1.md"] > scores["doc2.md"]

        # 验证分数降序排列
        result_scores = [r.score for r in result.results]
        assert result_scores == sorted(result_scores, reverse=True)

        # 验证分数在 [-1, 1] 范围内（余弦相似度）
        assert all(-1 <= r.score <= 1 for r in result.results)

    def test_rerank_top_n(self, backend: SentenceTransformerBackend):
        """测试 rerank top_n 限制"""
        query = "test query"

        documents = [
            RerankDocument(file=f"doc{i}.md", text=f"Document {i}")
            for i in range(10)
        ]

        result = backend.rerank(query, documents, top_n=3)

        # 只返回前 3 个
        assert len(result.results) == 3

    def test_rerank_empty_documents(self, backend: SentenceTransformerBackend):
        """测试空文档列表"""
        result = backend.rerank("query", [])

        assert result is not None
        assert len(result.results) == 0

    def test_rerank_single_document(self, backend: SentenceTransformerBackend):
        """测试单个文档"""
        query = "test"
        documents = [RerankDocument(file="doc.md", text="test document")]

        result = backend.rerank(query, documents)

        assert len(result.results) == 1
        assert result.results[0].file == "doc.md"
        # 单个文档也应该有合理的分数
        assert -1 <= result.results[0].score <= 1

    def test_expand_query(self, backend: SentenceTransformerBackend):
        """测试 query expansion（fallback 版本）"""
        query = "test query"

        result = backend.expand_query(query)

        # 应该返回简单的 fallback
        assert len(result) == 2
        assert result[0].type == "lex"
        assert result[0].text == query
        assert result[1].type == "vec"
        assert result[1].text == query

    def test_expand_query_with_context(self, backend: SentenceTransformerBackend):
        """测试带上下文的 query expansion"""
        query = "test"
        context = "some context"

        result = backend.expand_query(query, context)

        # context 应该被忽略
        assert len(result) == 2
        assert result[0].text == query
        assert result[1].text == query

    def test_close(self, backend: SentenceTransformerBackend):
        """测试 close"""
        # 先加载模型
        _ = backend.get_embedding_dimensions()
        assert backend._model is not None

        # 关闭
        backend.close()

        # 验证模型被清空
        assert backend._model is None

    def test_integration_embed_and_rerank(
        self, backend: SentenceTransformerBackend
    ):
        """集成测试：embed → rerank 完整流程"""
        # 1. 准备查询和文档
        query = "natural language processing"

        documents = [
            RerankDocument(
                file="nlp.md",
                text="Natural language processing enables computers to understand human language.",
            ),
            RerankDocument(
                file="cooking.md",
                text="Cooking is the art of preparing food for consumption.",
            ),
            RerankDocument(
                file="ml.md",
                text="Machine learning models can process and analyze text data.",
            ),
        ]

        # 2. 生成查询向量
        query_result = backend.embed(query, is_query=True)
        assert query_result is not None

        # 3. 生成文档向量（批量）
        doc_texts = [doc.text for doc in documents]
        doc_results = backend.embed_batch(doc_texts)
        assert len(doc_results) == 3
        assert all(r is not None for r in doc_results)

        # 4. Rerank
        rerank_result = backend.rerank(query, documents, top_n=2)
        assert len(rerank_result.results) == 2

        # 5. 验证 NLP 文档应该排在前面
        top_file = rerank_result.results[0].file
        assert top_file == "nlp.md"

        # 6. 验证分数合理性
        assert rerank_result.results[0].score > rerank_result.results[1].score

    def test_semantic_similarity(self, backend: SentenceTransformerBackend):
        """测试语义相似度：相似句子应该有高相似度"""
        text1 = "The cat is sleeping on the couch."
        text2 = "A feline is resting on the sofa."
        text3 = "The stock market crashed today."

        # 生成向量
        vec1 = backend.embed(text1)
        vec2 = backend.embed(text2)
        vec3 = backend.embed(text3)

        assert vec1 is not None
        assert vec2 is not None
        assert vec3 is not None

        # 计算相似度
        v1 = np.array(vec1.embedding)
        v2 = np.array(vec2.embedding)
        v3 = np.array(vec3.embedding)

        sim_1_2 = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        sim_1_3 = np.dot(v1, v3) / (np.linalg.norm(v1) * np.linalg.norm(v3))

        # 相似句子的相似度应该高于不相关句子
        assert sim_1_2 > sim_1_3

    def test_model_lazy_loading(self):
        """测试模型懒加载"""
        backend = SentenceTransformerBackend()

        # 初始化后模型未加载
        assert backend._model is None

        # 第一次调用触发加载
        _ = backend.get_embedding_dimensions()
        assert backend._model is not None

        # 后续调用复用实例
        model_instance = backend._model
        _ = backend.embed("test")
        assert backend._model is model_instance  # 同一个实例
