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
# Agent与MLE-bench交互的技术规范

## 概述

在 [[MLE-bench评估框架]] 中开发和部署 [[Agent]] 需要遵循一套标准化的技术规范。这套规范确保了不同 Agent 实现之间的互操作性,同时提供了统一的容器化运行环境和评估接口。本文档详细说明了 Agent 注册机制、Docker 镜像构建、容器配置、数据挂载、环境变量以及提交格式等核心技术要求,为开发者提供完整的实现指南。

MLE-bench 采用 Docker 容器技术来隔离 Agent 的运行环境,通过标准化的目录挂载和环境变量来传递竞赛数据和配置信息。Agent 系统无关的设计使得任何遵循本规范的 Agent 都可以无缝集成到评估流程中,这为 Agent 算法的创新和对比评估提供了坚实的技术基础。

## Agent 注册机制

### 配置类定义

MLE-bench 通过 `agents/registry.py` 中的 `Agent` 配置类来管理 Agent 的元信息。这个数据类封装了 Agent 的唯一标识、Docker 镜像名称、权限设置等关键配置:

```python
# agents/registry.py
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Agent:
    """Agent 配置"""
    id: str              # Agent 唯一标识,如 "my_agent"
    name: str            # Docker 镜像名称
    privileged: bool = False  # 是否需要特权容器
    entry_point: str = None   # 可选:自定义入口命令
```

在实际应用中,Agent 的注册通过调用 registry 的 `register_agent` 方法完成。这个注册过程将 Agent 的配置信息添加到全局注册表中,使得运行脚本能够通过 Agent ID 来查找和启动对应的容器:

```python
from agents.registry import registry

registry.register_agent(
    Agent(
        id="my_agent",
        name="my_agent",  # 对应 docker build -t my_agent
        privileged=False
    )
)
```

`privileged` 参数决定了容器是否需要特权模式运行。在大多数情况下,标准的非特权容器已足够,但如果 Agent 需要访问宿主机的特殊资源或执行需要高权限的操作,则可能需要启用特权模式。`entry_point` 参数允许自定义容器的启动命令,为不同的 Agent 实现提供了灵活性。

### 目录结构规范

MLE-bench 对 Agent 的目录结构有明确的约定,这确保了构建过程的一致性和可维护性:

```
mle-bench/
├── agents/
│   ├── my_agent/           # 你的 Agent 目录
│   │   ├── Dockerfile      # 必需:定义容器镜像
│   │   ├── main.py         # Agent 主程序入口
│   │   ├── requirements.txt # Python 依赖列表
│   │   └── config.yaml     # 可选:Agent 特定配置
│   ├── registry.py         # Agent 注册表
│   └── run.py              # 容器执行逻辑
```

每个 Agent 必须有自己的独立目录,目录名通常与 Agent ID 保持一致。`Dockerfile` 是必需的,它定义了 Agent 运行环境的完整镜像构建过程。`main.py` 作为 Agent 的入口程序,包含了 Agent 的核心逻辑实现。`requirements.txt` 列出了所有 Python 依赖,确保环境的可重现性。

## Dockerfile 规范

### 标准模板

Dockerfile 是定义 Agent 运行环境的核心文件,必须严格遵循 MLE-bench 的规范。标准模板确保了所有 Agent 都基于相同的基础环境,并按照统一的目录结构组织文件:

```dockerfile
# agents/my_agent/Dockerfile

# 1. 基础镜像:必须继承自 mlebench-env
FROM mlebench-env:latest

# 2. 接收 build args(目录约定)
ARG SUBMISSION_DIR=/home/submission
ARG LOGS_DIR=/home/logs
ARG CODE_DIR=/home/code
ARG AGENT_DIR=/home/agent

# 3. 设置环境变量
ENV SUBMISSION_DIR=${SUBMISSION_DIR}
ENV LOGS_DIR=${LOGS_DIR}
ENV CODE_DIR=${CODE_DIR}
ENV AGENT_DIR=${AGENT_DIR}

# 4. 创建必需的目录
RUN mkdir -p ${SUBMISSION_DIR} ${LOGS_DIR} ${CODE_DIR} ${AGENT_DIR}

# 5. 复制 Agent 代码
COPY . ${AGENT_DIR}/
WORKDIR ${AGENT_DIR}

# 6. 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 7. 设置工作目录(重要!)
WORKDIR /home

# 8. 入口命令(可选,也可以在 run.py 中动态指定)
# CMD ["python", "/home/agent/main.py"]
```

