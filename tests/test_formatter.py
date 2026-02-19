"""
测试输出格式化器
"""

import json

import pytest

from qmd.cli.formatter import (
    add_line_numbers,
    documents_to_csv,
    documents_to_files,
    documents_to_json,
    documents_to_markdown,
    documents_to_xml,
    escape_csv,
    escape_xml,
    format_documents,
    format_search_results,
    get_docid,
    search_results_to_csv,
    search_results_to_files,
    search_results_to_json,
    search_results_to_markdown,
    search_results_to_mcp_csv,
    search_results_to_xml,
)


class TestHelperFunctions:
    """测试辅助函数"""

    def test_add_line_numbers(self):
        """测试添加行号"""
        text = "line 1\nline 2\nline 3"
        result = add_line_numbers(text)
        assert result == "1: line 1\n2: line 2\n3: line 3"

        # 自定义起始行号
        result = add_line_numbers(text, start_line=10)
        assert result == "10: line 1\n11: line 2\n12: line 3"

    def test_get_docid(self):
        """测试提取 docid"""
        hash_value = "abc123def456"
        assert get_docid(hash_value) == "abc123"

    def test_escape_csv(self):
        """测试 CSV 转义"""
        # 普通字符串
        assert escape_csv("hello") == "hello"

        # 包含逗号
        assert escape_csv("hello,world") == '"hello,world"'

        # 包含双引号
        assert escape_csv('say "hello"') == '"say ""hello"""'

        # 包含换行符
        assert escape_csv("line1\nline2") == '"line1\nline2"'

        # None 值
        assert escape_csv(None) == ""

        # 数字
        assert escape_csv(123) == "123"

    def test_escape_xml(self):
        """测试 XML 转义"""
        text = '<tag attr="value"> & < > \' "'
        result = escape_xml(text)
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result
        assert "&quot;" in result
        assert "&apos;" in result


class TestSearchResultFormatters:
    """测试搜索结果格式化器"""

    @pytest.fixture
    def sample_results(self):
        """测试数据"""
        return [
            {
                "file": "test.md",
                "title": "Test Document",
                "body": "This is a test document.\nWith multiple lines.\nContains test keyword.",
                "score": 0.8545,
                "collection": "docs",
                "hash": "abc123def456",
                "pos": 0,
                "context": "Test context",
            },
            {
                "file": "another.md",
                "title": "Another Document",
                "body": "Another test document.",
                "score": 0.6234,
                "collection": "docs",
                "hash": "xyz789ghi012",
                "pos": 0,
                "context": None,
            },
        ]

    def test_search_results_to_json(self, sample_results):
        """测试 JSON 格式化"""
        result = search_results_to_json(sample_results, {"query": "test"})
        data = json.loads(result)

        assert len(data) == 2
        assert data[0]["docid"] == "#abc123"
        assert data[0]["score"] == 0.85
        assert data[0]["file"] == "test.md"
        assert data[0]["title"] == "Test Document"
        assert data[0]["context"] == "Test context"
        assert "snippet" in data[0]

        # 第二个结果没有 context
        assert "context" not in data[1]

    def test_search_results_to_json_full(self, sample_results):
        """测试 JSON 格式化（full 选项）"""
        result = search_results_to_json(sample_results, {"query": "test", "full": True})
        data = json.loads(result)

        assert "body" in data[0]
        assert "snippet" not in data[0]
        assert "This is a test document" in data[0]["body"]

    def test_search_results_to_json_line_numbers(self, sample_results):
        """测试 JSON 格式化（line_numbers 选项）"""
        result = search_results_to_json(
            sample_results, {"query": "test", "line_numbers": True}
        )
        data = json.loads(result)

        # snippet 应该包含行号
        assert "1:" in data[0]["snippet"] or "2:" in data[0]["snippet"]

    def test_search_results_to_csv(self, sample_results):
        """测试 CSV 格式化"""
        result = search_results_to_csv(sample_results, {"query": "test"})
        lines = result.split("\n")

        # 检查表头
        assert lines[0] == "docid,score,file,title,context,line,snippet"

        # 检查第一行数据
        assert lines[1].startswith("#abc123,0.8545")
        assert "test.md" in lines[1]
        assert "Test Document" in lines[1]

    def test_search_results_to_files(self, sample_results):
        """测试 files 格式化"""
        result = search_results_to_files(sample_results)
        lines = result.split("\n")

        assert len(lines) == 2
        assert lines[0].startswith("#abc123,0.85,test.md")
        assert '"Test context"' in lines[0]
        assert lines[1].startswith("#xyz789,0.62,another.md")

    def test_search_results_to_markdown(self, sample_results):
        """测试 Markdown 格式化"""
        result = search_results_to_markdown(sample_results, {"query": "test"})

        assert "# Test Document" in result
        assert "**docid:** `#abc123`" in result
        assert "**context:** Test context" in result
        assert "---" in result

    def test_search_results_to_xml(self, sample_results):
        """测试 XML 格式化"""
        result = search_results_to_xml(sample_results, {"query": "test"})

        assert '<file docid="#abc123"' in result
        assert 'name="test.md"' in result
        assert 'title="Test Document"' in result
        assert 'context="Test context"' in result
        assert "</file>" in result

    def test_search_results_to_mcp_csv(self):
        """测试 MCP CSV 格式化"""
        results = [
            {
                "docid": "abc123",
                "file": "test.md",
                "title": "Test",
                "score": 0.85,
                "context": "Context",
                "snippet": "Snippet text",
            }
        ]
        result = search_results_to_mcp_csv(results)
        lines = result.split("\n")

        assert lines[0] == "docid,file,title,score,context,snippet"
        assert lines[1].startswith("#abc123,test.md,Test,0.85")


