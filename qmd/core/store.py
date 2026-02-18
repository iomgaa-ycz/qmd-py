"""
文档存储与索引层

核心功能：
- 文档索引：content-addressable 存储 + 增量更新
- 分块 + embedding 生成
- 集合管理：扫描、更新、清理

整合模块：chunking、db、config、llm
"""

from datetime import datetime, timezone
from glob import glob
from pathlib import Path
from typing import Any

from loguru import logger

from qmd.core.chunking import chunk_document
from qmd.core.config import Collection
from qmd.core.db import Database
from qmd.llm.base import LLMBackend
from qmd.utils.hashing import content_hash as compute_content_hash
from qmd.utils.paths import extract_title, get_file_stats, handelize


class Store:
    """
    文档存储与索引管理器

    提供文档的 CRUD 操作、增量更新、向量化索引等功能。
    使用 content-addressable storage（基于 SHA256）实现去重和增量更新。
    """

    def __init__(self, db: Database):
        """
        初始化 Store

        Args:
            db: 数据库实例
        """
        self.db = db

    def index_document(
        self,
        collection_name: str,
        file_path: str,
        content: str,
    ) -> dict[str, Any]:
        """
        索引单个文档

        增量更新逻辑：
        - 计算 content hash (SHA256)
        - 如果 hash 相同且文档存在 → 跳过或只更新 title
        - 如果 hash 不同 → 插入新 content，更新 document 记录
        - 如果文档不存在 → 插入 content 和 document

        Args:
            collection_name: 集合名称
            file_path: 文件路径（相对于集合根目录）
            content: 文档内容

        Returns:
            索引结果字典，包含 status、hash 等信息
        """
        # 跳过空文档
        if not content.strip():
            logger.debug(f"跳过空文档: {file_path}")
            return {"status": "skipped", "reason": "empty"}

        # 计算 content hash
        content_hash = compute_content_hash(content)

        # 提取 title
        title = extract_title(content, file_path)

        # Normalize path for token-friendliness
        normalized_path = handelize(file_path)

        # 获取文件元数据
        file_stats = get_file_stats(file_path)
        created_at = file_stats.get("created_at", self._now())
        modified_at = file_stats.get("modified_at", self._now())

        # 检查文档是否存在
        existing_doc = self.db.find_active_document(collection_name, normalized_path)

        if existing_doc:
            # 文档已存在
            if existing_doc["hash"] == content_hash:
                # Hash 相同 → 检查 title 是否需要更新
                if existing_doc.get("title") != title:
                    self.db.update_document_title(
                        existing_doc["id"], title, modified_at
                    )
                    logger.info(f"更新 title: {file_path}")
                    return {
                        "status": "title_updated",
                        "hash": content_hash,
                        "docid": existing_doc["id"],
                    }
                else:
                    logger.debug(f"文档未变化: {file_path}")
                    return {
                        "status": "unchanged",
                        "hash": content_hash,
                        "docid": existing_doc["id"],
                    }
            else:
                # Hash 不同 → 内容变化
                # 插入新 content
                self.db.insert_content(content_hash, content, self._now())

                # 更新 document 记录
                self.db.update_document(
                    existing_doc["id"], title, content_hash, modified_at
                )

                logger.info(f"更新文档: {file_path} (hash 变化)")
                return {
                    "status": "updated",
                    "hash": content_hash,
                    "docid": existing_doc["id"],
                }
        else:
            # 新文档 → 插入 content 和 document
            self.db.insert_content(content_hash, content, self._now())
            self.db.insert_document(
                collection_name,
                normalized_path,
                title,
                content_hash,
                created_at,
                modified_at,
            )

            logger.info(f"索引新文档: {file_path}")
            return {"status": "indexed", "hash": content_hash}

    def remove_document(self, collection_name: str, file_path: str) -> bool:
        """
        删除文档（标记为 inactive）

        Args:
            collection_name: 集合名称
            file_path: 文件路径

        Returns:
            是否成功删除
        """
        normalized_path = handelize(file_path)

        # 检查文档是否存在
        existing_doc = self.db.find_active_document(collection_name, normalized_path)

        if not existing_doc:
            logger.warning(f"文档不存在: {file_path}")
            return False

        # 标记为 inactive
        self.db.deactivate_document(collection_name, normalized_path)
        logger.info(f"删除文档: {file_path}")
        return True

    def update_collection(
        self,
        collection: Collection,
        llm_backend: LLMBackend | None = None,
        auto_embed: bool = False,
    ) -> dict[str, int]:
        """
        更新整个集合

        扫描集合路径，索引所有匹配的文件，删除不再存在的文档。

        Args:
            collection: 集合配置
            llm_backend: LLM 后端（用于 embedding，可选）
            auto_embed: 是否自动生成 embedding

        Returns:
            更新统计信息字典
        """
        collection_path = Path(collection.path).resolve()
        glob_pattern = collection.pattern or "**/*.md"

        logger.info(
            f"扫描集合: {collection.name} @ {collection_path} (pattern: {glob_pattern})"
        )

        # 扫描文件
        matched_files = glob(str(collection_path / glob_pattern), recursive=True)

        seen_paths = set()
        stats = {
            "indexed": 0,
            "updated": 0,
            "unchanged": 0,
            "title_updated": 0,
            "removed": 0,
            "skipped": 0,
        }

        # 索引所有文件
        for file_path in matched_files:
            file_path_obj = Path(file_path)

            # 计算相对路径
            try:
                relative_path = file_path_obj.relative_to(collection_path)
            except ValueError:
                logger.warning(f"文件不在集合路径下: {file_path}")
                continue

            relative_path_str = str(relative_path)
            normalized_path = handelize(relative_path_str)
            seen_paths.add(normalized_path)

            # 读取内容
            try:
                content = file_path_obj.read_text(encoding="utf-8")
            except Exception as e:
                logger.error(f"读取文件失败: {file_path} - {e}")
                stats["skipped"] += 1
                continue

            # 索引文档
            result = self.index_document(collection.name, relative_path_str, content)

            # 更新统计
            status = result.get("status", "unknown")
            if status in stats:
                stats[status] += 1

        # 清理不存在的文档
        active_docs = self.db.get_active_document_paths(collection.name)
        for doc_path in active_docs:
            if doc_path not in seen_paths:
                self.db.deactivate_document(collection.name, doc_path)
                stats["removed"] += 1

        # 清理孤立的 content
        orphaned_content_count = self.db.cleanup_orphaned_content()
        if orphaned_content_count > 0:
            logger.info(f"清理孤立 content: {orphaned_content_count} 条")

        logger.info(f"集合更新完成: {collection.name} - {stats}")

        # 如果需要，自动生成 embedding
        if auto_embed and llm_backend:
            logger.info("开始生成 embedding...")
            embed_stats = self.embed_documents(llm_backend)
            logger.info(f"Embedding 完成: {embed_stats}")

        return stats

    def get_document_count(self, collection_name: str) -> int:
        """
        获取集合中活跃文档数量

        Args:
            collection_name: 集合名称

        Returns:
            文档数量
        """
        return self.db.get_document_count(collection_name)

    def get_indexed_files(self, collection_name: str) -> list[str]:
        """
        获取集合中所有已索引文件路径

        Args:
            collection_name: 集合名称

        Returns:
            文件路径列表
        """
        return self.db.get_active_document_paths(collection_name)

    def embed_documents(
        self,
        llm_backend: LLMBackend,
        force: bool = False,
        batch_size: int = 32,
    ) -> dict[str, int]:
        """
        为文档生成 embedding

        Args:
            llm_backend: LLM 后端
            force: 是否强制重新生成（清空现有向量）
            batch_size: 批处理大小

        Returns:
            统计信息字典
        """
        if force:
            logger.warning("强制重新生成 embedding（清空现有向量）")
            self.db.clear_all_embeddings()

        # 获取需要 embedding 的 hash
        hashes_to_embed = self.db.get_hashes_for_embedding()

        if not hashes_to_embed:
            logger.info("所有文档已有 embedding")
            return {"embedded": 0, "errors": 0}

        logger.info(f"需要生成 embedding 的文档: {len(hashes_to_embed)} 个")

        # 准备分块
        all_chunks: list[dict[str, Any]] = []

        for item in hashes_to_embed:
            content = item["content"]
            content_hash = item["hash"]
            title = extract_title(content, item.get("path", ""))

            # 分块
            chunks = chunk_document(content)

            for seq, chunk in enumerate(chunks):
                all_chunks.append(
                    {
                        "hash": content_hash,
                        "title": title,
                        "text": chunk.text,
                        "seq": seq,
                        "pos": chunk.pos,
                    }
                )

        logger.info(f"总共 {len(all_chunks)} 个 chunk 需要 embedding")

        # 先获取 embedding 维度并确保 vectors_vec 表存在
        if all_chunks:
            # 使用第一个 chunk 获取维度
            first_text = all_chunks[0]["text"]
            first_embed_result = llm_backend.embed(first_text)
            if first_embed_result:
                from qmd.core.db import ensure_vec_table
                dimensions = len(first_embed_result.embedding)
                ensure_vec_table(self.db.conn, dimensions)
                logger.debug(f"Vectors 表已确保存在 (维度={dimensions})")

        # 批量生成 embedding
        stats = {"embedded": 0, "errors": 0}
        now = self._now()

        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i : i + batch_size]

            # 格式化文本
            texts = [chunk["text"] for chunk in batch]

            # 批量 embed
            try:
                embed_results = llm_backend.embed_batch(texts)

                # 插入数据库
                for chunk, embed_result in zip(batch, embed_results):
                    if embed_result is None:
                        stats["errors"] += 1
                        logger.warning(
                            f"Embedding 失败: hash={chunk['hash'][:8]}, seq={chunk['seq']}"
                        )
                        continue

                    # 插入 embedding
                    self.db.insert_embedding(
                        chunk["hash"],
                        chunk["seq"],
                        chunk["pos"],
                        embed_result.embedding,
                        embed_result.model,
                        now,
                    )
                    stats["embedded"] += 1

            except Exception as e:
                logger.error(f"批量 embedding 失败: {e}")
                stats["errors"] += len(batch)

        logger.info(f"Embedding 完成: {stats}")
        return stats

    def _now(self) -> str:
        """获取当前 UTC 时间戳（ISO 8601 格式）"""
        return datetime.now(timezone.utc).isoformat()
