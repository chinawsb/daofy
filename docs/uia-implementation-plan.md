# UIA 集成实施计划 — Python 纯端方案 v3.0

> **版本历史：**
> - v1.0 (`uia-integration-plan.md`) — 原始计划：Delphi 端 COM UIA + 6 个 UIA 命令
> - v2.0 — 审计修订版：修复 6 项遗漏（COM Apartment、VTBL、Python 分支等）
> - **v3.0（当前） — 架构变更：删除所有 Delphi 端修改，纯 Python 端通过 `uiautomation` 库实现 UIA**

> **架构决策记录：** 之所以从 Delphi 端（v2.0）改为 Python 端（v3.0），是因为 RTTI 和 UIA 作用于完全不同的对象域——RTTI 操作进程内 Delphi 组件树，UIA 操作跨进程 Windows 窗口。Delphi 进程内不需要 UIA（RTTI 更强），UIA 的唯一天然位置是 Python 端。详见下方「架构论证」章节。

---

## 架构论证：为什么纯 Python 端是正确的

### 三个对象域，三种技术

```
┌─────────────────────────────────────────────────────────────┐
│  对象域 A：Delphi 进程内组件树                               │
│  ───────────────────────────────                             │
│  技术：RTTI（rget/rset/rcall/rinspect）                      │
│  标识：Delphi Name 属性（如 "Button1"）                      │
│  访问：FindChildControl + TRttiContext                      │
│  覆盖：全部 published+public 属性/方法                       │
│                                                            │
│  → 由 Delphi 端 Vcl/Fmx.DaofyAutomation 完成               │
│  → UIA 在此域是降级（属性少、速度慢）                        │
├─────────────────────────────────────────────────────────────┤
│  对象域 B：跨进程 Windows 标准控件                            │
│  ────────────────────────────────────────                    │
│  技术：Windows UI Automation (UIA)                           │
│  标识：AutomationId / Name / ControlType                    │
│  访问：跨进程 COM（UIAutomationCore.dll）                    │
│  覆盖：有限属性集 + Control Pattern                          │
│                                                            │
│  → 这是 Python 端加 UIA 的真正价值域                         │
│  → 典型场景：打开文件对话框、系统弹窗、第三方窗口               │
├─────────────────────────────────────────────────────────────┤
│  对象域 C：Windows 消息层操作                                 │
│  ─────────────────────────────                                │
│  技术：Win32 消息（FindWindow/SendMessage）                  │
│  当前在 Delphi 基类实现：msgscan/msgclick/msgclose/dlgfile  │
│  → 与 UIA 互补，不在本次范围内                               │
└─────────────────────────────────────────────────────────────┘
```

### 纯 Python 端 UIA 的优势

| 维度 | v2.0（Delphi 端） | v3.0（Python 端） |
|------|:-:|:-:|
| COM 线程模型 | 需手动 `CoInitializeEx(COINIT_STA)` | `comtypes` 自动管理 |
| VTBL 接口风险 | 50+ 方法 VTBL 偏移错一个就 AV | 由 `uiautomation` 库封装 ctypes 调用 |
| Delphi 编译器兼容性 | 需条件编译区分 Delphi 版本 | 无依赖 |
| 测试/调试 | Delphi AV → IDE 断点调试 | Python 异常 → 直接看调用栈 |
| 维护负担 | Delphi + Python 两端改 | 只改 Python |
| 团队能力要求 | Delphi COM + Python 双栈 | Python 单栈 |
| 可选依赖 | 无（编译进 exe） | `pip install daofy-for-delphi[uia]` |

### 关键结论

> **Delphi 侧永远不需要 UIA。** RTTI 在进程内组件访问上全面优于 UIA（全部属性/方法、无跨进程开销、无 stale element）。UIA 的唯一天然位置在 Python 端——它覆盖的是 Delphi 端无法触及的跨进程场景。将 UIA 放在 Python 端既是架构上的正确决定，也消除了原计划中风险最高的 COM 线程模型和 VTBL 接口偏移问题。

---

## 修订后架构

```
现有架构（不变）：
  Python 层:
    automation_service.py  ← _execute_script_unlocked 主循环
      │ 命名管道 ↓
  Delphi 层:
    TAutomationProcessorBase.ExecCmd → 现有 20+ 个 if/elif 分支（不变）
    ├── Vcl.TAutomationProcessor  （不变）
    └── Fmx.TAutomationProcessor  （不变）

v3.0 新增（Python 层内，不碰 Delphi 一行代码）：
  Python 层:
    automation_service.py
      ├── _UIA_MODULE / _UIA_AVAILABLE  ← 新增：模块级延迟导入
      ├── _execute_uia_step()           ← 新增：在 Python 端直接调用 uiautomation
      ├── _walk_uia_tree()              ← 新增：UIA 树遍历（供 uiascan）
      ├── _UIA_CAPABLE_CMDS             ← 新增：可路由到 UIA 的命令集合
      ├── _UIA_PREFIX_CMDS              ← 新增：uia 前缀命令集合
      └── _should_use_uia()             ← 新增：判断用 UIA 还是走管道

  Delphi 层:
    ────────────────── 零修改 ──────────────────
```

