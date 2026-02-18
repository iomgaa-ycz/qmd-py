---
title: "Herald — 改造蓝图与开发路线"
date: 2026-02-17
tags: [herald, design, roadmap]
owner: project/Herald — AI Research Companion
---

我们已经明确了 Herald 的目标（[[Herald — 为什么要做这个项目]]），分析了可以借鉴的项目（[[Herald — 参考项目深度分析]]），确定了技术选型（[[Herald — 技术选型与架构决策]]），设计了两个核心能力（[[Herald — 代码能力与 Coding Agent 集成]]、[[Herald — 四层记忆系统设计]]）。

现在到了最关键的问题：具体怎么做？

这篇笔记会回答：
- 从 nanobot 保留什么、改什么、新建什么
- 需要哪些科研专用工具
- 分几个阶段开发，每个阶段的目标是什么

## 保留的：nanobot 的优势

nanobot 的架构非常优秀，我们没有理由推翻重来。以下这些模块我们完全保留：

### 核心架构（100% 保留）

**AgentLoop** — 476 行的核心循环，处理 LLM 调用、工具执行、结果反馈。这是 nanobot 的心脏，经过充分验证，无需改动。

**ContextBuilder** — 构建 LLM 的输入上下文（system prompt + memory + tools + messages）。我们只需要扩展它支持四层记忆的加载策略，不需要重写。

**SkillsLoader** — 加载工具定义（从 `SKILLS.md` 和 `skills/` 目录）。科研工具也会以 skill 的形式集成，所以这个模块原样保留。

**SubagentManager** — 派生子 agent 处理复杂任务。这个机制我们会大量使用（文献调研、代码实现、实验分析都可能派生子 agent）。

**Provider Registry (LiteLLM)** — 统一的模型接口，支持 OpenAI、Anthropic、本地模型等。这是 nanobot 的一个巨大优势，让我们不被单一模型提供商绑定。

**MessageBus** — 消息总线，解耦 channel 和 agent。保留。

**CronService** — 定时任务。我们会用它实现"每天晚上自动调研新论文"、"每周日生成进度摘要"等功能。

**HeartbeatService** — 空闲时主动思考。这正是 Herald 需要的"主动性"。我们会扩展它的触发逻辑（不只是空闲，还包括"实验运行中"、"论文投稿后"等状态）。

**SubagentManager** — MVP 阶段暂不实现。Claude Code 支持上下文注入（`--append-system-prompt` + `--mcp-config`），可以被赋予科研记忆，能力边界不限于纯代码任务。等后续确实需要并行的"带记忆的非代码后台任务"时再加回来。

### 基础工具（选择性保留）

nanobot 的基础工具：

- ✅ **read / write / edit** — 文件操作，保留
- ✅ **exec** — 执行命令，保留
- ✅ **spawn** — 派生子 agent，保留
- ✅ **web_search / web_fetch** — 网络搜索和抓取，保留（文献调研会用到）
- ✅ **browser** — 浏览器控制，保留（可能用于下载论文全文）
- ❌ **message** — 发送消息到各种平台，保留但会精简支持的平台

## 大改的：从通用助手到科研伙伴

### 记忆系统：从 30 行到四层架构

nanobot 的 `memory.py`（30 行）→ Herald 的 `memory/` 模块（预计 800+ 行）

**改动内容**：

1. **保留 Layer 4**：`MEMORY.md` 和 `HISTORY.md` 的机制完全保留
2. **新增 Layer 2**：实现 `ProjectMemory` 类，管理项目结构化记忆
   - `memory/projects/{project}/overview.md`
   - `memory/projects/{project}/papers.jsonl`
   - `memory/projects/{project}/experiments.jsonl`
   - `memory/projects/{project}/decisions.md`
   - `memory/projects/{project}/timeline.md`
3. **新增 Layer 3**：集成 QMD，实现混合搜索（BM25 + 向量 + LLM 重排序）
   - 索引所有论文、实验、笔记
   - 通过 MCP 或 CLI 对接 QMD
   - 每个研究项目一个 collection
4. **改写上下文加载逻辑**：从"全部塞进 system prompt"改为"分层按需加载"

详细设计见 [[Herald — 四层记忆系统设计]]。

### Channel 层：精简

nanobot 支持 9 个 channel：Telegram、Discord、Email、iMessage、Slack、QQ、钉钉、飞书、Lark。

对 Herald 来说，这太多了。我们只需要：

- **iMessage** — 承璋日常使用的主力通道（需要新增，nanobot 没有，参考 OpenClaw 的实现）
- **Telegram** — 灵活好用，API 友好
- **Discord** — 学术社区和团队协作场景
- **Email** — 接收论文提醒、审稿邮件、每周摘要等

