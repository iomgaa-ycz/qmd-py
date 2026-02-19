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
    from qmd.cli.formatter import format_search_results

    qmd = QMD(backend=args.backend, db_path=args.db)
    try:
        collections = [args.collection] if args.collection else None
        results = qmd.search(args.query, collections=collections, limit=args.limit)

        if not results:
            print("未找到匹配的文档")
            return 0

        # 使用 formatter 输出
        output_format = getattr(args, "format", "cli")
        if output_format and output_format != "cli":
            # 转换为 dict
            results_dict = [
                {
                    "file": r.file,
                    "title": r.title,
                    "body": r.body,
                    "score": r.score,
                    "collection": r.collection,
                    "hash": r.hash,
                    "pos": r.pos,
                    "context": r.context,
                }
                for r in results
            ]
            opts = {
                "query": args.query,
                "full": getattr(args, "full", False),
                "line_numbers": getattr(args, "line_numbers", False),
            }
            output = format_search_results(results_dict, output_format, opts)
            print(output)
        else:
            # CLI 格式（原有逻辑）
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
    from qmd.cli.formatter import format_search_results

    qmd = QMD(backend=args.backend, db_path=args.db)
    try:
        collections = [args.collection] if args.collection else None

        # query 命令强制使用完整的混合检索（如果后端支持）
        logger.info("执行深度搜索（hybrid + rerank）")
        results = qmd.search(args.query, collections=collections, limit=args.limit)

        if not results:
            print("未找到匹配的文档")
            return 0

        # 使用 formatter 输出
        output_format = getattr(args, "format", "cli")
        if output_format and output_format != "cli":
            # 转换为 dict
            results_dict = [
                {
                    "file": r.file,
                    "title": r.title,
                    "body": r.body,
                    "score": r.score,
                    "collection": r.collection,
                    "hash": r.hash,
                    "pos": r.pos,
                    "context": r.context,
                }
                for r in results
            ]
            opts = {
                "query": args.query,
                "full": getattr(args, "full", False),
                "line_numbers": getattr(args, "line_numbers", False),
            }
            output = format_search_results(results_dict, output_format, opts)
            print(output)
        else:
            # CLI 格式（原有逻辑）
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


def cmd_ls(args: argparse.Namespace) -> int:
    """列出 collections 或文件"""
    from qmd.core.config import list_collections

    qmd = QMD(backend=args.backend, db_path=args.db)
    try:
        path_arg = getattr(args, "path", None)

        if not path_arg:
            # 列出所有 collections
            collections = list_collections()
            if not collections:
                print("没有 collection。运行 'qmd add' 来索引文件。")
                return 0

            print("Collections:\n")
            for coll in collections:
                count = qmd.store.get_document_count(coll.name)
                print(f"  qmd://{coll.name}/  ({count} 个文件)")
            return 0
        else:
            # 列出指定 collection 的文件
            # 简化实现：只支持 collection 名称
            collection_name = path_arg.replace("qmd://", "").rstrip("/")
            docs = qmd.db.conn.execute(
                """
                SELECT d.path, d.title, d.modified_at, LENGTH(c.doc) as size
                FROM documents d
                JOIN content c ON d.hash = c.hash
                WHERE d.collection = ? AND d.active = 1
                ORDER BY d.path
                """,
                (collection_name,),
            ).fetchall()

            if not docs:
                print(f"Collection '{collection_name}' 为空或不存在")
                return 0

            print(f"qmd://{collection_name}/  ({len(docs)} 个文件):\n")
            for doc in docs:
                print(f"  {doc['path']}  ({doc['size']} bytes)")
            return 0
    finally:
        qmd.stop()


