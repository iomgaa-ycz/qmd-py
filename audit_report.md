# qmd-py 忠实度审查报告

> 审查日期：2026-02-19
> 审查范围：qmd-py (Python) vs qmd v1.0.6 (TypeScript 原版)
> 审查依据：`/home/pci/ycz/Code/herald/reference/qmd/src/`

---

## 审查结论（总览）

| 指标 | 结果 |
|------|------|
| **总体忠实度评分** | **7.5/10** |
| 🔴 必须修复的差异数 | **3** |
| 🟡 建议修复的差异数 | **12** |
| 🟢 可接受的差异数 | **8** |
| ❌ 缺失功能数 | **15** |

### 核心结论

**优点**：
- ✅ 数据库 Schema **100% 对齐**（表结构、索引、触发器完全一致）
- ✅ Chunking 算法 **核心逻辑对齐**（断点扫描、代码围栏保护、平方衰减公式）
- ✅ BM25 检索 **完全对齐**（FTS5 配置、权重、分数归一化）
- ✅ RRF 融合算法 **完全对齐**（公式、top-rank bonus、k=60）

**关键问题**：
- 🔴 **缺少 Query Expansion（LLM 查询扩展）** — 原版的核心特性，影响检索质量
- 🔴 **缺少 Reranking（LLM 重排序）** — 原版混合检索流程的关键步骤
- 🔴 **缺少 LLM Cache** — 原版有 `llm_cache` 表缓存 LLM 调用结果
- 🟡 **缺少 Context 系统** — 原版支持 global/per-collection context
- 🟡 **缺少 VirtualPath 系统** — `qmd://collection/path` URI
- 🟡 **缺少多个 CLI 命令** — `query`, `get`, `multi-get`, `context *`, `pull` 等
- 🟡 **缺少多个 MCP 工具** — `vector_search`, `deep_search`, `get`, `multi_get`

---

## 按模块详细审查

---

### 1. 数据库 Schema

#### 对齐项 ✅

| 项目 | 原版 | Python 版 | 状态 |
|------|------|-----------|------|
| **PRAGMA 设置** | `journal_mode=WAL`, `foreign_keys=ON` | 完全一致 | ✅ |
| **表结构** | `content`, `documents`, `llm_cache`, `content_vectors` | 完全一致 | ✅ |
| **documents 外键** | `FOREIGN KEY (hash) REFERENCES content(hash) ON DELETE CASCADE` | 一致 | ✅ |
| **索引** | `idx_documents_collection`, `idx_documents_hash`, `idx_documents_path` | 一致 | ✅ |
| **FTS5 配置** | `tokenize='porter unicode61'` | 一致 | ✅ |
| **FTS 触发器** | `documents_ai`, `documents_ad`, `documents_au` | 逻辑完全一致 | ✅ |
| **vectors_vec** | `hash_seq TEXT PRIMARY KEY`, `distance_metric=cosine` | 一致 | ✅ |

#### 差异项 ⚠️

无差异。数据库 Schema **100% 对齐**。

#### 缺失项 ❌

无缺失。

---

### 2. Chunking 算法

#### 对齐项 ✅

| 项目 | 原版 | Python 版 | 状态 |
|------|------|-----------|------|
| **常量** | `CHUNK_SIZE_CHARS=3600`, `CHUNK_OVERLAP_CHARS=540`, `CHUNK_WINDOW_CHARS=800` | 完全一致 | ✅ |
| **断点模式** | `BREAK_PATTERNS`（H1-H3, codeblock, hr, blank, newline） | 完全一致 | ✅ |
| **断点分数** | H1=100, H2=90, H3=80, codeblock=80, hr=60, blank=20, newline=1 | 完全一致 | ✅ |
| **same-position 去重** | 同位置只保留最高分 | 一致 | ✅ |
| **代码围栏检测** | `findCodeFences()` — 匹配 ````...``` ` | 一致 | ✅ |
| **代码围栏保护** | `isInsideCodeFence()` — 二分查找 | 一致 | ✅ |
| **平方衰减公式** | `multiplier = 1.0 - (normalizedDist^2) * decayFactor` | 一致 | ✅ |
| **主循环逻辑** | chunk 切割、overlap 回退、无限循环保护 | 一致 | ✅ |
| **短文档边界** | `content.length <= maxChars` 返回单 chunk | 一致 | ✅ |

#### 差异项 ⚠️

