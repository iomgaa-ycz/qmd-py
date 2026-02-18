"""
YAML 配置管理

管理 ~/.config/qmd/index.yml 的 YAML 配置文件。
Collection 定义了要索引的目录及其关联的上下文。

忠实移植自 qmd/src/collections.ts
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Pydantic 模型（Schema 验证）
# =============================================================================

class Collection(BaseModel):
    """单个 Collection 配置"""
    path: str  # 绝对路径
    pattern: str = "**/*.md"  # Glob 模式
    context: dict[str, str] | None = None  # 路径前缀 -> 上下文描述
    update: str | None = None  # 可选的更新命令

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """验证路径非空"""
        if not v or not v.strip():
            raise ValueError("path cannot be empty")
        return v

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        """验证 pattern 非空"""
        if not v or not v.strip():
            raise ValueError("pattern cannot be empty")
        return v


class CollectionConfig(BaseModel):
    """完整的配置文件结构"""
    global_context: str | None = None  # 应用于所有 collections 的上下文
    collections: dict[str, Collection] = Field(default_factory=dict)  # collection 名 -> 配置


class NamedCollection(Collection):
    """带名称的 Collection（用于返回值）"""
    name: str


# =============================================================================
# 配置路径
# =============================================================================

# 当前索引名称（默认: "index"）
_current_index_name: str = "index"


def set_config_index_name(name: str) -> None:
    """
    设置当前索引名称用于配置文件查找
    配置文件将是 ~/.config/qmd/{indexName}.yml
    """
    global _current_index_name
    _current_index_name = name


def get_config_dir() -> Path:
    """
    获取配置目录路径

    优先级:
    1. QMD_CONFIG_DIR 环境变量（用于测试）
    2. XDG_CONFIG_HOME/qmd（遵循 XDG 规范）
    3. ~/.config/qmd（默认）
    """
    if qmd_config_dir := os.getenv("QMD_CONFIG_DIR"):
        return Path(qmd_config_dir)

    if xdg_config_home := os.getenv("XDG_CONFIG_HOME"):
        return Path(xdg_config_home) / "qmd"

    return Path.home() / ".config" / "qmd"


def get_config_file_path() -> Path:
    """获取配置文件完整路径"""
    return get_config_dir() / f"{_current_index_name}.yml"


def ensure_config_dir() -> None:
    """确保配置目录存在"""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)


# =============================================================================
# 核心功能
# =============================================================================

def load_config() -> CollectionConfig:
    """
    从 ~/.config/qmd/index.yml 加载配置
    如果文件不存在，返回空配置
    """
    config_path = get_config_file_path()

    if not config_path.exists():
        return CollectionConfig(collections={})

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
            data = yaml.safe_load(content)

        # 处理空文件
        if data is None:
            return CollectionConfig(collections={})

        # 确保 collections 对象存在
        if "collections" not in data:
            data["collections"] = {}

        return CollectionConfig(**data)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse {config_path}: {e}") from e
    except Exception as e:
        raise ValueError(f"Failed to load {config_path}: {e}") from e


def save_config(config: CollectionConfig) -> None:
    """保存配置到 ~/.config/qmd/index.yml"""
    ensure_config_dir()
    config_path = get_config_file_path()

    try:
        # 转换为字典，移除 None 值以保持 YAML 简洁
        data = config.model_dump(exclude_none=True)

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                indent=2,
                sort_keys=False,
            )
    except Exception as e:
        raise IOError(f"Failed to write {config_path}: {e}") from e


def get_collection(name: str) -> NamedCollection | None:
    """
    获取指定名称的 collection
    如果未找到返回 None
    """
    config = load_config()
    collection = config.collections.get(name)

    if collection is None:
        return None

    return NamedCollection(name=name, **collection.model_dump())


def list_collections() -> list[NamedCollection]:
    """列出所有 collections"""
    config = load_config()
    return [
        NamedCollection(name=name, **collection.model_dump())
        for name, collection in config.collections.items()
    ]


def add_collection(
    name: str,
    path: str,
    pattern: str = "**/*.md",
    context: dict[str, str] | None = None,
    update: str | None = None,
) -> None:
    """
    添加或更新一个 collection

    Args:
        name: Collection 名称
        path: 索引路径
        pattern: Glob 模式（默认 "**/*.md"）
        context: 可选的上下文映射
        update: 可选的更新命令
    """
    config = load_config()

    # 如果 collection 已存在，保留现有的 context（除非显式提供新的）
    existing = config.collections.get(name)
    if existing and context is None:
        context = existing.context

    config.collections[name] = Collection(
        path=path,
        pattern=pattern,
        context=context,
        update=update,
    )

    save_config(config)


def remove_collection(name: str) -> bool:
    """
    删除一个 collection

    Returns:
        如果删除成功返回 True，如果 collection 不存在返回 False
    """
    config = load_config()

    if name not in config.collections:
        return False

    del config.collections[name]
    save_config(config)
    return True


def rename_collection(old_name: str, new_name: str) -> bool:
    """
    重命名一个 collection

    Args:
        old_name: 旧名称
        new_name: 新名称

    Returns:
        如果重命名成功返回 True

    Raises:
        ValueError: 如果旧 collection 不存在或新名称已存在
    """
    config = load_config()

    if old_name not in config.collections:
        return False

    if new_name in config.collections:
        raise ValueError(f"Collection '{new_name}' already exists")

    config.collections[new_name] = config.collections[old_name]
    del config.collections[old_name]
    save_config(config)
    return True


# =============================================================================
# Context 管理
# =============================================================================

def get_global_context() -> str | None:
    """获取全局上下文"""
    config = load_config()
    return config.global_context


def set_global_context(context: str | None) -> None:
    """设置全局上下文"""
    config = load_config()
    config.global_context = context
    save_config(config)


def get_contexts(collection_name: str) -> dict[str, str] | None:
    """获取 collection 的所有上下文"""
    collection = get_collection(collection_name)
    return collection.context if collection else None


def add_context(
    collection_name: str,
    path_prefix: str,
    context_text: str
) -> bool:
    """
    为 collection 中的特定路径添加或更新上下文

    Args:
        collection_name: Collection 名称
        path_prefix: 路径前缀
        context_text: 上下文文本

    Returns:
        如果成功返回 True，如果 collection 不存在返回 False
    """
    config = load_config()
    collection = config.collections.get(collection_name)

    if collection is None:
        return False

    if collection.context is None:
        collection.context = {}

    collection.context[path_prefix] = context_text
    save_config(config)
    return True


def remove_context(collection_name: str, path_prefix: str) -> bool:
    """
    从 collection 中移除上下文

    Args:
        collection_name: Collection 名称
        path_prefix: 路径前缀

    Returns:
        如果成功返回 True，如果 collection 或上下文不存在返回 False
    """
    config = load_config()
    collection = config.collections.get(collection_name)

    if collection is None or collection.context is None:
        return False

    if path_prefix not in collection.context:
        return False

    del collection.context[path_prefix]

    # 移除空的 context 对象
    if not collection.context:
        collection.context = None

    save_config(config)
    return True


def list_all_contexts() -> list[dict[str, str]]:
    """
    列出所有 collections 的所有上下文

    Returns:
        包含 collection、path、context 的字典列表
    """
    config = load_config()
    results: list[dict[str, str]] = []

    # 添加全局上下文
    if config.global_context:
        results.append({
            "collection": "*",
            "path": "/",
            "context": config.global_context,
        })

    # 添加 collection 上下文
    for name, collection in config.collections.items():
        if collection.context:
            for path, context in collection.context.items():
                results.append({
                    "collection": name,
                    "path": path,
                    "context": context,
                })

    return results


def find_context_for_path(
    collection_name: str,
    file_path: str
) -> str | None:
    """
    为给定的 collection 和路径查找最匹配的上下文
    返回最具体的匹配上下文（最长路径前缀匹配）

    Args:
        collection_name: Collection 名称
        file_path: 文件路径

    Returns:
        匹配的上下文文本，如果没有匹配则返回全局上下文或 None
    """
    config = load_config()
    collection = config.collections.get(collection_name)

    if collection is None or collection.context is None:
        return config.global_context

    # 查找所有匹配的前缀
    matches: list[tuple[str, str]] = []  # (prefix, context)

    for prefix, context in collection.context.items():
        # 规范化路径以进行比较
        normalized_path = file_path if file_path.startswith("/") else f"/{file_path}"
        normalized_prefix = prefix if prefix.startswith("/") else f"/{prefix}"

        if normalized_path.startswith(normalized_prefix):
            matches.append((normalized_prefix, context))

    # 返回最具体的匹配（最长前缀）
    if matches:
        matches.sort(key=lambda x: len(x[0]), reverse=True)
        return matches[0][1]

    # 回退到全局上下文
    return config.global_context


# =============================================================================
# 工具函数
# =============================================================================

def get_config_path() -> Path:
    """获取配置文件路径（用于错误消息）"""
    return get_config_file_path()


def config_exists() -> bool:
    """检查配置文件是否存在"""
    return get_config_file_path().exists()


def is_valid_collection_name(name: str) -> bool:
    """
    验证 collection 名称
    Collection 名称必须有效且不包含特殊字符

    允许字母数字、连字符、下划线
    """
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", name))