砍掉：QQ、钉钉、飞书、Lark、Slack、Mochat、WhatsApp

这能减少大量依赖和维护成本。

### 工具系统：新增科研专用工具

nanobot 的工具是通用的（文件、命令、浏览器等）。Herald 需要科研专用工具。

我们会在 `skills/research/` 目录下新增一整套工具（详见下一节"新建的"）。

## 新建的：科研核心能力

### CodingAgentTool

详细设计见 [[Herald — 代码能力与 Coding Agent 集成]]。

**功能**：委托代码任务给外部 coding agent（Claude Code、Codex）

**实现位置**：`skills/research/coding_agent.py`

**接口**：

```python
def coding_agent(
    task: str,
    context: dict,
    agent_type: str = "claude_code",
    config: dict = None
) -> dict:
    """
    委托代码任务给 coding agent
    
    Args:
        task: 代码任务描述
        context: 上下文（项目路径、文件列表、测试要求等）
        agent_type: claude_code | codex | opencode
        config: agent 配置
        
    Returns:
        {
            "success": bool,
            "output": str,
            "files_changed": list,
            "tests_passed": bool,
            "summary": str
        }
    """
```

**初期支持**：Claude Code CLI、Codex CLI（pci-3 上已安装）

**后续扩展**：OpenCode、GitHub Copilot

### 项目管理模块

**功能**：管理研究项目的生命周期

**实现位置**：`herald/project_manager.py`

**核心方法**：

```python
class ProjectManager:
    def create_project(self, name: str, goal: str) -> Project
    def get_project(self, name: str) -> Project
    def list_projects(self, status: str = None) -> list[Project]
    def add_paper(self, project: str, paper: Paper) -> None
    def add_experiment(self, project: str, experiment: Experiment) -> None
    def add_decision(self, project: str, decision: str) -> None
    def update_timeline(self, project: str, event: str) -> None
```

**与记忆系统的关系**：ProjectManager 负责写入，MemoryStore 负责读取和检索

### 主动调研机制

**功能**：在用户未察觉文献缺失时主动调研

**触发场景**：

1. **用户提到新概念**："我想试试 diffusion model"
   → Herald 检查项目记忆，发现没有 diffusion 相关论文
   → 主动调研："我发现你还没有关于 diffusion model 的文献。我帮你调研一下最新进展吧？"

2. **实验结果异常**：实验 MSE 突然升高
   → Herald 怀疑可能是某个 bug 或配置问题
   → 主动检查代码变更、超参数变化、数据集版本

3. **定时巡检**：每天晚上 10 点（用户的科研时间）
   → 检查 arXiv 是否有相关新论文
   → 如果有，发送摘要："今天 arXiv 上有 3 篇和你项目相关的论文：xxx"

**实现方式**：结合 HeartbeatService 和 CronService

```python
# 在 HeartbeatService 中注册回调
async def on_user_message(message: str):
    # 提取关键概念
    concepts = extract_concepts(message)
    
    # 检查项目记忆中是否有相关论文
    for concept in concepts:
        papers = project_memory.search_papers(concept)
        if not papers:
            # 触发主动调研
            await proactive_research(concept)

# 在 CronService 中注册定时任务
@cron("0 22 * * *")  # 每天 22:00
async def daily_arxiv_check():
    projects = project_manager.list_projects(status="active")
    for project in projects:
        keywords = project.get_keywords()
        new_papers = arxiv_search(keywords, since="yesterday")
        if new_papers:
            await notify_user(f"今天 arXiv 上有 {len(new_papers)} 篇和 {project.name} 相关的论文")
```

## 科研专用工具清单

我们会在 `skills/research/` 下实现以下工具：

### 文献工具

**search_papers**：搜索论文（Semantic Scholar API + arXiv API）

```python
def search_papers(
    query: str,
    venue: str = None,
    year_from: int = None,
    year_to: int = None,
    limit: int = 10
) -> list[Paper]:
    """
    搜索学术论文
    
    Args:
        query: 搜索关键词
        venue: 限定会议/期刊（如 "NeurIPS", "ACL"）
        year_from: 起始年份
        year_to: 截止年份
        limit: 返回数量
        
    Returns:
        论文列表（标题、作者、摘要、引用数、PDF链接等）
    """
```

**fetch_paper**：获取论文全文（下载 PDF 并存储）

**parse_paper**：解析论文（提取标题、摘要、方法、实验结果）

**get_citations**：获取论文的引用关系（引用了谁、被谁引用）

### 写作工具

