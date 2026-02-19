"""
llama-cpp-python 后端实现

使用 llama-cpp-python 实现 Embedding、Reranking、Query Expansion。
与 qmd 原版保持一致，使用相同的 GGUF 模型和格式化方法。
"""

from typing import Any

from llama_cpp import Llama
from loguru import logger

from qmd.llm.base import (
    EmbeddingResult,
    ExpandedQuery,
    LLMBackend,
    RerankDocument,
    RerankDocumentResult,
    RerankResult,
)
from qmd.llm.models import ModelManager


# =============================================================================
# Embedding 格式化函数（与 qmd 原版一致）
# =============================================================================


def format_query_for_embedding(query: str) -> str:
    """
    格式化查询文本用于 embedding

    使用 nomic-style task prefix 格式（embeddinggemma 格式）

    Args:
        query: 查询文本

    Returns:
        格式化后的文本

    Examples:
        >>> format_query_for_embedding("authentication flow")
        'task: search result | query: authentication flow'
    """
    return f"task: search result | query: {query}"


def format_doc_for_embedding(text: str, title: str | None = None) -> str:
    """
    格式化文档文本用于 embedding

    使用 nomic-style 格式，包含 title 和 text 字段

    Args:
        text: 文档文本
        title: 可选的文档标题

    Returns:
        格式化后的文本

    Examples:
        >>> format_doc_for_embedding("Document content", "Title")
        'title: Title | text: Document content'
        >>> format_doc_for_embedding("Document content")
        'title: none | text: Document content'
    """
    return f"title: {title or 'none'} | text: {text}"


# =============================================================================
# LlamaCppBackend 实现
# =============================================================================


