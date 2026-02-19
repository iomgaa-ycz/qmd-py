"""
测试模型管理器

测试 GPU 检测、Idle Timeout、模型 URI 解析、活跃操作计数等。
"""

import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from qmd.llm.models import (
    DEFAULT_EMBED_MODEL,
    DEFAULT_GENERATE_MODEL,
    DEFAULT_MODEL_CACHE_DIR,
    DEFAULT_RERANK_MODEL,
    ModelManager,
    detect_gpu,
    resolve_model_path,
)


class TestDetectGPU:
    """测试 GPU 检测"""

    def test_detect_gpu_returns_valid_type(self):
        """测试 GPU 检测返回合法值"""
        gpu_type = detect_gpu()
        assert gpu_type in ["cuda", "mps", "cpu"]

    def test_detect_gpu_with_real_torch(self):
        """测试使用真实 torch 检测 GPU"""
        try:
            import torch
            gpu_type = detect_gpu()
            if torch.cuda.is_available():
                assert gpu_type == "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                assert gpu_type == "mps"
            else:
                assert gpu_type == "cpu"
        except ImportError:
            assert detect_gpu() == "cpu"


class TestResolveModelPath:
    """测试模型路径解析"""

    def test_resolve_hf_model_path(self, tmp_path):
        """测试解析 HuggingFace URI"""
        model_uri = "hf:ggml-org/embeddinggemma-300M-GGUF/model.gguf"
        result = resolve_model_path(model_uri, cache_dir=tmp_path)

        assert result == tmp_path / "model.gguf"
        assert tmp_path.exists()

    def test_resolve_hf_model_with_subdirs(self, tmp_path):
        """测试解析带子目录的 HF URI"""
        model_uri = "hf:org/repo/subdir/file.gguf"
        result = resolve_model_path(model_uri, cache_dir=tmp_path)

        assert result == tmp_path / "subdir/file.gguf"

    def test_resolve_local_path(self, tmp_path):
        """测试解析本地路径"""
        local_model = tmp_path / "local_model.gguf"
        result = resolve_model_path(str(local_model), cache_dir=tmp_path)

        assert result == local_model

    def test_resolve_hf_invalid_format(self, tmp_path):
        """测试无效的 HF URI 格式"""
        with pytest.raises(ValueError, match="无效的 HuggingFace URI 格式"):
            resolve_model_path("hf:invalid", cache_dir=tmp_path)

    def test_resolve_creates_cache_dir(self):
        """测试自动创建缓存目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "new_cache"
            assert not cache_dir.exists()

            resolve_model_path("hf:org/repo/model.gguf", cache_dir=cache_dir)

            assert cache_dir.exists()


class TestModelManager:
    """测试模型管理器"""

    def test_init_default_values(self):
        """测试默认初始化值"""
        manager = ModelManager()

        assert manager.embed_model_uri == DEFAULT_EMBED_MODEL
        assert manager.rerank_model_uri == DEFAULT_RERANK_MODEL
        assert manager.generate_model_uri == DEFAULT_GENERATE_MODEL
        assert manager.cache_dir == DEFAULT_MODEL_CACHE_DIR

    def test_init_custom_values(self, tmp_path):
        """测试自定义初始化值"""
        custom_embed = "hf:custom/embed/model.gguf"
        custom_rerank = "hf:custom/rerank/model.gguf"
        custom_generate = "hf:custom/generate/model.gguf"

        manager = ModelManager(
            embed_model_uri=custom_embed,
            rerank_model_uri=custom_rerank,
            generate_model_uri=custom_generate,
            cache_dir=tmp_path,
        )

        assert manager.embed_model_uri == custom_embed
        assert manager.rerank_model_uri == custom_rerank
        assert manager.generate_model_uri == custom_generate
        assert manager.cache_dir == tmp_path

    def test_gpu_type_detection(self):
        """测试 GPU 类型检测"""
        manager = ModelManager()
        gpu_type = manager.gpu_type
        assert gpu_type in ["cuda", "mps", "cpu"]

    def test_model_properties_return_none(self):
        """测试模型属性始终返回 None（后端自己管理加载）"""
        manager = ModelManager()
        assert manager.embed_model is None
        assert manager.rerank_model is None
        assert manager.generate_model is None
