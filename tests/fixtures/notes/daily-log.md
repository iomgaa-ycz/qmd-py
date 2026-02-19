# 开发日志 - 2024年2月

## 2024-02-19 (周一)

### 完成任务
- ✅ 修复了智能分块算法中的代码块保护逻辑
- ✅ 添加了 RRF 融合的单元测试
- ✅ 更新了文档中的 API 说明

### 遇到的问题
- SQLite FTS5 在中文分词时存在性能瓶颈
- 需要考虑引入 jieba 分词器

### 明天计划
- 实现 LLM Query Expansion 功能
- 完成 MCP 服务器的基本框架

---

## 2024-02-18 (周日)

### 完成任务
- ✅ 重构了 LLM 抽象层
- ✅ 集成了 llama-cpp-python

### 代码质量
- 测试覆盖率: 78% → 82%
- Lint 检查: 全部通过

---

## 2024-02-17 (周六)

### 完成任务
- ✅ 实现了向量检索的基本功能
- ✅ 添加了 sqlite-vec 扩展

### 技术笔记
使用 `vec_distance_cosine()` 函数时需要注意：
```sql
SELECT docid, vec_distance_cosine(embedding, ?) as distance
FROM chunks_vec
ORDER BY distance ASC
LIMIT 10;
```

---

## 2024-02-16 (周五)

### 学习记录
- 阅读了 BM25 算法论文
- 研究了 BEIR 基准测试方法

### 想法
混合检索的关键在于如何平衡召回和精度，需要更多实验验证。