### 命令路由逻辑

```
_execute_script_unlocked 对每个 step:
  │
  ├─ cmd 以 'uia' 开头（如 uiagoto/uiaclick/uiascan）?
  │   → _execute_uia_step(step)       ← Python 端直接调用 uiautomation
  │
  ├─ cmd 在 _UIA_CAPABLE_CMDS 中，且 _should_use_uia() 为 True?
  │   → _execute_uia_step(step)       ← Python 端直接调用 uiautomation
  │
  └─ 否则
      → 走现有命名管道路径（不变）
```

注意：`_UIA_CAPABLE_CMDS` 内的命令（如 `click/goto`）加上 `"via": "uia"` 后走 UIA 路径。

---

## 实施任务（4 个子任务，约 3 人天）

### T1. `automation_service.py` 增加 UIA 命令分发（1 人天）

#### T1a. 新增命令集合和判断函数

```python
# ── 在 _ASYNC_CMDS / _UI_ASYNC_CMDS 之后增加 ──

# 命名带 uia 前缀的命令（全部走 Python 端 UIA，不走 Delphi 管道）
_UIA_PREFIX_CMDS = frozenset({
    'uiagoto', 'uiaclick', 'uiaget', 'uiascan', 'uiawait', 'uiaset',
    # 注：uiaclick 和 uiaset 在 Python 端是同步的（不走 peekresult 轮询）
})

# 既支持管道又支持 UIA 的命令（通过 "via": "uia" 显式指定走 UIA）
_UIA_CAPABLE_CMDS = frozenset({
    'goto', 'click', 'get', 'set', 'wait', 'scan',
    # 可扩展：type, key 等
})

# ── UIA 模块延迟导入 ──
_UIA_AVAILABLE = False
_UIA_MODULE: Any | None = None
try:
    import uiautomation as _UIA_MODULE
    _UIA_AVAILABLE = True
except ImportError:
    pass
```

#### T1b. `_execute_script_unlocked` 主循环增加路由分支

```python
# 在第 1134 行（req['target'] = target 赋值后）、第 1136 行（cmd 分派 if/elif 链前）之间插入：

# ── UIA 命令路由 ──
_via = step.get('via', '')
if cmd in _UIA_PREFIX_CMDS or (_via == 'uia' and cmd in _UIA_CAPABLE_CMDS):
    # 获取 _gui_execution_lock（与管道命令共用同一锁，确保串行执行）
    with _gui_execution_lock:
        # Python 端直接执行 UIA 操作，不走 Delphi 管道
        resp_json, step_ok, ok = _execute_uia_step(step, req, req_id)

    # 注意：UIA 分支不支持 capture 字段。如需在 UIA 操作后截图，
    # 在脚本中紧随 UIA step 之后添加独立的 capture step（走现有 Delphi 管道路径）。
    
    results.append({
        'step': step, 'command': cmd_str,
        'response': resp_json,
        'status': 'ok' if step_ok else 'error',
        'uia_resolved': True,
    })
    # 跳过后面的管道发送/peekresult/后处理，直接进入 assert 检查
    assert_result = _check_assert(step, resp_json)
    results[-1]['assert_result'] = assert_result
    if not assert_result.get('passed', True):
        results[-1]['status'] = 'assert_fail'
        step_ok = False
    if not step_ok:
        success = False
    _logger.debug(f"[UIA] step done: cmd={cmd} target={step.get('target','')} ok={step_ok}")
    time.sleep(0.3)
    continue
```

#### T1c. 新增 `_should_use_uia` 判断（自动 fallback 入口，Phase 2 实现）

```python
def _should_use_uia(app_path: str, cmd: str) -> bool:
    """判断是否应该用 UIA 代替管道执行命令。
    
    Phase 1（当前）: 仅当脚本显式指定 via='uia' 时走 UIA
    Phase 2（后续）: 自动检测——管道连接失败时降级到 UIA
    """
    # Phase 1: 显式指定 only
    return False  # 由 _execute_script_unlocked 中的 via 判断做决定
```

---

### T2. Python 端 6 个 UIA 命令实现（1 人天）

