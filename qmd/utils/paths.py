"""
路径处理工具

提供配置和数据目录路径管理，支持 XDG 规范。
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger


def get_config_dir() -> Path:
    """
    获取配置目录路径

    优先级:
    1. QMD_CONFIG_DIR 环境变量（用于测试）
    2. XDG_CONFIG_HOME/qmd（遵循 XDG 规范）
    3. ~/.config/qmd（默认）

    Returns:
        配置目录路径
    """
    if qmd_config_dir := os.getenv("QMD_CONFIG_DIR"):
        return Path(qmd_config_dir)

    if xdg_config_home := os.getenv("XDG_CONFIG_HOME"):
        return Path(xdg_config_home) / "qmd"

    return Path.home() / ".config" / "qmd"


def get_data_dir() -> Path:
    """
    获取数据目录路径（用于缓存、数据库等）

    优先级:
    1. QMD_DATA_DIR 环境变量（用于测试）
    2. XDG_CACHE_HOME/qmd（遵循 XDG 规范）
    3. ~/.cache/qmd（默认）

    Returns:
        数据目录路径
    """
    if qmd_data_dir := os.getenv("QMD_DATA_DIR"):
        return Path(qmd_data_dir)

    if xdg_cache_home := os.getenv("XDG_CACHE_HOME"):
        return Path(xdg_cache_home) / "qmd"

    return Path.home() / ".cache" / "qmd"


def resolve_doc_path(collection_path: str, doc_path: str) -> str:
    """
    解析文档相对路径

    将文档路径转换为相对于 collection 根目录的规范路径。

    Args:
        collection_path: Collection 根目录路径
        doc_path: 文档的绝对或相对路径

    Returns:
        相对于 collection 的规范路径

    Examples:
        >>> resolve_doc_path("/home/user/docs", "/home/user/docs/2024/report.md")
        "2024/report.md"
        >>> resolve_doc_path("/home/user/docs", "2024/report.md")
        "2024/report.md"
    """
    collection_path_obj = Path(collection_path).resolve()
    doc_path_obj = Path(doc_path).resolve()

    try:
        # 尝试计算相对路径
        relative_path = doc_path_obj.relative_to(collection_path_obj)
        return normalize_path(str(relative_path))
    except ValueError:
        # 如果文档不在 collection 下，记录警告并返回原路径
        logger.warning(
            f"文档 {doc_path} 不在 collection {collection_path} 下"
        )
        return normalize_path(doc_path)


def normalize_path(path: str) -> str:
    """
    规范化路径分隔符

    将路径中的反斜杠统一转换为正斜杠，并清理多余的斜杠。

    Args:
        path: 原始路径

    Returns:
        规范化后的路径

    Examples:
        >>> normalize_path("docs\\\\2024\\\\report.md")
        "docs/2024/report.md"
        >>> normalize_path("docs//2024//report.md")
        "docs/2024/report.md"
    """
    # 将反斜杠转换为正斜杠
    normalized = path.replace("\\", "/")

    # 使用 Path 规范化路径（处理 .. 和 .）
    # 对于绝对路径和相对路径都适用
    if normalized.startswith("/"):
        # 绝对路径
        result = str(Path(normalized))
    else:
        # 相对路径
        result = str(Path(normalized))

    # 再次确保使用正斜杠（Windows 上 Path 可能返回反斜杠）
    return result.replace("\\", "/")


def handelize(path: str) -> str:
    """
    将路径转换为 token-friendly 格式

    清理路径，使其更适合用作文档标识符：
    - 统一分隔符为 /
    - 移除前导 ./
    - 移除尾部斜杠

    Args:
        path: 原始路径

    Returns:
        规范化后的路径

    Examples:
        >>> handelize("./docs/report.md")
        "docs/report.md"
        >>> handelize("docs/")
        "docs"
    """
    normalized = normalize_path(path)

    # 移除前导 ./
    if normalized.startswith("./"):
        normalized = normalized[2:]

    # 移除尾部斜杠
    if normalized.endswith("/"):
        normalized = normalized[:-1]

    return normalized


def get_file_stats(file_path: str) -> dict[str, str]:
    """
    获取文件统计信息

    Args:
        file_path: 文件路径

    Returns:
        包含 created_at 和 modified_at 的字典（ISO 8601 格式）
    """
    try:
        path = Path(file_path)
        if not path.exists():
            # 文件不存在，返回当前时间
            now = datetime.now(timezone.utc).isoformat()
            return {"created_at": now, "modified_at": now}

        stat = path.stat()

        # 创建时间（st_birthtime 在某些系统上不可用）
        try:
            created_timestamp = stat.st_birthtime
        except AttributeError:
            # 使用 ctime（metadata 修改时间）作为 fallback
            created_timestamp = stat.st_ctime

        created_at = datetime.fromtimestamp(created_timestamp, tz=timezone.utc).isoformat()
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

        return {"created_at": created_at, "modified_at": modified_at}

    except Exception as e:
        logger.warning(f"获取文件统计信息失败: {file_path} - {e}")
        now = datetime.now(timezone.utc).isoformat()
        return {"created_at": now, "modified_at": now}


# ==============================================================================
# VirtualPath 系统 — qmd://collection/path URI 支持
# ==============================================================================


@dataclass
class VirtualPath:
    """解析后的虚拟路径

    Attributes:
        collection_name: 集合名称
        path: 集合内的相对路径
    """

    collection_name: str
    path: str


def normalize_virtual_path(input_str: str) -> str:
    """规范化虚拟路径（去空格、统一前缀）

    Args:
        input_str: 虚拟路径字符串

    Returns:
        规范化后的虚拟路径
    """
    # 去除前后空格
    normalized = input_str.strip()

    # 确保有 qmd:// 前缀
    if not normalized.startswith("qmd://"):
        if normalized.startswith("//"):
            normalized = "qmd:" + normalized
        else:
            normalized = "qmd://" + normalized

    return normalized


def parse_virtual_path(virtual_path: str) -> VirtualPath | None:
    """解析 qmd://collection/path 格式

    Args:
        virtual_path: 虚拟路径字符串

    Returns:
        VirtualPath 对象，如果格式无效返回 None

    Examples:
        >>> parse_virtual_path("qmd://notes/file.md")
        VirtualPath(collection_name='notes', path='file.md')
        >>> parse_virtual_path("qmd://docs/subfolder/file.md")
        VirtualPath(collection_name='docs', path='subfolder/file.md')
        >>> parse_virtual_path("invalid")
        None
    """
    if not virtual_path or not isinstance(virtual_path, str):
        return None

    # 只处理以 qmd:// 开头的路径（避免误判其他协议）
    stripped = virtual_path.strip()
    if not stripped.startswith("qmd://"):
        return None

    # 规范化
    normalized = normalize_virtual_path(virtual_path)

    # 移除 qmd:// 前缀
    if not normalized.startswith("qmd://"):
        return None

    remainder = normalized[6:]  # 去掉 "qmd://"

    # 至少需要 collection/path 格式
    if not remainder or "/" not in remainder:
        return None

    # 分割 collection 和 path
    parts = remainder.split("/", 1)
    if len(parts) != 2:
        return None

    collection_name, path = parts

    if not collection_name or not path:
        return None

    return VirtualPath(collection_name=collection_name, path=path)


def build_virtual_path(collection_name: str, path: str) -> str:
    """构建 qmd://collection/path 格式

    Args:
        collection_name: 集合名称
        path: 集合内的相对路径

    Returns:
        虚拟路径字符串

    Examples:
        >>> build_virtual_path("notes", "file.md")
        'qmd://notes/file.md'
        >>> build_virtual_path("docs", "subfolder/file.md")
        'qmd://docs/subfolder/file.md'
    """
    # 移除 path 开头的斜杠（如果有）
    clean_path = path.lstrip("/")

    return f"qmd://{collection_name}/{clean_path}"


def is_virtual_path(path: str) -> bool:
    """判断是否为 qmd:// 格式

    Args:
        path: 路径字符串

    Returns:
        True 如果是虚拟路径格式

    Examples:
        >>> is_virtual_path("qmd://notes/file.md")
        True
        >>> is_virtual_path("/absolute/path/file.md")
        False
        >>> is_virtual_path("relative/path.md")
        False
    """
    if not path or not isinstance(path, str):
        return False

    return path.strip().startswith("qmd://")
