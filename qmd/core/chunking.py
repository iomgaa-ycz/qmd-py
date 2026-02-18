"""
智能分块算法 (Smart Chunking)

基于语义边界的文档分块，使用平方距离衰减算法选择最佳切分点。
忠实移植自 qmd/src/store.ts
"""

import re
from dataclasses import dataclass
from typing import Protocol


# =============================================================================
# 常量定义
# =============================================================================

CHUNK_SIZE_TOKENS = 900
CHUNK_OVERLAP_TOKENS = 135  # 15%
CHUNK_WINDOW_TOKENS = 200

# 字符估算：1 token ≈ 4 chars (英文)
CHUNK_SIZE_CHARS = CHUNK_SIZE_TOKENS * 4
CHUNK_OVERLAP_CHARS = CHUNK_OVERLAP_TOKENS * 4
CHUNK_WINDOW_CHARS = CHUNK_WINDOW_TOKENS * 4


# =============================================================================
# 数据结构
# =============================================================================

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


@dataclass
class Chunk:
    """文档块"""
    text: str
    pos: int
    tokens: int | None = None


# =============================================================================
# 断点模式
# =============================================================================

# 断点检测模式：(正则, 分数, 类型)
# 分数越高表示越适合作为切分点
# 分数范围较大，确保标题能明显胜过低质量断点
BREAK_PATTERNS: list[tuple[str, float, str]] = [
    (r'\n#{1}(?!#)', 100, 'h1'),           # # 但不是 ##
    (r'\n#{2}(?!#)', 90, 'h2'),            # ## 但不是 ###
    (r'\n#{3}(?!#)', 80, 'h3'),            # ### 但不是 ####
    (r'\n#{4}(?!#)', 70, 'h4'),            # #### 但不是 #####
    (r'\n#{5}(?!#)', 60, 'h5'),            # ##### 但不是 ######
    (r'\n#{6}(?!#)', 50, 'h6'),            # ######
    (r'\n```', 80, 'codeblock'),           # 代码块边界（同 h3）
    (r'\n(?:---|\*\*\*|___)\s*\n', 60, 'hr'),  # 分隔线
    (r'\n\n+', 20, 'blank'),               # 段落边界
    (r'\n[-*]\s', 5, 'list'),              # 无序列表
    (r'\n\d+\.\s', 5, 'numlist'),          # 有序列表
    (r'\n', 1, 'newline'),                 # 最低分（换行）
]


# =============================================================================
# 断点扫描
# =============================================================================

def scan_break_points(text: str) -> list[BreakPoint]:
    """
    扫描文本中的所有潜在断点

    返回按位置排序的断点数组，当多个模式匹配同一位置时保留分数最高的
    """
    seen: dict[int, BreakPoint] = {}  # pos -> 该位置的最佳断点

    for pattern, score, type_ in BREAK_PATTERNS:
        regex = re.compile(pattern)
        for match in regex.finditer(text):
            pos = match.start()
            existing = seen.get(pos)
            # 如果位置已存在，保留分数更高的
            if existing is None or score > existing.score:
                seen[pos] = BreakPoint(pos=pos, score=score, type=type_)

    # 转换为列表并按位置排序
    points = list(seen.values())
    points.sort(key=lambda bp: bp.pos)
    return points


def find_code_fences(text: str) -> list[CodeFenceRegion]:
    """
    查找所有代码块区域

    代码块由 ``` 分隔，绝不在其内部切分
    """
    regions: list[CodeFenceRegion] = []
    fence_pattern = re.compile(r'\n```')
    in_fence = False
    fence_start = 0

    for match in fence_pattern.finditer(text):
        if not in_fence:
            fence_start = match.start()
            in_fence = True
        else:
            regions.append(CodeFenceRegion(start=fence_start, end=match.start()))
            in_fence = False

    # 处理未闭合的代码块——延伸到文档末尾
    if in_fence:
        regions.append(CodeFenceRegion(start=fence_start, end=len(text)))

    return regions


def is_inside_code_fence(pos: int, fences: list[CodeFenceRegion]) -> bool:
    """检查位置是否在代码块区域内"""
    return any(fence.start < pos < fence.end for fence in fences)


# =============================================================================
# 最佳切分点查找
# =============================================================================

def find_best_cutoff(
    break_points: list[BreakPoint],
    target_char_pos: int,
    window_chars: int = CHUNK_WINDOW_CHARS,
    decay_factor: float = 0.7,
    code_fences: list[CodeFenceRegion] | None = None
) -> int:
    """
    使用平方距离衰减查找最佳切分位置

    平方距离提供更温和的早期衰减——远处的标题仍能胜过附近的低质量断点

    Args:
        break_points: 预扫描的断点（来自 scan_break_points）
        target_char_pos: 理想切分位置（例如 maxChars 边界）
        window_chars: 向后搜索的距离（默认 ~200 tokens）
        decay_factor: 距离惩罚系数（0.7 = 窗口边缘保留 30% 分数）
        code_fences: 代码块区域（避免在内部切分）

    Returns:
        最佳切分位置
    """
    if code_fences is None:
        code_fences = []

    window_start = target_char_pos - window_chars
    best_score = -1.0
    best_pos = target_char_pos

    for bp in break_points:
        if bp.pos < window_start:
            continue
        if bp.pos > target_char_pos:
            break  # 已排序，可以停止

        # 跳过代码块内的断点
        if is_inside_code_fence(bp.pos, code_fences):
            continue

        # 平方距离衰减：早期温和，后期陡峭
        # 在目标位置：multiplier = 1.0
        # 回退 25%：multiplier = 0.956
        # 回退 50%：multiplier = 0.825
        # 回退 75%：multiplier = 0.606
        # 窗口边缘：multiplier = 0.3
        distance = target_char_pos - bp.pos
        normalized_dist = distance / window_chars
        multiplier = 1.0 - (normalized_dist ** 2) * decay_factor
        final_score = bp.score * multiplier

        if final_score > best_score:
            best_score = final_score
            best_pos = bp.pos

    return best_pos