这个模板的每个步骤都有其特定的目的。首先,所有 Agent 必须基于 `mlebench-env` 基础镜像构建,这个镜像包含了运行机器学习任务所需的常用库和工具。其次,通过 build args 传递标准化的目录路径,确保所有 Agent 使用一致的文件组织方式。第三,将这些目录路径设置为环境变量,使得 Agent 代码可以方便地访问。第四步创建这些必需的目录结构。

特别需要注意的是第 7 步,必须将工作目录设置为 `/home`,而不是 `/home/agent`。这是因为容器运行时会挂载竞赛数据到 `/home` 下的各个子目录,如果工作目录设置错误,Agent 可能无法正确访问数据文件。

### 构建命令

构建 Docker 镜像时需要传递正确的 build args,以确保目录结构与运行时环境一致:

```bash
# 设置环境变量
export SUBMISSION_DIR=/home/submission
export LOGS_DIR=/home/logs
export CODE_DIR=/home/code
export AGENT_DIR=/home/agent

# 构建镜像
docker build --platform=linux/amd64 -t my_agent agents/my_agent/ \
  --build-arg SUBMISSION_DIR=$SUBMISSION_DIR \
  --build-arg LOGS_DIR=$LOGS_DIR \
  --build-arg CODE_DIR=$CODE_DIR \
  --build-arg AGENT_DIR=$AGENT_DIR
```

`--platform=linux/amd64` 参数确保镜像在不同架构的机器上都能正常运行,特别是在 Apple Silicon (ARM64) 机器上开发但需要在 x86_64 服务器上运行的情况。通过 `-t` 参数指定的镜像名称应该与 Agent 注册时的 `name` 字段保持一致。

## 容器配置规范

### 默认配置

MLE-bench 提供了默认的容器配置文件 `environment/config/container_configs/default.json`,定义了容器运行时的资源限制和运行参数:

```json
{
  "mem_limit": "32g",           // 内存限制
  "memswap_limit": "32g",       // 交换内存限制
  "cpu_count": 8,               // CPU 核心数
  "shm_size": "16g",            // 共享内存
  "runtime": "sysbox-runc",     // 推荐使用 sysbox 运行时
  "network_mode": "bridge",     // 网络模式
  "detach": true,               // 后台运行
  "auto_remove": false,         // 不自动删除容器
  "environment": {
    "PYTHONUNBUFFERED": "1"     // Python 无缓冲输出
  },
  "gpus": null                  // GPU 配置,设置 -1 使用所有 GPU
}
```

这些配置参数需要根据实际硬件资源和任务需求进行调整。内存限制应该足够支持模型训练,但也不能过大导致系统资源耗尽。CPU 核心数影响并行计算的效率。共享内存 (`shm_size`) 对于使用 PyTorch DataLoader 等需要进程间共享数据的场景特别重要,设置过小可能导致 "bus error" 错误。

推荐使用 Sysbox 运行时而非默认的 runc,因为 Sysbox 提供了更好的容器隔离性和安全性,允许在容器内运行 Docker 等嵌套容器,这对某些复杂的 Agent 实现很有用。`PYTHONUNBUFFERED=1` 确保 Python 程序的输出能够实时显示,便于监控 Agent 的运行状态。

### GPU 配置

对于需要 GPU 加速的 Agent,可以使用专门的 GPU 配置文件:

```json
// environment/config/container_configs/gpu.json
{
  "mem_limit": "64g",
  "gpus": -1,                   // 使用所有可用 GPU
  "runtime": "nvidia",          // 注意:使用 GPU 时不能用 sysbox
  // ... 其他配置
}
```

需要注意的是,使用 GPU 时不能同时使用 Sysbox 运行时,必须改用 NVIDIA 运行时。`gpus` 参数设置为 `-1` 表示使用所有可用的 GPU,也可以指定具体的 GPU ID 列表,如 `"0,1"` 表示使用前两块 GPU。GPU 配置还需要确保宿主机已正确安装 NVIDIA Container Toolkit。

## 容器挂载卷规范

### 挂载点配置

容器通过 Docker volumes 将宿主机上的竞赛数据和输出目录挂载到容器内部。`agents/run.py` 中定义了标准的挂载配置:

```python
def run_in_container(
    client: docker.DockerClient,
    competition: Competition,
    agent: Agent,
    run_dir: Path,
    ...
):
    # 1. 竞赛数据(只读)
    data_mounts = {
        str(competition.data_dir / "prepared"): {
            "bind": "/data",
            "mode": "ro"  # 只读!Agent 不能修改
        }
    }

    # 2. 竞赛描述(只读)
    description_mounts = {
        str(competition.data_dir / "description.md"): {
            "bind": "/home/description.md",
            "mode": "ro"
        }
    }

    # 3. 输出目录(读写)
    output_mounts = {
        str(run_dir / "submission"): {
            "bind": "/home/submission",
            "mode": "rw"
        },
        str(run_dir / "logs"): {
            "bind": "/home/logs",
            "mode": "rw"
        },
        str(run_dir / "code"): {
            "bind": "/home/code",
            "mode": "rw"
        }
    }

    # 4. 合并所有挂载
    volumes = {**data_mounts, **description_mounts, **output_mounts}

    # 5. 创建容器
    container = client.containers.create(
        image=agent.name,
        volumes=volumes,
        working_dir="/home",
        **container_config
    )
```

