"""
MCP 服务器模块

提供 Model Context Protocol 服务器实现，
通过 stdio transport 与 Claude Desktop 等客户端通信。
"""

from qmd.mcp.server import create_server, serve

__all__ = ["create_server", "serve"]
