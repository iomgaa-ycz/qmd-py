"""
模型管理器

提供模型下载、GPU 检测、懒加载、Idle Timeout 等功能。
"""

import threading
from pathlib import Path
from typing import Any, Literal

from loguru import logger

# 默认模型 URI（HuggingFace 格式）
DEFAULT_EMBED_MODEL = "hf:ggml-org/embeddinggemma-300M-GGUF/embeddinggemma-300M-Q8_0.gguf"
DEFAULT_RERANK_MODEL = "hf:ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF/qwen3-reranker-0.6b-q8_0.gguf"
DEFAULT_GENERATE_MODEL = "hf:tobil/qmd-query-expansion-1.7B-gguf/qmd-query-expansion-1.7B-Q4_K_M.gguf"

# 模型缓存目录
DEFAULT_MODEL_CACHE_DIR = Path.home() / ".cache" / "qmd-py" / "models"

# 默认 Idle Timeout（秒）
DEFAULT_INACTIVITY_TIMEOUT = 300  # 5 分钟

# GPU 类型
GPUType = Literal["cuda", "mps", "cpu"]


def detect_gpu() -> GPUType:
    """
    检测可用的 GPU 类型

    优先级：CUDA > MPS > CPU
    如果 GPU 初始化失败，自动降级到下一个选项。

    Returns:
        "cuda", "mps", 或 "cpu"
    """
    # 尝试检测 CUDA
    try:
        import torch

        if torch.cuda.is_available():
            # 尝试实际使用 CUDA
            try:
                torch.cuda.init()
                device = torch.device("cuda")
                # 测试分配一个小 tensor
                test_tensor = torch.zeros(1, device=device)
                del test_tensor
                logger.info("检测到 CUDA GPU")
                return "cuda"
            except Exception as e:
                logger.warning(f"CUDA 可用但初始化失败，降级到下一个选项: {e}")
    except ImportError:
        pass

    # 尝试检测 MPS (Apple Silicon)
    try:
        import torch

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            try:
                device = torch.device("mps")
                # 测试分配一个小 tensor
                test_tensor = torch.zeros(1, device=device)
                del test_tensor
                logger.info("检测到 MPS GPU (Apple Silicon)")
                return "mps"
            except Exception as e:
                logger.warning(f"MPS 可用但初始化失败，降级到 CPU: {e}")
    except (ImportError, AttributeError):
        pass

    # 降级到 CPU
    logger.warning("未检测到 GPU，使用 CPU（速度较慢）")
    return "cpu"


def resolve_model_path(model_uri: str, cache_dir: Path | None = None) -> Path:
    """
    解析模型 URI 到本地路径

    支持格式：
    - "hf:org/repo/file.gguf" → 从 HuggingFace 下载
    - "/path/to/local/model.gguf" → 直接使用本地路径

    Args:
        model_uri: 模型 URI
        cache_dir: 缓存目录（默认 ~/.cache/qmd-py/models/）

    Returns:
        模型文件的本地路径

    Examples:
        >>> resolve_model_path("hf:ggml-org/embeddinggemma-300M-GGUF/model.gguf")
        PosixPath('/home/user/.cache/qmd-py/models/model.gguf')
        >>> resolve_model_path("/local/path/model.gguf")
        PosixPath('/local/path/model.gguf')
    """
    if cache_dir is None:
        cache_dir = DEFAULT_MODEL_CACHE_DIR

    # 确保缓存目录存在
    cache_dir.mkdir(parents=True, exist_ok=True)

    if model_uri.startswith("hf:"):
        # HuggingFace 格式：hf:org/repo/file.gguf
        hf_path = model_uri[3:]  # 去除 "hf:" 前缀
        parts = hf_path.split("/")

        if len(parts) < 3:
            raise ValueError(
                f"无效的 HuggingFace URI 格式: {model_uri}。"
                f"期望格式: hf:org/repo/file.gguf"
            )

        repo_id = "/".join(parts[:2])  # org/repo
        filename = "/".join(parts[2:])  # file.gguf

        # 在 MVP 阶段，我们返回缓存路径，但不实际下载
        # 真正的下载会在首次使用模型时触发（懒加载）
        local_path = cache_dir / filename

        logger.debug(
            f"解析 HF 模型: {model_uri} → repo={repo_id}, file={filename}, "
            f"local_path={local_path}"
        )

        return local_path

    else:
        # 本地路径
        local_path = Path(model_uri)
        logger.debug(f"使用本地模型路径: {local_path}")
        return local_path


