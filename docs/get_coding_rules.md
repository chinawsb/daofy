# Get Coding Rules — 获取 Delphi 编码规范

> 版本：v1.1 | 最后更新：2026-07-05

---

## 目录

1. [概述](#1-概述)
2. [使用说明](#2-使用说明)
3. [章节索引](#3-章节索引)
4. [工作流集成](#4-工作流集成)
5. [故障排除](#5-故障排除)

---

## 1. 概述

`get_coding_rules` 提供 Delphi 编码规范的按需查询。AI Agent 在写/修改任何 Delphi 代码前，**必须先调用此工具**了解编码规范，确保生成的代码风格与项目一致。

### 核心规则

> ⚠️ **看到 `.pas`/`.dfm`/`.dproj`/`.dpk`/`.dpr`/`.inc`/`.res` 等 Delphi 文件时，必须先调用此工具。**
>
> ⚠️ **在写/修改任何 Delphi 代码前，必须先 `get_coding_rules` 了解编码规范。**

### 硬约束

- 无 — 此工具为只读查询，不修改任何文件

---

## 2. 使用说明

### 基础调用

```python
# 获取完整工作流总览 + 章节索引（推荐首次调用）
get_coding_rules()

# 指定章节获取
get_coding_rules(section="workflow")
get_coding_rules(section="writing")
get_coding_rules(section="review")
get_coding_rules(section="safety")
get_coding_rules(section="ui_layout")
get_coding_rules(section="agent_rules")
```

### 参数说明

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `project_path` | ❌ | — | 项目路径。传此参数可获取项目级自定义规则（优先于默认规则） |
| `section` | ❌ | — | 章节筛选。不传则返回工作流总览+所有章节索引 |
| `source_only` | ❌ | false | 仅返回规则文件内容，不包含 AI 解读 |

---

## 3. 章节索引

| Section | 内容 | 适用场景 |
|---------|------|---------|
| `workflow` | 工作流总览 | 首次接触项目时先看这个了解整体流程 |
| `writing` | Delphi 代码编写规则（命名/格式/泛型） | 写/改代码前必看 |
| `review` / `review-guide` / `review-table` | 编译后审查代码（含完整审核表） | 完成代码后审查 |
| `ui_layout` / `ui_testing` | UI 布局规范与审计 | 生成或修改 Delphi 窗体后检查布局质量 |
| `safety` | 安全敏感操作规则 | 涉及注册表、进程、文件操作时 |
| `agent_rules` | Agent 操作硬规则 | 了解 AI 的行为限制 |
| `compile` | 编译规则与参数说明 | 编译项目前查看 DCC 参数含义 |
| `format` | 代码格式化规则（pasfmt） | 格式化前查看格式化配置 |
| `cleanup` | 清理规则 | 代码清理时查看清理策略 |
| `kb_search` | 知识库搜索策略 | 使用 delphi_kb 搜索前查看搜索优先级 |
| `kb_rebuild` | 知识库重建规则 | 重建知识库时查看重建流程 |
| `debugging` | Delphi 调试完整方法论（12 子章节） | 遇到编译/运行时错误时查看 |
| `console-testing` | 控制台测试规则 | 使用 automate_delphi console 模式时 |
| `experience` | 经验记忆使用规则 | 保存/搜索 AI 经验时 |
| `maintenance` | 维护规则 | 项目维护时查看维护策略 |
| `planning` | 规划规则 | 开始新功能前查看规划策略 |
| `human-collab` | 人机协作规范 | 需要用户介入时查看协作流程 |

### 规则优先级

```
项目自定义规则 > 默认规则
```

当 `project_path` 指定具体项目时，会先尝试加载该项目下的自定义规则文件；若无自定义规则，则使用内置默认规则。

---

## 4. 工作流集成

### 标准 Delphi 开发工作流

```
get_coding_rules(section="workflow")          # ① 了解工作流
    ↓
get_coding_rules(section="writing")           # ② 了解编码规范
    ↓
delphi_kb(query="...")                        # ③ 搜索 API 定义
    ↓
delphi_file(action="read", ...)               # ④ 读源码确认修改点
    ↓
delphi_file(action="write", ...)              # ⑤ 写代码
    ↓
delphi_file(action="format", ...)             # ⑥ 格式化
    ↓
delphi_project(action="compile", ...)                # ⑦ 编译验证
    ↓
get_coding_rules(section="review")            # ⑧ 审查代码
```

### 快速调研现有项目

```python
# 先了解编码规范
get_coding_rules(section="workflow")

# 再了解代码结构
delphi_project(action="ast", base_dir="src")
```

---

## 5. 故障排除

| 现象 | 原因 | 解决 |
|------|------|------|
| 返回空结果 | 指定了不存在的章节 | 不传 section 参数获取所有章节索引 |
| 自定义规则未生效 | project_path 不正确 | 确认路径指向包含 `.coding-rules/` 的目录 |
| 规则过于严格/宽松 | 默认规则不匹配项目风格 | 在项目目录下创建自定义规则覆盖默认规则 |