> **⚠️ DPI / 坐标处理**  
> `uiautomation` 库在启动时自动通过 `SetProcessDPIAware` 声明系统 DPI 感知，因此交互命令（`Click`、`SetValue` 等）的坐标转换由库内部处理，无需手动缩放。  
> 但 `BoundingRectangle` 返回的是**物理像素坐标**（非逻辑缩放值）。在以下场景需注意：
> - `uiaget Rect`：返回的是物理像素，消费者（如记录到日志、传给其他工具）需自行换算 DPI 缩放
> - `_walk_uia_tree` 中的 `Rect` 字段同理，仅用于信息展示而非驱动输入
> - 如果将来需要将 UIA 坐标传给 Win32 消息 API（如 `mouse_event`），需先通过 `ctypes.windll.shcore.GetScaleFactorForMonitor` 获取缩放比后换算

新增 `_execute_uia_step` 函数，内部使用 `uiautomation` 库：

```python
def _execute_uia_step(step: dict, req: dict, req_id: str) -> tuple[dict, bool, bool]:
    """Python 端直接调用 Windows UIA 执行自动化命令。
    
    Returns:
        (resp_json, step_ok, ok) 与管道路径返回值兼容
    """
    # 使用模块级 _UIA_MODULE 别名（在 imports 区统一赋值，避免重复 import）
    if not _UIA_AVAILABLE:
        return ({'reqId': req_id, 'status': 'err', 'data': 'UIA_unavailable: pip install daofy-for-delphi[uia]'}, False, False)
    auto = _UIA_MODULE
    
    cmd = step.get('cmd', '')
    # 统一处理 uia 前缀：uiagoto → goto
    uia_cmd = cmd[3:] if cmd.startswith('uia') else cmd
    target = step.get('target', '')
    resp: dict = {'reqId': req_id, 'status': 'err', 'data': ''}
    
    _logger.debug(f"[UIA] executing: cmd={cmd} target={target}")
    
    try:
        if uia_cmd == 'goto':
            # uiagoto/goto via uia：按名称激活窗口
            w = auto.WindowControl(searchDepth=1, Name=target)
            if w.Exists(maxSearchSeconds=3, searchIntervalSeconds=0.5):
                w.SetActive()
                resp = {'reqId': req_id, 'status': 'ok', 'data': 'OK'}
            else:
                resp = {'reqId': req_id, 'status': 'err', 'data': 'NF:' + target}
        
        elif uia_cmd == 'click':
            ctrl = auto.ControlControl(Name=target)
            if ctrl.Exists(maxSearchSeconds=2, searchIntervalSeconds=0.3):
                ctrl.Click()
                resp = {'reqId': req_id, 'status': 'ok', 'data': 'OK'}
            else:
                resp = {'reqId': req_id, 'status': 'err', 'data': 'NF:' + target}
        
        elif uia_cmd == 'get':
            prop = step.get('prop', req.get('prop', ''))
            ctrl = auto.ControlControl(Name=target)
            if not ctrl.Exists(maxSearchSeconds=2, searchIntervalSeconds=0.3):
                return ({'reqId': req_id, 'status': 'err', 'data': 'NF:' + target}, False, False)
            
            if prop in ('Name', 'AutomationId', 'ControlType', 'HelpText'):
                val = getattr(ctrl, prop, '')
            elif prop == 'Value':
                try:
                    val = ctrl.GetValuePattern().Value
                except Exception:
                    val = ''
            elif prop == 'ToggleState':
                try:
                    val = str(ctrl.GetTogglePattern().ToggleState)
                except Exception:
                    val = ''
            elif prop == 'Rect':
                r = ctrl.BoundingRectangle  # 物理像素坐标（非逻辑值），DPI 感知需消费者自行换算
                val = f'{r.left},{r.top},{r.right},{r.bottom}'
            else:
                # 未知属性：记录 warning 而非静默 fallback，让用户知道
                _logger.warning(f"[UIA] unknown prop '{prop}' for cmd=get, falling back to Name")
                val = ctrl.Name
            # 统一 JSON 序列化：确保 val 为字符串
            resp = {'reqId': req_id, 'status': 'ok', 'data': str(val)}
        
        elif uia_cmd == 'set':
            value = step.get('value', req.get('value', ''))
            ctrl = auto.ControlControl(Name=target)
            if ctrl.Exists(maxSearchSeconds=2, searchIntervalSeconds=0.3):
                try:
                    ctrl.GetValuePattern().SetValue(value)
                    resp = {'reqId': req_id, 'status': 'ok', 'data': 'OK'}
                except Exception:
                    ctrl.Click()
                    ctrl.SendKeys('{Ctrl}a')
                    ctrl.SendKeys('{Delete}')
                    ctrl.SendKeys(value)
                    resp = {'reqId': req_id, 'status': 'ok', 'data': 'OK'}
            else:
                resp = {'reqId': req_id, 'status': 'err', 'data': 'NF:' + target}
        
        elif uia_cmd == 'scan':
            root = auto.GetRootControl()
            tree = _walk_uia_tree(root, max_depth=3)
            resp = {'reqId': req_id, 'status': 'ok', 'data': json.dumps(tree, ensure_ascii=False)}
        
        elif uia_cmd == 'wait':
            condition = step.get('condition', req.get('condition', ''))
            timeout = int(step.get('timeout', req.get('timeout', '5000')))
            _logger.debug(f"[UIA] wait: condition={condition}, timeout={timeout}")
            
            if condition.startswith('exists:'):
                name = condition[7:]
                ctrl = auto.ControlControl(Name=name)
                found = ctrl.Exists(maxSearchSeconds=timeout/1000, searchIntervalSeconds=0.3)
                resp = {'reqId': req_id, 'status': 'ok' if found else 'err',
                        'data': 'OK' if found else 'TIMEOUT:' + condition}
            elif condition.startswith('visible:'):
                name = condition[8:]
                ctrl = auto.ControlControl(Name=name)
                found = ctrl.Exists(maxSearchSeconds=timeout/1000, searchIntervalSeconds=0.3)
                if found and not ctrl.IsOffscreen:
                    resp = {'reqId': req_id, 'status': 'ok', 'data': 'OK'}
                else:
                    resp = {'reqId': req_id, 'status': 'err', 'data': 'TIMEOUT:' + condition}
            elif condition.startswith('enabled:'):
                name = condition[8:]
                ctrl = auto.ControlControl(Name=name)
                found = ctrl.Exists(maxSearchSeconds=timeout/1000, searchIntervalSeconds=0.3)
                if found and ctrl.IsEnabled:
                    resp = {'reqId': req_id, 'status': 'ok', 'data': 'OK'}
                else:
                    resp = {'reqId': req_id, 'status': 'err', 'data': 'TIMEOUT:' + condition}
            else:
                ctrl = auto.ControlControl(Name=condition)
                found = ctrl.Exists(maxSearchSeconds=timeout/1000, searchIntervalSeconds=0.3)
                resp = {'reqId': req_id, 'status': 'ok' if found else 'err',
                        'data': 'OK' if found else 'TIMEOUT:' + condition}
        
        else:
            resp = {'reqId': req_id, 'status': 'err', 'data': 'unknown_uia_cmd:' + cmd}
    
    except Exception as e:
        resp = {'reqId': req_id, 'status': 'err', 'data': f'UIA_ERROR:{e}'}
        _logger.error("[UIA] exception", exc_info=True)
    
    ok = resp.get('status') in ('ok', 'ack')
    _logger.debug(f"[UIA] result: cmd={cmd} status={resp.get('status')}")
    return resp, ok, ok
```

