"""契约测试：pydantic 模型往返稳定性与字段校验。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from qmd.models import ChunkRef, CollectionInfo, SearchResult


def test_chunk_ref_roundtrip():
    """ChunkRef.model_dump → model_validate 必须得到等价对象。"""
    ref = ChunkRef(document_id="doc1", chunk_index=0, char_start=0, char_end=9)
    dumped = ref.model_dump(mode="json")
    restored = ChunkRef.model_validate(dumped)
    assert restored == ref


def test_chunk_ref_char_end_must_be_greater_than_start():
    """char_end 必须 > char_start（闭区间，且非空）。"""
    with pytest.raises(ValidationError):
        ChunkRef(document_id="d", chunk_index=0, char_start=10, char_end=5)
    with pytest.raises(ValidationError):
        ChunkRef(document_id="d", chunk_index=0, char_start=10, char_end=10)


def test_search_result_optional_scores_default_none():
    """bm25/vector/rerank score 默认 None。"""
    ref = ChunkRef(document_id="d", chunk_index=0, char_start=0, char_end=4)
    r = SearchResult(chunk_ref=ref, text="hello", score=0.5, metadata={})
    assert r.bm25_score is None
    assert r.vector_score is None
    assert r.rerank_score is None


def test_search_result_roundtrip_with_all_fields():
    """SearchResult 全字段填充的 JSON 往返。"""
    ref = ChunkRef(document_id="d", chunk_index=1, char_start=10, char_end=19)
    r = SearchResult(
        chunk_ref=ref, text="world", score=0.9,
        bm25_score=0.7, vector_score=0.8, rerank_score=0.95,
        metadata={"type": "law", "year": 2024},
    )
    dumped = r.model_dump(mode="json")
    restored = SearchResult.model_validate(dumped)
    assert restored == r


def test_collection_info_roundtrip():
    info = CollectionInfo(name="rules", document_count=3, chunk_count=15, embedding_dim=384)
    assert CollectionInfo.model_validate(info.model_dump(mode="json")) == info


def test_collection_info_embedding_dim_optional():
    """未 embed 时 embedding_dim 可为 None。"""
    info = CollectionInfo(name="empty", document_count=0, chunk_count=0, embedding_dim=None)
    assert info.embedding_dim is None
