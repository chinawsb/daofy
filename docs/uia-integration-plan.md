# UIA 集成工作计划 — Phase 1

> **⚠️ 废弃说明：此计划（v1.0）已被 `docs/uia-implementation-plan.md` v3.0 取代。**
> **废弃原因：架构变更——原计划走 Delphi 端 COM UIA，新计划走 Python 端 `uiautomation` 库。**
> **新方案不需要修改 Delphi 端任何代码，工作量从 9.5 人天降至 3 人天。详见新计划。**

> 基于 `tools/auto/` 现有自动化架构评估生成的 Phase 1 实施计划。
> 目标：以最小侵入方式将 Windows UI Automation 作为可选增强通道引入，不改变现有非 UIA 命令的行为。

---

## 总体策略

```
现有架构：
  TAutomationProcessorBase (基类)
    ├── Vcl.TAutomationProcessor
    └── Fmx.TAutomationProcessor

Phase 1 新增：
  可选 UIA 通道（独立单元，条件 uses）
    ├── DaofyAutomation.UIA.pas          ← UIA COM 包装 + 工具函数
    └── DaofyAutomation.UIA.Commands.pas  ← UIA 命令实现 (uiagoto/uiaclick/uiaget/uiascan/uiawait)
```

**设计原则：**
- UIA 命令通过独立前缀 `uia` 与现有命令共存（`goto` vs `uiagoto`）
- UIA 依赖（`UIAutomationCore.dll`）延迟加载，未安装时不阻塞启动
- 不修改现有非 UIA 命令的任何代码路径
- Python 端 `automation_service.py` 支持自动 fallback：UIA 命令失败降级回 RTTI

---

## 工作量估算

| 任务 | 估算人天 | 依赖 |
|---|---|---|
| T1. 创建 `DaofyAutomation.UIA.pas` — COM Import Type Library + 延迟加载 | 2 | 无 |
| T2. 创建 `DaofyAutomation.UIA.Commands.pas` — 6 个 UIA 命令实现 | 3 | T1 |
| T3. 基类扩展：`DaofyAutomation.Base.pas` 新增 uia 命令分发分支 | 0.5 | T2 |
| T4. 修改 `Vcl.DaofyAutomation.pas` — 处理 uia 命令的具体框架上下文 | 1 | T3 |
| T5. 修改 `Fmx.DaofyAutomation.pas` — 同上 | 1 | T3 |
| T6. Python 端 `automation_service.py` — 命令映射 + fallback 逻辑 | 1.5 | T3 |
| T7. 集成测试 — 测试脚本 + 实测验证 | 2 | T6 |
| **合计** | **~11 人天** | |

---

## 各任务详细设计

### T1. `DaofyAutomation.UIA.pas`

```pascal
unit DaofyAutomation.UIA;

interface

uses Winapi.Windows, System.SysUtils, System.Variants;

// ── UIA COM 接口定义（从 UIAutomationCore.dll 导入，非源代码依赖）──

type
  IUIAutomation = interface ... // 导入类型库或手写关键接口
  IUIAutomationElement = interface ...
  // 核心 Control Patterns:
  IInvokeProvider = interface ...    // 按钮点击
  IValueProvider = interface ...     // 读写文本
  IToggleProvider = interface ...    // 复选框
  ISelectionProvider = interface ... // 列表选择
  IRangeValueProvider = interface ...// 滑块/进度条

// ── 延迟加载 UIAutomationCore.dll ──

function IsUIAvailable: Boolean;      // 检测是否可加载
function GetUIAutomation: IUIAutomation; // 单例

// ── 工具函数 ──

function FindElementByAutomationId(Root: IUIAutomationElement; const AId: string): IUIAutomationElement;
function FindElementByName(Root: IUIAutomationElement; const AName: string): IUIAutomationElement;
function FindElementByControlType(Root: IUIAutomationElement; AType: Integer): TArray<IUIAutomationElement>;
function GetElementRect(Root: IUIAutomationElement): TRect;

// ── Control Pattern 工具 ──

function TryGetInvokePattern(Elem: IUIAutomationElement; out Pattern: IInvokeProvider): Boolean;
function TryGetValuePattern(Elem: IUIAutomationElement; out Pattern: IValueProvider): Boolean;
function TryGetTogglePattern(Elem: IUIAutomationElement; out Pattern: IToggleProvider): Boolean;

implementation

var
  _UIAInstance: THandle = 0;
  _UIAutomation: IUIAutomation = nil;

function IsUIAvailable: Boolean;
begin
  // CoCreateInstance(CLSID_CUIAutomation, ...) 延迟加载
  Result := Assigned(_UIAutomation);
end;

// ...其余实现
```

