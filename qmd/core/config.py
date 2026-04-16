"""qmd.yaml 配置系统：pydantic schema + 加载优先级。

加载优先级（高 → 低）：
1. connect(db_path, config_overrides={...}) 显式 kwargs
2. {db_path 同目录}/qmd.yaml 自动发现
3. pydantic 默认值（yaml 不存在不报错）
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


class ConfigError(Exception):
    """配置解析或校验错误。消息包含字段路径以便定位。"""


class ChunkingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    size: int = 512
    overlap: int = 64
    strategy: Literal["semantic"] = "semantic"


class EmbeddingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    backend: Literal["sentence_tf"] = "sentence_tf"
    model_name: str = "Qwen/Qwen3-Embedding-0.6B"
    dim: int = 1024
    batch_size: int = 64  # "auto" 在 validator 中解析；默认值会被覆盖

    @field_validator("batch_size", mode="before")
    @classmethod
    def _resolve_auto(cls, v: object) -> int:
        """将 'auto' 解析为 GPU=64/CPU=16。"""
        if v == "auto":
            import torch  # lazy: only when resolving 'auto'
            return 64 if torch.cuda.is_available() else 16
        return int(v)  # type: ignore[arg-type]


class RerankConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    enabled: bool = False
    backend: Literal["sentence_tf"] = "sentence_tf"
    model_name: str = "Qwen/Qwen3-Reranker-0.6B"
    top_k_candidates: int = 40


class BlendingWeights(BaseModel):
    """Position-Aware Blending 的权重配置（rrf_weight, rerank_weight）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)
    top: tuple[float, float] = (0.75, 0.25)   # Rank 1-3
    mid: tuple[float, float] = (0.60, 0.40)   # Rank 4-10
    tail: tuple[float, float] = (0.40, 0.60)  # Rank 11+


class RetrievalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rrf_k: int = 60
    bm25_top_k: int = 20
    vector_top_k: int = 20
    blending_mode: Literal["pure_rerank", "position_aware"] = "pure_rerank"
    blending_weights: BlendingWeights = BlendingWeights()


class ExpansionConfig(BaseModel):
    """LLM Query Expansion 配置。"""

    model_config = ConfigDict(extra="forbid", frozen=True)
    enabled: bool = False
    model_name: str = "Qwen/Qwen3-0.6B"
    strong_signal_threshold: float = 0.85
    strong_signal_gap: float = 0.15


class QmdConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    chunking: ChunkingConfig = ChunkingConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    rerank: RerankConfig = RerankConfig()
    retrieval: RetrievalConfig = RetrievalConfig()
    expansion: ExpansionConfig = ExpansionConfig()

    @classmethod
    def load(
        cls,
        db_path: str | Path,
        config_overrides: dict[str, Any] | None = None,
    ) -> "QmdConfig":
        """按优先级加载配置。

        优先级（高 → 低）：
            1. config_overrides kwargs
            2. {db_path 同目录}/qmd.yaml
            3. pydantic 默认值
        """
        db_p = Path(db_path)
        yaml_path = db_p.parent / "qmd.yaml"
        yaml_data: dict[str, Any] = {}

        if yaml_path.exists():
            try:
                with yaml_path.open("r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                if loaded is None:
                    yaml_data = {}
                elif isinstance(loaded, dict):
                    yaml_data = loaded
                else:
                    raise ConfigError(
                        f"qmd.yaml 顶层结构必须是 dict，实际为 {type(loaded).__name__}: {yaml_path}"
                    )
            except yaml.YAMLError as e:
                raise ConfigError(f"qmd.yaml 语法错误 ({yaml_path}): {e}") from e

        if config_overrides:
            none_sections = [k for k, v in config_overrides.items() if v is None]
            if none_sections:
                raise ConfigError(f"config_overrides 中字段不能为 None: {none_sections}")

        merged = _deep_merge(yaml_data, config_overrides or {})

        try:
            return cls.model_validate(merged)
        except ValidationError as e:
            raise ConfigError(f"qmd.yaml schema 校验失败: {e}") from e


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """深度合并两个 dict，override 覆盖 base。"""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
