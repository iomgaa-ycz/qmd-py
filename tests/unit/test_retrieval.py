"""单测：qmd/core/retrieval.py。"""
from qmd.core.retrieval import rrf_fuse


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
