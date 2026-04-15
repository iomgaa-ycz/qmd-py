"""契约测试：Collection.add_documents 批量入库。参数化 [fake, sqlite]。"""
from __future__ import annotations

import time

import pytest


def test_batch_add_basic(qmd_client):
    col = qmd_client.collection("c")
    col.add_documents([
        {"document_id": "d1", "markdown": "alpha beta.", "metadata": {}},
        {"document_id": "d2", "markdown": "gamma delta.", "metadata": {"t": "x"}},
        {"document_id": "d3", "markdown": "epsilon zeta.", "metadata": {}},
    ])
    assert set(col.list_documents()) == {"d1", "d2", "d3"}
    assert col.get_document("d2")["metadata"] == {"t": "x"}


def test_batch_upsert(qmd_client):
    """批量内包含已存在 id → 覆盖；批内同 id 以最后一个为准。"""
    col = qmd_client.collection("c")
    col.add_document("d1", "OLD content", {"v": 1})
    col.add_documents([
        {"document_id": "d1", "markdown": "first", "metadata": {"v": 2}},
        {"document_id": "d1", "markdown": "NEW content", "metadata": {"v": 3}},
        {"document_id": "d2", "markdown": "other", "metadata": {}},
    ])
    doc = col.get_document("d1")
    assert doc["markdown"] == "NEW content"
    assert doc["metadata"] == {"v": 3}


def test_batch_atomic_rollback(qmd_client):
    """第 3 个 doc 缺 markdown → 整批抛错，前 2 个也不应入库。"""
    col = qmd_client.collection("c")
    with pytest.raises(ValueError):
        col.add_documents([
            {"document_id": "d1", "markdown": "ok", "metadata": {}},
            {"document_id": "d2", "markdown": "ok2", "metadata": {}},
            {"document_id": "d3", "metadata": {}},  # 缺 markdown
        ])
    assert col.list_documents() == []


def test_batch_empty_noop(qmd_client):
    col = qmd_client.collection("c")
    col.add_documents([])
    assert col.list_documents() == []


def test_batch_wrong_type_raises(qmd_client):
    """字段类型错 → ValueError。"""
    col = qmd_client.collection("c")
    with pytest.raises(ValueError):
        col.add_documents([
            {"document_id": 123, "markdown": "ok", "metadata": {}},  # id 非 str
        ])
    assert col.list_documents() == []


def test_batch_faster_than_loop_sqlite(tmp_path):
    """仅 sqlite 后端：20 文档批量 vs 循环单加，批量 ≥1.5x 快。

    设计 spec §1 目标 "≥3x" 在 10万 chunk 规模（Task 11 端到端 perf）才稳定成立；
    小规模 benchmark 中 GPU embedding 固定开销小 + tmpfs fsync 接近零
    → 加速比常落在 1.5-2x（GPU kernel 启动 + 单次 COMMIT 节省 fsync 的那部分）。
    此处只校验 "显著加速"（1.5x 是保守下限，确保批量 API 确实走了正确路径），
    3x+ 目标由 Task 11 perf 验证。不参数化——性能断言只对真实 SQLite 后端有意义。
    """
    from qmd import connect

    docs = [
        {"document_id": f"d{i}", "markdown": f"段落 {i}。\n\n内容 " * 20, "metadata": {"i": i}}
        for i in range(20)
    ]

    # 预热 Embedder（首次加载 ~1.2GB 模型不计入基准）
    warmup_client = connect(tmp_path / "warmup.sqlite")
    warmup_client.collection("c").add_document("w", "预热", {})
    warmup_client.close()

    # 循环单加计时
    client1 = connect(tmp_path / "loop.sqlite")
    col1 = client1.collection("c")
    t0 = time.perf_counter()
    for d in docs:
        col1.add_document(d["document_id"], d["markdown"], d["metadata"])
    loop_time = time.perf_counter() - t0
    client1.close()

    # 批量计时
    client2 = connect(tmp_path / "batch.sqlite")
    col2 = client2.collection("c")
    t0 = time.perf_counter()
    col2.add_documents(docs)
    batch_time = time.perf_counter() - t0
    client2.close()

    assert batch_time * 1.5 <= loop_time, (
        f"batch={batch_time:.3f}s, loop={loop_time:.3f}s, 加速比={loop_time/batch_time:.1f}x (目标 ≥1.5x)"
    )
