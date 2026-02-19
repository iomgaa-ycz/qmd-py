"""
qmd-py CLI 工具

提供完整的命令行界面，用于文档索引、搜索、监听等功能。
"""

import argparse
import sys
from pathlib import Path

from loguru import logger

from qmd import QMD
from qmd.core.config import add_context, list_all_contexts, remove_context
from qmd.utils.paths import is_virtual_path, parse_virtual_path


def setup_logging(verbose: bool) -> None:
    """
    配置日志级别

    Args:
        verbose: 是否启用详细日志
    """
    logger.remove()  # 移除默认 handler
    if verbose:
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.add(sys.stderr, level="INFO")


def cmd_add(args: argparse.Namespace) -> int:
    """添加 collection"""
    qmd = QMD(backend=args.backend, db_path=args.db)
    try:
        qmd.add(args.name, args.path, pattern=args.pattern)
        print(f"✓ 已添加 collection: {args.name}")
        print(f"  路径: {args.path}")
        print(f"  Pattern: {args.pattern}")
        return 0
    finally:
        qmd.stop()


def cmd_remove(args: argparse.Namespace) -> int:
    """删除 collection"""
    qmd = QMD(backend=args.backend, db_path=args.db)
    try:
        success = qmd.remove(args.name)
        if success:
            print(f"✓ 已删除 collection: {args.name}")
            return 0
        else:
            print(f"✗ Collection 不存在: {args.name}", file=sys.stderr)
            return 1
    finally:
        qmd.stop()


def cmd_update(args: argparse.Namespace) -> int:
    """更新索引"""
    qmd = QMD(backend=args.backend, db_path=args.db)
    try:
        collection_name = args.name if hasattr(args, "name") and args.name else None
        stats = qmd.update(name=collection_name)

        if "error" in stats:
            print(f"✗ {stats['error']}", file=sys.stderr)
            return 1

        print(f"✓ 索引更新完成:")
        print(f"  Collections: {stats['collections']}")
        print(f"  新增: {stats['indexed']}")
        print(f"  更新: {stats['updated']}")
        print(f"  未变化: {stats['unchanged']}")
        if stats["errors"] > 0:
            print(f"  错误: {stats['errors']}")
        return 0
    finally:
        qmd.stop()


def cmd_search(args: argparse.Namespace) -> int:
    """搜索文档"""
    qmd = QMD(backend=args.backend, db_path=args.db)
    try:
        collections = [args.collection] if args.collection else None
        results = qmd.search(args.query, collections=collections, limit=args.limit)

        if not results:
            print("未找到匹配的文档")
            return 0

        print(f"找到 {len(results)} 个结果:\n")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result.collection}/{result.file}")
            print(f"   分数: {result.score:.3f}")
            print(f"   标题: {result.title}")

            # 显示摘要（前 200 个字符）
            snippet = result.body[:200].replace("\n", " ")
            if len(result.body) > 200:
                snippet += "..."
            print(f"   摘要: {snippet}")
            print()

        return 0
    finally:
        qmd.stop()


def cmd_list(args: argparse.Namespace) -> int:
    """列出所有 collections"""
    qmd = QMD(backend=args.backend, db_path=args.db)
    try:
        collections = qmd.collections

        if not collections:
            print("没有 collection")
            return 0

        print(f"共 {len(collections)} 个 collection:\n")
        for collection in collections:
            print(f"• {collection.name}")
            print(f"  路径: {collection.path}")
            print(f"  Pattern: {collection.pattern}")

            # 获取文档数量
            count = qmd.store.get_document_count(collection.name)
            print(f"  文档数: {count}")
            print()

        return 0
    finally:
        qmd.stop()


def cmd_watch(args: argparse.Namespace) -> int:
    """启动文件监听"""
    qmd = QMD(backend=args.backend, db_path=args.db)
    try:
        collection_name = args.name if hasattr(args, "name") and args.name else None

        print(f"启动文件监听...")
        if collection_name:
            print(f"监听 collection: {collection_name}")
        else:
            print(f"监听所有 collections")

        qmd.watch(name=collection_name)

        print("按 Ctrl+C 停止监听")
        try:
            # 保持运行直到 Ctrl+C
            import signal
            import time

            def signal_handler(sig, frame):
                print("\n停止监听...")
                sys.exit(0)

            signal.signal(signal.SIGINT, signal_handler)

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n停止监听...")
            return 0
    finally:
        qmd.stop()


