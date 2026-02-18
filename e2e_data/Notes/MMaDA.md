---
tags:
  - note
  - DLA
  - 多模态
  - 语言模型
creation date: 2025-08-18
modification date: 2025-08-18
owner: area/扩散大语言模型
---
# MMaDA（多模态大扩散语言模型）

**核心概念**：MMaDA是首个系统性探索扩散架构的多模态基础模型，通过统一的扩散框架实现文本推理、多模态理解与图像生成的统一建模。
![](https://pica.zhimg.com/v2-3ea3b3eef5c129050f1b601183293c9a_1440w.jpg)

## 主要突破

### 问题背景
- 传统多模态大模型基于自回归架构，文本与图像生成过程分离
- 跨模态协同效率低下，后训练阶段难以优化复杂推理任务
- 现有统一理解与生成模型都不支持文本的强推理能力

### 核心创新：三项技术突破

#### 1. 统一扩散架构（Unified Diffusion Architecture）
**简化解释**：将文本和图像的生成过程统一到同一个扩散框架中

**具体实现**：
- **数据表征统一**：文本使用LLaMA Tokenizer，图像采用MAGVIT-v2 Tokenizer（512×512图像转化为1024个离散Token）
- **扩散目标统一**：定义统一掩码预测损失函数，通过随机掩码同步优化文本与图像的语义恢复能力
	$$
\mathcal{L}_{\text {unify }}(\theta)=-\mathbb{E}_{t, x_0, x_t}\left[\frac{1}{t} \sum_{i=1}^L \mathbf{I}\left[x_t^i=[\mathrm{MASK}]\right] \log p_\theta\left(x_0^i \mid x_t\right)\right]
$$
- **架构优势**：消除传统混合架构（AR+Diffusion）的复杂性，实现底层跨模态信息交互

#### 2. 混合长链思维微调（Mixed Long-CoT Finetuning）
**简化解释**：让模型在生成答案前先进行跨模态推理

**具体实现**：
- **统一推理格式**：定义特殊标记结构`<think>推理过程</think>`
- **跨模态推理**：处理几何问题时先解析图形关系，再进行数值计算
- **数据增强**：利用LLM/VLM生成高质量推理轨迹，通过验证器筛选逻辑严谨样本

#### 3. 统一策略梯度优化（UniGRPO算法）
**简化解释**：专门为扩散模型设计的强化学习优化方法

**解决的问题**：
- 局部掩码依赖
- 掩码比例敏感性
- 非自回归特性

**创新方案**：
- **结构化噪声策略**：对答案部分随机采样掩码比例（30%-70%），保留问题部分完整
	$$
\begin{gathered}
\mathcal{J}_{\mathrm{UniGRPO}}(\theta)=\mathbb{E}_{(q, a) \sim \mathcal{D},\left\{o_i\right\}_{i=1}^G \sim \pi_{\theta_{\mathrm{old}}}(\cdot \mid q),\left\{p_i \in[0,1]\right\}_{i=1}^G}\left[\frac { 1 } { G } \sum _ { i = 1 } ^ { G } \frac { 1 } { | o _ { i } | } \sum _ { t = 1 } ^ { | o _ { i } | } \left(\operatorname { m i n } \left(r_{i, t}^{\prime}(\theta) \hat{A}_{i, t},\right.\right.\right. \\
\left.\left.\left.\operatorname{clip}\left(r_{i, t}^{\prime}(\theta), 1-\varepsilon, 1+\varepsilon\right) \hat{A}_{i, t}\right)-\beta D_{\mathrm{KL}}\left(\pi_\theta^{\prime} \| \pi_{\mathrm{ref}}^{\prime}\right)\right)\right],
\end{gathered}
$$
- **多样化奖励建模**：针对不同任务设计复合奖励函数（如图像生成中CLIP Reward + Image Reward）
	![](https://pic4.zhimg.com/v2-b2d730adaf9230ca8c83bf31810b3d15_1440w.jpg)
## 性能表现

### SOTA性能表现
- **文本推理**：MMLU准确率68.4%，超越LLaMA-3-8B、Qwen2-7B
- **多模态理解**：POPE（86.1 vs 85.9）、VQAv2（76.7 vs 78.5）与专用模型持平
- **图像生成**：CLIP Score达32.46，较SDXL、Janus提升显著，文化知识生成任务准确率提升56%

### 关键优势：跨任务协同效应
在混合训练阶段（130K-200K步），文本推理与图像生成指标**同步上升**，证明了统一架构的多任务协同效应。
![](https://picx.zhimg.com/v2-992ca8265bc03c10f081b9ce36f04427_1440w.jpg)

## 任务泛化能力

扩散模型的独特优势：无需额外微调即可泛化到补全任务
- **文本补全**：预测文本序列中的缺失片段
- **视觉问答补全**：基于不完整图文输入生成完整答案  
- **图像补全**：根据局部视觉提示重建完整图像
![](https://pic3.zhimg.com/v2-e7808277f30c3447eeb60a6e202f460a_1440w.jpg)

## 技术意义

1. **首次实现真正统一**：在多模态任务中保持文本强推理能力的统一基座模型
2. **架构突破**：证明了扩散模型在文本建模领域的潜力
3. **协同效应验证**：文本建模能力提升直接改善图像生成的事实一致性

## 原始资料来源

- 作者：机器之心
- 链接：https://zhuanlan.zhihu.com/p/1908950492756804744
- 来源：知乎
- 论文：MMaDA: Multimodal Large Diffusion Language Models
- 论文链接：https://arxiv.org/abs/2505.15809
- 代码仓库：https://github.com/Gen-Verse/MMaDA

## 相关领域
- [[扩散大语言模型]]
