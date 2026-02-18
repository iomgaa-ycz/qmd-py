---
tags:
  - note
  - Agent
  - ClaudeCode
creation date: 2026-01-04 21:09
modification date: Sunday 4th January 2026 21:09:50
owner: area/Claude Code
---
Claude Code 不只是交互式 CLI；它还是一个强大的 SDK，能构建全新的代理——既可做编码任务，也可处理非编码任务。多数新的个人项目我都把它作为默认代理框架，替代 LangChain/CrewAI。

我主要有三种使用方式：

1. 大规模并行脚本化：做大范围重构、修 Bug 或迁移时，我不走交互式聊天，而是写简单的 Bash 脚本并行调用 `claude -p "in /pathA change all refs from foo to bar"`。这比让主代理管理几十个子代理任务更可控、更易扩展。
2. 构建内部聊天工具：把复杂流程封装成简单的聊天界面供非技术用户使用。比如安装器出错时，回退到 Claude Code SDK 直接“修好”。或者做一个“自建版 v0（v0‑at‑home）”，让设计团队在自家 UI 框架里随心编码（vibe code）原型前端，使灵感更高保真，产出的代码更快用于生产前端。
3. 快速原型验证：这是我最常用的方式，不仅用于编码。想到任何代理化任务（例如用自定义 CLI 或 MCP 构建“威胁调查代理”），我会用 Claude Code SDK 快速搭建并测试原型，再决定是否上完整脚手架。

结论：Claude Code SDK 是强大的通用代理框架。先用它完成批量代码处理、内部工具与快速原型，再考虑更复杂的框架。