"""
工具函数测试

测试路径处理、哈希计算、文本摘要提取
"""

import os
import tempfile
from pathlib import Path

import pytest

from qmd.utils.hashing import content_hash, file_hash, get_docid
from qmd.utils.paths import (
    VirtualPath,
    build_virtual_path,
    get_config_dir,
    get_data_dir,
    is_virtual_path,
    normalize_path,
    normalize_virtual_path,
    parse_virtual_path,
    resolve_doc_path,
)
from qmd.utils.snippet import extract_snippet, extract_title


# =============================================================================
# 路径工具测试
# =============================================================================

class TestPaths:
    """测试路径处理工具"""

    def test_get_config_dir_default(self, monkeypatch):
        """测试默认配置目录"""
        monkeypatch.delenv("QMD_CONFIG_DIR", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

        config_dir = get_config_dir()
        expected = Path.home() / ".config" / "qmd"
        assert config_dir == expected

    def test_get_config_dir_with_xdg(self, monkeypatch, tmp_path):
        """测试 XDG_CONFIG_HOME 环境变量"""
        xdg_home = tmp_path / "xdg_config"
        monkeypatch.delenv("QMD_CONFIG_DIR", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_home))

        config_dir = get_config_dir()
        expected = xdg_home / "qmd"
        assert config_dir == expected

    def test_get_config_dir_with_qmd_env(self, monkeypatch, tmp_path):
        """测试 QMD_CONFIG_DIR 环境变量优先级最高"""
        qmd_dir = tmp_path / "qmd_config"
        monkeypatch.setenv("QMD_CONFIG_DIR", str(qmd_dir))

        config_dir = get_config_dir()
        assert config_dir == qmd_dir

    def test_get_data_dir_default(self, monkeypatch):
        """测试默认数据目录"""
        monkeypatch.delenv("QMD_DATA_DIR", raising=False)
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)

        data_dir = get_data_dir()
        expected = Path.home() / ".cache" / "qmd"
        assert data_dir == expected

    def test_get_data_dir_with_xdg(self, monkeypatch, tmp_path):
        """测试 XDG_CACHE_HOME 环境变量"""
        xdg_cache = tmp_path / "xdg_cache"
        monkeypatch.delenv("QMD_DATA_DIR", raising=False)
        monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_cache))

        data_dir = get_data_dir()
        expected = xdg_cache / "qmd"
        assert data_dir == expected

    def test_get_data_dir_with_qmd_env(self, monkeypatch, tmp_path):
        """测试 QMD_DATA_DIR 环境变量优先级最高"""
        qmd_dir = tmp_path / "qmd_data"
        monkeypatch.setenv("QMD_DATA_DIR", str(qmd_dir))

        data_dir = get_data_dir()
        assert data_dir == qmd_dir

    def test_normalize_path_backslash(self):
        """测试反斜杠转换"""
        path = "docs\\2024\\report.md"
        normalized = normalize_path(path)
        assert "\\" not in normalized
        assert "docs" in normalized
        assert "2024" in normalized

    def test_normalize_path_double_slash(self):
        """测试双斜杠清理"""
        path = "docs//2024//report.md"
        normalized = normalize_path(path)
        assert "//" not in normalized

    def test_normalize_path_mixed(self):
        """测试混合斜杠"""
        path = "docs\\2024/subfolder\\file.md"
        normalized = normalize_path(path)
        assert "\\" not in normalized
        assert "/" in normalized

    def test_resolve_doc_path_absolute(self, tmp_path):
        """测试解析绝对路径"""
        collection_path = tmp_path / "docs"
        doc_path = collection_path / "2024" / "report.md"

        # 创建目录
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text("test")

        result = resolve_doc_path(str(collection_path), str(doc_path))
        assert result == "2024/report.md"

    def test_resolve_doc_path_relative(self, tmp_path):
        """测试解析相对路径"""
        collection_path = tmp_path / "docs"
        collection_path.mkdir()

        # 使用相对路径
        result = resolve_doc_path(str(collection_path), "2024/report.md")
        # 相对路径会被 resolve，然后再计算相对关系
        assert "2024" in result or "report.md" in result

    def test_resolve_doc_path_outside_collection(self, tmp_path):
        """测试文档在 collection 外的情况"""
        collection_path = tmp_path / "docs"
        doc_path = tmp_path / "other" / "file.md"

        collection_path.mkdir()
        doc_path.parent.mkdir(parents=True)
        doc_path.write_text("test")

        result = resolve_doc_path(str(collection_path), str(doc_path))
        # 应该返回规范化的路径
        assert isinstance(result, str)


# =============================================================================
# 哈希工具测试
# =============================================================================

