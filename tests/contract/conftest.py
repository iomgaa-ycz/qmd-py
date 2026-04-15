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


@pytest.fixture
def qmd_client_factory() -> Callable[[], QmdClient]:
    """默认注入 FakeQmdClient。M1 后会新增一个参数化 fixture 同时跑 Sqlite。"""
    from qmd.testing.fakes import FakeQmdClient
    return lambda: FakeQmdClient()


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