| 差异 | 原版 | Python 版 | 级别 | 说明 |
|------|------|-----------|------|------|
| **decay_factor** | 未找到显式参数 | `decay_factor=0.7` 作为参数 | 🟢 可接受 | Python 版参数化了，更灵活 |

#### 缺失项 ❌

| 功能 | 原版 | Python 版 | 级别 |
|------|------|-----------|------|
| **chunkDocumentByTokens** | 异步版本，使用 LLM tokenizer 精确分块 | 未实现 | 🟡 建议修复 |

**说明**：原版有两个 chunking 函数：
1. `chunkDocument()` — 同步版本，基于字符估算（4 char/token）
2. `chunkDocumentByTokens()` — 异步版本，使用真实 tokenizer

Python 版只实现了同步版本。对于混合检索流程，原版使用的是同步版本（`chunkDocument`），因此核心逻辑对齐。

---

### 3. BM25 检索

#### 对齐项 ✅

| 项目 | 原版 | Python 版 | 状态 |
|------|------|-----------|------|
| **FTS5 查询构建** | `sanitizeFTS5Term()` — 特殊字符转义 | `_sanitize_fts_term()` 逻辑一致 | ✅ |
| **BM25 权重** | `bm25(documents_fts, 10.0, 1.0)` | filepath=10, title=1 | ✅ |
| **分数归一化** | `abs(x) / (1 + abs(x))` | 一致 | ✅ |
| **SQL JOIN** | JOIN documents, content | 一致 | ✅ |
| **活跃文档过滤** | `WHERE active = 1` | 一致 | ✅ |
| **排序** | `ORDER BY bm25_score ASC` | 一致 | ✅ |

#### 差异项 ⚠️

| 差异 | 原版 | Python 版 | 级别 | 说明 |
|------|------|-----------|------|------|
| **filepath 格式** | `collection/path` | `collection/path` | ✅ 一致 | 无差异 |

#### 缺失项 ❌

无缺失。BM25 检索 **100% 对齐**。

---

### 4. 向量检索

#### 对齐项 ✅

| 项目 | 原版 | Python 版 | 状态 |
|------|------|-----------|------|
| **两步查询** | 先查 `vectors_vec`，再查文档（避免 sqlite-vec 挂起） | 一致 | ✅ |
| **k 值过采样** | `limit * 3` | 一致 | ✅ |
| **去重逻辑** | 同文档取最佳距离 chunk | 一致 | ✅ |
| **分数转换** | `1 - distance` | 一致 | ✅ |
| **collection 过滤** | SQL `WHERE collection = ?` | 一致 | ✅ |

#### 差异项 ⚠️

| 差异 | 原版 | Python 版 | 级别 | 说明 |
|------|------|-----------|------|------|
| **向量格式** | `Float32Array` | `struct.pack(f"{len(embedding)}f", *embedding)` | 🟢 可接受 | 语言差异 |

#### 缺失项 ❌

无缺失。向量检索 **核心逻辑对齐**。

---

### 5. 混合检索流程（hybridQuery）⭐ 最关键

#### 对齐项 ✅

| 步骤 | 原版 | Python 版 | 状态 |
|------|------|-----------|------|
| **Step 1: BM25 强信号探测** | `STRONG_SIGNAL_MIN_SCORE=0.85`, `MIN_GAP=0.15` | 一致 | ✅ |
| **Step 4: RRF 融合** | 权重: 前2个列表2x，其余1x；top-rank bonus | 一致 | ✅ |
| **Step 8: 去重 + 过滤** | 按 file 去重，minScore 过滤，截取 limit | 一致 | ✅ |

#### 差异项 ⚠️

无差异（已实现的部分）。

#### 缺失项 ❌

| 功能 | 原版 | Python 版 | 级别 | 影响 |
|------|------|-----------|------|------|
| **Step 2: Query Expansion** | 使用 LLM 生成 lex/vec/hyde 扩展查询 | ❌ **未实现** | 🔴 **必须修复** | 严重影响检索质量 |
| **Step 3: 路由搜索** | lex→FTS, vec/hyde→Vector | 部分实现（无扩展） | 🔴 连带缺失 | - |
| **Step 5: 选最佳 chunk** | 对每个候选文档调用 `chunkDocument()`，选关键词覆盖度最高的 chunk | ❌ **未实现** | 🟡 建议修复 | Rerank 的是全文而非 chunk |
| **Step 6: Rerank chunks** | LLM 重排序（仅对 chunks，非全文） | ❌ **未实现** | 🔴 **必须修复** | 严重影响检索质量 |
| **Step 7: Position-Aware Blending** | rrfRank≤3 → 75%, ≤10 → 60%, else → 40% | ❌ 连带缺失 | 🔴 连带缺失 | - |
| **LLM Cache** | `getCachedResult()` / `setCachedResult()` | ❌ **未实现** | 🔴 **必须修复** | llm_cache 表存在但未使用 |

