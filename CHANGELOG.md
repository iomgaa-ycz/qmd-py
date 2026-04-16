# Changelog

## 0.1.1 — 完全重写

qmd-py 0.1.1 是完整重写版本，与旧 API 不兼容。

### 核心功能
- SQLite + sqlite-vec 混合检索引擎
- Qwen3-Embedding-0.6B 向量编码（sentence-transformers）
- Qwen3-Reranker-0.6B 重排序（transformers, yes/no softmax）
- BM25 + Vector + RRF 融合检索（k=60）
- 批量 `add_documents` API（原子事务，fail-fast 校验）
- `qmd.yaml` 配置系统（chunking / embedding / rerank / retrieval / expansion）
- Query Expansion（Qwen3-0.6B，可选）
- Position-aware Blending（可选，权重可配）
- Strong Signal Skip（BM25 强信号时跳过 expansion）
- CLI（`python -m qmd`）+ MCP 接口
