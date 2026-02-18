---
tags:
  - note
  - Agent
  - 强化学习
  - 开源项目
creation date: 2025-08-18
modification date: 2025-08-18
owner: area/Agent
---
# ART(Agent Reinforcement Trainer)概述

**核心概念**：ART是训练AI Agent的新利器，让你的Agent更稳定，基于强化学习对主流模型进行训练。

## 基本信息

- **项目名称**：ART（Agent Reinforcement Trainer）
- **GitHub星数**：2.3k⭐
- **开源地址**：https://github.com/OpenPipe/ART
- **主要功能**：训练AI Agent，提升Agent稳定性

## 支持的模型

ART支持对以下主流模型进行基于RL的训练：
- Qwen
- LLaMA  
- Kimi
- 其他主流模型

## 核心技术亮点

### RULER奖励机制
- **核心亮点**：RULER奖励机制
- **简化优势**：不用写reward function
- **工作原理**：直接用LLM打分评估agent表现
- **适用性**：适配任意任务

### 技术架构特点
- **项目结构**：项目结构清晰
- **微调技术**：基于GRPO实现LoRA微调
- **系统架构**：训练过程抽象成client-server架构
- **性能优化**：支持异步推理与训练解耦

## 适用人群

ART适合以下用户：
- **Agent实践者**
- **Agent评估方法研究者**
- **初学者**：学习RLHF架构与agent任务建模

## 相关领域
- [[Agent]]