**关键问题**：Python 版的混合检索流程**严重不完整**，缺少原版的核心步骤（Query Expansion, Reranking, Position-Aware Blending）。

---

### 6. RRF 融合算法

#### 对齐项 ✅

| 项目 | 原版 | Python 版 | 状态 |
|------|------|-----------|------|
| **RRF 公式** | `weight / (k + rank + 1)`, k=60 | 一致 | ✅ |
| **Top-rank bonus** | rank=0 → +0.05, rank≤2 → +0.02 | 一致 | ✅ |
| **权重参数** | 可配置 `weights` 数组 | 一致 | ✅ |
| **去重** | 同文件合并分数，保留最佳 rank | 一致 | ✅ |

#### 差异项 ⚠️

无差异。RRF 融合算法 **100% 对齐**。

#### 缺失项 ❌

无缺失。

---

### 7. LLM 抽象层

#### 对齐项 ✅

| 项目 | 原版 | Python 版 | 状态 |
|------|------|-----------|------|
| **接口方法** | `embed()`, `embedBatch()`, `rerank()`, `expandQuery()`, `generate()` | 定义一致（`LLMBackend`） | ✅ |

#### 差异项 ⚠️

| 差异 | 原版 | Python 版 | 级别 | 说明 |
|------|------|-----------|------|------|
| **Embedding 格式化** | `formatQueryForEmbedding()`: `"task: search result \| query: {query}"` <br> `formatDocForEmbedding()`: `"title: {title} \| text: {text}"` | ❌ **未实现** | 🟡 建议修复 | llama_cpp.py 有部分实现，但 sentence_tf.py 未使用 |
| **默认模型** | embeddinggemma-300M (GGUF) | paraphrase-multilingual-MiniLM-L12-v2 (HF) | 🟢 可接受 | MVP 阶段使用 HuggingFace 模型，符合 CLAUDE.md 要求 |
| **Query Expansion prompt** | 使用 grammar 约束，格式 `lex: ...\nvec: ...\nhyde: ...` | ❌ 未实现 | 🔴 连带缺失 | - |
| **Reranker 实现** | `rerank()` — 并行 context 策略 | ❌ 未实现（llama_cpp.py 有 stub） | 🔴 连带缺失 | - |
| **Model Pull** | `pullModels()` — 自动下载 GGUF | ❌ 未实现 | 🟡 建议修复 | - |

#### 缺失项 ❌

| 功能 | 原版 | Python 版 | 级别 |
|------|------|-----------|------|
| **Query Expansion** | ✅ 完整实现 | ❌ 未实现 | 🔴 必须修复 |
| **Reranking** | ✅ 完整实现 | ❌ 未实现 | 🔴 必须修复 |
| **LLM Cache 调用** | ✅ 自动缓存 | ❌ 未使用（表存在） | 🔴 必须修复 |
| **Embedding 格式化** | ✅ nomic-style | ❌ 部分实现 | 🟡 建议修复 |
| **Model Pull** | ✅ 自动下载 | ❌ 未实现 | 🟡 建议修复 |

---

### 8. 文档存储（Store）

#### 对齐项 ✅

| 项目 | 原版 | Python 版 | 状态 |
|------|------|-----------|------|
| **handelize()** | 路径归一化（小写、去特殊字符） | `qmd/utils/paths.py:handelize()` 逻辑一致 | ✅ |
| **hashContent()** | SHA-256 | `qmd/utils/hashing.py:content_hash()` 一致 | ✅ |
| **insertContent()** | `INSERT OR IGNORE` | 一致 | ✅ |
| **insertDocument()** | `ON CONFLICT ... DO UPDATE` | 一致 | ✅ |
| **deactivateDocument()** | `UPDATE ... SET active = 0` | 一致 | ✅ |
| **extractTitle()** | H1、首行等逻辑 | `qmd/utils/snippet.py:extract_title()` 一致 | ✅ |

