"""Qwen3-Reranker-0.6B 封装（via transformers HF checkpoint）。

- 类级单例：共享模型避免 GPU OOM（同 Embedder 策略）。
- 懒加载：首次 score 时下载（~1.2GB）。
- GPU 优先 fp16；CPU fp32。
- 线程安全：加载用 class-level 锁保护。
"""
from __future__ import annotations

import threading
from typing import Any, ClassVar

from loguru import logger


# Qwen3-Reranker prompt 模板（基于模型卡）
_PROMPT_TEMPLATE = (
    '<|im_start|>system\n'
    'Judge whether the Document meets the requirements based on the Query and '
    'the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n'
    '<|im_start|>user\n'
    '<Instruct>: Given a web search query, retrieve relevant passages that answer the query\n'
    '<Query>: {query}\n'
    '<Document>: {doc}<|im_end|>\n'
    '<|im_start|>assistant\n'
    '<think>\n\n</think>\n\n'
)


class Reranker:
    MODEL_NAME: str = "Qwen/Qwen3-Reranker-0.6B"

    _shared_model: ClassVar[Any] = None
    _shared_tokenizer: ClassVar[Any] = None
    _shared_lock: ClassVar[threading.Lock] = threading.Lock()

    def _load(self) -> tuple[Any, Any]:
        """加载 tokenizer + CausalLM。子类或测试可 patch 本方法。"""
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        logger.info("正在加载 reranker 模型: {}", self.MODEL_NAME)
        tokenizer = AutoTokenizer.from_pretrained(self.MODEL_NAME, padding_side="left")
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        model = AutoModelForCausalLM.from_pretrained(self.MODEL_NAME, torch_dtype=dtype)
        if torch.cuda.is_available():
            model = model.cuda()
        model.eval()
        return model, tokenizer

    def _ensure(self) -> tuple[Any, Any]:
        """返回共享 (model, tokenizer)，必要时触发首次加载。"""
        if Reranker._shared_model is None:
            with Reranker._shared_lock:
                if Reranker._shared_model is None:
                    model, tok = self._load()
                    Reranker._shared_model = model
                    Reranker._shared_tokenizer = tok
        return Reranker._shared_model, Reranker._shared_tokenizer

    def score(self, query: str, docs: list[str]) -> list[float]:
        """返回每个 doc 对 query 的 P(yes) 分数，范围 [0, 1]。空 list 不触发加载。"""
        if not docs:
            return []
        import torch

        model, tokenizer = self._ensure()

        prompts = [_PROMPT_TEMPLATE.format(query=query, doc=d) for d in docs]
        encoded = tokenizer(
            prompts,
            padding=True,
            truncation=True,
            max_length=2048,
            return_tensors="pt",
        )
        input_ids = encoded["input_ids"].to(model.device)
        attention_mask = encoded["attention_mask"].to(model.device)

        yes_id = tokenizer.convert_tokens_to_ids("yes")
        no_id = tokenizer.convert_tokens_to_ids("no")

        with torch.inference_mode():
            out = model(input_ids=input_ids, attention_mask=attention_mask)
        # 每行最后一个 token 的 logits
        last_logits = out.logits[:, -1, :]
        yes_logits = last_logits[:, yes_id]
        no_logits = last_logits[:, no_id]
        probs = torch.softmax(torch.stack([yes_logits, no_logits], dim=-1), dim=-1)
        return probs[:, 0].tolist()