class LlamaCppBackend(LLMBackend):
    """
    llama-cpp-python 后端实现

    使用 GGUF 模型实现 Embedding、Reranking、Query Expansion。
    通过 ModelManager 管理模型的懒加载和 Idle Timeout。
    """

    def __init__(self, model_manager: ModelManager | None = None):
        """
        初始化 llama-cpp-python 后端

        Args:
            model_manager: 模型管理器（默认创建新实例）
        """
        self.model_manager = model_manager or ModelManager()

        # 模型实例（通过 ModelManager 懒加载）
        self._embed_model_instance: Llama | None = None
        self._rerank_model_instance: Llama | None = None
        self._generate_model_instance: Llama | None = None

    def _get_embed_model(self) -> Llama:
        """
        获取 Embedding 模型实例

        通过 ModelManager 懒加载模型，并缓存实例。

        Returns:
            Llama 模型实例

        Raises:
            FileNotFoundError: 如果模型文件不存在
        """
        if self._embed_model_instance is None:
            # 从 ModelManager 触发懒加载（但在 MVP 阶段返回 None）
            _ = self.model_manager.embed_model

            # 直接使用 llama-cpp-python 加载
            from pathlib import Path

            from qmd.llm.models import resolve_model_path

            model_path = resolve_model_path(
                self.model_manager.embed_model_uri, self.model_manager.cache_dir
            )

            # 检查模型文件是否存在
            if not model_path.exists():
                raise FileNotFoundError(
                    f"Embedding 模型文件不存在: {model_path}。"
                    f"请先下载模型到缓存目录。"
                )

            logger.info(f"加载 Embedding 模型: {model_path}")

            # 加载模型
            # embedding=True 表示用于 embedding
            # n_ctx=0 表示不需要 context（embedding 不需要）
            # n_gpu_layers=-1 表示全部加载到 GPU（如果可用）
            self._embed_model_instance = Llama(
                model_path=str(model_path),
                embedding=True,
                n_ctx=0,
                n_gpu_layers=-1 if self.model_manager.gpu_type != "cpu" else 0,
                verbose=False,
            )

        return self._embed_model_instance

    def _get_rerank_model(self) -> Llama:
        """
        获取 Rerank 模型实例

        通过 ModelManager 懒加载模型，并缓存实例。

        Returns:
            Llama 模型实例

        Raises:
            RuntimeError: 如果模型加载失败
        """
        if self._rerank_model_instance is None:
            from pathlib import Path

            from qmd.llm.models import resolve_model_path

            model_path = resolve_model_path(
                self.model_manager.rerank_model_uri, self.model_manager.cache_dir
            )

            # 检查模型文件是否存在
            if not model_path.exists():
                raise FileNotFoundError(
                    f"Rerank 模型文件不存在: {model_path}。请先下载模型到缓存目录。"
                )

            logger.info(f"加载 Rerank 模型: {model_path}")

            # Rerank 需要 context（用于生成 logits）
            # n_ctx=2048 参考 qmd 原版的 RERANK_CONTEXT_SIZE
            self._rerank_model_instance = Llama(
                model_path=str(model_path),
                n_ctx=2048,
                n_gpu_layers=-1 if self.model_manager.gpu_type != "cpu" else 0,
                verbose=False,
                logits_all=True,  # 启用 logits 输出
            )

        return self._rerank_model_instance

    def _get_generate_model(self) -> Llama:
        """
        获取 Generate 模型实例

        通过 ModelManager 懒加载模型，并缓存实例。

        Returns:
            Llama 模型实例

        Raises:
            RuntimeError: 如果模型加载失败
        """
        if self._generate_model_instance is None:
            from pathlib import Path

            from qmd.llm.models import resolve_model_path

            model_path = resolve_model_path(
                self.model_manager.generate_model_uri, self.model_manager.cache_dir
            )

            # 检查模型文件是否存在
            if not model_path.exists():
                raise FileNotFoundError(
                    f"Generate 模型文件不存在: {model_path}。"
                    f"请先下载模型到缓存目录。"
                )

            logger.info(f"加载 Generate 模型: {model_path}")

            # Generate 需要较大的 context
            self._generate_model_instance = Llama(
                model_path=str(model_path),
                n_ctx=2048,
                n_gpu_layers=-1 if self.model_manager.gpu_type != "cpu" else 0,
                verbose=False,
            )

        return self._generate_model_instance

    def embed(
        self, text: str, is_query: bool = False, title: str | None = None
    ) -> EmbeddingResult | None:
        """
        生成文本的向量表示

        Args:
            text: 输入文本
            is_query: 是否为查询文本（影响格式化）
            title: 可选的文档标题（用于文档 embedding）

        Returns:
            Embedding 结果，失败时返回 None
        """
        try:
            # 格式化文本（参考 qmd 原版）
            if is_query:
                formatted_text = format_query_for_embedding(text)
            else:
                formatted_text = format_doc_for_embedding(text, title)

            # 获取模型并生成 embedding
            model = self._get_embed_model()
            embedding = model.embed(formatted_text)

            return EmbeddingResult(
                embedding=embedding,  # llama-cpp-python 直接返回 list[float]
                model=self.model_manager.embed_model_uri,
            )

        except Exception as e:
            logger.error(f"Embedding 失败: {e}")
            return None

    def embed_batch(
        self, texts: list[str], titles: list[str | None] | None = None
    ) -> list[EmbeddingResult | None]:
        """
        批量生成文本的向量表示

        注意：llama-cpp-python 不支持真正的批处理，这里循环调用 embed()

        Args:
            texts: 输入文本列表
            titles: 可选的标题列表（与 texts 对应）

        Returns:
            Embedding 结果列表，失败的项为 None
        """
        if not texts:
            return []

        # 准备标题列表
        if titles is None:
            titles = [None] * len(texts)
        elif len(titles) != len(texts):
            raise ValueError(
                f"titles 长度 ({len(titles)}) 与 texts 长度 ({len(texts)}) 不匹配"
            )

        results: list[EmbeddingResult | None] = []

        for text, title in zip(texts, titles):
            # 文档 embedding（is_query=False）
            result = self.embed(text, is_query=False, title=title)
            results.append(result)

        return results

    def rerank(
        self, query: str, documents: list[RerankDocument], top_n: int | None = None
    ) -> RerankResult:
        """
        根据查询重排序文档列表

        使用 "yes"/"no" token logits 对比法计算相关性分数（参考 qmd 原版）

        Args:
            query: 查询文本
            documents: 待重排序的文档列表
            top_n: 可选的返回结果数量限制

        Returns:
            重排序结果（按相关性降序）
        """
        try:
            model = self._get_rerank_model()

            # 计算每个文档的相关性分数
            scores: list[float] = []

            for doc in documents:
                # 构造 rerank prompt（参考 Qwen3-Reranker 格式）
                # 格式：Query: {query}\nDocument: {text}\nRelevant:
                prompt = f"Query: {query}\nDocument: {doc.text}\nRelevant:"

                # 生成 logits（需要 logits_all=True）
                # max_tokens=1 因为我们只需要第一个 token 的 logits
                output = model(
                    prompt,
                    max_tokens=1,
                    logprobs=True,  # 启用 logprobs
                    temperature=0.0,  # 贪心解码
                )

                # 获取 logits
                # 在 llama-cpp-python 中，logprobs 包含在输出的 choices 中
                if not output or "choices" not in output or not output["choices"]:
                    logger.warning(f"Rerank 输出为空，文档: {doc.file}")
                    scores.append(0.0)
                    continue

                choice = output["choices"][0]

                # 获取 token 的 logprobs
                if "logprobs" not in choice or not choice["logprobs"]:
                    logger.warning(f"Rerank logprobs 为空，文档: {doc.file}")
                    scores.append(0.0)
                    continue

                logprobs_data = choice["logprobs"]

                # top_logprobs 包含所有 token 的 logprob
                if "top_logprobs" not in logprobs_data or not logprobs_data["top_logprobs"]:
                    logger.warning(f"Rerank top_logprobs 为空，文档: {doc.file}")
                    scores.append(0.0)
                    continue

                # 获取第一个位置的 top_logprobs（dict: token -> logprob）
                first_token_logprobs = logprobs_data["top_logprobs"][0]

                # 查找 "yes" 和 "no" 的 logprob
                # 注意：token 可能包含空格，如 " yes", " no"
                yes_logprob = None
                no_logprob = None

                for token, logprob in first_token_logprobs.items():
                    token_lower = token.strip().lower()
                    if token_lower == "yes":
                        yes_logprob = logprob
                    elif token_lower == "no":
                        no_logprob = logprob

                # 如果找不到 yes/no，使用默认分数
                if yes_logprob is None or no_logprob is None:
                    logger.warning(
                        f"Rerank 未找到 yes/no token，文档: {doc.file}，"
                        f"top_logprobs: {first_token_logprobs}"
                    )
                    scores.append(0.0)
                    continue

                # 计算相关性分数：yes_prob / (yes_prob + no_prob)
                # 使用 exp(logprob) 转换为概率
                import math

                yes_prob = math.exp(yes_logprob)
                no_prob = math.exp(no_logprob)
                score = yes_prob / (yes_prob + no_prob)

                scores.append(score)

            # 构造结果列表（带索引）
            results_with_scores = [
                RerankDocumentResult(file=doc.file, score=score, index=i)
                for i, (doc, score) in enumerate(zip(documents, scores))
            ]

            # 按分数降序排序
            results_with_scores.sort(key=lambda x: x.score, reverse=True)

            # 限制返回数量
            if top_n is not None and top_n > 0:
                results_with_scores = results_with_scores[:top_n]

            return RerankResult(
                results=results_with_scores, model=self.model_manager.rerank_model_uri
            )

        except Exception as e:
            logger.error(f"Rerank 失败: {e}")
            # 返回空结果
            return RerankResult(results=[], model=self.model_manager.rerank_model_uri)

    def expand_query(
        self, query: str, context: str | None = None
    ) -> list[ExpandedQuery]:
        """
        扩展查询为多个变体

        使用 LLM 生成 lex/vec/hyde 扩展查询（参考 qmd 原版）

        Args:
            query: 原始查询
            context: 可选的上下文信息（当前未使用）

        Returns:
            扩展查询列表
        """
        try:
            model = self._get_generate_model()

            # 构造 prompt（参考 qmd 原版）
            # 使用 /no_think 模式（Qwen3 的非思考模式）
            prompt = f"/no_think Expand this search query: {query}"

            # 生成扩展查询
            # 期望输出格式：
            # lex: keyword query
            # vec: semantic query
            # hyde: hypothetical document
            output = model(
                prompt,
                max_tokens=600,
                temperature=0.7,  # 参考 qmd 原版
                top_k=20,
                top_p=0.8,
                repeat_penalty=1.1,  # 防止重复
                stop=["\n\n"],  # 遇到空行停止
            )

            # 解析输出
            if not output or "choices" not in output or not output["choices"]:
                logger.warning("Query expansion 输出为空，返回原始查询")
                return self._fallback_queries(query)

            generated_text = output["choices"][0].get("text", "").strip()

            if not generated_text:
                logger.warning("Query expansion 生成为空，返回原始查询")
                return self._fallback_queries(query)

            # 解析每一行：type: text
            lines = generated_text.split("\n")
            expanded_queries: list[ExpandedQuery] = []

            query_lower = query.lower()
            query_terms = set(query_lower.replace(",", " ").replace(".", " ").split())

            for line in lines:
                line = line.strip()
                if not line or ":" not in line:
                    continue

                # 分离 type 和 text
                colon_idx = line.index(":")
                query_type = line[:colon_idx].strip().lower()
                query_text = line[colon_idx + 1 :].strip()

                # 验证 type
                if query_type not in ["lex", "vec", "hyde"]:
                    continue

                # 验证文本包含至少一个查询关键词（参考 qmd 原版的 hasQueryTerm）
                text_lower = query_text.lower()
                if not any(term in text_lower for term in query_terms):
                    logger.debug(
                        f"跳过扩展查询（不包含原始关键词）: {query_type}: {query_text}"
                    )
                    continue

                expanded_queries.append(
                    ExpandedQuery(
                        type=query_type,  # type: ignore
                        text=query_text,
                    )
                )

            # 如果没有有效的扩展查询，返回 fallback
            if not expanded_queries:
                logger.warning("Query expansion 未生成有效查询，返回 fallback")
                return self._fallback_queries(query)

            logger.info(f"Query expansion 成功，生成 {len(expanded_queries)} 个查询")
            return expanded_queries

        except Exception as e:
            logger.error(f"Query expansion 失败: {e}，返回原始查询")
            return self._fallback_queries(query)

    def _fallback_queries(self, query: str) -> list[ExpandedQuery]:
        """
        生成 fallback 查询（当 LLM 失败时）

        Args:
            query: 原始查询

        Returns:
            fallback 查询列表
        """
        return [
            ExpandedQuery(type="hyde", text=f"Information about {query}"),
            ExpandedQuery(type="lex", text=query),
            ExpandedQuery(type="vec", text=query),
        ]

    def get_embedding_dimensions(self) -> int:
        """
        获取 Embedding 向量的维度

        embeddinggemma-300M 的维度是 768

        Returns:
            向量维度
        """
        return 768

    def close(self) -> None:
        """
        释放资源（关闭模型、释放显存等）
        """
        logger.info("关闭 LlamaCppBackend")

        # 关闭所有模型实例
        # llama-cpp-python 的 Llama 对象会在 __del__ 时自动释放资源
        # 但我们显式设为 None 以触发 GC
        self._embed_model_instance = None
        self._rerank_model_instance = None
        self._generate_model_instance = None

        # 卸载 ModelManager 管理的模型
        self.model_manager.unload()

        logger.info("LlamaCppBackend 关闭完成")
