<!-- @when: 需将 Delphi 项目接入自动化框架，或了解命名管道协议 -->
<!-- @chain: after=workflow.md -->

# Delphi 内联自动化单元

Delphi 端代码位于 `tools/auto`。

MCP resource URI: `delphi://automation/inline-unit`。

## 文件清单

| 文件 | 功能 |
|------|------|
| `DaofyAutomation.Base.pas` | 命名管道协议、命令分发、共享 Win32 命令、异步结果缓存 |
| `Vcl.DaofyAutomation.pas` | VCL 控件查找、截图、RTTI 操作 |
| `Fmx.DaofyAutomation.pas` | FMX 控件查找、截图、RTTI 操作 |
| `DaofyAutomation.RttiDiscovery.pas` | 运行时 RTTI 能力发现 |
| `DaofyAutomation.RttiAttributes.pas` | 可选的 AI 注解属性声明 |
| `DaofyAutomation.CallGraph.pas` | 可选调用图命令扩展；需要同时将 `tools\stacktrace` 加入搜索路径 |

## 项目接入

VCL `.dpr` 示例：
```pascal
uses
  Vcl.Forms,
  Vcl.DaofyAutomation in 'C:\path\to\tools\auto\Vcl.DaofyAutomation.pas',
  MainForm in 'MainForm.pas' {MainForm};
begin
  Vcl.DaofyAutomation.AutoStart;
  Application.Initialize;
  Application.CreateForm(TMainForm, MainForm);
  Application.Run;
  Vcl.DaofyAutomation.AutoStop;
end.
```
FMX 使用 `Fmx.DaofyAutomation`。

建议将 `tools\auto` 加入项目搜索路径，避免在 `.dpr` 中罗列所有支持单元。若需要 `callgraph`/`callgraph_diff`/`callgraph_path`/`callgraph_impact` 及用途层 `callgraph_*` 命令，还需将 `tools\stacktrace` 加入搜索路径，并在项目中额外 `uses DaofyAutomation.CallGraph`。

## 协议说明

- 管道：`\\.\pipe\daofy_auto`，JSON 请求/响应。
- 异步命令（返回 ACK，Python 轮询 `peekresult`）：`click`/`rclick`/`dblclick`/`hover`/`move`/`drag`/`msgclick`/`dlgclick`/`rcall`/`key`/`rset`/`type`。
- 同步命令（阻塞等待）：`goto`/`capture`/`waitfor`/`wait`/`dumpstate`/`listwnd`/`dlgscan`/`msgscan`/`msgclose`/`dlgfile`/`snapdir`/`exit`/`rget`/`rinspect`/`peekresult`；可选诊断命令 `callgraph`/`callgraph_diff`/`callgraph_path`/`callgraph_impact` 和用途层 `callgraph_*` 需要额外引用 `DaofyAutomation.CallGraph` 并生成 Detailed 级别 `.map`。`callgraph` 支持 `direction=callees|callers`、`project_only`、`exclude_prefixes`、`include_prefixes`、`edge_limit`，响应包含 `edge_count`、`returned_count`、`truncated`，每条边包含 `call_addr`、`call_file`、`call_line`、`category`、`from_category`、`to_category`；`callgraph_path` 支持 `source`、`target`、`max_depth`、`max_paths`、`include_prefixes`；`callgraph_diff` 默认 `compare_by=name`，可选 `addr|full`，`baseline_path`/`save_as` 和用途层文件型 graph/impact 输入都限制在 `snapshots_dir` 内；`callgraph_impact` 支持 `functions`/`targets` 或 `file`+`line`/`locations`，批量查询 callers 并汇总入口候选。

`msgscan` 返回 `data="NOD"`（无 MessageBox）；返回 `data="OK"` 时将 MessageBox JSON 写入 `_formstate.json`，Daofy 加载到 `response.state` 用于断言和报告检查。

### dumpstate 属性白名单

`dumpstate` 接受 `props` 参数（逗号分隔的属性名列表），仅输出指定属性（跳过 `IsSkippedProp` 黑名单）。不传时返回全部过滤后的属性。
```
dumpstate                        → 全部属性（按 IsSkippedProp + 无名控件过滤）
dumpstate props=caption,enabled  → 仅 Caption 和 Enabled
dumpstate props=name,class,items → 仅 name、class、集合项
```
无名控件（`Name=''`）和空标题的集合项不输出。

### 通用 RTTI 项点击

`click` 支持 `ControlName@ItemCaption` 语法，通过泛型 RTTI 查找并点击任何 `TCollection` 属性中的项，无需 VCL 类型绑定。
```
click cbMenus@打开工程...   → 查找 Caption="打开工程..." 的项，点击其 Bounds 中心
```
关键实现方法（`Vcl.DaofyAutomation.pas`）：
- `ReadItemCaption(Item)` — RTTI 读 `Caption` 属性，回退到 `Text`
- `TryGetItemBounds(Item, out R)` — RTTI 逐字段读 `Bounds`（Left/Top/Right/Bottom）
- `TryFindAndClickItem(Ctrl, SearchCaption)` — 扫描所有 TCollection 属性 + 嵌套集合，`AnsiContainsText` 匹配标题，点击 Bounds 中心

标题匹配不区分大小写（`AnsiContainsText`），无需引用 `Vcl.CategoryButtons` 等类型相关单元。

### msgscan/msgclick/msgclose 的 FindDialog 行为

FindDialog 已重写：从简单的 `FindWindowW('#32770', nil)` 改为 `EnumWindows` + `IsWindowVisible` + 标题/类名匹配。
- `FindDialog` 接受两个过滤参数：`ATitle`（窗口标题子串，不区分大小写）和 `AClass`（对话框类名，默认 `#32770`）
- 优先查前台窗口，再 `EnumWindows` 遍历 + `IsWindowVisible` 过滤
- 旧行为返回找到的第一个 `#32770` HWND — 有隐蔽 HWND 残留时失败
- 调用示例：`msgscan target:'浏览' class:'#32770'` / `msgclick target:'确定'` / `msgclose class:'#32770'`
- `msgclose` 也通过 `IsWindowVisible` 过滤避免关闭残留 HWND

### FindControl 回退（Delphi 表单）

`dlgscan` 使用不同的策略：`GetForegroundWindow` → `FindControl` 检测 Delphi `TForm`（fsModal）对话框。回退到 Win32 `#32770` 类检测。VCL 重写可检测 `TForm`（fsModal），扫描其 `Controls` 中的 `TButton`，返回结构化 JSON（含 `type`/`class`/`title`/`text`/`name`/`buttons: [{caption, modalresult}]`）。

### peekresult

`peekresult` 一次消费一个结果，由 `FAsyncResultsCS` 保护线程安全。
