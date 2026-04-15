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
