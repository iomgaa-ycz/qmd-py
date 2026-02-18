"""
测试 llama-cpp-python 后端实现

使用 unittest.mock 模拟 llama_cpp.Llama，避免依赖实际的 GGUF 模型文件。
"""

import math
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from qmd.llm.base import ExpandedQuery, RerankDocument
from qmd.llm.llama_cpp import (
    LlamaCppBackend,
    format_doc_for_embedding,
    format_query_for_embedding,
)
from qmd.llm.models import ModelManager


# =============================================================================
# 测试格式化函数
# =============================================================================


def test_format_query_for_embedding():
    """测试查询格式化"""
    query = "authentication flow"
    expected = "task: search result | query: authentication flow"
    assert format_query_for_embedding(query) == expected


def test_format_doc_for_embedding_with_title():
    """测试文档格式化（有标题）"""
    text = "Document content"
    title = "My Title"
    expected = "title: My Title | text: Document content"
    assert format_doc_for_embedding(text, title) == expected


def test_format_doc_for_embedding_without_title():
    """测试文档格式化（无标题）"""
    text = "Document content"
    expected = "title: none | text: Document content"
    assert format_doc_for_embedding(text) == expected


# =============================================================================
# 测试 LlamaCppBackend
# =============================================================================


class TestLlamaCppBackend:
    """LlamaCppBackend 测试类"""

    @pytest.fixture
    def mock_model_manager(self, tmp_path: Path):
        """
        创建 mock ModelManager

        Args:
            tmp_path: pytest 提供的临时目录

        Returns:
            Mock ModelManager 实例
        """
        manager = Mock(spec=ModelManager)
        manager.embed_model_uri = "hf:test/embed/model.gguf"
        manager.rerank_model_uri = "hf:test/rerank/model.gguf"
        manager.generate_model_uri = "hf:test/generate/model.gguf"
        manager.cache_dir = tmp_path / "models"
        manager.cache_dir.mkdir(parents=True, exist_ok=True)
        manager.gpu_type = "cpu"
        manager.embed_model = None
        manager.rerank_model = None
        manager.generate_model = None

        # Mock 操作计数方法
        manager.start_operation = Mock()
        manager.end_operation = Mock()
        manager.unload = Mock()

        return manager

    @pytest.fixture
    def backend(self, mock_model_manager: Mock):
        """
        创建 LlamaCppBackend 实例

        Args:
            mock_model_manager: Mock ModelManager

        Returns:
            LlamaCppBackend 实例
        """
        return LlamaCppBackend(model_manager=mock_model_manager)

    def test_init(self, backend: LlamaCppBackend, mock_model_manager: Mock):
        """测试初始化"""
        assert backend.model_manager == mock_model_manager
        assert backend._embed_model_instance is None
        assert backend._rerank_model_instance is None
        assert backend._generate_model_instance is None

    def test_get_embedding_dimensions(self, backend: LlamaCppBackend):
        """测试获取 embedding 维度"""
        assert backend.get_embedding_dimensions() == 768

    def test_embed_success(
        self, backend: LlamaCppBackend, mock_model_manager: Mock, tmp_path: Path
    ):
        """测试 embed 成功"""
        # 创建假的模型文件
        model_path = tmp_path / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

        # Mock Llama 实例
        mock_llama = MagicMock()
        mock_embedding = [0.1, 0.2, 0.3] * 256  # 768 维
        mock_llama.embed.return_value = mock_embedding

        # Mock Llama 构造函数
        with patch("qmd.llm.llama_cpp.Llama", return_value=mock_llama):
            result = backend.embed("test text", is_query=True)

        assert result is not None
        assert result.embedding == mock_embedding
        assert result.model == mock_model_manager.embed_model_uri

        # 验证格式化
        mock_llama.embed.assert_called_once_with(
            "task: search result | query: test text"
        )

        # 验证操作计数
        mock_model_manager.start_operation.assert_called_once()
        mock_model_manager.end_operation.assert_called_once()

    def test_embed_document_with_title(
        self, backend: LlamaCppBackend, mock_model_manager: Mock, tmp_path: Path
    ):
        """测试文档 embedding（有标题）"""
        model_path = tmp_path / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

        mock_llama = MagicMock()
        mock_embedding = [0.1] * 768
        mock_llama.embed.return_value = mock_embedding

        with patch("qmd.llm.llama_cpp.Llama", return_value=mock_llama):
            result = backend.embed("doc content", is_query=False, title="Doc Title")

        assert result is not None
        mock_llama.embed.assert_called_once_with(
            "title: Doc Title | text: doc content"
        )

    def test_embed_file_not_found(self, backend: LlamaCppBackend):
        """测试 embed 时模型文件不存在"""
        # 不创建模型文件，embed 应该返回 None（异常被捕获）
        result = backend.embed("test text")
        assert result is None

    def test_embed_exception(
        self, backend: LlamaCppBackend, mock_model_manager: Mock, tmp_path: Path
    ):
        """测试 embed 发生异常"""
        model_path = tmp_path / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

        mock_llama = MagicMock()
        mock_llama.embed.side_effect = RuntimeError("Embedding failed")

        with patch("qmd.llm.llama_cpp.Llama", return_value=mock_llama):
            result = backend.embed("test text")

        # 异常时应返回 None
        assert result is None

        # 仍然要调用 end_operation
        mock_model_manager.end_operation.assert_called_once()

    def test_embed_batch_success(
        self, backend: LlamaCppBackend, mock_model_manager: Mock, tmp_path: Path
    ):
        """测试批量 embedding"""
        model_path = tmp_path / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

        mock_llama = MagicMock()
        mock_embedding = [0.1] * 768
        mock_llama.embed.return_value = mock_embedding

        texts = ["text1", "text2", "text3"]
        titles = ["title1", "title2", None]

        with patch("qmd.llm.llama_cpp.Llama", return_value=mock_llama):
            results = backend.embed_batch(texts, titles)

        assert len(results) == 3
        assert all(r is not None for r in results)
        assert all(r.embedding == mock_embedding for r in results if r)

        # 验证调用了 3 次 embed
        assert mock_llama.embed.call_count == 3

        # 验证格式化
        expected_calls = [
            "title: title1 | text: text1",
            "title: title2 | text: text2",
            "title: none | text: text3",
        ]
        for i, expected in enumerate(expected_calls):
            assert mock_llama.embed.call_args_list[i][0][0] == expected

    def test_embed_batch_empty(self, backend: LlamaCppBackend):
        """测试空批次"""
        results = backend.embed_batch([])
        assert results == []

    def test_embed_batch_titles_mismatch(self, backend: LlamaCppBackend):
        """测试 titles 长度不匹配"""
        texts = ["text1", "text2"]
        titles = ["title1"]  # 长度不匹配

        with pytest.raises(ValueError, match="titles 长度.*不匹配"):
            backend.embed_batch(texts, titles)

    def test_rerank_success(
        self, backend: LlamaCppBackend, mock_model_manager: Mock, tmp_path: Path
    ):
        """测试 rerank 成功"""
        model_path = tmp_path / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

        # Mock rerank 输出（yes/no logprobs）
        def mock_llama_call(prompt, **kwargs):
            # 根据文档内容返回不同的分数
            if "doc1" in prompt:
                yes_logprob = math.log(0.8)
                no_logprob = math.log(0.2)
            elif "doc2" in prompt:
                yes_logprob = math.log(0.3)
                no_logprob = math.log(0.7)
            else:
                yes_logprob = math.log(0.5)
                no_logprob = math.log(0.5)

            return {
                "choices": [
                    {
                        "logprobs": {
                            "top_logprobs": [
                                {
                                    " yes": yes_logprob,
                                    " no": no_logprob,
                                }
                            ]
                        }
                    }
                ]
            }

        # 创建一个可调用的 Mock
        mock_llama = Mock(side_effect=mock_llama_call)

        documents = [
            RerankDocument(file="file1.md", text="doc1 content"),
            RerankDocument(file="file2.md", text="doc2 content"),
            RerankDocument(file="file3.md", text="doc3 content"),
        ]

        with patch("qmd.llm.llama_cpp.Llama", return_value=mock_llama):
            result = backend.rerank("test query", documents)

        assert result is not None
        assert len(result.results) == 3
        assert result.model == mock_model_manager.rerank_model_uri

        # 验证排序（doc1 分数最高，doc2 最低）
        assert result.results[0].file == "file1.md"
        assert result.results[0].score == pytest.approx(0.8, rel=0.01)
        assert result.results[2].file == "file2.md"
        assert result.results[2].score == pytest.approx(0.3, rel=0.01)

    def test_rerank_top_n(
        self, backend: LlamaCppBackend, mock_model_manager: Mock, tmp_path: Path
    ):
        """测试 rerank top_n 限制"""
        model_path = tmp_path / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

        def mock_call(prompt, **kwargs):
            return {
                "choices": [
                    {
                        "logprobs": {
                            "top_logprobs": [
                                {" yes": math.log(0.5), " no": math.log(0.5)}
                            ]
                        }
                    }
                ]
            }

        mock_llama = Mock(side_effect=mock_call)

        documents = [
            RerankDocument(file=f"file{i}.md", text=f"doc{i}")
            for i in range(10)
        ]

        with patch("qmd.llm.llama_cpp.Llama", return_value=mock_llama):
            result = backend.rerank("query", documents, top_n=3)

        # 只返回前 3 个
        assert len(result.results) == 3

    def test_rerank_missing_yes_no_tokens(
        self, backend: LlamaCppBackend, mock_model_manager: Mock, tmp_path: Path
    ):
        """测试 rerank 缺少 yes/no token"""
        model_path = tmp_path / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

        # 返回不包含 yes/no 的 logprobs
        mock_llama = Mock(
            return_value={
                "choices": [
                    {
                        "logprobs": {
                            "top_logprobs": [
                                {" maybe": math.log(0.5), " unknown": math.log(0.5)}
                            ]
                        }
                    }
                ]
            }
        )

        documents = [RerankDocument(file="file1.md", text="doc1")]

        with patch("qmd.llm.llama_cpp.Llama", return_value=mock_llama):
            result = backend.rerank("query", documents)

        # 缺少 yes/no 时应该返回分数 0.0
        assert result.results[0].score == 0.0

    def test_rerank_empty_output(
        self, backend: LlamaCppBackend, mock_model_manager: Mock, tmp_path: Path
    ):
        """测试 rerank 输出为空"""
        model_path = tmp_path / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

        mock_llama = Mock(return_value={})  # 空输出

        documents = [RerankDocument(file="file1.md", text="doc1")]

        with patch("qmd.llm.llama_cpp.Llama", return_value=mock_llama):
            result = backend.rerank("query", documents)

        # 空输出应该返回分数 0.0
        assert result.results[0].score == 0.0

    def test_rerank_exception(
        self, backend: LlamaCppBackend, mock_model_manager: Mock, tmp_path: Path
    ):
        """测试 rerank 异常"""
        model_path = tmp_path / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

        mock_llama = Mock(side_effect=RuntimeError("Rerank failed"))

        documents = [RerankDocument(file="file1.md", text="doc1")]

        with patch("qmd.llm.llama_cpp.Llama", return_value=mock_llama):
            result = backend.rerank("query", documents)

        # 异常时返回空结果
        assert result.results == []

    def test_expand_query_success(
        self, backend: LlamaCppBackend, mock_model_manager: Mock, tmp_path: Path
    ):
        """测试 expand_query 成功"""
        model_path = tmp_path / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

        # Mock 生成的扩展查询
        mock_llama = Mock(
            return_value={
                "choices": [
                    {
                        "text": "lex: authentication login\nvec: user authentication process\nhyde: How to implement authentication flow in web applications"
                    }
                ]
            }
        )

        with patch("qmd.llm.llama_cpp.Llama", return_value=mock_llama):
            result = backend.expand_query("authentication flow")

        assert len(result) == 3
        assert result[0].type == "lex"
        assert "authentication" in result[0].text.lower()
        assert result[1].type == "vec"
        assert "authentication" in result[1].text.lower()
        assert result[2].type == "hyde"
        assert "authentication" in result[2].text.lower()

    def test_expand_query_invalid_type(
        self, backend: LlamaCppBackend, mock_model_manager: Mock, tmp_path: Path
    ):
        """测试 expand_query 包含无效类型"""
        model_path = tmp_path / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

        # 包含无效类型（foo）
        mock_llama = Mock(
            return_value={
                "choices": [
                    {
                        "text": "lex: authentication login\nfoo: invalid type\nvec: user authentication"
                    }
                ]
            }
        )

        with patch("qmd.llm.llama_cpp.Llama", return_value=mock_llama):
            result = backend.expand_query("authentication")

        # 只保留有效类型
        assert len(result) == 2
        assert all(q.type in ["lex", "vec", "hyde"] for q in result)

    def test_expand_query_no_matching_terms(
        self, backend: LlamaCppBackend, mock_model_manager: Mock, tmp_path: Path
    ):
        """测试 expand_query 不包含原始关键词"""
        model_path = tmp_path / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

        # 生成的查询不包含 "auth" 关键词
        mock_llama = Mock(
            return_value={"choices": [{"text": "lex: login system\nvec: user login"}]}
        )

        with patch("qmd.llm.llama_cpp.Llama", return_value=mock_llama):
            result = backend.expand_query("auth")

        # 没有匹配的关键词，返回 fallback
        assert len(result) == 3
        assert result[0].type == "hyde"
        assert "auth" in result[0].text.lower()

    def test_expand_query_empty_output(
        self, backend: LlamaCppBackend, mock_model_manager: Mock, tmp_path: Path
    ):
        """测试 expand_query 输出为空"""
        model_path = tmp_path / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

        mock_llama = Mock(return_value={"choices": [{"text": ""}]})

        with patch("qmd.llm.llama_cpp.Llama", return_value=mock_llama):
            result = backend.expand_query("test")

        # 空输出返回 fallback
        assert len(result) == 3
        assert result[0].type == "hyde"

    def test_expand_query_exception(
        self, backend: LlamaCppBackend, mock_model_manager: Mock, tmp_path: Path
    ):
        """测试 expand_query 异常"""
        model_path = tmp_path / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

        mock_llama = Mock(side_effect=RuntimeError("Generate failed"))

        with patch("qmd.llm.llama_cpp.Llama", return_value=mock_llama):
            result = backend.expand_query("test")

        # 异常时返回 fallback
        assert len(result) == 3

    def test_fallback_queries(self, backend: LlamaCppBackend):
        """测试 fallback 查询生成"""
        result = backend._fallback_queries("test query")

        assert len(result) == 3
        assert result[0].type == "hyde"
        assert "test query" in result[0].text
        assert result[1].type == "lex"
        assert result[1].text == "test query"
        assert result[2].type == "vec"
        assert result[2].text == "test query"

    def test_close(self, backend: LlamaCppBackend, mock_model_manager: Mock):
        """测试 close"""
        # 设置一些模型实例
        backend._embed_model_instance = MagicMock()
        backend._rerank_model_instance = MagicMock()
        backend._generate_model_instance = MagicMock()

        backend.close()

        # 验证实例被清空
        assert backend._embed_model_instance is None
        assert backend._rerank_model_instance is None
        assert backend._generate_model_instance is None

        # 验证调用了 ModelManager.unload
        mock_model_manager.unload.assert_called_once()

    def test_model_caching(
        self, backend: LlamaCppBackend, mock_model_manager: Mock, tmp_path: Path
    ):
        """测试模型实例缓存"""
        model_path = tmp_path / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.touch()

        mock_llama = MagicMock()
        mock_llama.embed.return_value = [0.1] * 768

        with patch("qmd.llm.llama_cpp.Llama", return_value=mock_llama) as mock_constructor:
            # 第一次调用
            backend.embed("text1")
            # 第二次调用（应该复用实例）
            backend.embed("text2")

            # Llama 构造函数只应该被调用一次
            assert mock_constructor.call_count == 1

            # embed 方法应该被调用两次
            assert mock_llama.embed.call_count == 2
