"""contract 测试 fixture。

本地跑：默认注入 FakeQmdClient。
下游 Scrivai 通过 pytest plugin（Task 5）也用同一 fixture 跑契约。
"""
from __future__ import annotations

from collections.abc import Callable

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
