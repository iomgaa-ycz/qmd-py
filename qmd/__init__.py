"""qmd — Markdown 混合检索引擎。

对外只暴露 6 个名字：
    ChunkRef, SearchResult, CollectionInfo  —— pydantic 数据模型
    Collection, QmdClient                    —— Protocol
    connect                                  —— 工厂函数

内部实现位于 qmd.core 和 qmd.testing（Fake）。
下游代码请勿直接 import qmd.core.*。
"""
from __future__ import annotations

from qmd.models import (
    ChunkRef,
    Collection,
    CollectionInfo,
    QmdClient,
    SearchResult,
    connect,
)

__all__ = [
    "ChunkRef",
    "SearchResult",
    "CollectionInfo",
    "Collection",
    "QmdClient",
    "connect",
]

__version__ = "0.1.2"