class TestHashing:
    """测试哈希计算工具"""

    def test_content_hash_consistency(self):
        """测试相同内容产生相同哈希"""
        text = "Hello, World!"
        hash1 = content_hash(text)
        hash2 = content_hash(text)
        assert hash1 == hash2

    def test_content_hash_different(self):
        """测试不同内容产生不同哈希"""
        hash1 = content_hash("Hello, World!")
        hash2 = content_hash("Hello, Python!")
        assert hash1 != hash2

    def test_content_hash_empty(self):
        """测试空字符串哈希"""
        hash_value = content_hash("")
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA256 十六进制长度

    def test_content_hash_unicode(self):
        """测试 Unicode 字符"""
        text = "你好，世界！🌍"
        hash_value = content_hash(text)
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64

    def test_content_hash_multiline(self):
        """测试多行文本"""
        text = "Line 1\nLine 2\nLine 3"
        hash_value = content_hash(text)
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64

    def test_file_hash_success(self, tmp_path):
        """测试成功计算文件哈希"""
        file_path = tmp_path / "test.txt"
        content = "Test content"
        file_path.write_text(content, encoding="utf-8")

        hash_value = file_hash(file_path)
        expected = content_hash(content)
        assert hash_value == expected

    def test_file_hash_nonexistent(self, tmp_path):
        """测试不存在的文件"""
        file_path = tmp_path / "nonexistent.txt"

        with pytest.raises(FileNotFoundError):
            file_hash(file_path)

    def test_file_hash_directory(self, tmp_path):
        """测试目录路径应报错"""
        with pytest.raises(ValueError, match="不是文件"):
            file_hash(tmp_path)

    def test_file_hash_binary(self, tmp_path):
        """测试二进制文件"""
        file_path = tmp_path / "test.bin"
        file_path.write_bytes(b"\x00\x01\x02\x03")

        hash_value = file_hash(file_path)
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64

    def test_file_hash_empty(self, tmp_path):
        """测试空文件的哈希"""
        file_path = tmp_path / "empty.txt"
        file_path.write_text("", encoding="utf-8")

        hash_value = file_hash(file_path)
        expected = content_hash("")
        assert hash_value == expected
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64

    def test_file_hash_consistency(self, tmp_path):
        """测试相同内容的文件哈希应一致"""
        content = "Same content for testing\n中文内容测试"

        # 创建两个内容相同的文件
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        file1.write_text(content, encoding="utf-8")
        file2.write_text(content, encoding="utf-8")

        hash1 = file_hash(file1)
        hash2 = file_hash(file2)

        # 两个文件的哈希应该相同
        assert hash1 == hash2
        # 并且应该等于内容的哈希
        assert hash1 == content_hash(content)

    def test_file_hash_large_file(self, tmp_path):
        """测试大文件的哈希（触发分块读取）"""
        file_path = tmp_path / "large.txt"
        # 创建一个大于 8192 字节的文件以触发分块读取
        large_content = "x" * 10000
        file_path.write_text(large_content, encoding="utf-8")

        hash_value = file_hash(file_path)
        expected = content_hash(large_content)
        assert hash_value == expected

    def test_file_hash_unicode_content(self, tmp_path):
        """测试包含 Unicode 字符的文件"""
        file_path = tmp_path / "unicode.txt"
        content = "Hello 世界 🌍 Привет مرحبا"
        file_path.write_text(content, encoding="utf-8")

        hash_value = file_hash(file_path)
        expected = content_hash(content)
        assert hash_value == expected

    def test_file_hash_invalid_utf8(self, tmp_path):
        """测试无效 UTF-8 编码的文件（触发二进制模式）"""
        file_path = tmp_path / "invalid_utf8.bin"
        # 写入无效的 UTF-8 字节序列
        # 0xFF 和 0xFE 在 UTF-8 中是无效的起始字节
        invalid_utf8_bytes = b'\xff\xfe\xfd Invalid UTF-8 \x80\x81'
        file_path.write_bytes(invalid_utf8_bytes)

        # 应该能够计算哈希（使用二进制模式）
        hash_value = file_hash(file_path)
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA256 哈希长度

        # 验证与直接计算二进制数据的哈希一致
        import hashlib
        expected_hash = hashlib.sha256(invalid_utf8_bytes).hexdigest()
        assert hash_value == expected_hash

    def test_get_docid(self):
        """测试提取 docid"""
        hash_value = "a1b2c3d4e5f6789abcdef"
        docid = get_docid(hash_value)
        assert docid == "a1b2c3"
        assert len(docid) == 6

    def test_get_docid_short_hash(self):
        """测试短哈希"""
        hash_value = "abc"
        docid = get_docid(hash_value)
        assert docid == "abc"


