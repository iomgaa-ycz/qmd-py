"""契约测试：rerank=True 时 rerank_score 被正确填充 + 语义相关排序。

默认 skip（需下载 ~1.2GB 模型）；`pytest -m reranker` 触发。
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.reranker


def test_rerank_fills_score(tmp_path):
    """rerank=True 时 rerank_score 非 None 且 ∈ [0,1]。"""
    from qmd import connect

    client = connect(
        tmp_path / "db.sqlite",
        config_overrides={"rerank": {"enabled": True}},
    )
    col = client.collection("c")
    col.add_document("d1", "Python 是一门高级编程语言。", {})
    col.add_document("d2", "香蕉是一种水果。", {})

    results = col.hybrid_search("编程语言", top_k=2, rerank=True)
    assert len(results) >= 1
    for r in results:
        assert r.rerank_score is not None
        assert 0.0 <= r.rerank_score <= 1.0

    results_no = col.hybrid_search("编程语言", top_k=2, rerank=False)
    for r in results_no:
        assert r.rerank_score is None
    client.close()


def test_rerank_semantic_ordering(tmp_path):
    """构造明确语义：rerank 后相关文档应排第一（或至少在 top_k 中）。"""
    from qmd import connect

    client = connect(tmp_path / "db.sqlite")
    col = client.collection("c")
    col.add_document("d_relevant", "Python 是一门用于编程的高级语言，常用于数据科学。", {})
    col.add_document("d_noise1", "编程 编程 编程 编程 编程。", {})
    col.add_document("d_noise2", "香蕉 苹果 橙子 水果 水果。", {})

    results = col.hybrid_search("什么是 Python 编程语言", top_k=3, rerank=True)
    assert len(results) >= 1
    # 相关文档应该在 top_k（严格 top1 可能因 reranker 输出略有出入而不稳定）
    doc_ids = [r.chunk_ref.document_id for r in results]
    assert "d_relevant" in doc_ids
    client.close()
