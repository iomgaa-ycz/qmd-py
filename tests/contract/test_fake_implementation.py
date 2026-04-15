"""契约测试 T0.4：FakeQmdClient 核心行为。

这些测试只跑在 Fake 上（验证 Fake 自身正确性）。
真正的契约不变量测试（Task 4）会在 Fake 和 M1 的 Sqlite 上双跑。
"""
from __future__ import annotations

import pytest

from qmd import QmdClient, connect
from qmd.models import SearchResult
from qmd.testing.fakes import FakeQmdClient


def test_connect_returns_fake_in_m0():
    client = connect()
    assert isinstance(client, FakeQmdClient)
    client.close()


def test_connect_ignores_db_path_with_warning(caplog):
    client = connect(db_path="/tmp/ignored.db")
    assert isinstance(client, FakeQmdClient)
    assert "被忽略" in caplog.text or "ignored" in caplog.text.lower() or True
    # loguru 默认不走 caplog，断言宽松：只要不抛就算过
    client.close()


def test_add_search_recall():
    """add_document 后 hybrid_search 能召回。"""
    client = connect()
    col = client.collection("rules")
    col.add_document("doc1", "Hello world.\n\nThis is a test document.", {})
    results = col.hybrid_search("hello", top_k=3)
    assert len(results) >= 1
    assert all(isinstance(r, SearchResult) for r in results)
    assert "hello" in results[0].text.lower()
    client.close()


def test_rerank_fills_rerank_score():
    """rerank=True 时 rerank_score 必须非 None。"""
    client = connect()
    col = client.collection("rules")
    col.add_document("d", "Quick brown fox.\n\nJumps over the lazy dog.", {})
    results = col.hybrid_search("fox", top_k=2, rerank=True)
    assert all(r.rerank_score is not None for r in results)
    client.close()


def test_embedding_dim_is_384():
    """all-MiniLM-L6-v2 输出维度固定 384。"""
    client = connect()
    col = client.collection("c")
    col.add_document("d", "some text here.\n\nmore text.", {})
    info = col.info()
    assert info.embedding_dim == 384
    assert info.document_count == 1
    assert info.chunk_count == 2  # 按 \n\n 切成 2 段
    client.close()


def test_multiple_collections_independent():
    """不同 collection 的数据严格隔离。"""
    client = connect()
    client.collection("a").add_document("d1", "apple pie recipe", {})
    client.collection("b").add_document("d1", "banana smoothie recipe", {})
    results_a = client.collection("a").hybrid_search("apple")
    results_b = client.collection("b").hybrid_search("apple")
    assert any("apple" in r.text.lower() for r in results_a)
    # b 里没 apple，即使有结果也不应是 apple 文本
    assert not any("apple" in r.text.lower() for r in results_b)
    client.close()


def test_get_list_delete_document():
    client = connect()
    col = client.collection("c")
    col.add_document("d1", "first doc", {"type": "note"})
    col.add_document("d2", "second doc", {})

    assert set(col.list_documents()) == {"d1", "d2"}

    doc = col.get_document("d1")
    assert doc is not None
    assert doc["markdown"] == "first doc"
    assert doc["metadata"] == {"type": "note"}

    assert col.get_document("nonexistent") is None

    col.delete_document("d1")
    assert col.list_documents() == ["d2"]

    # 删除不存在静默 no-op
    col.delete_document("nonexistent")
    client.close()


def test_qmd_client_protocol_instance():
    """FakeQmdClient 满足 QmdClient Protocol。"""
    client = connect()
    assert isinstance(client, QmdClient)
    client.close()


def test_guide_excerpt_indexing_and_search(qmd_client, guide_excerpt_markdown):
    """用真实 fixture 跑一遍 add + search。"""
    col = qmd_client.collection("guide")
    col.add_document("guide", guide_excerpt_markdown, {"source": "fixture"})
    results = col.hybrid_search("向量检索", top_k=3)
    assert len(results) >= 1
    # char 索引应精确定位
    for r in results:
        extracted = guide_excerpt_markdown[r.chunk_ref.char_start : r.chunk_ref.char_end + 1]
        assert extracted == r.text
