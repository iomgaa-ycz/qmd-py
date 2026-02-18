---
tags:
  - note
  - ClaudeCode
creation date: 2025-10-27
modification date: 2025-10-27
owner: area/Claude Code
---
# Claude Code 核心配置与使用

本文档整合了 Claude Code 的核心配置方法和基本使用技巧,包括 MCP 配置、工具权限设置、工作目录管理等内容。

## 📋 MCP 配置

### MCP 简介
模型上下文协议 (MCP) 允许 Claude Code 连接到外部工具和服务。配置 MCP 服务器以扩展 Claude 的功能。

### 配置文件位置
MCP 配置可以存储在多个位置(优先级从高到低):
- **项目专用**: `.claude/settings.local.json` (在项目目录中)
- **用户特定的本地**: `~/.claude/settings.local.json`
- **用户特定的全局**: `~/.claude/settings.json`
- **主 Claude.json**: `~/.claude.json`
- **专用 MCP 文件**: `~/.claude/mcp_servers.json`

### MCP 配置示例

```json
// Example: ~/.claude.json (recommended for reliability)
{
  "projects": {
    "/path/to/your/project": {
      "mcpServers": {
        "filesystem": {
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/username/Desktop", "/path/to/allowed/dir"]
        },
        "memory": {
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-memory"]
        },
        "fetch": {
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-fetch"]
        }
      }
    }
  }
}
```

**注意**: 请确保更新为正确的项目路径。

## 🔧 工具权限设置

### 配置文件位置
工具配置可以存储在多个位置:
- **项目专用**: `.claude/settings.local.json`
- **用户特定的本地**: `~/.claude/settings.local.json`
- **用户专属全局**: `~/.claude/settings.json`
- **主 Claude.json**: `~/.claude.json`

### 允许的工具示例配置

```json
// Example: ~/.claude.json
{
  "projects": {
    "/path/to/your/project": {
      "mcpServers": {
        "filesystem": {
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/username/Desktop", "/path/to/allowed/dir"]
        }
      },
      "allowedTools": [
        "Task",
        "Bash",                    // ⚠️ Dangerous: allows all system commands
        "Bash(git log:*)",         // Safer: only allows git log commands
        "Glob",
        "Grep",
        "LS",
        "Read",
        "Edit",
        "MultiEdit",
        "Write",
        "WebFetch",
        "WebSearch"
      ]
    }
  }
}
```

### 交互式权限管理

使用 `/permissions` 命令可以更便捷地管理工具权限:

```bash
/permissions
```

这个高级界面允许您:
- **查看当前权限** - 查看当前允许或拒绝使用哪些工具
- **显式允许工具** - 授予对特定工具或工具模式的权限
- **明确拒绝工具** - 阻止访问您想要限制的工具
- **可视化导航** - 使用直观的用户界面,而非手动编辑 JSON 文件

`/permissions` 界面提供实时权限管理,具备流畅且响应迅速的体验,使配置更改轻松自如——无需重启 Claude Code 或手动编辑配置文件。

## 📂 附加工作目录与扩展工作区

### 功能说明
Claude Code 可以通过以下方式访问当前工作目录之外的多个目录:
- **命令行参数**: `--add-dir` (v1.0.18 版本新增) 启动时使用
- **斜杠命令**: `/add-dir` 会话中途无缝扩展工作流程

这使您能够在不切换目录或重启会话的情况下跨多个项目工作或引用外部资源。

### 使用方法

**CLI 参数 (启动时)**:
```bash
# Add a single additional directory
claude --add-dir /path/to/other/project

# Combine with other options
claude --add-dir ~/shared/libraries

# Use with print mode for scripting
claude --add-dir ../backend -p "Validate that API calls in the current directory match endpoints defined in ../backend"
```

**斜杠命令 (会话中途)**:
```bash
# Add directory without restarting your session
/add-dir /path/to/other/project

# Add multiple directories as needed
/add-dir ~/shared/libraries
/add-dir ../backend-api
```

### 常见使用场景

**多仓库项目**:
```bash
# At startup: Work on frontend while referencing the backend API
claude --add-dir ../backend-api

# Mid-session: Add backend when you need to reference API endpoints
/add-dir ../backend-api
```

**共享资源**:
```bash
# At startup: Access shared configs or documentation
claude --add-dir ~/company/shared-configs

# Mid-session: Add shared resources when needed
/add-dir ~/company/shared-configs
```

**动态工作流扩展**:
```bash
# Start with current project, then expand as needed
# No need to restart when you realize you need additional context
/add-dir ../related-service
/add-dir ~/templates
```

**注意**: 当前工作目录始终会被包含。通过 `--add-dir` 添加的额外目录似乎不会自动读取其中的 CLAUDE.md 文件。

### 工作流编排优势

该功能通过使 Claude 能够执行以下操作,显著提升了工作流编排:
- 可同时在多个代码仓库中工作——保持上下文并应用一致的更改
- 直接从库或配置仓库中引用共享代码
- 临时暴露一个代码仓库,供 Claude 分析或修改,而无需切换目录
- 使用 `/add-dir` 动态扩展工作区,无需中断当前会话

`/add-dir` 斜杠命令让这一切变得尤为流畅——你可以专注于一个项目开始工作,随着需求的出现有机地扩展工作区,而不会丢失上下文或重新启动。无需在多个会话之间切换或复制文件,你可以在同一工作流程结构中组合多个仓库——在单一的、上下文感知的会话中协调复杂的多仓库操作。

## 📝 相关笔记
- [[Claude Code最佳实践]] - CLAUDE.md 设计、上下文管理、健康检查
- [[Claude Code高级特性]] - Plan Mode、Custom Agents、Ultrathink 等高级功能

## 相关领域
- [[Claude Code]] - AI辅助开发工具领域
