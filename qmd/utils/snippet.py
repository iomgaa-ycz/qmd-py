"""
文本摘要提取工具

从文档中提取标题和围绕关键词的上下文片段。
"""

import re

from loguru import logger


def extract_title(content: str, filename: str = "") -> str:
    """
    从文档内容中提取标题

    支持 Markdown 和 Org-mode 格式。
    如果没有找到标题，返回文件名（去除扩展名）。

    Args:
        content: 文档内容
        filename: 文件名（用作 fallback）

    Returns:
        提取的标题或文件名

    Examples:
        >>> extract_title("# My Title\\nContent...")
        "My Title"
        >>> extract_title("## Second Level\\nContent...")
        "Second Level"
        >>> extract_title("No title here", "document.md")
        "document"
    """
    ext = filename[filename.rfind("."):].lower() if "." in filename else ""

    # Markdown 标题提取
    if ext == ".md" or ext == "":
        match = re.search(r"^##?\s+(.+)$", content, re.MULTILINE)
        if match:
            title = match.group(1).strip()
            # 跳过通用的 "Notes" 标题
            if title and title not in ["📝 Notes", "Notes"]:
                return title

    # Org-mode 标题提取
    if ext == ".org":
        # 尝试匹配 #+TITLE: 属性
        title_prop = re.search(r"^#\+TITLE:\s*(.+)$", content, re.MULTILINE | re.IGNORECASE)
        if title_prop:
            return title_prop.group(1).strip()

        # 尝试匹配 org heading (* heading)
        heading = re.search(r"^\*+\s+(.+)$", content, re.MULTILINE)
        if heading:
            return heading.group(1).strip()

    # Fallback: 使用文件名（去除扩展名和路径）
    if filename:
        # 去除扩展名
        name_without_ext = re.sub(r"\.[^.]+$", "", filename)
        # 取最后一部分（去除路径）
        parts = name_without_ext.split("/")
        return parts[-1] if parts else filename

    return "Untitled"


def extract_snippet(
    content: str,
    query: str,
    max_chars: int = 200,
    chunk_pos: int | None = None,
    chunk_len: int | None = None
) -> dict[str, any]:
    """
    围绕查询关键词提取上下文片段

    找到包含最多查询词的行，并提取周围的上下文。
    返回带有 diff 风格头部的片段。

    Args:
        content: 文档内容
        query: 查询字符串（会被分词）
        max_chars: 片段最大字符数
        chunk_pos: 可选的块起始位置（字符偏移）
        chunk_len: 可选的块长度

    Returns:
        包含以下字段的字典:
        - line: 最佳匹配行号（1-indexed）
        - snippet: 带头部的片段文本
        - lines_before: 片段前的行数
        - lines_after: 片段后的行数
        - snippet_lines: 片段包含的行数

    Examples:
        >>> result = extract_snippet("Line 1\\nTarget line\\nLine 3", "target")
        >>> result["line"]
        2
        >>> "Target line" in result["snippet"]
        True
    """
    total_lines = content.count("\n") + 1
    search_body = content
    line_offset = 0

    # 如果提供了块位置，聚焦在该块及周围
    if chunk_pos is not None and chunk_pos > 0:
        max_chunk_len = 4000  # 默认最大块长度
        effective_chunk_len = chunk_len if chunk_len else max_chunk_len

        # 添加一些 padding 以获取上下文
        padding = 500
        start = max(0, chunk_pos - padding)
        end = min(len(content), chunk_pos + effective_chunk_len + padding)

        search_body = content[start:end]
        line_offset = content[:start].count("\n")

    lines = search_body.split("\n")

    # 分词查询字符串
    query_terms = [term.strip().lower() for term in query.split() if len(term.strip()) > 2]

    # 找到包含最多查询词的行
    best_line = 0
    best_score = 0

    for i, line in enumerate(lines):
        line_lower = line.lower()
        score = sum(1 for term in query_terms if term in line_lower)
        if score > best_score:
            best_score = score
            best_line = i

    # 提取周围上下文：前 1 行，后 3 行
    start = max(0, best_line - 1)
    end = min(len(lines), best_line + 4)  # +4 因为包括当前行
    snippet_lines = lines[start:end]
    snippet_text = "\n".join(snippet_lines)

    # 如果聚焦在块窗口且片段为空，回退到全文档
    if chunk_pos is not None and chunk_pos > 0 and not snippet_text.strip():
        return extract_snippet(content, query, max_chars, None, None)

    # 截断过长的片段
    if len(snippet_text) > max_chars:
        snippet_text = snippet_text[:max_chars - 3] + "..."

    # 计算绝对行号和统计信息
    absolute_start = line_offset + start + 1  # 1-indexed
    snippet_line_count = len(snippet_lines)
    lines_before = absolute_start - 1
    lines_after = total_lines - (absolute_start + snippet_line_count - 1)

    # 格式化为 diff 风格头部
    header = f"@@ -{absolute_start},{snippet_line_count} @@ ({lines_before} before, {lines_after} after)"
    snippet = f"{header}\n{snippet_text}"

    return {
        "line": line_offset + best_line + 1,  # 1-indexed
        "snippet": snippet,
        "lines_before": lines_before,
        "lines_after": lines_after,
        "snippet_lines": snippet_line_count,
    }
