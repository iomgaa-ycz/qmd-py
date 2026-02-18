---
tags:
  - note
  - 强化学习
  - Agent
  - 语言模型
creation date: 2025-01-19
modification date: 2025-01-19
owner: area/强化学习
---
# GiGPO分组内分组策略优化算法

GiGPO通过创新的两层优势估计结构，解决了长视距LLM智能体训练中的细粒度信贷分配问题，在保持group-based强化学习优势的同时实现了显著性能提升。

## 问题背景

现有基于分组的强化学习算法（如GRPO、RLOO）在单步任务中表现优异，但在长视距LLM智能体训练中面临严重挑战。长视距任务的特点包括：奖励稀疏或延迟、个体步骤间信贷分配复杂、传统方法将步骤级别差异折叠从而削弱有效性。

传统group-based方法在长视距场景中的局限性在于，它们将整个轨迹视为一个整体进行优势估计，无法为个别步骤提供精确的反馈信号。这种粗粒度的信贷分配在面对可能包含50个步骤、超过20k tokens的复杂任务时显得力不从心。

GiGPO的核心创新是引入了**分组内分组**的两层优势估计结构：
![[CleanShot 2025-08-19 at 12.11.19@2x.png]]
图1：长时程LLM代理训练的比较。左：Vanilla GRPO展开一组完整轨迹并计算回合级优势。中：通过额外的每状态展开构建步骤级组（例如 $a_4^{\prime} a_4^{\prime \prime} a_4^{\prime \prime \prime} \ldots$ ），，能够实现细粒度反馈，但会产生过高的计算成本。右：GiGPO通过聚合来自相同环境状态 $\tilde{s}$ 轨迹中的不同动作（ $a^{\prime}, a^{\prime \prime}, a^{\prime \prime \prime}, a^{\prime \prime \prime \prime}$ ）高效地实现了细粒度信用分配。

## 算法核心机制

GiGPO的核心创新是引入了**分组内分组**的两层优势估计结构：
![[CleanShot 2025-08-19 at 12.14.37@2x.png]]
图2：GiGPO概述。智能体与环境组（初始状态相同）交互，生成轨迹集 $\left\{\boldsymbol{\tau}_i\right\}_{i=1^{\circ}}^N$ 具有相同颜色的状态表示相同的环境状态。GiGPO执行二维组计算（回合级 $A^E$ 和步级 $A^S$ ），以生成分层相对优势，指导细粒度策略优化
### 层级1：序列级相对优势（Episode-Level）

序列级优势捕获轨迹的整体有效性，计算公式为：

$$
A^E\left(\boldsymbol{\tau}_i\right)=\frac{R\left(\boldsymbol{\tau}_i\right)-\operatorname{mean}\left(\left\{R\left(\boldsymbol{\tau}_j\right)\right\}_{j=1}^N\right)}{F_{\text {norm }}\left(\left\{R\left(\boldsymbol{\tau}_j\right)\right\}_{j=1}^N\right)}
$$

这一层级提供稳定的全局训练信号，鼓励策略发展连贯的、轨迹范围的行为以最大化整体任务性能。

### 层级2：步骤级相对优势（Step-Level）

步骤级优势通过**锚定状态分组机制**实现精细化信贷分配：

**锚定状态分组**：
- 识别轨迹间重复出现的环境状态作为"锚点"
- 构建步骤级分组：$G^S(\tilde{\boldsymbol{s}})=\left\{\left(\boldsymbol{a}_t^{(i)}, r_t^{(i)}\right) \mid \boldsymbol{s}_t^{(i)}=\tilde{\boldsymbol{s}}, 1 \leq i \leq N, 1 \leq t \leq \hat{T}\right\}$
- 利用相同状态下不同动作的自然对比

**优势计算**：
$$
A^S\left(\boldsymbol{a}_t^{(i)}\right)=\frac{R_t^{(i)}-\operatorname{mean}\left(\left\{R_t^{(j)} \mid\left(\boldsymbol{a}_t^{(j)}, R_t^{(j)}\right) \in G^S(\tilde{\boldsymbol{s}})\right\}\right)}{F_{\text {norm }}\left(\left\{R_t^{(j)} \mid\left(\boldsymbol{a}_t^{(j)}, R_t^{(j)}\right) \in G^S(\tilde{\boldsymbol{s}})\right\}\right)}
$$

**关键洞察**：在相同任务和初始条件下，多个轨迹会因无效动作或循环行为而遭遇相同状态（如重访网页、房间、游戏场景），这为步骤级分组提供了天然基础。

### 组合优势估计

最终的优势函数结合两个层级：
$$
A\left(\boldsymbol{a}_t^{(i)}\right)=A^E\left(\boldsymbol{\tau}_i\right)+\omega \cdot A^S\left(\boldsymbol{a}_t^{(i)}\right)
$$

其中ω为权重系数，平衡全局和局部信号。

## 实验验证

### 性能提升数据

**ALFWorld基准测试**：
- Qwen2.5-1.5B：86.1% vs GRPO的72.8%（+13.3%）
- Qwen2.5-7B：90.2% vs GRPO的77.6%（+12.6%）

**WebShop基准测试**：
- Qwen2.5-1.5B：67.4% vs GRPO的56.8%（+10.6%）
- Qwen2.5-7B：75.2% vs GRPO的66.1%（+9.1%）

### 消融研究发现

- 移除序列级优势：性能大幅下降，失去轨迹连贯性
- 移除步骤级优势：复杂任务性能显著下降
- 规范化因子Fₙₒᵣₘ=1提供更稳定的训练过程

### 计算效率

- 锚定状态分组：仅0.01s/迭代（HashMap操作）
- 步骤级优势计算：仅0.53s/迭代（简单算术运算）
- 总额外开销：<0.002%训练时间
- GPU内存使用：与GRPO完全相同

## 技术优势

**保持group-based RL核心优势**：
- ✅ 无批评器：避免额外价值网络复杂性
- ✅ 低内存：与GRPO相同资源需求  
- ✅ 稳定收敛：继承group-based方法的稳定性

**突破性改进**：
- 🎯 细粒度信贷分配：精确到步骤级别的动作评估
- 📈 显著性能提升：在复杂长视距任务中实现双位数改进
- 🔄 通用兼容性：与其他group-based技术正交兼容

**算法特性**：
- 完全离线构建：无需额外LLM推理开销
- 自动适应性：当无状态重复时自然退化为GRPO
- 扩展友好：支持与DAPO等技术集成

## 应用前景

GiGPO为长视距LLM智能体的实际应用奠定了重要技术基础。在具身智能、Web智能体、游戏AI和机器人控制等需要复杂多步推理和规划的场景中具有巨大潜力。算法的高效性和兼容性使其适合在大规模生产环境中部署。

未来发展方向包括：基于嵌入的状态相似性匹配以处理噪声状态、动态权重调整策略、以及向视觉-语言模型的扩展。这些改进将进一步提升算法在更复杂、更真实环境中的表现。

---

**原始资料来源**：
论文《Group-in-Group Policy Optimization for LLM Agent Training》- Lang Feng等，南洋理工大学&Skywork AI，2025年