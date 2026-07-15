# Tool Help — 工具帮助文档

> 版本：v1.1 | 最后更新：2026-07-15

---

## 目录

1. [概述](#1-概述)
2. [使用说明](#2-使用说明)
3. [返回内容](#3-返回内容)
4. [工作流场景](#4-工作流场景)
5. [工具列表](#5-工具列表)

---

## 1. 概述

`tool_help` 提供 Daofy 中任意 MCP 工具的**完整帮助文档**。当不确定某个工具的详细用法时，调用此工具获取包含参数说明、示例、触发词、协作链等所有详细信息。

### 一句话

> 不确定某个工具怎么用时 → `tool_help(tool_name="...")`

### 与 `docs/` 文档的关系

- `tool_help` 返回的是**内联精简版**帮助：参数说明、示例、触发词、协作链
- `docs/*.md` 提供的是**完整独立版**文档：工作流场景、技术架构、故障排除

两条途径内容互补，`tool_help` 更省 token，适合快速查阅。

---

## 2. 使用说明

### 基础调用

```python
# 获取 delphi_project 工具的完整帮助
tool_help(tool_name="delphi_project")

# 获取 delphi_file 工具的完整帮助
tool_help(tool_name="delphi_file")
```

### 参数说明

| 参数 | 必需 | 说明 |
|------|------|------|
| `tool_name` | ✅ | 工具名称。必须是已注册的 MCP 工具名 |

### 可查询的工具

| 工具名 | 说明 |
|--------|------|
| `delphi_project` | 项目全生命周期管理 |
| `delphi_kb` | 知识库搜索/管理 |
| `delphi_file` | Delphi 文件专用操作 |
| `manage_component` | DFM 组件管理 |
| `check_environment` | 编译环境诊断 |
| `async_task` | 异步任务管理 |
| `package` | 组件包管理 |
| `get_coding_rules` | Delphi 编码规则 |
| `code_hosting` | Git 操作/代码托管 |
| `tool_help` | 本工具自身 |
| `experience` | 经验记忆管理 |
| `daofy_update` | Daofy 自身更新 |

---

## 3. 返回内容

`tool_help` 返回的信息包含以下字段：

| 字段 | 说明 |
|------|------|
| `summary` | 工具一句话简介 |
| `description` | 详细描述 |
| `triggers` | AI 自动触发该工具的关键词 |
| `constraints` | 使用限制（如：不得用 bash 执行 git） |
| `actions` | 所有可用的 action 列表及说明 |
| `action_params` | 每个 action 的参数详情（必需/可选/默认值） |
| `examples` | 使用示例 |
| `workflow` | 典型工作流 |
| `workflow_hints` | 场景化工作流建议 |

---

## 4. 工作流场景

### AI 不熟悉某个工具时

```
tool_help(tool_name="delphi_file")    # 查看 delphi_file 所有 action
    ↓
delphi_file(action="read", ...)       # 根据帮助使用
```

### 回顾某个工具的完整参数

```python
# 当需要 delphi_project 的 compile action 参数时
tool_help(tool_name="delphi_project")
# → 返回 compile 的 required/optional 参数、默认值、示例
```

### 新手引导

```python
# 先看 check_environment
tool_help(tool_name="check_environment")

# 再看 delphi_project
tool_help(tool_name="delphi_project")
```

### 部署设备

```python
# 查看 deploy action 参数
tool_help(tool_name="delphi_project", action="devices")

# 枚举设备
delphi_project(action="devices", target_platform="iosdevice64")

# 部署
delphi_project(action="deploy", project_path="App.dproj", target_platform="iosdevice64")
```

---

## 5. 工具列表

Daofy 共注册 12 个 MCP 工具：

| # | 工具名 | 功能域 |
|---|--------|--------|
| 1 | `delphi_project` | 编译/配置/审计/部署 |
| 2 | `delphi_kb` | 知识库搜索/构建 |
| 3 | `delphi_file` | Delphi 文件操作 |
| 4 | `manage_component` | DFM 组件管理 |
| 5 | `check_environment` | 环境诊断 |
| 6 | `async_task` | 后台任务 |
| 7 | `package` | 组件包管理 |
| 8 | `get_coding_rules` | 编码规范 |
| 9 | `code_hosting` | Git/代码托管 |
| 10 | `tool_help` | 帮助文档 |
| 11 | `experience` | 经验记忆 |
| 12 | `daofy_update` | 自身更新 |
