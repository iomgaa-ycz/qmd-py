"""单测：qmd/core/collection.py（依赖真实 Embedder）。

首次运行会下载 Qwen3-Embedding-0.6B (~1.2GB)。
"""
from __future__ import annotations

import pytest

from qmd.core.client import SqliteQmdClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db = tmp_path_factory.mktemp("col") / "db.sqlite"
    c = SqliteQmdClient(db)
    yield c
    c.close()


@pytest.fixture
def col(client):
    name = f"test_{id(object())}"
    c = client.collection(name)
    yield c
    client.delete_collection(name)


def test_add_and_get_document(col):
    col.add_document("d1", "# Hello\n\nworld", metadata={"tag": "a"})
    doc = col.get_document("d1")
    assert doc is not None
    assert doc["id"] == "d1"
    assert doc["markdown"] == "# Hello\n\nworld"
    assert doc["metadata"] == {"tag": "a"}
    assert doc["chunk_count"] >= 1


def test_add_document_is_upsert(col):
    col.add_document("d1", "first version")
    col.add_document("d1", "second version")
    doc = col.get_document("d1")
    assert doc["markdown"] == "second version"


def test_delete_document(col):
    col.add_document("d1", "to be deleted")
    col.delete_document("d1")
    assert col.get_document("d1") is None


def test_delete_nonexistent_is_noop(col):
    col.delete_document("never_existed")


def test_list_documents(col):
    col.add_document("a", "content a")
    col.add_document("b", "content b")
    ids = col.list_documents()
    assert set(ids) == {"a", "b"}


def test_info_counts(col):
    col.add_document("x", "# Title\n\nbody text")
    info = col.info()
    assert info.name == col.name
    assert info.document_count == 1
    assert info.chunk_count >= 1
    assert info.embedding_dim == 1024


def test_hybrid_search_returns_results(col):
    col.add_document("d1", "The quick brown fox jumps over the lazy dog.")
    col.add_document("d2", "Python is a programming language.")
    results = col.hybrid_search("programming language", top_k=5)
    assert len(results) >= 1
    assert results[0].chunk_ref.document_id == "d2"
    for a, b in zip(results, results[1:]):
        assert a.score >= b.score


def test_hybrid_search_rerank_is_noop_in_m1(col):
    col.add_document("d1", "hello world")
    results_a = col.hybrid_search("hello", rerank=False)
    results_b = col.hybrid_search("hello", rerank=True)
    assert [r.chunk_ref.document_id for r in results_a] == [r.chunk_ref.document_id for r in results_b]
    assert all(r.rerank_score is None for r in results_b)


def test_char_indices_match_original(col):
    md = "# H\n\n" + "x" * 1500 + "\n\n## H2\n\n" + "y" * 1500
    col.add_document("d", md)
    doc = col.get_document("d")
    assert doc is not None
    results = col.hybrid_search("x", top_k=10)
    for r in results:
        assert md[r.chunk_ref.char_start:r.chunk_ref.char_end] == r.text