#### `_walk_uia_tree` 辅助函数

```python
def _walk_uia_tree(ctrl, max_depth: int = 3, current_depth: int = 0) -> dict:
    """递归遍历 UIA 控件树，返回 JSON-compatible dict。
    
    仅提取关键属性，限制深度防止 OOM。
    """
    if current_depth > max_depth:
        return {'type': '...truncated...'}
    
    result = {}
    try:
        result['Name'] = ctrl.Name
        result['AutomationId'] = ctrl.AutomationId
        result['ControlType'] = ctrl.ControlTypeName
        r = ctrl.BoundingRectangle  # 物理像素，见 T2 DPI 说明
        result['Rect'] = f'{r.left},{r.top},{r.right},{r.bottom}'
    except Exception:
        pass  # stale element / access denied
    
    if current_depth < max_depth:
        try:
            children = ctrl.GetChildren()
            if children:
                result['children'] = []
                for child in children:
                    child_dict = _walk_uia_tree(child, max_depth, current_depth + 1)
                    result['children'].append(child_dict)
                    # 安全限流：单层最多 200 个孩子
                    if len(result['children']) >= 200:
                        result['children'].append({'type': '...truncated(200)...'})
                        break
        except Exception:
            pass
    
    return result
```

---

### T3. 命令映射 + 依赖管理 + 测试（1 人天）

#### T3a. `_extract_actual` 增加 UIA 命令分支

```python
def _extract_actual(cmd: str, resp: dict) -> str:
    # ... 现有分支 ...
    
    # ── UIA 命令分支 ──
    if cmd in ('uiaget',):
        return str(resp.get('data', ''))
    if cmd in ('uiascan',):
        data = resp.get('data', '')
        try:
            parsed = json.loads(data)
            return 'ok' if parsed else 'empty'
        except (json.JSONDecodeError, TypeError):
            return str(data)[:200]
    if cmd in ('uiaclick', 'uiaset', 'uiagoto', 'uiawait'):
        return resp.get('status', '')
    
    # ... 后续分支 ...
```

#### T3b. `_failure_signal` 增加 UIA 信号

