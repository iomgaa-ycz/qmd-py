"""Perf: 10 万 chunk 规模下 hybrid_search(top_k=5) P95 < 500ms。

默认 skip；`pytest -m perf` 触发。首次运行会构建 corpus DB（~20-40min）。
报告写入 tests/perf/.cache/report_hybrid_search.json。
"""
from __future__ import annotations

import json
import platform
import random
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.perf


_QUERY_SEEDS = [
    "法律 责任", "合同 条款", "审核 批准", "标准 技术", "数据 管理",
    "项目 实施", "报告 记录", "系统 平台", "评估 验收", "监督 检查",
    "市场 客户", "产品 服务", "流程 质量", "成本 效率", "计划 任务",
    "目标 结果", "分析 决策", "执行 反馈", "培训 教育", "学习 研究",
]


def _sample_queries(n: int, seed: int = 0) -> list[str]:
    rng = random.Random(seed)
    return [rng.choice(_QUERY_SEEDS) for _ in range(n)]


def test_p95_hybrid_search_under_500ms(large_corpus_db: Path):
    from qmd import connect

    client = connect(large_corpus_db)
    col = client.collection("bench")

    queries = _sample_queries(100)
    latencies_ms: list[float] = []

    # 预热 3 次（触发 embedding + sqlite-vec 索引加载）
    for q in queries[:3]:
        col.hybrid_search(q, top_k=5)

    for q in queries:
        t0 = time.perf_counter()
        col.hybrid_search(q, top_k=5)
        latencies_ms.append((time.perf_counter() - t0) * 1000)

    client.close()

    latencies_ms.sort()
    p50 = latencies_ms[49]
    p95 = latencies_ms[94]
    p99 = latencies_ms[98]

    report = {
        "test": "hybrid_search_p95",
        "n": len(queries),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "platform": platform.platform(),
        "python": platform.python_version(),
    }
    report_path = Path("tests/perf/.cache/report_hybrid_search.json")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{report}")
    assert p95 < 500, f"P95={p95:.1f}ms (target <500ms); 报告: {report_path}"


def test_batch_vs_loop_speedup_at_scale(large_corpus_db: Path):
    """50 文档批量 vs 循环单加，加速比 ≥ 3x。

    M2 小 benchmark (20 doc) 只到 1.8x（GPU kernel 固定开销 + tmpfs fsync 零成本），
    大规模下 embedding batch 吞吐优势显著，3x 应可稳定达标。
    """
    import tempfile

    from qmd import connect

    docs = [
        {"document_id": f"perf_d{i}", "markdown": f"批量性能测试段落 {i}。\n\n内容 " * 30, "metadata": {"i": i}}
        for i in range(50)
    ]

    with tempfile.TemporaryDirectory() as td:
        # 循环单加
        client1 = connect(Path(td) / "loop.sqlite")
        col1 = client1.collection("c")
        t0 = time.perf_counter()
        for d in docs:
            col1.add_document(d["document_id"], d["markdown"], d["metadata"])
        loop_time = time.perf_counter() - t0
        client1.close()

        # 批量
        client2 = connect(Path(td) / "batch.sqlite")
        col2 = client2.collection("c")
        t0 = time.perf_counter()
        col2.add_documents(docs)
        batch_time = time.perf_counter() - t0
        client2.close()

    speedup = loop_time / batch_time if batch_time > 0 else 0

    report = {
        "test": "batch_vs_loop_speedup",
        "n_docs": len(docs),
        "loop_s": round(loop_time, 3),
        "batch_s": round(batch_time, 3),
        "speedup": round(speedup, 1),
        "platform": platform.platform(),
    }
    report_path = Path("tests/perf/.cache/report_batch_speedup.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{report}")
    assert speedup >= 3.0, (
        f"batch={batch_time:.3f}s, loop={loop_time:.3f}s, "
        f"加速比={speedup:.1f}x (目标 ≥3x); 报告: {report_path}"
    )
