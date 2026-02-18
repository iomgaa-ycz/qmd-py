"""
智能分块算法测试

测试断点评分、代码块保护、短文档不切分、长文档切分+重叠
"""

import pytest
from qmd.core.chunking import (
    BREAK_PATTERNS,
    BreakPoint,
    CodeFenceRegion,
    Chunk,
    scan_break_points,
    find_code_fences,
    is_inside_code_fence,
    find_best_cutoff,
    chunk_document,
    chunk_document_by_tokens,
)


class TestBreakPointScanning:
    """测试断点扫描和评分"""

    def test_scan_h1_breakpoint(self):
        """测试识别 H1 标题"""
        text = "\n# Header 1\nSome content"
        points = scan_break_points(text)

        assert len(points) >= 1
        h1_point = next(p for p in points if p.type == 'h1')
        assert h1_point.score == 100
        assert text[h1_point.pos:h1_point.pos + 2] == "\n#"

    def test_scan_multiple_headings(self):
        """测试扫描多级标题"""
        text = "\n# H1\n## H2\n### H3\nContent"
        points = scan_break_points(text)

        h1 = next((p for p in points if p.type == 'h1'), None)
        h2 = next((p for p in points if p.type == 'h2'), None)
        h3 = next((p for p in points if p.type == 'h3'), None)

        assert h1 is not None and h1.score == 100
        assert h2 is not None and h2.score == 90
        assert h3 is not None and h3.score == 80

    def test_scan_codeblock_boundary(self):
        """测试识别代码块边界"""
        text = "Text\n```python\ncode\n```\nMore text"
        points = scan_break_points(text)

        codeblock_points = [p for p in points if p.type == 'codeblock']
        assert len(codeblock_points) == 2  # 开始和结束

    def test_scan_blank_lines(self):
        """测试识别空行"""
        text = "Paragraph 1\n\nParagraph 2"
        points = scan_break_points(text)

        blank_point = next((p for p in points if p.type == 'blank'), None)
        assert blank_point is not None
        assert blank_point.score == 20

    def test_same_position_keeps_highest_score(self):
        """测试同一位置多个模式时保留最高分"""
        # 在同一位置可能有 newline (分数1) 和其他模式
        text = "\n# Title\n"
        points = scan_break_points(text)

        # 位置0应该是 h1，不是 newline
        pos0_points = [p for p in points if p.pos == 0]
        if pos0_points:
            assert pos0_points[0].type == 'h1'
            assert pos0_points[0].score == 100

    def test_points_sorted_by_position(self):
        """测试断点按位置排序"""
        text = "\n### H3\n\n# H1\n## H2"
        points = scan_break_points(text)

        positions = [p.pos for p in points]
        assert positions == sorted(positions)


class TestCodeFenceDetection:
    """测试代码块检测"""

    def test_find_closed_code_fence(self):
        """测试查找闭合的代码块"""
        text = "Before\n```python\ncode\n```\nAfter"
        fences = find_code_fences(text)

        assert len(fences) == 1
        assert fences[0].start == text.index("\n```")
        assert fences[0].end == text.rindex("\n```")

    def test_find_unclosed_code_fence(self):
        """测试未闭合的代码块延伸到文档末尾"""
        text = "Before\n```python\ncode goes on forever"
        fences = find_code_fences(text)

        assert len(fences) == 1
        assert fences[0].start == text.index("\n```")
        assert fences[0].end == len(text)

    def test_find_multiple_code_fences(self):
        """测试多个代码块"""
        text = "Text\n```\ncode1\n```\nMiddle\n```\ncode2\n```\nEnd"
        fences = find_code_fences(text)

        assert len(fences) == 2

    def test_is_inside_code_fence(self):
        """测试判断位置是否在代码块内"""
        text = "Before\n```python\ncode\n```\nAfter"
        fences = find_code_fences(text)

        fence_start = text.index("\n```")
        fence_end = text.rindex("\n```")

        # 在代码块内
        assert is_inside_code_fence(fence_start + 10, fences)
        # 在代码块外
        assert not is_inside_code_fence(0, fences)
        assert not is_inside_code_fence(len(text) - 1, fences)
        # 边界上
        assert not is_inside_code_fence(fence_start, fences)
        assert not is_inside_code_fence(fence_end, fences)

    def test_best_cutoff_avoids_code_fence(self):
        """测试最佳切分点避开代码块内部"""
        text = "Text before\n```python\ndef foo():\n    pass\n```\nText after"

        break_points = scan_break_points(text)
        fences = find_code_fences(text)

        # 目标位置在代码块中间
        fence_start = text.index("\n```")
        target_pos = fence_start + 20  # 代码块内部

        best_pos = find_best_cutoff(break_points, target_pos, 100, 0.7, fences)

        # 最佳位置不应该在代码块内
        assert not is_inside_code_fence(best_pos, fences)


