"""qmd 契约测试 pytest plugin。

下游（如 Scrivai）：
1. pip install qmd[testing]
2. 在 conftest.py 覆盖 qmd_client_factory fixture 指向自己的实现
3. 运行 pytest，本 plugin 自动贡献契约测试集

plugin 机制：通过 pyproject.toml 的 [project.entry-points.pytest11] 注册。
"""
from __future__ import annotations

from collections.abc import Callable

import pytest

from qmd.models import QmdClient


@pytest.fixture
def qmd_client_factory() -> Callable[[], QmdClient]:
    """下游必须在自己的 conftest.py 覆盖此 fixture。

    示例：
        @pytest.fixture
        def qmd_client_factory():
            from qmd.testing import FakeQmdClient
            return lambda: FakeQmdClient()
    """
    raise NotImplementedError(
        "请在你的 conftest.py 覆盖 qmd_client_factory fixture。"
        "示例：返回 lambda: FakeQmdClient()"
    )


@pytest.fixture
def qmd_client(qmd_client_factory):
    """统一的 qmd_client fixture，契约测试集使用。"""
    client = qmd_client_factory()
    yield client
    client.close()
