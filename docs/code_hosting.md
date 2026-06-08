# Code Hosting — Git 操作与代码托管平台

> 版本：v1.0 | 最后更新：2026-06-08

---

## 目录

1. [概述](#1-概述)
2. [Action 速查](#2-action-速查)
3. [Git 本地操作](#3-git-本地操作)
4. [平台 API 操作](#4-平台-api-操作)
5. [工作流场景](#5-工作流场景)
6. [故障排除](#6-故障排除)

---

## 1. 概述

`code_hosting` 是 Daofy 中所有 Git 操作和代码托管平台操作的统一入口。提供 Git 本地操作（status/add/commit/push/clone）和多平台 API 操作（Gitea/GitHub/GitLab/Gitee/GitCode）。

### 核心规则

> ❌ **所有 Git 操作必须使用此工具，禁止用 bash 直接执行 git 命令。**

使用 `code_hosting` 的好处：
- **统一格式化输出**：比原始 bash git 更省 token
- **自动处理异步推送重试**：推送失败自动重试
- **平台统一**：一套语法操作 Gitea/GitHub/GitLab/Gitee/GitCode

### 支持的平台

| 平台 | 标识 | 说明 |
|------|------|------|
| Gitea | `gitea` | 自托管 Gitea |
| GitHub | `github` | github.com |
| GitLab | `gitlab` | GitLab CE/EE |
| Gitee | `gitee` | gitee.com 码云 |
| GitCode | `gitcode` | gitcode.net |

---

## 2. Action 速查

| Action 分组 | Action | 用途 | 必需参数 |
|------------|--------|------|---------|
| **Git 同步** | `git_status` | 查看仓库状态 | — |
| | `git_add` | 暂存文件 | `files` |
| | `git_commit` | 创建提交 | `message` |
| **Git 异步** | `git_clone` | 克隆远程仓库 | `url` |
| | `git_push` | 推送到远程 | — |
| | `git_push_retry` | 后台自动重试推送 | — |
| **平台 API** | `create_token` | 创建访问令牌（仅 Gitea） | `name`, `scopes` |
| | `init_labels` | 批量初始化四维流程标签 | — |
| | `create_issue` | 创建工单 | `title` |
| | `close_issue` | 关闭工单 | `owner`, `repo`, `index` |
| | `add_comment` | 添加评论 | `owner`, `repo`, `index`, `body` |
| | `list_issues` | 查询工单列表 | `owner`, `repo` |

---

## 3. Git 本地操作

### 3.1 查看状态

```python
code_hosting(action="git_status")
```

返回工作区状态，格式统一，比 `git status` 更省 token。

### 3.2 暂存文件

```python
# 暂存所有变更
code_hosting(action="git_add", files=["."])

# 暂存指定文件
code_hosting(action="git_add", files=["src/Unit1.pas", "src/Unit2.dfm"])
```

### 3.3 创建提交

```python
code_hosting(action="git_commit", message="feat: add user authentication module")
```

### 3.4 克隆仓库

```python
# 基础克隆
code_hosting(action="git_clone", url="https://github.com/user/repo.git")

# 国内镜像源加速
code_hosting(action="git_clone",
    url="https://github.com/user/repo.git",
    mirror="https://gitclone.com")
```

**国内加速**：`git_clone` 支持 `mirror` 参数指定镜像源。

### 3.5 推送

```python
# 单次推送
code_hosting(action="git_push")

# 后台自动重试（推送失败时自动重试）
code_hosting(action="git_push_retry")
```

`git_push_retry` 会在后台自动处理推送重试，不会阻塞当前对话。

---

## 4. 平台 API 操作

### 4.1 工单管理

```python
# 创建工单
code_hosting(action="create_issue",
    owner="myorg",
    repo="myproject",
    title="Fix login crash on Windows 11",
    body="## 问题描述\n在 Windows 11 下点击登录按钮时崩溃",
    labels=["bug", "priority-high"])

# 关闭工单
code_hosting(action="close_issue",
    owner="myorg",
    repo="myproject",
    index=42)

# 添加评论
code_hosting(action="add_comment",
    owner="myorg",
    repo="myproject",
    index=42,
    body="已在 #43 中修复")

# 查询工单列表
code_hosting(action="list_issues",
    owner="myorg",
    repo="myproject",
    state="open",
    labels=["bug"])
```

### 4.2 令牌管理

```python
# 创建 Gitea 访问令牌
code_hosting(action="create_token",
    name="daofy-ai-token",
    scopes=["read:repository", "write:repository", "read:issue", "write:issue"])
```

### 4.3 标签初始化

```python
# 批量初始化四维流程标签（优先级、类型、状态、领域）
code_hosting(action="init_labels",
    owner="myorg",
    repo="myproject")
```

---

## 5. 工作流场景

### 日常开发提交

```
delphi_file(action="write", ...)              # 编写代码
project(action="compile", ...)                # 编译验证
code_hosting(action="git_add", files=["."])   # 暂存
code_hosting(action="git_commit", ...)        # 提交
code_hosting(action="git_push")               # 推送
```

### 收到 Bug 报告

```
code_hosting(action="list_issues", state="open", labels=["bug"])  # 查看待处理 Bug
    ↓
# 修复 Bug
    ↓
code_hosting(action="git_add", files=["src/Unit1.pas"])
code_hosting(action="git_commit", message="fix: #42 login crash")
code_hosting(action="git_push")
code_hosting(action="add_comment", index=42, body="已在 #43 中修复")
code_hosting(action="close_issue", index=42)
```

### 首次克隆项目

```
code_hosting(action="git_clone",
    url="https://github.com/user/repo.git",
    mirror="https://gitclone.com")    # 国内用户加速
    ↓
check_environment(action="check")    # 检查编译环境
```

---

## 6. 故障排除

| 现象 | 原因 | 解决 |
|------|------|------|
| git_push 失败 | 远程分支有更新 | 先 pull 或用 `git_push_retry` 自动重试 |
| 克隆超时 | 网络原因 | 使用 `mirror` 参数指定国内镜像源 |
| API 操作失败 | 未配置 token | 先通过 `create_token` 创建访问令牌 |
| 提交信息不规范 | — | 建议格式：`type(scope): description` |

### 提交信息规范建议

```
feat(scope): 新功能
fix(scope): 修复 Bug
docs(scope): 文档变更
refactor(scope): 重构
test(scope): 测试
chore(scope): 构建/工具变更
```