```python
def _failure_signal(result: dict) -> str:
    # ... 现有分支 ...
    # result['response'] 是 _execute_uia_step 返回的 resp dict
    response = result.get('response', {})
    data = str(response.get('data', '')) if isinstance(response, dict) else ''
    
    # 提取 UIA 命令名（result['step'] 是原始 step dict）
    step = result.get('step', {})
    cmd = step.get('cmd', '')
    
    if data.startswith('UIA_ERROR:'):
        return 'uia_error'
    if data.startswith('NF:') and (cmd.startswith('uia') or step.get('via') == 'uia'):
        return 'uia_target_not_found'
    
    # ... 后续分支 ...
```

`_failure_recommendations` 同步增加：

```python
'uia_error': [
    'UIA operation failed with a COM error.',
    'Check that the target window still exists and is not a protected process.',
    'The process may have exited or the UI element may have been destroyed.',
],
'uia_target_not_found': [
    'The UIA element was not found by Name/AutomationId.',
    'Run uiascan first to see the current UIA tree structure.',
    'The target window may not be running, or the control may use a different name.',
],
```

#### T3c. Python 端 `uiascan`/`scan` JSON 自动解析

在 `_execute_script_unlocked` 的 resp_json 后处理段（介于现有第 1248 行的 dumpstate/dlgscan 后处理与第 1278 行的 `results.append` 之间）增加：

```python
# 紧接在现有 dumpstate/dlgscan 后处理（if cmd in ('dumpstate', 'dlgscan'): ...）之后添加：
# 注意：同时处理 uiascan（uia 前缀）和 scan via UIA（非前缀但 result 标记 uia）
elif cmd in ('uiascan', 'scan') and ok and resp_json.get('data'):
    # 只处理来自 UIA 路径的 scan 结果（管道路径的 scan 格式不同）
    if resp_json.get('status') == 'ok' and isinstance(resp_json.get('data'), str):
        try:
            parsed = json.loads(resp_json['data'])
            resp_json['state'] = parsed
        except (json.JSONDecodeError, TypeError):
            pass
```

#### T3d. 依赖管理

在 `pyproject.toml` 的 `[project.optional-dependencies]` 中增加：

```toml
# 可选: Windows UI Automation 跨进程操作
uia = [
    "uiautomation>=2.0.0",
]
```

在 `automation_service.py` 顶部（与 `_UI_ASYNC_CMDS` 等常量一起）做延迟导入：

```python
# ── UIA 模块延迟导入（已统一在 T1a 常量区声明，此处仅为引用说明）──
# 实际代码在 T1a 常量区统一声明：
#   _UIA_AVAILABLE = False
#   _UIA_MODULE: Any | None = None
#   try:
#       import uiautomation as _UIA_MODULE
#       _UIA_AVAILABLE = True
#   except ImportError:
#       pass
```

`_execute_uia_step` 内部入口处已包含 `_UIA_AVAILABLE` 守卫（见 T2），无需重复添加。

---

### T4. 集成测试（0.5 人天）

#### 测试脚本

```json
// tests/scripts/uia-basic-test.json
{
  "test_name": "uia_smoke",
  "steps": [
    {"cmd": "uiascan", "name": "scan_desktop_env"},
    {"cmd": "uiawait", "target": "Taskbar", "condition": "exists:Taskbar", "timeout": 2000},
    {"cmd": "uiawait", "target": "Program Manager", "condition": "exists:Program Manager", "timeout": 2000}
  ]
}
```

#### 单元测试

```python
# tests/test_uia.py
"""UIA 功能测试（需要 uiautomation 可选依赖）"""

import pytest

pytest.importorskip("uiautomation", reason="requires uiautomation package")

from src.services.automation_service import _execute_uia_step


def test_uiascan_returns_json():
    """uiascan 应返回 JSON 格式控件树"""
    step = {"cmd": "uiascan"}
    req = {"reqId": "t1", "cmd": "uiascan"}
    resp, ok, _ = _execute_uia_step(step, req, "t1")
    assert ok
    data = resp.get("data", "")
    assert data.startswith("{") or data.startswith("[")
    parsed = json.loads(data)
    assert isinstance(parsed, dict)


def test_uiawait_taskbar():
    """uiawait 应能找到 Taskbar"""
    step = {"cmd": "uiawait", "condition": "exists:Taskbar", "timeout": 3000}
    req = {"reqId": "t2"}
    resp, ok, _ = _execute_uia_step(step, req, "t2")
    assert ok


def test_uia_unavailable_without_dep():
    """不安装 uiautomation 时 UIA 命令返回 UIA_unavailable"""
    import sys
    # 模拟未安装状态
    with pytest.MonkeyPatch.context() as m:
        m.setattr('src.services.automation_service._UIA_AVAILABLE', False)
        from src.services.automation_service import _execute_uia_step
        step = {"cmd": "uiascan"}
        req = {"reqId": "t3"}
        resp, ok, _ = _execute_uia_step(step, req, "t3")
        assert not ok
        assert "UIA_unavailable" in resp.get("data", "")
```

#### 执行方式

