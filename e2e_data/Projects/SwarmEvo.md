---
tags:
  - project
  - SwarmEvo
creation date: 2026-01-27
status: active
ownerKey: project/SwarmEvo
---
# SwarmEvo

## 项目简介
SwarmEvo 是一个多智能体（Agent）群体智能 + 在线进化方向的项目，当前工作重点围绕 **MLE-bench** 的端到端评测与工程化落地。

## 关键入口
- 概述：[[Notes/SwarmEvo 概述]]
- Baseline：[[Notes/SwarmEvo Baseline]]
- 获得评分方法：[[Notes/SwarmEvo 获得评分方法]]
- 组会总结：[[Notes/2026-1-12 组会]]

## mle-bench（归属：SwarmEvo）
- [[Notes/MLE-bench评估框架]]
- [[Notes/MLE-bench GPU加速配置]]
- [[Notes/Agent与MLE-bench交互的技术规范]]
- [[Notes/AIDE Agent在MLE-bench上的使用指南]]

## Swarm-Evo 不同版本效果记录

| commit id | 实验压缩包的 url | 测试的数据集规模 | 备注 |
|---|---|---|---|
| 4044b858 | [2026-01-11T04-06-28-GMT_run-group_swarm-evo](x-devonthink-item://CC011084-3BC2-460B-AAB7-6AAF97B8BF13) | low |  |
| 77cf431 | [2026-01-17T06-33-27-GMT_run-group_swarm-evo](x-devonthink-item://59B1776E-B9E4-4E76-A857-B3914BE3514D) | low |  |

## Tasks
- [x] 合并徐岳对 SwarmEvo 项目的 PR ⏳ 2026-01-27 ✅ 2026-01-27
- [x] 为 SwarmEvo 添加功能：使用一个特殊任务获取足够特征信息，并处理繁琐步骤，为后续 Agent 代码生成效果打基础 ⏳ 2026-01-27 ✅ 2026-01-30
- [x] 整理 Swarm-Evo 已经运行成功的实验结果 ⏳ 2026-01-27 ✅ 2026-01-30
- [ ] 添加一个兜底方案
- [ ] 生成 submission.csv 后验证格式

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
