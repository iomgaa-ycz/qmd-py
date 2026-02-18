---
tags:
  - note
  - LLM
creation date: 2025-11-13 22:22
modification date: Thursday 13th November 2025 22:22:51
owner: area/LLM
---
## 1. Memory 的核心定义与物理形态

### 1.1 概念定义

MemoryLLM 中的 Memory 并非传统意义上的外部向量数据库（如 RAG），也非单纯的 KV Cache。

- **定义**：Memory 被实例化为一个固定大小的 **Memory Pool（内存池）**。
    
- **位置**：位于 Transformer 的 **Latent Space（潜在空间）** 内。
    
- **本质**：Memory 被概念化为每一层 Transformer 内部的 Hidden Vectors（隐藏向量），被称为 **"Memory Tokens"**。
    
- **功能**：作为过往知识的 **Compressed Representation（压缩表示）**。它是模型中的 **Self-updatable Parameters（可自我更新参数）**。
    

### 1.2 数学符号与维度

- **符号表示**：$\theta = \{\theta^l\}_{l=1}^L$
    
    - $L$：Transformer 的层数。
        
    - $\theta^l$：第 $l$ 层的 Memory 矩阵。
        
- **单层维度**：$N \times d$
    
    - $N$：Memory Tokens 的数量（总容量）。
        
    - $d$：Word Embedding 维度（与 Backbone 模型一致）。
        
- **关键参数**：
    
    - **$N$** (Total Capacity)：Memory 的总大小。
        
    - **$K$** (Update Size/Compression Ratio)：每次更新时用于存储新知识的 Token 数量。
        
    - _注：更小的 $K$ 意味着更高的压缩率；$N/K$ 的比值决定了知识保留的能力。_
        

### 1.3 具体实例化 (基于 Llama2-7B)

对话中详细探讨了基于 Llama2-7B 的具体实现参数：

- **Backbone ($\phi$)**：Llama2-7B (32 Layers, Hidden Dim $d=4096$)。
    
- **Memory ($\theta$)**：
    
    - 每层 Memory Tokens 数量 ($N$)：**7,680**。
        
    - 每层 Memory 维度：**7,680 × 4,096**。
        
    - 层数：**32 层**（每层都有独立的 Memory Pool）。
        
- **Memory 总参数量**：$\theta \in \mathbb{R}^{32 \times 7680 \times 4096} \approx$ **1.066 Billion (1.066B)**。
    
- **模型总规模**：7B (Backbone) + 1.066B (Memory) $\approx$ **8B**。
    

---

## 2. 架构实现与存储逻辑

### 2.1 存储方式：独立于 Attention Block

**核心澄清**：Memory Pool **不是**存储在 Multi-Head Attention 或 MLP 内部，而是作为**独立的 Token Embeddings 矩阵**存在于每一层的表示空间中。

- 它类似于可学习的 "Prefix Tokens" 或 "Soft Prompts"，但规模巨大且动态更新。
    
- **结构图示**：
    
    ```
    Input Tokens + Memory Tokens (θ^l)
             ↓
    [Layer l: Attention + MLP]
             ↓
    Output Hidden States (传递给下一层)
    ```
    

### 2.2 两种运行模式的交互机制

MemoryLLM 通过两种截然不同的模式处理 Memory：**Generation（读取/推理）** 和 **Self-Update（写入/更新）**。

#### A. Generation 阶段（如何使用 Memory）

在此阶段，Memory Tokens 充当**额外的 Context**，被当前的 Input Tokens "Attend" 到。

- **逻辑流程**：
    
    1. **拼接 (Concat)**：将当前层的 Input Hidden States 与该层的 Memory Pool ($\theta^l$) 拼接。
        
        - 输入维度：`(Batch, Seq_Len, Dim)`
            
        - Memory 维度：`(N, Dim)`
            
        - 拼接后维度：`(Batch, Seq_Len + N, Dim)`
            
    2. **Attention 计算**：
        
        - **Query (Q)**：仅来自 Input Hidden States。
            
        - **Key (K) & Value (V)**：来自 **Input + Memory Tokens**。
            
        - _结果_：输入 Token 可以从 Memory Token 中获取信息。
            
    3. **MLP 处理**：Attention 的输出（仅对应 Input 部分）通过 MLP，Memory 部分不参与后续 MLP 计算。
        