**关键设计决策：**
- 使用 COM `CoCreateInstance` 而非静态链接 `UIAutomationCore.dll`，确保不安装 UIA 的系统也可运行
- 导出的工具函数全部以 `IUIAutomationElement` 作为输入而非 `HWND`，保持抽象
- Control Pattern 接口精简为当前 Phase 1 需要的 4-5 种

### T2. `DaofyAutomation.UIA.Commands.pas`

```pascal
unit DaofyAutomation.UIA.Commands;

interface

uses DaofyAutomation.UIA;

// 6 个 UIA 命令，全部返回 JSON 字符串（与基类 WriteResp 格式兼容）

function UiaGoto(const ReqId, Target: string): string;
  // 定位窗口：按 Name/AutomationId 激活指定 UIA 窗口

function UiaClick(const ReqId, Target: string): string;
  // 语义化点击：找到控件 → InvokePattern.Invoke 或模拟鼠标点击

function UiaGet(const ReqId, Target, Prop: string): string;
  // 读值：ValuePattern.Value / TogglePattern.ToggleState / 属性表

function UiaScan(const ReqId: string): string;
  // 扫描当前 UIA 树，返回 JSON 格式的控件摘要（类似 dumpstate 但走 UIA）

function UiaWait(const ReqId, Target, Condition: string; TimeoutMs: Integer): string;
  // 等待条件：控件出现 / 属性满足 / 状态变化

function UiaSet(const ReqId, Target, Value: string): string;
  // 设置值：ValuePattern.SetValue 输入文本
```

**关键设计决策：**
- 每个命令函数独立，无状态（UI Automation Element 在单次调用内获取 + 释放）
- 返回格式与基类 `WriteResp` 完全一致，上层不需要区分是否 UIA
- `UiaScan` 只返回关键属性（Name/AutomationId/ControlType/Role），不返回完整 RTTI 属性表

### T3. 基类扩展 `DaofyAutomation.Base.pas`

在 `ExecCmd` 方法中新增分支：

```pascal
// ── 在 ExecCmd 的框架相关命令段之前插入 ──

else if Cmd = 'uiagoto' then
  Result := WriteResp(ReqId, 'ok', DaofyAutomation.UIA.Commands.UiaGoto(ReqId, Target))

else if Cmd = 'uiaclick' then
  Result := WriteResp(ReqId, 'ok', DaofyAutomation.UIA.Commands.UiaClick(ReqId, Target))

else if Cmd = 'uiaget' then
  Result := WriteResp(ReqId, 'ok', DaofyAutomation.UIA.Commands.UiaGet(ReqId,
    Target, GetJSONStr(J, 'prop', '')))

else if Cmd = 'uiascan' then
  Result := WriteResp(ReqId, 'ok', DaofyAutomation.UIA.Commands.UiaScan(ReqId))

else if Cmd = 'uiawait' then
  Result := WriteResp(ReqId, 'ok', DaofyAutomation.UIA.Commands.UiaWait(ReqId,
    Target, GetJSONStr(J, 'condition', ''), StrToIntDef(GetJSONStr(J, 'timeout', '5000'), 5000)))

else if Cmd = 'uiaset' then
  Result := WriteResp(ReqId, 'ok', DaofyAutomation.UIA.Commands.UiaSet(ReqId,
    Target, GetJSONStr(J, 'value', '')))
```

`uses` 子句需要条件引用——仅在有 UIA 可用时导入：

```pascal
implementation

uses
  // ... 现有 uses ...
  DaofyAutomation.UIA.Commands;
// Uses 放在 implementation 段，仅在编译时链接。若 UIAutomationCore.dll 不存在，
// CoCreateInstance 在运行时返回错误，函数内部优雅降级为 `WriteResp(reqId, 'err', 'UIA_unavailable')`
```

**关键设计决策：**
- 新增命令的 `timer` 列表定义（`ExecCmd` 的 cmd 分支表）应与现有 `async/sync` 同步/异步一致：`uiaclick`/`uiaset` 异步，其余同步
- 新增 `IsAsyncCmd` 返回值中增加 `uiaclick`、`uiaset`