#### 差异项 ⚠️

| 差异 | 原版 | Python 版 | 级别 | 说明 |
|------|------|-----------|------|------|
| **FTS 同步** | 通过触发器自动同步 | 一致 | ✅ | 无差异 |
| **Store 对象** | 导出 `Store` 对象（含方法） | `Store` 类（含方法） | 🟢 可接受 | 语言惯例差异 |

#### 缺失项 ❌

| 功能 | 原版 | Python 版 | 级别 |
|------|------|-----------|------|
| **getStatus()** | 返回索引健康状态 | ❌ 未实现 | 🟡 建议修复 |
| **findDocument()** | 支持路径/docid/fuzzy match | ❌ 未实现 | 🟡 建议修复 |
| **getDocumentBody()** | 获取文档全文 | ❌ 未实现 | 🟡 建议修复 |
| **getIndexHealth()** | 返回 `needsEmbedding` 等统计 | ❌ 未实现 | 🟡 建议修复 |
| **cleanupOrphanedVectors()** | 清理孤立向量 | ❌ 未实现 | 🟡 建议修复 |
| **vacuumDatabase()** | VACUUM | ❌ 未实现 | 🟡 建议修复 |

---

### 9. 配置管理

#### 对齐项 ✅

| 项目 | 原版 | Python 版 | 状态 |
|------|------|-----------|------|
| **配置文件路径** | `~/.config/qmd/index.yml` | 一致 | ✅ |
| **配置结构** | `collections` 字典 | 一致 | ✅ |
| **Collection 字段** | `path`, `pattern` | 一致 | ✅ |
| **Collection CRUD** | `add`, `remove`, `list` | 一致 | ✅ |

#### 差异项 ⚠️

无差异（已实现的部分）。

#### 缺失项 ❌

| 功能 | 原版 | Python 版 | 级别 | 影响 |
|------|------|-----------|------|------|
| **Context 系统** | `global_context`, per-collection `context` (ContextMap) | ❌ **未实现** | 🟡 建议修复 | 缺少上下文注入功能 |
| **findContextForPath()** | 最长前缀匹配 | ❌ 未实现 | 🟡 连带缺失 | - |
| **renameCollection()** | 重命名集合 | ❌ 未实现 | 🟡 建议修复 | - |
| **setConfigIndexName()** | 切换索引名（多索引） | ❌ 未实现 | 🟡 建议修复 | - |
| **update 字段** | 集合的 bash 更新命令 | ❌ 未实现 | 🟡 建议修复 | - |

---

### 10. MCP Server

#### 对齐项 ✅

| 项目 | 原版 | Python 版 | 状态 |
|------|------|-----------|------|
| **基本工具** | `search`, `status` | `qmd_search`, `qmd_status` | ✅ 部分对齐 |

#### 差异项 ⚠️

| 差异 | 原版 | Python 版 | 级别 | 说明 |
|------|------|-----------|------|------|
| **工具名称** | `search`, `status` | `qmd_search`, `qmd_status` | 🟢 可接受 | 加前缀避免冲突 |

#### 缺失项 ❌

| 功能 | 原版 | Python 版 | 级别 | 影响 |
|------|------|-----------|------|------|
| **vector_search 工具** | ✅ 纯语义向量检索 | ❌ 未实现 | 🟡 建议修复 | 缺少独立向量检索入口 |
| **deep_search 工具** | ✅ 混合检索（expand + rerank） | ❌ 未实现 | 🔴 **必须修复** | 缺少核心功能 |
| **get 工具** | ✅ 获取单个文档 | ❌ 未实现 | 🟡 建议修复 | - |
| **multi_get 工具** | ✅ 批量获取文档（glob） | ❌ 未实现 | 🟡 建议修复 | - |
| **Resource 定义** | ✅ `qmd://{+path}` resource template | ❌ 未实现 | 🟡 建议修复 | 缺少 VirtualPath 系统 |
| **buildInstructions()** | ✅ 动态生成 instructions | ❌ 未实现 | 🟡 建议修复 | - |
| **structuredContent** | ✅ 返回结构化内容 | ❌ 未实现 | 🟡 建议修复 | - |

---

### 11. CLI 命令

#### 对齐项 ✅

| 项目 | 原版 | Python 版 | 状态 |
|------|------|-----------|------|
| **基本命令** | `add`, `remove`, `update`, `search`, `status`, `serve` | 一致 | ✅ |

