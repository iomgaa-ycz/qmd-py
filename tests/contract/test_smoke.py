"""I1 smoke test：真实 fixture 跑完整 add + hybrid_search 流程（参数化 fake + sqlite）。"""
from __future__ import annotations


def test_smoke_guide_excerpt(qmd_client, guide_excerpt_markdown):
    col = qmd_client.collection("smoke")
    col.add_document("guide", guide_excerpt_markdown)
    results = col.hybrid_search("Collection 隔离", top_k=3)
    assert len(results) >= 1, "期望至少召回一条结果"
    # fixture 的第一章节讲 Collection，top_k 结果里应至少一条提及
    assert any(
        "Collection" in r.text or "collection" in r.text.lower()
        for r in results
    ), f"期望结果含 Collection，实际: {[r.text[:60] for r in results]}"
