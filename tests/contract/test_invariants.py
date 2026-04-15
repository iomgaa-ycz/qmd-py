"""契约不变量测试（对齐 design.md §3.1 的 7 条不变量）。

这些测试不依赖具体实现，只依赖 qmd_client fixture——
因此同一套测试可以跑在 Fake 和 Sqlite（M1）上。
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest


# ---------- 不变量 1：hybrid_search 结果按 score 严格降序 ----------

def test_search_results_strictly_descending(qmd_client):
    col = qmd_client.collection("c")
    for i in range(5):
        col.add_document(f"d{i}", f"document {i} about topic alpha and beta.\n\nmore content here.", {})
    results = col.hybrid_search("alpha", top_k=10)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


# ---------- 不变量 2：char_start/char_end 精确定位原始 markdown ----------

def test_chunk_ref_char_indices_match_original(qmd_client):
    markdown = "First paragraph about foxes.\n\nSecond paragraph about dogs.\n\nThird paragraph."
    col = qmd_client.collection("c")
    col.add_document("d", markdown, {})
    results = col.hybrid_search("foxes", top_k=3)
    for r in results:
        extracted = markdown[r.chunk_ref.char_start : r.chunk_ref.char_end + 1]
        assert extracted == r.text, (
            f"char 索引不匹配：期望 {r.text!r}，实际 {extracted!r}"
        )


# ---------- 不变量 3：metadata 透传不解释 ----------

def test_metadata_passthrough(qmd_client):
    col = qmd_client.collection("c")
    col.add_document("d", "content about foxes", {"arbitrary_key": 42, "nested": {"a": 1}})
    results = col.hybrid_search("foxes", top_k=1)
    assert len(results) == 1
    assert results[0].metadata == {"arbitrary_key": 42, "nested": {"a": 1}}


# ---------- 不变量 4：filters 仅支持精确相等 ----------

def test_filters_exact_match_only(qmd_client):
    col = qmd_client.collection("c")
    col.add_document("d1", "text about foxes", {"type": "law"})
    col.add_document("d2", "text about foxes too", {"type": "case"})

    results = col.hybrid_search("foxes", top_k=10, filters={"type": "law"})
    assert len(results) == 1
    assert results[0].chunk_ref.document_id == "d1"


def test_filters_no_match_returns_empty(qmd_client):
    col = qmd_client.collection("c")
    col.add_document("d1", "text about foxes", {"type": "law"})
    results = col.hybrid_search("foxes", top_k=10, filters={"type": "nonexistent"})
    assert results == []


# ---------- 不变量 5：collection 隔离 ----------

def test_collections_are_isolated(qmd_client):
    qmd_client.collection("a").add_document("d", "banana is yellow", {})
    qmd_client.collection("b").add_document("d", "apple is red", {})

    ra = qmd_client.collection("a").hybrid_search("banana", top_k=5)
    rb = qmd_client.collection("b").hybrid_search("banana", top_k=5)

    assert any("banana" in r.text for r in ra)
    assert not any("banana" in r.text for r in rb)


def test_delete_collection_isolation(qmd_client):
    qmd_client.collection("a").add_document("d", "content here", {})
    qmd_client.collection("b").add_document("d", "other content", {})
    qmd_client.delete_collection("a")
    names = [info.name for info in qmd_client.list_collections()]
    assert "a" not in names
    assert "b" in names


# ---------- 不变量 6：add_document 同 id 幂等 upsert ----------

def test_add_document_same_id_is_upsert(qmd_client):
    col = qmd_client.collection("c")
    col.add_document("d", "original content", {"v": 1})
    col.add_document("d", "updated content", {"v": 2})

    assert col.info().document_count == 1
    doc = col.get_document("d")
    assert doc is not None
    assert doc["markdown"] == "updated content"
    assert doc["metadata"] == {"v": 2}


def test_add_document_upsert_does_not_raise(qmd_client):
    col = qmd_client.collection("c")
    col.add_document("d", "content", {})
    # 重复 3 次不应抛
    for _ in range(3):
        col.add_document("d", "content", {})
    assert col.info().document_count == 1


# ---------- 不变量 7：Collection 方法线程安全 ----------

def test_concurrent_upsert_same_id_is_safe(qmd_client):
    col = qmd_client.collection("c")

    def worker(i: int) -> None:
        col.add_document("shared", f"content version {i}", {"v": i})

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(worker, range(100)))

    assert col.info().document_count == 1


def test_concurrent_add_different_ids(qmd_client):
    col = qmd_client.collection("c")

    def worker(i: int) -> None:
        col.add_document(f"d{i}", f"content {i}", {})

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(worker, range(50)))

    assert col.info().document_count == 50


# ---------- 额外：top_k 生效 ----------

def test_top_k_limits_results(qmd_client):
    col = qmd_client.collection("c")
    for i in range(10):
        col.add_document(f"d{i}", f"document {i} talking about common topic.\n\nmore text.", {})
    results = col.hybrid_search("common", top_k=3)
    assert len(results) <= 3
