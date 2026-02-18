"""
内容哈希工具

提供 SHA256 哈希计算，用于内容去重和变更检测。
与 qmd 原版保持一致（前 6 位作为 docid）。
"""

import hashlib
from pathlib import Path

from loguru import logger


def content_hash(text: str) -> str:
    """
    计算文本内容的 SHA256 哈希值

    Args:
        text: 文本内容

    Returns:
        完整的 SHA256 哈希值（十六进制字符串）

    Examples:
        >>> content_hash("Hello, World!")
        "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
    """
    hash_obj = hashlib.sha256()
    hash_obj.update(text.encode("utf-8"))
    return hash_obj.hexdigest()


def file_hash(path: str | Path) -> str:
    """
    计算文件内容的 SHA256 哈希值

    Args:
        path: 文件路径

    Returns:
        完整的 SHA256 哈希值（十六进制字符串）

    Raises:
        FileNotFoundError: 如果文件不存在
        IOError: 如果读取文件失败

    Examples:
        >>> file_hash("/path/to/document.md")
        "a1b2c3d4e5f6..."
    """
    path_obj = Path(path)

    if not path_obj.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    if not path_obj.is_file():
        raise ValueError(f"路径不是文件: {path}")

    try:
        with open(path_obj, "r", encoding="utf-8") as f:
            content = f.read()
        return content_hash(content)
    except UnicodeDecodeError:
        # 尝试以二进制模式读取（处理非 UTF-8 文件）
        logger.warning(f"文件 {path} 不是 UTF-8 编码，使用二进制模式")
        hash_obj = hashlib.sha256()
        with open(path_obj, "rb") as f:
            # 分块读取大文件
            for chunk in iter(lambda: f.read(8192), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except Exception as e:
        raise IOError(f"读取文件失败 {path}: {e}") from e


def get_docid(hash_value: str) -> str:
    """
    从完整哈希值提取 docid（前 6 个字符）

    这与 qmd 原版一致，用于快速引用文档。

    Args:
        hash_value: 完整的哈希值

    Returns:
        前 6 个字符的短 ID

    Examples:
        >>> get_docid("a1b2c3d4e5f6789...")
        "a1b2c3"
    """
    return hash_value[:6]
