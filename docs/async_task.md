# Async Task — 异步任务管理

> 版本：v1.0 | 最后更新：2026-06-08

---

## 目录

1. [概述](#1-概述)
2. [Action 速查](#2-action-速查)
3. [Status — 查询进度](#3-status--查询进度)
4. [Result — 获取结果](#4-result--获取结果)
5. [List — 列出任务](#5-list--列出任务)
6. [Cancel — 取消任务](#6-cancel--取消任务)
7. [Start — 启动任务](#7-start--启动任务)
8. [通知机制](#8-通知机制)
9. [故障排除](#9-故障排除)

---

## 1. 概述

`async_task` 管理 Daofy 中的**后台异步任务**。耗时操作（如知识库构建、文档扫描、向量索引构建）会在后台执行，不阻塞 MCP 通信通道。通过此工具可以查询进度、获取结果或取消任务。

> 通常知识库构建通过 `delphi_kb(action="build", async_mode=True)` 自动触发，无需手动调用 `async_task(action="start")`。

---

## 2. Action 速查

| Action | 用途 |
|--------|------|
| `start` | 启动异步任务（通常自动触发，无需手动调用） |
| `status` | 查询任务状态（进度百分比 + 状态） |
| `result` | 获取任务结果 |
| `list` | 列出所有任务 |
| `cancel` | 取消运行中的任务 |

---

## 3. Status — 查询进度

查询异步任务的执行进度。支持**长轮询**（等待一段时间后再返回）和**短轮询**（立即返回）。

```python
# 短轮询（立即返回）
async_task(action="status", task_id="task_xxx")

# 长轮询（最多等待 30 秒，有结果立即返回）
async_task(action="status", task_id="task_xxx", long_poll_seconds=30)
```

**返回信息**：
- `status`: pending/running/completed/failed/cancelled
- `progress`: 0~100 百分比
- `message`: 当前阶段描述

### 长轮询说明

```
长轮询 ≤30 秒 → MCP 请求通道约 60s 超时
  ↓ 超时
切换短轮询 → 每 N 秒轮询一次
```

---

## 4. Result — 获取任务结果

任务完成后获取最终结果。

```python
async_task(action="result", task_id="task_xxx")
```

---

## 5. List — 列出任务

列出所有（包括已完成和运行中的）异步任务。

```python
async_task(action="list")
```

---

## 6. Cancel — 取消任务

取消正在运行的任务。

```python
async_task(action="cancel", task_id="task_xxx")
```

---

## 7. Start — 启动任务

通常情况下，耗时操作会自动触发异步任务，无需手动调用 `start`。如需手动启动：

```python
async_task(action="start",
    task_type="build_embedding",
    task_params={"project_path": "..."})
```

**支持的任务类型**：

| task_type | 说明 |
|-----------|------|
| `build_knowledge_base` | 构建 Delphi 源码知识库 |
| `build_thirdparty_knowledge_base` | 构建三方库知识库 |
| `init_project_knowledge_base` | 初始化项目知识库 |
| `build_document_knowledge_base` | 构建文档知识库 |
| `build_embedding` | 构建向量索引 |

---

## 8. 通知机制

Daofy 支持 **TaskStatusNotification 推送通知**：

> 所有异步任务（知识库构建、文档扫描、embedding 等）完成/失败/取消时，自动推送 `TaskStatusNotification` 到 MCP 客户端，**无需轮询**。

AI Agent 只需：
1. 启动任务（自动触发或手动）
2. 等待推送通知
3. 通过 `async_task(action="result", task_id="...")` 获取结果

---

## 9. 故障排除

| 现象 | 原因 | 解决 |
|------|------|------|
| 任务长时间 pending | 资源不足 | 检查系统资源，稍后重试 |
| 任务 failed | 构建过程出错 | `action="result"` 查看错误信息 |
| 任务卡住 | 数据量大 | 耐心等待或 `cancel` 后重试 |
| 未收到推送通知 | MCP 客户端不支持 | 手动轮询 `action="status"` |
