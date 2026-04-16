# QMD-Py — Query Markup Documents

[English](README.md)

本地运行的 Markdown 混合检索引擎。[qmd](https://github.com/tobi/qmd) 的 Python 移植版。

结合 BM25 全文检索、向量语义检索（Qwen3-Embedding-0.6B）和 LLM 重排序（Qwen3-Reranker-0.6B），全部本地运行，基于 SQLite + sqlite-vec。

## 安装

```bash
pip install -e .               # 核心
pip install -e ".[dev]"        # + 开发/测试依赖
pip install -e ".[testing]"    # + 契约测试依赖 (rank-bm25, deepdiff)
```

## 快速开始 — Python API

```python
from qmd import connect

client = connect("my_docs.sqlite")
col = client.collection("notes")

# 添加文档
col.add_document("doc1", "# 会议记录\n\n讨论了项目时间线。", {"tag": "meeting"})
col.add_documents([
    {"document_id": "doc2", "markdown": "# API 设计\n\nREST 接口..."},
    {"document_id": "doc3", "markdown": "# 部署\n\nDocker 配置..."},
])

# 搜索
results = col.hybrid_search("项目时间线", top_k=5)
for r in results:
    print(f"{r.chunk_ref.document_id}: {r.score:.3f} — {r.text[:80]}")

# 带重排序的搜索
results = col.hybrid_search("部署", top_k=5, rerank=True)

client.close()
```

## 快速开始 — CLI

```bash
# 添加文档
python -m qmd document add --collection notes --document-id doc1 --markdown-file notes.md

# 列出文档
python -m qmd document list --collection notes

# 搜索
python -m qmd search --collection notes --query "项目时间线" --top-k 5

# 列出 collection
python -m qmd collection list
```

## 架构

- **存储**: SQLite + sqlite-vec（单文件数据库）
- **Embedding**: Qwen3-Embedding-0.6B（sentence-transformers，1024 维）
- **Reranker**: Qwen3-Reranker-0.6B（transformers，yes/no softmax 打分）
- **Query Expansion**: Qwen3-0.6B（可选，yaml 可配）
- **融合**: BM25 + Vector → RRF（k=60）
- **Blending**: Position-aware blending（可选，权重可配）

## 配置

在 `.sqlite` 文件同目录放置 `qmd.yaml`：

```yaml
chunking:
  size: 512
  overlap: 64

embedding:
  batch_size: "auto"     # GPU=64, CPU=16

rerank:
  enabled: false
  top_k_candidates: 40

expansion:
  enabled: false         # Query Expansion (Qwen3-0.6B)

retrieval:
  rrf_k: 60
  blending_mode: "pure_rerank"   # 或 "position_aware"
```

## 系统要求

- Python >= 3.11
- GPU（可选）：CUDA 加速 embedding/reranking

## License

MIT
