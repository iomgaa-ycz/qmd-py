"""Qwen3-Embedding-0.6B 封装（via sentence-transformers）。

- 懒加载：首次 embed 调用时下载/加载模型（~1.2GB，冷启动 5-15s）。
- **类级单例**：所有 Embedder 实例共享同一份 GPU 上的模型，避免多个 SqliteQmdClient
  并存时 GPU OOM（Qwen3-0.6B 约占 ~1.5GB 显存）。
- **实例级 batch_size**：不同实例可有不同 batch_size（auto 模式根据 GPU/CPU 决定）。
- 线程安全：加载用 class-level 锁保护；encode 本身在 sentence-transformers 内部已线程安全。
"""
from __future__ import annotations

import threading
from typing import Any, ClassVar, Literal

import torch
from loguru import logger


def _auto_batch_size() -> int:
    """GPU → 64；CPU → 16（避免 CPU OOM）。"""
    return 64 if torch.cuda.is_available() else 16


class Embedder:
    DIM: int = 1024
    MODEL_NAME: str = "Qwen/Qwen3-Embedding-0.6B"

    # 类级单例：首次加载后整个进程共享
    _shared_model: ClassVar[Any] = None
    _shared_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, batch_size: int | Literal["auto"] = "auto") -> None:
        """:param batch_size: int 或 'auto'（auto → GPU=64/CPU=16）。构造后只读。"""
        self._batch_size: int = _auto_batch_size() if batch_size == "auto" else batch_size

    @property
    def batch_size(self) -> int:
        """只读：构造后不可变，防止跨 Collection 共享的 Embedder 被意外修改。"""
        return self._batch_size

    def _load_model(self) -> Any:
        """加载模型。子类或测试可 patch 本方法以注入替身。"""
        from sentence_transformers import SentenceTransformer
        logger.info("正在加载 embedding 模型: {}", self.MODEL_NAME)
        return SentenceTransformer(self.MODEL_NAME)

    def _ensure_model(self) -> Any:
        """返回共享模型，必要时触发首次加载。"""
        if Embedder._shared_model is None:
            with Embedder._shared_lock:
                if Embedder._shared_model is None:
                    Embedder._shared_model = self._load_model()
        return Embedder._shared_model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量 embed，使用 self.batch_size。空 list 不触发加载。"""
        if not texts:
            return []
        model = self._ensure_model()
        vectors = model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(x) for x in vec] for vec in vectors]