def cmd_cleanup(args: argparse.Namespace) -> int:
    """清理数据库"""
    from qmd.core.document import cleanup_orphaned_vectors, delete_inactive_documents, vacuum_database

    qmd = QMD(backend=args.backend, db_path=args.db)
    try:
        print("清理孤立向量...")
        deleted_vectors = cleanup_orphaned_vectors(qmd.db)
        print(f"  删除 {deleted_vectors} 个孤立向量")

        print("删除 inactive 文档...")
        deleted_docs = delete_inactive_documents(qmd.db)
        print(f"  删除 {deleted_docs} 个文档")

        print("压缩数据库...")
        vacuum_database(qmd.db)
        print("  ✓ VACUUM 完成")

        print("\n清理完成")
        return 0
    finally:
        qmd.stop()


def cmd_collection_rename(args: argparse.Namespace) -> int:
    """重命名 collection"""
    from qmd.core.config import rename_collection

    qmd = QMD(backend=args.backend, db_path=args.db)
    try:
        old_name = args.old_name
        new_name = args.new_name

        # 重命名配置
        success = rename_collection(old_name, new_name)
        if not success:
            print(f"✗ Collection 不存在: {old_name}", file=sys.stderr)
            return 1

        # 更新数据库中的 collection 名称
        qmd.db.conn.execute(
            "UPDATE documents SET collection = ? WHERE collection = ?",
            (new_name, old_name),
        )
        qmd.db.conn.commit()

        print(f"✓ 已重命名 collection: {old_name} → {new_name}")
        return 0
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
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
    parser_search.add_argument(
        "--format",
        choices=["cli", "json", "csv", "xml", "md", "files"],
        default="cli",
        help="输出格式 (默认: cli)",
    )
    parser_search.add_argument(
        "--full",
        action="store_true",
        help="显示完整文档内容",
    )
    parser_search.add_argument(
        "--line-numbers",
        action="store_true",
        help="显示行号",
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
    parser_query.add_argument(
        "--format",
        choices=["cli", "json", "csv", "xml", "md", "files"],
        default="cli",
        help="输出格式 (默认: cli)",
    )
    parser_query.add_argument(
        "--full",
        action="store_true",
        help="显示完整文档内容",
    )
    parser_query.add_argument(
        "--line-numbers",
        action="store_true",
        help="显示行号",
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
    parser_get.add_argument(
        "--format",
        choices=["cli", "json", "md", "xml"],
        default="cli",
        help="输出格式 (默认: cli)",
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

    # ls
    parser_ls = subparsers.add_parser("ls", help="列出 collections 或文件")
    parser_ls.add_argument(
        "path",
        nargs="?",
        help="Collection 名称或路径 (可选)",
    )

    # cleanup
    subparsers.add_parser("cleanup", help="清理数据库（删除孤立向量和 inactive 文档）")

    # collection 子命令组
    parser_coll = subparsers.add_parser("collection", help="管理 collections")
    coll_subparsers = parser_coll.add_subparsers(dest="coll_command", help="collection 子命令")

    # collection add (已有)
    coll_add = coll_subparsers.add_parser("add", help="添加 collection")
    coll_add.add_argument("name", help="Collection 名称")
    coll_add.add_argument("path", help="Collection 路径")
    coll_add.add_argument("--pattern", default="**/*.md", help="Glob pattern")

    # collection remove (已有)
    coll_remove = coll_subparsers.add_parser("remove", help="删除 collection")
    coll_remove.add_argument("name", help="Collection 名称")

    # collection rename (新增)
    coll_rename = coll_subparsers.add_parser("rename", help="重命名 collection")
    coll_rename.add_argument("old_name", help="旧名称")
    coll_rename.add_argument("new_name", help="新名称")

    # collection list (已有，保持向后兼容)
    coll_subparsers.add_parser("list", help="列出所有 collections")

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

    # 特殊处理 collection 子命令
    if args.command == "collection":
        if not hasattr(args, "coll_command") or not args.coll_command:
            print("✗ 请指定 collection 子命令: add, remove, list, rename", file=sys.stderr)
            return 1

        collection_commands = {
            "add": cmd_add,
            "remove": cmd_remove,
            "list": cmd_list,
            "rename": cmd_collection_rename,
        }
        handler = collection_commands.get(args.coll_command)
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
        "ls": cmd_ls,
        "cleanup": cmd_cleanup,
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
