# Daofy Update — Daofy 自身更新管理

> 版本：v1.1 | 最后更新：2026-07-05

---

## 目录

1. [概述](#1-概述)
2. [Action 速查](#2-action-速查)
3. [使用说明](#3-使用说明)
4. [工作流场景](#4-工作流场景)
5. [故障排除](#5-故障排除)

---

## 1. 概述

`daofy_update` 管理 Daofy MCP Server 自身的版本检查和更新。支持两种安装模式的更新：

| 安装方式 | 更新方式 |
|---------|---------|
| **git clone** 源码安装 | `git pull` 拉取最新代码 |
| **pip install** 安装 | 提示使用 `pip install --upgrade daofy-for-delphi` |

### 自动检查机制

Daofy 启动时会在后台自动检查 GitHub 最新 Release，有新版本时会通过工具响应智能提示通知 AI。

> AI 看到更新提示后应主动询问用户是否需要更新。

### 硬约束

- 更新完成后需要**重启 Daofy 或 AI Agent** 使新版本生效

---

## 2. Action 速查

| Action | 用途 | 必需参数 |
|--------|------|---------|
| `check` | 检查 GitHub 最新 Release | — |
| `check_retry` | 失败后强制后台重试检查（返回 task_id） | — |
| `update` | 执行 git pull 更新代码 | — |
| `update_retry` | 执行 git pull 带自动重试（失败后间隔 retry_interval 秒重试，最多 max_retries 次） | — |
| `version` | 显示当前版本号和安装方式 | — |

---

## 3. 使用说明

### 3.1 `check` — 检查更新

检查 GitHub 最新 Release，返回当前版本/最新版本/是否有更新。

```python
daofy_update(action="check")
```

**返回信息**：
- 当前安装版本
- GitHub 最新版本
- 是否有可用更新
- 安装方式（git/pip）

### 3.2 `update` — 执行更新

```python
# git 安装模式：自动 git pull
daofy_update(action="update")
```

- **git 安装模式**：自动执行 `git pull` 拉取最新代码
- **pip 安装模式**：不会自动更新，提示用户运行 `pip install --upgrade daofy-for-delphi`

### 3.3 `version` — 查看版本

```python
daofy_update(action="version")
```

返回：
- 当前版本号
- 安装方式（git/pip）
- 最近更新日期

---

## 4. 工作流场景

### 收到更新通知

```
AI: "检测到 Daofy 有新版本 v2026.07.05，当前版本 v2026.06.22。是否需要更新？"
用户: "更新吧"
AI: daofy_update(action="check")       # 确认版本
     daofy_update(action="update")      # 执行更新
     "更新完成。请重启 Daofy 或 AI Agent 使新版本生效。"
```

### 手动检查版本

```python
# 查看当前版本
daofy_update(action="version")

# 检查是否有更新
daofy_update(action="check")
```

### pip 安装用户的更新

```python
# 1. 检查版本
daofy_update(action="check")
# → 返回：当前 v2026.06.22，最新 v2026.07.05，安装方式 pip

# 2. 手动更新
# pip install --upgrade daofy-for-delphi
```

---

## 5. 故障排除

| 现象 | 原因 | 解决 |
|------|------|------|
| `update` 失败 | git 安装模式下本地有未提交修改 | 先 `code_hosting(action="git_status")` 检查，提交或 stash 后重试 |
| 更新后工具不生效 | Daofy 进程未重启 | 重启 AI Agent 或 MCP Server |
| pip 用户调用 `update` | 安装方式不支持 git pull | 使用 `pip install --upgrade daofy-for-delphi` |
| `check` 返回网络错误 | 无法访问 GitHub | 检查网络/代理设置 |
| 版本号显示异常 | 非标准安装 | 确认安装方式后重新安装 |

### 常见更新后操作

```json
{
  "更新类型": "操作",
  "git pull": "重启 Daofy 进程",
  "pip upgrade": "重启 AI Agent 客户端",
  "配置文件变更": "检查 config/*.json 是否需要合并"
}
```
