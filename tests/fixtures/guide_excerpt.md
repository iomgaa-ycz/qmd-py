# 向量检索引擎使用指南

本指南介绍一个通用的向量检索引擎的基本概念与使用方式。目标读者是熟悉 Python 但不熟悉检索系统的开发者。

## 核心概念

### Collection

Collection 是一组相关文档的命名分组。每个 collection 内部维护自己的索引，彼此之间的数据严格隔离，搜索结果不会跨 collection 混入。

### Chunk 与 ChunkRef

一篇 markdown 文档在入库时会被切分为若干 chunk。每个 chunk 通过 `ChunkRef` 回指原始 markdown 的字符区间，便于上层系统在展示搜索结果时高亮证据片段。

## 使用流程

典型的使用流程包含三步：

1. 连接数据库得到 client
2. 取得或创建 collection
3. 添加文档后执行混合检索

示例代码如下：

```python
import qmd

client = qmd.connect("./index.db")
col = client.collection("rules")
col.add_document("doc1", "文档正文...", {"source": "manual"})
results = col.hybrid_search("关键词", top_k=5)
```

## 混合检索原理

`hybrid_search` 内部同时执行 BM25 和向量两路召回，然后用 Reciprocal Rank Fusion 融合排名。可选的重排阶段进一步利用交叉编码器提升前排结果的精度。

* BM25 擅长处理精确关键词匹配
* 向量召回擅长处理语义相似
* 融合后通常比单路更稳健

---

进一步的性能调优与配置参数请参阅对应章节。
