"""契约测试 T0.1：公开 API 表面冻结为 6 个名字。"""
from __future__ import annotations

import pytest


def test_public_api_surface():
    """from qmd import * 只得到 6 个名字 + __version__。"""
    import qmd
    expected = {"ChunkRef", "SearchResult", "CollectionInfo",
                "Collection", "QmdClient", "connect"}
    assert set(qmd.__all__) == expected


def test_version_attribute():
    import qmd
    assert hasattr(qmd, "__version__")
    assert isinstance(qmd.__version__, str)


@pytest.mark.parametrize("symbol", [
    "create_store", "create_llm_backend", "Store", "Database",
    "NamedCollection", "LLMBackend", "BackendType", "search",
    "load_config", "init_schema", "open_database",
])
def test_legacy_symbols_not_exported(symbol: str):
    """旧符号在 qmd 顶层不可见。"""
    import qmd
    assert not hasattr(qmd, symbol), f"旧符号 {symbol} 不应出现在 qmd 顶层"