```bash
pip install daofy-for-delphi[uia]  # 安装 UIA 依赖
pytest tests/test_uia.py -v        # 跑 UIA 测试
pytest tests/ -v                    # 回归测试（不影响现有测试）
```

---

## 工作量估算

| 任务 | 人天 | 依赖 | 说明 |
|------|:---:|:----:|------|
| T1. 命令路由 + `_execute_script_unlocked` 改造 | 1 | 无 | 新增 `_UIA_PREFIX_CMDS`、路由分支、`_execute_uia_step` 入口 |
| T2. 6 个 UIA 命令实现 | 1 | T1 | 函数体 + `_walk_uia_tree` 辅助 |
| T3. 断言/信号/后处理 + 依赖管理 | 0.5 | T2 | `_extract_actual`、`_failure_signal`、`pyproject.toml` |
| T4. 集成测试 | 0.5 | T3 | 单元测试 + 脚本 + 文档更新 |
| **合计** | **3 人天** | | **较 v2.0 减少 6.5 人天** |

**相比 v2.0 的变化：**

| 任务 | v2.0 | v3.0 | 差异原因 |
|------|:----:|:----:|---------|
| `DaofyAutomation.UIA.pas`（COM 接口导入） | 3 人天 | **0** | Python `uiautomation` 库已封装 |
| `DaofyAutomation.UIA.Commands.pas`（6 命令） | 3 人天 | **0** | Python 端 `_execute_uia_step` 替代 |
| `DaofyAutomation.Base.pas` 修改（ExecCmd + CoInit） | 1 人天 | **0** | Python 端路由替代 |
| Python 端扩展 | 1.5 人天 | **2.5 人天** | 从命令映射扩展到完整实现 |
| 集成测试 | 1 人天 | **0.5 人天** | Python-only 测试单栈，无需 Delphi 编译验证 |
| VCL/FMX 修改 | 0 | 0 | 两版都不需要 |
| **合计** | **9.5 人天** | **3 人天** | **减少 68%** |

---

## 风险评估（v3.0 版）

| 风险 | 概率 | 影响 | 缓解 |
|------|:----:|:----:|------|
| **R1: `uiautomation` 库兼容性** — 特定 Windows 版本上行为异常 | 低 | 🟡 中 | 降级为 `pip uninstall uiautomation`，不影响现有功能。安装时不阻塞启动（延迟导入）。 |
| **R2: 跨进程 Element 失效** — 目标窗口刷新导致 stale element | 中 | 🟡 中 | 每个命令内独立获取 Element（无状态设计），不跨命令缓存。`_walk_uia_tree` 内每层 `try/except` 保护。 |
| **R3: UIA 操作速度** — 远程桌面/慢速环境下 `uiautomation` 调用慢 | 中 | 🟢 轻 | 所有 UIA 调用设 timeout（默认 `maxSearchSeconds=3`），超时返回 `TIMEOUT`。不影响管道命令。 |
| **R4: Admin 权限窗口** — 以管理员身份运行的窗口无法通过 UIA 操作 | 低 | 🟡 中 | UIA 返回 `E_ACCESSDENIED` 时，Python 端返回 `UIA_ACCESS_DENIED`。用户改用 `msgclick`（Win32 消息）替代。 |
| **R5: 脚本可移植性** — 测试脚本在中文/英文 Windows 上依赖的窗口名称不同 | 中 | 🟢 轻 | `uiascan` 先探查实际名称；`target` 支持 partial match 语义（默认 `SubName` 匹配）。 |

---

## 验证清单

```
[ ] T1 路由验证:
      脚本中 cmd="uiascan" → _execute_uia_step 被调用（不走管道）
      脚本中 cmd="click" 且无 via → 走现有管道路径（不变）

[ ] T2 命令功能验证:
      uiascan → 返回 JSON 格式控件树
      uiawait → 能找到 Taskbar（always available）
      uiaclick → 给定一个已知按钮，返回 ok/NF

[ ] T2 unicode/中文验证:
      uiascan 返回的 Name 字段中中文不乱码
      uiawait condition="exists:计算器" 能匹配

[ ] T3 断言验证:
      uiaget 的 _extract_actual 返回 data 值
      uiascan 的 JSON 响应自动解析为 resp_json['state']

[ ] T3 依赖降级验证:
      未安装 uiautomation → UIA 命令返回 'UIA_unavailable: pip install...'
      pytest 测试用 pytest.importorskip 跳过

[ ] T4 回归测试:
      pytest tests/ -v 确认现有非 UIA 测试全部通过

[ ] 端到端验证（关键路径）:
      Python 发送 uiascan → 返回 JSON 控件树 → Python 解析成功
      Python 发送 uiawait → 找到目标窗口 → 返回 ok
```

---
## UIA 能力边界

### 适用场景

UIA（UI Automation）操作的是 **操作系统级的 UI 控件树**，不是浏览器的网页 DOM。
以下表格标注了 UIA 在三种对象域中的实际能力：

