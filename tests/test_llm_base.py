"""
测试 LLM 抽象接口和数据类型

仅测试数据类型的创建和属性访问，不测试具体实现。
"""

import pytest

from qmd.llm.base import (
    EmbeddingResult,
    ExpandedQuery,
    LLMBackend,
    RerankDocument,
    RerankDocumentResult,
    RerankResult,
    Tokenizer,
)


class TestEmbeddingResult:
    """测试 EmbeddingResult 数据类"""

    def test_create_embedding_result(self):
        """测试创建 EmbeddingResult"""
        embedding = [0.1, 0.2, 0.3, 0.4]
        model = "test-model"

        result = EmbeddingResult(embedding=embedding, model=model)

        assert result.embedding == embedding
        assert result.model == model

    def test_embedding_result_frozen(self):
        """测试 EmbeddingResult 是不可变的"""
        result = EmbeddingResult(embedding=[0.1, 0.2], model="test")

        with pytest.raises(AttributeError):
            result.embedding = [0.3, 0.4]

        with pytest.raises(AttributeError):
            result.model = "new-model"

    def test_embedding_result_equality(self):
        """测试 EmbeddingResult 相等性"""
        result1 = EmbeddingResult(embedding=[0.1, 0.2], model="test")
        result2 = EmbeddingResult(embedding=[0.1, 0.2], model="test")
        result3 = EmbeddingResult(embedding=[0.3, 0.4], model="test")

        assert result1 == result2
        assert result1 != result3


class TestRerankDocumentResult:
    """测试 RerankDocumentResult 数据类"""

    def test_create_rerank_document_result(self):
        """测试创建 RerankDocumentResult"""
        file = "docs/test.md"
        score = 0.85
        index = 5

        result = RerankDocumentResult(file=file, score=score, index=index)

        assert result.file == file
        assert result.score == score
        assert result.index == index

    def test_rerank_document_result_frozen(self):
        """测试 RerankDocumentResult 是不可变的"""
        result = RerankDocumentResult(file="test.md", score=0.5, index=0)

        with pytest.raises(AttributeError):
            result.score = 0.9

    def test_rerank_document_result_equality(self):
        """测试 RerankDocumentResult 相等性"""
        result1 = RerankDocumentResult(file="test.md", score=0.5, index=0)
        result2 = RerankDocumentResult(file="test.md", score=0.5, index=0)
        result3 = RerankDocumentResult(file="test.md", score=0.8, index=0)

        assert result1 == result2
        assert result1 != result3


class TestRerankResult:
    """测试 RerankResult 数据类"""

    def test_create_rerank_result(self):
        """测试创建 RerankResult"""
        results = [
            RerankDocumentResult(file="doc1.md", score=0.9, index=0),
            RerankDocumentResult(file="doc2.md", score=0.7, index=1),
        ]
        model = "rerank-model"

        result = RerankResult(results=results, model=model)

        assert result.results == results
        assert result.model == model
        assert len(result.results) == 2

    def test_rerank_result_frozen(self):
        """测试 RerankResult 是不可变的"""
        result = RerankResult(results=[], model="test")

        with pytest.raises(AttributeError):
            result.model = "new-model"

    def test_rerank_result_empty_list(self):
        """测试空结果列表"""
        result = RerankResult(results=[], model="test")

        assert result.results == []
        assert len(result.results) == 0


class TestExpandedQuery:
    """测试 ExpandedQuery 数据类"""

    def test_create_expanded_query_lex(self):
        """测试创建 lex 类型的扩展查询"""
        query = ExpandedQuery(type="lex", text="keyword search terms")

        assert query.type == "lex"
        assert query.text == "keyword search terms"

    def test_create_expanded_query_vec(self):
        """测试创建 vec 类型的扩展查询"""
        query = ExpandedQuery(type="vec", text="semantic query")

        assert query.type == "vec"
        assert query.text == "semantic query"

    def test_create_expanded_query_hyde(self):
        """测试创建 hyde 类型的扩展查询"""
        query = ExpandedQuery(type="hyde", text="hypothetical answer")

        assert query.type == "hyde"
        assert query.text == "hypothetical answer"

    def test_expanded_query_frozen(self):
        """测试 ExpandedQuery 是不可变的"""
        query = ExpandedQuery(type="lex", text="test")

        with pytest.raises(AttributeError):
            query.type = "vec"

        with pytest.raises(AttributeError):
            query.text = "new text"

    def test_expanded_query_equality(self):
        """测试 ExpandedQuery 相等性"""
        query1 = ExpandedQuery(type="lex", text="test")
        query2 = ExpandedQuery(type="lex", text="test")
        query3 = ExpandedQuery(type="vec", text="test")

        assert query1 == query2
        assert query1 != query3


