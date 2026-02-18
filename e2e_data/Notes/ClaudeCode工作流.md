---
tags:
  - note
  - ClaudeCode
creation date: 2026-01-04 21:04
modification date: Sunday 4th January 2026 21:04:49
owner: area/Claude Code
---
一般有三种工作流

- `/compact`（尽量避免）：尽量不使用。自动压缩不透明、容易出错且优化不足。
- `/clear` + `/catchup`（简单重启）：我的默认做法。先用 `/clear` 清空状态，再运行自定义 `/catchup` 命令，让 Claude 阅读当前分支的所有改动文件。
- “文档化并清空”（复杂重启）：用于大型任务。先让 Claude 把计划与进度写入一个 `.md`，再 `/clear` 清空状态，开启新会话并让它读取该 `.md` 继续执行。

结论：不要依赖自动压缩。简单任务用 `/clear` 重启；复杂任务用“文档化并清空”，为代理建立更持久的外部“记忆”。