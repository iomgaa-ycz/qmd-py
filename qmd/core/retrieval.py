"""Reciprocal Rank Fusion（RRF）纯函数。"""
from __future__ import annotations


def rrf_fuse(
    rankings: list[list[int]],
    k: int = 60,
) -> list[tuple[int, float]]:
    """融合多个排序列表。

    参数：
        rankings: 多个按相关度降序的 rowid 列表。同一 rowid 可能出现在多个列表里。
        k: RRF 常数，默认 60（design §4.1）。

    返回：(rowid, rrf_score) 列表，按 rrf_score 降序；打平时按 rowid 升序（稳定）。
    rrf_score = Σ_i 1 / (k + rank_i(rowid))，rank 从 0 开始。
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, rowid in enumerate(ranking):
            scores[rowid] = scores.get(rowid, 0.0) + 1.0 / (k + rank)
    # 先按 rowid 升序（tie-breaker），再按 score 降序
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))
