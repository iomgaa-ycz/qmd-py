"""契约测试：Collection.add_documents 批量入库。参数化 [fake, sqlite]。"""
from __future__ import annotations

import pytest


def test_batch_add_basic(qmd_client):
    col = qmd_client.collection("c")
    col.add_documents([
        {"document_id": "d1", "markdown": "alpha beta.", "metadata": {}},
        {"document_id": "d2", "markdown": "gamma delta.", "metadata": {"t": "x"}},
        {"document_id": "d3", "markdown": "epsilon zeta.", "metadata": {}},
    ])
    assert set(col.list_documents()) == {"d1", "d2", "d3"}
    assert col.get_document("d2")["metadata"] == {"t": "x"}


def test_batch_upsert(qmd_client):
    """批量内包含已存在 id → 覆盖；批内同 id 以最后一个为准。"""
    col = qmd_client.collection("c")
    col.add_document("d1", "OLD content", {"v": 1})
    col.add_documents([
        {"document_id": "d1", "markdown": "first", "metadata": {"v": 2}},
        {"document_id": "d1", "markdown": "NEW content", "metadata": {"v": 3}},
        {"document_id": "d2", "markdown": "other", "metadata": {}},
    ])
    doc = col.get_document("d1")
    assert doc["markdown"] == "NEW content"
    assert doc["metadata"] == {"v": 3}


def test_batch_atomic_rollback(qmd_client):
    """第 3 个 doc 缺 markdown → 整批抛错，前 2 个也不应入库。"""
    col = qmd_client.collection("c")
    with pytest.raises(ValueError):
        col.add_documents([
            {"document_id": "d1", "markdown": "ok", "metadata": {}},
            {"document_id": "d2", "markdown": "ok2", "metadata": {}},
            {"document_id": "d3", "metadata": {}},  # 缺 markdown
        ])
    assert col.list_documents() == []


def test_batch_empty_noop(qmd_client):
    col = qmd_client.collection("c")
    col.add_documents([])
    assert col.list_documents() == []


def test_batch_wrong_type_raises(qmd_client):
    """字段类型错 → ValueError。"""
    col = qmd_client.collection("c")
    with pytest.raises(ValueError):
        col.add_documents([
            {"document_id": 123, "markdown": "ok", "metadata": {}},  # id 非 str
        ])
    assert col.list_documents() == []
