"""Qwen3-Embedding-0.6B 封装（via sentence-transformers）。

- 懒加载：首次 embed 调用时下载/加载模型（~1.2GB，冷启动 5-15s）。
- 批量 encode：默认 batch_size=32。
- 线程安全：_load_model 用锁保护，encode 本身在 ST 内部已线程安全。
"""
from __future__ import annotations

import threading
from typing import Any

from loguru import logger


class Embedder:
    DIM: int = 1024
    MODEL_NAME: str = "Qwen/Qwen3-Embedding-0.6B"

    def __init__(self) -> None:
        self._model: Any = None
        self._lock = threading.Lock()

    def _load_model(self) -> Any:
        """首次加载模型。子类或测试可 patch。"""
        from sentence_transformers import SentenceTransformer
        logger.info("正在加载 embedding 模型: {}", self.MODEL_NAME)
        return SentenceTransformer(self.MODEL_NAME)

    def _ensure_model(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = self._load_model()
        return self._model

    def embed(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """批量 embed。空 list 直接返回空 list（不触发加载）。"""
        if not texts:
            return []
        model = self._ensure_model()
        vectors = model.encode(texts, batch_size=batch_size, convert_to_numpy=True, show_progress_bar=False)
        return [[float(x) for x in vec] for vec in vectors]
