"""契约测试 T0.3：Protocol runtime_checkable 可用。"""
from __future__ import annotations

from qmd import Collection, QmdClient, connect


def test_qmd_client_runtime_checkable():
    client = connect()
    assert isinstance(client, QmdClient)
    client.close()


def test_collection_runtime_checkable():
    client = connect()
    col = client.collection("c")
    assert isinstance(col, Collection)
    client.close()
