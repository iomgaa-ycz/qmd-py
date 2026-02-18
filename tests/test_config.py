"""
YAML 配置管理测试

测试配置加载、保存、Collection CRUD、Context 管理、Schema 验证
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from qmd.core.config import (
    Collection,
    CollectionConfig,
    NamedCollection,
    add_collection,
    add_context,
    config_exists,
    find_context_for_path,
    get_collection,
    get_config_dir,
    get_config_path,
    get_contexts,
    get_global_context,
    is_valid_collection_name,
    list_all_contexts,
    list_collections,
    load_config,
    remove_collection,
    remove_context,
    rename_collection,
    save_config,
    set_config_index_name,
    set_global_context,
)


@pytest.fixture
def temp_config_dir(monkeypatch):
    """创建临时配置目录，测试后自动清理"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 设置 QMD_CONFIG_DIR 环境变量指向临时目录
        monkeypatch.setenv("QMD_CONFIG_DIR", tmpdir)
        yield Path(tmpdir)


class TestConfigPaths:
    """测试配置路径相关功能"""

    def test_get_config_dir_with_env_var(self, temp_config_dir):
        """测试 QMD_CONFIG_DIR 环境变量优先级最高"""
        assert get_config_dir() == temp_config_dir

    def test_get_config_dir_with_xdg(self, monkeypatch, tmp_path):
        """测试 XDG_CONFIG_HOME 环境变量"""
        xdg_home = tmp_path / "xdg_config"
        xdg_home.mkdir()
        monkeypatch.delenv("QMD_CONFIG_DIR", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_home))

        expected = xdg_home / "qmd"
        assert get_config_dir() == expected

    def test_get_config_file_path(self, temp_config_dir):
        """测试获取配置文件路径"""
        expected = temp_config_dir / "index.yml"
        assert get_config_path() == expected

    def test_set_config_index_name(self, temp_config_dir):
        """测试设置自定义索引名称"""
        set_config_index_name("custom")
        expected = temp_config_dir / "custom.yml"
        assert get_config_path() == expected

        # 恢复默认值
        set_config_index_name("index")

    def test_config_exists(self, temp_config_dir):
        """测试检查配置文件是否存在"""
        assert not config_exists()

        # 创建空配置文件
        config_path = get_config_path()
        config_path.write_text("collections: {}")

        assert config_exists()


class TestLoadConfig:
    """测试配置加载"""

    def test_load_nonexistent_config(self, temp_config_dir):
        """测试加载不存在的配置文件返回空配置"""
        config = load_config()

        assert isinstance(config, CollectionConfig)
        assert config.collections == {}
        assert config.global_context is None

    def test_load_empty_config(self, temp_config_dir):
        """测试加载空配置文件"""
        config_path = get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("")

        config = load_config()
        assert config.collections == {}

    def test_load_valid_config(self, temp_config_dir):
        """测试加载有效配置"""
        config_path = get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        yaml_content = """
global_context: "Global context text"
collections:
  docs:
    path: /home/user/docs
    pattern: "**/*.md"
    context:
      /2024: "Documents from 2024"
  notes:
    path: /home/user/notes
    pattern: "**/*.txt"
"""
        config_path.write_text(yaml_content)

        config = load_config()
        assert config.global_context == "Global context text"
        assert "docs" in config.collections
        assert "notes" in config.collections
        assert config.collections["docs"].path == "/home/user/docs"
        assert config.collections["docs"].context == {"/2024": "Documents from 2024"}

    def test_load_invalid_yaml(self, temp_config_dir):
        """测试加载无效 YAML 应报错"""
        config_path = get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("invalid: yaml: content: [")

        with pytest.raises(ValueError, match="Failed to parse"):
            load_config()


class TestSaveConfig:
    """测试配置保存"""

    def test_save_empty_config(self, temp_config_dir):
        """测试保存空配置"""
        config = CollectionConfig(collections={})
        save_config(config)

        assert config_exists()

        # 重新加载验证
        loaded = load_config()
        assert loaded.collections == {}

    def test_save_config_creates_directory(self, temp_config_dir):
        """测试保存配置时自动创建目录"""
        # 删除目录
        config_dir = get_config_dir()
        if config_dir.exists():
            import shutil
            shutil.rmtree(config_dir)

        config = CollectionConfig(collections={})
        save_config(config)

        assert config_dir.exists()
        assert config_exists()

    def test_save_and_load_roundtrip(self, temp_config_dir):
        """测试保存后重新加载配置一致性"""
        original = CollectionConfig(
            global_context="Test global context",
            collections={
                "test": Collection(
                    path="/test/path",
                    pattern="**/*.md",
                    context={"/sub": "Sub context"},
                    update="git pull",
                )
            }
        )

        save_config(original)
        loaded = load_config()

        assert loaded.global_context == original.global_context
        assert loaded.collections.keys() == original.collections.keys()
        assert loaded.collections["test"].path == original.collections["test"].path
        assert loaded.collections["test"].pattern == original.collections["test"].pattern
        assert loaded.collections["test"].context == original.collections["test"].context
        assert loaded.collections["test"].update == original.collections["test"].update


