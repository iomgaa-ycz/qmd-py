---
tags:
  - note
  - Agent
  - 量化交易
  - 开源项目
creation date: 2025-10-28
modification date: 2025-10-28
owner: area/Agent
---
# TradingAgents - 多智能体交易框架使用指南

## 项目简介

TradingAgents 是一个开源的多智能体金融交易框架，通过 LLM 驱动的专家 Agent 协作来模拟真实交易公司的决策流程。系统提供 CLI 工具和 Python API 两种使用方式，支持灵活的配置和多种数据源。

**GitHub 仓库**：https://github.com/TauricResearch/TradingAgents

## 安装部署

### 1. 克隆仓库

```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

### 2. 创建虚拟环境

```bash
# 使用 conda
conda create -n tradingagents python=3.13
conda activate tradingagents
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

## API 配置

### 必需的 API 密钥

TradingAgents 需要以下 API 服务：

- **OpenAI API**：必需，用于所有 Agent 操作
- **Alpha Vantage API**：默认数据源，用于基本面和新闻数据

### 环境变量设置

**方式1：命令行导出**

```bash
export OPENAI_API_KEY=$YOUR_OPENAI_API_KEY
export ALPHA_VANTAGE_API_KEY=$YOUR_ALPHA_VANTAGE_API_KEY
```

**方式2：使用 .env 文件**

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑 .env 文件，填入实际的 API 密钥
OPENAI_API_KEY=sk-xxx...
ALPHA_VANTAGE_API_KEY=xxx...
```

### API 使用说明

- **Alpha Vantage 免费账户**：通过 TradingAgents 的合作关系，可享受每分钟 60 次请求，无每日限制
- **成本控制**：建议测试时使用 `gpt-4.1-mini` 和 `o4-mini` 模型以节省成本，因为系统会进行大量 API 调用

## CLI 使用方式

### 启动交互式命令行界面

```bash
python -m cli.main
```

### CLI 功能特性

- **交互式菜单**：选择股票代码、日期、语言模型
- **研究参数配置**：设置辩论轮次、分析深度等参数
- **实时进度追踪**：显示 Agent 执行状态和进度
- **决策结果输出**：展示最终交易决策和分析报告

## Python API 使用方式

### 基础使用示例

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# 创建 TradingAgents 实例
ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# 生成交易决策
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

### 自定义配置示例

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# 复制默认配置并修改
config = DEFAULT_CONFIG.copy()

# 配置 LLM 模型
config["deep_think_llm"] = "gpt-4.1-nano"  # 深度思考模型
config["quick_think_llm"] = "gpt-4.1-nano"  # 快速思考模型

# 配置辩论参数
config["max_debate_rounds"] = 1  # 最大辩论轮次

# 配置数据源
config["data_vendors"] = {
    "core_stock_apis": "yfinance",        # 核心股票 API
    "technical_indicators": "yfinance",   # 技术指标
    "fundamental_data": "alpha_vantage",  # 基本面数据
    "news_data": "alpha_vantage"          # 新闻数据
}

# 创建实例并运行
ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2024-05-10")
```

## 配置选项详解

### LLM 模型配置

| 参数 | 说明 | 推荐值（测试） | 推荐值（生产） |
|------|------|---------------|---------------|
| `deep_think_llm` | 深度思考模型 | `gpt-4.1-mini`, `o4-mini` | `o1-preview`, `gpt-4o` |
| `quick_think_llm` | 快速思考模型 | `gpt-4.1-mini`, `o4-mini` | `gpt-4o` |

### 辩论参数配置

| 参数 | 说明 | 默认值 | 建议范围 |
|------|------|--------|---------|
| `max_debate_rounds` | 最大辩论轮次 | 3 | 1-5 |

**注意**：辩论轮次越多，API 调用次数越多，成本越高，但分析质量可能更好。

### 数据源配置选项

完整的数据源配置在 `tradingagents/default_config.py` 中定义：

```python
config["data_vendors"] = {
    "core_stock_apis": "yfinance",        # 可选：yfinance, alpha_vantage, local
    "technical_indicators": "yfinance",   # 可选：yfinance, alpha_vantage, local
    "fundamental_data": "alpha_vantage",  # 可选：openai, alpha_vantage, local
    "news_data": "alpha_vantage"          # 可选：openai, alpha_vantage, google, local
}
```

**数据源选项说明**：
- **yfinance**：免费，无需 API 密钥，适合获取历史价格和技术指标
- **alpha_vantage**：需要 API 密钥，提供基本面和新闻数据
- **openai**：使用 OpenAI 生成基本面和新闻分析，成本较高
- **google**：使用 Google 搜索获取新闻
- **local**：使用本地数据文件（需要自行准备）

## 使用建议

### 成本控制策略

1. **测试阶段**：使用 `gpt-4.1-mini` 和 `o4-mini` 模型，降低 API 调用成本
2. **减少辩论轮次**：设置 `max_debate_rounds = 1`，减少 API 调用次数
3. **选择合适数据源**：优先使用 yfinance（免费）获取价格和技术指标数据

### 生产环境配置

1. **使用高性能模型**：`o1-preview` 和 `gpt-4o`，提升分析质量
2. **增加辩论轮次**：设置 `max_debate_rounds = 3-5`，深化分析深度
3. **多数据源组合**：结合 yfinance、Alpha Vantage 和 OpenAI，获取全面信息

### 调试模式

```python
# 开启调试模式，查看 Agent 执行详情
ta = TradingAgentsGraph(debug=True, config=config)
```

开启 `debug=True` 可以：
- 查看每个 Agent 的执行日志
- 追踪 API 调用和数据获取过程
- 诊断配置问题和数据源错误

## 技术框架

- **编排框架**：LangGraph - 提供模块化和灵活的 Agent 编排能力
- **编程语言**：Python 3.13
- **接口方式**：CLI 工具 + Python API

## 作为 TradeSwarm 的参考实现

TradingAgents 是 [[TradeSwarm]] 项目的重要参考实现，提供了以下可借鉴的设计思路：

### 参考价值

1. **Agent 角色设计**：
   - 基本面分析师、情绪分析师、新闻分析师、技术分析师四个维度
   - 多空研究员的辩论机制
   - 交易员-风险管理-经理的三层决策流程

2. **数据源集成方案**：
   - yfinance 用于价格和技术指标
   - Alpha Vantage 用于基本面和新闻数据
   - 灵活的数据源配置机制

3. **LLM 配置策略**：
   - 深度思考 vs 快速思考模型的分级使用
   - 测试环境和生产环境的差异化配置
   - API 成本控制策略

### TradeSwarm 的差异化设计

- **架构模式**：从层级化结构改造为完全并行的 Pipeline 架构
- **通信机制**：从 LangGraph 编排改为 SQLite 数据库解耦
- **执行方式**：从顺序执行改为 asyncio 并发执行
- **协作模式**：从层级审批改为去中心化自组织协作

## 相关笔记

- [[TradeSwarm]] - 基于 TradingAgents 参考实现的多智能体量化交易系统
- [[Agent]] - AI 智能体的理论基础和技术框架

## 参考资源

- **GitHub 仓库**：https://github.com/TauricResearch/TradingAgents
- **LangGraph 文档**：https://langchain-ai.github.io/langgraph/
- **yfinance 文档**：https://pypi.org/project/yfinance/
- **Alpha Vantage**：https://www.alphavantage.co/

---

*最后更新：2025-10-28*