class TestRerankDocument:
    """测试 RerankDocument 数据类"""

    def test_create_rerank_document_without_title(self):
        """测试创建不带标题的 RerankDocument"""
        doc = RerankDocument(file="test.md", text="Content here")

        assert doc.file == "test.md"
        assert doc.text == "Content here"
        assert doc.title is None

    def test_create_rerank_document_with_title(self):
        """测试创建带标题的 RerankDocument"""
        doc = RerankDocument(file="test.md", text="Content", title="Test Title")

        assert doc.file == "test.md"
        assert doc.text == "Content"
        assert doc.title == "Test Title"

    def test_rerank_document_frozen(self):
        """测试 RerankDocument 是不可变的"""
        doc = RerankDocument(file="test.md", text="content")

        with pytest.raises(AttributeError):
            doc.file = "new.md"

        with pytest.raises(AttributeError):
            doc.text = "new content"

    def test_rerank_document_equality(self):
        """测试 RerankDocument 相等性"""
        doc1 = RerankDocument(file="test.md", text="content")
        doc2 = RerankDocument(file="test.md", text="content")
        doc3 = RerankDocument(file="test.md", text="different")

        assert doc1 == doc2
        assert doc1 != doc3


class TestTokenizerProtocol:
    """测试 Tokenizer Protocol"""

    def test_tokenizer_protocol_duck_typing(self):
        """测试 Tokenizer Protocol 鸭子类型"""

        class MockTokenizer:
            def tokenize(self, text: str) -> list[int]:
                return [1, 2, 3]

            def detokenize(self, tokens: list[int]) -> str:
                return "decoded"

        tokenizer = MockTokenizer()

        assert tokenizer.tokenize("test") == [1, 2, 3]
        assert tokenizer.detokenize([1, 2, 3]) == "decoded"

        assert hasattr(tokenizer, "tokenize")
        assert hasattr(tokenizer, "detokenize")
        assert callable(tokenizer.tokenize)
        assert callable(tokenizer.detokenize)


class TestLLMBackendAbstract:
    """测试 LLMBackend 抽象基类"""

    def test_cannot_instantiate_abstract_class(self):
        """测试不能直接实例化抽象类"""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            LLMBackend()

    def test_abstract_methods_required(self):
        """测试必须实现所有抽象方法"""

        class PartialBackend(LLMBackend):
            def embed(self, text, is_query=False, title=None):
                return None

            def embed_batch(self, texts, titles=None):
                return []

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            PartialBackend()

    def test_concrete_implementation_works(self):
        """测试完整实现可以正常实例化"""

        class ConcreteBackend(LLMBackend):
            def embed(self, text, is_query=False, title=None):
                return EmbeddingResult(embedding=[0.1, 0.2], model="test")

            def embed_batch(self, texts, titles=None):
                return [
                    EmbeddingResult(embedding=[0.1, 0.2], model="test")
                    for _ in texts
                ]

            def rerank(self, query, documents, top_n=None):
                return RerankResult(results=[], model="test")

            def expand_query(self, query, context=None):
                return [ExpandedQuery(type="lex", text=query)]

            def get_embedding_dimensions(self):
                return 768

            def close(self):
                pass

        backend = ConcreteBackend()
        assert backend is not None
        assert isinstance(backend, LLMBackend)

        result = backend.embed("test")
        assert result is not None
        assert result.model == "test"

        batch_result = backend.embed_batch(["test1", "test2"])
        assert len(batch_result) == 2

        rerank_result = backend.rerank("query", [])
        assert rerank_result.model == "test"

        expanded = backend.expand_query("test query")
        assert len(expanded) == 1
        assert expanded[0].type == "lex"

        dims = backend.get_embedding_dimensions()
        assert dims == 768

        backend.close()
