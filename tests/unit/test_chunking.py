"""单测：qmd/core/chunking.py。"""
from __future__ import annotations

from qmd.core.chunking import Chunk, chunk_document


def test_empty_text_returns_empty_list():
    assert chunk_document("") == []


def test_short_text_returns_single_chunk():
    text = "hello world"
    chunks = chunk_document(text, size=512, overlap=64)
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(text)


def test_chunk_preserves_char_indices():
    text = "A\n\n" + ("x" * 600) + "\n\n" + ("y" * 600)
    chunks = chunk_document(text, size=512, overlap=64)
    for c in chunks:
        assert text[c.char_start:c.char_end] == c.text
        assert c.char_start < c.char_end


def test_chunks_are_contiguous_with_overlap():
    text = ("word " * 800).strip()  # ~4000 chars → > 512-token threshold
    chunks = chunk_document(text, size=512, overlap=64)
    assert len(chunks) >= 2
    for a, b in zip(chunks, chunks[1:]):
        assert a.char_end >= b.char_start


def test_code_fence_not_split_in_middle():
    body = "text " * 200
    fenced = "```python\n" + ("code_line\n" * 300) + "```\n"
    text = body + fenced + body
    chunks = chunk_document(text, size=512, overlap=64)
    fence_open = text.index("```python")
    fence_close = text.index("```\n", fence_open + 3)
    for c in chunks:
        assert not (fence_open < c.char_start < fence_close), \
            f"chunk start {c.char_start} inside fence [{fence_open},{fence_close}]"
        assert not (fence_open < c.char_end < fence_close), \
            f"chunk end {c.char_end} inside fence [{fence_open},{fence_close}]"


def test_heading_boundary_preferred():
    # size=512 tokens ≈ 1024 chars；构造 1600+ 字符文本保证多 chunk
    prefix = "a " * 600
    text = prefix + "\n## New Section\n" + "b " * 600
    chunks = chunk_document(text, size=512, overlap=64)
    assert len(chunks) >= 2, f"expected multi-chunk, got {len(chunks)}"
    boundary = chunks[0].char_end
    section_idx = text.index("## New Section")
    # 第一 chunk 的终点应落在 H2 标题附近（±100 字符窗口内）
    assert abs(boundary - section_idx) <= 100, \
        f"boundary={boundary} section={section_idx}, diff={boundary - section_idx}"


def test_chunk_is_frozen_dataclass():
    c = Chunk(text="x", char_start=0, char_end=1)
    try:
        c.text = "y"  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("Chunk should be frozen")
