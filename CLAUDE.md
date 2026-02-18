# CLAUDE.md

> [!URGENT]
> **研究性项目 (Research Project)**
> 1. 本项目为 MVP（最小可行性产品），严禁过度工程化。
> 2. 你的所有思考过程和回复必须使用 **简体中文**。

## 1. 项目元数据 (Metadata)

- **项目名**: qmd-py — Python Semantic Retrieval Library
- **核心目标**: 独立的 Python 语义检索库，适配中文科研场景
- **项目类型**: MVP / 研究性项目 / PyPI 独立发布
- **灵感来源**: 受 tobi/qmd（TypeScript）启发，用 Python 重写
- **核心功能**: 
  - Markdown 语义边界 chunking
  - bge-m3 embedding（稠密 + 稀疏双模式）
  - ChromaDB（稠密向量）+ SQLite FTS5（稀疏/全文检索）
  - RRF（Reciprocal Rank Fusion）混合检索
  - bge-reranker-v2-m3 重排序
- **独立性**: 不耦合任何上层应用，独立发布到 PyPI
- **后端**: Python 3.11+
- **Conda 环境**: qmd-py（Python 3.11+）

## 2. 常用命令 (Commands)

### 2.1 Conda 环境管理

> [!CRITICAL]
> **所有 Python 相关命令必须在 qmd-py 环境中执行**
> - 使用 `conda run -n qmd-py <command>` 确保命令在正确环境中运行
> - 或 `source ~/miniconda3/etc/profile.d/conda.sh && conda activate qmd-py`

```bash
# 激活项目环境
source ~/miniconda3/etc/profile.d/conda.sh && conda activate qmd-py

# 推荐：使用 conda run 执行命令
conda run -n qmd-py pip install -e ".[dev]"
conda run -n qmd-py pytest tests/ -v --cov=qmd_py --cov-report=term-missing
conda run -n qmd-py python -m qmd_py

# 代码格式化与检查
conda run -n qmd-py ruff format qmd_py/ tests/
conda run -n qmd-py ruff check qmd_py/ tests/ --fix
```

### 2.2 运行

```bash
# CLI 入口
conda run -n qmd-py qmd-py --help

# 示例：索引 markdown 文件
conda run -n qmd-py qmd-py index --path ./docs/ --db-path ./data/qmd.db

# 示例：查询
conda run -n qmd-py qmd-py search --query "语义检索原理" --top-k 5
```

## 3. 项目结构 (Structure)

```
qmd-py/
├── CLAUDE.md                 # 项目规范（本文件）
├── pyproject.toml            # 依赖、构建、工具配置
├── README.md                 # 项目说明
├── implementation_plan.md    # 临时实施计划（不提交）
├── reference/                # 参考代码（不提交）
│   ├── qmd/                  # QMD 原版 TypeScript 源码
│   └── openclaw-memory/      # OpenClaw memory 模块源码
├── qmd_py/                   # 核心包
│   ├── __init__.py
│   ├── store.py              # QMDStore facade（主入口）
│   ├── chunker.py            # markdown 语义边界切分
│   ├── embedder.py           # bge-m3 embedding（稠密+稀疏）
│   ├── reranker.py           # bge-reranker-v2-m3
│   ├── retriever.py          # 混合检索 + RRF 融合
│   ├── vector_store.py       # ChromaDB 封装
│   ├── model_manager.py      # 模型懒加载 + idle timeout
│   └── cli.py                # Typer CLI
└── tests/                    # 测试
    ├── test_chunker.py
    ├── test_embedder.py
    ├── test_retriever.py
    └── test_store.py
```

## 4. 核心规则 (Rules)

### 4.1 代码开发规范 (Code Style)

- **类型系统**: 强制所有函数签名包含完整类型注解（`Union`, `Optional`, `dict[str, Any]` 等）
- **文档**: 所有模块、类、方法必须包含 **中文 Docstring**（功能、参数、返回值）
- **注释**: 代码注释用 **中文**
- **MVP 原则**:
  - **严禁** 使用默认参数掩盖逻辑（关键参数必须显式传递）
  - **必须** 运行时检查：关键维度/一致性通过 assert 或 if + raise 验证
  - **必须** 在 `tests/` 下编写测试
  - **MVP 优先**: 先跑通再迭代，严禁过度工程化
  - **代码简洁**: 能短就短，不保留废弃代码
