# CLAUDE.md

> [!URGENT]
> **研究性项目 (Research Project)**
> 1. 本项目为 MVP（最小可行性产品），严禁过度工程化。
> 2. 你的所有思考过程和回复必须使用 **简体中文**。

## 1. 项目概述 (Project Overview)

- **项目名**: qmd-py — Python 移植版本的 QMD (Query Markup Documents)
- **原版项目**: [tobi/qmd](https://github.com/tobi/qmd) (TypeScript)
- **移植目标**: 
  - **功能对齐**: 实现与 qmd 相同的混合检索能力
  - **API 兼容**: 保持相似的 CLI 和 MCP 接口
  - **模型一致**: 使用相同的 GGUF 模型（embeddinggemma-300M, Qwen3-Reranker, qmd-query-expansion）
  - **存储一致**: 使用相同的 SQLite + sqlite-vec 架构
- **核心能力**: Markdown 文档的智能检索引擎
  - 智能语义边界分块 (Smart Chunking)
  - 混合检索 (BM25 + Vector + RRF 融合)
  - LLM Query Expansion
  - Position-Aware Reranking
- **独立性**: 作为独立的 Python 包发布，可被其他项目集成

## 2. 技术栈 (Tech Stack)

### 2.1 核心技术

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| **语言** | Python 3.11+ | 需要 3.10+ 的类型注解特性 |
| **向量存储** | SQLite + sqlite-vec | 与 qmd 一致，单文件数据库 |
| **全文检索** | SQLite FTS5 | BM25 算法 |
| **配置管理** | PyYAML + pydantic | YAML 配置 + 类型验证 |
| **CLI** | argparse | 保持轻量，不用 Typer/Click |
| **MCP 服务器** | mcp (PyPI) | Model Context Protocol |
| **测试框架** | pytest | 目标覆盖率 80% |
| **日志** | loguru | 禁用 print() |

### 2.2 LLM 后端 (分阶段)

#### MVP 阶段（快速验证）
| 任务 | 库 | 模型 | 说明 |
|------|-----|------|------|
| **Embedding** | sentence-transformers | all-MiniLM-L6-v2 | HuggingFace 生态，快速验证 |
| **Reranker** | FlagEmbedding | bge-reranker-v2-m3 | 成熟的重排序模型 |
| **Query Expansion** | llama-cpp-python | qmd-query-expansion-1.7B GGUF | 必须用 GGUF（与 qmd 一致） |

#### 生产阶段（与 qmd 对齐）
| 任务 | 库 | 模型 | 说明 |
|------|-----|------|------|
| **Embedding** | llama-cpp-python | embeddinggemma-300M-Q8_0.gguf | 与 qmd 完全一致 |
| **Reranker** | llama-cpp-python (手动实现) | Qwen3-Reranker-0.6B-Q8_0.gguf | 需要自己解析 logprobs |
| **Query Expansion** | llama-cpp-python | qmd-query-expansion-1.7B-q4_k_m.gguf | 与 MVP 一致 |

### 2.3 依赖映射表

| TypeScript (qmd) | Python (qmd-py) | 说明 |
|------------------|-----------------|------|
| better-sqlite3 | sqlite3 (内置) | SQLite 驱动 |
| sqlite-vec | sqlite-vec (PyPI) | 向量扩展 |
| node-llama-cpp | llama-cpp-python | GGUF 加载器 |
| fast-glob | glob / pathlib | 文件匹配 |
| yaml | PyYAML | YAML 解析 |
| zod | pydantic | Schema 验证 |
| @modelcontextprotocol/sdk | mcp | MCP 协议 |

## 3. 项目结构 (Project Structure)

```
qmd-py/
├── CLAUDE.md                # 项目规范（本文件）
├── pyproject.toml           # 项目配置 (PEP 621)
├── README.md                # 项目说明
├── .gitignore               # migration_analysis.md, reference/ 已加入
├── migration_analysis.md    # 迁移分析报告（不提交）
├── implementation_plan.md   # 实施计划（不提交）
│
├── reference/               # 参考代码（不提交）
│   ├── qmd/                 # QMD 原版 TypeScript 源码
│   └── openclaw-memory/     # OpenClaw memory 模块
│
├── qmd/                     # 核心包（注意：包名是 qmd，不是 qmd_py）
│   ├── __init__.py
│   ├── __main__.py          # CLI 入口 (python -m qmd)
│   │
│   ├── core/                # 核心模块
│   │   ├── __init__.py
│   │   ├── db.py            # SQLite 抽象层 (~50行)
│   │   ├── store.py         # 数据层：索引、存储、Schema
│   │   ├── chunking.py      # 智能分块算法（断点扫描、平方衰减）
│   │   ├── retrieval.py     # 检索算法 (FTS + Vector + RRF)
│   │   └── config.py        # 配置管理 (YAML + pydantic)
│   │
│   ├── llm/                 # LLM 抽象层
│   │   ├── __init__.py
│   │   ├── base.py          # LLM 接口定义 (Protocol/ABC)
│   │   ├── llama_cpp.py     # llama-cpp-python 实现
│   │   ├── huggingface.py   # sentence-transformers 实现 (MVP 阶段)
│   │   ├── models.py        # 模型管理 (下载、缓存、idle timeout)
│   │   └── formatters.py    # Prompt 格式化 (nomic-style 等)
│   │
│   ├── cli/                 # CLI 命令
│   │   ├── __init__.py
│   │   ├── main.py          # 命令路由 (argparse)
│   │   ├── search.py        # search/vsearch/query 命令
│   │   ├── embed.py         # embed 命令
│   │   ├── collection.py    # collection add/list/remove
│   │   ├── context.py       # context 管理
│   │   └── formatter.py     # 输出格式化 (JSON/CSV/CLI)
│   │
│   ├── mcp/                 # MCP 服务器
│   │   ├── __init__.py
│   │   ├── server.py        # MCP 服务器实现
│   │   └── tools.py         # MCP 工具定义
│   │
│   └── utils/               # 工具函数
│       ├── __init__.py
│       ├── paths.py         # 路径处理
│       ├── hashing.py       # 内容哈希 (SHA256)
│       └── snippet.py       # Snippet 提取
│
├── tests/                   # 测试
│   ├── __init__.py
│   ├── test_chunking.py     # 智能分块测试（关键！）
│   ├── test_retrieval.py    # 检索算法测试
│   ├── test_llm.py          # LLM 调用测试
│   ├── test_store.py        # 数据层测试
│   └── fixtures/            # 测试数据
│       └── sample_docs/
│
├── scripts/                 # 工具脚本
│   ├── download_models.py   # 预下载 GGUF 模型
│   └── migrate_from_qmd.py  # 从 qmd 迁移索引数据
│
└── docs/                    # 文档
    ├── architecture.md      # 架构说明
    ├── chunking_algorithm.md # 智能分块算法详解
    └── api.md               # API 文档
```

## 4. 核心代码规范 (Code Standards)

### 4.1 开发原则

> [!CRITICAL]
> **MVP 优先原则**
> - 先跑通再迭代，严禁过度工程化
> - 代码简洁：能短就短，不保留废弃代码
> - 显式优于隐式：关键参数必须显式传递
> - 不考虑向后兼容，直接改原文件

### 4.2 代码风格

- **类型注解**: 强制所有函数签名包含完整类型注解（Python 3.10+ 语法）
  ```python
  def chunk_document(
      text: str,
      max_tokens: int = 900,
      overlap_tokens: int = 135
  ) -> list[dict[str, Any]]:  # 注意：不用 List/Dict，用 list/dict
      """按语义边界切分文档"""
      ...
  ```

- **文档**: 所有模块、类、方法必须包含 **中文 Docstring**
- **注释**: 关键逻辑用中文注释
- **命名**: 
  - 类名 `PascalCase`
  - 函数/变量 `snake_case`
  - 私有成员前缀 `_`
  - 常量 `UPPER_SNAKE_CASE`

- **导入顺序**: 
  ```python
  # 1. 标准库
  import re
  from pathlib import Path
  
  # 2. 第三方库
  import numpy as np
  from llama_cpp import Llama
  
  # 3. 项目内部
  from qmd.core.db import open_database
  ```

### 4.3 日志规范

- **禁用 print()**，全部使用 loguru
  ```python
  from loguru import logger
  
  logger.info("开始索引: {path}", path=doc_path)
  logger.debug("切分结果: {count} 个块", count=len(chunks))
  logger.error("模型加载失败: {error}", error=e)
  ```

### 4.4 测试规范

- **测试框架**: pytest
- **目标覆盖率**: 80%
- **测试位置**: `tests/` 目录
- **运行命令**: 
  ```bash
  conda run -n qmd-py pytest tests/ --cov=qmd --cov-report=term-missing
  ```

- **必须先写测试或同步编写**

### 4.5 Git 规范

使用 Conventional Commits，commit message 用中文描述：

| 前缀 | 用途 | 示例 |
|------|------|------|
| `feat:` | 新功能 | `feat: 实现智能分块算法` |
| `fix:` | 修复 | `fix: 修复代码块保护逻辑` |
| `refactor:` | 重构 | `refactor: 拆分 store.py 为多个模块` |
| `chore:` | 杂项 | `chore: 更新依赖版本` |
| `docs:` | 文档 | `docs: 重写 CLAUDE.md 基于迁移分析` |
| `test:` | 测试 | `test: 添加 RRF 融合测试` |

**不提交**: `migration_analysis.md`、`implementation_plan.md`、`reference/` 已加入 `.gitignore`

## 5. 关键设计决策 (Design Decisions)

### 5.1 存储架构

**统一使用 SQLite**（不用 ChromaDB/FAISS）

**原因**:
- ✅ 单文件数据库，无需额外服务
- ✅ SQL 查询能力 (可以 JOIN 元数据)
- ✅ 事务支持
- ✅ sqlite-vec 扩展提供向量检索

### 5.2 模型管理

**懒加载 + Idle Timeout + GPU 自动检测**

- **懒加载**: 首次使用时才加载模型到显存
- **Idle Timeout**: 5 分钟无调用自动释放显存
- **GPU 检测优先级**: CUDA > MPS > CPU
- **模型缓存路径**: `~/.cache/qmd/models/`

### 5.3 智能 Chunking

**参数**:
- **目标大小**: 900 tokens/chunk
- **重叠**: 15% (135 tokens)
- **搜索窗口**: 200 tokens

**断点优先级** (分数):
```python
BREAK_PATTERNS = [
    (r'\n#{1}(?!#)', 100, 'h1'),     # H1 最高分
    (r'\n#{2}(?!#)', 90, 'h2'),
    (r'\n#{3}(?!#)', 80, 'h3'),
    (r'\n```', 80, 'codeblock'),      # 代码块边界
    (r'\n(?:---|\*\*\*)\s*\n', 60, 'hr'),  # 分隔线
    (r'\n\n+', 20, 'blank'),          # 空行
    (r'\n', 1, 'newline'),            # 换行（最低分）
]
```

**平方距离衰减** (核心算法):
```python
distance = target_pos - break_point.pos
normalized_dist = distance / window_chars
multiplier = 1.0 - (normalized_dist ** 2) * decay_factor
final_score = break_point.score * multiplier
```

**代码块保护**: 绝不在 ``` 内切分

