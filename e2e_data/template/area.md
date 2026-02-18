---
tags:
  - area
ownerKey: "area/area"
creation date: 2026-02-14
status: active
---

# area

> Area 只做地图与指针，不复制内容。

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

## 关键入口（手选）
- 
