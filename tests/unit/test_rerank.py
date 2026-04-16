"""单测：qmd/core/rerank.py — Qwen3-Reranker 接口。使用 mock 模型避免真实加载。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import torch

from qmd.core.rerank import Reranker


@pytest.fixture(autouse=True)
def _reset_reranker_cache():
    Reranker._shared_model = None
    Reranker._shared_tokenizer = None
    yield
    Reranker._shared_model = None
    Reranker._shared_tokenizer = None


def test_reranker_model_name_constant():
    assert Reranker.MODEL_NAME == "Qwen/Qwen3-Reranker-0.6B"


def test_empty_docs_returns_empty_list():
    r = Reranker()
    assert r.score("query", []) == []


def test_score_returns_floats_in_unit_interval():
    """mock 模型返回可控 logits，验证 softmax 后得分 ∈ [0,1]。"""
    r = Reranker()

    fake_tokenizer = MagicMock()
    fake_tokenizer.return_value = {
        "input_ids": torch.zeros((2, 10), dtype=torch.long),
        "attention_mask": torch.ones((2, 10), dtype=torch.long),
    }
    fake_tokenizer.convert_tokens_to_ids = MagicMock(
        side_effect=lambda tok: 100 if tok == "yes" else 200
    )

    fake_model = MagicMock()
    logits = torch.full((2, 10, 1000), -10.0)
    logits[0, -1, 100] = 5.0   # doc 0: yes >> no
    logits[0, -1, 200] = -5.0
    logits[1, -1, 100] = -5.0  # doc 1: no >> yes
    logits[1, -1, 200] = 5.0
    fake_output = MagicMock()
    fake_output.logits = logits
    fake_model.return_value = fake_output
    fake_model.device = torch.device("cpu")

    with patch.object(Reranker, "_load", return_value=(fake_model, fake_tokenizer)):
        scores = r.score("q", ["doc_about_q", "unrelated_doc"])

    assert len(scores) == 2
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert scores[0] > scores[1]


def test_model_loaded_once():
    r = Reranker()
    call_count = [0]

    def fake_load():
        call_count[0] += 1
        tok = MagicMock()
        tok.return_value = {
            "input_ids": torch.zeros((1, 5), dtype=torch.long),
            "attention_mask": torch.ones((1, 5), dtype=torch.long),
        }
        tok.convert_tokens_to_ids = MagicMock(side_effect=lambda t: 100 if t == "yes" else 200)
        model = MagicMock()
        out = MagicMock()
        out.logits = torch.zeros((1, 5, 1000))
        out.logits[0, -1, 100] = 1.0
        model.return_value = out
        model.device = torch.device("cpu")
        return (model, tok)

    with patch.object(Reranker, "_load", side_effect=fake_load):
        r.score("q", ["d1"])
        r.score("q", ["d2"])
        r.score("q", ["d3"])
    assert call_count[0] == 1
