<!-- @when: 编译通过后，需对 GUI 程序进行 UI 交互验证。首次接入自动化测试时按此流程操作 -->
<!-- @part-of: ui-testing -->
<!-- @chain: after=../../coding-rules/ui-testing.md, before=a-smoke.md -->

## 自动化测试基础设施

### 前置判断

执行以下检查以确定当前状态：

1. 读取目标项目的 `.dpr` 文件
2. 如果 `.dpr` 的 `uses` 中已包含 `Vcl.DaofyAutomation` 或 `Fmx.DaofyAutomation` → **跳过启用步骤**，直接执行脚本
3. 如果未包含 → 按下方「启用流程」操作

### 启用流程（AI 可执行）

#### 步骤 1：确认框架文件存在

检查 `tools/auto/` 下是否包含必需文件：

| 框架 | 必需文件 |
|------|---------|
| VCL | `DaofyAutomation.Base.pas` + `Vcl.DaofyAutomation.pas` |
| FMX | `DaofyAutomation.Base.pas` + `Fmx.DaofyAutomation.pas` |
| callgraph optional | `DaofyAutomation.CallGraph.pas` + `tools\stacktrace\StackTrace.pas` |

> ⚠️ `DaofyAutomation.Base.pas` 是 VCL 和 FMX 的共同基础依赖，两个都必须引用。

如果文件不存在，检查 Daofy 安装目录是否正确，或从源码复制 `tools/auto/` 目录。

#### 步骤 2：修改 .dpr

**方式 A（推荐）：用 `in` 子句直接引用（最可靠，无需改 .dproj）**

```pascal
program MyApp;

uses
  Vcl.Forms,
  Vcl.DaofyAutomation in '$(DaofyRoot)\tools\auto\Vcl.DaofyAutomation.pas',
  DaofyAutomation.Base in '$(DaofyRoot)\tools\auto\DaofyAutomation.Base.pas',
  MainForm in 'MainForm.pas';

begin
  Vcl.DaofyAutomation.AutoStart;    // ← ⚠️ 必须在 Application.Initialize 之前
  Application.Initialize;
  Application.CreateForm(TMainForm, MainForm);
  Application.Run;
  Vcl.DaofyAutomation.AutoStop;
end.
```

FMX 版本：

```pascal
uses
  FMX.Forms,
  Fmx.DaofyAutomation in '$(DaofyRoot)\tools\auto\Fmx.DaofyAutomation.pas',
  DaofyAutomation.Base in '$(DaofyRoot)\tools\auto\DaofyAutomation.Base.pas';
```

**方式 B（如已配搜索路径，或项目不允许 `in` 子句）**

将 `tools/auto` 目录加入项目搜索路径（IDE: Project → Options → Delphi Compiler → Search path），
如果需要 `callgraph`/`callgraph_diff`/`callgraph_path`/`callgraph_impact` 及用途层 `callgraph_*` 可选诊断命令，还需加入 `tools/stacktrace` 并在项目 `uses` 中增加 `DaofyAutomation.CallGraph`。`callgraph` 支持 `direction=callees|callers`、`project_only`、`exclude_prefixes`、`include_prefixes`、`edge_limit`，响应包含 `edge_count`、`returned_count`、`truncated`，每条边包含 `call_addr`、`call_file`、`call_line`、`category`、`from_category`、`to_category`；`callgraph_path` 接收 `source`、`target`、`max_depth`、`max_paths`、`include_prefixes`，返回 `found` 和 `paths`；`callgraph_diff` 用 baseline JSON 或 `baseline_path` 快照文件对比当前调用边变化，默认 `compare_by=name`，可选 `addr|full`，并可用 `save_as` 保存当前快照；`save_as` 必须是 `snapshots_dir` 下的相对 JSON 路径，读取型快照路径必须 resolve 后仍在 `snapshots_dir` 内；`callgraph_impact` 接收 `functions`/`targets` 或 `file`+`line`/`locations`，批量查询 callers 并汇总入口候选和 unresolved。用途层命令包括测试选择、失败诊断、边界检查、重构检查、孤岛候选和异常栈解释。
然后 `.dpr` 中只需单元名，无需 `in` 子句：

```pascal
uses
  Vcl.Forms,
  Vcl.DaofyAutomation;          // ← 依赖搜索路径解析
```

> 方式 A 不需要动 .dproj 配置，对任意环境都可靠，AI 可直接用 `delphi_file(action="write", edits=[...])` 修改 `.dpr`。如果项目已有搜索路径体系且不接受 `in` 子句，改用方式 B 但需要人为确认搜索路径添加无误。

#### 步骤 3：编译验证

```python
delphi_project(action="compile", project_path="MyApp.dproj")
```

确认 0 error 0 warning。

#### 步骤 4：冒烟测试

启动目标程序，用 `automate_delphi` 发送一条简单命令验证管道通信：

```python
automate_delphi(
    app_path="C:\MyApp\Win32\Debug\MyApp.exe",
    keep_alive=True,
    script=[
        {"cmd": "goto", "target": "TMainForm"},
        {"cmd": "capture", "target": "smoke_001"},
        {"cmd": "exit"}
    ]
)
```

如果返回 `"status": "ok"` 且截图文件生成 → **启用成功**。

#### 常见失败恢复