# =============================================================================
# 文本摘要提取测试
# =============================================================================

class TestSnippet:
    """测试文本摘要提取工具"""

    # 标题提取测试
    def test_extract_title_markdown_h1(self):
        """测试提取 Markdown H1 标题"""
        content = "# My Title\nSome content here"
        title = extract_title(content, "test.md")
        assert title == "My Title"

    def test_extract_title_markdown_h2(self):
        """测试提取 Markdown H2 标题"""
        content = "## Second Level\nSome content"
        title = extract_title(content, "test.md")
        assert title == "Second Level"

    def test_extract_title_no_title(self):
        """测试没有标题时使用文件名"""
        content = "Just some content without a title"
        title = extract_title(content, "document.md")
        assert title == "document"

    def test_extract_title_multiple_headings(self):
        """测试多个标题时使用第一个"""
        content = "# First Title\n## Second Title\n### Third"
        title = extract_title(content, "test.md")
        assert title == "First Title"

    def test_extract_title_skip_notes(self):
        """测试跳过通用的 Notes 标题"""
        content = "# Notes\nActual content"
        title = extract_title(content, "notes.md")
        assert title == "notes"  # 应该回退到文件名

    def test_extract_title_org_mode_title_prop(self):
        """测试 Org-mode #+TITLE: 属性"""
        content = "#+TITLE: My Org Document\n* Heading"
        title = extract_title(content, "test.org")
        assert title == "My Org Document"

    def test_extract_title_org_mode_heading(self):
        """测试 Org-mode heading"""
        content = "* Top Level Heading\n** Sub heading"
        title = extract_title(content, "test.org")
        assert title == "Top Level Heading"

    def test_extract_title_path_in_filename(self):
        """测试文件名包含路径"""
        content = "No title"
        title = extract_title(content, "/path/to/document.md")
        assert title == "document"

    def test_extract_title_no_extension(self):
        """测试没有扩展名的文件"""
        content = "No title"
        title = extract_title(content, "README")
        assert title == "README"

    # Snippet 提取测试
    def test_extract_snippet_basic(self):
        """测试基本 snippet 提取"""
        content = "Line 1\nTarget line with keyword\nLine 3\nLine 4"
        result = extract_snippet(content, "keyword")

        assert "snippet" in result
        assert "Target line" in result["snippet"]
        assert result["line"] == 2

    def test_extract_snippet_keyword_at_start(self):
        """测试关键词在开头"""
        content = "keyword line\nLine 2\nLine 3"
        result = extract_snippet(content, "keyword")

        assert result["line"] == 1
        assert "keyword line" in result["snippet"]

    def test_extract_snippet_keyword_at_end(self):
        """测试关键词在结尾"""
        content = "Line 1\nLine 2\nLine 3\nLast line with keyword"
        result = extract_snippet(content, "keyword")

        assert result["line"] == 4
        assert "keyword" in result["snippet"]

    def test_extract_snippet_no_keyword(self):
        """测试没有关键词时返回开头"""
        content = "Line 1\nLine 2\nLine 3"
        result = extract_snippet(content, "nonexistent")

        assert "snippet" in result
        assert result["line"] >= 1

    def test_extract_snippet_multiple_keywords(self):
        """测试多个关键词"""
        content = "Line 1\nLine with multiple keywords here\nLine 3"
        result = extract_snippet(content, "multiple keywords")

        assert "multiple" in result["snippet"]
        assert "keywords" in result["snippet"]

    def test_extract_snippet_max_chars(self):
        """测试最大字符限制"""
        long_line = "x" * 500
        content = f"Line 1\n{long_line}\nLine 3"
        result = extract_snippet(content, "xxx", max_chars=100)

        # snippet 应该被截断（包括头部）
        assert len(result["snippet"]) < 200

    def test_extract_snippet_context(self):
        """测试上下文提取（前1行，后3行）"""
        content = "Before\nTarget line\nAfter 1\nAfter 2\nAfter 3\nAfter 4"
        result = extract_snippet(content, "target")

        snippet_text = result["snippet"]
        # 应该包含前后上下文
        assert "Before" in snippet_text or "After" in snippet_text

    def test_extract_snippet_chunk_pos(self):
        """测试使用块位置参数"""
        content = "Line 1\nLine 2\nLine 3\nTarget line\nLine 5\nLine 6"
        # 使用 chunk_pos 参数
        result = extract_snippet(content, "target", chunk_pos=20, chunk_len=30)

        # 验证函数正常运行并返回结果
        assert "snippet" in result
        assert isinstance(result["line"], int)
        assert result["line"] > 0

    def test_extract_snippet_diff_header(self):
        """测试 diff 风格头部"""
        content = "Line 1\nLine 2\nTarget\nLine 4"
        result = extract_snippet(content, "target")

        snippet = result["snippet"]
        # 应该包含 @@ 头部
        assert "@@" in snippet
        assert "before" in snippet
        assert "after" in snippet

    def test_extract_snippet_line_numbers(self):
        """测试行号计算"""
        lines = [f"Line {i}" for i in range(1, 21)]
        lines[9] = "Line 10 SPECIAL"  # 让第10行更特殊
        content = "\n".join(lines)
        result = extract_snippet(content, "SPECIAL")

        assert result["line"] == 10
        assert result["lines_before"] > 0
        assert result["lines_after"] > 0

    def test_extract_snippet_case_insensitive(self):
        """测试大小写不敏感"""
        content = "Line 1\nTARGET LINE\nLine 3"
        result = extract_snippet(content, "target")

        assert "TARGET" in result["snippet"]


