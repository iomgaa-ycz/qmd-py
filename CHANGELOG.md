# Changelog

## 0.1.0 (2026-02-19)

### Features
- BM25 全文检索 + 向量语义检索 + 混合检索（RRF 融合 + LLM 重排序）
- Query Expansion（查询扩展）
- Position-Aware Blending（位置感知混合）
- 智能分块（Markdown 断点检测，代码围栏保护）
- Context 系统（层级继承）
- 三种 LLM 后端：llama-cpp-python / sentence-transformers / FlagEmbedding
- CLI 完整命令集（add/remove/search/query/get/embed/ls/status/cleanup）
- MCP Server（stdio transport）
- 多种输出格式（JSON/CSV/XML/MD/Files）
- 文件监听（watchdog watcher）
- LLM 响应缓存