**中文 token 估算**: `tokens * 2` (中文字符数估算)

### 5.4 混合检索流程

**完整的 Hybrid Query 流程**:

```
用户查询: "authentication flow"
  ↓
Step 1: BM25 Probe (强信号检测)
  └─ 如果 top1_score > 0.85 且 (top1 - top2) > 0.15 → 跳过扩展
  ↓
Step 2: LLM Query Expansion (如果需要)
  └─ Qwen3-1.7B → 生成 lex/vec/hyde 变体
  ↓
Step 3: 并行检索
  - 原查询 (×2 权重) → FTS + Vector
  - 扩展查询 → 根据类型路由 (lex→FTS, vec/hyde→Vector)
  ↓
Step 4: Reciprocal Rank Fusion (RRF)
  - k=60, top-rank bonus (+0.05/#1, +0.02/#2-3)
  - 保留前 40 个候选
  ↓
Step 5: 智能分块 + 关键词选择最佳块
  - chunk_document() → 900 tokens
  - 计算每块的关键词覆盖度 → 选 best chunk
  ↓
Step 6: LLM Reranking (仅对块，非全文)
  └─ Qwen3-Reranker → yes/no + logprob
  ↓
Step 7: Position-Aware Blending
  - Rank 1-3:  75% RRF + 25% Reranker
  - Rank 4-10: 60% RRF + 40% Reranker
  - Rank 11+:  40% RRF + 60% Reranker
  ↓
返回结果 (带 snippet、docid、context)
```

