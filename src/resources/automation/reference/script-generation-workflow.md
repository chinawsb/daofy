---
name: delphi-automation-script-generation
description: >-
  从 Delphi 源码/DFM 分析生成自动化测试脚本。覆盖原生对话框处理、
  组合策略和模型-脚本通信。
---

# 脚本生成工作流

<!-- @when: 从 Delphi 源码/DFM 分析生成自动化脚本时 -->
<!-- @chain: after=workflow.md, before=script-schema.md -->

MCP resource URI: `delphi://automation/script-generation-workflow`。

## 核心原则

1. **源码驱动**：所有 target（控件名、属性路径）必须从 `.pas/.dfm` 源码提取，不得猜测或凭记忆。
2. **先读源文件 → 再写脚本**：生成脚本前必须读目标 `.pas` 和 `.dfm`。
3. **优先管道命令**：Delphi 进程内控件优先用管道 RTTI 命令（`rget`/`click`/`waitfor` 等）；无法覆盖时回退 `uia.xxx` 或 OCR。
4. **非注入黑盒**：`uia.xxx` 命令走 UIA 跨进程协议，不修改被测程序源码。

## 工作流

### Step 1: 读取源码

读 `.dfm` 和 `.pas`，提取以下信息：

| 源码元素 | 提取内容 | 脚本中使用 |
|----------|---------|-----------|
| `object BtnSave: TButton` | 名称 `BtnSave` | `target: "BtnSave"` |
| `Caption = '保存'` | 标题字符串 | `expected`、`assert_expr` |
| `OnClick = BtnSaveClick` | 事件处理程序名 | 通过 `StatusBar.Caption` 验证其触发 |
| `DataSource1.DataSet` | 数据绑定 | 保存后通过 `DataSource1.DataSet.Modified` 断言 |
| `TMyForm = class(TForm)` | 表单类名 | `goto "TMyForm"` |
| `ActionList / PopupMenu` | 命名动作/项 | `click "cbMenus@打开工程..."` |

**黑盒测试说明**：非侵入测试仅在脚本生成阶段读 `.dfm`/`.pas`。运行时脚本只能使用 `uia.xxx`/`click`/`type`/`key`/`waitfor`/`capture`——不得使用 RTTI 写命令（`rcall`/`rset`）。

### Step 2: 确定对话框策略

根据 UI 自动化决策流程选择测试中每个对话框或窗口的恰当命令。完整能力选型矩阵见 `delphi://automation/capability-matrix`。

### Step 3: 组装脚本

1. 指定 `App.exe` 路径。
2. 多步流程设置 `keep_alive=true`。
3. 步骤按 `phase: "perceive | execute | verify | wait | rebuild"` 编排。
4. 每个验证步骤添加 `expected` 说明和 `assert_expr`。
5. 通过的可复用脚本保存到被测项目根目录 `Tests\<测试类型>\` 下。

### Step 4: 执行

```python
automate_delphi(
    app_path="C:/App/App.exe",
    keep_alive=True,
    stop_on_failure=True,
    script=[...]
)
```

执行后检查：

```text
result.status
result.resolved_action
result.report.first_failure
result.report.solution
result.report.steps
```

失败信号应对：

| 信号 | 应对策略 |
|------|---------|
| `target_not_found` | 执行 `formsum/dumpstate`；更新脚本 target 或修复缺失控件 |
| `property_not_found` | 执行 `rinspect`；更新属性路径 |
| `assertion_failed` | 对比源码推导的预期行为与实际值 |
| `timeout` | 截取状态，执行 `msgscan/formsum`，再决定等待还是修复代码 |
| `command_error` | 检查 `response_data`；优先用低风险证据命令 |
| `capture_failed` | 检查 snapshots_dir 可写性；确保窗口可见 |
| `uia_error` | 执行 `uia.scan` 验证 UIA 树；用 inspect.exe 确认控件标识 |
| `uia_not_available` | `pip install daofy-for-delphi[uia]`，重启服务 |
| `skipped` | 修复前置失败后再重跑依赖步骤 |

若源码推导的预期行为未满足，切换到编码模式：

1. `get_coding_rules(section="writing")`
2. `delphi_file(action="read", ...)`
3. `delphi_file(action="write", edits=[...])`
4. `delphi_file(action="format", ...)`
5. `delphi_project(action="compile", project_path=...)`
6. 重跑同一自动化脚本

## 最终输出格式

向用户报告时包含：

```markdown
**脚本**
- 文件或内联步骤
- app_path 和 resolved_action

**运行结果**
- 总计/通过/失败/跳过
- 耗时
- 首个失败（若有）

**解决方案**
- 脚本调整或代码修复
- 具体的文件/命令变更

**验证**
- 编译结果
- 重跑结果
```
