"""Perf 测试 fixture：构建 10 万 chunk 规模语料库。

策略:
    1. 优先流式抽取 wikipedia-zh (wikimedia/wikipedia @ 20231101.zh)
    2. 失败 fallback 合成（~60 中文高频词拼接）
    3. 结果缓存到 tests/perf/.cache/corpus.sqlite，首次 ~20-40min，之后秒级
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
from loguru import logger


CACHE_DIR = Path(__file__).parent / ".cache"
CORPUS_DB = CACHE_DIR / "corpus.sqlite"
CORPUS_META = CACHE_DIR / "corpus.meta.json"
TARGET_DOCS = 100_000          # 每文档截断至约 1024 字符 ≈ 1 chunk
DOC_CHARS_APPROX = 1024
MIN_TEXT_LEN = 200             # wikipedia 文章至少要有这么长才入库


def _load_wikipedia_zh_streaming(target_docs: int) -> list[dict]:
    """流式抽取 wikipedia-zh 直到凑够 target_docs 份文档。"""
    from datasets import load_dataset  # 延迟导入：避免 datasets 未安装时模块级失败

    logger.info("尝试流式加载 wikimedia/wikipedia 20231101.zh ...")
    ds = load_dataset(
        "wikimedia/wikipedia", "20231101.zh", streaming=True, split="train"
    )
    docs: list[dict] = []
    for i, item in enumerate(ds):
        text = item.get("text", "")
        if len(text) < MIN_TEXT_LEN:
            continue
        docs.append({
            "document_id": f"wiki_{i}",
            "markdown": text[:DOC_CHARS_APPROX],
            "metadata": {"title": item.get("title", "")},
        })
        if len(docs) >= target_docs:
            break
    logger.info("wikipedia-zh 抽取完成：{} docs", len(docs))
    return docs


# ~60 个中文高频词；作为 wikipedia 不可用时的 fallback 合成池
_VOCAB = [
    "法律", "合同", "条款", "规定", "责任", "义务", "权利", "主体",
    "审核", "批准", "备案", "登记", "注册", "许可", "执照", "证书",
    "标准", "规范", "技术", "工程", "项目", "方案", "设计", "实施",
    "报告", "记录", "档案", "文件", "数据", "信息", "系统", "平台",
    "管理", "监督", "检查", "评估", "验收", "考核", "审计", "核查",
    "市场", "客户", "产品", "服务", "流程", "质量", "成本", "效率",
    "计划", "任务", "目标", "结果", "分析", "决策", "执行", "反馈",
    "培训", "教育", "学习", "研究",
]


def _gen_synthetic_corpus(target_docs: int) -> list[dict]:
    """合成语料 fallback：从词池随机拼接，模拟真实 markdown 段落结构。"""
    rng = random.Random(42)
    docs: list[dict] = []
    for i in range(target_docs):
        paragraphs = []
        for _ in range(rng.randint(2, 5)):
            words = rng.choices(_VOCAB, k=rng.randint(30, 80))
            paragraphs.append("".join(words) + "。")
        md = f"# 文档 {i}\n\n" + "\n\n".join(paragraphs)
        docs.append({
            "document_id": f"syn_{i}",
            "markdown": md,
            "metadata": {"source": "synthetic"},
        })
    logger.info("合成语料完成：{} docs", len(docs))
    return docs


def _build_db(db_path: Path, docs: list[dict], source: str) -> None:
    """批量入库到 connect(db_path).collection('bench')，每批 500 控制内存。"""
    from qmd import connect

    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("开始构建 perf DB: {} ({} docs)", db_path, len(docs))
    client = connect(db_path)
    col = client.collection("bench")
    BATCH = 500
    for i in range(0, len(docs), BATCH):
        col.add_documents(docs[i : i + BATCH])
        logger.info("已入库 {}/{}", min(i + BATCH, len(docs)), len(docs))
    info = col.info()
    client.close()

    CORPUS_META.write_text(
        json.dumps({
            "source": source,
            "doc_count": info.document_count,
            "chunk_count": info.chunk_count,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("perf DB 构建完成：{} chunks (source={})", info.chunk_count, source)


@pytest.fixture(scope="session")
def large_corpus_db() -> Path:
    """10 万 chunk 规模 SQLite。首次构建 ~20-40min，之后秒级返回。

    缓存在 tests/perf/.cache/corpus.sqlite，.gitignore 已排除。
    """
    if CORPUS_DB.exists() and CORPUS_META.exists():
        meta = json.loads(CORPUS_META.read_text(encoding="utf-8"))
        # 20% 容差：chunk_count 在 target 的 80% 以上即视为有效缓存
        if meta.get("chunk_count", 0) >= TARGET_DOCS * 0.8:
            logger.info(
                "复用已有 perf DB: {} ({} chunks)", CORPUS_DB, meta["chunk_count"]
            )
            return CORPUS_DB

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        docs = _load_wikipedia_zh_streaming(TARGET_DOCS)
        source = "wikipedia-zh"
    except Exception as e:
        logger.warning(
            "wikipedia-zh 不可用 ({}: {}), fallback 合成语料", type(e).__name__, e
        )
        docs = _gen_synthetic_corpus(TARGET_DOCS)
        source = "synthetic"

    _build_db(CORPUS_DB, docs, source)
    return CORPUS_DB
