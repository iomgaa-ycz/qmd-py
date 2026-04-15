"""单测：connect() 读 qmd.yaml 并贯穿到 Collection/Embedder。"""
from __future__ import annotations

from pathlib import Path

import yaml

from qmd import connect


def test_connect_no_yaml_uses_defaults(tmp_path: Path):
    """qmd.yaml 不存在 → 走默认值。"""
    client = connect(tmp_path / "db.sqlite")
    assert client.config.chunking.size == 512
    # auto 已解析成 16 或 64
    assert client.config.embedding.batch_size in (16, 64)
    client.close()


def test_connect_reads_adjacent_yaml(tmp_path: Path):
    """{db_path 同目录}/qmd.yaml 自动发现。"""
    (tmp_path / "qmd.yaml").write_text(
        yaml.safe_dump({"chunking": {"size": 256, "overlap": 32}}),
        encoding="utf-8",
    )
    client = connect(tmp_path / "db.sqlite")
    assert client.config.chunking.size == 256
    client.close()


def test_connect_config_overrides_beats_yaml(tmp_path: Path):
    """config_overrides 优先级高于 yaml。"""
    (tmp_path / "qmd.yaml").write_text(
        yaml.safe_dump({"rerank": {"enabled": False}}),
        encoding="utf-8",
    )
    client = connect(
        tmp_path / "db.sqlite",
        config_overrides={"rerank": {"enabled": True}},
    )
    assert client.config.rerank.enabled is True
    client.close()


def test_collection_uses_config_chunk_size(tmp_path: Path):
    """Collection.add_document 的 chunking 读 config.chunking.size。"""
    client = connect(
        tmp_path / "db.sqlite",
        config_overrides={"chunking": {"size": 100, "overlap": 10}},
    )
    col = client.collection("c")
    md = "段落一。\n\n" + ("长段落内容 " * 200) + "\n\n段落三。"
    col.add_document("d1", md, {})
    info = col.info()
    # size=100 切得更碎，至少 3 段
    assert info.chunk_count >= 3
    client.close()