def cmd_serve(args: argparse.Namespace) -> int:
    """启动 MCP 服务器"""
    import asyncio
    from qmd.mcp import serve

    print("启动 QMD MCP 服务器（stdio transport）...")
    print("按 Ctrl+C 停止服务器")

    try:
        asyncio.run(serve(db_path=args.db))
        return 0
    except KeyboardInterrupt:
        print("\n服务器已停止")
        return 0


def cmd_status(args: argparse.Namespace) -> int:
    """显示索引状态"""
    qmd = QMD(backend=args.backend, db_path=args.db)
    try:
        collections = qmd.collections
        total_docs = 0

        print("索引状态:\n")
        print(f"数据库: {qmd.db_path}")
        print(f"Collections: {len(collections)}\n")

        for collection in collections:
            count = qmd.store.get_document_count(collection.name)
            total_docs += count
            print(f"• {collection.name}: {count} 个文档")

        print(f"\n总计: {total_docs} 个文档")

        # 显示数据库大小
        if qmd.db_path.exists():
            size_mb = qmd.db_path.stat().st_size / (1024 * 1024)
            print(f"数据库大小: {size_mb:.2f} MB")

        return 0
    finally:
        qmd.stop()


def cmd_query(args: argparse.Namespace) -> int:
    """深度搜索（hybrid + rerank）"""
    qmd = QMD(backend=args.backend, db_path=args.db)
    try:
        collections = [args.collection] if args.collection else None

        # query 命令强制使用完整的混合检索（如果后端支持）
        logger.info("执行深度搜索（hybrid + rerank）")
        results = qmd.search(args.query, collections=collections, limit=args.limit)

        if not results:
            print("未找到匹配的文档")
            return 0

        print(f"找到 {len(results)} 个结果:\n")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result.collection}/{result.file}")
            print(f"   分数: {result.score:.3f}")
            print(f"   标题: {result.title}")

            # 显示摘要（前 200 个字符）
            snippet = result.body[:200].replace("\n", " ")
            if len(result.body) > 200:
                snippet += "..."
            print(f"   摘要: {snippet}")
            print()

        return 0
    finally:
        qmd.stop()


def cmd_get(args: argparse.Namespace) -> int:
    """获取单个文档内容"""
    qmd = QMD(backend=args.backend, db_path=args.db)
    try:
        file_path = args.file
        line_num = None

        # 检查是否有 :linenum 后缀
        if ":" in file_path:
            parts = file_path.rsplit(":", 1)
            if parts[1].isdigit():
                file_path = parts[0]
                line_num = int(parts[1])

        # 解析路径（支持虚拟路径和普通路径）
        collection_name = None
        doc_path = None

        if is_virtual_path(file_path):
            # 虚拟路径：qmd://collection/path
            vpath = parse_virtual_path(file_path)
            if vpath is None:
                print(f"✗ 无效的虚拟路径: {file_path}", file=sys.stderr)
                return 1
            collection_name = vpath.collection_name
            doc_path = vpath.path
        else:
            # 普通路径：需要从所有 collections 中查找
            # 简化实现：假设用户提供的是相对路径，需要指定 collection
            if not args.collection:
                print("✗ 普通路径需要指定 --collection", file=sys.stderr)
                return 1
            collection_name = args.collection
            doc_path = file_path

        # 查找文档
        doc = qmd.db.find_active_document(collection_name, doc_path)
        if doc is None:
            print(f"✗ 文档不存在: {collection_name}/{doc_path}", file=sys.stderr)
            return 1

        # 获取内容
        content = qmd.db.get_content_by_hash(doc["hash"])
        if content is None:
            print(f"✗ 无法读取文档内容", file=sys.stderr)
            return 1

        lines = content.splitlines()

        # 处理行号过滤
        from_line = args.from_line or 1
        max_lines = args.max_lines

        if line_num:
            # 如果有 :linenum 后缀，显示该行附近的内容
            from_line = max(1, line_num - 5)
            max_lines = max_lines or 11

        # 裁剪内容
        start_idx = from_line - 1
        end_idx = start_idx + max_lines if max_lines else len(lines)
        display_lines = lines[start_idx:end_idx]

        # 输出
        print(f"文档: {collection_name}/{doc_path}")
        print(f"标题: {doc['title']}")
        print(f"哈希: {doc['hash'][:8]}...")
        print()

        if args.line_numbers:
            for i, line in enumerate(display_lines, start=from_line):
                print(f"{i:5d} | {line}")
        else:
            for line in display_lines:
                print(line)

        return 0
    finally:
        qmd.stop()


