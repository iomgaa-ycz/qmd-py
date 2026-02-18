"""
测试 CLI 命令行接口
"""

import os
import sys
from io import StringIO
from pathlib import Path
from unittest import mock

import pytest

from qmd.cli.main import create_parser, main


class TestCLI:
    """CLI 测试"""

    @pytest.fixture(autouse=True)
    def isolate_config(self, tmp_path: Path, monkeypatch):
        """隔离配置环境，防止测试污染全局配置"""
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

    def test_parser_creation(self):
        """测试 parser 创建"""
        parser = create_parser()
        assert parser.prog == "qmd-py"

        # 测试帮助信息
        with pytest.raises(SystemExit):
            parser.parse_args(["--help"])

    def test_no_command_shows_help(self, capsys):
        """测试无参数显示帮助"""
        with mock.patch.object(sys, "argv", ["qmd-py"]):
            exit_code = main()

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "usage:" in captured.out or "usage:" in captured.err

    def test_add_command(self, tmp_docs: Path, tmp_path: Path, capsys):
        """测试 add 命令"""
        db_path = tmp_path / "test.db"

        with mock.patch.object(
            sys,
            "argv",
            [
                "qmd-py",
                "--db",
                str(db_path),
                "add",
                "docs",
                str(tmp_docs),
                "--pattern",
                "**/*.md",
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "已添加 collection" in captured.out
        assert "docs" in captured.out

    def test_list_command_empty(self, tmp_path: Path, capsys):
        """测试 list 命令（空）"""
        db_path = tmp_path / "test.db"

        with mock.patch.object(sys, "argv", ["qmd-py", "--db", str(db_path), "list"]):
            exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "没有 collection" in captured.out

    def test_list_command_with_collections(
        self, tmp_docs: Path, tmp_path: Path, capsys
    ):
        """测试 list 命令（有 collections）"""
        db_path = tmp_path / "test.db"

        # 先添加 collection
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "add", "docs", str(tmp_docs)]
        ):
            main()

        # 然后列出
        with mock.patch.object(sys, "argv", ["qmd-py", "--db", str(db_path), "list"]):
            exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "docs" in captured.out
        assert "路径:" in captured.out

    def test_remove_command(self, tmp_docs: Path, tmp_path: Path, capsys):
        """测试 remove 命令"""
        db_path = tmp_path / "test.db"

        # 先添加
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "add", "docs", str(tmp_docs)]
        ):
            main()

        # 然后删除
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "remove", "docs"]
        ):
            exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "已删除 collection" in captured.out

    def test_remove_nonexistent(self, tmp_path: Path, capsys):
        """测试删除不存在的 collection"""
        db_path = tmp_path / "test.db"

        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "remove", "nonexistent"]
        ):
            exit_code = main()

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "不存在" in captured.err

    def test_update_command(self, tmp_docs: Path, tmp_path: Path, capsys):
        """测试 update 命令"""
        db_path = tmp_path / "test.db"

        # 先添加
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "add", "docs", str(tmp_docs)]
        ):
            main()

        # 更新索引
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "update"]
        ):
            exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "索引更新完成" in captured.out
        assert "新增:" in captured.out

    def test_update_specific_collection(self, tmp_docs: Path, tmp_path: Path, capsys):
        """测试更新指定 collection"""
        db_path = tmp_path / "test.db"

        # 先添加
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "add", "docs", str(tmp_docs)]
        ):
            main()

        # 更新指定 collection
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "update", "docs"]
        ):
            exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "索引更新完成" in captured.out

    def test_update_nonexistent(self, tmp_path: Path, capsys):
        """测试更新不存在的 collection"""
        db_path = tmp_path / "test.db"

        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "update", "nonexistent"]
        ):
            exit_code = main()

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "error" in captured.err.lower() or "不存在" in captured.err

    def test_search_command(self, tmp_docs: Path, tmp_path: Path, capsys):
        """测试 search 命令"""
        db_path = tmp_path / "test.db"

        # 添加并更新
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "add", "docs", str(tmp_docs)]
        ):
            main()

        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "update"]
        ):
            main()

        # 搜索
        with mock.patch.object(
            sys,
            "argv",
            [
                "qmd-py",
                "--db",
                str(db_path),
                "--backend",
                "sentence_tf",
                "search",
                "Python",
            ],
        ):
            exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        # 可能找到结果或未找到（取决于模型是否可用）
        assert "找到" in captured.out or "未找到" in captured.out

    def test_search_with_limit(self, tmp_docs: Path, tmp_path: Path, capsys):
        """测试 search 命令带 limit"""
        db_path = tmp_path / "test.db"

        # 添加并更新
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "add", "docs", str(tmp_docs)]
        ):
            main()

        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "update"]
        ):
            main()

        # 搜索 with limit
        with mock.patch.object(
            sys,
            "argv",
            [
                "qmd-py",
                "--db",
                str(db_path),
                "--backend",
                "sentence_tf",
                "search",
                "test",
                "--limit",
                "5",
            ],
        ):
            exit_code = main()

        assert exit_code == 0

    def test_search_with_collection(self, tmp_docs: Path, tmp_path: Path, capsys):
        """测试 search 命令带 collection 过滤"""
        db_path = tmp_path / "test.db"

        # 添加并更新
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "add", "docs", str(tmp_docs)]
        ):
            main()

        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "update"]
        ):
            main()

        # 搜索 with collection
        with mock.patch.object(
            sys,
            "argv",
            [
                "qmd-py",
                "--db",
                str(db_path),
                "--backend",
                "sentence_tf",
                "search",
                "test",
                "--collection",
                "docs",
            ],
        ):
            exit_code = main()

        assert exit_code == 0

    def test_status_command(self, tmp_docs: Path, tmp_path: Path, capsys):
        """测试 status 命令"""
        db_path = tmp_path / "test.db"

        # 添加并更新
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "add", "docs", str(tmp_docs)]
        ):
            main()

        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "update"]
        ):
            main()

        # 显示状态
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "status"]
        ):
            exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "索引状态" in captured.out
        assert "数据库:" in captured.out
        assert "Collections:" in captured.out

    def test_serve_command(self, tmp_path: Path, capsys):
        """测试 serve 命令"""
        db_path = tmp_path / "test.db"

        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "serve"]
        ):
            exit_code = main()

        # serve 命令会因为 stdio 不可用而失败，返回 1
        assert exit_code == 1
        captured = capsys.readouterr()
        # 检查启动消息
        assert "MCP 服务器" in captured.out or "stdio" in captured.out

    def test_verbose_flag(self, tmp_path: Path, capsys):
        """测试 --verbose 标志"""
        db_path = tmp_path / "test.db"

        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "--verbose", "list"]
        ):
            exit_code = main()

        assert exit_code == 0
        # verbose 模式会输出更多日志

    def test_backend_selection(self, tmp_docs: Path, tmp_path: Path):
        """测试 --backend 选项"""
        db_path = tmp_path / "test.db"

        # 测试 auto backend
        with mock.patch.object(
            sys,
            "argv",
            [
                "qmd-py",
                "--db",
                str(db_path),
                "--backend",
                "auto",
                "add",
                "docs",
                str(tmp_docs),
            ],
        ):
            exit_code = main()

        assert exit_code == 0

        # 测试 sentence_tf backend
        with mock.patch.object(
            sys,
            "argv",
            [
                "qmd-py",
                "--db",
                str(db_path),
                "--backend",
                "sentence_tf",
                "list",
            ],
        ):
            exit_code = main()

        assert exit_code == 0

    def test_complete_workflow(self, tmp_docs: Path, tmp_path: Path, capsys):
        """测试完整工作流: add → update → search → status → remove"""
        db_path = tmp_path / "test.db"

        # 1. Add
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "add", "docs", str(tmp_docs)]
        ):
            assert main() == 0

        # 2. Update
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "update"]
        ):
            assert main() == 0

        # 3. Search
        with mock.patch.object(
            sys,
            "argv",
            [
                "qmd-py",
                "--db",
                str(db_path),
                "--backend",
                "sentence_tf",
                "search",
                "document",
            ],
        ):
            assert main() == 0

        # 4. Status
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "status"]
        ):
            assert main() == 0

        # 5. Remove
        with mock.patch.object(
            sys, "argv", ["qmd-py", "--db", str(db_path), "remove", "docs"]
        ):
            assert main() == 0

    def test_keyboard_interrupt(self, tmp_path: Path):
        """测试 KeyboardInterrupt 处理"""
        db_path = tmp_path / "test.db"

        # Mock cmd_list 抛出 KeyboardInterrupt
        with mock.patch("qmd.cli.main.cmd_list", side_effect=KeyboardInterrupt):
            with mock.patch.object(
                sys, "argv", ["qmd-py", "--db", str(db_path), "list"]
            ):
                exit_code = main()

        assert exit_code == 130

    def test_exception_handling(self, tmp_path: Path, capsys):
        """测试异常处理"""
        db_path = tmp_path / "test.db"

        # Mock cmd_list 抛出异常
        with mock.patch(
            "qmd.cli.main.cmd_list", side_effect=RuntimeError("Test error")
        ):
            with mock.patch.object(
                sys, "argv", ["qmd-py", "--db", str(db_path), "list"]
            ):
                exit_code = main()

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "错误" in captured.err or "Test error" in captured.err

    def test_unknown_command(self, tmp_path: Path, capsys):
        """测试未知命令"""
        db_path = tmp_path / "test.db"

        # 直接构造未知命令（绕过 argparse）
        parser = create_parser()
        args = parser.parse_args(["--db", str(db_path), "list"])

        # 修改为未知命令
        args.command = "unknown"

        with mock.patch("qmd.cli.main.create_parser", return_value=parser):
            with mock.patch("argparse.ArgumentParser.parse_args", return_value=args):
                with mock.patch.object(
                    sys, "argv", ["qmd-py", "--db", str(db_path), "unknown"]
                ):
                    exit_code = main()

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "未知命令" in captured.err or "unknown" in captured.err.lower()