### T4/T5. VCL/FMX 具体实现调整

**Vcl.DaofyAutomation.pas** 和 **Fmx.DaofyAutomation.pas** 几乎不需要修改——因为 UIA 命令是 COM 层面的操作，不依赖 VCL/FMX 框架。

需要关注的点：
- `UiaGoto` 可以通过 UIA 定位窗口句柄后在 VCL 侧调用 `SetForegroundWindow`，而 VCL 的 `HandleCmdGoto` 已经用 `Screen.Forms[I].BringToFront`，所以 UIA 命令不需要框架上下文
- 截图命令 `uicapture` 暂不实现——UIA 不提供截图能力，复杂场景截图留待后续 DXGI Phase

### T6. Python 端 `automation_service.py` 扩展

```python
# 新增 UIA 命令集合
_UIA_CMDS = frozenset({
    'uiagoto', 'uiaclick', 'uiaget', 'uiascan', 'uiawait', 'uiaset',
})

# `_is_async_cmd` 增加：
_ASYNC_CMDS = _ASYNC_CMDS | frozenset({'uiaclick', 'uiaset'})
_UI_ASYNC_CMDS = _UI_ASYNC_CMDS | frozenset({'uiaclick', 'uiaset'})

# 命令构造逻辑增加 uia 前缀分支（在 `_execute_script_unlocked` 的 cmd 分支表中：
if cmd in ('uiaget',):
    # 解析 target.prop 语法
elif cmd == 'uiawait':
    req['condition'] = step.get('condition', '')
```

### T7. 集成测试

```
测试脚本目录: tests/scripts/
新增: tests/scripts/uia-basic-test.json

测试内容:
  1. uiascan — 扫描桌面 UIA 树（验证返回 JSON 格式正确）
  2. uiagoto — 定位计算器/记事本窗口
  3. uiaclick — 点击窗口上的标准按钮
  4. uiget — 读取 Edit 和 Button 的属性
  5. uiawait — 等待窗口打开

测试方式:
  - 手动启动一个带标准控件的 Delphi 测试程序（或直接用 notepad.exe）
  - 通过 mcp 测试或 pytest 调用 execute_script
```

---

## 风险与缓解措施

| 风险 | 概率 | 缓解 |
|---|---|---|
| UIAutomationCore.dll 在某些精简 Windows 版本上不可用 | 低 | `CoCreateInstance` 失败时返回 `'UIA_unavailable'`，不影响现有命令 |
| COM 接口导入不完整导致编译问题 | 中 | 采用手写关键接口而非全量导入类型库，只导入 Phase 1 需要的接口和模式 |
| UIA 获取的控件属性时序与 RTTI 不一致 | 中 | 在测试层面增加 200ms 的 `wait` 缓冲，后续积累数据后调整 |
| 需要管理员权限的跨进程窗口无法通过 UIA 操作 | 中 | UIA 操作失败时返回具体错误码（`E_ACCESSDENIED`），测试脚本可用 `capture` + `note` 替代 |

---

## 后续 Phase 规划（参考）

| Phase | 内容 | 优先级 |
|---|---|---|
| **Phase 2** | DXGI Desktop Duplication API 替代 GDI BitBlt 截图 | 高（解决黑框问题） |
| **Phase 3** | Delphi 自定义控件 UIA Provider 实现指南 | 中（按需） |
| **Phase 4** | `action="auto"` hybrid 模式——自动选择 UIA/RTTI/消息 | 低（累积足够经验后） |
| **Phase 5** | OCR 输出对齐 UIA 定位——OCR 识别的文本位置 + UIA 控件矩形做映射 | 低 |

---

## 参考文档

- 现有架构基类：`tools/auto/DaofyAutomation.Base.pas`
- VCL 实现：`tools/auto/Vcl.DaofyAutomation.pas`
- FMX 实现：`tools/auto/Fmx.DaofyAutomation.pas`
- Python 自动化服务：`src/services/automation_service.py`
- 评估报告：`docs/uia-integration-plan.md`（本文）
- Microsoft UIA 文档：https://learn.microsoft.com/en-us/windows/win32/winauto/entry-uiauto-win32
- UIA Control Patterns：https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-controlpatternsoverview
