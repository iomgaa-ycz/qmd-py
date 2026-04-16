"""Reciprocal Rank Fusion（RRF）纯函数。"""
from __future__ import annotations


def rrf_fuse(
    rankings: list[list[int]],
    k: int = 60,
    weights: list[float] | None = None,
) -> list[tuple[int, float]]:
    """融合多个排序列表。

    参数：
        rankings: 多个按相关度降序的 rowid 列表。同一 rowid 可能出现在多个列表里。
        k: RRF 常数，默认 60（design §4.1）。
        weights: 每个 ranking 的权重，默认 None（等价于全 1.0）。
                 长度须与 rankings 相同。

    返回：(rowid, rrf_score) 列表，按 rrf_score 降序；打平时按 rowid 升序（稳定）。
    rrf_score = Σ_i w_i / (k + rank_i(rowid))，rank 从 0 开始。
    """
    if weights is None:
        weights = [1.0] * len(rankings)
    scores: dict[int, float] = {}
    for w, ranking in zip(weights, rankings):
        for rank, rowid in enumerate(ranking):
            scores[rowid] = scores.get(rowid, 0.0) + w / (k + rank)
    # 先按 rowid 升序（tie-breaker），再按 score 降序
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))
