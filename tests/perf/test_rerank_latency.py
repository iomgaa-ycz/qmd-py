"""Perf: rerank 开销 < 200ms / query（top_k_candidates=40）。

默认 skip；`pytest -m "perf and reranker"` 触发。
CPU 环境可能不达标，此时记录 xfail 不阻塞。
报告写入 tests/perf/.cache/report_rerank.json。
"""
from __future__ import annotations

import json
import platform
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.perf, pytest.mark.reranker]


def test_rerank_latency_under_200ms(large_corpus_db: Path):
    from qmd import connect

    client = connect(
        large_corpus_db,
        config_overrides={"rerank": {"enabled": True}},
    )
    col = client.collection("bench")

    queries = [
        "法律 责任", "合同 条款", "审核 批准", "标准 技术", "数据 管理",
        "项目 实施", "报告 记录", "系统 平台", "评估 验收", "监督 检查",
    ]

    # 预热（触发 reranker 模型加载）
    col.hybrid_search(queries[0], top_k=5, rerank=True)

    latencies_ms: list[float] = []
    for q in queries:
        t0 = time.perf_counter()
        col.hybrid_search(q, top_k=5, rerank=True)
        latencies_ms.append((time.perf_counter() - t0) * 1000)

    client.close()

    latencies_ms.sort()
    p50 = latencies_ms[len(latencies_ms) // 2]
    p95 = latencies_ms[int(len(latencies_ms) * 0.95)]

    report = {
        "test": "rerank_latency",
        "n": len(queries),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "platform": platform.platform(),
    }
    report_path = Path("tests/perf/.cache/report_rerank.json")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{report}")
    if p95 >= 200:
        pytest.xfail(
            f"rerank P95={p95:.1f}ms (target <200ms) — 环境未达标，记录于 {report_path}"
        )
