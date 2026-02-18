---
tags:
  - project
  - ExplicitLM
creation date: 2026-01-27
status: active
ownerKey: project/ExplicitLM
---
# ExplicitLM

## 项目简介

## 相关笔记
- [[Notes/2026-1-12 组会]]
- [[Notes/ICLR投稿感悟]]

## Tasks
- [x] 检查 train_router.py 运行结果 ⏳ 2026-01-14
- [x] 审查卢泽宁提交的代码 ⏳ 2026-01-14
- [x] 审查郑辰阳的评测结果 ⏳ 2026-01-18
- [ ] 构建无PMK模型 ⏳ 2026-01-18
- [ ] 构建基于PCA的PMK ⏳ 2026-01-18

## Idea
1. 我们的Memory Bank能否不只是存储知识，而是存储一个claude skill。因为现阶段的claude skill本质还是prompt。这就不可避免的和context等其他prompt在模型内部事实上被摆在了同一位置。这其实不利于利用skill。（参考[一文了解 Anthropic 新推出的 Claude agent 的 Skills 标准](cubox://card?id=7407065408773032789)）

### 构建数据库的难点
1. 行key和列key中每一个序号表示的意思不是固定的，甚至由行和列构成的这整个坐标系都可能发生偏转
2. 行key和列key有时候会相互影响
3. 如何能保证刚好行是1024个列也是1024个
4. k-mean/PCA

## Now
- 

## Knowledge
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
