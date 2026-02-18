---
tags:
  - note
  - 强化学习
  - 语言模型
creation date: 2025-08-19 17:49
modification date: Tuesday 19th August 2025 17:49:53
owner: area/强化学习
---
DPO思路很直觉：对于同一个 propmt，给定一个好的回答 $y_w$ 和一个不好的回答 $y_l$ ，通过降低不好回答被采样的概率，提升好回答的概率，从而进行模型训练。这个数据和训练 Reward Model 的 pair 数据格式完全一致，都是同一个 prompt 对应两个不同质量的 responses。
$$
\mathcal{L}_{\mathrm{DPO}}\left(\pi_\theta ; \pi_{\mathrm{ref}}\right)=-\mathbb{E}_{\left(x, y_w, y_l\right) \sim \mathcal{D}}\left[\log \sigma\left(\beta \log \frac{\pi_\theta\left(y_w \mid x\right)}{\pi_{\mathrm{ref}}\left(y_w \mid x\right)}-\beta \log \frac{\pi_\theta\left(y_l \mid x\right)}{\pi_{\mathrm{ref}}\left(y_l \mid x\right)}\right)\right]
$$
