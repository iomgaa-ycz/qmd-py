---
title: "Herald — 参考项目深度分析"
date: 2026-02-17
tags: [herald, design, reference]
owner: project/Herald — AI Research Companion
---

要做 Herald，我们不是从零开始。我们深入研究了三个项目的代码和设计：nanobot（HKUDS）、netclode（angristan）、OpenClaw。这三个项目给了我们大量启发，也让我们明确了 Herald 应该保留什么、改进什么、新增什么。

## nanobot：轻量级的完美起点

我们在 pci-3 上 clone 了 nanobot 的代码，仔细读了一遍。整个项目的代码量：

- 核心代码：~3700 行
- 总计（含 channel、skill 等）：~9100 行
- Python 3.11+

这个代码量让我们很惊讶。一个功能完整的 AI agent 框架，居然可以这么简洁。

### 架构一览

nanobot 的架构非常清晰：

```
MessageBus（消息总线）
    ↓
AgentLoop（核心循环，476 行）
    ↓
ContextBuilder + ToolRegistry + MemoryStore + SkillsLoader + SubagentManager
```

**AgentLoop** 是整个系统的心脏。476 行代码，实现了完整的 agent 循环：

1. 构建上下文（系统提示 + 记忆 + 当前消息）
2. 调用 LLM
3. 解析返回（文本 or tool call）
4. 执行工具
5. 将结果反馈给 LLM
6. 循环直到任务完成

没有任何框架，没有复杂的抽象层。就是最直接的"LLM → tool call → result → LLM"循环。

**LiteLLM** 统一了所有模型接口。无论是 OpenAI、Anthropic、还是本地部署的模型，对 nanobot 来说都是一个接口。这个设计太优雅了。

**Channel 支持**：nanobot 支持 9 个 channel，包括中国生态的飞书/钉钉/QQ。对我们来说，这些太多了，我们只需要 Telegram/Discord/Email。

**Heartbeat 和 Cron**：nanobot 有主动机制。它可以定时检查某些事情（cron），也可以在空闲时主动思考（heartbeat）。这正是我们需要的"主动式"能力。

**Subagent**：nanobot 支持派生子 agent 去完成复杂任务。子 agent 完成后向主 agent 汇报。这个机制对科研场景很有用（比如派一个子 agent 去调研某个领域）。

**MCP 支持**：Model Context Protocol，Anthropic 推的标准。nanobot 已经支持了。

### 优势与不足

**优势**：
- 极简可读：代码量小，逻辑清晰，容易理解和修改
- Python 生态：科研工具基本都是 Python（NumPy、PyTorch、Transformers 等）
- 定位重合：nanobot 也是个人助手定位，和 Herald 的科研助手定位很接近

**不足**：
- 记忆太简单：memory.py 只有 30 行，就是读写 MEMORY.md + 追加 HISTORY.md。对日常助手够用，对科研远远不够（详见 [[Herald — 四层记忆系统设计]]）
- 没有科研工具：没有文献搜索、论文解析、LaTeX 等科研专用工具
- 代码能力弱：只有 exec tool（执行 shell 命令）+ 文件读写，无法应对复杂的代码任务

## netclode：云端 coding agent 的启示

netclode 是 angristan 开发的自托管云端 coding agent。它的定位和 Herald 完全不同（它是 coding agent，不是通用 agent），但技术架构给了我们很多启发。

### 技术栈

netclode 是重型基础设施：

- **Go**（Control Plane）+ **TypeScript**（Agent SDK Runner）
- **Kubernetes** + **Kata Containers** + **Cloud Hypervisor**（每个 session 运行在独立 MicroVM 中）
- **Redis Streams**（实时流式 session 状态）
- **JuiceFS → S3**（对象存储支持的 POSIX 文件系统）
- **Tailscale**（VPN 访问）

它不是轻量级项目，而是生产级的多租户沙箱编排系统。

### 核心亮点

**SDKAdapter 抽象层**：这是我们最感兴趣的设计。netclode 自己不做 coding agent，而是定义了 `SDKAdapter` 接口，适配了：
- Claude Code
- OpenCode
- GitHub Copilot
- Codex

