# qmd-py 设计文档

> **版本**: v3（2026-04-15）
> **v2→v3 变更**：pydantic/Protocol 定义集中在本项目 `qmd/models.py`（单一真相），从 `qmd/__init__.py` 公开导出；design.md 不再内嵌代码，仅引用源文件。

**日期**: 2026-04-15（v3 更新）
**项目**: qmd-py (Query Markup Documents, Python port)
**本项目在系统中的定位**: 向量数据库（类比 Chroma / Milvus）

> 本文档是 qmd-py 在 GovDoc 三项目体系中的设计。顶层计划见 `/home/iomgaa/Projects/GOVDOC_PROGRAM_PLAN.md`。

---

## 1. 定位

qmd-py 在 GovDoc-Auditor / Scrivai / qmd-py 三层架构中是**最底层**：**通用 Markdown 混合检索引擎**，只提供检索原语。

| 维度 | 要点 |
|---|---|
| **知道什么** | Markdown 文本、chunk、embedding、BM25 索引、collection |
| **不知道什么** | 法规 / 审核点 / 招标 / 任何业务领域概念；LLM 编排；Chain；prompt |
| **被谁使用** | Scrivai（直接）；业务层**不得**直接调用 qmd |
| **禁止事项** | 源码中出现 `audit`、`generate`、`scrivai`、`govdoc`、`招标`、`审核` 等词（namespace 独立性） |

**类比**：qmd = 向量数据库；Scrivai = 使用它的 langchain。

## 2. 上下游关系

```
 Scrivai.knowledge  ─→  qmd.QmdClient
                         │
                         ├─→  qmd.Collection
                         │      add_document / hybrid_search / ...
                         │
                         └─→  qmd.sqlite  (sqlite-vec + FTS5)
```

**qmd 的输入**：来自 Scrivai 的 Markdown 字符串（已由 Scrivai.io 把 docx/pdf 转换好）。qmd **不做**格式转换。

**qmd 的输出**：`SearchResult` 列表，含 `ChunkRef`（用于业务层回溯证据到原文位置）。

## 3. 对外契约（Public API — canonical from PLAN §4.1）

qmd 暴露**两个对等的对外接口**：
- **Python API**：被 Scrivai 直接 `import qmd` 使用（用于 Library 实现等内部场景）
- **CLI 命令**：JSON-stdout 子命令，被 Claude Agent SDK 通过 Bash 工具调用

两者必须语义对齐：CLI 命令的 JSON 输出 = Python API 对应方法返回 pydantic `.model_dump(mode="json")`。

**v3**：所有 pydantic / Protocol 定义位于 qmd 项目自身 `qmd/models.py`，从 `qmd/__init__.py` 导出。下游（Scrivai / GovDoc）直接 `from qmd import ...`。

```python
from qmd import (
    ChunkRef, SearchResult, CollectionInfo,   # pydantic models
    Collection, QmdClient,                    # Protocols
    connect,                                  # 工厂函数 connect(db_path) -> QmdClient
)
```

完整 pydantic 定义见源文件 `qmd-py/qmd/models.py`。本文档不再内嵌代码。

### 3.1 不变量（契约测试会检查）

1. `hybrid_search` 返回按 `score` **严格降序**
2. `ChunkRef.char_start / char_end` 定位于**传入的原始 markdown 字符串**（UTF-8 字符索引），业务层据此高亮
3. `metadata` **透传不解释**：qmd 存它、按它过滤（相等匹配），但不依赖其语义
4. `filters` MVP 只支持精确相等（`{"type": "law"}` → `metadata.type == "law"`）
5. Collection 隔离：不同 collection 的 search 结果**绝不**混入
6. `add_document(id, ...)` 同 id 重复调用**等价于 `update_document`**（幂等 upsert 语义；不抛错）
7. 所有 Collection 方法是**线程安全**的（MVP 只需进程内安全，用 `threading.Lock`）

### 3.2 CLI 命令规范（Agent 通过 Bash 调用）

入口：`qmd <subcommand> [args]`，等价 `python -m qmd <subcommand>`

**通用约定**：
- JSON 到 stdout（`json.dumps(..., ensure_ascii=False)`）
- 错误：`{"error": "..."}` 到 stderr，exit 1
- 路径：`--db-path` > 环境变量 `QMD_DB_PATH` > 默认 `~/.qmd/db.sqlite`

