"""契约测试：expansion 真模型生成查询变体 + 集成到 hybrid_search。

默认 skip（需下载 ~1.2GB 模型）；`pytest -m expander` 触发。
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.expander


def test_expansion_generates_variants():
    """真模型生成的变体包含有效内容。"""
    from qmd.core.expansion import QueryExpander

    expander = QueryExpander()
    result = expander.expand("Python 编程语言")
    total = len(result.get("lex", [])) + len(result.get("vec", [])) + len(result.get("hyde", []))
    assert total >= 1, f"expansion 未产出任何变体: {result}"


def test_expansion_integrated_search(tmp_path):
    """expansion.enabled=True 时 hybrid_search 能正常返回结果。"""
    from qmd import connect

    client = connect(
        tmp_path / "db.sqlite",
        config_overrides={"expansion": {"enabled": True}},
    )
    col = client.collection("c")
    col.add_document("d1", "Python 是一门高级编程语言，常用于人工智能和数据分析。", {})
    col.add_document("d2", "Java 是一门面向对象的编程语言。", {})
    col.add_document("d3", "橙子是一种柑橘类水果。", {})

    results = col.hybrid_search("编程语言", top_k=3)
    assert len(results) >= 1
    doc_ids = [r.chunk_ref.document_id for r in results]
    assert "d1" in doc_ids or "d2" in doc_ids
    client.close()
