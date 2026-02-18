---
tags:
  - note
  - SwarmEvo
  - AI部署
  - 开源项目
  - Agent
creation date: 2025-10-29
modification date: 2025-10-29
owner: area/Agent
---
# MLE-bench GPU加速配置

## 概述

在使用 [[MLE-bench评估框架]] 进行 Agent 评估时，默认的容器配置仅使用CPU资源。为了充分利用GPU加速能力，需要修改容器配置文件以启用NVIDIA GPU支持。

## 配置方法

### 配置文件位置

需要修改的配置文件路径为：
```
environment/config/container_configs/default.json
```

### GPU加速配置

将配置文件内容修改为以下JSON格式：

```json
{
    "mem_limit": null,
    "shm_size": "4G",
    "nano_cpus": 4e9,
    "device_requests": [
        {
            "driver": "nvidia",
            "count": -1,
            "capabilities": [["gpu", "compute", "utility"]]
        }
    ]
}
```

## 配置参数说明

**内存配置**：
- `mem_limit: null` - 不限制容器内存使用量，允许使用宿主机全部可用内存
- `shm_size: "4G"` - 设置共享内存大小为4GB，这对于GPU密集型任务很重要，可以避免因共享内存不足导致的错误

**CPU配置**：
- `nano_cpus: 4e9` - 限制容器使用4个CPU核心（4 × 10^9 纳秒CPU时间）

**GPU配置**：
- `driver: "nvidia"` - 指定使用NVIDIA驱动
- `count: -1` - 使用所有可用的GPU设备（-1表示全部）
- `capabilities: [["gpu", "compute", "utility"]]` - 启用GPU、计算和实用工具能力

## 注意事项

**前置要求**：
- 宿主机已安装NVIDIA GPU驱动
- 已安装 NVIDIA Container Toolkit
- Docker 版本支持 GPU 设备请求功能

**验证方法**：
可以在容器内运行以下命令验证GPU是否可用：
```bash
nvidia-smi
```

如果看到GPU信息输出，说明配置成功。

## 相关笔记
- [[MLE-bench评估框架]]