**RRF 融合参数**: k=60

**Strong Signal 检测** (省 ~8s LLM 调用):
- BM25 top1 > 0.85 且 gap > 0.15 时跳过扩展

**Position-Aware Blending** (防止 reranker 误杀):
- Rank 1-3:  75% RRF + 25% Reranker
- Rank 4-10: 60% RRF + 40% Reranker
- Rank 11+:  40% RRF + 60% Reranker

### 5.5 增量更新

**去重策略**: 基于内容 SHA256 哈希

**更新逻辑**:
```python
def update_document(path: str, new_content: str):
    new_hash = compute_doc_hash(new_content)
    old_doc = db.get_document_by_path(path)
    
    if old_doc and old_doc['hash'] == new_hash:
        logger.info("文档未变化，跳过: {path}", path=path)
        return
    
    if old_doc:
        # 标记旧版本为 inactive
        db.mark_inactive(old_doc['id'])
    
    # 插入新版本
    db.insert_document(path, new_content, new_hash)
```

## 6. 参考代码 (Reference Code)

| 路径 | 说明 | 关键文件 |
|------|------|----------|
| `reference/qmd/` | QMD 原版 TypeScript 源码 | 完整的 qmd v1.0.6 源码 |
| `reference/qmd/src/llm.ts` | LLM 抽象层 | embedding、rerank、query expansion |
| `reference/qmd/src/store.ts` | 核心数据层 | chunking、检索、RRF |
| `reference/qmd/src/db.ts` | SQLite 抽象 | 跨运行时支持 |
| `reference/qmd/src/collections.ts` | 配置管理 | YAML 配置加载 |
| `reference/qmd/src/mcp.ts` | MCP 服务器 | MCP 工具定义 |
| `reference/openclaw-memory/` | OpenClaw memory 模块 | qmd 集成示例 |

