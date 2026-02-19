"""
输出格式化

提供将搜索结果和文档格式化为各种输出格式的方法：
JSON、CSV、XML、Markdown、files 列表和 CLI（彩色终端输出）。
"""

from __future__ import annotations

import json
from typing import Any, Literal, TypedDict

from qmd.utils.snippet import extract_snippet

# =============================================================================
# 类型定义
# =============================================================================

OutputFormat = Literal["cli", "csv", "md", "xml", "files", "json"]


class FormatOptions(TypedDict, total=False):
    """格式化选项"""

    full: bool  # 显示完整文档内容而非摘要
    query: str  # 用于摘要提取和高亮的查询
    use_color: bool  # 启用终端颜色（默认：非 CLI 模式为 False）
    line_numbers: bool  # 添加行号


# =============================================================================
# 辅助函数
# =============================================================================


def add_line_numbers(text: str, start_line: int = 1) -> str:
    """
    为文本内容添加行号

    每行变为: "{lineNum}: {content}"

    Args:
        text: 要添加行号的文本
        start_line: 起始行号（默认：1）

    Returns:
        带行号的文本
    """
    lines = text.split("\n")
    return "\n".join(f"{start_line + i}: {line}" for i, line in enumerate(lines))


def get_docid(hash_value: str) -> str:
    """从完整哈希中提取短 docid（前 6 个字符）"""
    return hash_value[:6]


def escape_csv(value: str | None | int | float) -> str:
    """
    转义 CSV 字段值

    Args:
        value: 要转义的值

    Returns:
        转义后的字符串
    """
    if value is None:
        return ""
    str_value = str(value)
    if "," in str_value or '"' in str_value or "\n" in str_value:
        escaped = str_value.replace('"', '""')
        return f'"{escaped}"'
    return str_value


def escape_xml(text: str) -> str:
    """
    转义 XML 特殊字符

    Args:
        text: 要转义的文本

    Returns:
        转义后的文本
    """
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


# =============================================================================
# 搜索结果格式化器
# =============================================================================


def search_results_to_json(
    results: list[dict[str, Any]], opts: FormatOptions | None = None
) -> str:
    """
    将搜索结果格式化为 JSON

    Args:
        results: 搜索结果列表
        opts: 格式化选项

    Returns:
        JSON 字符串
    """
    if opts is None:
        opts = {}

    query = opts.get("query", "")
    output = []

    for row in results:
        body_str = row.get("body", "")
        docid = get_docid(row["hash"])
        chunk_pos = row.get("pos", 0)

        # 根据 full 选项决定输出内容
        if opts.get("full"):
            body = body_str
            snippet = None
        else:
            body = None
            snippet_result = extract_snippet(body_str, query, 300, chunk_pos)
            snippet = snippet_result["snippet"]

        # 添加行号（如果需要）
        if opts.get("line_numbers"):
            if body:
                body = add_line_numbers(body)
            if snippet:
                snippet = add_line_numbers(snippet)

        result = {
            "docid": f"#{docid}",
            "score": round(row["score"], 2),
            "file": row["file"],
            "title": row["title"],
        }

        # 添加可选字段
        if row.get("context"):
            result["context"] = row["context"]
        if body:
            result["body"] = body
        if snippet:
            result["snippet"] = snippet

        output.append(result)

    return json.dumps(output, indent=2, ensure_ascii=False)


def search_results_to_csv(
    results: list[dict[str, Any]], opts: FormatOptions | None = None
) -> str:
    """
    将搜索结果格式化为 CSV

    Args:
        results: 搜索结果列表
        opts: 格式化选项

    Returns:
        CSV 字符串
    """
    if opts is None:
        opts = {}

    query = opts.get("query", "")
    header = "docid,score,file,title,context,line,snippet"
    rows = []

    for row in results:
        body_str = row.get("body", "")
        docid = get_docid(row["hash"])
        chunk_pos = row.get("pos", 0)

        snippet_result = extract_snippet(body_str, query, 500, chunk_pos)
        line = snippet_result["line"]
        snippet = snippet_result["snippet"]

        # 如果 full=True，使用完整内容
        if opts.get("full"):
            content = body_str
        else:
            content = snippet

        # 添加行号（如果需要）
        if opts.get("line_numbers") and content:
            content = add_line_numbers(content)

        csv_row = ",".join(
            [
                f"#{docid}",
                f"{row['score']:.4f}",
                escape_csv(row["file"]),
                escape_csv(row["title"]),
                escape_csv(row.get("context", "")),
                str(line),
                escape_csv(content),
            ]
        )
        rows.append(csv_row)

    return "\n".join([header] + rows)


def search_results_to_files(results: list[dict[str, Any]]) -> str:
    """
    将搜索结果格式化为简单文件列表（docid,score,filepath,context）

    Args:
        results: 搜索结果列表

    Returns:
        简单文件列表字符串
    """
    lines = []
    for row in results:
        docid = get_docid(row["hash"])
        ctx = ""
        if row.get("context"):
            # 转义双引号
            escaped_ctx = row["context"].replace('"', '""')
            ctx = f',"{escaped_ctx}"'
        lines.append(f"#{docid},{row['score']:.2f},{row['file']}{ctx}")
    return "\n".join(lines)


def search_results_to_markdown(
    results: list[dict[str, Any]], opts: FormatOptions | None = None
) -> str:
    """
    将搜索结果格式化为 Markdown

    Args:
        results: 搜索结果列表
        opts: 格式化选项

    Returns:
        Markdown 字符串
    """
    if opts is None:
        opts = {}

    query = opts.get("query", "")
    output = []

    for row in results:
        heading = row["title"] or row["file"]
        body_str = row.get("body", "")
        docid = get_docid(row["hash"])
        chunk_pos = row.get("pos", 0)

        # 根据 full 选项决定输出内容
        if opts.get("full"):
            content = body_str
        else:
            snippet_result = extract_snippet(body_str, query, 500, chunk_pos)
            content = snippet_result["snippet"]

        # 添加行号（如果需要）
        if opts.get("line_numbers"):
            content = add_line_numbers(content)

        # 构建 Markdown
        md = f"---\n# {heading}\n\n"
        md += f"**docid:** `#{docid}`\n"
        if row.get("context"):
            md += f"**context:** {row['context']}\n"
        md += f"\n{content}\n"

        output.append(md)

    return "\n".join(output)


def search_results_to_xml(
    results: list[dict[str, Any]], opts: FormatOptions | None = None
) -> str:
    """
    将搜索结果格式化为 XML

    Args:
        results: 搜索结果列表
        opts: 格式化选项

    Returns:
        XML 字符串
    """
    if opts is None:
        opts = {}

    query = opts.get("query", "")
    items = []

    for row in results:
        title_attr = f' title="{escape_xml(row["title"])}"' if row["title"] else ""
        body_str = row.get("body", "")
        docid = get_docid(row["hash"])
        chunk_pos = row.get("pos", 0)

        # 根据 full 选项决定输出内容
        if opts.get("full"):
            content = body_str
        else:
            snippet_result = extract_snippet(body_str, query, 500, chunk_pos)
            content = snippet_result["snippet"]

        # 添加行号（如果需要）
        if opts.get("line_numbers"):
            content = add_line_numbers(content)

        context_attr = ""
        if row.get("context"):
            context_attr = f' context="{escape_xml(row["context"])}"'

        xml = (
            f'<file docid="#{docid}" name="{escape_xml(row["file"])}"{title_attr}{context_attr}>\n'
            f"{escape_xml(content)}\n"
            "</file>"
        )
        items.append(xml)

    return "\n\n".join(items)


def search_results_to_mcp_csv(
    results: list[dict[str, Any]]
) -> str:
    """
    将搜索结果格式化为 MCP CSV 格式（简化的 CSV，带预提取摘要）

    Args:
        results: 搜索结果列表（包含预提取的 snippet）

    Returns:
        CSV 字符串
    """
    header = "docid,file,title,score,context,snippet"
    rows = []

    for r in results:
        docid = r.get("docid", "")
        if not docid.startswith("#"):
            docid = f"#{docid}"

        row_data = [
            docid,
            r.get("file", ""),
            r.get("title", ""),
            str(r.get("score", 0)),
            r.get("context", ""),
            r.get("snippet", ""),
        ]
        csv_row = ",".join(escape_csv(field) for field in row_data)
        rows.append(csv_row)

    return "\n".join([header] + rows)


# =============================================================================
# 文档格式化器（用于 multi-get，使用 MultiGetFile）
# =============================================================================


def documents_to_json(results: list[dict[str, Any]]) -> str:
    """
    将文档格式化为 JSON

    Args:
        results: 文档结果列表

    Returns:
        JSON 字符串
    """
    output = []
    for r in results:
        doc = {
            "file": r["displayPath"],
            "title": r["title"],
        }
        if r.get("context"):
            doc["context"] = r["context"]
        if r.get("skipped"):
            doc["skipped"] = True
            doc["reason"] = r.get("skipReason", "")
        else:
            doc["body"] = r.get("body", "")
        output.append(doc)

    return json.dumps(output, indent=2, ensure_ascii=False)


def documents_to_csv(results: list[dict[str, Any]]) -> str:
    """
    将文档格式化为 CSV

    Args:
        results: 文档结果列表

    Returns:
        CSV 字符串
    """
    header = "file,title,context,skipped,body"
    rows = []

    for r in results:
        row_data = [
            r["displayPath"],
            r["title"],
            r.get("context", ""),
            "true" if r.get("skipped") else "false",
            r.get("skipReason", "") if r.get("skipped") else r.get("body", ""),
        ]
        csv_row = ",".join(escape_csv(field) for field in row_data)
        rows.append(csv_row)

    return "\n".join([header] + rows)


def documents_to_files(results: list[dict[str, Any]]) -> str:
    """
    将文档格式化为文件列表

    Args:
        results: 文档结果列表

    Returns:
        文件列表字符串
    """
    lines = []
    for r in results:
        ctx = ""
        if r.get("context"):
            escaped_ctx = r["context"].replace('"', '""')
            ctx = f',"{escaped_ctx}"'
        status = ",[SKIPPED]" if r.get("skipped") else ""
        lines.append(f"{r['displayPath']}{ctx}{status}")
    return "\n".join(lines)


def documents_to_markdown(results: list[dict[str, Any]]) -> str:
    """
    将文档格式化为 Markdown

    Args:
        results: 文档结果列表

    Returns:
        Markdown 字符串
    """
    output = []
    for r in results:
        md = f"## {r['displayPath']}\n\n"
        if r["title"] and r["title"] != r["displayPath"]:
            md += f"**Title:** {r['title']}\n\n"
        if r.get("context"):
            md += f"**Context:** {r['context']}\n\n"
        if r.get("skipped"):
            md += f"> {r.get('skipReason', '')}\n"
        else:
            md += "```\n" + r.get("body", "") + "\n```\n"
        output.append(md)

    return "\n".join(output)


def documents_to_xml(results: list[dict[str, Any]]) -> str:
    """
    将文档格式化为 XML

    Args:
        results: 文档结果列表

    Returns:
        XML 字符串
    """
    items = []
    for r in results:
        xml = "  <document>\n"
        xml += f"    <file>{escape_xml(r['displayPath'])}</file>\n"
        xml += f"    <title>{escape_xml(r['title'])}</title>\n"
        if r.get("context"):
            xml += f"    <context>{escape_xml(r['context'])}</context>\n"
        if r.get("skipped"):
            xml += "    <skipped>true</skipped>\n"
            xml += f"    <reason>{escape_xml(r.get('skipReason', ''))}</reason>\n"
        else:
            xml += f"    <body>{escape_xml(r.get('body', ''))}</body>\n"
        xml += "  </document>"
        items.append(xml)

    return '<?xml version="1.0" encoding="UTF-8"?>\n<documents>\n' + "\n".join(items) + "\n</documents>"


# =============================================================================
# 单文档格式化器
# =============================================================================


def document_to_json(doc: dict[str, Any]) -> str:
    """
    将单个文档结果格式化为 JSON

    Args:
        doc: 文档结果

    Returns:
        JSON 字符串
    """
    output = {
        "file": doc["displayPath"],
        "title": doc["title"],
    }
    if doc.get("context"):
        output["context"] = doc["context"]
    output["hash"] = doc["hash"]
    output["modifiedAt"] = doc["modifiedAt"]
    output["bodyLength"] = doc["bodyLength"]
    if "body" in doc:
        output["body"] = doc["body"]

    return json.dumps(output, indent=2, ensure_ascii=False)


def document_to_markdown(doc: dict[str, Any]) -> str:
    """
    将单个文档结果格式化为 Markdown

    Args:
        doc: 文档结果

    Returns:
        Markdown 字符串
    """
    md = f"# {doc['title'] or doc['displayPath']}\n\n"
    if doc.get("context"):
        md += f"**Context:** {doc['context']}\n\n"
    md += f"**File:** {doc['displayPath']}\n"
    md += f"**Modified:** {doc['modifiedAt']}\n\n"
    if "body" in doc:
        md += "---\n\n" + doc["body"] + "\n"
    return md


def document_to_xml(doc: dict[str, Any]) -> str:
    """
    将单个文档结果格式化为 XML

    Args:
        doc: 文档结果

    Returns:
        XML 字符串
    """
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<document>\n'
    xml += f"  <file>{escape_xml(doc['displayPath'])}</file>\n"
    xml += f"  <title>{escape_xml(doc['title'])}</title>\n"
    if doc.get("context"):
        xml += f"  <context>{escape_xml(doc['context'])}</context>\n"
    xml += f"  <hash>{escape_xml(doc['hash'])}</hash>\n"
    xml += f"  <modifiedAt>{escape_xml(doc['modifiedAt'])}</modifiedAt>\n"
    xml += f"  <bodyLength>{doc['bodyLength']}</bodyLength>\n"
    if "body" in doc:
        xml += f"  <body>{escape_xml(doc['body'])}</body>\n"
    xml += "</document>"
    return xml


# =============================================================================
# 主入口函数
# =============================================================================


def format_search_results(
    results: list[dict[str, Any]],
    output_format: OutputFormat = "json",
    opts: FormatOptions | None = None,
) -> str:
    """
    格式化搜索结果（统一入口）

    Args:
        results: 搜索结果列表
        output_format: 输出格式
        opts: 格式化选项

    Returns:
        格式化后的字符串
    """
    if output_format == "json":
        return search_results_to_json(results, opts)
    elif output_format == "csv":
        return search_results_to_csv(results, opts)
    elif output_format == "xml":
        return search_results_to_xml(results, opts)
    elif output_format == "md":
        return search_results_to_markdown(results, opts)
    elif output_format == "files":
        return search_results_to_files(results)
    else:
        # 默认返回 JSON
        return search_results_to_json(results, opts)


def format_documents(
    results: list[dict[str, Any]], output_format: OutputFormat = "json"
) -> str:
    """
    格式化文档列表（用于 multi-get）

    Args:
        results: 文档结果列表
        output_format: 输出格式

    Returns:
        格式化后的字符串
    """
    if output_format == "json":
        return documents_to_json(results)
    elif output_format == "csv":
        return documents_to_csv(results)
    elif output_format == "xml":
        return documents_to_xml(results)
    elif output_format == "md":
        return documents_to_markdown(results)
    elif output_format == "files":
        return documents_to_files(results)
    else:
        # 默认返回 JSON
        return documents_to_json(results)
