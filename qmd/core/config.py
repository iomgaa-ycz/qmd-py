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
    为给定的 collection 和路径查找匹配的上下文（层级继承）

    收集所有匹配的上下文（global + 所有匹配的路径前缀），
    按照从通用到具体的顺序拼接（使用 \\n\\n 分隔）。

    Args:
        collection_name: Collection 名称
        file_path: 文件路径

    Returns:
        拼接后的上下文文本，如果没有任何匹配则返回 None
    """
    config = load_config()
    collection = config.collections.get(collection_name)

    if collection is None:
        return config.global_context

    # 收集所有匹配的上下文（从通用到具体）
    contexts: list[str] = []

    # 1. 添加全局上下文（如果有）
    if config.global_context:
        contexts.append(config.global_context)

    # 2. 添加所有匹配的路径上下文
    if collection.context:
        normalized_path = file_path if file_path.startswith("/") else f"/{file_path}"

        # 收集所有匹配的前缀
        matching_contexts: list[tuple[str, str]] = []  # (prefix, context)
        for prefix, context in collection.context.items():
            normalized_prefix = prefix if prefix.startswith("/") else f"/{prefix}"
            if normalized_path.startswith(normalized_prefix):
                matching_contexts.append((normalized_prefix, context))

        # 按前缀长度排序（从短到长，即从通用到具体）
        matching_contexts.sort(key=lambda x: len(x[0]))

        # 添加所有匹配的上下文
        for _, context in matching_contexts:
            contexts.append(context)

    # 3. 拼接所有上下文（用双换行符分隔）
    return "\n\n".join(contexts) if contexts else None


def find_context_for_file(
    file_path: str
) -> str | None:
    """
    为给定的文件路径查找匹配的上下文（支持虚拟路径和文件系统路径）

    Args:
        file_path: 虚拟路径（qmd://collection/path）或文件系统绝对路径

    Returns:
        拼接后的上下文文本，如果没有任何匹配则返回 None
    """
    if not file_path:
        return None

    # 导入 VirtualPath 工具（避免循环导入）
    from qmd.utils.paths import is_virtual_path, parse_virtual_path

    collection_name: str | None = None
    relative_path: str | None = None

    # 1. 尝试解析虚拟路径格式: qmd://collection/path
    if is_virtual_path(file_path):
        parsed = parse_virtual_path(file_path)
        if parsed:
            collection_name = parsed.collection_name
            relative_path = parsed.path
    else:
        # 2. 文件系统路径：查找属于哪个 collection
        collections = list_collections()
        for coll in collections:
            if not coll.path:
                continue

            coll_path = Path(coll.path).resolve()
            try:
                file_resolved = Path(file_path).resolve()
                # 检查文件路径是否在 collection 路径下
                if file_resolved == coll_path or coll_path in file_resolved.parents:
                    collection_name = coll.name
                    # 提取相对路径
                    relative_path = str(file_resolved.relative_to(coll_path))
                    break
            except (ValueError, OSError):
                # 路径解析失败（例如路径不存在或无法计算相对路径）
                continue

    # 3. 如果无法确定 collection，返回 None
    if not collection_name or relative_path is None:
        return None

    # 4. 调用 find_context_for_path() 获取层级继承的 context
    return find_context_for_path(collection_name, relative_path)


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
