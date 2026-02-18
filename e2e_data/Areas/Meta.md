---
tags:
  - area
  - meta
creation date: 2026-01-27
status: active
ownerKey: area/Meta
---
# Meta

> 用于维护 ycz-database 本身的规则、写作规范、工作流、工具与自动化。

## 关键入口（Notes）
- [[Notes/CLAUDE.md写作指南]]

## Notes（持续补充）
- 

## Notes（自动索引）

```base
filters:
  and:
    - file.inFolder("Notes")
    - note.owner == this.ownerKey
views:
  - type: table
    name: Notes
```
