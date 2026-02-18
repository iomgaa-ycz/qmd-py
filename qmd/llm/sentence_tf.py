"""
sentence-transformers MVP 嵌入后端

使用 sentence-transformers 实现快速验证的 Embedding 后端。
这是 MVP 阶段的实现，无需下载 GGUF 模型即可运行。

特性：
- 使用 HuggingFace 模型（默认 all-MiniLM-L6-v2，384 维）
- 支持批量嵌入
- 基于余弦相似度的 reranking
- 简化的 query expansion（无 LLM 生成能力）
"""

from typing import Any

import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

from qmd.llm.base import (
    EmbeddingResult,
    ExpandedQuery,
    LLMBackend,
    RerankDocument,
    RerankDocumentResult,
    RerankResult,
)


class SentenceTransformerBackend(LLMBackend):
    """
    sentence-transformers 后端实现

    MVP 阶段的快速验证后端，使用 HuggingFace 生态的模型。
    适合在没有 GGUF 模型时快速验证完整流程。
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: str | None = None,
    ):
        """
        初始化 sentence-transformers 后端

        Args:
            model_name: HuggingFace 模型名称（默认 all-MiniLM-L6-v2）
            device: 设备类型（"cuda", "mps", "cpu" 或 None 自动检测）
        """
        self.model_name = model_name
        self.device = device or self._auto_detect_device()

        # 模型实例（懒加载）
        self._model: SentenceTransformer | None = None

        logger.info(
            f"初始化 SentenceTransformerBackend: model={model_name}, device={self.device}"
        )

    def _auto_detect_device(self) -> str:
        """
        自动检测可用的设备

        优先级：CUDA > MPS > CPU

        Returns:
            设备类型字符串
        """
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass

        return "cpu"

    def _get_model(self) -> SentenceTransformer:
        """
        获取模型实例（懒加载）

        Returns:
            SentenceTransformer 实例
        """
        if self._model is None:
            logger.info(f"加载模型: {self.model_name}")
            self._model = SentenceTransformer(self.model_name, device=self.device)
            logger.info(
                f"模型加载完成: {self.model_name}, "
                f"维度={self._model.get_sentence_embedding_dimension()}"
            )

        return self._model

    def embed(
        self, text: str, is_query: bool = False, title: str | None = None
    ) -> EmbeddingResult | None:
        """
        生成文本的向量表示

        Args:
            text: 输入文本
            is_query: 是否为查询文本（当前未使用，为保持接口一致）
            title: 可选的文档标题（当前未使用，为保持接口一致）

        Returns:
            Embedding 结果，失败时返回 None
        """
        try:
            model = self._get_model()

            # 使用 model.encode() 生成向量
            embedding = model.encode(text, convert_to_numpy=True)

            # 转换为列表
            embedding_list = embedding.tolist()

            return EmbeddingResult(embedding=embedding_list, model=self.model_name)

        except Exception as e:
            logger.error(f"Embedding 失败: {e}")
            return None

    def embed_batch(
        self, texts: list[str], titles: list[str | None] | None = None
    ) -> list[EmbeddingResult | None]:
        """
        批量生成文本的向量表示

        使用 sentence-transformers 的批量处理能力，性能优于循环调用。

        Args:
            texts: 输入文本列表
            titles: 可选的标题列表（当前未使用，为保持接口一致）

        Returns:
            Embedding 结果列表，失败的项为 None
        """
        if not texts:
            return []

        try:
            model = self._get_model()

            # 批量编码
            embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

            # 转换为结果列表
            results: list[EmbeddingResult | None] = []
            for embedding in embeddings:
                embedding_list = embedding.tolist()
                results.append(
                    EmbeddingResult(embedding=embedding_list, model=self.model_name)
                )

            return results

        except Exception as e:
            logger.error(f"批量 Embedding 失败: {e}")
            # 返回全 None
            return [None] * len(texts)

    def rerank(
        self, query: str, documents: list[RerankDocument], top_n: int | None = None
    ) -> RerankResult:
        """
        根据查询重排序文档列表

        使用余弦相似度计算查询和文档之间的相关性。
        这是基于真实向量的实现（非 mock），但比 LLM reranker 简单。

        Args:
            query: 查询文本
            documents: 待重排序的文档列表
            top_n: 可选的返回结果数量限制

        Returns:
            重排序结果（按相关性降序）
        """
        try:
            model = self._get_model()

            # 生成查询向量
            query_embedding = model.encode(query, convert_to_numpy=True)

            # 生成文档向量
            doc_texts = [doc.text for doc in documents]
            doc_embeddings = model.encode(doc_texts, convert_to_numpy=True, show_progress_bar=False)

            # 计算余弦相似度
            # 使用 numpy 的向量化操作
            # cosine_similarity = dot(q, d) / (norm(q) * norm(d))
            query_norm = np.linalg.norm(query_embedding)
            doc_norms = np.linalg.norm(doc_embeddings, axis=1)

            # 点积
            dot_products = np.dot(doc_embeddings, query_embedding)

            # 余弦相似度
            cosine_similarities = dot_products / (query_norm * doc_norms)

            # 构造结果列表（带索引）
            results_with_scores = [
                RerankDocumentResult(file=doc.file, score=float(score), index=i)
                for i, (doc, score) in enumerate(zip(documents, cosine_similarities))
            ]

            # 按分数降序排序
            results_with_scores.sort(key=lambda x: x.score, reverse=True)

            # 限制返回数量
            if top_n is not None and top_n > 0:
                results_with_scores = results_with_scores[:top_n]

            return RerankResult(results=results_with_scores, model=self.model_name)

        except Exception as e:
            logger.error(f"Rerank 失败: {e}")
            # 返回空结果
            return RerankResult(results=[], model=self.model_name)

    def expand_query(
        self, query: str, context: str | None = None
    ) -> list[ExpandedQuery]:
        """
        扩展查询为多个变体

        由于 sentence-transformers 没有文本生成能力，这里返回简单的 fallback。

        Args:
            query: 原始查询
            context: 可选的上下文信息（当前未使用）

        Returns:
            扩展查询列表（简化版）
        """
        # sentence-transformers 没有生成能力，返回简单的 fallback
        logger.debug(f"Query expansion (fallback): {query}")

        return [
            ExpandedQuery(type="lex", text=query),
            ExpandedQuery(type="vec", text=query),
        ]

    def get_embedding_dimensions(self) -> int:
        """
        获取 Embedding 向量的维度

        Returns:
            向量维度
        """
        model = self._get_model()
        return model.get_sentence_embedding_dimension()

    def close(self) -> None:
        """
        释放资源（关闭模型、释放显存等）
        """
        logger.info("关闭 SentenceTransformerBackend")

        # 删除模型实例
        if self._model is not None:
            # 尝试清空 CUDA 缓存
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

            self._model = None

        logger.info("SentenceTransformerBackend 关闭完成")
