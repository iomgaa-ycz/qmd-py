---
tags:
  - note
  - ClaudeCode
creation date: 2025-10-27
modification date: 2025-10-27
owner: area/Claude Code
---
# Claude Code 高级特性

本文档整合了 Claude Code 的高级特性,包括 Plan Mode、Agent-First Design、Custom Agents、Ultrathink、Split Role Sub-Agents 等内容。

## 📋 Plan Mode (计划模式)

### 基础介绍
计划模式是 Claude Code 中的一项功能,它将研究和分析与执行分开,从而显著提高安全性。

启用后,Claude 不会编辑文件、运行命令或更改任何内容,直到你批准该计划。

### 如何激活
- **进入计划模式**: 连续按两次 `Shift+Tab`
- **退出计划模式**: 再次按下 `Shift+Tab`

### Available Tools & Restricted Tools

在计划模式下,Claude 可以使用只读和研究工具:
- **Read** - 文件和内容查看
- **LS** - 目录列表
- **Glob** - 文件模式搜索
- **Grep** - 内容搜索
- **Task** - 研究代理
- **TodoRead/TodoWrite** - 任务管理
- **WebFetch** - 网络内容分析
- **WebSearch** - 网络搜索
- **NotebookRead** - Jupyter 笔记本

## 🏗️ Agent-First Design (Agent优先设计)

### 范式转变
目前,我们设计的产品是针对人类团队的开发便利性进行优化的。我相信,未来最成功的产品将会是以 AI 智能体作为核心参与者来设计、迭代和扩展的。一切都会改变:产品架构、功能设计、商业模式、市场策略。

我已经注意到我们对软件架构的思考方式正在发生变化。以人类为中心的设计专注于可读性和团队效率。而以代理为中心的设计则在此基础上进一步优化,使 AI 代理能够快速生成、扩展和大规模个性化内容。软件架构成为一种支持性基础设施,使代理能够高效地理解、修改和扩展产品。

### Agent优先产品原则

- **模块化架构** - 产品由离散、可组合的组件构建而成,这些组件具有清晰的接口,使得智能体能够安全地扩展、修改和重新组合,同时保持系统完整性

- **可模板化的体验** - 代理可以自信地修改并生成变体的用户体验模式,同时保持质量和连贯性

- **可扩展的个性化** - 系统架构使代理能够为单个用户创建独特的版本,而不会使复杂性或运营成本呈指数级增长

- **自动化验证** - 内置机制,使 Agent 能够验证其修改是否正确有效,无需持续人工监督即可为用户提供价值

## 🤖 Custom Agents (自定义代理)

### 什么是 Custom Agents

`Custom agents` 是专门的代理,可用于解决特定任务。它们由 Claude 自动调用,类似于 `Tools` 被自动调用的方式!

### 核心特性

- **独立上下文窗口** - 每个 `custom agent` 都拥有独立的上下文窗口,与 `delegating agent` 相互分离。这使得在无需将每个细节都交由 `delegating agent` 处理的情况下完成更复杂的任务,防止不同任务之间相互干扰上下文,同时保持最佳性能

- **专用系统提示** - 单个 `custom agent` 系统提示可以被精确限定作用域,避免继承冗余上下文,从而节省有限的上下文窗口

- **角色专用工具** - 可以为智能体配置特定工具,通过仅允许受信任的智能体执行某些任务来帮助防止安全问题。可以针对特定智能体在对应角色上进行可靠性的测试和评估。这种第一方级别的集成将"角色拆分子智能体"的概念提升到了一个新的层次!

- **社区共享** - 一旦完善,`custom agents` 可以在项目之间、团队之间甚至在 r/ClaudeAI 社区中共享,从而创建一个不断演进的专业代理协作生态系统

### 构建方式

1. **打开自定义智能体界面**
   ```
   /agents
   ```

2. **选择"创建新代理"** - 选择创建项目级还是用户级的 `custom agent`

3. **定义你的智能体**
   - 建议:先使用 Claude 生成内容,然后根据需要进行个性化修改
   - 请详细描述你的智能体以及何时应使用它
   - 选择特定工具或留空以继承所有工具
   - 编辑系统提示,以定义角色、功能和方法
   - 选择你的智能体颜色
   - 查看你的 `custom agent` 配置

4. **保存并使用** - 你的 `custom agent` 现在已可用!Claude 将在适当情况下自动使用它,你也可以显式调用它:
   ```
   Use the algorithmic complexity specialist agent to analyze this function.
   ```

### 文件格式

```markdown
---
name: your-agent-name
description: Description of when this agent should be invoked
tools: tool1, tool2, tool3  # Optional - inherits all tools if omitted
---

Your agent's system prompt goes here. Define the role, capabilities,
and approach to solving problems. Include specific instructions,
best practices, and any constraints the agent should follow.
```