- **代码组织**:
  - 导入顺序：标准库 → 第三方库 → 项目内部
  - 类名 `PascalCase`，变量描述性命名，私有变量前缀 `_`
- **日志**: 使用 `loguru`，禁用 `print()`
- **功能修改**: 不考虑向后兼容，直接改原文件，代码简洁性优先

### 4.2 测试规范

- **目录**: `tests/`，目标覆盖率 80%
- **运行**: `conda run -n qmd-py pytest tests/ --cov=qmd_py --cov-report=term-missing`
- **必须先写测试再写实现**（或同步编写）

### 4.3 Git 规范

使用 Conventional Commits，commit message 用中文描述：

| 前缀 | 用途 |
|------|------|
| `feat:` | 新功能 |
| `fix:` | 修复 |
| `refactor:` | 重构（不改功能） |
| `chore:` | 杂项（依赖、配置、清理） |
| `docs:` | 文档 |
| `test:` | 测试 |

**不提交**: `implementation_plan.md` 和 `reference/` 已加入 `.gitignore`

## 5. 技术栈 (Tech Stack)

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| Embedding | bge-m3 (FlagEmbedding)（稠密 + 稀疏） |
| Rerank | bge-reranker-v2-m3 (FlagEmbedding) |
| 稠密向量存储 | ChromaDB |
| 稀疏/全文检索 | SQLite FTS5 |
| 混合检索 | RRF (Reciprocal Rank Fusion, k=60) |
| CLI | Typer |
| 测试 | pytest |
| 日志 | loguru |

## 6. 关键设计决策 (Design Decisions)

### 6.1 模型管理
- **懒加载**: 首次使用时才加载模型到显存
- **Idle Timeout**: 5 分钟无调用自动释放显存
- **GPU 自动检测**: CUDA > MPS > CPU（优先级顺序）
- **模型缓存**: `~/.cache/qmd-py/models/`

### 6.2 Chunking 策略
- **目标大小**: 900 tokens/chunk
- **重叠**: 15% 重叠
- **语义边界**: Markdown 语义边界切分（标题、列表、代码块边界）
- **中文 token 估算**: 字符数 / 1.5

### 6.3 检索策略
- **稠密检索**: ChromaDB 余弦相似度
- **稀疏检索**: SQLite FTS5 全文检索
- **融合**: RRF (k=60) 混合排序
- **重排序**: bge-reranker-v2-m3 对 top-k 候选重新打分

### 6.4 增量更新
- **去重**: 基于内容 SHA256 哈希去重
- **更新策略**: 哈希变化时重新索引

## 7. 参考代码 (Reference Code)

| 路径 | 说明 |
|------|------|
| `reference/qmd/` | QMD 原版 TypeScript 源码 |
| `reference/qmd/src/llm.ts` | 模型管理、chunking 逻辑 |
| `reference/qmd/src/store.ts` | 存储逻辑 |
| `reference/openclaw-memory/` | OpenClaw memory 模块 |
| `reference/openclaw-memory/qmd-manager.ts` | QMD 集成、索引流水线 |
| `reference/openclaw-memory/manager-sync-ops.ts` | 异步更新机制 |

## 8. 开发流程 (Workflow)

1. **规划阶段**: 阅读 `implementation_plan.md`，确认模块边界和接口
2. **执行阶段**: 
   - 先写测试（或同步编写）
   - 实现模块
   - 运行测试验证
3. **收尾阶段**: 
   - 每完成一个模块提交一个 commit
   - 更新文档（如需要）

## 9. 输出规范

### 9.1 语言要求

- 所有输出语言: **中文**

### 9.2 信息密度原则

- **优先使用**: 简洁文本、表格、流程图（Mermaid）、项目符号列表
- **避免使用**: 大段完整代码（信息密度低）、冗长自然语言解释
- **核心原则**: 用最少的字符传递最多的信息

## 10. 上下文获取 (Context & Navigation)

| 需求 | 路径 | 说明 |
|------|------|------|
| 项目规范 | `CLAUDE.md` | 本文件 |
| 项目说明 | `README.md` | 项目概述 |
| 开发计划 | `implementation_plan.md` | 当前迭代的实施计划（临时文件） |
| 项目配置 | `pyproject.toml` | 依赖、构建、工具配置 |
| 参考代码 | `reference/` | QMD 原版 + OpenClaw memory |
