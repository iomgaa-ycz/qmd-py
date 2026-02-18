---
tags:
  - note
  - 强化学习
  - 语言模型
creation date: 2025-08-19 16:17
modification date: Tuesday 19th August 2025 16:17:17
owner: area/强化学习
---
强化学习中，我们有一个Agent作为我们的智能体，它根据策略 $\pi$ ，在不同的环境状态 s 下选择相应的动作来执行，环境根据Agent的动作，反馈新的状态以及奖励，Agent又根据新的状态选择新的动作，这样不停的循环，知道游戏结束，便完成了eposide。在深度强化学习中，策略 $\pi$ 是由神经网络构成，神经网络的参数为 $\theta$ ，表示成 $\pi_\theta$ 。
![[Pasted image 20250819161817.png]]
一个完整的eposide序列，用 $\tau$ 来表示。而一个特定的 $\tau$ 序列发生的概率为：
$$
\begin{aligned}
& p_\theta(\tau) \\
& \quad=p\left(s_1\right) p_\theta\left(a_1 \mid s_1\right) p\left(s_2 \mid s_1, a_1\right) p_\theta\left(a_2 \mid s_2\right) p\left(s_3 \mid s_2, a_2\right) \cdots \\
& \quad=p\left(s_1\right) \prod_{t=1}^T p_\theta\left(a_t \mid s_t\right) p\left(s_{t+1} \mid s_t, a_t\right)
\end{aligned}
$$
对于一个完整的 $\tau$ 序列，他在整个游戏期间获得的总的奖励用 $R(\tau)$ 来表示。对于给定参数 $\theta$ 的策略，我们评估其应该获得的每局中的总奖励是：对每个采样得到的的 $\tau$ 序列（即每一局）的加权和，即：
$$
\bar{R}_\theta=\sum_\tau R(\tau) p_\theta(\tau)=E_{\tau \sim p_\theta(\tau)}[R(\tau)]
$$
因此，对于一个游戏，我们自然希望通过调整策略参数 $\theta$ ，得到的 $\bar{R}_\theta$ 越大越好，因为这意味着，我们选用的策略参数能平均获得更多奖励。这个形式自然就很熟悉了。调整 $\theta$ ，获取更大的 $\bar{R}_\theta$ ，这个很自然的就想到梯度下降 + 的方式来求解。于是用期望的每局奖励对 $\theta$ 求导：
![[Pasted image 20250819161943.png]]
在这个过程中，第一个等号是梯度的变换；第二三个等号是利用了log函数的特性；第四个等号将求和转化成期望的形式；期望又可以由我们采集到的数据序列进行近似；最后一个等号是将每一个数据序列展开成每个数据点上的形式：
$$
\begin{gathered}
\nabla \bar{R}_\theta=\frac{1}{N} \sum_{n=1}^N \sum_{t=1}^{T_n} R\left(\tau^n\right) \nabla \log p_\theta\left(a_t^n \mid s_t^n\right) \\
=\frac{1}{N} \sum_{n=1}^N R\left(\tau^n\right)\left[\sum_{t=1}^{T_n} \nabla \log p_\theta\left(a_t^n \mid s_t^n\right)\right]
\end{gathered}
$$
之所以把 $R$ 提出来，因为这样理解起来会更直观一点。形象的解释这个式子就是：每一条采样到的数据序列都会希望 $\theta$ 的向着自己的方向进行更新，总体上，我们希望更加靠近奖励比较大的那条序列（效果好的话语权自然要大一点嘛），因此用每条序列的奖励来加权平均他们的更新方向。比如我们假设第三条数据的奖励很大，通过上述公式更新后的策略，使得 $p_\theta\left(a_t^3 \mid s_t^3\right)$ 发生的概率更大，以后再遇到 $s_t^3$ 这个状态时，我们就更倾向于采取 $a_t^3$ 这个动作，或者说以后遇到的状态和第三条序列中的状态相同时，我们更倾向于采取第三条序列曾经所采用过的策略。具体的算法伪代码是：
![[Pasted image 20250819163825.png]]
以上，就构成了梯度和采集到的数据序列的近似关系。有了梯度方向和采集的数据序列的关系，一个完整的PG方法就可以表示成：
![[Pasted image 20250819163843.png]]
为了让PG算法的效果更好，我们还可以使用一下几个Tips
1. [[奖励基线]]
2. [[折扣因子]]
3. [[优势函数]]