class TestCollectionCRUD:
    """测试 Collection 增删改查"""

    def test_add_collection(self, temp_config_dir):
        """测试添加 collection"""
        add_collection("docs", "/home/user/docs", "**/*.md")

        config = load_config()
        assert "docs" in config.collections
        assert config.collections["docs"].path == "/home/user/docs"
        assert config.collections["docs"].pattern == "**/*.md"

    def test_add_collection_with_context(self, temp_config_dir):
        """测试添加带 context 的 collection"""
        context = {"/2024": "Year 2024", "/2025": "Year 2025"}
        add_collection("docs", "/home/user/docs", context=context)

        config = load_config()
        assert config.collections["docs"].context == context

    def test_add_collection_preserves_existing_context(self, temp_config_dir):
        """测试更新 collection 时保留现有 context"""
        # 先添加带 context 的 collection
        add_collection("docs", "/home/user/docs", context={"/old": "Old context"})

        # 更新 collection（不提供 context）
        add_collection("docs", "/home/user/new_docs")

        config = load_config()
        assert config.collections["docs"].path == "/home/user/new_docs"
        assert config.collections["docs"].context == {"/old": "Old context"}

    def test_get_collection(self, temp_config_dir):
        """测试获取 collection"""
        add_collection("docs", "/home/user/docs")

        collection = get_collection("docs")
        assert collection is not None
        assert collection.name == "docs"
        assert collection.path == "/home/user/docs"

    def test_get_nonexistent_collection(self, temp_config_dir):
        """测试获取不存在的 collection 返回 None"""
        collection = get_collection("nonexistent")
        assert collection is None

    def test_list_collections(self, temp_config_dir):
        """测试列出所有 collections"""
        add_collection("docs", "/home/user/docs")
        add_collection("notes", "/home/user/notes")

        collections = list_collections()
        assert len(collections) == 2
        names = {c.name for c in collections}
        assert names == {"docs", "notes"}

    def test_list_collections_empty(self, temp_config_dir):
        """测试列出空 collections"""
        collections = list_collections()
        assert collections == []

    def test_remove_collection(self, temp_config_dir):
        """测试删除 collection"""
        add_collection("docs", "/home/user/docs")
        assert get_collection("docs") is not None

        result = remove_collection("docs")
        assert result is True
        assert get_collection("docs") is None

    def test_remove_nonexistent_collection(self, temp_config_dir):
        """测试删除不存在的 collection 返回 False"""
        result = remove_collection("nonexistent")
        assert result is False

    def test_rename_collection(self, temp_config_dir):
        """测试重命名 collection"""
        add_collection("docs", "/home/user/docs", context={"/sub": "Sub"})

        result = rename_collection("docs", "documents")
        assert result is True

        assert get_collection("docs") is None
        renamed = get_collection("documents")
        assert renamed is not None
        assert renamed.path == "/home/user/docs"
        assert renamed.context == {"/sub": "Sub"}

    def test_rename_nonexistent_collection(self, temp_config_dir):
        """测试重命名不存在的 collection 返回 False"""
        result = rename_collection("nonexistent", "new")
        assert result is False

    def test_rename_to_existing_name(self, temp_config_dir):
        """测试重命名到已存在的名称应报错"""
        add_collection("docs", "/home/user/docs")
        add_collection("notes", "/home/user/notes")

        with pytest.raises(ValueError, match="already exists"):
            rename_collection("docs", "notes")


class TestGlobalContext:
    """测试全局上下文管理"""

    def test_get_global_context_none(self, temp_config_dir):
        """测试默认没有全局上下文"""
        context = get_global_context()
        assert context is None

    def test_set_global_context(self, temp_config_dir):
        """测试设置全局上下文"""
        set_global_context("This is global context")

        context = get_global_context()
        assert context == "This is global context"

    def test_set_global_context_none(self, temp_config_dir):
        """测试将全局上下文设为 None"""
        set_global_context("Some context")
        set_global_context(None)

        context = get_global_context()
        assert context is None

    def test_global_context_persistence(self, temp_config_dir):
        """测试全局上下文持久化"""
        set_global_context("Persistent context")

        # 重新加载配置验证
        config = load_config()
        assert config.global_context == "Persistent context"


