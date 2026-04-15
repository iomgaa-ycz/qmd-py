"""
qmd CLI 模块

提供命令行接口功能。新 CLI 入口为 qmd.cli.__main__:main。
旧 CLI（qmd.cli.main）保留至 M3，通过 python -m qmd.cli.main 访问。
"""

from qmd.cli.__main__ import main

__all__ = ["main"]
