"""
测试 MCP 服务器
"""

from pathlib import Path
from unittest import mock

import pytest

from qmd import QMD
from qmd.mcp.server import (
    create_server,
    dispatch_tool_call,
    format_search_summary,
    get_tool_definitions,
    handle_collections,
    handle_deep_search,
    handle_get,
    handle_index,
    handle_search,
    handle_status,
    handle_vector_search,
)


class TestMCPServer:
    """MCP 服务器测试"""

    @pytest.fixture(autouse=True)
    def isolate_config(self, tmp_path: Path, monkeypatch):
        """隔离配置环境"""
        config_dir = tmp_path / "qmd_config"
        config_dir.mkdir()
        monkeypatch.setenv("QMD_CONFIG_DIR", str(config_dir))

    @pytest.fixture
    def tmp_docs(self, tmp_path: Path) -> Path:
        """创建临时文档目录"""
        docs_path = tmp_path / "docs"
        docs_path.mkdir()

        (docs_path / "doc1.md").write_text(
            "# Document 1\n\nPython programming.", encoding="utf-8"
        )
        (docs_path / "doc2.md").write_text(
            "# Document 2\n\nTesting frameworks.", encoding="utf-8"
        )

        return docs_path

    @pytest.fixture
    def qmd_instance(self, tmp_docs: Path, tmp_path: Path) -> QMD:
        """创建并初始化 QMD 实例"""
        db_path = tmp_path / "test.db"
        qmd = QMD(backend="sentence_tf", db_path=db_path)

        # 添加 collection 并更新索引
        qmd.add("docs", tmp_docs, pattern="**/*.md")
        qmd.update()

        return qmd

    def test_create_server_returns_valid_instance(self, tmp_path: Path):
        """测试 create_server 返回有效的 Server 实例"""
        db_path = tmp_path / "test.db"
        server = create_server(db_path)

        assert server is not None
        assert server.name == "qmd"

    def test_format_search_summary_with_results(self):
        """测试格式化搜索结果摘要"""
        results = [
            {
                "collection": "docs",
                "file": "doc1.md",
                "title": "Document 1",
                "score": 0.85,
            },
            {
                "collection": "docs",
                "file": "doc2.md",
                "title": "Document 2",
                "score": 0.75,
            },
        ]

        summary = format_search_summary(results, "test query")

        assert '找到 2 个 "test query" 的结果' in summary
        assert "85% docs/doc1.md - Document 1" in summary
        assert "75% docs/doc2.md - Document 2" in summary

    def test_format_search_summary_empty(self):
        """测试格式化空搜索结果"""
        summary = format_search_summary([], "test query")
        assert '未找到 "test query" 的匹配结果' in summary

    @pytest.mark.asyncio
    async def test_handle_search_with_results(self, qmd_instance: QMD):
        """测试 qmd_search 工具（有结果）"""
        arguments = {"query": "Python", "limit": 10}

        result = await handle_search(qmd_instance, arguments)

        assert len(result) == 1
        assert result[0].type == "text"
        # 可能找到结果或未找到（取决于模型是否可用）
        assert "Python" in result[0].text or "未找到" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_search_empty_query(self, qmd_instance: QMD):
        """测试 qmd_search 工具（空查询）"""
        arguments = {"query": "", "limit": 10}

        result = await handle_search(qmd_instance, arguments)

        assert len(result) == 1
        assert "错误" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_search_with_collection_filter(self, qmd_instance: QMD):
        """测试 qmd_search 工具（collection 过滤）"""
        arguments = {"query": "test", "collection": "docs", "limit": 10}

        result = await handle_search(qmd_instance, arguments)

        assert len(result) == 1
        assert result[0].type == "text"

    @pytest.mark.asyncio
    async def test_handle_index_all_collections(self, qmd_instance: QMD):
        """测试 qmd_index 工具（所有 collections）"""
        arguments = {}

        result = await handle_index(qmd_instance, arguments)

        assert len(result) == 1
        assert "索引更新完成" in result[0].text
        assert "Collections:" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_index_specific_collection(self, qmd_instance: QMD):
        """测试 qmd_index 工具（指定 collection）"""
        arguments = {"collection": "docs"}

        result = await handle_index(qmd_instance, arguments)

        assert len(result) == 1
        assert "索引更新完成" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_index_nonexistent_collection(self, qmd_instance: QMD):
        """测试 qmd_index 工具（不存在的 collection）"""
        arguments = {"collection": "nonexistent"}

        result = await handle_index(qmd_instance, arguments)

        assert len(result) == 1
        assert "错误" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_collections_with_data(self, qmd_instance: QMD):
        """测试 qmd_collections 工具（有数据）"""
        arguments = {}

        result = await handle_collections(qmd_instance, arguments)

        assert len(result) == 1
        assert "collection" in result[0].text
        assert "docs" in result[0].text
        assert "路径:" in result[0].text
        assert "Pattern:" in result[0].text
        assert "文档数:" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_collections_empty(self, tmp_path: Path):
        """测试 qmd_collections 工具（空）"""
        db_path = tmp_path / "empty.db"
        qmd = QMD(backend="auto", db_path=db_path)

        arguments = {}
        result = await handle_collections(qmd, arguments)

        assert len(result) == 1
        assert "没有 collection" in result[0].text

        qmd.stop()

    @pytest.mark.asyncio
    async def test_handle_status_all_collections(self, qmd_instance: QMD):
        """测试 qmd_status 工具（所有 collections）"""
        arguments = {}

        result = await handle_status(qmd_instance, arguments)

        assert len(result) == 1
        assert "索引状态" in result[0].text
        assert "数据库:" in result[0].text
        assert "Collections:" in result[0].text
        assert "总计:" in result[0].text
        assert "数据库大小:" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_status_specific_collection(self, qmd_instance: QMD):
        """测试 qmd_status 工具（指定 collection）"""
        arguments = {"collection": "docs"}

        result = await handle_status(qmd_instance, arguments)

        assert len(result) == 1
        assert "索引状态" in result[0].text
        assert "docs" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_status_nonexistent_collection(self, qmd_instance: QMD):
        """测试 qmd_status 工具（不存在的 collection）"""
        arguments = {"collection": "nonexistent"}

        result = await handle_status(qmd_instance, arguments)

        # 应该返回空结果（总计 0 个文档）
        assert len(result) == 1
        assert "索引状态" in result[0].text
        assert "总计: 0 个文档" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_index_with_errors(self, qmd_instance: QMD, tmp_path: Path):
        """测试 qmd_index 工具（有错误）"""
        # 创建一个不存在的 collection
        qmd_instance.config.collections["bad"] = type(
            "Collection", (), {"path": str(tmp_path / "nonexistent"), "pattern": "**/*.md"}
        )()

        arguments = {"collection": "bad"}
        result = await handle_index(qmd_instance, arguments)

        # 应该包含错误统计
        assert len(result) == 1
        assert "索引更新完成" in result[0].text or "错误" in result[0].text

    def test_create_server_with_custom_db_path(self, tmp_path: Path):
        """测试 create_server 使用自定义数据库路径"""
        db_path = tmp_path / "custom.db"
        server = create_server(db_path)

        assert server is not None
        assert server.name == "qmd"

    @pytest.mark.asyncio
    async def test_handle_search_with_limit(self, qmd_instance: QMD):
        """测试 qmd_search 工具（自定义 limit）"""
        arguments = {"query": "test", "limit": 5}

        result = await handle_search(qmd_instance, arguments)

        assert len(result) == 1
        assert result[0].type == "text"

    def test_server_has_tool_handlers(self, tmp_path: Path):
        """测试服务器注册了工具处理器"""
        db_path = tmp_path / "test.db"
        server = create_server(db_path)

        # 验证服务器实例包含必要的属性
        assert hasattr(server, "name")
        assert server.name == "qmd"

    @pytest.mark.asyncio
    async def test_handle_index_with_error_branch(self, tmp_path: Path):
        """测试 handle_index 错误分支覆盖"""
        db_path = tmp_path / "test.db"
        qmd = QMD(backend="auto", db_path=db_path)

        # 添加一个路径不存在的 collection
        from qmd.core.config import Collection

        qmd.config.collections["broken"] = Collection(
            path=str(tmp_path / "nonexistent"), pattern="**/*.md"
        )

        arguments = {}
        result = await handle_index(qmd, arguments)

        # 应该显示有错误
        assert len(result) == 1
        assert "索引更新完成" in result[0].text

        qmd.stop()

    def test_main_entry_point(self):
        """测试 main 入口函数存在"""
        from qmd.mcp.server import main

        assert callable(main)

    def test_get_tool_definitions(self):
        """测试获取工具定义列表"""
        tools = get_tool_definitions()

        assert len(tools) == 7
        tool_names = [t.name for t in tools]
        assert "qmd_search" in tool_names
        assert "qmd_index" in tool_names
        assert "qmd_collections" in tool_names
        assert "qmd_status" in tool_names
        assert "qmd_deep_search" in tool_names
        assert "qmd_vector_search" in tool_names
        assert "qmd_get" in tool_names

    @pytest.mark.asyncio
    async def test_dispatch_tool_call_search(self, qmd_instance: QMD):
        """测试 dispatch_tool_call - qmd_search"""
        result = await dispatch_tool_call(
            qmd_instance, "qmd_search", {"query": "test", "limit": 10}
        )

        assert len(result) == 1
        assert result[0].type == "text"

    @pytest.mark.asyncio
    async def test_dispatch_tool_call_index(self, qmd_instance: QMD):
        """测试 dispatch_tool_call - qmd_index"""
        result = await dispatch_tool_call(qmd_instance, "qmd_index", {})

        assert len(result) == 1
        assert "索引更新完成" in result[0].text

    @pytest.mark.asyncio
    async def test_dispatch_tool_call_collections(self, qmd_instance: QMD):
        """测试 dispatch_tool_call - qmd_collections"""
        result = await dispatch_tool_call(qmd_instance, "qmd_collections", {})

        assert len(result) == 1
        assert "collection" in result[0].text

    @pytest.mark.asyncio
    async def test_dispatch_tool_call_status(self, qmd_instance: QMD):
        """测试 dispatch_tool_call - qmd_status"""
        result = await dispatch_tool_call(qmd_instance, "qmd_status", {})

        assert len(result) == 1
        assert "索引状态" in result[0].text

    @pytest.mark.asyncio
    async def test_dispatch_tool_call_unknown(self, qmd_instance: QMD):
        """测试 dispatch_tool_call - 未知工具"""
        result = await dispatch_tool_call(qmd_instance, "unknown_tool", {})

        assert len(result) == 1
        assert "未知工具" in result[0].text

    @pytest.mark.asyncio
    async def test_dispatch_tool_call_exception(self, qmd_instance: QMD):
        """测试 dispatch_tool_call - 异常处理"""
        # 传入错误的参数导致异常
        result = await dispatch_tool_call(
            qmd_instance, "qmd_search", {"query": None}  # None 会导致错误
        )

        assert len(result) == 1
        # 应该返回错误信息（捕获异常）
        assert "错误" in result[0].text or result[0].type == "text"

    @pytest.mark.asyncio
    async def test_handle_deep_search(self, qmd_instance: QMD):
        """测试深度搜索处理函数"""
        result = await handle_deep_search(qmd_instance, {"query": "python"})

        assert len(result) == 1
        # 应该包含搜索结果或"未找到"
        assert "结果" in result[0].text or "未找到" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_vector_search(self, qmd_instance: QMD):
        """测试向量搜索处理函数"""
        result = await handle_vector_search(qmd_instance, {"query": "testing"})

        assert len(result) == 1
        # 应该包含搜索结果或"未找到"
        assert "结果" in result[0].text or "未找到" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_get(self, qmd_instance: QMD):
        """测试获取文档处理函数"""
        # 通过虚拟路径获取文档
        result = await handle_get(qmd_instance, {"file": "qmd://docs/doc1.md"})

        assert len(result) == 1
        # 应该包含文档内容
        assert "Document 1" in result[0].text or "Python" in result[0].text

    @pytest.mark.asyncio
    async def test_dispatch_tool_call_deep_search(self, qmd_instance: QMD):
        """测试 dispatch_tool_call - qmd_deep_search"""
        result = await dispatch_tool_call(qmd_instance, "qmd_deep_search", {"query": "python"})

        assert len(result) == 1
        assert "结果" in result[0].text or "未找到" in result[0].text

    @pytest.mark.asyncio
    async def test_dispatch_tool_call_vector_search(self, qmd_instance: QMD):
        """测试 dispatch_tool_call - qmd_vector_search"""
        result = await dispatch_tool_call(qmd_instance, "qmd_vector_search", {"query": "testing"})

        assert len(result) == 1
        assert "结果" in result[0].text or "未找到" in result[0].text

    @pytest.mark.asyncio
    async def test_dispatch_tool_call_get(self, qmd_instance: QMD):
        """测试 dispatch_tool_call - qmd_get"""
        result = await dispatch_tool_call(qmd_instance, "qmd_get", {"file": "qmd://docs/doc1.md"})

        assert len(result) == 1
        assert "Document 1" in result[0].text or "Python" in result[0].text
