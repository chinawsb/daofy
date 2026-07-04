---
name: delphi-automation-workflow
description: >-
  构建并运行 Delphi GUI/控制台自动化测试。当 AI 需要分析 Delphi 源码/DFM 文件、
  生成机器可执行的自动化脚本、调用 automate_delphi、生成结构化测试报告和修复方案、
  然后切换到编码模式修复失败并重跑时使用。
---

<!-- @when: 首次进行 Delphi 自动化测试，需了解完整工作流 -->
<!-- @chain: after=coding-rules/ui-testing.md, before=script-generation-workflow.md -->

# Delphi 自动化测试工作流

完整闭环：源码分析 → 脚本构造 → 执行 → 报告 → 修复 → 重跑。

MCP resource URI: `delphi://automation/workflow`。

## 核心循环

1. 加载 `delphi://automation/workflow`。
2. 生成新脚本前，先读 `delphi://automation/script-generation-workflow`。
3. 先分析源码：读目标 `.pas/.dfm`，映射控件、事件和源码推导的断言。
4. 构造脚本：可执行检查用 `assert_expr`，说明文字放 `expected` 或 `note`。
5. 执行 `automate_delphi(action="auto"|"gui"|"console", ...)`。
6. 读取 `result.report.first_failure`。若存在，停止依赖步骤。
7. 根据 `result.report.solution` 和失败证据生成修复方案。
8. 切换到编码模式，修复确定性缺陷，编译，重跑。
9. 将通过的脚本保存在项目根目录 `Tests\<测试类型>\` 下，
   将有用的事故恢复存入 `experience`。

## 关联文档

- `delphi://automation/script-schema` — 创建或编辑脚本前必读。
- `delphi://automation/script-generation-workflow` — 从源码推导脚本时必读。
- `delphi://automation/report-schema` — 解释结果或生成测试报告时必读。
- `delphi://automation/inline-unit` — 将 Delphi 项目接入 `tools/auto` 时必读。
- `delphi://automation/repair-loop` — 运行失败且需修改代码时必读。

## 硬性规则

- 不得在 `assert_expr` 中写自然语言。
- 黑盒执行步骤不得使用 `rcall`、`rset` 或直接 RTTI 调用。
- 优先用 `rget/waitfor/msgscan` 做断言，而非纯视觉检查。
- 集合类控件（TCategoryButtons、TListBox 等）应使用基于标题的点击
  （`ControlName@ItemCaption`）而非坐标。仅在子项无稳定标题时回退到
  `ControlName@x,y`。
- 坐标点击应使用 `ControlName@x,y`，除非新版的独立 `x/y` 脚本字段有特殊需要。
- 不要在启动表单上盲目执行 `dumpstate/formsum`（含项目相关 getter 的表单）；
  先用 `listwnd`、`capture`、`rinspect` 或定向 `rget` 校准。使用 `dumpstate` 时，
  传入 `props` 白名单（如 `props=name,class,caption,enabled`）避免触发有问题的
  getter 并控制响应大小。
- 当 `action="auto"` 时，以 `resolved_action` 为准。
- 保持 `stop_on_failure=true`，除非明确是探索性任务。
- Delphi 源码编辑使用 `delphi_file`，然后用 `delphi_project` 编译。
- 前置步骤失败后不得继续后续自动化步骤。
