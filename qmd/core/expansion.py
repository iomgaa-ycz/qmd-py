"""Qwen3-0.6B Query Expansion（类级单例 + 懒加载）。

生成 lex/vec/hyde 三种查询变体用于扩充检索。
解析失败降级为空变体，不阻塞检索流程。
"""
from __future__ import annotations

import json
import threading
from typing import Any, ClassVar

from loguru import logger


_EXPANSION_PROMPT = (
    'Given the search query: "{query}"\n'
    "Generate search query variants in JSON format:\n"
    '{{\n'
    '  "lex": ["synonym/keyword variant 1", "variant 2"],\n'
    '  "vec": ["semantic rephrase 1"],\n'
    '  "hyde": ["hypothetical document snippet"]\n'
    '}}\n'
    "Output ONLY the JSON, no explanation."
)

_EMPTY_RESULT: dict[str, list[str]] = {"lex": [], "vec": [], "hyde": []}


class QueryExpander:
    """Qwen3-0.6B query expansion — 类级单例，懒加载。"""

    MODEL_NAME: str = "Qwen/Qwen3-0.6B"

    _shared_model: ClassVar[Any] = None
    _shared_tokenizer: ClassVar[Any] = None
    _shared_lock: ClassVar[threading.Lock] = threading.Lock()

    def _load(self) -> tuple[Any, Any]:
        """加载 tokenizer + CausalLM。子类或测试可 patch 本方法。"""
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        logger.info("正在加载 expansion 模型: {}", self.MODEL_NAME)
        tokenizer = AutoTokenizer.from_pretrained(self.MODEL_NAME)
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        model = AutoModelForCausalLM.from_pretrained(self.MODEL_NAME, torch_dtype=dtype)
        if torch.cuda.is_available():
            model = model.cuda()
        model.eval()
        return model, tokenizer

    def _ensure(self) -> tuple[Any, Any]:
        """返回共享 (model, tokenizer)，必要时触发首次加载。"""
        if QueryExpander._shared_model is None:
            with QueryExpander._shared_lock:
                if QueryExpander._shared_model is None:
                    model, tok = self._load()
                    QueryExpander._shared_model = model
                    QueryExpander._shared_tokenizer = tok
        return QueryExpander._shared_model, QueryExpander._shared_tokenizer

    def expand(self, query: str) -> dict[str, list[str]]:
        """生成查询变体。返回 {"lex": [...], "vec": [...], "hyde": [...]}。

        空查询或解析失败返回空变体，不抛错。
        """
        if not query.strip():
            return dict(_EMPTY_RESULT)

        import torch

        model, tokenizer = self._ensure()
        prompt = _EXPANSION_PROMPT.format(query=query)

        inputs = tokenizer(prompt, return_tensors="pt")
        input_ids = inputs["input_ids"].to(model.device)

        with torch.inference_mode():
            output_ids = model.generate(
                input_ids,
                max_new_tokens=256,
                do_sample=False,
                temperature=1.0,
            )

        new_tokens = output_ids[0, input_ids.shape[1]:]
        raw_output = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

        return _parse_expansion_output(raw_output)


def _parse_expansion_output(raw: str) -> dict[str, list[str]]:
    """解析模型输出的 JSON。失败返回空变体。"""
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            logger.warning("expansion 输出无 JSON: {}", raw[:200])
            return dict(_EMPTY_RESULT)
        data = json.loads(raw[start:end])
        result: dict[str, list[str]] = {}
        for key in ("lex", "vec", "hyde"):
            val = data.get(key, [])
            if isinstance(val, list):
                result[key] = [str(v) for v in val if v]
            else:
                result[key] = []
        return result
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        logger.warning("expansion 输出解析失败: {} — raw: {}", e, raw[:200])
        return dict(_EMPTY_RESULT)