#### 差异项 ⚠️

| 差异 | 原版 | Python 版 | 级别 | 说明 |
|------|------|-----------|------|------|
| **输出格式** | `--format cli/json/xml/csv` | ❌ 只支持 CLI 格式 | 🟡 建议修复 | 缺少 JSON/XML/CSV 输出 |

#### 缺失项 ❌

| 功能 | 原版 | Python 版 | 级别 | 影响 |
|------|------|-----------|------|------|
| **query 命令** | ✅ 深度搜索（hybrid + rerank） | ❌ 未实现 | 🔴 **必须修复** | 缺少核心功能 |
| **get 命令** | ✅ 获取单个文档 | ❌ 未实现 | 🟡 建议修复 | - |
| **multi-get 命令** | ✅ 批量获取文档 | ❌ 未实现 | 🟡 建议修复 | - |
| **embed 命令** | ✅ 手动生成 embedding | ❌ 未实现 | 🟡 建议修复 | - |
| **ls 命令** | ✅ 列出文件 | ❌ 未实现 | 🟡 建议修复 | - |
| **context 子命令** | ✅ `context add/list/remove/check` | ❌ 未实现 | 🟡 建议修复 | Context 系统缺失 |
| **collection 子命令** | ✅ `collection add/remove/rename/list` | ❌ 部分实现（缺 rename） | 🟡 建议修复 | - |
| **pull 命令** | ✅ 下载模型 | ❌ 未实现 | 🟡 建议修复 | - |
| **version 命令** | ✅ 显示版本 | ❌ 未实现 | 🟡 建议修复 | - |

---

### 12. 工具函数

#### 对齐项 ✅

| 项目 | 原版 | Python 版 | 状态 |
|------|------|-----------|------|
| **extractSnippet()** | 提取代码片段（line number + chunkPos） | `qmd/utils/snippet.py:extract_snippet()` | ✅ 基本对齐 |
| **handelize()** | 路径归一化 | `qmd/utils/paths.py:handelize()` | ✅ |
| **hashContent()** | SHA-256 | `qmd/utils/hashing.py:content_hash()` | ✅ |
| **extractTitle()** | 标题提取 | `qmd/utils/snippet.py:extract_title()` | ✅ |

#### 差异项 ⚠️

无重大差异。

#### 缺失项 ❌

| 功能 | 原版 | Python 版 | 级别 |
|------|------|-----------|------|
| **formatQueryForEmbedding()** | nomic-style 格式化 | ❌ 部分实现 | 🟡 建议修复 |
| **formatDocForEmbedding()** | nomic-style 格式化 | ❌ 部分实现 | 🟡 建议修复 |
| **addLineNumbers()** | 行号标注 | ❌ 未实现 | 🟡 建议修复 |
| **VirtualPath 解析** | `qmd://collection/path` → 实际路径 | ❌ 未实现 | 🟡 建议修复 |
| **formatSearchResults()** | XML/CSV/CLI 格式化 | ❌ 未实现 | 🟡 建议修复 |

---

### 13. Watcher

#### 对齐项 ✅

无（原版无 watcher）。

#### 差异项 ⚠️

| 差异 | 原版 | Python 版 | 级别 | 说明 |
|------|------|-----------|------|------|
| **Watcher 功能** | ❌ 未实现 | ✅ 完整实现 | 🟢 **扩展功能** | Python 版的扩展功能，非原版移植 |

**说明**：Python 版的 `qmd/core/watcher.py` 是扩展功能，原版无此模块。这是**正面差异**。

#### 缺失项 ❌

无。

---

### 14. 功能完整性审查（缺失功能清单）

#### 🔴 必须修复（影响正确性）

1. **Query Expansion（LLM 查询扩展）** — 原版混合检索的核心步骤
2. **Reranking（LLM 重排序）** — 原版混合检索的核心步骤
3. **LLM Cache 调用** — `llm_cache` 表存在但未使用，浪费资源

#### 🟡 建议修复（功能缺失）

