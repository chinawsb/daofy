---
name: daofy
description: >-
  Daofy for Delphi 用法 skill（按需加载）。当实际需要调用 delphi_file 写入/修改 Delphi 文件、
  需要做编译/审计/自动化测试，或遇到 Trae 等只暴露 run_mcp 的客户端包装时使用。
  强制路由规则(Delphi 文件必用 delphi_file)由 Daofy Rule 与 initialize.instructions 常驻保证，本 skill 只讲"怎么用"。
---

<!-- daofy-managed-skill: true -->
<!-- daofy-managed-skill-version: 2026.07.17 -->

# Daofy for Delphi — 用法 Skill（按需加载）

> 本 skill 是**按需加载**的详细用法手册，不是常驻规则。
> 强制路由约束（Delphi 文件必须用 `delphi_file`，禁用内置 Read/Edit/Write/grep）已由
> Daofy Rule（安装到客户端规则目录）与 MCP `initialize.instructions` 常驻保证，此处不再复述，
> 以免与 Rule 重复注入。本 skill 只补充 Rule 没覆盖的"客户端包装"与"工作流"。

## 客户端包装

- 直接暴露 MCP 工具的客户端：调用 `delphi_file` 时只传 Daofy 参数，例如
  `action/file_path/start_line/end_line`。
- Trae 等只暴露 `run_mcp` 的客户端：外层传 `server_name` 和 `tool_name`，内层
  `args` 才放 Daofy 参数；`server_name` 是该客户端 MCP 配置里的 Daofy 服务别名，
  按实际配置填写，不是 Daofy 固定值；不要把 `server_name/tool_name` 混进
  `delphi_file` 的参数对象。

```python
run_mcp({
  "server_name": "<client-configured-daofy-server-name>",
  "tool_name": "delphi_file",
  "args": {
    "action": "read",
    "file_path": "C:\\path\\Unit1.pas",
    "start_line": 1,
    "end_line": 100
  }
})
```

## 工作流

1. **确定 Delphi 编译器/环境时，调用 `check_environment(action="detect")`**
   （首次编译前先 `action="check"`），**不要**用 shell 跑 `where dcc32` /
   `dcc64 --version` 等探测命令——编译器路径/版本由 Daofy 统一探测与缓存。
   工具参数不确定时再用 `tool_help` 或 `get_coding_rules`。
2. 读取 Delphi 文件时调用 `delphi_file(action="read", file_path=...)`。
3. 写入 Delphi 文件时使用 `delphi_file(action="write", edits=[...])`；同一文件多处
   修改合并为一次写入。
4. 写入后按需调用 `delphi_file(action="format", file_path=...)`。
5. 编译、审计、布局、运行时 uses 检查使用 `delphi_project`。
6. 自动化测试使用 `automate_delphi`；需要完整流程时读取
   `delphi://automation/workflow`。
7. 深度编码/编译/审查规范用 `get_coding_rules(section=..., examples=...)` 按需获取，不要在常驻上下文里堆规范。

## 编码规则按需加载

`get_coding_rules` 支持 `section` 和 `examples` 两个维度按需加载，避免一次性注入全部规则：

```python
# 只加载写代码规则
get_coding_rules(section="writing")

# 只加载某个子章节
get_coding_rules(section="delphi_file_write_rule")

# 加载写代码规则 + 命名规范示例
get_coding_rules(section="writing", examples="naming")

# 加载编译规则 + 格式化示例
get_coding_rules(section="compile", examples="formatting")
```

**常用 section**: `writing`, `compile`, `review`, `agent_rules`, `kb_search`,
`delphi_file_write_rule`, `delphi_file_dirty_flag`, `delphi_file_output_format`,
`delphi_file_usage_tips`

**常用 examples**: `naming`, `formatting`, `documentation`, `error-handling`

## DFM 中文内容

编辑 DFM 文件时，中文内容（Caption、Text、Hint 等）**直接写原文，不需要转义**：

```python
# ✅ 正确：直接写中文
delphi_file(action="write", file_path="MainForm.dfm", edits=[
    {"start_line": 5, "end_line": 5, "new_text": '    Caption = "中文标题"'}
])

# ❌ 错误：不要手动转义 Unicode
delphi_file(action="write", file_path="MainForm.dfm", edits=[
    {"start_line": 5, "end_line": 5, "new_text": '    Caption = \u4e2d\u6587\u6807\u9898'}
])
```

原理：`delphi_file` 读写时自动处理编码（GBK/UTF-8/BOM），中文内容保持原文写入。

## 与其他 IDE skill 的关系

如果 Kai/RAD Studio IDE skill 同时存在，仍然优先遵守 Daofy 对 Delphi 文件的工具
路由规则。Daofy 的 `delphi_file` 负责编码检测、备份、DFM 转换、脏标记和 edit guard；
缺少 Daofy 工具时，刷新 MCP 连接或询问用户，不要静默回退到普通文件编辑。

## 不限制的范围

Daofy MCP Server 自身的 Python、Markdown、测试和配置文件可以按当前 Agent 的普通代码
编辑流程处理；本 skill 的直接读写限制只针对 Delphi 源码和工程文件。