def cmd_embed(args: argparse.Namespace) -> int:
    """手动生成 embedding"""
    qmd = QMD(backend=args.backend, db_path=args.db)
    try:
        if qmd.llm_backend is None:
            print("✗ 无可用的 LLM 后端，无法生成 embedding", file=sys.stderr)
            return 1

        # 如果 --force，清空所有 embedding
        if args.force:
            logger.info("清空所有 embedding...")
            qmd.db.clear_all_embeddings()
            print("✓ 已清空所有 embedding")

        # 生成 embedding
        logger.info("开始生成 embedding...")
        stats = qmd.store.embed_documents(qmd.llm_backend, force=args.force)

        print(f"✓ Embedding 生成完成:")
        print(f"  已生成: {stats['embedded']}")
        print(f"  跳过: {stats['skipped']}")

        if stats["errors"] > 0:
            print(f"  错误: {stats['errors']}")

        return 0
    finally:
        qmd.stop()


def cmd_context_add(args: argparse.Namespace) -> int:
    """添加上下文"""
    success = add_context(args.collection, args.path_prefix, args.context)
    if success:
        print(f"✓ 已添加上下文: {args.collection}/{args.path_prefix}")
        return 0
    else:
        print(f"✗ Collection 不存在: {args.collection}", file=sys.stderr)
        return 1


def cmd_context_list(args: argparse.Namespace) -> int:
    """列出所有上下文"""
    contexts = list_all_contexts()

    if not contexts:
        print("没有配置上下文")
        return 0

    print(f"共 {len(contexts)} 个上下文:\n")
    for ctx in contexts:
        print(f"• {ctx['collection']}/{ctx['path']}")
        print(f"  {ctx['context'][:100]}...")
        print()

    return 0


def cmd_context_remove(args: argparse.Namespace) -> int:
    """删除上下文"""
    success = remove_context(args.collection, args.path_prefix)
    if success:
        print(f"✓ 已删除上下文: {args.collection}/{args.path_prefix}")
        return 0
    else:
        print(f"✗ 上下文不存在: {args.collection}/{args.path_prefix}", file=sys.stderr)
        return 1


