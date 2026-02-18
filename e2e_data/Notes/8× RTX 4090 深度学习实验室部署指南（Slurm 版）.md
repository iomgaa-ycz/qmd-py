---
tags:
  - note
creation date: 2026-01-07 19:51
modification date: Wednesday 7th January 2026 19:51:02
owner: project/8x4090 服务器维护
---
> **适用场景**
> - 单机多卡（8× RTX 4090）
> - 固定团队 / 实验室  
> - GPU 统一调度、防抢占
> - 用户无 root 权限  
> - 追求稳定、低维护成本

---

## 🧱 0. 环境与设计原则

### 硬件 / 系统

- **OS**：Ubuntu 22.04 LTS
    
- **GPU**：8 × NVIDIA RTX 4090
    
- **调度器**：Slurm（单节点）
    
- **用户模型**：Linux 普通用户（无 sudo）
    

---

### 核心设计原则（非常重要）

1. **Slurm 是唯一 GPU 分配入口**
2. **用户不允许 sudo / apt-get**  
3. **Python / CUDA 环境 = 用户态 conda**
4. **允许看 GPU，不允许抢 GPU**
    
---

## 🔧 1. 系统基础准备（管理员）

### 1.1 更新系统

```bash
sudo apt update && sudo apt upgrade -y
sudo reboot
```

---

### 1.2 安装 NVIDIA Driver（一次性）

> ⚠️ 不推荐用户安装 CUDA Toolkit  
> Driver 版本 ≥ CUDA runtime 即可

```bash
sudo apt install nvidia-driver-550 -y
sudo reboot
```

验证：

```bash
nvidia-smi
```

---

## 🧩 2. 为 Slurm 启用 Cgroup v1（必须）

> **这是 GPU 隔离能否生效的关键**

### 2.1 修改 grub

```bash
sudo nano /etc/default/grub
```

修改为：

```ini
GRUB_CMDLINE_LINUX="systemd.unified_cgroup_hierarchy=0"
```

### 2.2 生效

```bash
sudo update-grub
sudo reboot
```

验证：

```bash
mount | grep cgroup
```

应看到 **cgroup v1**。

---

## 🏗 3. Slurm 单机集群部署

### 3.1 安装组件

```bash
sudo apt install -y \
  slurmctld slurmd slurm-client \
  munge libmunge-dev
```

---

### 3.2 配置 Munge（认证）

```bash
sudo dd if=/dev/urandom bs=1 count=1024 > /etc/munge/munge.key
sudo chown munge:munge /etc/munge/munge.key
sudo chmod 400 /etc/munge/munge.key

sudo systemctl enable --now munge
```

验证：

```bash
munge -n | unmunge
```

---

### 3.3 Slurm 配置文件

#### `/etc/slurm/slurm.conf`

```ini
# --- 基础集群信息 ---
ClusterName=lab-cluster
SlurmctldHost=server-4090
# [修正1] 删除 MungeSocketPath，Slurm 会自动通过库调用找到它

# --- 进程追踪与服务控制 ---
ProctrackType=proctrack/cgroup
TaskPlugin=task/cgroup
ReturnToService=1
SlurmctldPidFile=/var/run/slurmctld.pid
SlurmdPidFile=/var/run/slurmd.pid
SlurmdSpoolDir=/var/lib/slurm/slurmd
StateSaveLocation=/var/spool/slurm

# --- 用户身份 ---
SlurmUser=root

# --- 调度策略 ---
SchedulerType=sched/backfill
SelectType=select/cons_tres
SelectTypeParameters=CR_Core_Memory

# --- 资源类型声明 ---
GresTypes=gpu

# --- 节点定义 [修正2：使用全称关键字] ---
NodeName=server-4090 CPUs=192 RealMemory=515558 Sockets=2 CoresPerSocket=48 ThreadsPerCore=2 State=UNKNOWN Gres=gpu:7

# --- 分区定义 ---
PartitionName=debug Nodes=server-4090 Default=YES MaxTime=INFINITE State=UP OverSubscribe=YES

DefMemPerCPU=49152
MaxMemPerNode=131072
```

---

#### `/etc/slurm/gres.conf`

```ini
# 定义7张卡，自动关联 /dev/nvidia0 到 /dev/nvidia7
# Name=gpu File=/dev/nvidia[0-6]
Name=gpu File=/dev/nvidia0
Name=gpu File=/dev/nvidia1
Name=gpu File=/dev/nvidia2
Name=gpu File=/dev/nvidia3
Name=gpu File=/dev/nvidia4
Name=gpu File=/dev/nvidia5
Name=gpu File=/dev/nvidia6
```

---

#### `/etc/slurm/cgroup.conf`

```ini
CgroupMountpoint=/sys/fs/cgroup
CgroupAutomount=yes
ConstrainDevices=yes
ConstrainCores=yes
ConstrainRAMSpace=yes
```

---

### 3.4 启动 Slurm

```bash
sudo mkdir -p /var/spool/slurm /var/lib/slurm/slurmd
sudo systemctl enable --now slurmctld
sudo systemctl enable --now slurmd
```

验证：

```bash
sinfo
```

应看到节点状态 `idle`。

---

## 👤 4. 用户管理（普通用户）

### 4.1 创建普通用户（无 sudo）

```bash
sudo adduser yuchengzhang
```

确认无 sudo：

```bash
groups yuchengzhang
```

---

### 4.2（可选）禁止裸用 GPU（强约束）

```bash
sudo groupadd slurm
sudo chown root:slurm /dev/nvidia*
sudo chmod 660 /dev/nvidia*
```

> Slurm Job 内仍可正常使用 GPU

（生产建议加 udev 规则，避免重启失效）

---

## 🧪 5. 用户使用方式（标准流程）

### 5.1 交互式 GPU 调试

```bash
srun --gres=gpu:1 --pty bash
```

进入后：

```bash
nvidia-smi
echo $CUDA_VISIBLE_DEVICES
```

---

### 5.2 后台训练任务

`train.sh`：

```bash
#!/bin/bash
#SBATCH --gres=gpu:2
#SBATCH --time=24:00:00
#SBATCH --output=log.out

python train.py
```

提交：

```bash
sbatch train.sh
```

---

### 5.3 常用 Slurm 命令

|命令|作用|
|---|---|
|`sinfo`|节点状态|
|`squeue`|任务列表|
|`scancel <id>`|取消任务|
|`sacct`|历史任务|

---

## 🐍 6. Python / CUDA 环境（用户态）

### 6.1 推荐工具：Micromamba

```bash
curl -Ls https://micro.mamba.pm/install.sh | bash
source ~/.bashrc
```

---

### 6.2 官方推荐 PyTorch 环境

```bash
micromamba create -n torch \
  python=3.10 \
  pytorch pytorch-cuda=12.1 \
  -c pytorch -c nvidia

micromamba activate torch
```

无需 root，不污染系统。

---

## 📄 7. 给用户的一句话规则（非常重要）

> **所有 GPU 程序必须通过 Slurm 运行  
> 禁止裸跑 GPU  
> 禁止 sudo / apt-get  
> Python 环境用 conda / micromamba**

    
