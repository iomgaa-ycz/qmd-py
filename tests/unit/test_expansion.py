"""单测：qmd/core/expansion.py — QueryExpander mock 测试。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_expander_cache():
    """每个测试前重置类级单例。"""
    from qmd.core.expansion import QueryExpander
    QueryExpander._shared_model = None
    QueryExpander._shared_tokenizer = None
    yield
    QueryExpander._shared_model = None
    QueryExpander._shared_tokenizer = None


def test_model_name():
    from qmd.core.expansion import QueryExpander
    assert QueryExpander.MODEL_NAME == "Qwen/Qwen3-0.6B"


def test_empty_query_returns_empty():
    """空查询不触发模型加载，返回空变体。"""
    from qmd.core.expansion import QueryExpander
    result = QueryExpander().expand("")
    assert result == {"lex": [], "vec": [], "hyde": []}


def test_expand_parses_json_output():
    """mock 模型输出 JSON，验证解析逻辑。"""
    from qmd.core.expansion import QueryExpander

    mock_model = MagicMock()
    mock_tokenizer = MagicMock()

    mock_tokenizer.return_value = {"input_ids": MagicMock()}
    mock_tokenizer.return_value["input_ids"].to = MagicMock(return_value=MagicMock())

    import torch
    mock_output_ids = torch.tensor([[1, 2, 3, 4, 5]])
    mock_model.generate = MagicMock(return_value=mock_output_ids)
    mock_model.device = "cpu"

    json_output = '{"lex": ["keyword variant"], "vec": ["semantic rephrase"], "hyde": ["hypothetical doc"]}'
    mock_tokenizer.decode = MagicMock(return_value=json_output)

    with patch.object(QueryExpander, "_ensure", return_value=(mock_model, mock_tokenizer)):
        result = QueryExpander().expand("test query")

    assert result["lex"] == ["keyword variant"]
    assert result["vec"] == ["semantic rephrase"]
    assert result["hyde"] == ["hypothetical doc"]


def test_expand_bad_json_returns_empty():
    """模型输出非法 JSON → 降级为空变体，不抛错。"""
    from qmd.core.expansion import QueryExpander

    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    mock_tokenizer.return_value = {"input_ids": MagicMock()}
    mock_tokenizer.return_value["input_ids"].to = MagicMock(return_value=MagicMock())

    import torch
    mock_model.generate = MagicMock(return_value=torch.tensor([[1, 2, 3]]))
    mock_model.device = "cpu"
    mock_tokenizer.decode = MagicMock(return_value="this is not json at all")

    with patch.object(QueryExpander, "_ensure", return_value=(mock_model, mock_tokenizer)):
        result = QueryExpander().expand("test query")

    assert result == {"lex": [], "vec": [], "hyde": []}


def test_model_loaded_once():
    """类级单例：多次实例化只加载一次模型。"""
    from qmd.core.expansion import QueryExpander

    mock_model = MagicMock()
    mock_tokenizer = MagicMock()

    with patch.object(QueryExpander, "_load", return_value=(mock_model, mock_tokenizer)) as mock_load:
        e1 = QueryExpander()
        e1._ensure()
        e2 = QueryExpander()
        e2._ensure()
        assert mock_load.call_count == 1