**学习重点**:
- `store.ts` 的 `chunkDocumentByTokens()` — 智能分块核心算法
- `store.ts` 的 `hybridQuery()` — 完整的混合检索流程
- `llm.ts` 的模型管理逻辑 — idle timeout 实现

## 7. 与 qmd 的差异 (Differences from QMD)

### 7.1 不可避免的差异

| 功能 | qmd (TypeScript) | qmd-py (Python) | 影响 |
|------|------------------|-----------------|------|
| **GGUF 加载器** | node-llama-cpp | llama-cpp-python | ⚠️ Python 版功能较弱 |
| **并行 Embedding** | 多 context 并行 | 单线程循环 (llama-cpp) / 批处理 (HF) | ⚠️ 性能下降 |
| **Reranker API** | 内置 `rankAll()` | 需手动实现 (logprobs 解析) | ⚠️ 需自己编码 |
| **Context 管理** | 独立 context 对象 | 较简单 | ⚠️ 抽象层较薄 |
| **Idle Timeout** | 原生支持 | 需用 `threading.Timer` | ⚠️ 需自己实现 |

### 7.2 分阶段策略

#### MVP 阶段（2 周内可用）
- **Embedding**: `sentence-transformers` (all-MiniLM-L6-v2)
- **Reranker**: `FlagEmbedding` (bge-reranker-v2-m3)
- **Query Expansion**: `llama-cpp-python` (qmd-query-expansion GGUF)

**优势**: 快速验证核心逻辑，HuggingFace 生态成熟

#### 生产阶段（与 qmd 对齐）
- **Embedding**: `llama-cpp-python` + embeddinggemma GGUF
- **Reranker**: 手动实现 (logprobs 解析)
- **Query Expansion**: 同 MVP

**优势**: 与 qmd 结果完全一致，可直接对比质量

### 7.3 包名差异

- **qmd**: `qmd` (npm 包名)
- **qmd-py**: `qmd` (PyPI 包名，注意不是 `qmd_py`)

**原因**: Python 包通常用 `-` 而非 `_`

## 8. Git 规范补充

- **Conventional Commits**
- **不提交**: `migration_analysis.md`、`implementation_plan.md`、`reference/` 已加入 `.gitignore`

## 9. Conda 环境管理

> [!CRITICAL]
> **所有 Python 相关命令必须在 qmd-py 环境中执行**

```bash
# 激活项目环境
source ~/miniconda3/etc/profile.d/conda.sh && conda activate qmd-py

# 或使用 conda run（推荐）
conda run -n qmd-py pip install -e ".[dev]"
conda run -n qmd-py pytest tests/ -v --cov=qmd --cov-report=term-missing
conda run -n qmd-py python -m qmd

# 代码格式化与检查
conda run -n qmd-py ruff format qmd/ tests/
conda run -n qmd-py ruff check qmd/ tests/ --fix
```

## 10. 开发工作流 (Workflow)

### 10.1 标准作业程序 (SOP)

#### 阶段 1: 规划
1. 阅读 `migration_analysis.md`，确认模块边界和接口
2. 阅读 `reference/qmd/` 中的相关源码
3. 确定数据结构和类型定义

#### 阶段 2: 执行
1. **先写测试**（或同步编写）
2. **实现模块**
3. **运行测试验证**

#### 阶段 3: 收尾
1. 每完成一个模块提交一个 commit
2. 更新文档（如需要）

### 10.2 输出规范

- **所有输出语言**: **中文**
- **信息密度原则**: 优先使用表格、流程图、项目符号列表，避免大段代码和冗长解释
- **核心原则**: 用最少的字符传递最多的信息

## 11. 上下文获取 (Context & Navigation)

| 需求 | 路径 | 说明 |
|------|------|------|
| **项目规范** | `CLAUDE.md` | 本文件 |
| **项目说明** | `README.md` | 项目概述 |
| **迁移分析** | `migration_analysis.md` | 完整的架构分析（临时文件） |
| **实施计划** | `implementation_plan.md` | 当前迭代计划（临时文件） |
| **项目配置** | `pyproject.toml` | 依赖、构建、工具配置 |
| **参考代码** | `reference/qmd/` | QMD 原版 TypeScript 源码 |
