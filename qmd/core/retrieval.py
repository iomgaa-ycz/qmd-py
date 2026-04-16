"""Reciprocal Rank Fusion（RRF）纯函数 + Position-Aware Blending。"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qmd.core.config import BlendingWeights

from qmd.models import SearchResult


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


def position_aware_blend(
    candidates: list[SearchResult],
    blending_weights: "BlendingWeights",
) -> list[SearchResult]:
    """按 rank 分档混合 RRF score 和 rerank score。

    前提：candidates 已按 rerank_score 降序排列，每个 c.rerank_score 非 None。
    blending 后根据混合分数重新排序。
    """
    if not candidates:
        return candidates
    for i, c in enumerate(candidates):
        rank = i + 1
        if rank <= 3:
            rrf_w, rerank_w = blending_weights.top
        elif rank <= 10:
            rrf_w, rerank_w = blending_weights.mid
        else:
            rrf_w, rerank_w = blending_weights.tail
        c.score = rrf_w * c.score + rerank_w * (c.rerank_score or 0.0)
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates
