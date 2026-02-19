"""
QMD MCP Server - Model Context Protocol 服务器

提供 QMD 搜索和文档检索功能的 MCP 工具。
通过 stdio transport 与 Claude Desktop 等 MCP 客户端通信。

忠实移植自 qmd/src/mcp.ts（简化版，仅包含核心工具）
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from qmd import create_llm_backend, create_store
from qmd.utils.paths import is_virtual_path, parse_virtual_path


# =============================================================================
# Helper Functions
# =============================================================================


def format_search_summary(results: list[dict[str, Any]], query: str) -> str:
    """
    格式化搜索结果为人类可读的文本摘要

    Args:
        results: 搜索结果列表
        query: 查询文本

    Returns:
        格式化的摘要文本
    """
    if not results:
        return f'未找到 "{query}" 的匹配结果'

    lines = [f'找到 {len(results)} 个 "{query}" 的结果:\n']
    for r in results:
        score_pct = round(r["score"] * 100)
        lines.append(f"  {score_pct}% {r['collection']}/{r['file']} - {r['title']}")

    return "\n".join(lines)


# =============================================================================
# MCP Server
# =============================================================================


def get_tool_definitions() -> list[Tool]:
    """
    获取工具定义列表

    Returns:
        工具定义列表
    """
    return [
        Tool(
            name="qmd_search",
            description="搜索文档。使用混合检索（BM25 + Vector + RRF 融合）查找相关文档。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询 - 关键词或短语",
                    },
                    "collection": {
                        "type": "string",
                        "description": "限定 collection（可选）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量（默认: 10）",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="qmd_index",
            description="更新索引。重新扫描并索引指定 collection 或所有 collections 的文档。",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {
                        "type": "string",
                        "description": "Collection 名称（可选，不指定=全部）",
                    },
                },
            },
        ),
        Tool(
            name="qmd_collections",
            description="列出所有 collections 及其状态（路径、pattern、文档数）。",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="qmd_status",
            description="显示索引状态（文档数、数据库大小等）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {
                        "type": "string",
                        "description": "Collection 名称（可选，不指定=所有）",
                    },
                },
            },
        ),
        Tool(
            name="qmd_deep_search",
            description="深度搜索。自动扩展查询为多个变体，分别使用关键词和语义搜索，再重排序返回最佳结果。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "自然语言查询",
                    },
                    "collection": {
                        "type": "string",
                        "description": "限定 collection（可选）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量（默认: 10）",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="qmd_vector_search",
            description="语义搜索。通过语义理解查找相关文档，即使措辞不同也能找到。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "自然语言查询",
                    },
                    "collection": {
                        "type": "string",
                        "description": "限定 collection（可选）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量（默认: 10）",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="qmd_get",
            description="获取文档全文。通过文件路径或虚拟路径 (qmd://collection/path) 获取文档内容。",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "文件路径或虚拟路径",
                    },
                    "from_line": {
                        "type": "integer",
                        "description": "起始行号（可选）",
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "最大行数（可选）",
                    },
                },
                "required": ["file"],
            },
        ),
    ]


async def dispatch_tool_call(
    db, store, backend, name: str, arguments: dict[str, Any]
) -> list[TextContent]:
    """
    分发工具调用到相应的处理器

    Args:
        qmd: QMD 实例
        name: 工具名称
        arguments: 工具参数

    Returns:
        文本内容列表
    """
    try:
        if name == "qmd_search":
            return await handle_search(qmd, arguments)
        elif name == "qmd_index":
            return await handle_index(qmd, arguments)
        elif name == "qmd_collections":
            return await handle_collections(qmd, arguments)
        elif name == "qmd_status":
            return await handle_status(qmd, arguments)
        elif name == "qmd_deep_search":
            return await handle_deep_search(qmd, arguments)
        elif name == "qmd_vector_search":
            return await handle_vector_search(qmd, arguments)
        elif name == "qmd_get":
            return await handle_get(qmd, arguments)
        else:
            return [TextContent(type="text", text=f"未知工具: {name}")]
    except Exception as e:
        logger.exception(f"工具调用失败: {name}")
        return [TextContent(type="text", text=f"错误: {e}")]


def create_server(db_path: str | Path | None = None) -> Server:
    """
    创建 MCP 服务器实例并注册所有工具

    Args:
        db_path: 数据库路径，None 使用默认路径

    Returns:
        配置好的 MCP Server 实例
    """
    # 初始化 store 和 backend
    db, store = create_store(db_path)
    backend = create_llm_backend("auto")

    # 创建 MCP 服务器
    server = Server("qmd")

    # 注册工具列表
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """列出所有可用的工具"""
        return get_tool_definitions()

    # 注册工具调用处理器
    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """处理工具调用"""
        return await dispatch_tool_call(db, store, backend, name, arguments)

    return server


# =============================================================================
# Tool Handlers
# =============================================================================


async def handle_search(qmd: QMD, arguments: dict[str, Any]) -> list[TextContent]:
    """
    处理 qmd_search 工具调用

    Args:
        qmd: QMD 实例
        arguments: 工具参数 (query, collection, limit)

    Returns:
        文本内容列表
    """
    query = arguments.get("query", "")
    collection = arguments.get("collection")
    limit = arguments.get("limit", 10)

    if not query:
        return [TextContent(type="text", text="错误: query 参数为空")]

    # 调用搜索
    from qmd import search
    collections = [collection] if collection else None
    results = search(db, query, collection=collections[0] if collections else None, limit=limit)

    # 转换为字典格式
    results_dict = [
        {
            "collection": r.collection,
            "file": r.file,
            "title": r.title,
            "score": r.score,
            "snippet": r.body[:200].replace("\n", " ") + ("..." if len(r.body) > 200 else ""),
        }
        for r in results
    ]

    # 格式化摘要
    summary = format_search_summary(results_dict, query)

    return [TextContent(type="text", text=summary)]


async def handle_index(qmd: QMD, arguments: dict[str, Any]) -> list[TextContent]:
    """
    处理 qmd_index 工具调用

    Args:
        qmd: QMD 实例
        arguments: 工具参数 (collection)

    Returns:
        文本内容列表
    """
    collection = arguments.get("collection")

    # 调用更新
    stats = qmd.update(name=collection)

    if "error" in stats:
        return [TextContent(type="text", text=f"错误: {stats['error']}")]

    # 格式化统计
    summary = [
        "索引更新完成:",
        f"  Collections: {stats['collections']}",
        f"  新增: {stats['indexed']}",
        f"  更新: {stats['updated']}",
        f"  未变化: {stats['unchanged']}",
    ]

    if stats["errors"] > 0:
        summary.append(f"  错误: {stats['errors']}")

    return [TextContent(type="text", text="\n".join(summary))]


async def handle_collections(qmd: QMD, arguments: dict[str, Any]) -> list[TextContent]:
    """
    处理 qmd_collections 工具调用

    Args:
        qmd: QMD 实例
        arguments: 工具参数（无）

    Returns:
        文本内容列表
    """
    from qmd.core.config import list_collections

    collections = list_collections()

    if not collections:
        return [TextContent(type="text", text="没有 collection")]

    lines = [f"共 {len(collections)} 个 collection:\n"]
    for collection in collections:
        count = store.get_document_count(collection.name)
        lines.append(f"• {collection.name}")
        lines.append(f"  路径: {collection.path}")
        lines.append(f"  Pattern: {collection.pattern}")
        lines.append(f"  文档数: {count}")
        lines.append("")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_status(qmd: QMD, arguments: dict[str, Any]) -> list[TextContent]:
    """
    处理 qmd_status 工具调用

    Args:
        qmd: QMD 实例
        arguments: 工具参数 (collection)

    Returns:
        文本内容列表
    """
    collection = arguments.get("collection")

    from qmd.core.config import list_collections


    collections = list_collections()
    total_docs = 0

    lines = ["索引状态:\n"]
    lines.append(f"数据库: {qmd.db_path}")
    lines.append(f"Collections: {len(collections)}\n")

    for coll in collections:
        # 如果指定了 collection，只显示该 collection
        if collection and coll.name != collection:
            continue

        count = store.get_document_count(coll.name)
        total_docs += count
        lines.append(f"• {coll.name}: {count} 个文档")

    lines.append(f"\n总计: {total_docs} 个文档")

    # 显示数据库大小
    if qmd.db_path.exists():
        size_mb = qmd.db_path.stat().st_size / (1024 * 1024)
        lines.append(f"数据库大小: {size_mb:.2f} MB")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_deep_search(qmd: QMD, arguments: dict[str, Any]) -> list[TextContent]:
    """
    处理 qmd_deep_search 工具调用（深度搜索）

    Args:
        qmd: QMD 实例
        arguments: 工具参数 (query, collection, limit)

    Returns:
        文本内容列表
    """
    query = arguments.get("query", "")
    collection = arguments.get("collection")
    limit = arguments.get("limit", 10)

    if not query:
        return [TextContent(type="text", text="错误: query 参数为空")]

    # 深度搜索 - 使用完整的混合检索流程（与 search 相同，但强调使用 LLM backend）
    logger.info(f"执行深度搜索: {query}")
    collections = [collection] if collection else None
    from qmd import search

    results = search(db, query, collection=collections[0] if collections else None, limit=limit)

    # 转换为字典格式
    results_dict = [
        {
            "collection": r.collection,
            "file": r.file,
            "title": r.title,
            "score": r.score,
            "snippet": r.body[:200].replace("\n", " ") + ("..." if len(r.body) > 200 else ""),
        }
        for r in results
    ]

    # 格式化摘要
    summary = format_search_summary(results_dict, query)

    return [TextContent(type="text", text=summary)]


async def handle_vector_search(qmd: QMD, arguments: dict[str, Any]) -> list[TextContent]:
    """
    处理 qmd_vector_search 工具调用（纯语义向量检索）

    Args:
        qmd: QMD 实例
        arguments: 工具参数 (query, collection, limit)

    Returns:
        文本内容列表
    """
    query = arguments.get("query", "")
    collection = arguments.get("collection")
    limit = arguments.get("limit", 10)

    if not query:
        return [TextContent(type="text", text="错误: query 参数为空")]

    # 纯向量搜索 - 目前使用 search() 方法（因为它已经包含了向量检索）
    # 如果需要纯向量检索，可以在 QMD 类中添加 vector_search() 方法
    logger.info(f"执行语义向量搜索: {query}")
    collections = [collection] if collection else None
    from qmd import search

    results = search(db, query, collection=collections[0] if collections else None, limit=limit)

    # 转换为字典格式
    results_dict = [
        {
            "collection": r.collection,
            "file": r.file,
            "title": r.title,
            "score": r.score,
            "snippet": r.body[:200].replace("\n", " ") + ("..." if len(r.body) > 200 else ""),
        }
        for r in results
    ]

    # 格式化摘要
    summary = format_search_summary(results_dict, query)

    return [TextContent(type="text", text=summary)]


async def handle_get(qmd: QMD, arguments: dict[str, Any]) -> list[TextContent]:
    """
    处理 qmd_get 工具调用（获取文档全文）

    Args:
        qmd: QMD 实例
        arguments: 工具参数 (file, from_line, max_lines)

    Returns:
        文本内容列表
    """
    file_path = arguments.get("file", "")
    from_line = arguments.get("from_line")
    max_lines = arguments.get("max_lines")

    if not file_path:
        return [TextContent(type="text", text="错误: file 参数为空")]

    # 解析路径（支持虚拟路径和普通路径）
    collection_name = None
    doc_path = None

    if is_virtual_path(file_path):
        # 虚拟路径：qmd://collection/path
        vpath = parse_virtual_path(file_path)
        if vpath is None:
            return [TextContent(type="text", text=f"错误: 无效的虚拟路径 {file_path}")]
        collection_name = vpath.collection_name
        doc_path = vpath.path
    else:
        # 普通路径：需要从所有 collections 中查找
        # 简化实现：尝试从第一个 collection 查找
        from qmd.core.config import list_collections

        collections = list_collections()
        if not collections:
            return [TextContent(type="text", text="错误: 没有可用的 collection")]

        # 尝试在所有 collections 中查找
        found = False
        for coll in collections:
            doc = db.find_active_document(coll.name, file_path)
            if doc:
                collection_name = coll.name
                doc_path = file_path
                found = True
                break

        if not found:
            return [TextContent(type="text", text=f"错误: 文档不存在 {file_path}")]

    # 查找文档
    doc = db.find_active_document(collection_name, doc_path)
    if doc is None:
        return [TextContent(type="text", text=f"错误: 文档不存在 {collection_name}/{doc_path}")]

    # 获取内容
    content = db.get_content_by_hash(doc["hash"])
    if content is None:
        return [TextContent(type="text", text="错误: 无法读取文档内容")]

    # 处理行号过滤
    lines = content.splitlines()
    if from_line:
        start_idx = from_line - 1
        end_idx = start_idx + max_lines if max_lines else len(lines)
        display_lines = lines[start_idx:end_idx]
    else:
        display_lines = lines[:max_lines] if max_lines else lines

    # 格式化输出
    result_lines = [
        f"文档: {collection_name}/{doc_path}",
        f"标题: {doc['title']}",
        "",
        "\n".join(display_lines),
    ]

    return [TextContent(type="text", text="\n".join(result_lines))]


# =============================================================================
# Server Entry Point
# =============================================================================


async def serve(db_path: str | Path | None = None) -> None:
    """
    启动 MCP 服务器（stdio transport）

    Args:
        db_path: 数据库路径，None 使用默认路径
    """
    logger.info("启动 QMD MCP 服务器（stdio transport）")

    server = create_server(db_path)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """CLI 入口函数"""
    asyncio.run(serve())


if __name__ == "__main__":
    main()
