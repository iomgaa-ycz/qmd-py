"""qmd 对外契约：pydantic 数据模型与 Protocol（单一真相）。

本模块是 qmd 对下游（Scrivai 等）公开的唯一 API 入口。
任何下游代码都应当从 `qmd` 顶层或本模块导入，而不是从 `qmd.core`。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator


class ChunkRef(BaseModel):
    """标识原始 markdown 中的一段 chunk。

    用于业务层把搜索结果回溯到原始文档位置（例如高亮证据）。
    """

    document_id: str = Field(..., description="调用方传入的文档 id")
    chunk_index: int = Field(..., ge=0, description="该文档内 chunk 序号，从 0 开始")
    char_start: int = Field(..., ge=0, description="UTF-8 字符索引（非字节），闭区间起点")
    char_end: int = Field(..., description="闭区间终点（char_end > char_start）")

    @model_validator(mode="after")
    def _check_range(self) -> ChunkRef:
        if self.char_end <= self.char_start:
            raise ValueError("char_end 必须大于 char_start")
        return self


class SearchResult(BaseModel):
    """hybrid_search 单条结果。"""

    chunk_ref: ChunkRef
    text: str = Field(..., description="chunk 原文")
    score: float = Field(..., description="融合后总分，结果列表按此降序")
    bm25_score: float | None = Field(default=None, description="BM25 通道原始分")
    vector_score: float | None = Field(default=None, description="向量通道相似度")
    rerank_score: float | None = Field(default=None, description="rerank=True 时填充")
    metadata: dict[str, Any] = Field(default_factory=dict, description="add_document 透传")


class CollectionInfo(BaseModel):
    """collection 的元信息。"""

    name: str
    document_count: int = Field(..., ge=0)
    chunk_count: int = Field(..., ge=0)
    embedding_dim: int | None = Field(default=None, description="未 embed 时为 None")


@runtime_checkable
class Collection(Protocol):
    """单个 collection 的操作契约。实现类须通过 runtime_checkable 检查。"""

    name: str

    def add_document(
        self,
        document_id: str,
        markdown: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """新增或更新一个文档（同 id 幂等 upsert）。"""
        ...

    def delete_document(self, document_id: str) -> None:
        """删除指定文档。不存在时静默 no-op。"""
        ...

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        """取回文档全文与元数据。不存在时返回 None。

        返回 dict 含：id / markdown / metadata / chunk_count。
        """
        ...

    def list_documents(self) -> list[str]:
        """列出所有 document_id。"""
        ...

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        rerank: bool = False,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """混合检索（BM25 + 向量 + RRF），返回按 score 降序的 top_k 条。"""
        ...

    def add_documents(self, docs: list[dict]) -> None:
        """批量新增或更新文档。

        :param docs: 每个 dict 必含 'document_id: str', 'markdown: str'（必填）；'metadata: dict'（可选，缺省为 {}）。
        :raises ValueError: 任一 dict 缺字段或字段类型错（fail-fast 全检，入库前就抛）。

        契约:
        - 原子事务：任一失败整批回滚
        - upsert 语义：同 add_document；批内同 id 重复以最后一个为准
        - 空 list 合法（no-op）
        - 线程安全
        """
        ...

    def info(self) -> CollectionInfo:
        """返回本 collection 的元信息。"""
        ...


@runtime_checkable
class QmdClient(Protocol):
    """连接级契约。"""

    def collection(self, name: str) -> Collection:
        """取得指定 collection；不存在时自动创建。"""
        ...

    def list_collections(self) -> list[CollectionInfo]:
        """列出所有 collection 的元信息。"""
        ...

    def delete_collection(self, name: str) -> None:
        """删除 collection。不存在时静默 no-op。"""
        ...

    def close(self) -> None:
        """释放资源。"""
        ...


def connect(
    db_path: str | Path | None = None,
    config_overrides: dict | None = None,
) -> QmdClient:
    """工厂函数：创建一个 SqliteQmdClient 实例。

    db_path 解析顺序：参数 > 环境变量 QMD_DB_PATH > ~/.qmd/db.sqlite。
    首次连接自动创建父目录 + schema。

    :param db_path: SQLite 文件路径。
    :param config_overrides: 覆盖 {db_path 同目录}/qmd.yaml 的字段（测试用）。
    """
    import os

    from qmd.core.client import SqliteQmdClient

    if db_path is None:
        env = os.environ.get("QMD_DB_PATH")
        db_path = Path(env) if env else Path.home() / ".qmd" / "db.sqlite"
    return SqliteQmdClient(Path(db_path), config_overrides=config_overrides)
