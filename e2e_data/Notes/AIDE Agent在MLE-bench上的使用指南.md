---
tags:
  - note
  - SwarmEvo
  - Agent
  - AI部署
  - 开源项目
creation date: 2025-10-28
modification date: 2025-10-28
owner: area/Agent
---
# AIDE Agent在MLE-bench上的使用指南

## 概述

AIDE (AI-Driven Exploration in the Space of Code) 是由 WecoAI 开发的机器学习工程自动化 Agent，采用树搜索算法来自主地编写、调试和优化代码。在 [[MLE-bench评估框架]] 的评估中，AIDE 表现出色，o1-preview + AIDE 组合在 16.9% 的竞赛中获得奖牌，使用 pass@8 策略时该比例可提升至 34.1%，相比最佳线性代理（OpenHands）多获得 4 倍奖牌。

## 系统要求

在开始使用 AIDE Agent 之前，需要确保系统满足以下要求：

**Docker 环境**：必须安装 Docker 作为容器运行环境，这是运行 AIDE Agent 的基础设施。

**Sysbox 运行时**（推荐）：提供增强的容器隔离能力，确保 Agent 运行的安全性。虽然不是强制要求，但强烈建议在生产环境中使用。

**GPU 支持**（可选）：如果需要使用 GPU 加速训练过程，需要安装 NVIDIA Container Toolkit。对于计算密集型任务，GPU 支持可以显著提升性能。

**存储空间**：根据选择的数据集版本，至少需要 158GB（Lite 版）到 3.3TB（完整版）的可用存储空间。

## 环境准备

### MLE-bench 基础环境

首先需要完成 [[MLE-bench评估框架]] 的基础设置，包括克隆仓库、安装依赖和配置 Kaggle 凭证：

```bash
# 克隆 MLE-bench 仓库
git clone https://github.com/openai/mle-bench.git
cd mle-bench

# 安装 Git LFS 支持大文件
git lfs fetch --all
git lfs pull

# 安装 MLE-bench
pip install -e .

# 配置 Kaggle API 凭证
mkdir -p ~/.kaggle
cp /path/to/kaggle.json ~/.kaggle/
chmod 600 ~/.kaggle/kaggle.json

# 准备数据集（推荐 Lite 版）
mlebench prepare --lite
```

### AIDE Agent 安装

AIDE Agent 可以通过 pip 直接安装，也可以从源码安装用于开发：

```bash
# 方式1：通过 pip 安装（推荐）
pip install -U aideml

# 方式2：从源码安装（用于开发和定制）
git clone https://github.com/WecoAI/aideml.git
cd aideml && pip install -e .
```

### LLM API 配置

AIDE 需要配置 LLM API 才能正常工作。根据使用的模型提供商，设置相应的环境变量：

```bash
# OpenAI API
export OPENAI_API_KEY=<your-openai-key>

# Anthropic Claude API
export ANTHROPIC_API_KEY=<your-anthropic-key>

# Google Gemini API
export GOOGLE_API_KEY=<your-google-key>

# 使用本地模型（如 Ollama）
export OPENAI_BASE_URL="http://localhost:11434/v1"
export OPENAI_API_KEY="dummy"  # 本地模型可以使用任意值
```

### Docker 镜像构建

在 MLE-bench 中使用 AIDE 需要构建专门的 Docker 镜像。这个过程会将 AIDE Agent 打包到容器中，确保运行环境的一致性：

```bash
# 设置环境变量
export SUBMISSION_DIR=/home/submission
export LOGS_DIR=/home/logs
export CODE_DIR=/home/code
export AGENT_DIR=/home/agent

# 构建 AIDE Docker 镜像
docker build --platform=linux/amd64 -t aide agents/aide/ \
  --build-arg SUBMISSION_DIR=$SUBMISSION_DIR \
  --build-arg LOGS_DIR=$LOGS_DIR \
  --build-arg CODE_DIR=$CODE_DIR \
  --build-arg AGENT_DIR=$AGENT_DIR
```

构建过程可能需要几分钟时间，取决于网络速度和系统性能。

## 运行 AIDE Agent

### 单竞赛测试

对于初次使用或快速验证，可以先在单个竞赛上测试 AIDE Agent：

```bash
# 在单个竞赛上运行
python run_agent.py --agent-id aide \
  --competition-set experiments/splits/spaceship-titanic.txt
```

这个命令会在 Spaceship Titanic 竞赛上运行 AIDE Agent，这是一个相对简单的入门竞赛。

### 批量竞赛评估

完成单竞赛测试后，可以在 Lite 数据集的所有 22 个竞赛上运行完整评估：

```bash
# 在 Lite 数据集上运行
python run_agent.py --agent-id aide \
  --competition-set experiments/splits/lite.txt
```

对于更全面的评估，可以使用完整的 75 个竞赛集合：

```bash
# 在完整数据集上运行
python run_agent.py --agent-id aide \
  --competition-set experiments/splits/all.txt
```

### 自定义配置

