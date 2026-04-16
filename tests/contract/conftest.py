"""contract 测试 fixture。

本地跑：默认注入 FakeQmdClient。
下游 Scrivai 通过 pytest plugin（Task 5）也用同一 fixture 跑契约。
"""
from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from qmd.models import QmdClient


@pytest.fixture(params=["fake", "sqlite"])
def qmd_client_factory(request, tmp_path):
    """参数化：每个契约测试在 [fake] 和 [sqlite] 各跑一遍。"""
    backend = request.param
    if backend == "fake":
        from qmd.testing import FakeQmdClient
        def factory():
            return FakeQmdClient()
    else:
        from qmd.core.client import SqliteQmdClient
        def factory():
            return SqliteQmdClient(tmp_path / "contract.sqlite")
    yield factory


@pytest.fixture
def qmd_client(qmd_client_factory):
    client = qmd_client_factory()
    yield client
    client.close()


@pytest.fixture
def fixture_root() -> Path:
    """返回 fixture 根目录。

    优先级：env GOVDOC_FIXTURES > tests/fixtures/。
    GovDoc-Auditor 仓库提供真 fixtures 后，设 env 即可切换。
    """
    env_path = os.environ.get("GOVDOC_FIXTURES")
    if env_path:
        return Path(env_path)
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def guide_excerpt_markdown(fixture_root: Path) -> str:
    return (fixture_root / "guide_excerpt.md").read_text(encoding="utf-8")
