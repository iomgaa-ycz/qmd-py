---
title: "Herald — 代码能力与 Coding Agent 集成"
date: 2026-02-17
tags: [herald, design, coding-agent]
owner: project/Herald — AI Research Companion
---

科研工作离不开代码。我们需要写实验脚本、处理数据、实现模型、可视化结果。传统的科研流程里，这些代码工作往往占据了研究者大量的时间——有时候比真正的思考时间还要多。

Herald 的定位是科研伙伴，不是科研替代者。它不应该替我们思考研究问题，但它应该替我们写那些"思路已经清晰，但需要时间实现"的代码。问题是：我们要怎么赋予 Herald 足够强的代码能力？

## 现有能力远远不够

nanobot 的代码能力来自三个工具：

- **exec tool** — 执行 shell 命令
- **read tool** — 读取文件
- **write tool** — 写入文件

理论上，有这三个工具，agent 就能完成任何代码任务。给它一个"实现 attention-based 时序预测模型"的任务，它可以：

1. 用 write 创建 `model.py`
2. 用 exec 运行 `pip install torch`
3. 用 exec 执行 `python train.py`
4. 用 read 查看日志
5. 循环调试直到成功

但现实是这个过程极其低效。每一步都是孤立的工具调用，agent 无法"看到"完整的上下文。它不知道当前 Python 环境是什么版本，不知道已经安装了哪些包，不知道代码跑到哪一行报错了。它只能通过一次次调用 exec 和 read 来"盲人摸象"。

更糟糕的是，调试循环会变得非常长。写了一个 bug → 运行报错 → 读日志 → 理解错误 → 修改代码 → 再运行。每一步都要经过 LLM 的思考，都要消耗 token，都要等待响应。一个简单的 bug 可能需要十几轮对话才能修复。

对日常助手来说，这个能力够用。但对科研伙伴来说，远远不够。

## netclode 的启示：不重造轮子

我们在研究 netclode 时发现了一个非常聪明的设计思路：**自己不做 coding agent，而是调用成熟的 coding agent**。

netclode 定义了一个 `SDKAdapter` 接口：

```typescript
interface SDKAdapter {
  initialize(config: SDKConfig): Promise<void>;
  executePrompt(sessionId: string, text: string, config?: PromptConfig): AsyncGenerator<PromptEvent>;
  setInterruptSignal(): void;
  shutdown(): Promise<void>;
}
```

就这么简单。四个方法：初始化、执行 prompt、中断、关闭。

然后 netclode 实现了四个适配器：

- **ClaudeCodeAdapter** — 适配 Claude Code（通过 stdio 与 Claude Code CLI 通信）
- **OpenCodeAdapter** — 适配 OpenCode（通过 HTTP SSE）
- **CopilotAdapter** — 适配 GitHub Copilot（通过 stdio JSON-RPC）
- **CodexAdapter** — 适配 OpenAI Codex（通过 stdio JSON）

每个适配器负责处理与对应 SDK 的通信细节，但对外暴露的接口是统一的。这样 netclode 的 control plane 不需要关心底层用的是哪个 SDK，只需要调用 `executePrompt` 就行。

这个设计的精髓在于：**承认自己不擅长的事情，把它委托给专业工具**。

Claude Code 是 Anthropic 花了大量时间调优的 coding agent。它的 prompt engineering、工具使用策略、错误恢复机制，都是经过无数次迭代优化的。OpenCode、Copilot、Codex 同样如此。它们都是专业的 coding agent，各有优势。

我们为什么要重新实现一遍？

## 上下文注入 — 让 Coding Agent 拥有科研记忆

在研究 coding agent CLI 时，我们发现了一个改变游戏规则的特性：它们支持上下文注入。这让 coding agent 在 Herald 中的角色从"代码工具"升级为"带科研记忆的编码者"。

Claude Code 的支持最为完整。它提供了三个关键参数：

```
--system-prompt <prompt>          System prompt to use for the session
--append-system-prompt <prompt>   Append a system prompt to the default system prompt
--mcp-config <configs...>         Load MCP servers from JSON files or strings
```