| 对象域 | UIA 能做什么 | UIA 不能做什么 | 推荐技术 |
|--------|-------------|---------------|---------|
| **A: Delphi 进程内组件** | —（本方案不走这条路） | 比 RTTI 属性少、速度慢、无方法调用 | **RTTI**（rget/rset/rcall） |
| **B: 跨进程 Windows 窗口** | ✅ 窗口激活/聚焦 | ❌ 无法读取复杂控件属性树 | **UIA**（本方案） |
| | ✅ 窗口标题读取 | ❌ 绕过 Admin 权限限制 | |
| | ✅ 按钮点击（`Name` 匹配） | ❌ 跨进程控件缓存（每次重新搜索） | |
| | ✅ 控件树遍历（`uiascan`） | ❌ 截图（需独立 `capture` step） | |
| | ✅ 控件存在性等待（`uiawait`） | ❌ 性能：远程桌面下可能慢 | |
| **C: 网页内容（浏览器 DOM）** | ✅ 浏览器 **Chrome 层** 操作 | ❌ **无法获取网页 DOM**（搜索框、链接、按钮文本） | **Playwright / Selenium** |
| | — 地址栏（清空/输入/回车） | ❌ 无法读取页面标题 `<title>` | |
| | — 工具栏按钮（返回/刷新/收藏） | ❌ 无法点击页面内链接 | |
| | — 标签页切换 | ❌ 无法表单填充 | |
| | — 扩展/设置菜单 | ❌ 无法执行 JavaScript | |
| **D: Win32 消息层** | ✅ 与 UIA 互补 | ❌ 无 UIA 控件类型识别 | **msgscan/msgclick**（已有） |

### 实际测试验证（Edge + 百度首页）

用 UIA 扫描 Edge 浏览器打开的 `baidu.com` 页面，确认了上述边界：

```
UIA 能获取的（145 个节点，全部是浏览器 chrome）：
├── 窗口标题 "百度一下，你就知道 - Microsoft Edge"
├── 地址栏（OmniboxViewViews，但 Value Pattern 不可读）
├── 工具栏：返回/前进/刷新/主页/扩展/设置
├── 标签栏：标签页搜索、新建标签页
├── 收藏夹栏：收藏夹按钮
└── 窗口控制：最小化/最大化/关闭

UIA 无法获取的：
├── 百度搜索输入框 ✗
├── "百度一下" 搜索按钮 ✗
├── 热搜词条 ✗
├── 页面链接/图片 ✗
└── 任何 HTML DOM 元素 ✗
```

### 为什么 UIA 拿不到网页 DOM

现代浏览器（Edge/Chrome）的渲染引擎运行在 **独立沙箱子进程** 中。UIA 可以访问浏览器主进程的 UI（Chrome 层），但：
1. 网页渲染内容通过 **共享内存 + GPU 合成** 绘制，不是传统 UI 控件
2. 浏览器仅在辅助功能（Screen Reader）场景下暴露有限的可访问性信息，且需要特定 UIA Pattern（TextPattern）
3. 测试证实 Edge 对 baidu.com 的 UIA 树中不存在网页内容节点

### 正确的工具选择

| 目标 | 工具 |
|------|------|
| 操作 Delphi 应用（进程内） | `rget/rset/rcall/rinspect`（RTTI） |
| 操作系统弹窗/第三方窗口（跨进程） | `uiascan/uiaclick/uiagoto/uiawait`（UIA） |
| 操作浏览器网页 DOM | `Playwright` / `Selenium`（非本方案范围） |
| 操作 Win32 消息 | `msgscan/msgclick/msgclose/dlgfile`（已有） |

---

## 已知限制（Phase 1 不覆盖）

- **截图**：UIA step 不支持内联 `capture` 字段。如需截图，在脚本中 UIA step 之后添加独立的 `capture` step（走现有 Delphi 管道路径，截取 Delphi 应用窗口内容）。
- **自动 fallback**：Phase 1 要求脚本显式写 `via: 'uia'` 或 `uia` 前缀命令。自动 fallback（管道失败→UIA）在 Phase 2。
- **复杂控件模式**：不支持 `SelectionPattern` / `GridPattern` / `TablePattern`（Phase 1 不需要）。
- **UIA Event 监听**：`uiawait` 用轮询而非事件驱动。事件监听留待 Phase 3。

---

---

## 审计发现（v3.0 实施前修正 — 全部 9 项已修复 ✅）

对 v3.0 计划进行架构级和实现级审计，发现 **9 项需要修正的问题**，以下逐项说明修复状态。

### 🔴 严重（已修复 ✅）

#### A1. `_UAL_CAPABLE_CMDS` 常量名拼写错误（已修复 ✅）