这个挂载配置体现了 MLE-bench 的安全性设计。竞赛数据以只读模式挂载,确保 Agent 不会意外修改原始数据,保证了评估的公平性和可重复性。竞赛描述文件也是只读的,它包含了任务说明、数据格式、评估指标等重要信息。只有输出目录是可写的,Agent 必须将生成的提交文件、日志和代码保存到这些指定位置。

### 容器内部视图

从 Agent 容器内部看到的目录结构如下:

```bash
/home/                        # 工作目录
├── description.md            # 竞赛描述(只读)
├── /data/                    # 竞赛数据(只读)
│   ├── train.csv
│   ├── test.csv
│   └── sample_submission.csv
├── /submission/              # 提交输出(读写)
│   └── submission.csv        # Agent 必须生成这个文件
├── /logs/                    # 日志输出(读写)
│   └── agent.log
└── /code/                    # 代码输出(读写)
    └── solution.py

/home/agent/                  # Agent 自己的代码
└── main.py
```


Agent 程序应该从 `/data` 目录读取训练和测试数据,读取 `/home/description.md` 了解任务要求,然后将预测结果写入 `/home/submission/submission.csv`。日志和生成的代码可以分别保存到 `/logs` 和 `/code` 目录,便于后续分析。

## 环境变量规范

### 系统提供的环境变量

MLE-bench 在启动容器时会设置一系列环境变量,Agent 可以通过这些变量获取必要的配置信息:

```python
environment = {
    # 基础信息
    "COMPETITION_ID": "spaceship-titanic",
    "SUBMISSION_DIR": "/home/submission",
    "LOGS_DIR": "/home/logs",
    "CODE_DIR": "/home/code",

    # 数据路径
    "DATA_DIR": "/data",
    "DESCRIPTION_PATH": "/home/description.md",

    # Agent 需要自己设置的(通过 .env 或命令行)
    "OPENAI_API_KEY": "sk-...",
    "ANTHROPIC_API_KEY": "sk-ant-...",

    # Python 配置
    "PYTHONUNBUFFERED": "1",
    "PYTHONPATH": "/home/agent"
}
```

`COMPETITION_ID` 环境变量标识了当前运行的竞赛,Agent 可以根据这个 ID 来调整策略或加载特定的配置。路径相关的环境变量告诉 Agent 应该从哪里读取数据、写入输出。API key 等敏感信息需要由用户通过 `.env` 文件或命令行参数提供,不应该硬编码在代码或 Dockerfile 中。

### Agent 代码中读取环境变量

在 Agent 的主程序中,应该通过 `os.getenv` 来读取这些配置:

```python
import os

# 读取竞赛信息
competition_id = os.getenv("COMPETITION_ID")
data_dir = os.getenv("DATA_DIR", "/data")
description_path = os.getenv("DESCRIPTION_PATH", "/home/description.md")

# 读取输出路径
submission_dir = os.getenv("SUBMISSION_DIR", "/home/submission")
logs_dir = os.getenv("LOGS_DIR", "/home/logs")
code_dir = os.getenv("CODE_DIR", "/home/code")

# 读取 API Key
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY not set!")
```

使用 `os.getenv` 的第二个参数可以提供默认值,这样当环境变量未设置时,代码也能正常运行。对于必需的配置如 API key,应该在启动时就进行检查,如果缺失则立即抛出异常,避免运行到中途才发现问题。

## 提交格式规范

### 提交文件要求

Agent 生成的提交文件必须满足严格的格式要求,才能被 MLE-bench 的评分系统正确处理:

```python
# Agent 必须生成 /home/submission/submission.csv
# 示例:二分类问题
"""
PassengerId,Transported
0013_01,True
0018_01,False
0019_01,True
...
"""
```

关键要求包括:文件必须是标准的 CSV 格式,列名必须与竞赛提供的 `sample_submission.csv` 完全一致,行数必须与测试集 `test.csv` 的行数相同,不能包含任何缺失值。这些要求确保了提交文件能够被自动化评分系统正确解析和评估。

### 提交验证函数

可以使用以下验证函数来检查提交文件的格式:

