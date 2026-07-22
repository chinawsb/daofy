<!-- @when: 分析 automate_delphi 返回的测试报告时 -->
<!-- @chain: after=script-schema.md, before=repair-loop.md -->

# 自动化测试报告结构

`automate_delphi(action="gui", ...)` 返回的 `report` 结构足以驱动修复循环。

MCP resource URI: `delphi://automation/report-schema`。

## 重要字段

```json
{
  "status": "partial",
  "requested_action": "auto",
  "resolved_action": "gui",
  "detected_subsystem": 2,
  "report": {
    "total": 3,
    "passed": 1,
    "failed": 1,
    "skipped": 1,
    "executed": 2,
    "duration_seconds": 6.21,
    "success_rate": "33%",
    "executed_success_rate": "50%",
    "first_failure": {
      "index": 1,
      "phase": "verify",
      "cmd": "rget",
      "target": "BtnSave.Caption",
      "signal": "assertion_failed",
      "expected": "保存按钮标题正确",
      "diagnostics": {
        "callgraph": {
          "target": "main.TfrmMain.SaveIfModified",
          "direction": "callers",
          "status": "ok",
          "edge_count": 1,
          "returned_count": 1,
          "truncated": false
        }
      },
      "assertion": {
        "expression": "actual == '保存'",
        "source": "assert_expr",
        "actual": "取消",
        "message": "assert failed: actual == '保存'  (actual='取消')"
      },
      "recommendations": []
    },
    "solution": {
      "status": "requires_fix",
      "next_mode": "coding",
      "summary": "修复首个确定性失败，然后从失败步骤重跑此脚本。",
      "recommendations": []
    },
    "steps": [
      {"index": 0, "cmd": "goto", "status": "pass"},
      {"index": 1, "cmd": "rget", "status": "fail"},
      {"index": 2, "cmd": "click", "status": "skip"}
    ]
  }
}
```

## RTTI 测试任务结果

`automate_delphi(action="test", ...)` 先返回 `status="submitted"` 和 `task_id`。通过
`async_task(action="result")` 取得的任务结果不使用 GUI `report` 包装，其稳定字段如下：

```json
{
  "status": "failed",
  "total": 4,
  "passed": 1,
  "failed": 2,
  "errors": 1,
  "duration_seconds": 0.475,
  "process_reused": false,
  "results": [
    {
      "index": 0,
      "id": "invalid-input",
      "className": "Tests.TCalculator",
      "method": "Parse",
      "status": "ok",
      "phase": "test",
      "exception_class": "EConvertError",
      "exception_message": "invalid value",
      "assert": "pass"
    }
  ],
  "raw_responses": []
}
```

- `passed`：方法完成且全部 Delphi/Python 断言通过。
- `failed`：返回值、`assert_expr` 或预期异常断言失败。
- `errors`：启动、传输、setup/构造、未预期 test 异常或 teardown 失败。
- `phase`：错误发生阶段，取 `prepare`、`setup`、`constructor`、`test` 或 `teardown`。
- `raw_responses`：逐例 Delphi 原始协议响应，仅用于诊断，不应替代稳定统计字段。

## 失败信号

| 信号 | 应对策略 |
|------|---------|
| `assertion_failed` | 对比源码推导的预期行为与实际 UI 状态 |
| `capture_failed` | 检查窗口可见性和截图目录 |
| `timeout` | 截取当前 UI，检查 `msgscan/formsum`，避免盲目重试 |
| `target_not_found` | 执行 `formsum/dumpstate`，更新目标名或修复缺失控件 |
| `property_not_found` | 执行 `rinspect`，更新属性路径 |
| `command_error` | 检查 `response_data`，截取状态，再决定修复代码还是脚本 |
| `skipped` | 前置步骤失败；修复首个失败后重跑 |

## 报告输出规范

呈现结果时需包含：

- 执行的 app 路径和 `resolved_action`。
- 通过/失败总数和耗时。
- `skipped` 数量（`stop_on_failure=true` 阻止了依赖步骤时）。
- 首个失败：`cmd`、`target`、`signal`、实际值、证据。
- 如果脚本启用了 `callgraph_diagnostics`：列出 `diagnostics.callgraph.target`、`direction`、`status`、`edge_count`、`truncated`。callgraph 查询失败只能作为 warning/secondary diagnostic，不得覆盖原始失败原因。
- 修复方案：调整自动化脚本还是修复代码。
- 精确的下个命令：重跑脚本、编译项目、或切换到编码规则。