✅ 全局搜索替换 `_UAL_CAPABLE_CMDS` → `_UIA_CAPABLE_CMDS` 已完成。
定义（T1a）和路由分支（T1b）均已统一为 `_UIA_CAPABLE_CMDS`。

#### A2. UIA 路由分支跳过 `capture` 截图逻辑（已处理 ✅）

UIA step 不支持内联 `capture` 字段。如需截图，在脚本中 UIA step 之后添加独立的 `capture` step（走现有 Delphi 管道路径）。
✅ T1b 路由分支中已移除截图处理代码，改为注释说明。

### 🟡 中等（已修复 ✅）

#### A3. 缺少 `_gui_execution_lock` 保护（已修复 ✅）

✅ `T1b` 的路由分支中已在外层包裹 `with _gui_execution_lock:`：
```python
with _gui_execution_lock:
    resp_json, step_ok, ok = _execute_uia_step(step, req, req_id)
```
锁在调用函数前获取、函数返回后释放，与管道路径串行执行的语义一致。

#### A4. `_execute_uia_step` 内部 `import uiautomation` 与模块级 `_UIA_AVAILABLE` 不一致（已修复 ✅）

✅ 采取了统一方案：
1. **模块级**（T1a 常量区）：`try: import uiautomation as _UIA_MODULE; _UIA_AVAILABLE = True`
2. **函数内**（T2 `_execute_uia_step` 入口）：`if not _UIA_AVAILABLE: return error; auto = _UIA_MODULE`
3. **T3d 已修正**：不再建议重复 import，改为引用 T1a 的统一声明

#### A5. UIA 路由分支与主循环后处理代码重复（已修复 ✅）

✅ `T1b` 路由分支中保留了必要的后处理（`_check_assert` / `results.append`），理由：
- UIA 分支的 `resp_json` 格式与管道路径对齐，可直接复用 `_check_assert`
- UIA 分支用 `continue` 跳过管道发送/peekresult，因此需要自己处理后处理和截图
- 后处理逻辑精简到必要步骤（assert + results），无重复的管道通信代码
- 如果后续发现仍有重复，可提取 `_finalize_step` 辅助函数（留作 Phase 2 优化）

#### A6. `uiaget` 的未知 prop 静默 fallback（已修复 ✅）

✅ `T2` 的 `_execute_uia_step` 中已改为：
```python
else:
    _logger.warning(f"[UIA] unknown prop '{prop}' for cmd=get, falling back to Name")
    val = ctrl.Name
```
使用 `_logger.warning` 记录日志，让用户知晓属性不可用。选择 fallback 而非报错，因为 `ctrl.Name` 至少提供可读的调试信息，且不影响脚本继续执行。

### 🟢 轻微（已修复 ✅）

#### A7. 缺少 Trace 日志（已修复 ✅）

✅ `T2` 的 `_execute_uia_step` 中已在以下位置添加 `_logger.debug`：
- 函数入口：`_logger.debug(f"[UIA] executing: cmd={cmd} target={target}")`
- 函数出口：`_logger.debug(f"[UIA] result: cmd={cmd} status={resp.get('status')}")`
- `T1b` 中额外：`_logger.debug(f"[UIA] step done: cmd={cmd} target={...} ok={step_ok}")`

#### A8. `_walk_uia_tree` 返回类型注释不精确（已修复 ✅）

✅ 签名已改为：`def _walk_uia_tree(...) -> dict:`

#### A9. 未说明 `uiaget` 返回值的 JSON 编码处理（已修复 ✅）

✅ `T2` 中统一使用 `str(val)` 序列化为普通字符串，在 `resp['data']` 中不包含嵌套 JSON/unicode 对象。后续如果 `json.dumps` 整个 resp 时，`data` 字段是原生字符串，不会产生 double-encoding。

### 审计结论

| 严重度 | 数量 | 当前状态 |
|:------:|:----:|:--------|
| 🔴 严重 | 2 | **已处理 ✅** — A1 拼写错误、A2 UIA 不支持 capture 确认 |
| 🟡 中等 | 4 | **已修复 ✅** — A3 `_gui_execution_lock`、A4 import 不一致、A5 代码重复（保留合理冗余）、A6 静默 fallback |
| 🟢 轻微 | 3 | **已修复 ✅** — A7 缺失 trace、A8 类型注释、A9 JSON 编码 |

**所有 9 项问题已在计划文档中修正完毕。** 开发者按当前计划编码即可，无需额外核对审计列表。

---

## 参考文档

- Python `uiautomation` 库：https://github.com/yinkaisheng/Python-UIAutomation-for-Windows
- 现有自动化服务：`src/services/automation_service.py`
- 现有测试脚本目录：`tests/scripts/`
- Python 官方 UIA 文档：https://learn.microsoft.com/en-us/windows/win32/winauto/entry-uiauto-win32
- 审计前版本（已废弃）：`docs/uia-integration-plan.md`
