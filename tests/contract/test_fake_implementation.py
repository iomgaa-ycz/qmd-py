"""契约测试：FakeQmdClient 自身正确性（仅 Fake 后端）。

M1 起这些测试直接实例化 FakeQmdClient，不再通过 qmd.connect()——
因为 connect() 在 M1 已切换为返回 SqliteQmdClient。
跨后端的不变量测试见 test_invariants.py（参数化 fake + sqlite）。
"""
from __future__ import annotations

from qmd import QmdClient
from qmd.models import SearchResult
from qmd.testing.fakes import FakeQmdClient


def test_add_search_recall():
    """add_document 后 hybrid_search 能召回。"""
    client = FakeQmdClient()
    col = client.collection("rules")
    col.add_document("doc1", "Hello world.\n\nThis is a test document.", {})
    results = col.hybrid_search("hello", top_k=3)
    assert len(results) >= 1
    assert all(isinstance(r, SearchResult) for r in results)
    assert "hello" in results[0].text.lower()
    client.close()


def test_embedding_dim_is_1024():
    """Fake 复用 Qwen3-Embedding-0.6B 单例，输出维度 1024。"""
    client = FakeQmdClient()
    col = client.collection("c")
    col.add_document("d", "some text here.\n\nmore text.", {})
    info = col.info()
    assert info.embedding_dim == 1024
    assert info.document_count == 1
    assert info.chunk_count == 2  # 按 \n\n 切成 2 段
    client.close()


def test_multiple_collections_independent():
    """不同 collection 的数据严格隔离。"""
    client = FakeQmdClient()
    client.collection("a").add_document("d1", "apple pie recipe", {})
    client.collection("b").add_document("d1", "banana smoothie recipe", {})
    results_a = client.collection("a").hybrid_search("apple")
    results_b = client.collection("b").hybrid_search("apple")
    assert any("apple" in r.text.lower() for r in results_a)
    # b 里没 apple，即使有结果也不应是 apple 文本
    assert not any("apple" in r.text.lower() for r in results_b)
    client.close()


def test_get_list_delete_document():
    client = FakeQmdClient()
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
    client = FakeQmdClient()
    assert isinstance(client, QmdClient)
    client.close()


def test_guide_excerpt_indexing_and_search(guide_excerpt_markdown):
    """用真实 fixture 跑一遍 add + search（Fake 后端）。"""
    client = FakeQmdClient()
    col = client.collection("guide")
    col.add_document("guide", guide_excerpt_markdown, {"source": "fixture"})
    results = col.hybrid_search("向量检索", top_k=3)
    assert len(results) >= 1
    # char 索引应精确定位（闭区间，取 [start:end+1]）
    for r in results:
        extracted = guide_excerpt_markdown[r.chunk_ref.char_start : r.chunk_ref.char_end + 1]
        assert extracted == r.text
    client.close()
