"""
qmd - 基于 RAG 的智能文档查询系统

QMD 门面类提供统一的 API 入口，串联所有核心模块。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from loguru import logger

from qmd.core.config import NamedCollection, load_config
from qmd.core.db import Database, ensure_db_dir, get_db_path, init_schema, open_database
from qmd.core.retrieval import SearchResult, search
from qmd.core.store import Store
from qmd.core.watcher import CollectionWatcher
from qmd.llm.base import LLMBackend

# Backend 类型
BackendType = Literal["auto", "llama_cpp", "sentence_tf"]


class QMD:
    """
    QMD 门面类（Facade Pattern）

    提供文档索引、检索、监听的统一入口。
    串联 config、store、retrieval、watcher、llm 所有模块。

    Example:
        >>> qmd = QMD(backend="sentence_tf")
        >>> qmd.add("docs", "/path/to/docs", pattern="**/*.md")
        >>> qmd.update()
        >>> results = qmd.search("query text")
        >>> qmd.watch()
    """

    def __init__(
        self,
        config_path: str | Path | None = None,
        backend: BackendType = "auto",
        db_path: str | Path | None = None,
    ):
        """
        初始化 QMD 实例

        Args:
            config_path: 配置文件路径（qmd.yaml），None 使用默认路径
                注意：暂不支持自定义配置路径，总是使用默认路径
            backend: LLM 后端选择
                - "auto": 优先 llama_cpp，fallback 到 sentence_tf
                - "llama_cpp": 强制使用 LlamaCppBackend
                - "sentence_tf": 强制使用 SentenceTransformerBackend
            db_path: 数据库路径，None 使用默认路径 ~/.config/qmd/qmd.db
        """
        self.config_path = Path(config_path) if config_path else None
        self.backend_type = backend

        # 加载配置（总是从默认路径）
        from qmd.core.config import CollectionConfig
        if self.config_path and self.config_path.exists():
            # 暂不支持自定义配置路径，记录警告
            logger.warning(f"暂不支持自定义配置路径，忽略: {self.config_path}")

        # 对于测试或独立实例，创建空配置
        self.config = CollectionConfig(collections={})

        # 初始化数据库
        if db_path:
            self.db_path = Path(db_path)
        else:
            ensure_db_dir()
            self.db_path = get_db_path()

        logger.info(f"使用数据库: {self.db_path}")
        conn = open_database(self.db_path)
        init_schema(conn)
        self.db = Database(conn)

        # 初始化 Store
        self.store = Store(self.db)

        # 初始化 LLM 后端（懒加载）
        self._llm_backend: LLMBackend | None = None

        # 初始化 Watcher（懒加载）
        self._watcher: CollectionWatcher | None = None

        logger.info(f"QMD 初始化完成（backend={backend}）")

    @property
    def llm_backend(self) -> LLMBackend | None:
        """
        懒加载 LLM 后端

        Returns:
            LLM 后端实例或 None
        """
        if self._llm_backend is None:
            self._llm_backend = self._create_backend()
        return self._llm_backend

    def _create_backend(self) -> LLMBackend | None:
        """
        创建 LLM 后端

        Returns:
            LLM 后端实例或 None
        """
        if self.backend_type == "auto":
            # 优先尝试 llama_cpp
            try:
                from qmd.llm.llama_cpp import LlamaCppBackend
                logger.info("使用 LlamaCppBackend")
                return LlamaCppBackend()
            except ImportError as e:
                logger.warning(f"llama-cpp-python 不可用: {e}")

            # Fallback 到 sentence_tf
            try:
                from qmd.llm.sentence_tf import SentenceTransformerBackend
                logger.info("使用 SentenceTransformerBackend (fallback)")
                return SentenceTransformerBackend()
            except ImportError as e:
                logger.warning(f"sentence-transformers 不可用: {e}")

            logger.warning("没有可用的 LLM 后端，某些功能受限")
            return None

        elif self.backend_type == "llama_cpp":
            from qmd.llm.llama_cpp import LlamaCppBackend
            logger.info("使用 LlamaCppBackend")
            return LlamaCppBackend()

        elif self.backend_type == "sentence_tf":
            from qmd.llm.sentence_tf import SentenceTransformerBackend
            logger.info("使用 SentenceTransformerBackend")
            return SentenceTransformerBackend()

        else:
            raise ValueError(f"未知的 backend 类型: {self.backend_type}")

    @property
    def collections(self) -> list[NamedCollection]:
        """
        获取所有 collection

        Returns:
            Collection 列表
        """
        return [
            NamedCollection(name=name, **collection.model_dump())
            for name, collection in self.config.collections.items()
        ]

    def add(
        self,
        name: str,
        path: str | Path,
        pattern: str = "**/*.md",
    ) -> None:
        """
        添加 collection

        Args:
            name: Collection 名称
            path: Collection 路径
            pattern: Glob pattern（默认 **/*.md）
        """
        from qmd.core.config import Collection

        collection = Collection(
            path=str(Path(path).resolve()),
            pattern=pattern,
        )

        # 添加到配置（dict 结构）
        if name in self.config.collections:
            logger.warning(f"Collection '{name}' 已存在，将被覆盖")

        self.config.collections[name] = collection

        logger.info(f"添加 collection: {name} @ {path}")

    def remove(self, name: str) -> bool:
        """
        删除 collection

        Args:
            name: Collection 名称

        Returns:
            是否成功删除
        """
        # 从配置中删除
        if name not in self.config.collections:
            logger.warning(f"Collection '{name}' 不存在")
            return False

        del self.config.collections[name]

        # 停用数据库中的所有文档
        paths = self.db.get_active_document_paths(name)
        for path in paths:
            self.db.deactivate_document(name, path)

        logger.info(f"删除 collection: {name} ({len(paths)} 个文档)")
        return True

    def update(self, name: str | None = None) -> dict[str, Any]:
        """
        更新索引（重新扫描并索引文档）

        Args:
            name: Collection 名称，None 表示全部

        Returns:
            更新统计信息
        """
        # 获取要更新的 collections
        if name:
            if name not in self.config.collections:
                logger.warning(f"Collection '{name}' 不存在")
                return {"error": f"Collection '{name}' not found"}
            collections_to_update = [(name, self.config.collections[name])]
        else:
            collections_to_update = list(self.config.collections.items())

        stats = {
            "collections": 0,
            "indexed": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": 0,
        }

        for collection_name, collection in collections_to_update:
            logger.info(f"更新 collection: {collection_name}")
            stats["collections"] += 1

            # 获取所有匹配的文件
            from pathlib import Path as PathlibPath
            import glob

            collection_path = PathlibPath(collection.path)
            if not collection_path.exists():
                logger.error(f"路径不存在: {collection_path}")
                stats["errors"] += 1
                continue

            # 使用 glob 匹配文件
            pattern = collection.pattern or "**/*.md"
            files = glob.glob(
                str(collection_path / pattern),
                recursive=True,
            )

            for file_path in files:
                file_path_obj = PathlibPath(file_path)

                # 跳过隐藏文件
                if file_path_obj.name.startswith("."):
                    continue

                # 计算相对路径
                try:
                    relative_path = file_path_obj.relative_to(collection_path)
                except ValueError:
                    continue

                # 读取内容
                try:
                    content = file_path_obj.read_text(encoding="utf-8")
                except Exception as e:
                    logger.error(f"读取失败: {file_path} - {e}")
                    stats["errors"] += 1
                    continue

                # 索引文档
                result = self.store.index_document(
                    collection_name,
                    str(relative_path),
                    content,
                )

                if result["status"] == "indexed":
                    stats["indexed"] += 1
                elif result["status"] == "updated":
                    stats["updated"] += 1
                elif result["status"] == "unchanged":
                    stats["unchanged"] += 1

        logger.info(
            f"索引更新完成: {stats['indexed']} 新增, "
            f"{stats['updated']} 更新, "
            f"{stats['unchanged']} 未变化"
        )
        return stats

    def search(
        self,
        query: str,
        collections: list[str] | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """
        搜索文档

        Args:
            query: 查询文本
            collections: Collection 名称列表，None 表示全部
            limit: 返回结果数量

        Returns:
            搜索结果列表
        """
        # 如果指定了 collections，验证是否存在
        if collections:
            for name in collections:
                if name not in self.config.collections:
                    logger.warning(f"Collection '{name}' 不存在，已忽略")

        # collections 参数传给 search 函数时需要单个 collection 名称或 None
        # 目前 search 函数只支持单个 collection，需要循环调用
        if collections and len(collections) == 1:
            collection = collections[0]
        else:
            collection = None

        # 调用 retrieval.search
        results = search(
            db=self.db,
            query=query,
            collection=collection,
            limit=limit,
            llm_backend=self.llm_backend,
        )

        logger.info(f"搜索完成: {len(results)} 个结果")
        return results

    def watch(self, name: str | None = None) -> None:
        """
        启动文件监听（自动索引）

        Args:
            name: Collection 名称，None 表示全部
        """
        if self._watcher is None:
            self._watcher = CollectionWatcher(self.store)

        # 获取要监听的 collections
        if name:
            if name not in self.config.collections:
                logger.warning(f"Collection '{name}' 不存在")
                return
            collections_to_watch = [(name, self.config.collections[name])]
        else:
            collections_to_watch = list(self.config.collections.items())

        if not collections_to_watch:
            logger.warning("没有 collection 可监听")
            return

        for collection_name, collection in collections_to_watch:
            # 创建 NamedCollection
            named_collection = NamedCollection(name=collection_name, **collection.model_dump())
            self._watcher.watch(named_collection)

        self._watcher.start()
        logger.info(f"文件监听已启动: {len(collections_to_watch)} 个 collection")

    def stop(self) -> None:
        """
        停止监听并释放资源
        """
        # 停止 watcher
        if self._watcher:
            self._watcher.stop()
            self._watcher = None

        # 释放 LLM 后端资源
        if self._llm_backend:
            # 调用 dispose 方法（如果存在）
            if hasattr(self._llm_backend, "dispose"):
                self._llm_backend.dispose()  # type: ignore
            self._llm_backend = None

        # 关闭数据库连接
        if self.db:
            self.db.conn.close()

        logger.info("QMD 已停止")

    def __enter__(self):
        """Context manager 支持"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager 退出时自动清理"""
        self.stop()


__all__ = ["QMD", "SearchResult", "NamedCollection"]
