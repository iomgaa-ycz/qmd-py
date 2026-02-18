---
tags:
  - note
creation date: 2026-01-07 15:15
modification date: Wednesday 7th January 2026 15:15:45
owner: project/8x4090 服务器维护
---
# 🚀 8x4090 服务器 Clash Meta (TUN 模式) 部署指南

## 🛠 0. 环境准备

**开启 IP 转发**（TUN 模式必须）：

```
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

**创建目录**：

```
sudo mkdir -p /etc/clash/ui
```

---

## 📥 1. 安装 Clash Meta 内核

必须使用 Meta (Mihomo) 版本以支持 TUN 和新协议。

```
cd /tmp
# 下载 v1.18.1 (或最新版)
wget https://github.com/MetaCubeX/mihomo/releases/download/v1.18.1/mihomo-linux-amd64-v1.18.1.gz

# 解压并安装
gzip -d mihomo-linux-amd64-v1.18.1.gz
sudo mv mihomo-linux-amd64-v1.18.1 /usr/local/bin/clash
sudo chmod +x /usr/local/bin/clash
```

---

## 🌍 2. 下载必要规则库

确保 GeoIP/GeoSite 数据库存在，否则 Core 无法启动。

```
sudo wget -O /etc/clash/Country.mmdb https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/country.mmdb
sudo wget -O /etc/clash/geosite.dat https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat
sudo wget -O /etc/clash/geoip.dat https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.dat
```

---

## 🖥️ 3. 部署本地 Dashboard (可选但推荐)

为了不依赖外部网站（yacd.metacubex.one），直接将面板部署在本地。

```
cd /tmp
wget https://github.com/MetaCubeX/Yacd-meta/archive/gh-pages.zip
sudo apt install unzip -y
unzip gh-pages.zip
sudo rm -rf /etc/clash/ui/*
sudo cp -r Yacd-meta-gh-pages/* /etc/clash/ui/
```

---

## ⚙️ 4. 配置文件 (核心步骤)

警告：不要直接 wget 机场的订阅链接覆盖此文件！机场提供的配置通常不包含 TUN 和 DNS 劫持设置。

正确做法：下载机场配置后，将其中的 proxies, proxy-groups, rules 三部分内容，填入下方的模板中。

编辑文件：`sudo nano /etc/clash/config.yaml`

```
# ================= 基础设置 =================
port: 7890
socks-port: 7891
allow-lan: true
bind-address: "*"
mode: Rule
log-level: info
external-controller: 0.0.0.0:9090
external-ui: /etc/clash/ui
secret: "123456"  # 务必修改此密码，防止内网扫描入侵

# ================= DNS 设置 (TUN 必须) =================
dns:
  enable: true
  ipv6: false
  listen: 0.0.0.0:1053
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  fake-ip-filter:
    - "*"
    - "+.lan"
    - "+.local"
  nameserver:
    - https://doh.pub/dns-query
    - https://dns.alidns.com/dns-query
  fallback:
    - https://8.8.8.8/dns-query
    - https://1.1.1.1/dns-query

# ================= TUN 模式 (透明代理核心) =================
tun:
  enable: true
  stack: system
  dns-hijack:
    - any:53
  auto-route: true
  auto-detect-interface: true
  
  # 🛑【Slurm 防崩溃护栏】🛑
  # 必须排除以下网段，否则 Slurm/MPI 通信会被发往代理节点导致集群瘫痪
  inet4-route-exclude-address:
    - 127.0.0.1/32       # 本地回环
    - 192.168.0.0/16     # 实验室局域网
    - 10.0.0.0/8         # 常见内网
    - 172.16.0.0/12      # Docker 容器网段
    - 100.64.0.0/10      # Tailscale 网段 (至关重要)
    - 224.0.0.0/4        # 多播 (Slurm 心跳)

# ================= 节点订阅区 (请手动填入) =================
# 在此处粘贴你的 proxies, proxy-groups, rules
proxies:
  # ... 复制你的节点列表 ...

proxy-groups:
  # ... 复制你的策略组 ...

rules:
  # ... 复制你的规则 ...
```

---

## 🤖 5. 配置 Systemd 守护进程

`sudo nano /etc/systemd/system/clash.service`

内容如下：

```
[Unit]
Description=Clash Meta Kernel (TUN Mode)
After=network.target

[Service]
Type=simple
User=root
# 必须显式指定 Capability 以允许修改网络栈
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
ExecStart=/usr/local/bin/clash -d /etc/clash -f /etc/clash/config.yaml
Restart=on-failure
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

启动并开机自启：

```
sudo systemctl daemon-reload
sudo systemctl enable clash
sudo systemctl start clash
```

---

## ✅ 6. 验证与管理

### 6.1 验证透明代理 (无需 export 环境变量)

直接测试外网（应返回 200/301）：

Bash

```
curl -I https://www.google.com
```

### 6.2 验证 Slurm 安全性 (生死攸关)

必须确保 Slurm 节点通信未被劫持：

Bash

```
sinfo
```

如果显示 `idle` 或 `alloc`，说明正常。如果显示 `down*` 或卡住，立即检查 `inet4-route-exclude-address` 配置。

### 6.3 访问管理面板

打开浏览器访问：`http://100.x.x.x:9090/ui`
- **Host**: `100.x.x.x` (Tailscale IP)
- **Port**: `9090`
- **Secret**: 你在 config.yaml 设置的密码

---

## 📝 附：日常维护

**更新订阅步骤**（无脚本，纯手动）：

1. 下载新订阅 YAML 到本地电脑。
2. 复制其中的 `proxies` 和 `proxy-groups` 部分。
3. SSH 编辑 `/etc/clash/config.yaml`，替换对应部分。
4. `sudo systemctl restart clash`。
    

**查看日志**：

```
journalctl -u clash -f
```