class TestDocumentFormatters:
    """测试文档格式化器"""

    @pytest.fixture
    def sample_documents(self):
        """测试数据"""
        return [
            {
                "displayPath": "doc1.md",
                "title": "Document 1",
                "body": "Content of document 1",
                "context": "Context 1",
                "skipped": False,
            },
            {
                "displayPath": "doc2.md",
                "title": "Document 2",
                "body": "",
                "context": None,
                "skipped": True,
                "skipReason": "File too large",
            },
        ]

    def test_documents_to_json(self, sample_documents):
        """测试文档 JSON 格式化"""
        result = documents_to_json(sample_documents)
        data = json.loads(result)

        assert len(data) == 2
        assert data[0]["file"] == "doc1.md"
        assert data[0]["title"] == "Document 1"
        assert data[0]["context"] == "Context 1"
        assert data[0]["body"] == "Content of document 1"

        # 第二个文档被跳过
        assert data[1]["skipped"] is True
        assert data[1]["reason"] == "File too large"
        assert "body" not in data[1]

    def test_documents_to_csv(self, sample_documents):
        """测试文档 CSV 格式化"""
        result = documents_to_csv(sample_documents)
        lines = result.split("\n")

        assert lines[0] == "file,title,context,skipped,body"
        assert "doc1.md" in lines[1]
        assert "false" in lines[1]
        assert "doc2.md" in lines[2]
        assert "true" in lines[2]

    def test_documents_to_files(self, sample_documents):
        """测试文档 files 格式化"""
        result = documents_to_files(sample_documents)
        lines = result.split("\n")

        assert lines[0] == 'doc1.md,"Context 1"'
        assert lines[1] == "doc2.md,[SKIPPED]"

    def test_documents_to_markdown(self, sample_documents):
        """测试文档 Markdown 格式化"""
        result = documents_to_markdown(sample_documents)

        assert "## doc1.md" in result
        assert "**Title:** Document 1" in result
        assert "**Context:** Context 1" in result
        assert "```" in result
        assert "Content of document 1" in result

        assert "## doc2.md" in result
        assert "> File too large" in result

    def test_documents_to_xml(self, sample_documents):
        """测试文档 XML 格式化"""
        result = documents_to_xml(sample_documents)

        assert '<?xml version="1.0" encoding="UTF-8"?>' in result
        assert "<documents>" in result
        assert "<document>" in result
        assert "<file>doc1.md</file>" in result
        assert "<title>Document 1</title>" in result
        assert "<context>Context 1</context>" in result
        assert "<body>Content of document 1</body>" in result

        assert "<skipped>true</skipped>" in result
        assert "<reason>File too large</reason>" in result


class TestMainEntryFunctions:
    """测试主入口函数"""

    @pytest.fixture
    def sample_results(self):
        """测试数据"""
        return [
            {
                "file": "test.md",
                "title": "Test",
                "body": "Test content",
                "score": 0.85,
                "collection": "docs",
                "hash": "abc123",
                "pos": 0,
                "context": None,
            }
        ]

    @pytest.fixture
    def sample_documents(self):
        """测试数据"""
        return [
            {
                "displayPath": "doc.md",
                "title": "Doc",
                "body": "Content",
                "context": None,
                "skipped": False,
            }
        ]

    def test_format_search_results_json(self, sample_results):
        """测试 format_search_results 函数（JSON）"""
        result = format_search_results(sample_results, "json", {"query": "test"})
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["file"] == "test.md"

    def test_format_search_results_csv(self, sample_results):
        """测试 format_search_results 函数（CSV）"""
        result = format_search_results(sample_results, "csv", {"query": "test"})
        assert "docid,score,file,title,context,line,snippet" in result

    def test_format_search_results_xml(self, sample_results):
        """测试 format_search_results 函数（XML）"""
        result = format_search_results(sample_results, "xml", {"query": "test"})
        assert "<file" in result

    def test_format_search_results_md(self, sample_results):
        """测试 format_search_results 函数（Markdown）"""
        result = format_search_results(sample_results, "md", {"query": "test"})
        assert "# Test" in result

    def test_format_search_results_files(self, sample_results):
        """测试 format_search_results 函数（files）"""
        result = format_search_results(sample_results, "files")
        assert "#abc123" in result

    def test_format_documents_json(self, sample_documents):
        """测试 format_documents 函数（JSON）"""
        result = format_documents(sample_documents, "json")
        data = json.loads(result)
        assert len(data) == 1

    def test_format_documents_csv(self, sample_documents):
        """测试 format_documents 函数（CSV）"""
        result = format_documents(sample_documents, "csv")
        assert "file,title,context,skipped,body" in result

    def test_format_documents_xml(self, sample_documents):
        """测试 format_documents 函数（XML）"""
        result = format_documents(sample_documents, "xml")
        assert "<document>" in result

    def test_format_documents_md(self, sample_documents):
        """测试 format_documents 函数（Markdown）"""
        result = format_documents(sample_documents, "md")
        assert "## doc.md" in result

    def test_format_documents_files(self, sample_documents):
        """测试 format_documents 函数（files）"""
        result = format_documents(sample_documents, "files")
        assert "doc.md" in result