**必备子命令**（与 Python API 严格对应）：

```bash
qmd search --collection <name> --query <q> [--top-k 5] [--rerank] [--filters '{}']
# Python 等价: collection.hybrid_search(query, top_k=..., rerank=..., filters=...)
# 输出: JSON list[SearchResult.model_dump()]

qmd collection info --collection <name>
qmd collection list
# 输出: JSON CollectionInfo / list[CollectionInfo]

qmd document get --collection <name> --document-id <id>
qmd document add --collection <name> --document-id <id> --markdown-file <path> [--metadata-json <json>]
qmd document delete --collection <name> --document-id <id>
qmd document list --collection <name>
```

CLI 的 JSON 输出 schema 在契约测试中和 Python API 比对（防止漂移）。

### 3.4 禁止的公开 API

以下 **不在** public API / CLI 出口：
- 内部的 `Store`、`Database`、`Retriever`、`Chunker` 类（实现细节）
- SQL 直接查询入口
- `embed()` / `rerank()` 原始调用
- 对 Scrivai / GovDoc-Auditor 相关的任何符号或概念
- 旧的 `create_store / search` 函数式 API

## 4. 内部架构

```
qmd/
├── __init__.py            ← public API：6 个名字 + __version__
├── models.py              ← pydantic 模型 + Protocol（单一真相）
├── core/
│   ├── client.py          ← SqliteQmdClient 实现
│   ├── collection.py      ← SqliteCollection 实现（hybrid_search 完整流程）
│   ├── db.py              ← SQLite + sqlite-vec + FTS5 schema
│   ├── chunking.py        ← 语义边界分块
│   ├── retrieval.py       ← RRF 融合 + position_aware_blend
│   ├── config.py          ← 配置管理 (YAML + pydantic v2)
│   ├── embedding.py       ← Qwen3-Embedding-0.6B（sentence-transformers）
│   ├── rerank.py          ← Qwen3-Reranker-0.6B（transformers CausalLM）
│   └── expansion.py       ← Qwen3-0.6B Query Expansion（可选）
├── testing/
│   ├── fakes.py           ← FakeQmdClient / FakeCollection（内存版，用于 Scrivai 单测）
│   └── contract.py        ← 契约测试套件（pytest plugin，供下游复用）
└── cli/
    └── __main__.py        ← argparse 路由：search / collection / document
```

### 4.1 关键实现决策

- **Chunking**：语义边界分块（见 `qmd/core/chunking.py`），chunk 大小默认 512 tokens、overlap 64
- **Embedding**：Qwen/Qwen3-Embedding-0.6B（sentence-transformers，1024-dim，默认）；可通过 `qmd.yaml` 切换 model_name
- **BM25**：SQLite FTS5 内置（trigram tokenizer，支持中文）
- **融合**：Reciprocal Rank Fusion（RRF），k=60
- **Rerank**：Qwen/Qwen3-Reranker-0.6B（transformers HF checkpoint，可选开关，`hybrid_search(rerank=True)`；配置见 `qmd.yaml` `rerank.enabled`）
- **Query Expansion**：Qwen/Qwen3-0.6B（transformers CausalLM，可选开关，`qmd.yaml` `expansion.enabled`，默认关闭）

## 4.2 CLI 实现要点

- 所有命令进 `qmd/cli/__main__.py`（argparse 路由）
- 每个子命令一个函数 + 单测验证 JSON 输出 schema
- 入口在 `pyproject.toml` 注册：
  ```toml
  [project.scripts]
  qmd = "qmd.cli.__main__:main"
  ```
- 进程启动开销控制：CLI 命令 P50 < 200ms（不含真实搜索）

## 5. 与 Scrivai / GovDoc-Auditor 的协调点

### 5.1 Scrivai 怎么用 qmd

**双通道**：
- **Scrivai Python 内部**（构造 Library 时）→ `import qmd; qmd.connect(...)`
- **Agent SDK 通过 Bash**（agent 在审核中需要再查时）→ `qmd search ...`

Scrivai 的 `scrivai.knowledge.RuleLibrary / CaseLibrary / TemplateLibrary` 在 qmd 里对应 **三个固定命名的 collection**：

