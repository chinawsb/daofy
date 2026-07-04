# 道飞自动化测试指南

大模型驱动的 Delphi 自动化测试框架。

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                     大模型 (LLM)                             │
│  分析需求 → 规划步骤 → 验证结果 → 生成报告                   │
└──────────┬──────────────────────────────────────┬──────────┘
           │ automate_delphi 工具                    │ delphi_file / ...
           ▼                                        ▼
┌──────────────────────┐              ┌──────────────────────┐
│    Python 服务层       │              │   辅助工具            │
│  automation_service   │              │   rget / rset /       │
│  ─ 进程池管理          │              │   delphi_kb 等        │
│  ─ 管道通信            │              │                      │
│  ─ ERROR_MORE_DATA    │              └──────────────────────┘
│    循环读取             │
└──────────┬────────────┘
           │ 命名管道 \\.\pipe\daofy_auto
           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Delphi 程序 (AUT)                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  DaofyAutomation 单元 (链接到被测程序)                │   │
│  │  ─ 管道线程 + JSON 协议                              │   │
│  │  ─ Vcl.DaofyAutomation / Fmx.DaofyAutomation         │   │
│  │  ─ RTTI 操作 (rget/rset/rcall/rinspect)              │   │
│  │  ─ 截图 (2D PaintTo / 3D GPU / 对话框 BitBlt)       │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 启用指南（给 Delphi 开发者）

> 本节面向 **需要在自己的 Delphi 项目中启用自动化测试的开发者**。
> 按步骤操作后，你的程序就可以被 `automate_delphi` 工具远程操控和测试。

### 前置文件清单

自动化框架文件位于 Daofy 安装目录下的 `tools/auto/`：

| 文件 | 必需？ | 用途 |
|------|--------|------|
| `DaofyAutomation.Base.pas` | ✅ 必需 | 命名管道协议、命令分发、异步结果缓存 |
| `Vcl.DaofyAutomation.pas` | VCL 项目必选 | VCL 控件查找、截图、RTTI 操作 |
| `Fmx.DaofyAutomation.pas` | FMX 项目必选 | FMX 控件查找、截图、RTTI 操作 |
| `DaofyAutomation.RttiDiscovery.pas` | 可选 | RTTI 能力发现（供 `delphi_rtti` 工具使用） |
| `DaofyAutomation.RttiAttributes.pas` | 可选 | AI 注解属性声明 |
| `DaofyAutomation.CallGraph.pas` + `StackTrace.pas` | 可选 | `callgraph` / `callgraph_diff` / `callgraph_path` / `callgraph_impact` 以及用途层 `callgraph_*` 诊断命令 |

> ⚠️ `DaofyAutomation.Base.pas` 必须同时被项目引用（VCL/FMX 单元依赖它）。

### 步骤一：将 `tools/auto` 添加到项目搜索路径

在 Delphi IDE 中打开项目 → **Project → Options → Delphi Compiler → Search path**，添加：

```
$(DaofyRoot)\tools\auto
```

若要使用 `callgraph`，再添加：

```
$(DaofyRoot)\tools\stacktrace
```

`callgraph` 支持 `direction=callees|callers`、`project_only=true`、`exclude_prefixes`、`include_prefixes` 过滤和 `edge_limit` 输出上限；响应包含 `edge_count`、`returned_count`、`truncated`，每条边包含 `call_addr`、`call_file`、`call_line` 用于定位调用发生处（无行号信息时为空/0），并包含 `category`、`from_category`、`to_category`（`project|thirdparty|framework|system|unknown`）。`callgraph_path` 接收 `source`、`target`、`max_depth`、`max_paths`、`include_prefixes`，返回 `found` 和 `paths`，找不到路径不是错误；`callgraph_diff` 使用 baseline JSON 或 `baseline_path` 快照文件与当前调用图做边级 added/removed/unchanged 对比，默认 `compare_by=name` 避免重编译地址漂移，必要时可用 `compare_by=addr|full`，并可用 `save_as` 保存当前快照；`save_as` 必须是 `snapshots_dir` 下的相对 JSON 路径，`baseline_path` 及用途层命令的文件型 graph/impact 输入也必须 resolve 后仍在 `snapshots_dir` 内。`callgraph_impact` 接收 `functions`/`targets`、`file`+`line`/`locations`，也接收 PR/diff 风格 `changes`（每项可含 `function` 或 `file`+`start_line/new_line/line`），批量查询 callers 并汇总入口候选和 unresolved。`callgraph_select_tests` 的脚本元数据可用 `handler`/`entry`、`tags`、`covers`/`functions`/`targets` 显式声明覆盖范围。`callgraph_boundary_check` 支持 `from_prefix`/`to_prefix` 禁止规则、`exclude_from_prefixes`/`exclude_to_prefixes` 例外和 `severity`/`message` 输出。用途层命令还包括 `callgraph_failure_diag`、`callgraph_refactor_check`、`callgraph_orphan_candidates`、`callgraph_explain_exception`。

