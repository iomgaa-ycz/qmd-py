---
tags:
  - note
  - 语言模型
  - 强化学习
creation date: 2025-08-19 17:54
modification date: 星期二 19日 八月 2025 17:54:01
aliases:
  - Token-level Direct Preference Optimization
owner: area/强化学习
---
在 [[PPO算法]]训练的时候，我们通常会加上 KL 惩罚来约束模型不要偏离 reference model 过远，但在 [[DPO算法]]的实现中却没有并没有添加这一项。TDPO提出了这一改进，在原来的 DPO loss 上新增了 kl 惩罚项：
![[Pasted image 20250819175515.png]]

不过，不同于 PPO 中使用 backward KL，**TDPO 则是使用 forward KL 来计算 KL 惩罚**，因为 KL 是一个非对称的距离函数，所谓 forward 和 backward 其意思就是「以 SFT 计算采样概率」还是「以 Policy Model 计算采样概率」。

由于 backward KL 的目标是拟合整个分布中的「一部分」，而 forward KL 的目标是尽可能 cover 整个分布中的大部分。因此，**TDPO 训练后的模型会比 PPO 训练后的模型，在输出多样性上更加自由**。

> **PS：**经过 PPO 后的模型基本一眼就能看出来，输出风格都非常一致，因为此时输出分布已经「聚集」到一个局部分布上了，reward 方差会比 SFT 小很多。


