---
tags:
  - note
  - Agent
creation date: 2025-08-27 11:40
modification date: 星期三 27日 八月 2025 11:40:46
owner: area/Agent
---
**LaMAS（LLM-based Multi-Agent Systems，基于大语言模型的多智能体系统）**是利用多个LLM智能体协作解决复杂任务的系统。

## LaMAS的核心特征

### 1. **定义与优势**

LaMAS通过多个LLM智能体的协作，在处理复杂智能任务时展现出比单智能体更强的能力。在GAIA基准测试排行榜上，表现最好的系统都是多智能体框架，包括：

- OpenAI Agents SDK（原Swarm）
- Microsoft AutoGen
- Google AI Co-Scientist
- CAMEL-AI OWL

### 2. **现有优化方法**

论文将LaMAS的优化方法分为两类：

**无需调参技术**：

- 提示工程（prompt engineering）
- 上下文学习（in-context learning）
- 自我进化（self-evolution）

**参数微调**：

- 通过多智能体辩论生成高质量训练数据
- 编程模块微调以改进工作流组织
- 基于MARL的方法（如本文提出的MARFT）

### 3. **挑战与机遇**

LaMAS面临的主要挑战包括：

- 动态工作流和组织结构的处理
- 智能体间的有效协调
- 计算资源的高效利用

但同时，LaMAS为解决复杂任务提供了新的可能性，特别是在需要多种专业能力、分布式推理和灵活任务分解的场景中。

论文认为，LaMAS代表了向AGI迈进的重要方向，OpenAI的愿景中也将多智能体系统作为最高组织层。