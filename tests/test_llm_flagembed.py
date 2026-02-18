"""
测试 FlagEmbedding 后端实现

使用 mock FlagReranker 类来避免加载大型模型，但被测试的 FlagEmbeddingBackend 代码
必须是真实调用 FlagReranker API 的实现。
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from qmd.llm.base import RerankDocument
from qmd.llm.flagembed import FlagEmbeddingBackend


class TestFlagEmbeddingBackend:
    """FlagEmbeddingBackend 测试类"""

    @pytest.fixture
    def mock_reranker(self):
        """
        创建 mock FlagReranker

        Returns:
            Mock FlagReranker 实例
        """
        mock = MagicMock()
        # compute_score 返回分数列表
        mock.compute_score.return_value = [0.8, 0.3, 0.6]
        return mock

    @pytest.fixture
    def backend(self):
        """
        创建 backend 实例

        Returns:
            FlagEmbeddingBackend 实例
        """
        return FlagEmbeddingBackend(
            reranker_model_name="BAAI/bge-reranker-v2-m3", device="cpu"
        )

    def test_init(self):
        """测试初始化"""
        backend = FlagEmbeddingBackend(reranker_model_name="BAAI/bge-reranker-v2-m3")
        assert backend.reranker_model_name == "BAAI/bge-reranker-v2-m3"
        assert backend.device in ["cuda", "cpu"]
        assert backend._reranker is None  # 懒加载，初始为 None

    def test_init_with_custom_device(self):
        """测试自定义设备"""
        backend = FlagEmbeddingBackend(device="cpu")
        assert backend.device == "cpu"

    def test_auto_detect_device(self):
        """测试自动设备检测"""
        backend = FlagEmbeddingBackend()
        device = backend._auto_detect_device()
        assert device in ["cuda", "cpu"]

    def test_embed_raises_not_implemented(self, backend: FlagEmbeddingBackend):
        """测试 embed 抛出 NotImplementedError"""
        with pytest.raises(NotImplementedError, match="不支持 embedding"):
            backend.embed("test text")

    def test_embed_batch_raises_not_implemented(self, backend: FlagEmbeddingBackend):
        """测试 embed_batch 抛出 NotImplementedError"""
        with pytest.raises(NotImplementedError, match="不支持 embedding"):
            backend.embed_batch(["test1", "test2"])

    def test_get_embedding_dimensions(self, backend: FlagEmbeddingBackend):
        """测试获取向量维度（应返回 0）"""
        dim = backend.get_embedding_dimensions()
        assert dim == 0

    def test_rerank_success(
        self, backend: FlagEmbeddingBackend, mock_reranker: MagicMock
    ):
        """测试 rerank 成功"""
        documents = [
            RerankDocument(file="doc1.md", text="Document 1"),
            RerankDocument(file="doc2.md", text="Document 2"),
            RerankDocument(file="doc3.md", text="Document 3"),
        ]

        query = "test query"

        with patch("qmd.llm.flagembed.FlagReranker", return_value=mock_reranker):
            result = backend.rerank(query, documents)

        assert result is not None
        assert len(result.results) == 3
        assert result.model == "BAAI/bge-reranker-v2-m3"

        # 验证调用 compute_score
        mock_reranker.compute_score.assert_called_once()
        call_args = mock_reranker.compute_score.call_args[0][0]
        assert len(call_args) == 3
        assert call_args[0] == [query, "Document 1"]
        assert call_args[1] == [query, "Document 2"]
        assert call_args[2] == [query, "Document 3"]

        # 验证排序（分数：0.8, 0.3, 0.6）
        assert result.results[0].file == "doc1.md"  # 0.8 最高
        assert result.results[0].score == 0.8
        assert result.results[1].file == "doc3.md"  # 0.6 第二
        assert result.results[1].score == 0.6
        assert result.results[2].file == "doc2.md"  # 0.3 最低
        assert result.results[2].score == 0.3

        # 验证索引
        assert result.results[0].index == 0
        assert result.results[1].index == 2
        assert result.results[2].index == 1

    def test_rerank_top_n(
        self, backend: FlagEmbeddingBackend, mock_reranker: MagicMock
    ):
        """测试 rerank top_n 限制"""
        # 设置返回 10 个分数
        mock_reranker.compute_score.return_value = [
            0.9,
            0.8,
            0.7,
            0.6,
            0.5,
            0.4,
            0.3,
            0.2,
            0.1,
            0.0,
        ]

        documents = [
            RerankDocument(file=f"doc{i}.md", text=f"Document {i}")
            for i in range(10)
        ]

        with patch("qmd.llm.flagembed.FlagReranker", return_value=mock_reranker):
            result = backend.rerank("query", documents, top_n=3)

        # 只返回前 3 个
        assert len(result.results) == 3
        assert result.results[0].score == 0.9
        assert result.results[1].score == 0.8
        assert result.results[2].score == 0.7

    def test_rerank_empty_documents(self, backend: FlagEmbeddingBackend):
        """测试空文档列表"""
        with patch("qmd.llm.flagembed.FlagReranker"):
            result = backend.rerank("query", [])

        assert result is not None
        assert len(result.results) == 0

    def test_rerank_single_document(
        self, backend: FlagEmbeddingBackend, mock_reranker: MagicMock
    ):
        """测试单个文档"""
        # 单个文档时，compute_score 可能返回 float 而非 list
        mock_reranker.compute_score.return_value = 0.85

        documents = [RerankDocument(file="doc.md", text="test document")]

        with patch("qmd.llm.flagembed.FlagReranker", return_value=mock_reranker):
            result = backend.rerank("query", documents)

        assert len(result.results) == 1
        assert result.results[0].file == "doc.md"
        assert result.results[0].score == 0.85

    def test_rerank_exception(
        self, backend: FlagEmbeddingBackend, mock_reranker: MagicMock
    ):
        """测试 rerank 异常"""
        mock_reranker.compute_score.side_effect = RuntimeError("Rerank failed")

        documents = [RerankDocument(file="doc.md", text="test")]

        with patch("qmd.llm.flagembed.FlagReranker", return_value=mock_reranker):
            result = backend.rerank("query", documents)

        # 异常时返回空结果
        assert len(result.results) == 0

    def test_expand_query(self, backend: FlagEmbeddingBackend):
        """测试 query expansion（fallback 版本）"""
        query = "test query"

        result = backend.expand_query(query)

        # 应该返回简单的 fallback
        assert len(result) == 2
        assert result[0].type == "lex"
        assert result[0].text == query
        assert result[1].type == "vec"
        assert result[1].text == query

    def test_expand_query_with_context(self, backend: FlagEmbeddingBackend):
        """测试带上下文的 query expansion"""
        query = "test"
        context = "some context"

        result = backend.expand_query(query, context)

        # context 应该被忽略
        assert len(result) == 2
        assert result[0].text == query
        assert result[1].text == query

    def test_close(self, backend: FlagEmbeddingBackend, mock_reranker: MagicMock):
        """测试 close"""
        # 先加载模型
        with patch("qmd.llm.flagembed.FlagReranker", return_value=mock_reranker):
            _ = backend._get_reranker()
            assert backend._reranker is not None

        # 关闭
        backend.close()

        # 验证模型被清空
        assert backend._reranker is None

    def test_model_lazy_loading(
        self, backend: FlagEmbeddingBackend, mock_reranker: MagicMock
    ):
        """测试模型懒加载"""
        # 初始化后模型未加载
        assert backend._reranker is None

        documents = [RerankDocument(file="doc.md", text="test")]

        with patch("qmd.llm.flagembed.FlagReranker", return_value=mock_reranker):
            # 第一次调用触发加载
            _ = backend.rerank("query", documents)
            assert backend._reranker is not None

            # 后续调用复用实例
            reranker_instance = backend._reranker
            _ = backend.rerank("query", documents)
            assert backend._reranker is reranker_instance  # 同一个实例

    def test_rerank_score_range(
        self, backend: FlagEmbeddingBackend, mock_reranker: MagicMock
    ):
        """测试 rerank 分数范围"""
        # FlagReranker 分数通常在 [-10, 10] 范围，但没有严格限制
        mock_reranker.compute_score.return_value = [5.2, -2.3, 0.0, 8.7]

        documents = [
            RerankDocument(file=f"doc{i}.md", text=f"Document {i}")
            for i in range(4)
        ]

        with patch("qmd.llm.flagembed.FlagReranker", return_value=mock_reranker):
            result = backend.rerank("query", documents)

        # 验证分数被正确保存
        scores = [r.score for r in result.results]
        assert 8.7 in scores
        assert 5.2 in scores
        assert 0.0 in scores
        assert -2.3 in scores

    def test_integration_rerank_sorting(
        self, backend: FlagEmbeddingBackend, mock_reranker: MagicMock
    ):
        """集成测试：验证完整的 rerank 排序流程"""
        # 模拟真实场景：查询 "machine learning"，文档相关性不同
        query = "machine learning"

        documents = [
            RerankDocument(file="irrelevant.md", text="Cooking recipes"),
            RerankDocument(file="relevant.md", text="Machine learning algorithms"),
            RerankDocument(
                file="somewhat.md", text="Computer science and programming"
            ),
        ]

        # 模拟分数：irrelevant=0.1, relevant=0.9, somewhat=0.5
        mock_reranker.compute_score.return_value = [0.1, 0.9, 0.5]

        with patch("qmd.llm.flagembed.FlagReranker", return_value=mock_reranker):
            result = backend.rerank(query, documents, top_n=2)

        # 验证排序和 top_n
        assert len(result.results) == 2
        assert result.results[0].file == "relevant.md"  # 0.9 最高
        assert result.results[1].file == "somewhat.md"  # 0.5 第二

    def test_get_reranker_with_cuda(self, mock_reranker: MagicMock):
        """测试 CUDA 设备时的 use_fp16 参数"""
        backend = FlagEmbeddingBackend(device="cuda")

        with patch("qmd.llm.flagembed.FlagReranker", return_value=mock_reranker) as mock_constructor:
            _ = backend._get_reranker()

            # 验证使用 use_fp16=True
            mock_constructor.assert_called_once_with(
                "BAAI/bge-reranker-v2-m3", use_fp16=True
            )

    def test_get_reranker_with_cpu(self, mock_reranker: MagicMock):
        """测试 CPU 设备时的 use_fp16 参数"""
        backend = FlagEmbeddingBackend(device="cpu")

        with patch("qmd.llm.flagembed.FlagReranker", return_value=mock_reranker) as mock_constructor:
            _ = backend._get_reranker()

            # 验证使用 use_fp16=False
            mock_constructor.assert_called_once_with(
                "BAAI/bge-reranker-v2-m3", use_fp16=False
            )
