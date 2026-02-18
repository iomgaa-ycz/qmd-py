"""
LLM 抽象接口定义

定义 Embedding、Reranking、Query Expansion 的统一接口和数据类型。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Protocol

from loguru import logger


# =============================================================================
# 数据类型定义
# =============================================================================


@dataclass(frozen=True)
class EmbeddingResult:
    """
    Embedding 结果

    Attributes:
        embedding: 向量表示（浮点数列表）
        model: 使用的模型标识
    """

    embedding: list[float]
    model: str


@dataclass(frozen=True)
class RerankDocumentResult:
    """
    单个文档的重排序结果

    Attributes:
        file: 文档文件路径
        score: 相关性分数（越高越相关）
        index: 原始文档列表中的索引位置
    """

    file: str
    score: float
    index: int


@dataclass(frozen=True)
class RerankResult:
    """
    批量重排序结果

    Attributes:
        results: 重排序后的文档列表（按分数降序）
        model: 使用的模型标识
    """

    results: list[RerankDocumentResult]
    model: str


@dataclass(frozen=True)
class ExpandedQuery:
    """
    查询扩展结果

    支持三种查询类型，分别对应不同的检索后端：
    - lex: 词法检索（BM25 全文检索）
    - vec: 向量检索（语义相似度）
    - hyde: 假设文档扩展（生成假设答案再检索）

    Attributes:
        type: 查询类型（lex/vec/hyde）
        text: 扩展后的查询文本
    """

    type: Literal["lex", "vec", "hyde"]
    text: str


@dataclass(frozen=True)
class RerankDocument:
    """
    待重排序的文档

    Attributes:
        file: 文档文件路径
        text: 文档内容（用于重排序）
        title: 可选的文档标题
    """

    file: str
    text: str
    title: str | None = None


# =============================================================================
# Tokenizer 协议
# =============================================================================


class Tokenizer(Protocol):
    """
    文本 Tokenizer 协议

    定义文本分词和反分词的接口。
    """

    def tokenize(self, text: str) -> list[int]:
        """
        将文本转换为 token ID 列表

        Args:
            text: 输入文本

        Returns:
            Token ID 列表
        """
        ...

    def detokenize(self, tokens: list[int]) -> str:
        """
        将 token ID 列表转换回文本

        Args:
            tokens: Token ID 列表

        Returns:
            解码后的文本
        """
        ...


# =============================================================================
# LLM 抽象基类
# =============================================================================


class LLMBackend(ABC):
    """
    LLM 后端抽象基类

    定义 Embedding、Reranking、Query Expansion 的统一接口。
    所有具体实现（llama-cpp、HuggingFace 等）必须继承此类。
    """

    @abstractmethod
    def embed(
        self, text: str, is_query: bool = False, title: str | None = None
    ) -> EmbeddingResult | None:
        """
        生成文本的向量表示

        Args:
            text: 输入文本
            is_query: 是否为查询文本（影响 prompt 格式）
            title: 可选的文档标题（用于文档 embedding）

        Returns:
            Embedding 结果，失败时返回 None
        """
        ...

    @abstractmethod
    def embed_batch(
        self, texts: list[str], titles: list[str | None] | None = None
    ) -> list[EmbeddingResult | None]:
        """
        批量生成文本的向量表示

        Args:
            texts: 输入文本列表
            titles: 可选的标题列表（与 texts 对应）

        Returns:
            Embedding 结果列表，失败的项为 None
        """
        ...

    @abstractmethod
    def rerank(
        self, query: str, documents: list[RerankDocument], top_n: int | None = None
    ) -> RerankResult:
        """
        根据查询重排序文档列表

        Args:
            query: 查询文本
            documents: 待重排序的文档列表
            top_n: 可选的返回结果数量限制

        Returns:
            重排序结果（按相关性降序）
        """
        ...

    @abstractmethod
    def expand_query(
        self, query: str, context: str | None = None
    ) -> list[ExpandedQuery]:
        """
        扩展查询为多个变体

        使用 LLM 生成查询的不同表述，用于混合检索：
        - lex: 改写为关键词（BM25 检索）
        - vec: 改写为语义查询（向量检索）
        - hyde: 生成假设文档（HyDE 检索）

        Args:
            query: 原始查询
            context: 可选的上下文信息

        Returns:
            扩展查询列表
        """
        ...

    @abstractmethod
    def get_embedding_dimensions(self) -> int:
        """
        获取 Embedding 向量的维度

        Returns:
            向量维度（例如 768、1024 等）
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """
        释放资源（关闭模型、释放显存等）

        应在不再使用 LLM 后端时调用。
        """
        ...
