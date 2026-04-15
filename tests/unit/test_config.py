"""单测：qmd/core/config.py — pydantic schema + yaml 加载 + 优先级。"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from qmd.core.config import ConfigError, QmdConfig


def test_defaults_when_no_yaml(tmp_path: Path):
    """qmd.yaml 不存在 → 走 pydantic 默认值，不抛错。"""
    cfg = QmdConfig.load(db_path=tmp_path / "db.sqlite")
    assert cfg.chunking.size == 512
    assert cfg.chunking.overlap == 64
    assert cfg.embedding.model_name == "Qwen/Qwen3-Embedding-0.6B"
    assert cfg.embedding.dim == 1024
    assert cfg.embedding.batch_size == "auto"
    assert cfg.rerank.enabled is False
    assert cfg.rerank.model_name == "Qwen/Qwen3-Reranker-0.6B"
    assert cfg.rerank.top_k_candidates == 40
    assert cfg.retrieval.rrf_k == 60


def test_load_from_yaml(tmp_path: Path):
    yaml_path = tmp_path / "qmd.yaml"
    yaml_path.write_text(
        yaml.safe_dump({"chunking": {"size": 256, "overlap": 32}}),
        encoding="utf-8",
    )
    cfg = QmdConfig.load(db_path=tmp_path / "db.sqlite")
    assert cfg.chunking.size == 256
    assert cfg.chunking.overlap == 32
    assert cfg.retrieval.rrf_k == 60


def test_overrides_beats_yaml(tmp_path: Path):
    yaml_path = tmp_path / "qmd.yaml"
    yaml_path.write_text(yaml.safe_dump({"rerank": {"enabled": False}}), encoding="utf-8")
    cfg = QmdConfig.load(
        db_path=tmp_path / "db.sqlite",
        config_overrides={"rerank": {"enabled": True}},
    )
    assert cfg.rerank.enabled is True


def test_bad_yaml_syntax_raises_configerror(tmp_path: Path):
    yaml_path = tmp_path / "qmd.yaml"
    yaml_path.write_text("chunking: {size: 256, overlap\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        QmdConfig.load(db_path=tmp_path / "db.sqlite")


def test_bad_schema_raises_configerror(tmp_path: Path):
    yaml_path = tmp_path / "qmd.yaml"
    yaml_path.write_text(
        yaml.safe_dump({"chunking": {"size": "not an int"}}),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as exc_info:
        QmdConfig.load(db_path=tmp_path / "db.sqlite")
    assert "chunking" in str(exc_info.value).lower() or "size" in str(exc_info.value).lower()


def test_unknown_yaml_field_raises(tmp_path: Path):
    yaml_path = tmp_path / "qmd.yaml"
    yaml_path.write_text(
        yaml.safe_dump({"chunking": {"size": 512, "typo_field": 123}}),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        QmdConfig.load(db_path=tmp_path / "db.sqlite")
