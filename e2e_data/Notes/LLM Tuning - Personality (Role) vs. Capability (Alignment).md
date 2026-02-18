---
tags:
  - note
  - LLM
creation date: 2025-11-14 12:04
modification date: Friday 14th November 2025 12:04:20
owner: area/Agent
---
## 1. 核心核心区别：表面与内核

在定义和优化 AI Agent 时，我们需要区分两个维度的目标：**“性格（Personality）”** 与 **“能力（Capability）”**。这两者在技术实现路径上存在本质区别。

### 1.1 性格 (Personality / Role)

- **定义**：模型的“表达风格”和“人设表面”。关乎模型说话的语气、用词习惯、情感色彩以及它“认为”自己是谁。
    
- **本质**：**概率分布的模仿 (Mimicry)**。
    
    - 模型不需要改变底层的逻辑推理能力，只需要学会某种特定的 Token 预测概率（例如：在这个人设下，`Ahoy` 的概率 > `Hello`）。
        
- **关键词**：Style, Tone, Persona, Mimicry, Surface-level.
    

### 1.2 能力与规矩 (Capability / Alignment)

- **定义**：模型的“内在逻辑”、“执行质量”和“可控性”。关乎解决复杂问题的正确率、幻觉控制、以及对硬性指令（如 JSON 格式、API 调用规范）的遵循程度。
    
- **本质**：**认知路径的优化 (Cognitive Optimization)**。
    
    - 涉及改变模型内部处理信息的方式，或通过强化学习（RL）筛选出正确的推理路径（CoT）。
        
- **关键词**：Reasoning, Robustness, Instruction Following, Truthfulness, Self-Correction.
    

> [!ABSTRACT] **直观比喻：演员模型**
> 
> - **改变性格** = 给演员穿上不同的**戏服**，练不同的**口音**（穿上白大褂像医生，穿上海盗服像海盗）。
>     
> - **提升能力** = 送演员去上**特训班**，提高**智商**和**职业素养**（学会了真正的医学逻辑，或者学会了严格遵守剧组纪律不改词）。
>     

---

## 2. 技术实现路径映射

不同的微调技术（PEFT）适用于不同的维度：

### 2.1 LoRA (Low-Rank Adaptation) -> 侧重于“性格”

- **适用场景**：
    
    - **One Base, Multiple Agents**：利用 LoRA 权重小的特点，实现快速切换角色。
        
    - **风格迁移**：让模型变成“林黛玉”或“埃隆·马斯克”。
        
    - **领域知识注入**：让模型学会特定领域的术语（但未必能进行深层推理）。
        
- **优势**：数据需求量小，能够快速拟合特定的表达范式。
    
- **局限**：很难通过单纯的 LoRA 根本性地提升模型的逻辑推理上限（Upper Bound of Reasoning）。
    

### 2.2 ReFT / RFT (Reinforcement / Representation Finetuning) -> 侧重于“能力”

- **适用场景**：
    
    - **复杂推理 (Reasoning)**：提升数学、代码生成、逻辑推导的准确率。
        
    - **格式对齐 (Format Alignment)**：强行约束输出格式（如严格的 JSON/XML）。
        
    - **减少幻觉 (Hallucination Reduction)**：通过干预内部表征或负反馈，抑制模型“胡说八道”的倾向。
        
- **机制**：
    
    - **RFT (Reinforcement)**：通过 Reward Model (RM) 告诉模型“做对了加分，做错了扣分”，逼迫模型优化思考路径。
        
    - **ReFT (Representation)**：干预特定的 Layer 或 Head，调整内部激活状态，使其更“诚实”或“严谨”。
        

---

## 3. 案例分析：医疗 Agent (The Medical Agent Paradox)

假设我们要训练一个 **医疗诊断 Agent**，不同技术路径会导致截然不同的结果：

|**维度**|**使用 LoRA (Target: Dr. House Persona)**|**使用 ReFT/RFT (Target: Diagnostic Capability)**|
|---|---|---|
|**表现特征**|说话尖酸刻薄，喜欢用讽刺修辞，语气非常自信。|说话平淡冷静，客观中立。|
|**内在逻辑**|**弱变化**。可能因为过分追求“像豪斯医生”的语气，而产生错误的医疗建议（为了戏剧性而牺牲准确性）。|**强增强**。严格遵守“问诊-检查-诊断”流程，不会编造药名，逻辑严密。|
|**本质**|**像个医生** (Looks like a doctor)|**是个医生** (Thinks like a doctor)|

---

## 4. 总结与思考 (Takeaway)

在设计 Multi-Agent 系统架构时，应采用 **组合策略**：

1. 使用 **ReFT/SFT/RLHF** 打造一个强逻辑、高依从性的 **基座模型 (Base Model)** —— 保证“智商在线”。
    
2. 使用 **LoRA** 挂载不同的 **Adapter** —— 赋予不同的“性格”和“领域术语”。
    

> [!TIP] 架构设计公式
> 
> Final Agent = Base Model (High Capability via ReFT) + Adapter (Distinct Personality via LoRA)

---

## 5. Related Papers & Links

- [[Neeko: Dynamic LoRA for Role Playing]]
    
- [[LoRASA: Agent-Specific Adaptation]]
    
- [[ReFT: Representation Finetuning for Language Models]]
