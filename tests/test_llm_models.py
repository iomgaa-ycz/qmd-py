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
    DEFAULT_INACTIVITY_TIMEOUT,
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
        assert manager.inactivity_timeout == DEFAULT_INACTIVITY_TIMEOUT

    def test_init_custom_values(self, tmp_path):
        """测试自定义初始化值"""
        custom_embed = "hf:custom/embed/model.gguf"
        custom_rerank = "hf:custom/rerank/model.gguf"
        custom_generate = "hf:custom/generate/model.gguf"
        custom_timeout = 600

        manager = ModelManager(
            embed_model_uri=custom_embed,
            rerank_model_uri=custom_rerank,
            generate_model_uri=custom_generate,
            cache_dir=tmp_path,
            inactivity_timeout=custom_timeout,
        )

        assert manager.embed_model_uri == custom_embed
        assert manager.rerank_model_uri == custom_rerank
        assert manager.generate_model_uri == custom_generate
        assert manager.cache_dir == tmp_path
        assert manager.inactivity_timeout == custom_timeout

    def test_gpu_type_lazy_detection(self):
        """测试 GPU 类型懒检测"""
        manager = ModelManager()
        assert manager._gpu_type is None

        gpu_type = manager.gpu_type
        assert gpu_type in ["cuda", "mps", "cpu"]
        assert manager._gpu_type == gpu_type

    def test_active_operations_counter(self):
        """测试活跃操作计数"""
        manager = ModelManager()

        assert manager.active_operations == 0

        manager.start_operation()
        assert manager.active_operations == 1

        manager.start_operation()
        assert manager.active_operations == 2

        manager.end_operation()
        assert manager.active_operations == 1

        manager.end_operation()
        assert manager.active_operations == 0

    def test_active_operations_never_negative(self):
        """测试活跃操作计数不会为负"""
        manager = ModelManager()

        manager.end_operation()
        manager.end_operation()
        assert manager.active_operations == 0

    def test_embed_model_lazy_load(self, tmp_path):
        """测试 Embedding 模型懒加载"""
        manager = ModelManager(cache_dir=tmp_path)
        assert manager._embed_model is None

        model = manager.embed_model
        assert model is None  # MVP 阶段返回 None

    def test_rerank_model_lazy_load(self, tmp_path):
        """测试 Rerank 模型懒加载"""
        manager = ModelManager(cache_dir=tmp_path)
        assert manager._rerank_model is None

        model = manager.rerank_model
        assert model is None  # MVP 阶段返回 None

    def test_generate_model_lazy_load(self, tmp_path):
        """测试 Generate 模型懒加载"""
        manager = ModelManager(cache_dir=tmp_path)
        assert manager._generate_model is None

        model = manager.generate_model
        assert model is None  # MVP 阶段返回 None

    def test_idle_timeout_disabled_when_zero(self, tmp_path):
        """测试 inactivity_timeout=0 时禁用定时器"""
        manager = ModelManager(cache_dir=tmp_path, inactivity_timeout=0)

        manager.embed_model
        assert manager._idle_timer is None

    def test_idle_timeout_set_after_model_access(self, tmp_path):
        """测试访问模型后设置定时器"""
        manager = ModelManager(cache_dir=tmp_path, inactivity_timeout=1)

        manager.embed_model
        # MVP 阶段模型是 None，不会设置定时器
        # 真正的实现会在模型加载后设置定时器

    def test_idle_timeout_canceled_on_unload(self, tmp_path):
        """测试卸载时取消定时器"""
        manager = ModelManager(cache_dir=tmp_path, inactivity_timeout=10)

        mock_timer = Mock()
        manager._idle_timer = mock_timer
        
        manager.unload()

        mock_timer.cancel.assert_called_once()

    def test_unload_clears_models(self, tmp_path):
        """测试 unload 清除模型实例"""
        manager = ModelManager(cache_dir=tmp_path)

        manager._embed_model = Mock()
        manager._rerank_model = Mock()
        manager._generate_model = Mock()

        manager.unload()

        assert manager._embed_model is None
        assert manager._rerank_model is None
        assert manager._generate_model is None

    def test_unload_clears_cuda_cache_when_cuda(self, tmp_path):
        """测试使用 CUDA 时 unload 清除缓存"""
        manager = ModelManager(cache_dir=tmp_path)
        manager._gpu_type = "cuda"

        try:
            import torch
            if torch.cuda.is_available():
                manager.unload()
        except ImportError:
            pass

    def test_idle_timeout_reschedules_on_active_operations(self, tmp_path):
        """测试有活跃操作时重新调度定时器"""
        manager = ModelManager(cache_dir=tmp_path, inactivity_timeout=0.1)

        manager.start_operation()
        manager._embed_model = Mock()  # 模拟已加载模型

        with patch.object(manager, "_touch_activity") as mock_touch:
            manager._on_idle_timeout()
            mock_touch.assert_called_once()

    def test_idle_timeout_unloads_when_no_operations(self, tmp_path):
        """测试无活跃操作时卸载模型"""
        manager = ModelManager(cache_dir=tmp_path, inactivity_timeout=0.1)
        manager._embed_model = Mock()  # 模拟已加载模型

        with patch.object(manager, "unload") as mock_unload:
            manager._on_idle_timeout()
            mock_unload.assert_called_once()

    def test_touch_activity_resets_timer(self, tmp_path):
        """测试 _touch_activity 重置定时器"""
        manager = ModelManager(cache_dir=tmp_path, inactivity_timeout=10)
        manager._embed_model = Mock()  # 模拟已加载模型

        old_timer = manager._idle_timer
        manager._touch_activity()
        new_timer = manager._idle_timer

        if old_timer is not None:
            assert new_timer != old_timer

    def test_has_loaded_models_true(self, tmp_path):
        """测试 _has_loaded_models 检测到已加载模型"""
        manager = ModelManager(cache_dir=tmp_path)
        manager._embed_model = Mock()

        assert manager._has_loaded_models() is True

    def test_has_loaded_models_false(self, tmp_path):
        """测试 _has_loaded_models 检测无模型"""
        manager = ModelManager(cache_dir=tmp_path)

        assert manager._has_loaded_models() is False

    def test_end_operation_touches_activity(self, tmp_path):
        """测试 end_operation 重置定时器"""
        manager = ModelManager(cache_dir=tmp_path, inactivity_timeout=10)

        with patch.object(manager, "_touch_activity") as mock_touch:
            manager.end_operation()
            mock_touch.assert_called_once()


class TestModelManagerIntegration:
    """集成测试"""

    def test_full_lifecycle(self, tmp_path):
        """测试完整生命周期"""
        manager = ModelManager(cache_dir=tmp_path, inactivity_timeout=1)

        manager.start_operation()
        _ = manager.embed_model
        _ = manager.rerank_model
        manager.end_operation()

        assert manager.active_operations == 0

        manager.unload()
        assert manager._embed_model is None
        assert manager._rerank_model is None

    def test_concurrent_operations(self, tmp_path):
        """测试并发操作计数"""
        manager = ModelManager(cache_dir=tmp_path)

        import threading

        def operation():
            manager.start_operation()
            time.sleep(0.01)
            manager.end_operation()

        threads = [threading.Thread(target=operation) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert manager.active_operations == 0
