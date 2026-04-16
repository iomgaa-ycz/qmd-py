# QMD-Py — Query Markup Documents

[中文文档](README_CN.md)

An on-device hybrid search engine for Markdown documents. Python port of [qmd](https://github.com/tobi/qmd).

Combines BM25 full-text search, vector semantic search (Qwen3-Embedding-0.6B), and LLM re-ranking (Qwen3-Reranker-0.6B) — all running locally via SQLite + sqlite-vec.

## Install

```bash
pip install -e .               # core
pip install -e ".[dev]"        # + dev/test deps
pip install -e ".[testing]"    # + contract test deps (rank-bm25, deepdiff)
```

## Quick Start — Python API

```python
from qmd import connect

client = connect("my_docs.sqlite")
col = client.collection("notes")

# Add documents
col.add_document("doc1", "# Meeting Notes\n\nDiscussed project timeline.", {"tag": "meeting"})
col.add_documents([
    {"document_id": "doc2", "markdown": "# API Design\n\nREST endpoints..."},
    {"document_id": "doc3", "markdown": "# Deployment\n\nDocker setup..."},
])

# Search
results = col.hybrid_search("project timeline", top_k=5)
for r in results:
    print(f"{r.chunk_ref.document_id}: {r.score:.3f} — {r.text[:80]}")

# Search with reranking
results = col.hybrid_search("deployment", top_k=5, rerank=True)

client.close()
```

## Quick Start — CLI

```bash
# Add a document
python -m qmd document add --collection notes --document-id doc1 --markdown-file notes.md

# List documents
python -m qmd document list --collection notes

# Search
python -m qmd search --collection notes --query "project timeline" --top-k 5

# List collections
python -m qmd collection list
```

## Architecture

- **Storage**: SQLite + sqlite-vec (single-file database)
- **Embedding**: Qwen3-Embedding-0.6B (sentence-transformers, 1024-dim)
- **Reranker**: Qwen3-Reranker-0.6B (transformers, yes/no softmax)
- **Query Expansion**: Qwen3-0.6B (optional, configurable)
- **Fusion**: BM25 + Vector → Reciprocal Rank Fusion (RRF, k=60)
- **Blending**: Position-aware blending (optional, configurable weights)

## Configuration

Place `qmd.yaml` next to your `.sqlite` file:

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
  enabled: false         # Query expansion (Qwen3-0.6B)

retrieval:
  rrf_k: 60
  blending_mode: "pure_rerank"   # or "position_aware"
```

## Requirements

- Python >= 3.11
- GPU (optional): CUDA for accelerated embedding/reranking

## License

MIT
