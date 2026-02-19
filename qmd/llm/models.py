"""
模型管理器

提供模型配置、GPU 检测、模型路径解析等功能。
"""

from pathlib import Path
from typing import Literal

from loguru import logger

# 默认模型 URI（HuggingFace 格式）
DEFAULT_EMBED_MODEL = "hf:ggml-org/embeddinggemma-300M-GGUF/embeddinggemma-300M-Q8_0.gguf"
DEFAULT_RERANK_MODEL = "hf:ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF/qwen3-reranker-0.6b-q8_0.gguf"
DEFAULT_GENERATE_MODEL = "hf:tobil/qmd-query-expansion-1.7B-gguf/qmd-query-expansion-1.7B-Q4_K_M.gguf"

# 模型缓存目录
DEFAULT_MODEL_CACHE_DIR = Path.home() / ".cache" / "qmd-py" / "models"

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
    模型配置容器（精简版）

    只负责保存模型配置（URI、cache_dir），不再管理懒加载和 Idle Timeout。
    后端类（LlamaCppBackend、SentenceTransformerBackend）自己管理模型加载。
    """

    def __init__(
        self,
        embed_model_uri: str | None = None,
        rerank_model_uri: str | None = None,
        generate_model_uri: str | None = None,
        cache_dir: Path | None = None,
        inactivity_timeout: int = 0,  # 保留参数以兼容旧代码，但已不使用
    ):
        """
        初始化模型配置

        Args:
            embed_model_uri: Embedding 模型 URI（默认 embeddinggemma）
            rerank_model_uri: Rerank 模型 URI（默认 Qwen3-Reranker）
            generate_model_uri: Generate 模型 URI（默认 qmd-query-expansion）
            cache_dir: 模型缓存目录
            inactivity_timeout: 已废弃，保留以兼容旧代码
        """
        self.embed_model_uri = embed_model_uri or DEFAULT_EMBED_MODEL
        self.rerank_model_uri = rerank_model_uri or DEFAULT_RERANK_MODEL
        self.generate_model_uri = generate_model_uri or DEFAULT_GENERATE_MODEL
        self.cache_dir = cache_dir or DEFAULT_MODEL_CACHE_DIR

    @property
    def gpu_type(self) -> GPUType:
        """
        获取 GPU 类型

        Returns:
            "cuda", "mps", 或 "cpu"
        """
        return detect_gpu()

    @property
    def embed_model(self):
        """保留以兼容旧代码，始终返回 None（后端自己加载模型）"""
        return None

    @property
    def rerank_model(self):
        """保留以兼容旧代码，始终返回 None（后端自己加载模型）"""
        return None

    @property
    def generate_model(self):
        """保留以兼容旧代码，始终返回 None（后端自己加载模型）"""
        return None
