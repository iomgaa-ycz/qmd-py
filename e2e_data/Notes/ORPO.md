---
tags:
  - note
  - 语言模型
  - 强化学习
creation date: 2025-08-19 17:57
modification date: Tuesday 19th August 2025 17:57:20
owner: area/强化学习
---
一系列类 [[DPO算法]] 的方法已经将 RLHF 的训练成本从 4 个模型砍到 2 个.然而不管是哪种 DPO，除了 policy model 外，都还有一个 reference model，我们能不能把 ref_model 也干掉。

回想一下，在 [[DPOP]] 中，我们使用 ref_model 来保证模型在 chosen 上的概率不要过低，如果只是为了保证模型能够拟合 chosen 答案，那我们是不是直接把 chosen 答案拿出来做 SFT 就好，这不就不需要 ref_model 来吗？

ORPO的目标函数一共由两部分组成（SFT Loss + Odds Ratio Loss）：

![[Pasted image 20250819180116.png]]

其中 SFT Loss 就是拿 chosen 答案算 CrossEntropy Loss，这很好理解，剩下的就是这个 Odds Ratio 是什么。在统计学和概率论中，odds 指的是「某事件发生与不发生的比例」，比如，如果一件事情发生的概率是 $p$ ，那么它不发生的概率就是 $1-p$ ，其 odds 计算公式就为：

$$
\operatorname{odds}_\theta(y \mid x)=\frac{P_\theta(y \mid x)}{1-P_\theta(y \mid x)}
$$
当一件事情的发生概率越大，其对应的 odds 值就越大。知道 odds 的概念后，我们再一起上述 loss function 的后半部分 $L_{O R}$ 的定义：

$$
\mathcal{L}_{O R}=-\log \sigma\left(\log \frac{\operatorname{odds}_\theta\left(y_w \mid x\right)}{\operatorname{odds}_\theta\left(y_l \mid x\right)}\right)
$$

通过 minimize 这个 loss 值，我们就需要 maximize 括号内的值，**也就是尽可能的让「好句子」发生的概率增大，「坏句子」发生的概率减小**。由此可见，**ORPO 通过定义了一个神奇的 odds 值来提升好样本的概率，降低坏样本的概率，并通过一个 SFT loss 来保证模型对 chosen response 的基本拟合**。
