"""qmd.testing — 下游单测辅助。

暴露 FakeQmdClient / FakeCollection，供下游（如 Scrivai）在单测中使用，
避免加载真实 GGUF 或 SQLite。
"""
from __future__ import annotations

from qmd.testing.fakes import FakeCollection, FakeQmdClient

__all__ = ["FakeQmdClient", "FakeCollection"]