`--append-system-prompt` 可以在默认 system prompt 后追加内容 — 这意味着 Herald 可以把项目记忆、相关论文摘要、实验历史拼成一段上下文，直接注入进去。当 Herald 告诉 Claude Code "实现一个 attention-based 时序预测模型"时，它同时知道：你之前试过哪些方法、哪些论文的方法值得参考、实验的 baseline 是什么。

更进一步，`--mcp-config` 可以给它挂载 MCP 服务器 — 比如直接接入 QMD。这样 Claude Code 在写代码时能语义检索知识库，自己找到相关论文的实现细节。

Codex 的支持相对弱一些：没有 `--system-prompt` 参数，只能通过 prompt 本身注入上下文（把背景信息写在 prompt 开头）。但对于大多数场景，这已经够用。

这个发现的意义远超技术细节。既然 Coding Agent 可以被注入完整的科研上下文，那它的能力边界就不仅限于写代码 — 文献调研、知识索引构建等任务理论上也可以委托给它。这让 Herald 的架构更简洁：MVP 阶段不需要单独的 SubagentManager，把精力集中在 Coding Agent 集成上即可。等后续确实需要并行的"带记忆的非代码后台任务"时，再考虑加回来。

## Herald 的方案：编排者模式

Herald 不是 coding agent，它是科研伙伴。它的职责是理解科研上下文，而不是成为最好的代码生成器。

所以我们采用"编排者模式"：

**Herald 负责理解科研上下文** → "我需要一个 attention-based 时序预测模型，用 PyTorch 实现，输入是 (batch, seq_len, features)，输出是 (batch, pred_len)"

**构造精确的 prompt** → "在 `models/attention_forecaster.py` 中实现一个 AttentionForecaster 类。要求：使用 multi-head attention，支持可配置的 head 数量，包含 positional encoding。参考 `models/base.py` 中的 BaseModel 接口。"

**委托给外部 Coding Agent** → 调用 Claude Code / Codex CLI，传入 prompt

**Coding Agent 负责代码编写、调试、测试** → 它有完整的代码上下文、可以运行测试、可以多轮调试

**Herald 验收结果，记录到实验日志** → "AttentionForecaster 实现完成，通过了 3/3 测试用例。代码位置：models/attention_forecaster.py。参数：hidden_dim=256, num_heads=8, dropout=0.1。"

这个模式和我们现在 Scientist agent 的工作方式是一样的。Scientist 不直接写代码，而是委托给 Claude Code。Scientist 负责理解科研意图，Claude Code 负责把意图转化为代码。

Herald 会更进一步：它不仅会委托代码任务，还会主动发现需要代码的场景。

比如你在笔记里写："我们的实验需要在 5 个不同的数据集上运行，每个数据集 3 个随机种子，对比 baseline 和我们的方法。"

Herald 会意识到："这需要一个实验脚本"。然后它会：

1. 分析已有代码结构（`train.py` 是主入口，`configs/` 存放配置，`scripts/` 存放自动化脚本）
2. 构造 prompt："在 `scripts/run_full_experiment.py` 中实现一个脚本，自动在 5 个数据集（D1, D2, D3, D4, D5）上运行实验，每个 3 个随机种子，对比 baseline 和 proposed method，记录结果到 `results/{dataset}/{method}/seed{i}/`"
3. 委托给 Coding Agent 实现
4. 验收：检查脚本是否能运行，是否覆盖了所有数据集和种子
5. 记录到实验日志："实验脚本已生成，可通过 `python scripts/run_full_experiment.py` 运行完整实验"

整个过程，Herald 不直接写代码，但它理解了科研上下文，构造了精确的需求，委托给专业工具完成，最后验收并记录。

## 需要实现的：CodingAgentTool

从技术角度，我们需要实现一个新的工具：`CodingAgentTool`。

它的接口类似 nanobot 的 `SpawnTool`（派生子 agent），但对接的不是另一个 nanobot agent，而是外部的 coding agent。

