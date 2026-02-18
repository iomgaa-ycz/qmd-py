---
tags:
  - note
  - idea
creation date: 2025-11-14 11:01
modification date: Friday 14th November 2025 11:01:37
owner: area/Agent
---
**Title:** _Evo-Manifold: Evolutionary Agent Steering via Hyper-Network Generated Manifold Rectification_

## 1. 研究背景与目的 (Research Motivation)

### 1.1 现实问题 (The Problem)

在构建大规模多智能体系统（Multi-Agent Systems）时，我们面临“通用性”与“专业性”的深层矛盾：

- **Prompting 的局限：** System Prompt 仅能在浅层（输入端）进行语义偏置，难以改变模型深层的推理逻辑（如代码审核时的安全敏感度）。且随着对话进行，长上下文会导致指令遵循能力衰减（Lost in the Middle），同时占用宝贵的 Context Window。
    
- **SFT/LoRA 的局限：** 虽然微调能内化行为，但它是静态的。面对成百上千种动态变化的 Agent 需求（如从“温和的Python编辑”切换到“严厉的C++审核”），加载大量 LoRA 适配器会带来显著的显存开销和延迟，且无法实现行为的灵活组合（Compositionality）。
    

### 1.2 研究目标 (The Goal)

本研究旨在提出一种**“参数高效、零Token开销、可组合进化”**的 Agent 行为导向机制。我们试图证明：**Agent 的“角色（Persona）”本质上是基础模型流形空间上的一组特定变换算子。** 通过学习并动态应用这些算子，我们可以在不重训练基座模型的前提下，实现毫秒级的深度角色切换与在线行为进化。

## 2. 预计贡献点 (Expected Contributions)

1. **理论创新：基于流形矫正的行为解耦 (Manifold Rectification for Behavior Decoupling)**
    
    - 提出“行为即算子”假设，摒弃简单的“向量拼接”做法，利用超网络（HyperNetwork）生成层级特定的仿射变换参数，实现对模型隐空间流形的精确“扭曲”与矫正，从而在保留通用知识的同时，强制改变推理轨迹。
        
2. **架构创新：Evo-Manifold 框架**
    
    - 设计包含 **Global Context Compressor (全息压缩器)**、**Orthogonal Operator Codebook (正交算子码本)** 和 **Layer-Adaptive Gate (层级自适应门控)** 的三支柱架构，实现 Zero-Token Overhead 的角色注入。
        
3. **机制创新：基于种群策略的在线进化 (Population-Based Online Evolution)**
    
    - 提出一种非破坏性的进化机制。通过更新 Router 的策略分布而非底层码本，实现 Agent 在交互反馈中“越用越顺手”，避免了直接更新参数导致的灾难性遗忘。
        

## 3. 实现方法 (Methodology)

我们将构建一个轻量级的侧端网络（Side-Network），与冻结参数的 LLM 基座（如 Llama-3 或 Mistral）配合工作。

### 3.1 核心模块设计

#### A. 全息压缩器 (Holographic Context Compressor)

- **功能：** 替代简单的 Top-N Token 筛选，解决信息有损压缩问题。
    
- **实现：** 使用一个小型 Transformer Encoder，将复杂的 System Prompt（如代码规范文档、角色人设）编码为一个定长的全局上下文向量 $z_{global}$。该向量捕捉了指令的全局语义拓扑。
    

#### B. 正交算子码本 (Orthogonal Operator Codebook)

- **功能：** 存储离散的、可组合的行为原语（Behavior Primitives）。
    
- **结构：** 码本 $C = \{M_1, M_2, ..., M_K\}$，其中每个 $M_k$ 不是简单的加法向量，而是用于生成**仿射变换参数 ($\gamma, \beta$)** 的种子特征。
    
- **正交约束：** 在训练 Loss 中引入正交惩罚项，强迫不同的码本条目（如“简洁性”、“安全性”、“Python风格”）在特征空间上尽可能正交，以保证后续的可组合性。
    

#### C. 超网络与流形矫正 (HyperNetwork & Manifold Rectification)