### 基本用法

1. **自动调用** - 一旦创建,您的 `custom agents` 将自动运行。Claude 会根据您的请求和代理的描述选择并使用适当的代理

2. **手动调用** - 您也可以显式请求特定的代理:
   ```
   Use the algorithmic complexity specialist agent to analyze this function.
   ```

3. **任务委派** - Claude 会智能地将任务路由到专业化的隔离代理,类似于其为不同操作自动选择工具的方式

### 配置

`Custom agents` 以带有 YAML 前置内容的 Markdown 文件形式存储在两个可能的位置中:

| Type 类型 | Location 位置 | Scope 范围 | Priority 优先级 |
|-----------|--------------|-----------|----------------|
| Project agents 项目代理 | `.claude/agents/` | Available in current project 当前项目中可用 | Highest 最高 |
| User agents 用户代理 | `~/.claude/agents/` | Available across all projects 适用于所有项目 | Lower 下 |

当代理名称冲突时,项目级代理优先于用户级代理。

### 配置字段

| Field 字段 | Required 必需的 | Description 描述 |
|-----------|----------------|-----------------|
| name 名称 | Yes 是 | Unique identifier using lowercase letters and hyphens 使用小写字母和连字符的唯一标识符 |
| description 描述 | Yes 是 | Natural language description of the agent's purpose 代理目的的自然语言描述 |
| tools 工具 | No 否 | Comma-separated list of specific tools. If omitted, inherits all tools from the main thread 特定工具的逗号分隔列表。如果省略,则从主对话线程继承所有工具 |

### 最佳实践

- **从 Claude 生成开始** - 用 Claude 生成你的初始智能体,然后对其进行自定义以符合你的需求

- **关注点分离** - 与编程一样,在你的 `custom agents` 中实现更好的关注点分离,有助于提升性能、可维护性、可检查性以及可共享性

- **提供示例** - 在系统提示中包含正面/负面示例。LLMs 擅长模式识别和重复,因此请确保提供足够数量的不同实例

- **渐进式工具扩展** - 从为 `custom agent` 精心限定的一组工具开始,随着您验证其行为并确定实现最佳性能所需的额外功能,逐步扩展工具范围

## 🎭 Split Role Sub-Agents (角色拆分子代理)

### 基本流程

我尝试让 Claude 执行 `Utilise multiple sub-agents to validate this code from multiple perspectives` 操作:

- **设置阶段** - 确保 Claude 处于计划模式,并且已运行 ultrathink
- **角色建议** - Claude 会自动建议各种适用于当前任务的相关角色
- **视角选择** - 选择您希望任务被评审的视角类型
- **并行分析** - 子代理使用其专业方法完成审查
- **整合** - 发现结果由 Claude 进行整合并呈现

### 视角选择示例

**代码审查任务**:
```
Create sub-agents and analyse the problem from the following perspectives:
factual, senior engineer, security expert, consistency reviewer, redundancy checker
```

**用户体验任务**:
```
Create sub-agents and analyse the problem from a:
creative, nooby user, designer, marketing, seo perspective
```

**文档任务**:
```
Create sub-agents to review this documentation from the following perspectives:
technical accuracy, beginner accessibility, SEO optimization, content clarity
```

### 特点

有趣的是,每种视角都会根据自身角色和解决问题的方法自然地倾向于不同的工具。这使得分析更加全面,因为不同的智能体本能地为其专业领域选择最相关的工具组合。

## ⚡ Ultrathink (超级思考模式)

### Ultrathink 与计划模式

我个人使用 `ultrathink` + `Plan Mode` 与 `Claude 4 Sonnet` 搭配可获得出色的结果。当你不想动用 `Claude 4 Opus` 时,这种组合尤其有用。我发现它通常可以弥补复杂任务中的智能差距,而当效果不足时,我会通过多轮带有批评的 `ultrathink` + `Plan Mode` 来 `rev` 模型。

### 启动引擎 (Revving)

启动引擎意味着指示 Claude 在 `Plan Mode` 中创建一个计划,然后系统地对该计划进行批判,找出缺失的边界情况、冗余的部分以及顺序上的低效率。这一迭代过程推动模型经历多轮思考循环,以达到更高的表现水平。

### 完整的技术栈

- **基础**: `ultrathink` 用于增强思考
- **规划**: `Plan Mode` 用于结构化方法
- **迭代**: `revving` 用于多轮批评
- **观点**: `split role sub-agents` 用于多样化分析

## 📝 相关笔记
- [[Claude Code核心配置与使用]] - MCP 配置、工具设置、工作目录管理
- [[Claude Code最佳实践]] - CLAUDE.md 设计、上下文管理、健康检查

## 相关领域
- [[Claude Code]] - AI辅助开发工具领域
