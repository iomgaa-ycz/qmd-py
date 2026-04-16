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
    assert cfg.embedding.batch_size in (16, 64)  # "auto" 在 validator 中已解析为具体数字
    assert cfg.rerank.enabled is False
    assert cfg.rerank.model_name == "Qwen/Qwen3-Reranker-0.6B"
    assert cfg.rerank.top_k_candidates == 40
    assert cfg.retrieval.rrf_k == 60


def test_load_from_yaml(tmp_path: Path):
    """{db_path 同目录}/qmd.yaml 被自动发现。"""
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
    """config_overrides 优先级高于 yaml。"""
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


def test_list_top_level_yaml_raises(tmp_path: Path):
    """顶层结构非 dict（如 list）→ ConfigError，不静默走默认。"""
    yaml_path = tmp_path / "qmd.yaml"
    yaml_path.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc_info:
        QmdConfig.load(db_path=tmp_path / "db.sqlite")
    assert "dict" in str(exc_info.value).lower() or "list" in str(exc_info.value).lower()


def test_empty_yaml_uses_defaults(tmp_path: Path):
    """空 yaml 文件（safe_load 返回 None）→ 走默认，不抛错。"""
    yaml_path = tmp_path / "qmd.yaml"
    yaml_path.write_text("", encoding="utf-8")
    cfg = QmdConfig.load(db_path=tmp_path / "db.sqlite")
    assert cfg.chunking.size == 512


def test_overrides_none_section_raises(tmp_path: Path):
    """config_overrides 中某 section 为 None → ConfigError（防止调用方错误）。"""
    with pytest.raises(ConfigError):
        QmdConfig.load(
            db_path=tmp_path / "db.sqlite",
            config_overrides={"chunking": None},
        )


# ── 新增测试：ExpansionConfig + BlendingWeights ──────────────────────────────

def test_expansion_defaults(tmp_path: Path):
    """expansion 默认值校验。"""
    cfg = QmdConfig.load(db_path=tmp_path / "db.sqlite")
    assert cfg.expansion.enabled is False
    assert cfg.expansion.model_name == "Qwen/Qwen3-0.6B"
    assert cfg.expansion.strong_signal_threshold == 0.85
    assert cfg.expansion.strong_signal_gap == 0.15


def test_blending_defaults(tmp_path: Path):
    """retrieval.blending_mode 和 blending_weights 默认值校验。"""
    cfg = QmdConfig.load(db_path=tmp_path / "db.sqlite")
    assert cfg.retrieval.blending_mode == "pure_rerank"
    assert cfg.retrieval.blending_weights.top == (0.75, 0.25)
    assert cfg.retrieval.blending_weights.mid == (0.60, 0.40)
    assert cfg.retrieval.blending_weights.tail == (0.40, 0.60)


def test_expansion_yaml_override(tmp_path: Path):
    """yaml 可以启用 expansion。"""
    yaml_path = tmp_path / "qmd.yaml"
    yaml_path.write_text(
        yaml.safe_dump({"expansion": {"enabled": True, "model_name": "Qwen/Qwen3-1.7B"}}),
        encoding="utf-8",
    )
    cfg = QmdConfig.load(db_path=tmp_path / "db.sqlite")
    assert cfg.expansion.enabled is True
    assert cfg.expansion.model_name == "Qwen/Qwen3-1.7B"
    # 未覆盖字段保持默认
    assert cfg.expansion.strong_signal_threshold == 0.85


def test_blending_yaml_override(tmp_path: Path):
    """yaml 可覆盖 blending_mode 和 blending_weights（部分覆盖保留默认）。"""
    yaml_path = tmp_path / "qmd.yaml"
    yaml_path.write_text(
        yaml.safe_dump({
            "retrieval": {
                "blending_mode": "position_aware",
                "blending_weights": {"top": [0.8, 0.2]},
            }
        }),
        encoding="utf-8",
    )
    cfg = QmdConfig.load(db_path=tmp_path / "db.sqlite")
    assert cfg.retrieval.blending_mode == "position_aware"
    assert cfg.retrieval.blending_weights.top == (0.8, 0.2)
    # 未覆盖字段保持默认
    assert cfg.retrieval.blending_weights.mid == (0.60, 0.40)
    assert cfg.retrieval.blending_weights.tail == (0.40, 0.60)


def test_blending_invalid_mode_raises(tmp_path: Path):
    """无效 blending_mode → ConfigError。"""
    yaml_path = tmp_path / "qmd.yaml"
    yaml_path.write_text(
        yaml.safe_dump({"retrieval": {"blending_mode": "invalid_mode"}}),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        QmdConfig.load(db_path=tmp_path / "db.sqlite")