def cmd_version(args: argparse.Namespace) -> int:
    """显示版本号"""
    import tomllib
    from pathlib import Path

    # 读取 pyproject.toml
    project_root = Path(__file__).parent.parent.parent
    pyproject_path = project_root / "pyproject.toml"

    if pyproject_path.exists():
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            version = data.get("project", {}).get("version", "unknown")
    else:
        version = "unknown"

    print(f"qmd-py version {version}")
    return 0


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog="qmd-py",
        description="基于 RAG 的智能文档查询系统",
    )

    # 全局选项
    parser.add_argument(
        "--backend",
        choices=["auto", "llama_cpp", "sentence_tf"],
        default="auto",
        help="LLM 后端选择 (默认: auto)",
    )
    parser.add_argument(
        "--db",
        type=str,
        help="数据库路径 (默认: ~/.config/qmd/qmd.db)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="启用详细日志",
    )

    # 子命令
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # add
    parser_add = subparsers.add_parser("add", help="添加 collection")
    parser_add.add_argument("name", help="Collection 名称")
    parser_add.add_argument("path", help="Collection 路径")
    parser_add.add_argument(
        "--pattern",
        default="**/*.md",
        help="Glob pattern (默认: **/*.md)",
    )

    # remove
    parser_remove = subparsers.add_parser("remove", help="删除 collection")
    parser_remove.add_argument("name", help="Collection 名称")

    # update
    parser_update = subparsers.add_parser("update", help="更新索引")
    parser_update.add_argument(
        "name",
        nargs="?",
        help="Collection 名称 (不指定=全部)",
    )

    # search
    parser_search = subparsers.add_parser("search", help="搜索文档")
    parser_search.add_argument("query", help="查询文本")
    parser_search.add_argument(
        "--collection",
        "-c",
        help="限定 collection",
    )
    parser_search.add_argument(
        "--limit",
        "-n",
        type=int,
        default=10,
        help="返回结果数量 (默认: 10)",
    )

    # list
    subparsers.add_parser("list", help="列出所有 collections")

    # watch
    parser_watch = subparsers.add_parser("watch", help="启动文件监听")
    parser_watch.add_argument(
        "name",
        nargs="?",
        help="Collection 名称 (不指定=全部)",
    )

    # serve
    subparsers.add_parser("serve", help="启动 MCP 服务器 (占位)")

    # status
    subparsers.add_parser("status", help="显示索引状态")

    # query
    parser_query = subparsers.add_parser("query", help="深度搜索（hybrid + rerank）")
    parser_query.add_argument("query", help="查询文本")
    parser_query.add_argument(
        "--collection",
        "-c",
        help="限定 collection",
    )
    parser_query.add_argument(
        "--limit",
        "-n",
        type=int,
        default=10,
        help="返回结果数量 (默认: 10)",
    )

    # get
    parser_get = subparsers.add_parser("get", help="获取文档内容")
    parser_get.add_argument("file", help="文档路径或虚拟路径 (支持 :linenum 后缀)")
    parser_get.add_argument(
        "--collection",
        "-c",
        help="Collection 名称（普通路径需要）",
    )
    parser_get.add_argument(
        "--from-line",
        type=int,
        help="起始行号",
    )
    parser_get.add_argument(
        "--max-lines",
        type=int,
        help="最大行数",
    )
    parser_get.add_argument(
        "--line-numbers",
        "-n",
        action="store_true",
        help="显示行号",
    )

    # embed
    parser_embed = subparsers.add_parser("embed", help="生成 embedding 向量")
    parser_embed.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="强制重新生成所有 embedding",
    )

    # context 子命令组
    parser_context = subparsers.add_parser("context", help="管理上下文")
    context_subparsers = parser_context.add_subparsers(dest="context_command", help="context 子命令")

    # context add
    parser_context_add = context_subparsers.add_parser("add", help="添加上下文")
    parser_context_add.add_argument("collection", help="Collection 名称")
    parser_context_add.add_argument("path_prefix", help="路径前缀")
    parser_context_add.add_argument("context", help="上下文文本")

    # context list
    context_subparsers.add_parser("list", help="列出所有上下文")

    # context remove
    parser_context_remove = context_subparsers.add_parser("remove", help="删除上下文")
    parser_context_remove.add_argument("collection", help="Collection 名称")
    parser_context_remove.add_argument("path_prefix", help="路径前缀")

    # version
    subparsers.add_parser("version", help="显示版本号")

    return parser


def main() -> int:
    """CLI 入口函数"""
    parser = create_parser()
    args = parser.parse_args()

    # 配置日志
    setup_logging(args.verbose)

    # 如果没有子命令，显示帮助
    if not args.command:
        parser.print_help()
        return 1

    # 特殊处理 context 子命令
    if args.command == "context":
        if not hasattr(args, "context_command") or not args.context_command:
            print("✗ 请指定 context 子命令: add, list, remove", file=sys.stderr)
            return 1

        context_commands = {
            "add": cmd_context_add,
            "list": cmd_context_list,
            "remove": cmd_context_remove,
        }
        handler = context_commands.get(args.context_command)
        if handler:
            try:
                return handler(args)
            except Exception as e:
                logger.exception(f"命令执行失败: {e}")
                print(f"✗ 错误: {e}", file=sys.stderr)
                return 1

    # 路由到对应的命令处理函数
    commands = {
        "add": cmd_add,
        "remove": cmd_remove,
        "update": cmd_update,
        "search": cmd_search,
        "list": cmd_list,
        "watch": cmd_watch,
        "serve": cmd_serve,
        "status": cmd_status,
        "query": cmd_query,
        "get": cmd_get,
        "embed": cmd_embed,
        "version": cmd_version,
    }

    handler = commands.get(args.command)
    if handler:
        try:
            return handler(args)
        except KeyboardInterrupt:
            print("\n操作已取消")
            return 130
        except Exception as e:
            logger.exception(f"命令执行失败: {e}")
            print(f"✗ 错误: {e}", file=sys.stderr)
            return 1
    else:
        print(f"✗ 未知命令: {args.command}", file=sys.stderr)
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