#### B. Self-Update 阶段（如何更新 Memory）

在此阶段，模型将新知识压缩进 Memory Pool。这是一个**层层递进 (Layer-by-Layer)** 的过程。

- **逻辑流程 (单层更新)**：
    
    1. **提取候选**：从当前 Memory Pool ($\theta^l$) 中提取**最后 $K$ 个** Tokens ($e_\theta$)。
        
    2. **拼接新知识**：将这 $K$ 个 Tokens 与新知识的 Hidden States ($h_l$) 拼接。
        
    3. **Transformer 处理**：将拼接后的序列通过当前的 Transformer Layer（包含 Attention 和 MLP）。
        
    4. **生成新 Memory**：取输出结果中的**最后 $K$ 个** Hidden States，作为新的 Memory Tokens。
        
    5. **更新 Pool (Forgetting)**：
        
        - 从原 Memory Pool 中**随机丢弃 (Random Drop)** $K$ 个旧 Tokens。
            
        - 将新生成的 $K$ 个 Tokens 填入。
            
        - _机制_：这种固定大小 + 随机丢弃策略实现了类似人类的“指数级遗忘”。
            

---

## 3. 训练细节与配置

### 3.1 训练范式：Continued Training (继续训练)

MemoryLLM 不是从零预训练（Pre-training），而是基于预训练模型进行继续训练。

- **组件状态**：
    
    - **$\phi$ (Llama2-7B)**：**未冻结 (Not Frozen)**。虽然初始化自预训练权重，但在训练过程中会随梯度更新。
        
        - _目的_：让 Transformer 学会如何 Attend 到 Memory，以及如何进行知识压缩。
            
    - **$\theta$ (Memory Pool)**：随机初始化，随训练进行动态学习和更新。
        
- **梯度流 (Gradient Flow)**：训练时，梯度会同时回传给 Backbone ($\phi$) 和 Memory ($\theta$)。
    

### 3.2 数据集与训练目标

- **训练数据**：
    
    - **来源**：**C4 Dataset** (Processed version from Red-Pajama)。
        
    - **主要构成**：大规模网络文本语料。
        
    - **特殊子集**：**Long Context Subset**（文档长度 > 2048 tokens），用于训练长上下文能力。
        
    - _注_：未使用专门的结构化知识库，完全依靠阅读非结构化文本进行自我构建。
        
- **任务类型**：Next Word Prediction (下一个词预测)。
    
- **模型需要学习的能力**：
    
    1. **新知识整合**：将 $x_1$ 压缩进 Memory，用于辅助预测 $x_2$。
        
    2. **长上下文理解**：通过多步更新维持上下文。
        
    3. **减轻遗忘**：跨文档的知识保留。
        

### 3.3 资源与开销

- **硬件**：8 × A100-80GB GPUs。
    
- **时长**：3 天。
    

---

## 4. 关键问题澄清 (Q&A 整理)

针对对话中出现的困惑点，整理如下核心逻辑：

1. **"每层独立的 Memory Pool" 是什么意思？**
    
    - 这意味着 Memory 不是全局共享的。Llama2 有 32 层，就有 32 个 $7680 \times 4096$ 的矩阵。
        
    - 第 1 层的输出会更新第 1 层的 Memory，并传递给第 2 层；第 2 层的输出更新第 2 层的 Memory，以此类推。这是一个**串行**的更新过程。
        
2. **Backbone ($\phi$) 到底有没有冻结？**
    
    - **结论：没有冻结。**
        
    - 证据：训练流程图中包含 "With Gradient" 路径。如果冻结了 Backbone，模型就无法学会适配这个新增的巨大的 Memory Pool，也无法学会复杂的压缩操作。
        
3. **Memory Pool 如何与 Llama2 融合？**
    
    - **融合点**：Attention 机制。
        
    - Memory Tokens 被视为额外的 KV Pairs。这不改变 Transformer 的物理结构（Block 还是那个 Block），只是改变了 Attention 计算时的输入数据规模（Sequence Length 变长了）。
        
4. **MemoryLLM 与 Prefix/Prompt Tuning 的区别？**
    
    - 虽然形式上都像是在输入前加 Token，但 MemoryLLM 的 Token 是：
        
        1. **动态的**（随内容实时更新）。
            
        2. **海量的**（10亿参数规模）。
            
        3. **深度集成的**（每一层都有，参与深层计算）。