或用相对路径（假设 Daofy 与项目同级）：

```
..\daofy\tools\auto
```

> **为什么？** 将目录加入搜索路径后，`.dpr` 中不需要写冗长的 `in 'path\to\xxx.pas'`，只需写 `uses Vcl.DaofyAutomation;`。所有自动化单元会自动解析。

### 步骤二：修改 `.dpr` 文件

在 `program` 的 `uses` 中添加自动化单元，在 `begin..end.` 块中添加 `AutoStart`/`AutoStop` 调用：

```pascal
program MyApp;

uses
  Vcl.Forms,
  Vcl.DaofyAutomation,          // ← 添加（已配置搜索路径，无需 in 子句）
  MainForm in 'MainForm.pas';

begin
  Vcl.DaofyAutomation.AutoStart;    // ← 添加：创建命名管道 \\.\pipe\daofy_auto
  Application.Initialize;
  Application.CreateForm(TMainForm, MainForm);
  Application.Run;
  Vcl.DaofyAutomation.AutoStop;     // ← 添加：清理管道资源
end.
```

**FMX 项目**请使用 `Fmx.DaofyAutomation`：

```pascal
uses
  FMX.Forms,
  Fmx.DaofyAutomation;          // ← FMX 版本

begin
  Fmx.DaofyAutomation.AutoStart;
  Application.Initialize;
  Application.CreateForm(TMainForm, MainForm);
  Application.Run;
  Fmx.DaofyAutomation.AutoStop;
end.
```

> ⚠️ `AutoStart` **必须在** `Application.Initialize` **之前**调用，确保管道在线程启动阶段就绪。

### 步骤三：编译并验证管道就绪

```bash
# 在 IDE 中编译（Ctrl+F9），或在命令行中：
dcc32 MyApp.dproj
```

启动编译后的 exe：

```bash
MyApp.exe
# 控制台程序输入：MyApp.exe arg1 arg2
```

验证命名管道已创建：

```powershell
# 使用 PowerShell 检查管道是否存在
[System.IO.Directory]::GetFiles("\\.\\pipe\\").Where({$_ -match "daofy_auto"})
```

如果输出包含 `daofy_auto`，说明自动化单元已成功接入。

### 步骤四：运行冒烟测试确认可通信

通过 `automate_delphi` 工具发送一条简单的 `goto` + `capture` 命令，验证完整链路：

```python
automate_delphi(
    app_path="C:\MyApp\Win32\Debug\MyApp.exe",
    keep_alive=True,
    script=[
        {"cmd": "goto", "target": "TMainForm", "note": "确认主窗体就绪"},
        {"cmd": "capture", "target": "smoke_001"},
        {"cmd": "exit"}
    ]
)
```

**期望结果**：
- 返回 `status: "ok"`，`process_alive: false`（exit 后退出）
- `docs/copyright/snapshots/` 目录下生成 `smoke_001.jpg`

如果收到 `target_not_found`，先用 `listwnd` 查看实际窗体类名：

```python
automate_delphi(
    app_path="C:\MyApp\Win32\Debug\MyApp.exe",
    script=[{"cmd": "listwnd"}]
)
```

### 验证检查清单