可以通过自定义配置文件来调整 AIDE 的运行参数，例如启用 GPU 支持、调整资源限制等：

```bash
# 使用自定义配置
python run_agent.py --agent-id aide \
  --competition-set experiments/splits/lite.txt \
  --container-config path/to/custom_config.json
```

在 `custom_config.json` 中，可以设置 GPU 支持（`"gpus": -1` 表示使用所有可用 GPU）、内存限制、超时时间等参数。

### 多种子评估

为了获得可靠的评估结果，建议使用不同的随机种子运行多次实验：

```bash
# 运行 3 次实验（不同随机种子）
for seed in 1 2 3; do
  python run_agent.py --agent-id aide \
    --competition-set experiments/splits/lite.txt \
    --seed $seed
done
```

根据 MLE-bench 论文建议，至少应该使用 3 个不同的随机种子来评估 Agent 性能。

## 结果评估

### 生成提交文件

运行完成后，需要将 Agent 的输出转换为标准的提交格式：

```bash
python experiments/make_submission.py \
  --metadata runs/<run-group>/metadata.json \
  --output runs/<run-group>/submission.jsonl
```

这个命令会读取运行结果的元数据，生成符合 MLE-bench 评估标准的提交文件。

### 评分和分析

使用 MLE-bench 的评分工具对提交结果进行评估：

```bash
mlebench grade \
  --submission runs/<run-group>/submission.jsonl \
  --output-dir runs/<run-group>
```

评分工具会根据 Kaggle 竞赛的评估指标和奖牌标准，计算 Agent 的表现分数。

### 结果文件结构

运行完成后，在 `runs/<run-group>/` 目录下会生成完整的结果文件：

```
runs/<run-group>/
├── metadata.json              # 运行摘要和配置信息
├── submission.jsonl          # 标准提交文件
├── <competition-id>/         # 每个竞赛的详细结果
│   ├── logs/                 # Agent 执行日志
│   ├── code/                 # 生成的代码文件
│   ├── submission/           # 竞赛提交文件
│   ├── best_solution.py      # 最优解决方案代码
│   └── tree_plot.html        # 交互式解决方案树可视化
└── grading_results/          # 评分结果和分析
```

**tree_plot.html** 文件特别有价值，它可视化了 AIDE 的树搜索过程，展示了不同解决方案分支的探索路径和性能对比。
## 性能基准

根据 MLE-bench 论文的评估结果，AIDE Agent 展现了卓越的性能：

**奖牌获得率**：o1-preview + AIDE 在 16.9% 的竞赛中至少获得铜牌（pass@1），这一表现显著超越其他开源 Agent 框架。

**多次尝试提升**：使用 pass@8 策略（每个竞赛 8 次尝试），成功率可提升至 34.1%，翻了一倍。这表明 AIDE 的树搜索算法能够有效利用多次尝试来探索解决方案空间。

**相对优势**：AIDE 的树搜索方法相比最佳线性 Agent（OpenHands）多获得 4 倍奖牌，证明了树搜索策略在机器学习工程任务上的有效性。

**复杂度表现**：在 Low、Medium、High 三个复杂度级别的竞赛上都有良好表现，显示出较强的泛化能力。

## 评估标准和最佳实践

### 统计显著性

为确保评估结果的可靠性，应遵循以下最佳实践：

**最少 3 个随机种子**：每个实验至少使用 3 个不同的随机种子重复运行，以减少随机性的影响。

**报告格式**：使用 "Any Medal (%) = 均值 ± 标准误差" 的格式报告结果，例如 "16.9% ± 2.1%"。

**复杂度分类**：提供跨 Low、Medium、High 和 All 四个复杂度级别的详细分数分解，以全面评估 Agent 在不同难度任务上的表现。

### 多次尝试策略

**pass@k 评估**：除了单次尝试（pass@1），还应评估多次尝试的性能（如 pass@3、pass@8），以了解 Agent 的探索能力上限。

**资源权衡**：虽然多次尝试可以显著提升成功率，但也会增加计算成本和时间开销。需要根据实际资源和时间约束来平衡。

### 日志和调试

**详细日志**：保留完整的 Agent 执行日志，包括生成的代码、中间结果、错误信息等，便于后续分析和调试。

**失败分析**：对未获得奖牌的竞赛进行深入分析，识别 Agent 的弱点和改进方向。

**可视化审查**：利用 tree_plot.html 文件分析 Agent 的搜索策略，了解哪些分支被探索、哪些被剪枝。

## 相关资源

- **MLE-bench GitHub**：https://github.com/openai/mle-bench
- **AIDE GitHub**：https://github.com/WecoAI/aideml
- **AIDE PyPI**：https://pypi.org/project/aideml/
- **Weco AI 官网**：https://www.weco.ai/
- **MLE-bench 论文**：https://arxiv.org/abs/2410.07095
- **AIDE 技术报告**：https://www.weco.ai/blog/technical-report

## 相关笔记

- [[MLE-bench评估框架]]
- [[Agent]]