class TestCollectionContext:
    """测试 Collection 上下文管理"""

    def test_add_context(self, temp_config_dir):
        """测试添加上下文"""
        add_collection("docs", "/home/user/docs")
        result = add_context("docs", "/2024", "Documents from 2024")

        assert result is True

        contexts = get_contexts("docs")
        assert contexts == {"/2024": "Documents from 2024"}

    def test_add_context_to_nonexistent_collection(self, temp_config_dir):
        """测试向不存在的 collection 添加上下文返回 False"""
        result = add_context("nonexistent", "/path", "context")
        assert result is False

    def test_add_multiple_contexts(self, temp_config_dir):
        """测试添加多个上下文"""
        add_collection("docs", "/home/user/docs")
        add_context("docs", "/2024", "Year 2024")
        add_context("docs", "/2025", "Year 2025")

        contexts = get_contexts("docs")
        assert contexts == {"/2024": "Year 2024", "/2025": "Year 2025"}

    def test_update_context(self, temp_config_dir):
        """测试更新已存在的上下文"""
        add_collection("docs", "/home/user/docs")
        add_context("docs", "/2024", "Old description")
        add_context("docs", "/2024", "New description")

        contexts = get_contexts("docs")
        assert contexts["/2024"] == "New description"

    def test_get_contexts_none(self, temp_config_dir):
        """测试没有上下文的 collection"""
        add_collection("docs", "/home/user/docs")

        contexts = get_contexts("docs")
        assert contexts is None

    def test_get_contexts_nonexistent_collection(self, temp_config_dir):
        """测试获取不存在 collection 的上下文"""
        contexts = get_contexts("nonexistent")
        assert contexts is None

    def test_remove_context(self, temp_config_dir):
        """测试删除上下文"""
        add_collection("docs", "/home/user/docs")
        add_context("docs", "/2024", "Year 2024")
        add_context("docs", "/2025", "Year 2025")

        result = remove_context("docs", "/2024")
        assert result is True

        contexts = get_contexts("docs")
        assert contexts == {"/2025": "Year 2025"}

    def test_remove_last_context_clears_field(self, temp_config_dir):
        """测试删除最后一个上下文时清除 context 字段"""
        add_collection("docs", "/home/user/docs")
        add_context("docs", "/2024", "Year 2024")

        remove_context("docs", "/2024")

        contexts = get_contexts("docs")
        assert contexts is None

    def test_remove_nonexistent_context(self, temp_config_dir):
        """测试删除不存在的上下文返回 False"""
        add_collection("docs", "/home/user/docs")

        result = remove_context("docs", "/nonexistent")
        assert result is False

    def test_list_all_contexts(self, temp_config_dir):
        """测试列出所有上下文"""
        set_global_context("Global context")
        add_collection("docs", "/home/user/docs")
        add_context("docs", "/2024", "Docs 2024")
        add_collection("notes", "/home/user/notes")
        add_context("notes", "/personal", "Personal notes")

        all_contexts = list_all_contexts()

        assert len(all_contexts) == 3
        assert {"collection": "*", "path": "/", "context": "Global context"} in all_contexts
        assert {"collection": "docs", "path": "/2024", "context": "Docs 2024"} in all_contexts
        assert {"collection": "notes", "path": "/personal", "context": "Personal notes"} in all_contexts

    def test_find_context_for_path(self, temp_config_dir):
        """测试根据路径查找上下文（最长前缀匹配）"""
        add_collection("docs", "/home/user/docs")
        add_context("docs", "/", "Root context")
        add_context("docs", "/2024", "2024 context")
        add_context("docs", "/2024/Q1", "Q1 context")

        # 最具体匹配
        assert find_context_for_path("docs", "/2024/Q1/report.md") == "Q1 context"

        # 次具体匹配
        assert find_context_for_path("docs", "/2024/Q2/report.md") == "2024 context"

        # 根匹配
        assert find_context_for_path("docs", "/2025/report.md") == "Root context"

    def test_find_context_normalizes_paths(self, temp_config_dir):
        """测试路径规范化（处理前导斜杠）"""
        add_collection("docs", "/home/user/docs")
        add_context("docs", "2024", "2024 context")  # 无前导斜杠

        # 查询时有或无前导斜杠都能匹配
        assert find_context_for_path("docs", "/2024/file.md") == "2024 context"
        assert find_context_for_path("docs", "2024/file.md") == "2024 context"

    def test_find_context_fallback_to_global(self, temp_config_dir):
        """测试无匹配时回退到全局上下文"""
        set_global_context("Global fallback")
        add_collection("docs", "/home/user/docs")
        add_context("docs", "/2024", "2024 context")

        # 无匹配的路径应返回全局上下文
        assert find_context_for_path("docs", "/2025/file.md") == "Global fallback"

    def test_find_context_no_context(self, temp_config_dir):
        """测试既无 collection context 也无 global context"""
        add_collection("docs", "/home/user/docs")

        result = find_context_for_path("docs", "/any/path.md")
        assert result is None