```
[ ] tools/auto/ 的 3 个核心 .pas 文件存在且可读
[ ] 搜索路径已包含 tools/auto 目录
[ ] .dpr 文件中已添加 Vcl.DaofyAutomation / Fmx.DaofyAutomation
[ ] AutoStart 调用在 Application.Initialize 之前
[ ] 编译通过（0 error, 0 warning）
[ ] 进程启动后命名管道 \\.\pipe\daofy_auto 已创建
[ ] automate_delphi 冒烟测试返回 status=ok
```

### 常见集成问题

| 问题 | 原因 | 修复 |
|------|------|------|
| 编译报错 `File not found: 'DaofyAutomation.Base.pas'` | 搜索路径未包含 `tools/auto` | 检查 Project Options → Search path |
| 编译报错 `Duplicate resource` | dpr 中 `in` 子句和搜索路径双重引用 | 统一用搜索路径，删除 `in` 子句 |
| 进程启动但 `automate_delphi` 连不上管道 | AutoStart 未调用或被异常跳过 | 在 `Application.Initialize` 前确认 `AutoStart` 执行 |
| Windows 防火墙弹窗 | exe 首次侦听管道 | 允许私网访问 |
| FMX 启动崩溃 | 缺少 FMX 运行时 DLL | 确保 PATH 含 FMX 运行时目录，或启用静态链接 |

---

## 快速开始（给 AI 代理）

> 以下内容供 AI 代理在完成启用步骤后，编写和执行自动化测试脚本。

---

## 命令参考

### 导航
```json
{"cmd": "goto", "target": "TMainForm"}
```
激活指定类名或 Name 的窗体。

### 鼠标操作
```json
{"cmd": "click", "target": "BtnSave"}                  // RTTI 点击
{"cmd": "click", "target": "ListBox1@5,5"}             // 坐标点击（相对控件）
{"cmd": "rclick", "target": "EditName"}                // 右键弹出菜单
{"cmd": "dblclick", "target": "ListItem1"}             // 双击
{"cmd": "hover", "target": "Panel1"}                   // 悬停
{"cmd": "move", "target": "BtnSave"}                   // 移动鼠标到控件中心
{"cmd": "move", "x": "500", "y": "300"}                // 移动鼠标到屏幕坐标
{"cmd": "drag", "source": "Slider1", "target": "TrackBar1"}  // 拖拽到目标控件
{"cmd": "drag", "source": "Header1", "x": "500", "y": "300"} // 拖拽到坐标
```

### 键盘操作
```json
{"cmd": "type", "target": "EditName", "value": "张三"}        // 输入文本
{"cmd": "key", "target": "EditName", "key": "Tab"}            // 按键
{"cmd": "key", "key": "Enter"}
{"cmd": "key", "key": "Esc"}
{"cmd": "key", "key": "F5"}
```
支持的键名：`Tab`, `Enter`, `Esc`, `Back`, `Del`, `Home`, `End`,
`Up`, `Down`, `Left`, `Right`, `Space`, `F1`~`F12`, 单字符。

### 等待
```json
{"cmd": "wait", "ms": "2000"}                                          // 固定等待
{"cmd": "waitfor", "target": "BtnSave", "prop": "Enabled",            // 等条件满足
                  "value": "True", "timeout": "5000", "interval": "100"}
```
`timeout` 默认 5000ms，`interval` 默认 100ms。支持嵌套属性：
```json
{"cmd": "waitfor", "target": "ListBox1", "prop": "Items.Count", "value": "10", "timeout": "3000"}
```

### 截图
```json
{"cmd": "capture", "target": "test_001"}
```
截图保存到 `snapshots_dir/{target}.jpg`。内部自动选择最佳方式：

| 场景 | 方式 |
|------|------|
| MessageBox/TaskDialog 弹窗 | `FindWindowW('#32770')` → GDI BitBlt → JPEG |
| FMX 模态对话框 | `TFmxFormState.Modal` 检测 → PaintTo |
| FMX 3D 窗体 | `TContext3D.CopyToBitmap` GPU readback |
| FMX 2D 窗体 | `TCustomForm.PaintTo(Canvas)` |
| VCL 窗体 | `GetWindowDC` + GDI BitBlt |

### 窗口枚举
```json
{"cmd": "listwnd"}
```
返回所有窗口的 name/class/caption/active 状态：
```json
{"status": "ok", "data": "{\"windows\":[{\"name\":\"Form1\",\"class\":\"TForm1\",\"caption\":\"MyApp\",\"active\":\"true\"}]}"}
```