**outline**：生成论文大纲

```python
def outline(
    title: str,
    key_points: list[str],
    target_venue: str = "NeurIPS"
) -> dict:
    """
    生成论文大纲
    
    Args:
        title: 论文标题
        key_points: 关键点列表
        target_venue: 目标会议/期刊
        
    Returns:
        {
            "sections": [
                {"name": "Introduction", "subsections": [...], "key_points": [...]},
                {"name": "Related Work", ...},
                ...
            ],
            "estimated_pages": 9
        }
    """
```

**draft**：展开某个 section 的草稿

**latex**：生成 LaTeX 代码

**review**：论文自查（检查常见问题：缺失引用、实验不全、逻辑跳跃等）

### 实验工具

**track_experiment**：记录实验到项目记忆

```python
def track_experiment(
    project: str,
    name: str,
    config: dict,
    results: dict,
    notes: str = None
) -> str:
    """
    记录实验
    
    Args:
        project: 项目名
        name: 实验名称
        config: 配置（数据集、模型、超参数）
        results: 结果（指标）
        notes: 备注
        
    Returns:
        实验 ID
    """
```

**run_experiment**：运行实验脚本（包装 exec，自动记录日志）

**analyze_results**：分析实验结果（对比多个实验、生成图表）

### 知识工具

**index_knowledge**：将内容索引到语义记忆（手动触发向量化）

**relate**：建立知识关联（"实验 A 基于论文 B 的思路"）

## 分阶段路线

我们把开发分成 5 个阶段。每个阶段都有明确的、可验证的目标。

### P0 — 基础框架（1-2 周）

**目标**：搭建可运行的基础框架，实现最基本的文献搜索

**任务**：

- [ ] Fork nanobot 代码到 `/home/pci/ycz/Code/herald/`
- [ ] 精简 channel（保留 iMessage、Telegram、Discord、Email）
- [ ] 移除无关依赖（QQ SDK、钉钉 SDK 等）
- [ ] 实现第一个科研工具：`search_papers`（Semantic Scholar API）
- [ ] 测试：能通过 Telegram 搜索论文并返回结果

**验收标准**：

```
我: 帮我搜索最近关于 diffusion model 的论文
Herald: 找到 10 篇相关论文：
1. "Denoising Diffusion Probabilistic Models" (NeurIPS 2020) - 引用 12000+
   摘要：提出了 DDPM，通过逐步去噪生成高质量图像...
   PDF: https://arxiv.org/pdf/2006.11239.pdf
2. ...
```

### P1 — 记忆系统（2-3 周）

**目标**：实现四层记忆架构，让 Herald 能够记住项目信息

**任务**：

- [ ] 重写 `memory/` 模块
  - [ ] 实现 `ProjectMemory` 类（管理项目结构化记忆）
  - [ ] 集成 QMD（语义记忆）
  - [ ] 改写 `ContextBuilder`（分层加载策略）
- [ ] 实现 `ProjectManager`（项目管理）
- [ ] 实现 `fetch_paper` 和 `parse_paper`（论文下载和解析）
- [ ] 实现 `track_experiment`（实验记录）

**验收标准**：

```
我: 创建一个新项目，叫 TimeSeriesForecasting，目标是在 ETTh1 上做时序预测
Herald: 项目 TimeSeriesForecasting 已创建。我会帮你跟踪论文、实验和决策。

我: 帮我把刚才搜到的 "Attention Is All You Need" 加到项目里
Herald: 已添加到项目记忆。我标注了相关性："Multi-head attention 可能适用于时序建模"

（过了几天）

我: 我们项目里有哪些论文用了 attention？
Herald: 检索到 3 篇：
1. "Attention Is All You Need" (2017) - 你在 2026-02-17 添加的
2. "Temporal Fusion Transformers" (2021) - 我在 2026-02-19 主动调研时发现的
3. ...
```

### P2 — 论文写作 + 实验跟踪（2-3 周）

**目标**：支持论文写作辅助和实验管理

**任务**：

- [ ] 实现写作工具：`outline`、`draft`、`latex`、`review`
- [ ] 实现实验工具：`run_experiment`、`analyze_results`
- [ ] 改进项目记忆的可视化（生成项目进展报告）

**验收标准**：