- **功能：** 将抽象的 $z_{global}$ 和码本特征转化为对 LLM 每一层的具体干预。
    
- 机制：
    
    对于 LLM 的第 $l$ 层，超网络 $H_l$ 接收 $z_{global}$ 和路由选择的码本特征 $c_{selected}$，输出特定于该层的缩放因子 $\gamma_l$ 和平移因子 $\beta_l$。
    
    $$h'_l = \text{LayerNorm}(h_l) \cdot (1 + \gamma_l) + \beta_l$$
    
    - 这种 **FiLM (Feature-wise Linear Modulation)** 风格的注入，比简单的残差相加更能深刻改变特征分布（流形矫正）。
        
- **层级自适应：** 引入可学习的 Gate 机制，让网络自动决定主要在哪些层（通常是中间推理层）应用强干预，而在底层（语法层）保持静默。
    

### 3.2 进化机制 (Evolutionary Strategy)

- **推理时进化 (Inference-time Evolution):** 维护一个 Router Policy $\pi(c|x, z_{global})$。当 Agent 收到正/负反馈时，不更新 $C$ 或 HyperNetwork，而是通过梯度上升或强化学习（PPO）更新 $\pi$。这相当于让 Agent 学会“在什么情况下该调用哪个技能包”，实现了安全的在线适应。
    

## 4. 实验设计 (Experimental Design)

### 4.1 数据集选择 (Datasets)

我们将构建一个多维度的 **Code-Agent Benchmark**：

1. **Role-Specific Code Review Data:**
    
    - 包含 10 种不同风格（如 Google Style, Linux Kernel Style）和 5 种不同关注点（如 Security-First, Performance-First, Brevity-First）的代码 Review 数据集。
        
2. **Multi-Turn Interaction Data:**
    
    - 用于测试进化能力的连续对话数据，包含用户对 Agent 行为的显式反馈（如“太啰嗦了，简单点”）。
        

### 4.2 实验任务与对比基准 (Baselines)

**对比组：**

1. **Zero-shot / Few-shot Prompting:** 标准 Prompt 工程（基准线）。
    
2. **Full SFT / Standard LoRA:** 传统的参数微调方法（性能上限）。
    
3. **Prefix-Tuning / P-Tuning v2:** 传统的软提示方法（直接竞品）。
    

**核心实验：**

1. **角色一致性与深度评估 (Role Consistency & Depth):**
    
    - **指标：** 使用 GPT-4 作为裁判，对 Agent 生成的代码建议进行打分（是否符合特定安全标准、是否符合特定风格）。
        
    - **假设验证：** 证明 Evo-Manifold 在去除 System Prompt 的情况下（Zero-Token），仍能达到甚至超过 Few-shot Prompting 的角色依从度，且比 LoRA 更灵活。
        
2. **组合性测试 (Compositionality Test):**
    
    - **操作：** 激活“Python风格”码本 + “严厉语气”码本。
        
    - **目的：** 验证模型是否能正确输出“严厉的Python审核意见”，而不是产生精神分裂的输出（验证流形矫正的平滑性）。
        
3. **上下文效率测试 (Context Efficiency):**
    
    - **场景：** 输入超长代码库（Repo-level）。
        
    - **指标：** 对比 Prompting 方法（占用大量 Token）与本方法（Zero-Token）在处理长代码时的准确率和显存占用。
        
4. **在线进化仿真 (Online Evolution Simulation):**
    
    - **场景：** 模拟一个用户不断挑剔 Agent 的过程。
        
    - **指标：** 绘制 Agent 满足用户需求的成功率曲线。验证通过调整 Router 策略，Agent 能否在 5-10 轮对话内迅速收敛到用户喜欢的特定风格，且不发生灾难性遗忘。
        

### 4.3 预期结果

我们期望数据表明，Evo-Manifold 能够在仅增加 <1% 参数量的情况下，实现与 LoRA 相当的领域专业度，同时具备 Prompting 的灵活性和零 Token 占用的优势，成功展示出“流形矫正”在控制 LLM 行为上的理论优越性。