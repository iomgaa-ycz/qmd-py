"""
文件监听与自动索引

使用 watchdog 监听文件系统变化，自动索引/更新/删除文档。
支持 debounce 机制避免频繁重复操作。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from loguru import logger
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from qmd.core.config import Collection
from qmd.core.store import Store


class CollectionWatcher:
    """
    文件监听器

    监听 collection 路径下的文件变化，自动索引/更新/删除文档。
    使用 debounce 机制避免频繁操作。
    """

    def __init__(self, store: Store, debounce_ms: int = 2000):
        """
        初始化监听器

        Args:
            store: Store 实例
            debounce_ms: Debounce 延迟（毫秒）
        """
        self.store = store
        self.debounce_ms = debounce_ms

        # 观察者实例
        self.observer = Observer()

        # 监听的 collection 映射 {watch_id: (collection, handler)}
        self.watches: dict[str, tuple[Collection, Any]] = {}

        # Debounce 定时器 {file_path: Timer}
        self.debounce_timers: dict[str, threading.Timer] = {}

        # 定时器锁
        self.timer_lock = threading.Lock()

        # 数据库操作锁（防止并发事务冲突）
        self.db_lock = threading.Lock()

    def watch(self, collection: Collection) -> None:
        """
        开始监听 collection

        Args:
            collection: 要监听的 collection
        """
        collection_path = Path(collection.path).resolve()

        if not collection_path.exists():
            logger.warning(f"Collection 路径不存在: {collection_path}")
            return

        # 创建事件处理器
        handler = _CollectionEventHandler(
            watcher=self,
            collection=collection,
            pattern=collection.pattern or "**/*.md",
        )

        # 开始监听
        watch = self.observer.schedule(
            handler, str(collection_path), recursive=True
        )

        # 保存监听信息
        self.watches[collection.name] = (collection, watch)

        logger.info(
            f"开始监听 collection: {collection.name} @ {collection_path} (pattern: {collection.pattern})"
        )

    def stop(self) -> None:
        """停止所有监听"""
        # 取消所有 debounce 定时器
        with self.timer_lock:
            for timer in self.debounce_timers.values():
                timer.cancel()
            self.debounce_timers.clear()

        # 停止观察者
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join(timeout=5)

        self.watches.clear()
        logger.info("已停止所有文件监听")

    def start(self) -> None:
        """启动观察者（在添加 watch 后调用）"""
        if not self.observer.is_alive():
            self.observer.start()
            logger.info("文件监听器已启动")

    def _schedule_index(
        self, collection: Collection, file_path: str, operation: str
    ) -> None:
        """
        调度索引操作（带 debounce）

        Args:
            collection: Collection 实例
            file_path: 文件路径
            operation: 操作类型 (index/delete)
        """
        # 取消之前的定时器
        with self.timer_lock:
            if file_path in self.debounce_timers:
                self.debounce_timers[file_path].cancel()

            # 创建新定时器
            timer = threading.Timer(
                self.debounce_ms / 1000.0,
                self._execute_operation,
                args=(collection, file_path, operation),
            )
            self.debounce_timers[file_path] = timer
            timer.start()

    def _execute_operation(
        self, collection: Collection, file_path: str, operation: str
    ) -> None:
        """
        执行索引操作

        Args:
            collection: Collection 实例
            file_path: 文件路径
            operation: 操作类型 (index/delete)
        """
        try:
            # 从定时器字典中移除
            with self.timer_lock:
                self.debounce_timers.pop(file_path, None)

            collection_path = Path(collection.path).resolve()
            file_path_obj = Path(file_path).resolve()

            # 计算相对路径
            try:
                relative_path = file_path_obj.relative_to(collection_path)
            except ValueError:
                logger.warning(f"文件不在 collection 路径下: {file_path}")
                return

            relative_path_str = str(relative_path)

            # 使用数据库锁防止并发事务冲突
            with self.db_lock:
                if operation == "index":
                    # 检查文件是否存在
                    if not file_path_obj.exists():
                        logger.debug(f"文件不存在，跳过索引: {file_path}")
                        return

                    # 读取内容
                    try:
                        content = file_path_obj.read_text(encoding="utf-8")
                    except Exception as e:
                        logger.error(f"读取文件失败: {file_path} - {e}")
                        return

                    # 索引文档
                    result = self.store.index_document(
                        collection.name, relative_path_str, content
                    )
                    logger.info(
                        f"文件变化: {relative_path_str} ({result.get('status', 'unknown')})"
                    )

                elif operation == "delete":
                    # 删除文档
                    success = self.store.remove_document(
                        collection.name, relative_path_str
                    )
                    if success:
                        logger.info(f"文件删除: {relative_path_str}")

        except Exception as e:
            logger.error(f"处理文件变化失败: {file_path} - {e}")


class _CollectionEventHandler(FileSystemEventHandler):
    """
    Collection 文件事件处理器

    处理文件创建、修改、删除事件，并过滤 glob pattern。
    """

    def __init__(self, watcher: CollectionWatcher, collection: Collection, pattern: str):
        """
        初始化事件处理器

        Args:
            watcher: CollectionWatcher 实例
            collection: Collection 实例
            pattern: Glob pattern
        """
        super().__init__()
        self.watcher = watcher
        self.collection = collection
        self.pattern = pattern

    def _should_process(self, file_path: str) -> bool:
        """
        检查文件是否应该被处理

        Args:
            file_path: 文件路径

        Returns:
            是否应该处理
        """
        file_path_obj = Path(file_path)

        # 跳过目录
        if file_path_obj.is_dir():
            return False

        # 跳过隐藏文件
        if file_path_obj.name.startswith("."):
            return False

        # 计算相对路径
        try:
            collection_path = Path(self.collection.path).resolve()
            relative_path = file_path_obj.resolve().relative_to(collection_path)
        except ValueError:
            return False

        # 使用 Path.match() 检查 glob pattern（支持 **）
        # 注意：Path.match() 是从右向左匹配，**/*.md 不匹配根目录下的 .md 文件
        # 所以我们需要同时检查 pattern 和去掉 **/ 的 pattern
        matches = relative_path.match(self.pattern)

        # 如果 pattern 以 **/ 开头，也尝试去掉 **/ 的匹配
        if not matches and self.pattern.startswith("**/"):
            simple_pattern = self.pattern[3:]  # 去掉 "**/
            matches = relative_path.match(simple_pattern)

        if not matches:
            return False

        return True

    def on_created(self, event: FileSystemEvent) -> None:
        """文件创建事件"""
        if event.is_directory:
            return

        if self._should_process(event.src_path):
            logger.debug(f"检测到文件创建: {event.src_path}")
            self.watcher._schedule_index(
                self.collection, event.src_path, "index"
            )

    def on_modified(self, event: FileSystemEvent) -> None:
        """文件修改事件"""
        if event.is_directory:
            return

        if self._should_process(event.src_path):
            logger.debug(f"检测到文件修改: {event.src_path}")
            self.watcher._schedule_index(
                self.collection, event.src_path, "index"
            )

    def on_deleted(self, event: FileSystemEvent) -> None:
        """文件删除事件"""
        if event.is_directory:
            return

        # 删除事件不需要检查文件是否存在，但仍需检查 pattern
        file_path_obj = Path(event.src_path)

        # 跳过隐藏文件
        if file_path_obj.name.startswith("."):
            return

        # 计算相对路径
        try:
            collection_path = Path(self.collection.path).resolve()
            relative_path = file_path_obj.resolve().relative_to(collection_path)
        except ValueError:
            return

        # 使用 Path.match() 检查 glob pattern（支持 **）
        if not relative_path.match(self.pattern):
            return

        logger.debug(f"检测到文件删除: {event.src_path}")
        self.watcher._schedule_index(self.collection, event.src_path, "delete")