| Scrivai Library | qmd collection 名 | 内容 |
|---|---|---|
| `RuleLibrary` | `"rules"` | 法规 / 指引的 markdown 分块 |
| `CaseLibrary` | `"cases"` | 历史工作底稿定稿的 markdown 分块 |
| `TemplateLibrary` | `"templates"` | 文书模板（供相似度匹配参考） |

Scrivai 的 Chain（Extract/Audit/Generate）**也会**临时创建 collection（例如 `"tender_<project_id>"` 用于一次审核），qmd 不需要知道这些命名语义——只负责提供 collection 原语。

### 5.2 qmd 不参与的事

- **Prompt 文本管理**：在 Scrivai
- **LLM 调用**（生成/审核）：在 Scrivai（qmd 只用 LLM 做 embedding 和 rerank）
- **业务状态**（project / audit_run）：在 GovDoc 的 app.sqlite
- **格式转换**（docx/pdf → md）：在 Scrivai.io

### 5.3 变更请求的边界

如果 Scrivai 需要 qmd 做某事，但 qmd 当前不支持：

- ✅ **正确做法**：在 `/home/iomgaa/Projects/INTEGRATION_ISSUES.md` 提 issue，由协调员决定是否加入契约；若加入，走 PLAN §8 流程
- ❌ **错误做法**：Scrivai 自己在 qmd.sqlite 上直接 SQL 查询；或 qmd 给 Scrivai 加一个"仅 Scrivai 用"的私有方法

### 5.4 可能的变更请求（从 Scrivai 视角预判）

- **批量 add_document**：Scrivai 可能一次入库几百份文书 → 需要 `add_documents(batch)`。M1 加入契约
- **按文档删除**：Scrivai 删除整份法规时 → 已有 `delete_document`
- **元数据更新**：Scrivai 想给 chunk 打标签而不重建 → M2 再评估

## 6. 硬切换：Deprecation Target

以下当前 public 符号 **M0 结束前全部删除**，不留别名：

- 旧 `qmd.__init__.py` 里的：`create_store`、`create_llm_backend`、`load_config`、`init_schema`、`open_database`、`get_db_path`、`ensure_db_dir`、`BackendType`、`Database`、`NamedCollection`、`Store`、`search` 函数、`LLMBackend`
- 旧 `qmd.core.retrieval.search` 函数式 API
- 旧 `qmd.core.store.Store` 类（内部实现保留但不导出）

**M3 验收**：`git grep -E "qmd\.(create_store|Store|NamedCollection|LLMBackend)"` 在所有三项目中零结果。

## 7. 非目标（YAGNI）

- 多进程安全 / 分布式部署（MVP 单进程）
- 增量 embedding（全量 re-embed，简化实现）
- 多模态（只 Markdown 文本）
- 跨 collection 联合检索（Scrivai 可以串行多次 search + 合并）
- 权限控制（MVP 单用户）

## 8. 性能目标（M2 基线）

- 10万 chunk 规模下 `hybrid_search(top_k=5)` P95 < 500ms
- `add_document` 一份 100 页 markdown < 30s（含 embedding）
- 索引文件大小 < 原文的 3x

## 9. 配置

```yaml
# qmd.yaml（放在 db_path 同目录；缺失即走默认值）
chunking:
  size: 512
  overlap: 64
  strategy: "semantic"

embedding:
  backend: "sentence_tf"
  model_name: "Qwen/Qwen3-Embedding-0.6B"
  dim: 1024
  batch_size: "auto"     # auto → GPU=64, CPU=16

rerank:
  enabled: false
  backend: "sentence_tf"
  model_name: "Qwen/Qwen3-Reranker-0.6B"
  top_k_candidates: 40

retrieval:
  rrf_k: 60
  bm25_top_k: 20
  vector_top_k: 20
  blending_mode: "pure_rerank"   # 或 "position_aware"
  blending_weights:
    top: [0.75, 0.25]            # rank 1-3
    mid: [0.60, 0.40]            # rank 4-10
    tail: [0.40, 0.60]           # rank 11+

expansion:
  enabled: false
  model_name: "Qwen/Qwen3-0.6B"
  strong_signal_threshold: 0.85
  strong_signal_gap: 0.15
```

---

详细任务拆解见 `TD.md`。