# =============================================================================
# 文档分块
# =============================================================================

def chunk_document(
    content: str,
    max_chars: int = CHUNK_SIZE_CHARS,
    overlap_chars: int = CHUNK_OVERLAP_CHARS,
    window_chars: int = CHUNK_WINDOW_CHARS
) -> list[Chunk]:
    """
    按智能边界切分文档（基于字符）

    Args:
        content: 文档内容
        max_chars: 每块最大字符数
        overlap_chars: 块间重叠字符数
        window_chars: 断点搜索窗口大小

    Returns:
        文档块列表
    """
    # 空内容检查
    if not content or not content.strip():
        return []

    if len(content) <= max_chars:
        return [Chunk(text=content, pos=0)]

    # 预扫描所有断点和代码块
    break_points = scan_break_points(content)
    code_fences = find_code_fences(content)

    chunks: list[Chunk] = []
    char_pos = 0

    while char_pos < len(content):
        # 计算此块的目标结束位置
        target_end_pos = min(char_pos + max_chars, len(content))
        end_pos = target_end_pos

        # 如果不在末尾，查找最佳断点
        if end_pos < len(content):
            best_cutoff = find_best_cutoff(
                break_points,
                target_end_pos,
                window_chars,
                0.7,
                code_fences
            )

            # 仅在切分点在当前块内时使用
            if char_pos < best_cutoff <= target_end_pos:
                end_pos = best_cutoff

        # 确保前进
        if end_pos <= char_pos:
            end_pos = min(char_pos + max_chars, len(content))

        chunks.append(Chunk(text=content[char_pos:end_pos], pos=char_pos))

        # 向前移动，但与前一块重叠
        # 对于最后一块，不重叠（直接到末尾）
        if end_pos >= len(content):
            break

        char_pos = end_pos - overlap_chars
        last_chunk_pos = chunks[-1].pos
        if char_pos <= last_chunk_pos:
            # 防止无限循环——至少前进一点
            char_pos = end_pos

    return chunks


# =============================================================================
# 基于 Token 的分块（需要 tokenizer）
# =============================================================================

class Tokenizer(Protocol):
    """Tokenizer 接口"""
    def tokenize(self, text: str) -> list[int]:
        """将文本转换为 token ID 列表"""
        ...


def chunk_document_by_tokens(
    content: str,
    tokenizer: Tokenizer | None = None,
    max_tokens: int = CHUNK_SIZE_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
    window_tokens: int = CHUNK_WINDOW_TOKENS
) -> list[Chunk]:
    """
    按实际 token 数切分文档

    比基于字符的切分更准确，但需要 tokenizer

    Args:
        content: 文档内容
        tokenizer: Tokenizer 实例（如果为 None，使用简化估算）
        max_tokens: 每块最大 token 数
        overlap_tokens: 块间重叠 token 数
        window_tokens: 断点搜索窗口大小（token）

    Returns:
        文档块列表（包含 token 计数）
    """
    # 中文 token 估算：1 char ≈ 2 tokens（中文字符较密集）
    # 英文 token 估算：1 token ≈ 4 chars（与原版 qmd 一致）
    # 混合文本使用中间值：1 token ≈ 2 chars
    avg_chars_per_token = 2
    max_chars = max_tokens * avg_chars_per_token
    overlap_chars = overlap_tokens * avg_chars_per_token
    window_chars = window_tokens * avg_chars_per_token

    # 基于字符的保守估算进行切分
    char_chunks = chunk_document(content, max_chars, overlap_chars, window_chars)

    # 如果没有 tokenizer，返回估算的块
    if tokenizer is None:
        return [
            Chunk(
                text=chunk.text,
                pos=chunk.pos,
                tokens=len(chunk.text) // avg_chars_per_token
            )
            for chunk in char_chunks
        ]

    # 使用 tokenizer 验证并重新切分超限的块
    results: list[Chunk] = []

    for chunk in char_chunks:
        tokens = tokenizer.tokenize(chunk.text)

        if len(tokens) <= max_tokens:
            results.append(
                Chunk(text=chunk.text, pos=chunk.pos, tokens=len(tokens))
            )
        else:
            # 块仍然过大——进一步切分
            # 使用实际 token 数估算更好的字符限制
            actual_chars_per_token = len(chunk.text) / len(tokens)
            safe_max_chars = int(max_tokens * actual_chars_per_token * 0.95)  # 5% 安全边界

            sub_chunks = chunk_document(
                chunk.text,
                safe_max_chars,
                int(overlap_chars * actual_chars_per_token / 2),
                int(window_chars * actual_chars_per_token / 2)
            )

            for sub_chunk in sub_chunks:
                sub_tokens = tokenizer.tokenize(sub_chunk.text)
                results.append(
                    Chunk(
                        text=sub_chunk.text,
                        pos=chunk.pos + sub_chunk.pos,
                        tokens=len(sub_tokens)
                    )
                )

    return results