### 全量控件树
```json
{"cmd": "dumpstate"}
```
通过管道返回完整控件树 JSON（含所有控件的属性），不再写文件。

### 弹出菜单
```json
{"cmd": "dlgscan"}           // 扫描弹出菜单项
{"cmd": "dlgclick", "target": "复制"}  // 点击菜单项
```

### MessageBox / 对话框
```json
{"cmd": "msgscan"}                              // 扫描弹窗
{"cmd": "msgclick", "target": "ok"}             // 点按钮（支持 TaskDialog）
{"cmd": "msgclose", "target": "DaofyAuto"}      // 关闭弹窗（按标题匹配）
{"cmd": "dlgfile", "path": "C:\\test.txt", "target": "open"}   // 文件对话框
{"cmd": "dlgfile", "target": "cancel"}          // 取消文件对话框
```

### RTTI 操作
```json
{"cmd": "rget", "target": "EditName", "prop": "Text"}                        // 读属性
{"cmd": "rget", "target": "ListBox1", "prop": "Items.Count"}                 // 嵌套属性
{"cmd": "rset", "target": "EditName", "prop": "Text", "value": "Hello"}      // 写属性
{"cmd": "rcall", "target": "EditName", "method": "Clear"}                    // 调用无参方法
{"cmd": "rcall", "target": "ListBox1", "method": "Items.Add",               // 调用带参方法
         "params": ["Hello"]}
{"cmd": "rcall", "target": "Form1", "method": "Close"}                      // 关闭窗体
{"cmd": "rinspect", "target": "EditName"}                                    // 检视成员列表
```

### 进程管理
```json
{"cmd": "snapdir", "target": "D:\\screenshots\\"}    // 设置截图目录
{"cmd": "exit"}                                        // 退出程序
```

---

## 进程复用模式

**问题**：每次调用 `automate_delphi` 都要启动 exe、等管道初始化、执行、退出——重复开销大。

**解决**：`keep_alive=true` 让进程常驻：

```
# 第一次：启动并保持
automate_delphi(app_path="MyApp.exe", script=[goto, capture], keep_alive=true)
→ 返回 process_reused:false, process_alive:true

# 第二次：复用已有进程
automate_delphi(app_path="MyApp.exe", script=[click, capture])
→ 返回 process_reused:true, process_alive:true

# 最后：发送 exit 终止
automate_delphi(app_path="MyApp.exe", script=[exit])
→ 返回 process_alive:false
```

进程池自动管理：
- 同一 `app_path` 自动复用
- **5 分钟无调用**自动 `kill()`
- 进程崩溃后下次调用自动重启
- 返回 `process_reused` / `process_alive` 字段让 AI 感知状态

---

## 自动化测试流程模板

### 基本流程
```
1. 启动程序（keep_alive=true）
2. goto 激活目标窗体
3. listwnd / dumpstate 了解当前界面结构
4. 执行测试操作（click / type / key / rcall）
5. 截图或 rget 验证结果
6. `waitfor` 等待异步操作完成
7. 重复 4-6 直到测试结束
8. exit 退出
```

### 实际示例

```python
# 模拟用户登录
脚本 = [
    {"cmd": "goto", "target": "TLoginForm"},
    {"cmd": "type", "target": "EditUser", "value": "admin"},
    {"cmd": "key", "target": "EditPwd", "key": "Tab"},
    {"cmd": "type", "target": "EditPwd", "value": "123456"},
    {"cmd": "click", "target": "BtnLogin"},
    {"cmd": "waitfor", "target": "StatusBar", "prop": "Caption",
     "value": "登录成功", "timeout": "5000"},
    {"cmd": "rget", "target": "StatusBar.Caption", "assert_expr": "actual == '登录成功'"},
    {"cmd": "capture", "target": "login_result"},
]

# 验证列表加载
脚本2 = [
    {"cmd": "waitfor", "target": "ListView1", "prop": "Items.Count",
     "value": "10", "timeout": "5000"},
    {"cmd": "rget", "target": "ListView1", "prop": "Items[0].Caption"},
]
```

