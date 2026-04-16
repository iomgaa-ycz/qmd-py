"""契约测试：FakeQmdClient 自身正确性（仅 Fake 后端）。

直接实例化 FakeQmdClient（connect() 返回 SqliteQmdClient）。
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


def test_fake_rerank_fills_stable_score():
    """FakeCollection.hybrid_search(rerank=True) → rerank_score ∈ [0,1], 稳定 + 排序影响。"""
    from qmd.testing.fakes import FakeQmdClient

    client = FakeQmdClient()
    col = client.collection("c")
    col.add_document("d1", "alpha beta gamma", {})
    col.add_document("d2", "delta epsilon zeta", {})
    col.add_document("d3", "eta theta iota", {})

    # rerank=False: rerank_score 全为 None
    r_off = col.hybrid_search("alpha", top_k=3, rerank=False)
    assert all(r.rerank_score is None for r in r_off)

    # rerank=True: rerank_score 全非 None 且 ∈ [0,1]
    r_on_1 = col.hybrid_search("alpha", top_k=3, rerank=True)
    assert all(r.rerank_score is not None for r in r_on_1)
    assert all(0.0 <= r.rerank_score <= 1.0 for r in r_on_1)

    # 稳定性：同 query 再跑一次，分数相同
    r_on_2 = col.hybrid_search("alpha", top_k=3, rerank=True)
    scores1 = {(r.chunk_ref.document_id, r.chunk_ref.chunk_index): r.rerank_score for r in r_on_1}
    scores2 = {(r.chunk_ref.document_id, r.chunk_ref.chunk_index): r.rerank_score for r in r_on_2}
    assert scores1 == scores2

    # 排序单调：rerank_score 降序
    scores_in_order = [r.rerank_score for r in r_on_1]
    assert scores_in_order == sorted(scores_in_order, reverse=True)
    client.close()
    client.close()