| 失败现象 | 原因 | AI 处理动作 |
|----------|------|------------|
| `File not found: 'DaofyAutomation.Base.pas'` | 搜索路径未包含 `tools/auto` | 检查搜索路径配置；或改用方式 B `in` 子句 |
| `automate_delphi` 返回 `target_not_found` | 窗体类名不匹配 | 先用 `{"cmd": "listwnd"}` 扫描实际窗体列表，取返回的 class 修正 target |
| `automate_delphi` 连不上管道（超时） | AutoStart 未调用，或被异常跳过 | 读 `.dpr` 确认 AutoStart 在 `Application.Initialize` 前；或 exe 启动后手动等 1-2 秒 |
| 编译报 `Duplicate resource` | `in` 子句和搜索路径双重引用导致重复编译 | 删除 `in` 子句，统一用搜索路径 |

#### 管道建立失败诊断

当 `automate_delphi` 连接管道超时或失败时，按以下流程诊断。**注意：管道失败时 `listwnd`/`formsum`/`dumpstate` 等管道命令不可用，必须走 Python UIA（`uia.xxx`）。**

```
管道失败
  │
  ├─ 检查进程是否存在（tasklist / PowerShell Get-Process）
  │
  ├─ 进程不存在（启动失败或已崩溃）
  │   │
  │   └─ 检查 exception.log
  │       ├─ 存在 → 读取 StackTrace 输出，定位崩溃原因（异常类名+出错行号）
  │       └─ 不存在 → 进程未启动成功，检查：
  │           ├─ exe 路径是否正确
  │           ├─ 缺少 DLL 依赖（用 dumpbin / Dependencies 工具检查）
  │           └─ Windows Defender / 杀毒软件拦截
  │
  └─ 进程存在但管道不通（AutoStart 未调用或管道名不匹配）
      │
      ├─ 1. uia.scan 扫描顶层窗口，确认程序界面已加载
      │     {"cmd": "uia.scan", "depth": 2, "props": "name,class,rect"}
      │
      ├─ 2. uia.screenshot 截图 + OCR 识别报错信息
      │     {"cmd": "uia.screenshot", "path": "pipe_fail_diag.png"}
      │     → daofy_ocr(action="recognize", image_path="pipe_fail_diag.png")
      │
      └─ 3. 根据 OCR 结果判断：
            ├─ 识别到异常对话框 → 截图作为证据，分析异常内容
            ├─ 识别到权限/UAC 弹窗 → 需要管理员权限运行
            └─ 界面正常但管道不通 → 读 .dpr 确认 AutoStart 在 Application.Initialize 前
```

**诊断工具对照**：

| 场景 | 可用工具 | 不可用工具 |
|------|---------|-----------|
| 进程不存在 | `tasklist`, `powershell Get-Process`, 读 `exception.log` | 管道命令全部不可用 |
| 进程存在+管道失败 | `uia.scan`, `uia.screenshot`, `uia.goto`, OCR | `listwnd`, `formsum`, `dumpstate`, `rget` |
| 管道正常 | 所有命令 | — |

**快速检查脚本**（Python 侧）：
```python
import subprocess, os
# 检查进程是否存在
result = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe_name}"], 
                       capture_output=True, text=True)
if exe_name not in result.stdout:
    # 进程不存在，检查 exception.log
    log_path = os.path.join(exe_dir, "exception.log")
    if os.path.exists(log_path):
        # 读取 StackTrace
        with open(log_path, encoding="utf-8", errors="replace") as f:
            print(f.read())
else:
    # 进程存在，走 UIA 诊断
    # uia.scan → uia.screenshot → OCR
    pass
```

### 工具调用

```python
automate_delphi(app_path="App.exe", script=[...])
automate_delphi(action="gui", app_path="App.exe", script=[...])
automate_delphi(action="auto", app_path="App.exe", script="script.json", keep_alive=True)
```
`action="auto"` 自动检测 PE 头 Subsystem 字段（GUI vs Console）。

`action="console"` 用于控制台程序 stdin/stdout 交互，无需 Delphi 端改造。

### 通信架构

```
Python                              Delphi
  ── CreateFile(\\.\pipe\daofy_auto) → 管道线程接收 JSON
  ── WriteFile(JSON request)        → 主线程执行
  ←── ReadFile(JSON response)       ← 返回结果/ACK
```

### 命令同步/异步分类

| 同步 | 异步 |
|------|------|
| goto, capture, dumpstate, listwnd, formsum | click, rclick, dblclick |
| wait, waitfor, dlgscan, msgscan, msgclose | hover, move, drag |
| dlgfile, snapdir, exit | type, key |
| rget, rinspect | rcall, rset, msgclick, dlgclick |

### keep_alive

- `keep_alive=True` 进程保持运行，5 分钟未用自动清理
- 新建进程首次调用自动设置 `snapdir`
- 返回 `process_reused` / `process_alive` 字段让 AI 感知状态

### 协议

- 同步命令阻塞等待返回；异步立即 ACK
- 响应：`{"reqId":"step_0","status":"ok","data":"OK"}`
- >64KB 自动分块（ERROR_MORE_DATA 循环读）

### 测试场景总览

场景文件索引见 [index.md](../index.md)。各场景文件提供策略描述 + 可复用 JSON 模板。
