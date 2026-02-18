---
tags:
  - note
  - ClaudeCode
creation date: 2026-01-04 21:02
modification date: Sunday 4th January 2026 21:02:46
owner: area/Meta
---
1. 先立护栏，不写长手册。`CLAUDE.md` 应从小处着手，围绕 Claude 常见错误来写。
2. 不要用 `@` 直接嵌入长文档。虽然很诱人，但会让每次运行都嵌入整份文档，拖垮上下文窗口。而仅写路径时，Claude 又常常忽略。必须明确告诉代理“为何”与“何时”去读该文档。例如：“遇到复杂用法或出现 `FooBarError` 时，请阅读 `path/to/docs.md` 获取高级排错步骤。”
3. 不要只给“绝不”。避免只有负向约束，例如“绝不使用 `--foo-bar`”。一旦代理认为必须用这个标志就容易卡住。务必给出替代方案。
4. 把 `CLAUDE.md` 当作倒逼机制。如果 CLI 命令过于复杂冗长，不要用大段文档去解释——那是在修补人的问题。改为写一个简单的 Bash 封装，提供清晰直观的 API，并记录这个封装。保持 `CLAUDE.md` 尽可能简短，会倒逼你简化代码库与内部工具。

下面是一个简化示例：

```
# Monorepo

## Python
- Always ...
- Test with <command>
... 10 more ...

## <Internal CLI Tool>
... 10 bullets, focused on the 80% of use cases ...
- <usage example>
- Always ...
- Never <x>, prefer <Y>

For <complex usage> or <error> see path/to/<tool>_docs.md

...
```