```python
import pandas as pd

def validate_submission(submission_path, sample_path):
    """验证提交文件格式"""
    submission = pd.read_csv(submission_path)
    sample = pd.read_csv(sample_path)

    # 检查列名
    assert list(submission.columns) == list(sample.columns), \
        f"列名不匹配: {submission.columns} vs {sample.columns}"

    # 检查行数
    assert len(submission) == len(sample), \
        f"行数不匹配: {len(submission)} vs {len(sample)}"

    # 检查缺失值
    assert not submission.isnull().any().any(), \
        "提交文件包含缺失值"

    print("✅ 提交文件验证通过")
```

建议 Agent 在生成提交文件后立即调用这个验证函数,确保格式正确。如果验证失败,Agent 应该尝试修复问题或者输出详细的错误信息,帮助诊断问题。

### 本地评分服务器

MLE-bench 提供了一个本地的 grading server,Agent 可以在容器内调用它来验证提交格式和获取初步的评分结果:

```python
import requests

def check_submission_format(submission_path):
    """调用本地评分服务器验证格式"""
    response = requests.post(
        "http://localhost:5000/validate",
        files={"submission": open(submission_path, "rb")}
    )
    return response.json()
```

这个本地服务器在开发和调试阶段特别有用,可以快速验证 Agent 的输出是否符合要求,而不需要等待完整的评估流程结束。

## Agent 主程序实现

### 最小化实现示例

以下是一个完整的 Agent 主程序示例,展示了如何按照规范实现一个基本的 Agent:

```python
# agents/my_agent/main.py
import os
import pandas as pd
from pathlib import Path

def main():
    # 1. 读取环境变量
    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    submission_dir = Path(os.getenv("SUBMISSION_DIR", "/home/submission"))
    logs_dir = Path(os.getenv("LOGS_DIR", "/home/logs"))

    # 2. 设置日志
    log_file = logs_dir / "agent.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # 3. 读取数据
    train = pd.read_csv(data_dir / "train.csv")
    test = pd.read_csv(data_dir / "test.csv")
    sample = pd.read_csv(data_dir / "sample_submission.csv")

    print(f"Train shape: {train.shape}")
    print(f"Test shape: {test.shape}")

    # 4. 训练模型(你的核心逻辑)
    # ... 这里实现你的 Agent 逻辑
    predictions = train_and_predict(train, test)

    # 5. 生成提交文件
    submission = sample.copy()
    submission.iloc[:, 1:] = predictions  # 更新预测列
    submission_path = submission_dir / "submission.csv"
    submission.to_csv(submission_path, index=False)

    print(f"✅ Submission saved to {submission_path}")

if __name__ == "__main__":
    main()
```

这个示例展示了一个标准的 Agent 实现流程:首先读取环境变量获取路径配置,然后设置日志记录,接着加载训练和测试数据,执行核心的机器学习逻辑,最后生成并保存提交文件。实际的 Agent 实现会在 `train_and_predict` 函数中包含更复杂的逻辑,如特征工程、模型选择、超参数优化等。

## 实践建议

在实际开发 Agent 时,建议遵循以下最佳实践:

**完整的日志记录**:将 Agent 的运行日志详细记录到 `/home/logs/agent.log`,包括数据加载、特征工程、模型训练、预测生成等各个阶段的信息,这对于调试和分析非常重要。

**代码保存**:将生成的代码保存到 `/home/code` 目录,这不仅便于后续审查和复现,也是 MLE-bench 评估框架的要求之一。特别是对于像 [[AIDE Agent在MLE-bench上的使用指南]] 中描述的那种通过代码生成来解决问题的 Agent,代码保存更是核心功能。

**错误处理**:实现健壮的错误处理机制,当遇到异常时应该记录详细的错误信息,并尝试生成一个合法的提交文件(即使是基于简单启发式的结果),避免因异常导致整个评估流程失败。

**资源管理**:注意内存和磁盘使用,避免加载过大的数据到内存或生成过多的中间文件。可以使用分块处理、增量学习等技术来控制资源消耗。

**时间监控**:MLE-bench 对每个竞赛有运行时间限制,Agent 应该监控自己的运行时间,在接近限制时采取应对措施,如停止继续搜索、使用当前最佳结果生成提交等。

## 相关资源

- [[MLE-bench评估框架]] - MLE-bench 的整体介绍和快速开始指南
- [[AIDE Agent在MLE-bench上的使用指南]] - AIDE Agent 的完整使用教程
- [[Agent]] - Agent 技术的理论基础和应用场景
- MLE-bench GitHub: https://github.com/openai/mle-bench
- Docker 官方文档: https://docs.docker.com
- Sysbox 运行时: https://github.com/nestybox/sysbox

