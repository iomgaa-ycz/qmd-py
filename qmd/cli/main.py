"""
qmd-py CLI 工具

提供完整的命令行界面，用于文档索引、搜索、监听等功能。
"""

import argparse
import sys
from pathlib import Path

from loguru import logger

from qmd import QMD


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
    """启动 MCP 服务器（占位）"""
    print("MCP 服务器功能将在 Phase 5 实现")
    return 1


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
