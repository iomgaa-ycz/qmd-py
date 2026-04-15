"""单测：qmd/core/embedding.py。不加载真实模型，靠 mock 验证接口。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from qmd.core.embedding import Embedder


@pytest.fixture(autouse=True)
def _reset_embedder_cache():
    """单测之间重置类级共享模型缓存，防止 mock 跨测试串台。"""
    Embedder._shared_model = None
    yield
    Embedder._shared_model = None


def test_embedder_dim_and_model_name_constants():
    assert Embedder.DIM == 1024
    assert Embedder.MODEL_NAME == "Qwen/Qwen3-Embedding-0.6B"


def test_empty_input_returns_empty_list():
    e = Embedder()
    assert e.embed([]) == []


def test_embed_returns_list_of_lists_with_correct_dim():
    e = Embedder()
    fake_model = MagicMock()
    fake_model.encode = MagicMock(
        return_value=np.array([[0.1] * 1024, [0.2] * 1024], dtype=np.float32)
    )
    with patch.object(Embedder, "_load_model", return_value=fake_model):
        result = e.embed(["hello", "world"])
    assert len(result) == 2
    assert all(len(vec) == 1024 for vec in result)
    assert all(isinstance(x, float) for vec in result for x in vec)


def test_model_loaded_lazily_once():
    e = Embedder()
    load_count = [0]

    def fake_load():
        load_count[0] += 1
        m = MagicMock()
        m.encode = MagicMock(return_value=np.zeros((1, 1024), dtype=np.float32))
        return m

    with patch.object(Embedder, "_load_model", side_effect=fake_load):
        e.embed(["a"])
        e.embed(["b"])
        e.embed(["c"])
    assert load_count[0] == 1
