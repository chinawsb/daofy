<!-- @when: 编写或修改 automate_delphi GUI 脚本时 -->
<!-- @chain: after=script-generation-workflow.md -->

# 自动化脚本格式规范

传给 `automate_delphi(action="gui", script=...)` 的脚本可以是：

- 包含 `steps` 数组的完整脚本对象；
- 直接传 step 对象数组；
- 以上任一种形状的 JSON 字符串或文件路径。

保存可复用脚本时推荐使用完整对象，Daofy 会将 `steps` 之外的字段保留为 `script_metadata` 供执行结果使用。

MCP resource URI: `delphi://automation/script-schema`。

## 脚本元数据

可复用脚本应声明测试级别：

```json
{
  "test_name": "customer-create-smoke",
  "test_level": "black-box",
  "callgraph_diagnostics": false,
  "env": {
    "DEEPSEEK_API_KEY": "temporary value for this run"
  },
  "steps": []
}
```

`env` / `environment` are optional top-level script fields for temporary child-process
environment overrides. They are applied only when the tested application process is
started, are not persisted to User/Machine environment variables, and returned reports
redact values to `{count, names}`. Passing `null` unsets an inherited variable for the
tested process. With `keep_alive=true`, a cached tested process is reused only when the
requested environment is the same; changing `env` restarts the tested process.

测试级别说明：
- `black-box` — 通过可见 UI 入口的真实用户工作流。
- `gray-box` — 使用 RTTI 读取/调用做诊断、夹具或项目特定探测。
- `white-box` — 直接检查业务方法或数据层。

黑盒 `execute` 步骤不得使用 `rcall`、`rset` 或 `delphi_rtti(action="call")`。这些命令绕过了真实 UI 路径。如果脚本需要它们，标记为 `gray-box` 或 `white-box` 并在 `goal` 或 `note` 中说明原因。

**合规检查**：执行 `grep 'rcall' tests/**/*.json` 确认无黑盒脚本包含 RTTI 执行命令。零匹配即合规。

`callgraph_diagnostics=true` 时，失败步骤若声明 `handler` / `entry` / `callgraph_target`，Daofy 会在自动退出前追加一次 `callgraph(direction=callers)` 查询，并把摘要写入 `report.first_failure.diagnostics.callgraph`。默认关闭，避免普通 UI 测试额外消耗。

可选全局配置：

```json
{
  "callgraph_diagnostics": true,
  "callgraph_options": {
    "max_depth": 2,
    "edge_limit": 20,
    "project_only": true,
    "include_prefixes": ["main."]
  },
  "steps": [
    {"cmd": "click", "target": "btnSave", "handler": "main.TfrmMain.SaveIfModified"}
  ]
}
```

## 步骤字段

```json
{
  "phase": "perceive | execute | verify",
  "cmd": "rget",
  "target": "BtnSave.Caption",
  "handler": "main.TfrmMain.SaveIfModified",
  "expected": "保存按钮标题正确",
  "assert_expr": "actual == '保存'",
  "note": "供人类和 AI 规划查看的说明"
}
```

字段说明：
- `phase` — 用于报告分组。
- `cmd` — Daofy 自动化命令。
- `target` 和命令特定字段（`prop`、`value`、`timeout`、`text`、`params`、`props` 等）。
- `expected` — 人工可读的预期行为。
- `assert_expr` — Daofy 评估的 Python 断言表达式。
- `note` — 推理过程或源码推导的上下文。
- `handler` / `entry` / `callgraph_target` — 可选源码入口函数名，用于失败报告附加 callgraph 诊断和测试选择。
- `callgraph_diff` 步骤可使用 `baseline` 或 `baseline_path`、`compare_by=name|addr|full`、`save_as`；`save_as` 必须是 `snapshots_dir` 下的相对 JSON 路径，`baseline_path` 等文件型快照输入必须 resolve 后仍在 `snapshots_dir` 内。
- `cmd` 带 `uia.xxx` 前缀时通过 Python UIA（uiautomation 库）执行，不走 Delphi 管道。所有 `uia.xxx` 命令运行在 Python 进程内，可访问任何 UIA 兼容控件——Delphi、Win32、WPF、Qt、Chrome、系统对话框等。**非注入黑盒**：无需修改被测程序源码。
  > `via` 字段（旧方案）已废弃，统一使用 `uia.xxx` 命令前缀。迁移期兼容 `via: "uia"`，但新脚本禁用。

> 完整 UIA 命令表见 `delphi://automation/uia-commands`。

### dumpstate 属性白名单

`dumpstate` 接受 `props` 参数（逗号分隔的属性名列表），Delphi 内联单元仅输出这些属性（跳过 `IsSkippedProp` 黑名单）。避免管道溢出并加速响应：

```json
{"cmd": "dumpstate", "props": "caption,enabled"}
{"cmd": "dumpstate", "props": "name,class,caption,items"}
{"cmd": "dumpstate"}  // 默认输出全部属性
```

