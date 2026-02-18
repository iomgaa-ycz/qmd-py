---
tags:
  - note
  - ClaudeCode
creation date: 2025-10-27
modification date: 2025-10-27
owner: area/Claude Code
---
# Claude Code 最佳实践

本文档整合了 Claude Code 的最佳实践,包括 CLAUDE.md 设计原则、上下文污染预防、健康检查方法等核心内容。

## 📄 CLAUDE.md 设计原则

### 基础步骤
在您的项目根目录中创建一个 `CLAUDE.md` 文件,以帮助 Claude 理解您的项目。这是最重要的 Claude Code 最佳实践之一:

```markdown
# CLAUDE.md

## Project Overview
Brief description of your project, its purpose, and main technologies.

## Development Guidelines
- Coding standards and conventions
- File structure preferences
- Testing approaches

## Important Commands
- Build commands
- Test commands
- Development server commands
```

Claude Code 启动时会自动读取此文件以提供项目上下文。

### Claude 服从等级

`CLAUDE.md` 的内容比用户提示受到更严格的遵守:
- **CLAUDE.md 指令**: 视为定义操作边界的不可变系统规则
- **用户提示**: 被解读为必须在既定规则内运作的灵活请求

鉴于上述情况,我选择灵活地在 `CLAUDE.md` 中描述我的流程,并简单地利用用户提示为这些流程提供参数或引导模型。通过策略性地向 `CLAUDE.md` 中注入尽可能多的上下文信息,以明确其应遵循的步骤,已取得了良好的效果。

### 模块化 CLAUDE.md 设计与长度管理

我倾向于将 `CLAUDE.md` 拆分为多个功能模块。为了确保最大程度的遵循,我会用 markdown 格式化信息,确保 Claude 能清楚看到指令和模块之间的边界,这也有助于防止指令泄露。

当你在你的 `CLAUDE.md` 中添加更多工作流系统时,可能会收到关于 `CLAUDE.md` 大小可能影响性能的警告。如果你了解自己的令牌预算,这并不一定是个问题。我发现更有效的方式是在 `CLAUDE.md` 中预先加载上下文(包括提供多个示例,并标明他可以读取哪些文件以及禁止读取哪些文件),而不是让 Claude 随意读取可能会或不会对他产生负面影响的文件。

## 🧹 预防上下文污染

### 什么是上下文污染

根据我的经验,通过污染代理的上下文来破坏自己的进程是非常容易的。有很多方式都可能意外污染我的 Claude 代码会话,从而在整个会话过程中产生危险的非预期关联。

### 典型案例

我以一种艰难的方式发现了这一点,当一个简单的操作,比如让 Claude 更新代码然后请求部署,却无意中污染了我后续的更新请求。Claude 开始将每次代码更新都与立即部署关联起来,即使我只是在试验或处理尚未完成的功能。这让我明白,在我的上下文中,每一个操作组合都可能形成潜在的训练模式,日后可能会对我产生不利影响。

### 如何思考上下文污染

我添加到上下文中的每一条信息,或执行的一系列操作,都可能组合在一起,形成非预期的行为模式。我已学会对哪些上下文组合可能被 Claude 误解保持警惕,并在这些危险关联扎根之前主动扫描排查。这一点在让 Claude 执行持续较长时间的代理任务时尤为重要。

### 常见有害模式

**上下文干扰**:
如果没有明确的标记表明一个任务在哪里结束以及另一个任务在哪里开始,Claude 可能会将先前任务中的预期、设置或方法延续到新任务中,从而导致意外行为和结果不一致。
- **界限模糊** - 任务之间缺乏明确分隔标记的过渡
- **隐含假设** - 关于编码风格、部署偏好或工作流模式的隐藏预期,在不同项目类型或需求之间切换时可能产生冲突

**指令污染**:
太多指令类型在争夺注意力和优先级,导致决策瘫痪。
- **上下文过载** - 多个相互冲突的指令集同时生效
- **矛盾的指导** - 拥有指示 Claude 执行 `always test before deploying` 的指令,同时又包含需要 `immediate deployment without full testing` 的紧急修复程序,会导致 Claude 在决策时陷入瘫痪,无法确定哪条指导具有更高的优先级
- **时间混淆** - 早期会话指令使用过时上下文干扰当前任务执行

### 预防与解药

我既制定了防止上下文污染的策略,也准备了在发生污染时的补救措施。在预防方面,我在 `CLAUDE.md` 文件中广泛使用 markdown 格式,以防止指令之间相互干扰,同时我学会了在与 Claude 沟通时有意识地保持明确和具体。当我怀疑自己的上下文已经被污染时,我有相应的解毒剂:使用 `/clear` 命令或开启一个新会话,可以立即重置受污染的行为模式。

**预防策略**:
- **区分上下文** - 使用不同的会话来处理不同类型的工作,以避免相互干扰
- **清晰的边界** - 在任务类型切换时明确告知
- **Markdown 结构** - 使用正确的格式来创建清晰的指令分隔
- **明确沟通** - 清楚地陈述自己的假设和期望,而不是依赖于默会的理解
- **定期回顾上下文** - 定期评估自己可能无意中创建了哪些行为关联

**补救措施**:
- **上下文重置** - 当检测到有毒模式时,使用 `/clear` 或启动新会话以消除污染

### 保持语境清洁的纪律性

毒化上下文感知能力已成为我处理 Claude Code 的基础。就像我不会编写杂乱的代码却期待得到整洁的结果一样,我也不能维持混乱的上下文却期待获得一致的 AI 协作效果。

上下文感知能力可以带来显著的差异。不可预测的行为、不一致的结果以及神秘的故障往往可能源于无意中创建的受污染上下文模式。

## 🏥 Claude Code 健康检查

### 为什么需要健康检查

在与 AI 代理协作时,我们必须执行一种不同类型的健全性检查。

### 基本健康检查方法

在你的 `CLAUDE.md` 顶部添加你的名字:

```markdown
# My name is {NAME}

This file provides guidance to Claude Code when working with this repository.

## Project Overview

This is a React application built with TypeScript and Vite.

...
```

然后询问 Claude:

```
What is my name?
```

通过这个简单的测试,可以验证 Claude 是否正确读取并理解了 `CLAUDE.md` 文件的内容。

## 📝 相关笔记
- [[Claude Code核心配置与使用]] - MCP 配置、工具设置、工作目录管理
- [[Claude Code高级特性]] - Plan Mode、Custom Agents、Ultrathink 等高级功能

## 相关领域
- [[Claude Code]] - AI辅助开发工具领域
