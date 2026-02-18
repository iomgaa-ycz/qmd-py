---
tags:
  - inbox
  - note
creation date: 2025-12-05 13:57
modification date: Friday 5th December 2025 13:57:07
---
1. 多Agent还是单Agent
2. Prompt的强化学习




3. pipeline & 有向无环图
	1. pipeline：任务流水线
		1. base（基于上一个节点的方案进行创新）
		2. merge（基于前面多版的代码进行合并和修改）
		3. select（选择需要合并的节点）
		4. review（评价生成的代码）
		5. base-review/select-merge-review
	2. 有向无环图
		1. 可能多个节点都是其的父节点

代码结构）（基因）
- 数据 (Data): 预处理、增强策略 (Augmentation)、清洗。
- 模型结构 (Model): Backbone, Head, Attention机制等。
- 损失函数 (Loss Function): 决定优化的方向 (e.g., Focal Loss, Dice Loss)。
- 优化器与调度 (Optimizer & Scheduler): 决定优化的路径和速度。
- 正则化 (Regularization): Dropout, Weight Decay, Label Smoothing (防止过拟合)。
- 初始化 (Initialization): 权重的起始状态。
- 训练技巧 (Training Tricks): Gradient Clipping, Batch Size 策略等。

两种模式
- 直接基于最好的一版代码进行探索和优化
- 合并多个版本的好的设置进行融合

1. 更大的细粒度（七个基因）
2. 交换
	1. 结构本身
	2. 选择结构的经验