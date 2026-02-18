"""
路径处理工具

提供配置和数据目录路径管理，支持 XDG 规范。
"""

import os
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