```python
class CodingAgentTool:
    """Delegate coding tasks to external coding agents"""
    
    async def execute(
        self,
        task: str,
        context: dict,
        agent_type: str = "claude_code",
        config: dict = None
    ) -> dict:
        """
        执行代码任务
        
        Args:
            task: 代码任务描述（Herald 构造的精确 prompt）
            context: 上下文信息（项目路径、已有文件、测试要求等）
            agent_type: 使用哪个 coding agent（claude_code | codex | opencode）
            config: agent 配置（模型、推理强度等）
            
        Returns:
            {
                "success": bool,
                "output": str,  # agent 的输出
                "files_changed": list,  # 修改的文件列表
                "tests_passed": bool,  # 测试是否通过
                "summary": str  # 任务摘要
            }
        """
        pass
```

这个工具会：

1. **设置工作环境**：确保项目代码已 clone，依赖已安装
2. **调用 coding agent**：根据 `agent_type` 选择对应的 CLI（claude_code / codex），传入 task
3. **监控执行过程**：实时获取 agent 的输出，判断是否成功
4. **运行测试**（如果有）：验证代码是否正确
5. **返回结果**：包含成功状态、修改的文件、测试结果、摘要

### 初期支持的 Agent

我们在 pci-3 上已经有了两个 coding agent：

- **Claude Code CLI** — Anthropic 官方的 coding agent，已安装
- **Codex CLI** — OpenAI 的 coding agent，已安装

所以初期我们就支持这两个。它们都是命令行工具，调用方式很简单：

```bash
# Claude Code
claude code "implement attention model in models/attention.py"

# Codex
codex "implement attention model in models/attention.py"
```

我们的 `CodingAgentTool` 只需要：

1. 构造合适的命令行参数
2. 启动子进程
3. 实时读取输出
4. 解析结果

后续可以扩展支持更多 agent（OpenCode、Copilot 等），只需要添加对应的适配逻辑。

## 与 Scientist agent 的区别

你可能会问：这和我们现在用 Scientist agent 委托 Claude Code 有什么区别？

区别在于 **自动化程度** 和 **上下文理解**。

现在我们用 Scientist agent 时，是这样的：

1. 我们人工判断："这个任务需要代码"
2. 我们人工构造 prompt："请帮我实现 xxx"
3. 我们人工告诉 Scientist："把这个任务交给 Claude Code"
4. Scientist 调用 Claude Code
5. 我们人工检查结果

Herald 的目标是：

1. Herald 自动判断："这个任务需要代码"
2. Herald 自动构造 prompt（基于项目上下文、代码结构、已有文件）
3. Herald 自动选择合适的 coding agent
4. Herald 自动验收结果
5. Herald 自动记录到实验日志

整个过程，我们只需要告诉 Herald 一个高层次的意图（"我需要一个 attention model"），它会自己决定是否需要代码，如何实现，如何验收。

这才是真正的"科研伙伴"。

## 更进一步：主动代码重构

有了 `CodingAgentTool`，Herald 还能做更多事情。

比如它可以主动发现代码问题：

- "你的 `train.py` 有 500 行了，是不是该拆分成多个模块？"
- "你的实验脚本里硬编码了很多超参数，是不是该用配置文件？"
- "你有 3 个类似的数据处理函数，是不是该抽象成一个通用函数？"

这些不是科研的核心工作，但会影响科研效率。Herald 可以主动提出建议，经你同意后，委托给 coding agent 完成重构。

再比如它可以主动生成辅助代码：

- "你的实验跑了 3 天了，我帮你写个进度监控脚本吧，可以实时看到每个 epoch 的 loss 和 ETA"
- "你的实验结果存在 10 个不同的文件夹里，我帮你写个汇总脚本，生成一张对比表格"
- "你的论文里有 5 张图，我帮你写个批量生成脚本，以后改数据直接重新生成就行"

这些都是"思路很清楚，但需要时间实现"的任务。正是 Herald 应该接手的。

## 小结

Herald 的代码能力不是来自自己实现 coding agent，而是来自 **理解科研上下文 + 委托专业工具**。

这个设计理念贯穿 Herald 的整个架构：我们不重造轮子，而是把已有的优秀工具编排起来，让它们在科研场景下发挥最大价值。

下一篇：[[Herald — 四层记忆系统设计]]，我们会讲 Herald 如何记住长达数月甚至数年的研究历程。