使用 Daofy MCP 工具时，`props` 从步骤 JSON 转发到 Delphi 管道。对于仅发 `cmd`/`target` 的工具，属性列表可通过 `target` 字段传递：

```json
{"cmd": "dumpstate", "target": "caption,enabled"}
```

### 通用 RTTI 项点击

`click` 支持 `ControlName@ItemCaption` 语法，通过泛型 RTTI 查找并点击任何 `TCollection` 属性的项，无需计算坐标：

```json
{"cmd": "click", "target": "cbMenus@打开工程..."}
```

Delphi 内联单元使用纯 RTTI 读取每项的 `Caption`（或回退到 `Text`）和 `Bounds`（Left/Top/Right/Bottom），然后点击匹配项的中心。无需 VCL 类型绑定，任何基于 `TCollection` 的控件均支持。

### 坐标点击

坐标点击的坐标为相对于目标控件的客户区坐标。推荐使用 `"target": "ControlName@x,y"` 格式以便脚本可复用——Delphi 内联单元直接识别。新版 Daofy 也接受 `click` 的 `"target": "ControlName", "x": 10, "y": 20` 格式并自动转换为相同线协议。

**优先使用基于标题的点击**（菜单、列表、分类按钮等集合类控件），其对布局变化和 DPI 缩放的鲁棒性更好。

## 断言规则

`assert_expr` 是可在 Python 中求值的表达式，`__builtins__` 为空，显式可用变量：

| 变量 | 含义 |
|------|------|
| `actual` | 从命令响应提取的字符串值 |
| `re` | Python `re` 模块 |
| `len`、`str`、`int`、`float`、`bool` | 显式提供的辅助函数 |

示例：

```json
{"cmd": "rget", "target": "EditName.Text", "assert_expr": "actual == '张三'"}
{"cmd": "rget", "target": "BtnSave.Enabled", "assert_expr": "actual == 'True'"}
{"cmd": "waitfor", "target": "StatusBar", "prop": "Caption", "value": "完成", "assert_expr": "actual == 'ok'"}
{"cmd": "rget", "target": "PhoneEdit.Text", "assert_expr": "re.search(r'^1\\\d{10}$', actual)"}
```

禁止在 `assert_expr` 中写自然语言。将说明文字放在 `expected` 中，添加真实的验证步骤：

```json
{"cmd": "msgscan", "expected": "无意外弹窗", "assert_expr": "actual == 'NOD'"}
```

`msgscan` 在无 MessageBox 时返回 `NOD`，有 MessageBox 时返回 `OK` 并将对话框 JSON 写入 `_formstate.json` 供 `response.state` 使用。

## OCR / 视觉验证

对于无法通过 `rget`/`msgscan` 读取的原生 OS 对话框或自绘控件，使用 `capture` + `daofy_ocr` 验证：

```json
{"cmd": "capture", "expected": "对话框截图供 OCR", "note": "执行后用 daofy_ocr recognize 读取"}
```

**选中行检测**（颜色阈值）：
- `capture` 后用 `daofy_ocr color region=[x,y,w,h] threshold=0.5`。
- `light_brightness` < 0.98 且无 `>` 展开符 = 选中。
- 最佳粒度：`8x8` 块，左边缘 `X=105`（避开文字干扰）。

完整原生对话框处理模式见 `delphi://automation/script-generation-workflow`。

## 缓存测试文件

可复用脚本保存到被测项目根目录：

```
<project-root>\Tests\<测试类型>\<测试名>.json
```

常用分类目录：`黑盒测试`、`回归测试`、`灰盒测试`、`白盒测试`、`冒烟测试`。

文件格式：

```json
{
  "test_name": "新建客户-成功路径",
  "app_path": "C:/App/CustomerApp.exe",
  "target_form": "TNewCustomerForm",
  "version": 1,
  "created": "2026-06-27T10:30:00",
  "updated": "2026-06-27T10:35:00",
  "run_count": 0,
  "source_hash": "a1b2c3d4e5f6a7b8",
  "source_files": ["UnitCustomer.pas", "UnitCustomer.dfm"],
  "steps": []
}
```
## Cached Test File

Persist reusable scripts under the tested project root:

```text
<project-root>\Tests\<测试类型>\<test-name>.json
```

Common test type directories are `黑盒测试`, `回归测试`, `灰盒测试`, `白盒测试`,
and `冒烟测试`. Choose the directory by the long-term rerun purpose.

Use this file shape:

```json
{
  "test_name": "新建客户-成功路径",
  "app_path": "C:/App/CustomerApp.exe",
  "target_form": "TNewCustomerForm",
  "version": 1,
  "created": "2026-06-27T10:30:00",
  "updated": "2026-06-27T10:35:00",
  "run_count": 0,
  "source_hash": "a1b2c3d4e5f6a7b8",
  "source_files": ["UnitCustomer.pas", "UnitCustomer.dfm"],
  "steps": []
}
```