# =============================================================================
# 边界情况测试
# =============================================================================

class TestEdgeCases:
    """测试边界情况"""

    def test_empty_content_title(self):
        """测试空内容提取标题"""
        title = extract_title("", "test.md")
        assert title == "test"

    def test_empty_content_snippet(self):
        """测试空内容提取 snippet"""
        result = extract_snippet("", "query")
        assert "snippet" in result

    def test_whitespace_only_content(self):
        """测试仅空白字符的内容"""
        content = "   \n\n   \n  "
        result = extract_snippet(content, "query")
        assert isinstance(result, dict)

    def test_very_long_filename(self):
        """测试很长的文件名"""
        long_name = "a" * 500 + ".md"
        title = extract_title("No title", long_name)
        assert isinstance(title, str)

    def test_unicode_in_paths(self):
        """测试路径中的 Unicode 字符"""
        path = "文档/2024/报告.md"
        normalized = normalize_path(path)
        assert "文档" in normalized

    def test_hash_very_large_text(self):
        """测试非常大的文本哈希"""
        large_text = "x" * 1_000_000  # 1MB
        hash_value = content_hash(large_text)
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64


# =============================================================================
# VirtualPath 测试
# =============================================================================


class TestVirtualPath:
    """VirtualPath 系统测试"""

    def test_parse_virtual_path_valid(self):
        """测试正常解析虚拟路径"""
        result = parse_virtual_path("qmd://notes/file.md")
        assert isinstance(result, VirtualPath)
        assert result.collection_name == "notes"
        assert result.path == "file.md"

        # 带子目录
        result2 = parse_virtual_path("qmd://docs/subfolder/file.md")
        assert result2.collection_name == "docs"
        assert result2.path == "subfolder/file.md"

    def test_parse_virtual_path_invalid(self):
        """测试各种无效格式返回 None"""
        assert parse_virtual_path("") is None
        assert parse_virtual_path(None) is None
        assert parse_virtual_path("qmd://") is None
        assert parse_virtual_path("qmd://notes") is None  # 缺少 /path
        assert parse_virtual_path("http://example.com") is None
        assert parse_virtual_path("/absolute/path") is None
        assert parse_virtual_path("relative/path.md") is None

    def test_build_virtual_path(self):
        """测试构建虚拟路径"""
        path = build_virtual_path("notes", "file.md")
        assert path == "qmd://notes/file.md"

        # 带子目录
        path2 = build_virtual_path("docs", "subfolder/file.md")
        assert path2 == "qmd://docs/subfolder/file.md"

        # path 开头有斜杠会被清理
        path3 = build_virtual_path("notes", "/file.md")
        assert path3 == "qmd://notes/file.md"

    def test_is_virtual_path(self):
        """测试判断虚拟路径"""
        assert is_virtual_path("qmd://notes/file.md") is True
        assert is_virtual_path("  qmd://notes/file.md  ") is True  # 空格会被 strip
        assert is_virtual_path("/absolute/path") is False
        assert is_virtual_path("relative/path.md") is False
        assert is_virtual_path("") is False
        assert is_virtual_path(None) is False

    def test_normalize_virtual_path(self):
        """测试规范化虚拟路径"""
        # 去除空格
        assert normalize_virtual_path("  qmd://notes/file.md  ") == "qmd://notes/file.md"

        # 补齐前缀
        assert normalize_virtual_path("notes/file.md") == "qmd://notes/file.md"
        assert normalize_virtual_path("//notes/file.md") == "qmd://notes/file.md"

        # 已经正确的格式
        assert normalize_virtual_path("qmd://notes/file.md") == "qmd://notes/file.md"