---

## 报告与修复闭环

`automate_delphi` 返回的 `report` 是后续决策入口：

```json
{
  "status": "partial",
  "resolved_action": "gui",
  "report": {
    "first_failure": {
      "index": 3,
      "cmd": "rget",
      "target": "StatusBar.Caption",
      "signal": "assertion_failed"
    },
    "solution": {
      "next_mode": "coding",
      "recommendations": [
        "Compare actual with expected and decide whether the app logic or the test expectation is wrong."
      ]
    }
  }
}
```

处理规则：

1. `report.first_failure != null` 时停止后续依赖步骤。
2. `signal` 是 `target_not_found/property_not_found` 时先用 `formsum/rinspect` 修脚本。
3. `signal` 是 `assertion_failed/timeout/command_error` 且预期来自源码分析时，切回编码模式：`get_coding_rules(section="writing")` → `delphi_file` 修代码 → `delphi_project(action="compile")` → 重新执行脚本。
4. 修复后保存通过脚本到 `tests/scripts/`，保存可复用经验到 `experience`。

默认 `stop_on_failure=true`。首个失败后的步骤不会继续操作 UI，而是在 `report.steps` 中标为 `skip`；需要一次性探索全部步骤时才显式传 `stop_on_failure=false`。

需要源码影响面时，可在完整脚本对象中启用：

```json
{
  "callgraph_diagnostics": true,
  "callgraph_options": {"max_depth": 2, "edge_limit": 20, "project_only": true},
  "steps": [
    {"cmd": "click", "target": "btnSave", "handler": "main.TfrmMain.SaveIfModified"}
  ]
}
```

失败步骤会在自动 `exit` 前追加一次 `callgraph(direction=callers)`，并把摘要写入 `report.first_failure.diagnostics.callgraph`。如果 callgraph 查询失败，只记录二级 warning，不覆盖原始 UI 失败原因。

---

## 各框架差异说明

| 特性 | VCL | FMX 2D | FMX 3D |
|------|-----|--------|--------|
| 截图 | GDI BitBlt | PaintTo | CopyToBitmap |
| 控件查找 | FindChildControl | FindComponent | FindComponent |
| 右键菜单 | TPopupMenu | TPopupMenu(手动扫) | TPopupMenu(手动扫) |
| 点击 | SendMessage BM_CLICK | RTTI Click / OnClick | RTTI Click / OnClick |
| 坐标点击 @x,y | SendMessage WM_LBUTTONDOWN | FormToHWND + SendMessage | FormToHWND + SendMessage |
| 类型转换接口 | 通用 | 通用 | 通用 |

---

## 调试技巧

1. **先 `listwnd` 再操作**：查看当前有哪些窗体可用，确认窗体名
2. **`rinspect` 了解控件**：查看控件有哪些方法和属性
3. **`dumpstate` 获取全量状态**：排查控件属性值
4. **`capture` 直观验证**：截图确认界面状态
5. **`rget` 断言**：AI 自行比较预期值
6. **`waitfor` 替代固定 wait**：减少等待时间，提高稳定性
7. **进程残留**：检查 `process_alive` 字段，定期 exit

---

## 常见问题

**Q: `waitfor` 一直超时返回 TIMEOUT？**  
A: 检查 `prop` 属性名是否正确，先用 `rget` 确认。

**Q: `msgclick` 关不掉弹窗？**  
A: FMX 的 MessageDlg 在 Windows 上创建 TaskDialog（`#32770`），`msgclick` 找的是 `#32770` 类窗口。确认弹窗类型。

**Q: FMX exe 启动时报找不到文件？**  
A: FMX 运行时 DLL 需要能被进程找到。确保 PATH 环境变量包含 FMX 运行时目录，或使用静态链接。

**Q: `click` 点了但没反应？**  
A: 检查目标控件名是否正确，先用 `rinspect` 查看控件是否有 `Click` 方法或 `OnClick` 事件。

**Q: FileNotFoundError 启动失败？**  
A: FMX 项目需确保 Win32\Debug\ 目录下有 FMX 依赖的 DLL（如 `fmx260.bpl`）。可以试试用 VCL 测试项目验证基础功能。
