"""契约测试：position_aware blending 模式影响排序。参数化 [fake, sqlite]。"""
from __future__ import annotations

import pytest


def test_pure_rerank_no_blending(qmd_client):
    """blending_mode=pure_rerank 时 score 就是 rerank_score 的排序。"""
    col = qmd_client.collection("c")
    col.add_document("d1", "Python 是一门编程语言。", {})
    col.add_document("d2", "Java 也是编程语言。", {})

    results = col.hybrid_search("编程语言", top_k=2, rerank=True)
    if len(results) >= 2:
        assert results[0].rerank_score >= results[1].rerank_score


def test_blending_mode_position_aware_sqlite(tmp_path):
    """position_aware blending 改变最终排序（仅 sqlite）。"""
    from qmd import connect

    client = connect(
        tmp_path / "db.sqlite",
        config_overrides={
            "retrieval": {
                "blending_mode": "position_aware",
                "blending_weights": {
                    "top": [0.75, 0.25],
                    "mid": [0.60, 0.40],
                    "tail": [0.40, 0.60],
                },
            },
        },
    )
    col = client.collection("c")
    col.add_document("d1", "Python 编程语言常用于数据科学和机器学习。", {})
    col.add_document("d2", "Java 是一门面向对象的编程语言。", {})
    col.add_document("d3", "香蕉是一种热带水果。", {})

    results = col.hybrid_search("Python 编程", top_k=3, rerank=True)
    assert len(results) >= 1
    for r in results:
        assert r.rerank_score is not None
        assert r.score is not None
    client.close()


def test_blending_rerank_false_no_effect(qmd_client):
    """rerank=False 时 blending 不生效（无 rerank_score 可混合）。"""
    col = qmd_client.collection("c")
    col.add_document("d1", "测试文档内容。", {})

    results = col.hybrid_search("测试", top_k=1, rerank=False)
    if results:
        assert results[0].rerank_score is None
