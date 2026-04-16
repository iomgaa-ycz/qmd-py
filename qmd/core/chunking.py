"""语义边界分块。

纯函数：无 I/O、无全局状态、无外部依赖。

算法：
1. 扫描 break points：H1/H2/H3 标题、代码块 fence、分隔线、空行、换行，各有基础分。
2. 以字符位置前进，每步目标跳距 = (size - overlap) * 2（启发式 1 token ≈ 2 chars）。
3. 在 [target - window, target + window] 窗口内找最高分 break，应用平方距离衰减。
4. 代码块（``` ... ```）内部绝不切分。
5. 输出 Chunk(text, char_start, char_end)，满足 text == original[char_start:char_end]。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# =============================================================================
# 常量定义
# =============================================================================

CHUNK_SIZE_TOKENS = 900
CHUNK_OVERLAP_TOKENS = 135  # 15%
CHUNK_WINDOW_TOKENS = 200

_CHARS_PER_TOKEN = 2  # 中文保守估算


# =============================================================================
# 数据结构
# =============================================================================

@dataclass(frozen=True)
class Chunk:
    """单个 chunk。char_start 包含、char_end 不包含（Python slice 惯例）。"""
    text: str
    char_start: int
    char_end: int


@dataclass
class BreakPoint:
    """潜在的断点，带有基础分数"""
    pos: int       # 字符位置
    score: float   # 基础分数（越高越好）
    type: str      # 调试用：'h1', 'h2', 'blank' 等


@dataclass
class CodeFenceRegion:
    """代码块区域（``` 之间），绝不在内部切分"""
    start: int  # 开始位置
    end: int    # 结束位置（如果未闭合则为文档末尾）


# =============================================================================
# 断点模式
# =============================================================================

_BREAK_PATTERNS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\n#{1}(?!#)", re.MULTILINE), 100.0, "h1"),
    (re.compile(r"\n#{2}(?!#)", re.MULTILINE), 90.0, "h2"),
    (re.compile(r"\n#{3}(?!#)", re.MULTILINE), 80.0, "h3"),
    (re.compile(r"\n```", re.MULTILINE), 80.0, "fence"),
    (re.compile(r"\n(?:---|\*\*\*)\s*\n", re.MULTILINE), 60.0, "hr"),
    (re.compile(r"\n\n+", re.MULTILINE), 20.0, "blank"),
    (re.compile(r"\n", re.MULTILINE), 1.0, "newline"),
]

_FENCE_RE = re.compile(r"```", re.MULTILINE)


# =============================================================================
# 断点扫描与代码块检测
# =============================================================================

def _find_fence_ranges(text: str) -> list[tuple[int, int]]:
    """返回所有 ``` ... ``` 区间 [open_start, close_end)。未配对的 fence 视作直到文末。"""
    positions = [m.start() for m in _FENCE_RE.finditer(text)]
    ranges: list[tuple[int, int]] = []
    for i in range(0, len(positions), 2):
        start = positions[i]
        # close_end 指向关闭 fence 的 ``` 之后（含）
        close_pos = positions[i + 1] if i + 1 < len(positions) else None
        if close_pos is None:
            end = len(text)
        else:
            # 找到关闭 fence 行尾
            newline = text.find("\n", close_pos + 3)
            end = newline + 1 if newline != -1 else len(text)
        ranges.append((start, end))
    return ranges


def _in_fence(pos: int, ranges: list[tuple[int, int]]) -> bool:
    """检查位置是否在代码块区域内"""
    for a, b in ranges:
        if a < pos < b:
            return True
    return False


def _collect_breaks(text: str, fence_ranges: list[tuple[int, int]]) -> list[tuple[int, float]]:
    """扫描所有候选断点，过滤 fence 内部，返回 (pos, base_score) 升序列表。"""
    breaks: list[tuple[int, float]] = []
    for pattern, base, _kind in _BREAK_PATTERNS:
        for m in pattern.finditer(text):
            pos = m.start()
            if _in_fence(pos, fence_ranges):
                continue
            breaks.append((pos, base))
    dedup: dict[int, float] = {}
    for pos, sc in breaks:
        if sc > dedup.get(pos, -1.0):
            dedup[pos] = sc
    return sorted(dedup.items())


def _pick_cutoff(
    breaks: list[tuple[int, float]],
    target: int,
    window: int,
    cursor: int,
    fallback: int,
) -> int:
    """在 [target-window, target+window] 内找最高分断点，带平方距离衰减。都找不到用 fallback。"""
    lo, hi = target - window, target + window
    best_pos = fallback
    best_score = -1.0
    for pos, base in breaks:
        if pos <= cursor:
            continue
        if pos < lo or pos > hi:
            continue
        dist = abs(pos - target) / max(window, 1)
        score = base * (1.0 - dist * dist)
        if score > best_score:
            best_score = score
            best_pos = pos
    return best_pos


# =============================================================================
# 公开 API
# =============================================================================

def chunk_document(text: str, size: int = 512, overlap: int = 64) -> list[Chunk]:
    """按语义边界切分 markdown。

    参数：
        text: 原始 markdown 字符串。
        size: 目标 chunk 大小（单位：token）。
        overlap: chunk 之间的重叠（单位：token）。

    返回：Chunk 列表，text == original[char_start:char_end]。
    """
    if not text.strip():
        return []

    size_chars = size * _CHARS_PER_TOKEN
    _fallback_step_chars = max((size - overlap) * _CHARS_PER_TOKEN, 1)
    window_chars = size_chars

    total = len(text)
    if total <= size_chars:
        return [Chunk(text=text, char_start=0, char_end=total)]

    fence_ranges = _find_fence_ranges(text)
    breaks = _collect_breaks(text, fence_ranges)

    chunks: list[Chunk] = []
    cursor = 0
    while cursor < total:
        # 若 cursor 落在 fence 内，将其推到 fence 之后再继续
        for fa, fb in fence_ranges:
            if fa < cursor < fb:
                cursor = fb
                break

        if cursor >= total:
            break

        target = cursor + size_chars
        if target >= total:
            chunks.append(Chunk(text=text[cursor:total], char_start=cursor, char_end=total))
            break

        # 若整个目标区间都在 fence 内，把 cutoff 设为 fence 结束
        cutoff = _pick_cutoff(breaks, target, window_chars, cursor, fallback=target)
        if _in_fence(cutoff, fence_ranges):
            # 找到包含 cutoff 的 fence，跳到其结尾
            for fa, fb in fence_ranges:
                if fa < cutoff < fb:
                    cutoff = fb
                    break
            else:
                cutoff = target
        cutoff = min(max(cutoff, cursor + 1), total)
        chunks.append(Chunk(text=text[cursor:cutoff], char_start=cursor, char_end=cutoff))
        next_cursor = cutoff - overlap * _CHARS_PER_TOKEN
        if next_cursor <= cursor:
            next_cursor = cursor + _fallback_step_chars
        assert next_cursor > cursor, "liveness: cursor must advance"
        cursor = min(next_cursor, total)
    return chunks