class ModelManager:
    """
    模型管理器

    负责模型的懒加载、GPU 检测、Idle Timeout 管理。
    """

    def __init__(
        self,
        embed_model_uri: str | None = None,
        rerank_model_uri: str | None = None,
        generate_model_uri: str | None = None,
        cache_dir: Path | None = None,
        inactivity_timeout: int = DEFAULT_INACTIVITY_TIMEOUT,
    ):
        """
        初始化模型管理器

        Args:
            embed_model_uri: Embedding 模型 URI（默认 embeddinggemma）
            rerank_model_uri: Rerank 模型 URI（默认 Qwen3-Reranker）
            generate_model_uri: Generate 模型 URI（默认 qmd-query-expansion）
            cache_dir: 模型缓存目录
            inactivity_timeout: 无活动超时（秒），0 表示禁用
        """
        self.embed_model_uri = embed_model_uri or DEFAULT_EMBED_MODEL
        self.rerank_model_uri = rerank_model_uri or DEFAULT_RERANK_MODEL
        self.generate_model_uri = generate_model_uri or DEFAULT_GENERATE_MODEL
        self.cache_dir = cache_dir or DEFAULT_MODEL_CACHE_DIR
        self.inactivity_timeout = inactivity_timeout

        # 模型实例（懒加载）
        self._embed_model: Any | None = None
        self._rerank_model: Any | None = None
        self._generate_model: Any | None = None

        # GPU 类型（懒检测）
        self._gpu_type: GPUType | None = None

        # Idle Timeout 定时器
        self._idle_timer: threading.Timer | None = None
        self._timer_lock = threading.Lock()

        # 活跃操作计数
        self._active_operations = 0
        self._operations_lock = threading.Lock()

    @property
    def gpu_type(self) -> GPUType:
        """
        获取 GPU 类型（懒检测）

        Returns:
            "cuda", "mps", 或 "cpu"
        """
        if self._gpu_type is None:
            self._gpu_type = detect_gpu()
        return self._gpu_type

    @property
    def embed_model(self) -> Any | None:
        """
        获取 Embedding 模型（懒加载）

        Returns:
            模型实例，未加载时为 None
        """
        if self._embed_model is None:
            self._load_embed_model()
        self._touch_activity()
        return self._embed_model

    @property
    def rerank_model(self) -> Any | None:
        """
        获取 Rerank 模型（懒加载）

        Returns:
            模型实例，未加载时为 None
        """
        if self._rerank_model is None:
            self._load_rerank_model()
        self._touch_activity()
        return self._rerank_model

    @property
    def generate_model(self) -> Any | None:
        """
        获取 Generate 模型（懒加载）

        Returns:
            模型实例，未加载时为 None
        """
        if self._generate_model is None:
            self._load_generate_model()
        self._touch_activity()
        return self._generate_model

    @property
    def active_operations(self) -> int:
        """
        获取当前活跃操作数

        Returns:
            活跃操作数量
        """
        with self._operations_lock:
            return self._active_operations

    def _load_embed_model(self) -> None:
        """
        加载 Embedding 模型

        在 MVP 阶段，这只是占位符。
        真正的 GGUF 模型加载会在具体实现中完成。
        """
        model_path = resolve_model_path(self.embed_model_uri, self.cache_dir)
        logger.info(f"加载 Embedding 模型: {self.embed_model_uri} → {model_path}")

        # MVP 阶段：不实际加载模型
        # 真正的实现会使用 llama-cpp-python 或 sentence-transformers
        self._embed_model = None  # Placeholder

        self._touch_activity()

    def _load_rerank_model(self) -> None:
        """
        加载 Rerank 模型

        在 MVP 阶段，这只是占位符。
        """
        model_path = resolve_model_path(self.rerank_model_uri, self.cache_dir)
        logger.info(f"加载 Rerank 模型: {self.rerank_model_uri} → {model_path}")

        # MVP 阶段：不实际加载模型
        self._rerank_model = None  # Placeholder

        self._touch_activity()

    def _load_generate_model(self) -> None:
        """
        加载 Generate 模型

        在 MVP 阶段，这只是占位符。
        """
        model_path = resolve_model_path(self.generate_model_uri, self.cache_dir)
        logger.info(f"加载 Generate 模型: {self.generate_model_uri} → {model_path}")

        # MVP 阶段：不实际加载模型
        self._generate_model = None  # Placeholder

        self._touch_activity()

    def _touch_activity(self) -> None:
        """
        重置 Idle Timeout 定时器

        每次模型访问或操作时调用。
        """
        with self._timer_lock:
            # 清除现有定时器
            if self._idle_timer is not None:
                self._idle_timer.cancel()
                self._idle_timer = None

            # 如果超时禁用，不设置定时器
            if self.inactivity_timeout <= 0:
                return

            # 只在有模型加载时设置定时器
            if not self._has_loaded_models():
                return

            # 设置新的定时器
            self._idle_timer = threading.Timer(
                self.inactivity_timeout, self._on_idle_timeout
            )
            self._idle_timer.daemon = True  # 不阻止程序退出
            self._idle_timer.start()

            logger.debug(f"重置 Idle Timeout 定时器: {self.inactivity_timeout}s")

    def _has_loaded_models(self) -> bool:
        """
        检查是否有已加载的模型

        Returns:
            如果至少有一个模型已加载，返回 True
        """
        return any(
            [
                self._embed_model is not None,
                self._rerank_model is not None,
                self._generate_model is not None,
            ]
        )

    def _on_idle_timeout(self) -> None:
        """
        Idle Timeout 回调

        检查是否有活跃操作，如果有则重新调度，否则卸载模型。
        """
        with self._operations_lock:
            if self._active_operations > 0:
                # 有活跃操作，重新调度定时器
                logger.debug(
                    f"Idle Timeout 触发，但有 {self._active_operations} 个活跃操作，重新调度"
                )
                self._touch_activity()
                return

        # 没有活跃操作，卸载模型
        logger.info(f"Idle Timeout 触发（{self.inactivity_timeout}s），卸载模型")
        self.unload()

    def start_operation(self) -> None:
        """
        标记操作开始

        在执行 LLM 操作前调用，防止 Idle Timeout 期间卸载模型。
        """
        with self._operations_lock:
            self._active_operations += 1
            logger.debug(
                f"操作开始，活跃操作数: {self._active_operations}"
            )

    def end_operation(self) -> None:
        """
        标记操作结束

        在 LLM 操作完成后调用。
        """
        with self._operations_lock:
            self._active_operations = max(0, self._active_operations - 1)
            logger.debug(
                f"操作结束，活跃操作数: {self._active_operations}"
            )

        # 操作结束后重置定时器
        self._touch_activity()

    def unload(self) -> None:
        """
        卸载所有已加载的模型并释放资源

        包括：
        1. 清除模型实例
        2. 清除 CUDA 缓存（如果使用 CUDA）
        3. 取消 Idle Timeout 定时器
        """
        logger.info("卸载所有模型")

        # 取消定时器
        with self._timer_lock:
            if self._idle_timer is not None:
                self._idle_timer.cancel()
                self._idle_timer = None

        # 清除模型实例
        # MVP 阶段：这些是 None，真正的实现需要调用模型的 dispose/close 方法
        self._embed_model = None
        self._rerank_model = None
        self._generate_model = None

        # 清除 CUDA 缓存
        if self._gpu_type == "cuda":
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    logger.info("已清除 CUDA 缓存")
            except ImportError:
                pass

        logger.info("模型卸载完成")

    def __del__(self) -> None:
        """
        析构函数，确保资源释放
        """
        try:
            self.unload()
        except Exception:
            pass  # 忽略析构时的错误