```
我: 帮我生成一个论文大纲，标题是 "Attention-based Multi-horizon Time Series Forecasting"，目标是 NeurIPS
Herald: 我根据你的项目记忆生成了大纲：
## 1. Introduction (1 page)
- 时序预测的重要性和挑战
- 现有方法的局限（LSTM 难以捕捉长距离依赖）
- 我们的贡献：attention-based 架构 + multi-horizon 预测
## 2. Related Work (1.5 pages)
- Transformer 在 NLP 的成功（引用你项目里的 paper_001）
- 时序预测方法综述
- Attention 在时序的应用（引用 paper_003, paper_007）
...

我: 展开 Introduction 的第一段
Herald: 草稿如下：
"Time series forecasting is a fundamental problem in machine learning with applications in finance, weather prediction, and energy management. The key challenge lies in capturing complex temporal dependencies across multiple horizons..."

（修改几轮后）

我: 生成 LaTeX
Herald: 已生成 paper/introduction.tex
```

### P3 — Coding Agent 集成 + 主动调研（3-4 周）

**目标**：接入 coding agent，实现主动调研机制

**任务**：

- [ ] 实现 `CodingAgentTool`（支持 Claude Code 和 Codex）
- [ ] 实现主动调研机制（基于 HeartbeatService）
- [ ] 实现定时巡检（基于 CronService）
- [ ] 实现知识关联工具：`relate`

**验收标准**：

```
我: 我需要一个 attention-based 时序预测模型
Herald: 我会帮你实现。让我看看项目结构...
（Herald 检查代码，构造 prompt，委托给 Claude Code）
Herald: Claude Code 正在实现...
（10 分钟后）
Herald: 实现完成！
- 文件：models/attention_forecaster.py (245 lines)
- 通过测试：3/3
- 性能：在 ETTh1 val set 上 MSE=0.342
代码已提交到 git，实验记录已添加到项目记忆（exp_015）

（第二天早上）
Herald: 早上好！昨天晚上 arXiv 上有 2 篇和你项目相关的论文：
1. "Crossformer: Transformer Utilizing Cross-Dimension Dependency for Multivariate Time Series Forecasting"
   - 发表于 ICLR 2023
   - 提出了跨维度 attention，可能对你的多变量预测有帮助
   要我帮你添加到项目里吗？
```

### P4 — 项目管理 + 知识图谱（持续）

**目标**：完善项目管理，可视化知识图谱

**任务**：

- [ ] 实现项目看板（当前任务、进度、里程碑）
- [ ] 实现知识图谱可视化（论文引用关系、实验演进关系）
- [ ] 改进主动性（更智能的触发时机、更精准的调研方向）
- [ ] 性能优化（向量检索加速、上下文压缩）

**验收标准**：

```
我: 给我看看 TimeSeriesForecasting 的进展
Herald: 
项目：TimeSeriesForecasting
状态：进行中（第 45 天）
目标：在 ETTh1 上实现 SOTA 时序预测，投稿 NeurIPS 2026

进度：
✅ 文献调研（15 篇论文）
✅ 基线实验（LSTM, Transformer, Informer）
🔄 模型开发（Attention-based，当前 MSE=0.342，目标 <0.32）
⏳ 论文撰写（大纲完成，正文 30%）

里程碑：
- 2026-01-15: 项目启动
- 2026-02-01: 完成文献调研
- 2026-02-10: 首次超过 baseline
- 2026-03-01: 目标完成模型开发
- 2026-04-15: 目标投稿

知识图谱（论文引用关系）：见 graphs/paper_relations.pdf
实验演进（MSE 变化曲线）：见 graphs/experiment_history.pdf
```

## 技术债务和风险

**依赖管理**：

- QMD 需要本地 GGUF 模型（embedding + reranking），首次使用需要下载
- Coding Agent 的调用可能失败（CLI 崩溃、API 限流），需要重试和降级机制

**性能风险**：

- 向量检索在记忆量大时可能变慢，需要优化（批量索引、增量更新）
- Context window 仍然有限，需要更智能的压缩策略

**可维护性**：

- 代码量会从 nanobot 的 9000 行增长到预计 20000+ 行
- 需要更好的模块化和测试

**时间估算**：

- P0-P3 预计 8-12 周（2-3 个月）
- P4 是持续改进，没有明确终点

## 小结

Herald 的改造蓝图：

- **保留** nanobot 的核心架构和基础工具
- **大改** 记忆系统（从 30 行到四层架构）和 channel 层（精简）
- **新建** coding agent 集成、项目管理、主动调研、科研工具

分阶段路线：

- **P0**（1-2周）：基础框架 + 文献搜索
- **P1**（2-3周）：四层记忆 + 项目管理
- **P2**（2-3周）：论文写作 + 实验跟踪
- **P3**（3-4周）：Coding Agent + 主动调研
- **P4**（持续）：知识图谱 + 性能优化

目标：在 2-3 个月内，从一个想法，变成一个可用的科研伙伴系统。
