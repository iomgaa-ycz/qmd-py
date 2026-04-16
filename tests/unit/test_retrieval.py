"""单测：qmd/core/retrieval.py。"""
from qmd.core.config import BlendingWeights
from qmd.core.retrieval import position_aware_blend, rrf_fuse
from qmd.models import ChunkRef, SearchResult


def test_empty_rankings_returns_empty():
    assert rrf_fuse([]) == []


def test_single_ranking_preserves_order():
    result = rrf_fuse([[10, 20, 30]])
    assert [rowid for rowid, _ in result] == [10, 20, 30]
    # 严格降序
    assert all(result[i][1] > result[i + 1][1] for i in range(len(result) - 1))


def test_two_rankings_fuse_both():
    a = [1, 2, 3]
    b = [3, 2, 4]
    result = rrf_fuse([a, b], k=60)
    rowids = [rowid for rowid, _ in result]
    assert set(rowids) == {1, 2, 3, 4}
    # 3 在 a=rank2、b=rank0 都高 → 应 top1
    assert rowids[0] == 3


def test_scores_strictly_descending():
    a = [1, 2, 3, 4, 5]
    b = [5, 4, 3, 2, 1]
    result = rrf_fuse([a, b], k=60)
    scores = [s for _, s in result]
    for s1, s2 in zip(scores, scores[1:]):
        assert s1 >= s2  # RRF 允许打平；打平时用 rowid 稳定排序


def test_rrf_formula():
    # 单一 ranking，rrf_score = 1/(k+rank)，rank 从 0 开始
    k = 60
    result = rrf_fuse([[10, 20]], k=k)
    scores = dict(result)
    assert abs(scores[10] - 1 / (k + 0)) < 1e-9
    assert abs(scores[20] - 1 / (k + 1)) < 1e-9


def test_weighted_rrf_double_weight():
    """weights=[2.0, 1.0] 时第一个列表得分翻倍。"""
    k = 60
    # rowid=1 只在 ranking a（weight=2.0）rank0；rowid=2 只在 ranking b（weight=1.0）rank0
    result = rrf_fuse([[1], [2]], k=k, weights=[2.0, 1.0])
    scores = dict(result)
    assert abs(scores[1] - 2.0 / (k + 0)) < 1e-9
    assert abs(scores[2] - 1.0 / (k + 0)) < 1e-9
    # rowid=1 得分更高
    assert scores[1] > scores[2]


def test_weighted_rrf_none_weights_equals_unweighted():
    """weights=None 结果应与 weights=[1.0, 1.0] 完全相同。"""
    rankings = [[1, 2, 3], [3, 2, 4]]
    result_none = rrf_fuse(rankings, k=60, weights=None)
    result_ones = rrf_fuse(rankings, k=60, weights=[1.0, 1.0])
    assert result_none == result_ones


def test_weighted_rrf_empty_with_weights():
    """空列表 + weights 不报错，返回空。"""
    result = rrf_fuse([[], []], k=60, weights=[2.0, 3.0])
    assert result == []


def _make_result(doc_id: str, rrf_score: float, rerank_score: float) -> SearchResult:
    return SearchResult(
        chunk_ref=ChunkRef(document_id=doc_id, chunk_index=0, char_start=0, char_end=10),
        text="dummy",
        score=rrf_score,
        rerank_score=rerank_score,
        metadata={},
    )


def test_position_aware_blend_reorders():
    """blending 后按混合分数重新排序。"""
    weights = BlendingWeights()
    candidates = [
        _make_result("d1", rrf_score=0.9, rerank_score=0.1),
        _make_result("d2", rrf_score=0.1, rerank_score=0.9),
        _make_result("d3", rrf_score=0.5, rerank_score=0.5),
    ]
    blended = position_aware_blend(candidates, weights)
    # rank 1-3 用 top 权重: 0.75*rrf + 0.25*rerank
    # d1: 0.75*0.9 + 0.25*0.1 = 0.7
    # d2: 0.75*0.1 + 0.25*0.9 = 0.3
    # d3: 0.75*0.5 + 0.25*0.5 = 0.5
    assert blended[0].chunk_ref.document_id == "d1"
    assert blended[1].chunk_ref.document_id == "d3"
    assert blended[2].chunk_ref.document_id == "d2"


def test_position_aware_blend_uses_mid_weights():
    """rank 4-10 用 mid 权重。"""
    weights = BlendingWeights()
    candidates = [_make_result(f"d{i}", rrf_score=0.5, rerank_score=0.5) for i in range(11)]
    candidates[3] = _make_result("d3_special", rrf_score=0.8, rerank_score=0.2)
    blended = position_aware_blend(candidates, weights)
    d3 = [c for c in blended if c.chunk_ref.document_id == "d3_special"][0]
    assert abs(d3.score - (0.60 * 0.8 + 0.40 * 0.2)) < 1e-9


def test_position_aware_blend_empty():
    """空列表不报错。"""
    assert position_aware_blend([], BlendingWeights()) == []
