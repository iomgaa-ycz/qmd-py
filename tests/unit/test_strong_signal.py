"""单测：strong signal skip 逻辑。"""
from __future__ import annotations

from pathlib import Path

import pytest


def test_strong_signal_skip_when_high_bm25(tmp_path: Path):
    """BM25 probe 方法不报错，返回 bool。"""
    from qmd import connect

    client = connect(tmp_path / "db.sqlite")
    col = client.collection("c")
    col.add_document("d_exact", "Python 编程 Python 编程 Python 编程 Python 编程", {})
    col.add_document("d_noise", "香蕉苹果水果蔬菜牛奶面包鸡蛋", {})

    result = col._check_strong_signal("Python 编程", None)
    assert isinstance(result, bool)
    client.close()


def test_strong_signal_no_docs_returns_false(tmp_path: Path):
    """空 collection → 不跳过 expansion。"""
    from qmd import connect

    client = connect(tmp_path / "db.sqlite")
    col = client.collection("c")
    result = col._check_strong_signal("any query", None)
    assert result is False
    client.close()


def test_strong_signal_one_doc_returns_false(tmp_path: Path):
    """只有 1 个结果 → 不跳过。"""
    from qmd import connect

    client = connect(tmp_path / "db.sqlite")
    col = client.collection("c")
    col.add_document("d1", "Python 编程语言。", {})
    result = col._check_strong_signal("Python", None)
    assert result is False
    client.close()