class TestSchemaValidation:
    """测试 Schema 验证"""

    def test_collection_valid(self):
        """测试有效的 Collection"""
        collection = Collection(path="/home/user/docs", pattern="**/*.md")
        assert collection.path == "/home/user/docs"
        assert collection.pattern == "**/*.md"

    def test_collection_empty_path(self):
        """测试空路径应报错"""
        with pytest.raises(ValidationError, match="path cannot be empty"):
            Collection(path="", pattern="**/*.md")

    def test_collection_whitespace_path(self):
        """测试仅空白字符的路径应报错"""
        with pytest.raises(ValidationError, match="path cannot be empty"):
            Collection(path="   ", pattern="**/*.md")

    def test_collection_empty_pattern(self):
        """测试空 pattern 应报错"""
        with pytest.raises(ValidationError, match="pattern cannot be empty"):
            Collection(path="/home/user/docs", pattern="")

    def test_collection_default_pattern(self):
        """测试默认 pattern"""
        collection = Collection(path="/home/user/docs")
        assert collection.pattern == "**/*.md"

    def test_collection_optional_fields(self):
        """测试可选字段"""
        collection = Collection(
            path="/home/user/docs",
            context={"/sub": "Sub context"},
            update="git pull"
        )
        assert collection.context == {"/sub": "Sub context"}
        assert collection.update == "git pull"

    def test_collection_config_invalid_data(self, temp_config_dir):
        """测试无效配置数据应报错"""
        config_path = get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # path 字段缺失
        yaml_content = """
collections:
  docs:
    pattern: "**/*.md"
"""
        config_path.write_text(yaml_content)

        with pytest.raises(ValueError, match="Failed to load"):
            load_config()


class TestUtilityFunctions:
    """测试工具函数"""

    def test_is_valid_collection_name(self):
        """测试 collection 名称验证"""
        # 有效名称
        assert is_valid_collection_name("docs")
        assert is_valid_collection_name("my-docs")
        assert is_valid_collection_name("my_docs")
        assert is_valid_collection_name("docs123")
        assert is_valid_collection_name("MyDocs")

        # 无效名称
        assert not is_valid_collection_name("my docs")  # 空格
        assert not is_valid_collection_name("my.docs")  # 点号
        assert not is_valid_collection_name("my/docs")  # 斜杠
        assert not is_valid_collection_name("")  # 空字符串
        assert not is_valid_collection_name("my@docs")  # 特殊字符


class TestEdgeCases:
    """测试边界情况"""

    def test_empty_collections_dict(self, temp_config_dir):
        """测试空 collections 字典"""
        config = CollectionConfig(collections={})
        save_config(config)

        loaded = load_config()
        assert loaded.collections == {}

    def test_collection_with_none_context(self, temp_config_dir):
        """测试 context 为 None 的 collection"""
        add_collection("docs", "/home/user/docs")

        collection = get_collection("docs")
        assert collection is not None
        assert collection.context is None

    def test_multiple_saves(self, temp_config_dir):
        """测试多次保存"""
        add_collection("docs", "/home/user/docs")
        add_collection("notes", "/home/user/notes")
        add_collection("archive", "/home/user/archive")

        collections = list_collections()
        assert len(collections) == 3

    def test_yaml_special_characters(self, temp_config_dir):
        """测试 YAML 特殊字符处理"""
        special_context = "Context with: colons, 'quotes', and \"double quotes\""
        add_collection("docs", "/home/user/docs")
        add_context("docs", "/special", special_context)

        contexts = get_contexts("docs")
        assert contexts["/special"] == special_context
