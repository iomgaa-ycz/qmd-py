# QMD-Py — Query Markup Documents

本地运行的混合文档搜索引擎。索引你的 Markdown 笔记、会议记录、文档和知识库，用关键词或自然语言搜索。Python 移植版，忠实复现 [qmd](https://github.com/tobi/qmd) 的核心算法。

QMD-Py 结合 BM25 全文检索、向量语义检索和 LLM 重排序，全部本地运行。支持 llama-cpp-python（GGUF 模型）、sentence-transformers、FlagEmbedding 三种后端。

## 快速开始

```bash
# 安装
pip install qmd

# 带 LLM 后端
pip install "qmd[mvp]"

# 带 MCP 支持
pip install "qmd[mcp]"

# 创建 collection
qmd add notes ~/notes
qmd add docs ~/Documents/docs --pattern "**/*.md"

# 添加上下文（关键特性——帮助 LLM 理解文档归属）
qmd context add notes "" "个人笔记和想法"
qmd context add docs "api" "API 文档"

# 生成 embedding
qmd embed

# 搜索
qmd search "项目进度"              # BM25 关键词检索
qmd query "如何部署服务"            # 混合检索 + 重排序（最佳质量）

# 获取文档
qmd get qmd://notes/meeting.md
qmd get "#abc123"                  # 用 docid

# 列出文件
qmd ls
qmd ls notes
```

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    QMD-Py Hybrid Search Pipeline                │
└─────────────────────────────────────────────────────────────────┘

                           ┌──────────────┐
                           │  User Query  │
                           └──────┬───────┘
                                  │
                   ┌──────────────┴──────────────┐
                   ▼                             ▼
          ┌────────────────┐            ┌────────────────┐
          │ Query Expansion│            │  Original Query│
          │  (fine-tuned)  │            │   (×2 weight)  │
          └───────┬────────┘            └───────┬────────┘
                  │                             │
                  │  lex / vec / hyde 变体       │
                  └──────────────┬──────────────┘
                                 │
           ┌─────────────────────┼─────────────────────┐
           ▼                     ▼                     ▼
     ┌───────────┐         ┌───────────┐         ┌───────────┐
     │ BM25+Vec  │         │ BM25+Vec  │         │ BM25+Vec  │
     │(原始 query)│         │(扩展 query1)│        │(扩展 query2)│
     └─────┬─────┘         └─────┬─────┘         └─────┬─────┘
           │                     │                     │
           └─────────────────────┼─────────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   RRF Fusion (k=60)     │
                    │   原始 query ×2 权重      │
                    │   Top-rank bonus: +0.05  │
                    │   取 Top 40 候选          │
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │     LLM Re-ranking      │
                    │   (qwen3-reranker)      │
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │  Position-Aware Blend   │
                    │  Rank 1-3:  75% RRF     │
                    │  Rank 4-10: 60% RRF     │
                    │  Rank 11+:  40% RRF     │
                    └─────────────────────────┘
```

## 检索算法

### 分数归一化

| 后端 | 原始分数 | 转换 | 范围 |
|------|---------|------|------|
| **BM25 (FTS5)** | SQLite FTS5 BM25 | `abs(score)` | 0 ~ 25+ |
| **Vector** | 余弦距离 | `1 / (1 + distance)` | 0.0 ~ 1.0 |
| **Reranker** | LLM 0-10 评分 | `score / 10` | 0.0 ~ 1.0 |

### 融合策略

`query` 命令使用 **Reciprocal Rank Fusion (RRF)** + 位置感知混合：

1. **Query Expansion**: 原始查询 (×2 权重) + LLM 生成的变体查询
2. **并行检索**: 每个查询同时搜索 FTS 和向量索引
3. **RRF 融合**: `score = Σ(1/(k+rank+1))`，k=60
4. **Top-Rank Bonus**: 任意列表中排名 #1 的文档 +0.05，#2-3 +0.02
5. **强信号检测**: BM25 top-1 分数 ≥0.85 且与 top-2 差距 ≥0.15 时跳过 expansion
6. **Top-K 筛选**: 取 top 40 候选进入重排序
7. **LLM 重排序**: 对每个 chunk（非全文）打分
8. **Position-Aware Blending**:
   - RRF rank 1-3: 75% 检索 / 25% 重排序（保护精确匹配）
   - RRF rank 4-10: 60% 检索 / 40% 重排序
   - RRF rank 11+: 40% 检索 / 60% 重排序（信赖重排序）

### 分数解读

| 分数 | 含义 |
|------|------|
| 0.8 - 1.0 | 高度相关 |
| 0.5 - 0.8 | 中等相关 |
| 0.2 - 0.5 | 有一定相关 |
| 0.0 - 0.2 | 低相关 |

## 智能分块

文档按 ~900 token 分块，15% 重叠，使用断点检测算法寻找自然切割点：

| 模式 | 分数 | 说明 |
|------|------|------|
| `# Heading` | 100 | H1 标题 |
| `## Heading` | 90 | H2 标题 |
| `### Heading` | 80 | H3 标题 |
| `#### ~ ######` | 70~50 | H4-H6 |
| `` ``` `` | 80 | 代码块边界 |
| `---` / `***` | 60 | 分隔线 |
| 空行 | 20 | 段落边界 |
| `- item` / `1. item` | 5 | 列表项 |
| 换行 | 1 | 最小断点 |

**算法**: 接近 900 token 目标时，在前 200 token 窗口内搜索最佳断点。分数衰减公式：`finalScore = baseScore × (1 - (distance/window)² × 0.7)`。代码块内的断点被忽略——代码保持完整。

## Context 系统

Context 是 QMD 的核心特性——为路径添加描述性元数据，帮助 LLM 理解文档归属。

```bash
# Collection 级别
qmd context add notes "" "个人笔记和想法"

# 子路径级别
qmd context add notes "work" "工作相关笔记"
qmd context add notes "work/meetings" "会议记录"

# 层级继承：搜索 notes/work/meetings/2024.md 会返回所有匹配的 context 拼接
# → "个人笔记和想法\n工作相关笔记\n会议记录"

# 列出所有 context
qmd context list

# 删除
qmd context remove notes "work/meetings"
```

## CLI 命令

### Collection 管理

```bash
qmd add <name> <path> [--pattern "**/*.md"]   # 添加 collection
qmd remove <name>                              # 删除 collection
qmd collection rename <old> <new>              # 重命名
qmd list                                       # 列出所有 collection
qmd ls [collection]                            # 列出文件
qmd update [name]                              # 重新索引
qmd status                                     # 索引状态
```

### 搜索

```bash
qmd search <query> [-c collection] [-n 10]     # BM25 检索
qmd query <query> [-c collection] [-n 10]      # 混合检索 + 重排序
```

### 输出格式

```bash
--format cli     # 默认终端格式
--format json    # JSON（适合 agent 消费）
--format csv     # CSV
--format xml     # XML
--format md      # Markdown
--format files   # 简单文件列表：docid,score,filepath,context
--full           # 显示完整内容
--line-numbers   # 显示行号
```

### 文档操作

```bash
qmd get <file> [-c collection]                 # 获取文档
qmd get qmd://notes/file.md                    # 虚拟路径
qmd get "#abc123"                              # docid
qmd get file.md:42 --max-lines 20             # 指定行范围
qmd embed [--force]                            # 生成 embedding
qmd cleanup                                    # 清理孤立数据 + VACUUM
```

## MCP Server

QMD-Py 提供 MCP (Model Context Protocol) 服务器，通过 stdio transport 与 Claude Desktop 等客户端通信。

**工具列表:**
- `qmd_search` — BM25 关键词检索
- `qmd_deep_search` — 混合检索 + query expansion + 重排序
- `qmd_vector_search` — 向量语义检索
- `qmd_get` — 获取文档（路径或 docid，支持模糊匹配建议）
- `qmd_index` — 索引/更新 collection
- `qmd_status` — 索引健康状态
- `qmd_collections` — 列出 collection

**Claude Desktop 配置** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "qmd": {
      "command": "qmd",
      "args": ["serve"]
    }
  }
}
```

## LLM 后端

QMD-Py 支持三种后端，按优先级自动选择：

### llama-cpp-python（推荐）

使用 GGUF 模型，与原版 qmd 相同的模型：

| 模型 | 用途 | 大小 |
|------|------|------|
| `embeddinggemma-300M-Q8_0` | 向量 embedding | ~300MB |
| `qwen3-reranker-0.6b-q8_0` | 重排序 | ~640MB |
| `qmd-query-expansion-1.7B-Q4_K_M` | 查询扩展 | ~1.1GB |

模型从 HuggingFace 下载，缓存在 `~/.cache/qmd/models/`。

### sentence-transformers（fallback）

纯 Python embedding，不需要编译 llama-cpp。适合快速测试。

### FlagEmbedding

专用 reranker 后端（FlagReranker），可与其他后端组合使用。

## 数据存储

数据库: `~/.config/qmd/qmd.db` (SQLite)

```sql
collections     -- 集合目录配置
path_contexts   -- 路径 context 描述
documents       -- 文档元数据（path, title, hash, active）
documents_fts   -- FTS5 全文索引
content         -- 文档内容（content-addressable，按 SHA256 去重）
content_vectors -- embedding 分块（hash, seq, pos）
vectors_vec     -- sqlite-vec 向量索引
llm_cache       -- LLM 响应缓存（query expansion, rerank）
```

配置文件: `~/.config/qmd/qmd.yaml`

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `QMD_CONFIG_DIR` | `~/.config/qmd` | 配置目录 |
| `QMD_DATA_DIR` | `~/.cache/qmd` | 数据/缓存目录 |
| `XDG_CONFIG_HOME` | `~/.config` | XDG 配置根目录 |
| `XDG_CACHE_HOME` | `~/.cache` | XDG 缓存根目录 |

## 系统要求

- **Python** >= 3.11
- **SQLite** >= 3.35（FTS5 支持）
- **GPU**（可选）: CUDA 或 Apple MPS 加速 embedding/reranking

## 安装

```bash
# 基础安装
pip install qmd

# 完整安装（所有 LLM 后端 + MCP）
pip install "qmd[mvp,mcp]"

# 开发环境
pip install "qmd[mvp,mcp,dev]"
pytest tests/ -v
```

## 项目结构

```
qmd/
├── core/
│   ├── db.py           # SQLite 数据库层（schema、CRUD、FTS5、sqlite-vec）
│   ├── config.py       # YAML 配置管理、collection/context 操作
│   ├── store.py        # 文档索引层（content-addressable 存储、增量更新）
│   ├── retrieval.py    # 混合检索引擎（BM25 + Vector + RRF + Rerank）
│   ├── chunking.py     # 智能分块（断点检测、代码围栏保护）
│   ├── document.py     # 文档查找辅助（docid、模糊匹配、glob、cleanup）
│   └── watcher.py      # 文件监听（watchdog，自动索引）
├── cli/
│   ├── main.py         # CLI 入口（argparse，所有命令）
│   └── formatter.py    # 输出格式化（JSON/CSV/XML/MD/Files）
├── llm/
│   ├── base.py         # LLM 抽象接口
│   ├── llama_cpp.py    # llama-cpp-python 后端
│   ├── sentence_tf.py  # sentence-transformers 后端
│   ├── flagembed.py    # FlagEmbedding reranker 后端
│   └── models.py       # 模型配置、GPU 检测
├── mcp/
│   └── server.py       # MCP Server（stdio transport）
├── utils/
│   ├── paths.py        # 路径工具、VirtualPath (qmd://)
│   ├── snippet.py      # 摘要提取、标题提取
│   └── hashing.py      # SHA256 content hash
└── __init__.py         # create_store() / create_llm_backend() 入口
```

## 致谢

Python 移植自 [qmd](https://github.com/tobi/qmd)（Tobias Lütke），核心检索算法、分块策略和融合逻辑忠实复现原版设计。

## License

MIT
