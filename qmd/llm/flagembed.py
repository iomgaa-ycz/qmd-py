"""
FlagEmbedding MVP reranker 后端

使用 FlagEmbedding 的 FlagReranker 实现文档重排序。
这是 MVP 阶段的 reranker 后端，专注于 reranking 功能。

特性：
- 使用 FlagReranker（默认 BAAI/bge-reranker-v2-m3）
- 只提供 rerank 功能
- embed/embed_batch 不支持（抛出 NotImplementedError）
"""

from typing import Any

from FlagEmbedding import FlagReranker
from loguru import logger

from qmd.llm.base import (
    EmbeddingResult,
    ExpandedQuery,
    LLMBackend,
    RerankDocument,
    RerankDocumentResult,
    RerankResult,
)


class FlagEmbeddingBackend(LLMBackend):
    """
    FlagEmbedding 后端实现

    MVP 阶段的 reranker 后端，专门用于文档重排序。
    不提供 embedding 功能，只提供 rerank。
    """

    def __init__(
        self,
        reranker_model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str | None = None,
    ):
        """
        初始化 FlagEmbedding 后端

        Args:
            reranker_model_name: FlagReranker 模型名称（默认 BAAI/bge-reranker-v2-m3）
            device: 设备类型（"cuda", "mps", "cpu" 或 None 自动检测）
        """
        self.reranker_model_name = reranker_model_name
        self.device = device or self._auto_detect_device()

        # 模型实例（懒加载）
        self._reranker: FlagReranker | None = None

        logger.info(
            f"初始化 FlagEmbeddingBackend: model={reranker_model_name}, device={self.device}"
        )

    def _auto_detect_device(self) -> str:
        """
        自动检测可用的设备

        优先级：CUDA > CPU（FlagReranker 不支持 MPS）

        Returns:
            设备类型字符串
        """
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass

        return "cpu"

    def _get_reranker(self) -> FlagReranker:
        """
        获取 reranker 实例（懒加载）

        Returns:
            FlagReranker 实例
        """
        if self._reranker is None:
            logger.info(f"加载 reranker 模型: {self.reranker_model_name}")

            # FlagReranker 使用 use_fp16 而非 device 参数
            use_fp16 = self.device == "cuda"

            self._reranker = FlagReranker(
                self.reranker_model_name,
                use_fp16=use_fp16,
            )

            logger.info(f"Reranker 模型加载完成: {self.reranker_model_name}")

        return self._reranker

    def embed(
        self, text: str, is_query: bool = False, title: str | None = None
    ) -> EmbeddingResult | None:
        """
        生成文本的向量表示

        此后端不支持 embedding，抛出 NotImplementedError。

        Args:
            text: 输入文本
            is_query: 是否为查询文本
            title: 可选的文档标题

        Raises:
            NotImplementedError: 此后端不支持 embedding
        """
        raise NotImplementedError(
            "FlagEmbeddingBackend 不支持 embedding，请使用 SentenceTransformerBackend 或 LlamaCppBackend"
        )

    def embed_batch(
        self, texts: list[str], titles: list[str | None] | None = None
    ) -> list[EmbeddingResult | None]:
        """
        批量生成文本的向量表示

        此后端不支持 embedding，抛出 NotImplementedError。

        Args:
            texts: 输入文本列表
            titles: 可选的标题列表

        Raises:
            NotImplementedError: 此后端不支持 embedding
        """
        raise NotImplementedError(
            "FlagEmbeddingBackend 不支持 embedding，请使用 SentenceTransformerBackend 或 LlamaCppBackend"
        )

    def rerank(
        self, query: str, documents: list[RerankDocument], top_n: int | None = None
    ) -> RerankResult:
        """
        根据查询重排序文档列表

        使用 FlagReranker 计算查询和文档之间的相关性分数。

        Args:
            query: 查询文本
            documents: 待重排序的文档列表
            top_n: 可选的返回结果数量限制

        Returns:
            重排序结果（按相关性降序）
        """
        try:
            reranker = self._get_reranker()

            # 准备输入：[[query, doc1], [query, doc2], ...]
            pairs = [[query, doc.text] for doc in documents]

            # 调用 FlagReranker.compute_score() 获取分数
            scores = reranker.compute_score(pairs)

            # 处理单个结果的情况（compute_score 返回 float 而非 list）
            if not isinstance(scores, list):
                scores = [scores]

            # 构造结果列表（带索引）
            results_with_scores = [
                RerankDocumentResult(file=doc.file, score=float(score), index=i)
                for i, (doc, score) in enumerate(zip(documents, scores))
            ]

            # 按分数降序排序
            results_with_scores.sort(key=lambda x: x.score, reverse=True)

            # 限制返回数量
            if top_n is not None and top_n > 0:
                results_with_scores = results_with_scores[:top_n]

            return RerankResult(
                results=results_with_scores, model=self.reranker_model_name
            )

        except Exception as e:
            logger.error(f"Rerank 失败: {e}")
            # 返回空结果
            return RerankResult(results=[], model=self.reranker_model_name)

    def expand_query(
        self, query: str, context: str | None = None
    ) -> list[ExpandedQuery]:
        """
        扩展查询为多个变体

        由于 FlagReranker 没有文本生成能力，这里返回简单的 fallback。

        Args:
            query: 原始查询
            context: 可选的上下文信息（当前未使用）

        Returns:
            扩展查询列表（简化版）
        """
        # FlagReranker 没有生成能力，返回简单的 fallback
        logger.debug(f"Query expansion (fallback): {query}")

        return [
            ExpandedQuery(type="lex", text=query),
            ExpandedQuery(type="vec", text=query),
        ]

    def get_embedding_dimensions(self) -> int:
        """
        获取 Embedding 向量的维度

        此后端不提供 embedding，返回 0。

        Returns:
            0（不适用）
        """
        return 0

    def close(self) -> None:
        """
        释放资源（关闭模型、释放显存等）
        """
        logger.info("关闭 FlagEmbeddingBackend")

        # 删除模型实例
        if self._reranker is not None:
            # 尝试清空 CUDA 缓存
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

            self._reranker = None

        logger.info("FlagEmbeddingBackend 关闭完成")