class TestDocumentChunking:
    """测试文档分块"""

    def test_short_document_not_chunked(self):
        """测试短文档不切分"""
        short_text = "This is a short document."
        chunks = chunk_document(short_text, max_chars=1000)

        assert len(chunks) == 1
        assert chunks[0].text == short_text
        assert chunks[0].pos == 0

    def test_long_document_chunked(self):
        """测试长文档被切分"""
        # 创建一个超过 max_chars 的文档
        long_text = "x" * 5000
        chunks = chunk_document(long_text, max_chars=1000, overlap_chars=100)

        assert len(chunks) > 1
        # 检查每个块不超过 max_chars（除了可能的最后一块）
        for chunk in chunks[:-1]:
            assert len(chunk.text) <= 1000

    def test_chunk_overlap(self):
        """测试块之间有重叠"""
        text = "a" * 2000
        chunks = chunk_document(text, max_chars=1000, overlap_chars=100)

        # 检查相邻块之间有重叠
        for i in range(len(chunks) - 1):
            chunk1 = chunks[i]
            chunk2 = chunks[i + 1]

            # chunk2 的起始位置应该在 chunk1 结束前 overlap_chars
            chunk1_end = chunk1.pos + len(chunk1.text)
            expected_overlap_start = chunk1_end - 100

            # chunk2.pos 应该接近 expected_overlap_start（可能因断点调整）
            # 允许一定误差
            assert abs(chunk2.pos - expected_overlap_start) < 200

    def test_chunk_at_heading_boundary(self):
        """测试在标题处切分"""
        # 创建一个在合适位置有标题的文档
        text = "x" * 900 + "\n# Important Section\n" + "y" * 900
        chunks = chunk_document(text, max_chars=1000, overlap_chars=50)

        # 应该有多个块
        assert len(chunks) >= 2

        # 检查是否在标题附近切分
        h1_pos = text.index("\n# Important Section")
        # 某个块的边界应该接近标题位置
        chunk_boundaries = [c.pos for c in chunks] + [chunks[-1].pos + len(chunks[-1].text)]
        nearby = any(abs(boundary - h1_pos) < 200 for boundary in chunk_boundaries)
        assert nearby

    def test_chunk_preserves_code_blocks(self):
        """测试代码块不被内部切分"""
        code_block = "\n```python\n" + "x" * 500 + "\n```\n"
        text = "a" * 800 + code_block + "b" * 800

        chunks = chunk_document(text, max_chars=1000, overlap_chars=50)

        # 检查没有切分点在代码块内部
        code_start = text.index("\n```python")
        code_end = text.index("\n```\n", code_start + 1)

        # 收集所有切分点（块的开始位置）
        # 注意：由于 overlap，后续块可能会重复包含代码块的部分内容，这是预期行为
        # 但切分点（即决定在哪里"切断"前一块的位置）不应该在代码块内部
        chunk_boundaries = []
        for i, chunk in enumerate(chunks):
            if i > 0:
                # 前一块的结束位置就是切分点
                prev_end = chunks[i-1].pos + len(chunks[i-1].text)
                chunk_boundaries.append(prev_end)

        # 验证没有切分点在代码块内部（不包括边界）
        for boundary in chunk_boundaries:
            assert not (code_start < boundary < code_end), \
                f"切分点 {boundary} 在代码块内部 ({code_start}, {code_end})"

    def test_chunk_positions(self):
        """测试块的位置标记正确"""
        text = "a" * 3000
        chunks = chunk_document(text, max_chars=1000, overlap_chars=100)

        # 第一个块从位置 0 开始
        assert chunks[0].pos == 0

        # 每个块的位置应该对应实际内容
        for chunk in chunks:
            assert text[chunk.pos:chunk.pos + len(chunk.text)] == chunk.text


class TestTokenBasedChunking:
    """测试基于 Token 的分块"""

    def test_chunk_without_tokenizer(self):
        """测试没有 tokenizer 时使用估算"""
        text = "这是一个中文测试文档" * 100
        chunks = chunk_document_by_tokens(text, tokenizer=None, max_tokens=100)

        assert len(chunks) >= 1
        # 每个块应该有 tokens 字段
        for chunk in chunks:
            assert chunk.tokens is not None
            assert chunk.tokens > 0

    def test_chunk_with_mock_tokenizer(self):
        """测试使用 tokenizer 进行精确切分"""
        class MockTokenizer:
            def tokenize(self, text: str) -> list[int]:
                # 简单模拟：每个字符 = 1 token
                return list(range(len(text)))

        text = "a" * 2000
        tokenizer = MockTokenizer()
        chunks = chunk_document_by_tokens(text, tokenizer, max_tokens=500)

        # 验证没有块超过 token 限制
        for chunk in chunks:
            assert chunk.tokens is not None
            assert chunk.tokens <= 500


class TestEdgeCases:
    """测试边界情况"""

    def test_empty_document(self):
        """测试空文档"""
        chunks = chunk_document("", max_chars=1000)
        assert len(chunks) == 1
        assert chunks[0].text == ""

    def test_document_exactly_max_chars(self):
        """测试文档长度恰好等于 max_chars"""
        text = "x" * 1000
        chunks = chunk_document(text, max_chars=1000)
        assert len(chunks) == 1
        assert chunks[0].text == text

    def test_no_good_break_points(self):
        """测试没有好的断点时仍能切分"""
        # 没有任何空行、标题等，只有一长串字符
        text = "x" * 5000
        chunks = chunk_document(text, max_chars=1000, overlap_chars=100)

        # 应该仍然能切分（使用 newline 或强制切分）
        assert len(chunks) > 1

    def test_very_small_overlap(self):
        """测试极小的重叠"""
        text = "a" * 2000
        chunks = chunk_document(text, max_chars=1000, overlap_chars=10)

        assert len(chunks) >= 2
        # 验证仍然有重叠（即使很小）
        for i in range(len(chunks) - 1):
            chunk1_end = chunks[i].pos + len(chunks[i].text)
            chunk2_start = chunks[i + 1].pos
            assert chunk2_start < chunk1_end
