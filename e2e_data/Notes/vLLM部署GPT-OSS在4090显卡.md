---
tags:
  - note
  - tech
  - AI部署
creation date: 2025-08-14
modification date: 2025-08-14
owner: area/开发工具
---
# vLLM部署GPT-OSS在4090显卡

**一句话总结**：使用vLLM框架在RTX 4090显卡上通过Docker容器化部署GPT-OSS-20B模型的完整流程。

## 部署步骤

### 步骤1：下载模型

使用Hugging Face CLI工具从镜像站点下载GPT-OSS-20B模型到本地目录：

```bash
HF_ENDPOINT=https://hf-mirror.com hf download openai/gpt-oss-20b --local-dir ./gpt-oss
```

**关键点**：
- `HF_ENDPOINT`：设置为镜像地址，加速下载
- `--local-dir`：指定模型下载到本地的存储路径

### 步骤2：Docker部署vLLM

使用Docker容器运行vLLM服务，配置GPU资源和环境参数：

```bash
docker run -d --gpus all \
  -v /home/pci/ycz/gpt-oss:/app/model \
  -p 8001:8000 \
  --ipc=host \
  --restart unless-stopped \
  --name vllm-gptoss-v2 \
  --env "HF_TOKEN=xxxxxxxxxxxx" \
  --env "VLLM_ATTENTION_BACKEND=TRITON_ATTN_VLLM_V1" \
  --env "TORCH_CUDA_ARCH_LIST=8.6" \
  vllm/vllm-openai:gptoss \
  --model /app/model \
  --served-model-name gpt-oss-20b \
  --gpu-memory-utilization 0.9
```

**参数解释**：
- `--gpus all`：使用所有可用GPU
- `-v`：挂载本地模型目录到容器内
- `-p 8001:8000`：端口映射，外部8001映射到容器内8000
- `--ipc=host`：使用主机IPC命名空间
- `--restart unless-stopped`：自动重启策略
- `HF_TOKEN`：Hugging Face访问令牌
- `VLLM_ATTENTION_BACKEND`：注意力机制后端配置为TRITON
- `TORCH_CUDA_ARCH_LIST=8.6`：CUDA架构版本（RTX 4090对应8.6）
- `--gpu-memory-utilization 0.9`：GPU内存使用率设为90%

### 步骤3：监控运行状态

查看Docker容器运行日志，实时监控vLLM服务状态：

```bash
docker logs -f vllm-gptoss
```

**作用**：
- `-f`：实时跟踪日志输出
- 用于排查问题和监控服务启动过程

## 核心概念简化

- **vLLM**：让大模型能在GPU上高效运行的推理引擎
- **Docker容器**：将模型服务打包成独立运行环境
- **GPU内存利用率**：控制显卡内存使用比例，0.9表示使用90%
- **注意力后端**：处理模型注意力计算的优化方式

## 原始资料来源

本笔记基于用户提供的vLLM部署GPT-OSS技术文档整理。

## 相关领域
- [[开发工具]]