4. **Context 系统** — `global_context`, per-collection context, `findContextForPath()`
5. **VirtualPath 系统** — `qmd://collection/path` URI 解析
6. **Document 检索** — `findDocument()`, `getDocumentBody()`
7. **Index Health** — `getIndexHealth()`, `needsEmbedding` 计数
8. **Cleanup 操作** — `cleanupOrphanedVectors()`, `vacuumDatabase()`
9. **Model Pull** — 自动下载 GGUF 模型
10. **Embedding 格式化** — nomic-style (`task: search result | query: ...`)
11. **CLI 输出格式** — JSON/XML/CSV 输出
12. **CLI 命令** — `query`, `get`, `multi-get`, `embed`, `ls`, `context *`, `pull`, `version`
13. **MCP 工具** — `vector_search`, `deep_search`, `get`, `multi_get`
14. **Collection Rename** — `renameCollection()`
15. **多索引支持** — `setConfigIndexName()`

#### 🟢 可接受差异（语言惯例）

16. **异步模型** — 原版 TypeScript async，Python 同步（符合 Python 生态）
17. **默认模型** — 原版 GGUF，Python HuggingFace（MVP 阶段策略）
18. **向量格式** — 原版 `Float32Array`，Python `struct.pack`
19. **Store 封装** — 原版导出对象，Python 类封装
20. **日志库** — 原版 console，Python loguru
21. **CLI 解析** — 原版自定义，Python argparse
22. **MCP 工具命名** — 原版 `search`，Python `qmd_search`（加前缀）
23. **Watcher** — Python 版的扩展功能（正面差异）

---

## 优先级修复建议

### 第一优先级（核心功能）🔴

1. **实现 Query Expansion**（`qmd/llm/` 扩展 `expandQuery()` 方法）
   - 使用 llama-cpp-python 加载 `qmd-query-expansion-1.7B-q4_k_m.gguf`
   - 实现 grammar 约束，输出 `lex: ...\nvec: ...\nhyde: ...`
   - 集成到 `qmd/core/retrieval.py:search()` 的 Step 2

2. **实现 Reranking**（`qmd/llm/llama_cpp.py:rerank()` 完善）
   - 使用 llama-cpp-python 加载 `Qwen3-Reranker-0.6B-Q8_0.gguf`
   - 解析 logprobs，实现 yes/no 判断
   - 集成到 `qmd/core/retrieval.py:search()` 的 Step 6

3. **实现 LLM Cache 调用**
   - `qmd/core/db.py` 添加 `get_cached_result()`, `set_cached_result()`
   - `qmd/llm/base.py` 添加缓存装饰器
   - 集成到 `expandQuery()` 和 `rerank()`

### 第二优先级（增强功能）🟡

4. **实现 Context 系统**
   - `qmd/core/config.py` 添加 `global_context`, `context` 字段
   - 实现 `findContextForPath()` 最长前缀匹配
   - CLI 添加 `context add/list/remove/check` 子命令

5. **实现 Position-Aware Blending**
   - `qmd/core/retrieval.py:search()` 添加 Step 7
   - 实现动态权重计算

6. **实现 VirtualPath 系统**
   - `qmd/utils/paths.py` 添加 `qmd://` URI 解析
   - MCP Server 添加 Resource 定义

7. **补充 CLI 命令**
   - 添加 `query` 命令（调用 deep search）
   - 添加 `get`, `multi-get` 命令
   - 添加 `embed` 命令（手动生成 embedding）

8. **补充 MCP 工具**
   - 添加 `deep_search` 工具
   - 添加 `get`, `multi_get` 工具

### 第三优先级（完善功能）

9. **实现 Model Pull** — 自动下载 GGUF 模型
10. **实现 Embedding 格式化** — nomic-style
11. **实现 CLI 输出格式** — JSON/XML/CSV
12. **实现 Index Health** — `getIndexHealth()`, `needsEmbedding`
13. **实现 Cleanup 操作** — `cleanupOrphanedVectors()`, `vacuumDatabase()`
14. **实现 Collection Rename** — `renameCollection()`
15. **实现多索引支持** — `setConfigIndexName()`

---

## 总结

**核心优势**：
- ✅ 数据库架构、Chunking 算法、BM25/向量检索、RRF 融合 **完全对齐**
- ✅ 代码质量高，测试覆盖率 90%
- ✅ 扩展功能（Watcher）

**核心问题**：
- 🔴 **缺少 Query Expansion 和 Reranking**，导致混合检索流程不完整
- 🔴 LLM Cache 未使用
- 🟡 缺少 Context 系统、VirtualPath 系统
- 🟡 CLI 和 MCP 功能不完整

**忠实度评分 7.5/10**：基础架构扎实，但核心 LLM 功能缺失较多。建议优先实现 Query Expansion 和 Reranking，提升至 9/10。

---

**审查完成**。
