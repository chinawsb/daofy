---
name: daofy
description: >-
  Daofy for Delphi MCP 路由规则。处理 Delphi 源码、DFM、工程文件、Daofy MCP 工具、
  Delphi 编译/审计/自动化测试或 Daofy 仓库时使用；尤其是看到
  .pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx 路径、需要 Git 操作、需要调用
  delphi_file/delphi_project/delphi_kb/code_hosting/automate_delphi 时使用。
---

<!-- daofy-managed-skill: true -->
<!-- daofy-managed-skill-version: 2026.07.05.1 -->

# Daofy for Delphi

本 skill 是 Daofy MCP Server 提供的 Agent 侧兜底规则。它不替代 MCP
`initialize.instructions`、`list_tools`、`tool_help` 或 `get_coding_rules`，只用于让
支持 Agent Skills 的客户端更稳定地选对 Daofy 工具。

## 强制路由

- Delphi 文件必须用 `delphi_file` 读写/搜索/正则匹配+替换，不要用内置
  `Read/Edit/Write/grep`。
- 修改 Delphi 代码前，按需调用 `get_coding_rules(section="writing")`。
- API、类、函数或项目符号不确定时，先用 `delphi_kb` 查询。
- 修改后用 `delphi_project(action="compile")` 验证；涉及 UI/DFM 布局时，用
  `delphi_project(action="layout")` 做布局审计。
- 所有 Git 操作使用 `code_hosting`，不要在 shell 里直接运行 `git`。

## 工作流

1. 环境或规则不确定时，先调用 `check_environment`、`tool_help` 或
   `get_coding_rules`。
2. 读取 Delphi 文件时调用 `delphi_file(action="read", file_path=...)`。
3. 写入 Delphi 文件时使用 `delphi_file(action="write", edits=[...])`；同一文件多处
   修改合并为一次写入。
4. 写入后按需调用 `delphi_file(action="format", file_path=...)`。
5. 编译、审计、布局、运行时 uses 检查使用 `delphi_project`。
6. 自动化测试使用 `automate_delphi`；需要完整流程时读取
   `delphi://automation/workflow`。

## 与其他 IDE skill 的关系

如果 Kai/RAD Studio IDE skill 同时存在，仍然优先遵守 Daofy 对 Delphi 文件的工具
路由规则。Daofy 的 `delphi_file` 负责编码检测、备份、DFM 转换、脏标记和 edit guard；
缺少 Daofy 工具时，刷新 MCP 连接或询问用户，不要静默回退到普通文件编辑。

## 不限制的范围

Daofy MCP Server 自身的 Python、Markdown、测试和配置文件可以按当前 Agent 的普通代码
编辑流程处理；本 skill 的直接读写限制只针对 Delphi 源码和工程文件。