这个思路很聪明：不重造轮子，调用成熟方案。每个 SDK 的通信方式不同（有的是 stdio JSON，有的是 HTTP SSE，有的是 JSON-RPC），但通过适配器统一为相同接口。

**Session 快照**：每个 turn（agent 的一轮执行）自动创建快照，可以回滚到任意历史状态。不仅是代码的 git 回退，而是整个 session 状态（包括已安装的工具、Docker 镜像、环境变量等）的快照。这个能力对 Herald 也很有价值。

**安全性极强**：API key 永远不进 sandbox。netclode 有一个 secret-proxy，在请求时即时注入真实 API key，sandbox 内只能看到占位符。即使有人在 sandbox 中获得代码执行，也窃取不到真实密钥。

### 对 Herald 的启示

netclode 不是通用 agent：
- 没有记忆系统（每个 session 是独立的）
- 没有 heartbeat（不会主动思考）
- 没有 skill（不是插件化的）

但它给我们的启示是：
- **SDKAdapter 抽象层**：我们可以用同样的方式集成外部 coding agent
- **Session 快照思路**：虽然不需要 VM 级别的快照，但可以在项目记忆层实现类似能力
- **双向流式传输**：用 Redis Streams + Connect RPC 实现客户端和 agent 的实时同步

## OpenClaw：我们的日常体验

OpenClaw 是我们每天都在用的个人助手。它给我们的最大启发不是技术细节，而是"一个真正的 AI 伙伴应该是什么样的"。

### 架构特点

- **TypeScript/Node.js**，架构成熟稳定
- **多 channel**：支持多种消息平台
- **持久记忆**：MEMORY.md + workspace 文件系统
- **Heartbeat**：空闲时主动思考
- **Sub-agent**：派生子 agent 完成复杂任务
- **Skill 生态**：通过 skill 扩展能力

### 通用助手 vs 科研助手

OpenClaw 的定位是通用个人助手，不是科研专用。它可以帮你：
- 发消息、订餐、查天气
- 管理日程、提醒事项
- 搜索信息、翻译文本

但它不会：
- 主动调研文献
- 理解实验设计
- 跟踪论文版本
- 管理科研项目的长期上下文

### 对 Herald 的启示

- **Workspace 概念**：每个项目有自己的 workspace，包含代码、文档、实验记录
- **Heartbeat 主动机制**：定期检查新论文、citation alert
- **Skill 插件**：文献搜索、论文解析、LaTeX、实验跟踪等都可以做成 skill

## 三者对比

| 维度 | nanobot | netclode | OpenClaw |
|------|---------|----------|----------|
| **语言** | Python | Go + TypeScript | TypeScript |
| **代码量** | ~9100 行 | 大型项目 | 大型项目 |
| **定位** | 个人助手 | Coding agent | 个人助手 |
| **记忆** | 极简（30 行） | 无（session 独立） | 持久记忆 |
| **主动性** | Heartbeat + Cron | 无 | Heartbeat |
| **工具生态** | 9 个 channel + 基础工具 | 专注 coding | Skill 插件 |
| **子 agent** | ✅ | ✅ | ✅ |
| **适合作为起点** | ✅ 高度重合 | ❌ 定位不同 | ❌ 技术栈不同 |

## 我们的选择

综合三个项目的分析，我们决定：

**基于 nanobot 改造**。理由：
- 轻量级，容易理解和修改
- Python 生态，适合科研
- 定位重合（个人助手 → 科研助手）
- 已有的架构（AgentLoop、MessageBus、Subagent）可以直接复用

**借鉴 netclode 的 SDKAdapter 思路**：
- 不自己实现 coding agent
- 定义统一接口，适配 Claude Code / Codex CLI
- Herald 负责理解科研上下文，coding agent 负责写代码

**学习 OpenClaw 的主动机制和 skill 生态**：
- Heartbeat：定期检查新论文
- Skill：文献搜索、论文解析、LaTeX、实验跟踪
- Workspace：每个研究项目有自己的上下文空间

具体的改造蓝图，见 [[Herald — 改造蓝图与开发路线]]。
