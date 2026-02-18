---
tags:
  - note
  - tech
creation date: 2025-08-02
modification date: 2025-08-02
owner: area/开发工具
---
# Mac mini挂载NAS文件夹

Mac mini可以通过NFS协议将NAS网络存储的文件夹挂载为本地虚拟硬盘，实现像访问本地文件一样访问网络存储。

## 核心命令

```bash
sudo mount -t nfs -o rw,bg,hard,intr 192.168.0.109:/data /Users/yuchengzhang/Desktop/data
```

## 概念解释

### 命令分解
- `sudo` - 使用管理员权限执行
- `mount` - 挂载命令
- `-t nfs` - 指定使用NFS（网络文件系统）协议
- `-o` - 挂载选项：
  - `rw` - 读写权限
  - `bg` - 后台挂载
  - `hard` - 硬挂载
  - `intr` - 允许中断
- `192.168.0.109:/data` - NAS服务器IP地址和共享文件夹路径
- `/Users/yuchengzhang/Desktop/data` - 本地挂载点

### 简单理解
这条命令就像在Mac mini的桌面上创建了一个"传送门"，通过这个传送门可以直接访问NAS服务器上的文件夹，就像访问本地硬盘一样方便。

## 相关领域
- [[开发工具]]
