r"""
自动化测试服务 — GUI 命名管道 + 控制台 subprocess 交互。

通信方式：命名管道 \\.\pipe\daofy_auto（Delphi server -> Python client）
使用 ctypes 直接调用 Windows API，零外部依赖。

协议：JSON 请求/响应 (REST-style)
  请求: {"reqId":"step_0","cmd":"goto","target":"TForm1"}
  响应: {"reqId":"step_0","status":"ok","data":"OK"}
    (async 命令: click/rclick/dblclick/hover/move/drag/msgclick/dlgclick/rcall/key/rset/type 返回 ACK，
    同步命令: goto/capture/waitfor/wait/dumpstate/listwnd/dlgscan/msgscan/msgclose/dlgfile/snapdir/exit/rget/rinspect/
    callgraph/callgraph_diff/callgraph_path/callgraph_impact 阻塞等待返回。
    异步结果通过后续 peekresult 命令或 waitfor/rget/capture 验证获取，无文件落盘。)

进程池复用：
  通过 keep_alive 参数让 Delphi 进程常驻，后续调用直接复用。
  进程超过 PROCESS_KEEPALIVE_TIMEOUT 未被使用会自动清理。
"""

import ast
import ctypes
import io
import json
import os
import queue
import re
import select
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path
from threading import Lock, RLock

PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_SNAPSHOTS_DIR = PROJECT_ROOT / 'docs' / 'copyright' / 'snapshots'
PIPE_NAME = r'\\.\pipe\daofy_auto'

# ── PE 子系统检测 ──

IMAGE_SUBSYSTEM_WINDOWS_GUI = 2
IMAGE_SUBSYSTEM_WINDOWS_CUI = 3


def detect_exe_subsystem(exe_path: str) -> int | None:
    """读取 PE 头的 Subsystem 字段，判断 exe 类型。

    Returns:
        IMAGE_SUBSYSTEM_WINDOWS_GUI (2) — GUI 程序
        IMAGE_SUBSYSTEM_WINDOWS_CUI (3) — 控制台程序
        None — 无法读取或非 PE 文件
    """
    try:
        with open(exe_path, 'rb') as f:
            # DOS 头: e_magic @0, e_lfanew @0x3C
            magic = f.read(2)
            if magic != b'MZ':
                return None
            f.seek(0x3C)
            e_lfanew = int.from_bytes(f.read(4), 'little')

            # PE 头: 'PE\0\0' + COFF头(20字节) + OptionalHeader
            f.seek(e_lfanew)
            pe_sig = f.read(4)
            if pe_sig != b'PE\0\0':
                return None

            # 跳过 COFF 头 (20 bytes)
            f.seek(e_lfanew + 4 + 20)
            # OptionalHeader.Magic: PE32=0x10b, PE32+=0x20b
            opt_magic = f.read(2)
            if opt_magic not in (b'\x0b\x01', b'\x0b\x02'):
                return None

            # Subsystem 在 OptionalHeader 偏移 68 (0x44) 处，WORD
            f.seek(e_lfanew + 4 + 20 + 68)
            subsystem = int.from_bytes(f.read(2), 'little')
            if subsystem in (IMAGE_SUBSYSTEM_WINDOWS_GUI, IMAGE_SUBSYSTEM_WINDOWS_CUI):
                return subsystem
            return None
    except Exception:
        return None

# ── 异步命令集合（Delphi 端 IsAsyncCmd 的镜像）──
_ASYNC_CMDS = frozenset({
    'click', 'dblclick', 'rclick', 'msgclick', 'dlgclick',
    'hover', 'move', 'drag', 'rcall', 'key', 'rset', 'type',
})
_UI_ASYNC_CMDS = frozenset({
    'click', 'dblclick', 'rclick', 'msgclick', 'dlgclick',
    'hover', 'move', 'drag', 'key', 'type',
})
_ASYNC_PEEK_TIMEOUT = 6.0
_UI_ASYNC_PEEK_TIMEOUT = 0.25

# ── UIA 命令集合 ──
_UIA_PREFIX_CMDS = frozenset({
    'uiagoto', 'uiaclick', 'uiaget', 'uiascan', 'uiawait', 'uiaset',
})
_UIA_CAPABLE_CMDS = frozenset({
    'goto', 'click', 'get', 'set', 'wait', 'scan',
})
_UIA_AVAILABLE = False
_UIA_MODULE = None
try:
    import uiautomation as _UIA_MODULE
    _UIA_AVAILABLE = True
except ImportError:
    pass

# ── 进程池 ──
_process_pool: dict[str, dict] = {}
_pool_lock = Lock()
_gui_execution_lock = RLock()  # RLock 允许同线程重入，防止 UIA 路由死锁
_pipe_session = threading.local()
PROCESS_KEEPALIVE_TIMEOUT = 300  # 5 分钟无使用则自动清理

# ── Windows API ──
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
PIPE_READMODE_MESSAGE = 2
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
PIPE_TIMEOUT_MS = 5000

_k32 = ctypes.windll.kernel32

_CreateFile = _k32.CreateFileW
_CreateFile.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                        wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                        wintypes.HANDLE]
_CreateFile.restype = wintypes.HANDLE

_WriteFile = _k32.WriteFile
_WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
                       wintypes.PDWORD, wintypes.LPVOID]
_WriteFile.restype = wintypes.BOOL

_ReadFile = _k32.ReadFile
_ReadFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                      wintypes.PDWORD, wintypes.LPVOID]
_ReadFile.restype = wintypes.BOOL

_CloseHandle = _k32.CloseHandle
_CloseHandle.argtypes = [wintypes.HANDLE]
_CloseHandle.restype = wintypes.BOOL

_SetNPHState = _k32.SetNamedPipeHandleState
_SetNPHState.argtypes = [wintypes.HANDLE, wintypes.LPDWORD,
                         wintypes.LPVOID, wintypes.LPVOID]
_SetNPHState.restype = wintypes.BOOL

_WaitNP = _k32.WaitNamedPipeW
_WaitNP.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
_WaitNP.restype = wintypes.BOOL

_GetLastError = _k32.GetLastError
_GetLastError.restype = wintypes.DWORD


# ── 共享管道原语 ──


def _open_pipe(pipe_name: str, timeout_ms: int = PIPE_TIMEOUT_MS) -> int | None:
    """打开 Delphi 命名管道，返回句柄，失败返回 None。

    调用方负责 _CloseHandle()。
    """
    if not _WaitNP(pipe_name, timeout_ms):
        return None

    handle = _CreateFile(
        pipe_name, GENERIC_READ | GENERIC_WRITE, 0,
        None, OPEN_EXISTING, 0, None,
    )
    if handle == INVALID_HANDLE_VALUE or handle == 0:
        return None

    mode = wintypes.DWORD(PIPE_READMODE_MESSAGE)
    _SetNPHState(handle, ctypes.byref(mode), None, None)
    return handle


def _write_pipe(handle, data: bytes) -> bool:
    """向管道写入数据（追加 \\0 终止符），成功返回 True。"""
    payload = data + b'\0' if not data.endswith(b'\0') else data
    written = wintypes.DWORD(0)
    return bool(_WriteFile(handle, payload, len(payload),
                           ctypes.byref(written), None))


def _read_pipe_message(handle, buf_size: int = 65536) -> bytes | None:
    """从命名管道读取一条完整消息（自动处理 ERROR_MORE_DATA 分块）。

    Returns:
        bytes — 完整的消息内容
        None — 读取失败（管道断开或出错）
    """
    chunks: list[bytes] = []
    while True:
        buf = ctypes.create_string_buffer(buf_size)
        read = wintypes.DWORD(0)
        ok = _ReadFile(handle, buf, buf_size, ctypes.byref(read), None)
        if ok:
            chunks.append(buf.raw[:read.value])
            break
        err = _GetLastError()
        if err == 234:  # ERROR_MORE_DATA
            chunks.append(buf.raw[:read.value])
            continue
        return None  # 读取失败
    return b''.join(chunks)


def _read_pipe_message_poll(
    handle,
    timeout_ms: int = 15000,
    poll_interval_ms: int = 50,
    buf_size: int = 65536,
) -> bytes | None:
    """轮询读取管道消息（超时机制），用于 async rcall 等场景。

    将管道设为 PIPE_NOWAIT 模式进行轮询，到期自动恢复 PIPE_WAIT。
    Returns:
        bytes — 消息内容
        None — 超时或出错
    """
    PIPE_WAIT = 0x00000000
    PIPE_NOWAIT = 0x00000001
    ERROR_NO_DATA = 232

    # 切到非阻塞模式
    old_mode = wintypes.DWORD(PIPE_READMODE_MESSAGE | PIPE_NOWAIT)
    _SetNPHState(handle, ctypes.byref(old_mode), None, None)

    deadline = time.time() + (timeout_ms / 1000)
    try:
        while time.time() < deadline:
            chunks: list[bytes] = []
            while True:
                buf = ctypes.create_string_buffer(buf_size)
                read = wintypes.DWORD(0)
                ok = _ReadFile(handle, buf, buf_size, ctypes.byref(read), None)
                if ok:
                    chunks.append(buf.raw[:read.value])
                    return b''.join(chunks)
                err = _GetLastError()
                if err == 234:  # ERROR_MORE_DATA
                    chunks.append(buf.raw[:read.value])
                    continue
                if err == ERROR_NO_DATA:
                    break  # 暂无数据，继续外层轮询
                return None  # 非预期错误
            time.sleep(poll_interval_ms / 1000)
        return None  # 超时
    finally:
        # 恢复阻塞模式
        restore_mode = wintypes.DWORD(PIPE_READMODE_MESSAGE | PIPE_WAIT)
        _SetNPHState(handle, ctypes.byref(restore_mode), None, None)


def _send_command_on_handle(handle: int, cmd: str) -> str:
    if not _write_pipe(handle, cmd.encode('utf-8')):
        return f'ERR:write_failed (err={_GetLastError()})'

    raw = _read_pipe_message(handle)
    if raw is None:
        return f'ERR:read_failed (err={_GetLastError()})'
    return raw.decode('utf-8', errors='replace').strip()


def _begin_pipe_session() -> None:
    _end_pipe_session()
    _pipe_session.enabled = True
    _pipe_session.handle = None


def _end_pipe_session() -> None:
    handle = getattr(_pipe_session, 'handle', None)
    if handle:
        _CloseHandle(handle)
    _pipe_session.enabled = False
    _pipe_session.handle = None


def _is_pipe_io_error(response: str) -> bool:
    return response.startswith('ERR:write_failed') or response.startswith('ERR:read_failed')


def _send_command_to_pipe(pipe_name: str, cmd: str, timeout_ms: int = PIPE_TIMEOUT_MS) -> str:
    """发送命令到指定的 Delphi 命名管道。"""
    if getattr(_pipe_session, 'enabled', False):
        session_handle = getattr(_pipe_session, 'handle', None)
        if not session_handle:
            session_handle = _open_pipe(pipe_name, timeout_ms)
            if session_handle is None:
                return f'ERR:pipe_unavailable (err={_GetLastError()})'
            _pipe_session.handle = session_handle
        response = _send_command_on_handle(session_handle, cmd)
        if _is_pipe_io_error(response):
            _CloseHandle(session_handle)
            _pipe_session.handle = None
        return response

    handle = _open_pipe(pipe_name, timeout_ms)
    if handle is None:
        return f'ERR:pipe_unavailable (err={_GetLastError()})'

    try:
        return _send_command_on_handle(handle, cmd)
    finally:
        _CloseHandle(handle)


def _send_command(cmd: str, timeout_ms: int = PIPE_TIMEOUT_MS) -> str:
    """发送命令到 Delphi 命名管道（使用默认管道名）。"""
    return _send_command_to_pipe(PIPE_NAME, cmd, timeout_ms)


def _wait_for_pipe(timeout: float = 10.0, pipe_name: str = PIPE_NAME) -> bool:
    """等待 Delphi 程序创建管道。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _WaitNP(pipe_name, 200):
            return True
        time.sleep(0.2)
    return False


# ── 进程池管理 ──

def _cleanup_stale_processes():
    """清理超时未用的进程。"""
    now = time.time()
    with _pool_lock:
        stale = [k for k, v in _process_pool.items()
                 if now - v['last_used'] > PROCESS_KEEPALIVE_TIMEOUT]
        for key in stale:
            entry = _process_pool.pop(key)
            try:
                entry['proc'].kill()
            except Exception:
                pass


# ═════════════════════════════════════════════════════════════
# Assert 系统 — Python 端后置断言
# ═════════════════════════════════════════════════════════════

def _extract_actual(cmd: str, resp: dict) -> str:
    """从步骤响应中提取可断言的实际值。"""
    if cmd == 'rget':
        return str(resp.get('data', ''))
    if cmd == 'rinspect':
        raw = resp.get('data', '')
        if isinstance(raw, str) and raw.startswith('{'):
            try:
                import json
                parsed = json.loads(raw)
                for p in parsed.get('props', []):
                    if not p.get('name', '').startswith('On'):
                        return str(p.get('type', ''))
            except json.JSONDecodeError:
                pass
        return str(raw)
    if cmd == 'msgscan':
        state = resp.get('state') or resp.get('data', '')
        return str(state) if state else ''
    if cmd == 'waitfor':
        return 'ok' if resp.get('status') in ('ok', 'ack') else 'err'
    if cmd in ('click', 'type', 'key', 'goto', 'rcall', 'rset'):
        return resp.get('status', '')
    if cmd in ('uiascan', 'scan'):
        return str(resp.get('data', ''))
    if cmd in ('uiaget', 'get', 'uiaclick', 'uiagoto', 'uiawait', 'uiaset', 'set'):
        return resp.get('data', '')
    return str(resp.get('data', ''))


def _walk_uia_tree(control, depth: int = 0, max_depth: int = 8) -> dict:
    """递归遍历 UIA 控件树并转成可序列化 dict。

    Args:
        control: uiautomation.Control 实例。
        depth: 当前递归深度。
        max_depth: 最大深度，防止无限递归。

    Returns:
        控件信息 dict: { name, class_name, automation_id,
                         control_type, rect, children: [...] }
    """
    if control is None or depth > max_depth:
        return {}
    try:
        info = {
            'name': control.Name or '',
            'class_name': control.ClassName or '',
            'automation_id': control.AutomationId or '',
            'control_type': str(control.ControlType),
            'rect': [
                control.BoundingRectangle.left,
                control.BoundingRectangle.top,
                control.BoundingRectangle.right,
                control.BoundingRectangle.bottom,
            ] if control.BoundingRectangle and not control.BoundingRectangle.isempty() else [],
        }
        if depth < max_depth:
            children = []
            try:
                child = control.GetFirstChildControl()
                while child:
                    children.append(_walk_uia_tree(child, depth + 1, max_depth))
                    child = child.GetNextSiblingControl()
            except Exception:
                pass
            info['children'] = children
        return info
    except Exception:
        return {}


def _execute_uia_step(step: dict, req: dict, req_id: str) -> tuple:
    """在 Python 端直接执行 UIA 自动化步骤。

    Args:
        step: 原始脚本步骤 dict。
        req: 已构造的请求 dict（含 cmd / target 等字段）。
        req_id: 请求标识符。

    Returns:
        (resp_json, step_ok, ok) 三元组，兼容现有管道返回格式。
    """
    cmd = req.get('cmd', '')
    target = req.get('target', '')
    resp = {'reqId': req_id, 'status': 'ok', 'data': ''}

    if not _UIA_AVAILABLE:
        resp['status'] = 'err'
        resp['data'] = 'uiautomation 未安装，请 pip install daofy-for-delphi[uia]'
        return resp, False, False

    # UIA 需要 COM 初始化为 STA
    ctypes.windll.ole32.CoInitializeEx(None, 2)  # 2 = COINIT_APARTMENTTHREADED
    try:
        if cmd in ('uiagoto', 'goto'):
            # 按 Name 查找控件并聚焦
            ctrl = _UIA_MODULE.Control(Name=target, searchDepth=8)
            if ctrl.Exists():
                ctrl.SetFocus()
                resp['data'] = f'found: {ctrl.Name} ({ctrl.ClassName})'
            else:
                resp['status'] = 'err'
                resp['data'] = f'NF: {target}'
        elif cmd in ('uiaclick', 'click'):
            ctrl = _UIA_MODULE.Control(Name=target, searchDepth=8)
            if ctrl.Exists():
                ctrl.Click()
                resp['data'] = f'clicked: {target}'
            else:
                resp['status'] = 'err'
                resp['data'] = f'NF: {target}'
        elif cmd in ('uiaget', 'get'):
            ctrl = _UIA_MODULE.Control(Name=target, searchDepth=8)
            if ctrl.Exists():
                resp['data'] = ctrl.Name
            else:
                resp['status'] = 'err'
                resp['data'] = f'NF: {target}'
        elif cmd in ('uiaset', 'set'):
            ctrl = _UIA_MODULE.Control(Name=target, searchDepth=8)
            if ctrl.Exists():
                value = str(step.get('value', step.get('text', '')))
                value_pattern = None
                get_value_pattern = getattr(ctrl, 'GetValuePattern', None)
                if callable(get_value_pattern):
                    value_pattern = get_value_pattern()
                if value_pattern is not None and hasattr(value_pattern, 'SetValue'):
                    value_pattern.SetValue(value)
                elif hasattr(ctrl, 'SetValue'):
                    ctrl.SetValue(value)
                elif hasattr(ctrl, 'SendKeys'):
                    ctrl.SetFocus()
                    ctrl.SendKeys('{Ctrl}a')
                    ctrl.SendKeys(value)
                elif hasattr(_UIA_MODULE, 'SendKeys'):
                    ctrl.SetFocus()
                    _UIA_MODULE.SendKeys('{Ctrl}a')
                    _UIA_MODULE.SendKeys(value)
                else:
                    resp['status'] = 'err'
                    resp['data'] = f'UIA_SET_UNSUPPORTED: {target}'
                if resp['status'] == 'ok':
                    resp['data'] = f'set: {target}'
            else:
                resp['status'] = 'err'
                resp['data'] = f'NF: {target}'
        elif cmd in ('uiascan', 'scan'):
            root = _UIA_MODULE.GetRootControl()
            target_ctrl = root
            if target:
                t = _UIA_MODULE.Control(Name=target, searchDepth=8)
                if t.Exists():
                    target_ctrl = t
            tree = _walk_uia_tree(target_ctrl, max_depth=6)
            resp['data'] = json.dumps(tree, ensure_ascii=False, default=str)
            resp['state'] = tree
        elif cmd in ('uiawait', 'wait'):
            timeout_ms = int(step.get('timeout', 5000))
            ctrl = _UIA_MODULE.Control(Name=target, searchDepth=8)
            if ctrl.Exists():
                resp['data'] = f'found: {target}'
            else:
                resp['status'] = 'err'
                resp['data'] = f'TIMEOUT: {target}'
        else:
            resp['status'] = 'err'
            resp['data'] = f'unknown UIA command: {cmd}'

    except Exception as exc:
        resp['status'] = 'err'
        resp['data'] = f'UIA_ERROR: {exc}'
    finally:
        ctypes.windll.ole32.CoUninitialize()

    ok = resp.get('status') in ('ok', 'ack')
    return resp, ok, ok


def _decode_response(resp_raw: str) -> dict:
    """Decode a pipe response, preserving raw text on JSON failure."""
    try:
        return json.loads(resp_raw) if resp_raw else {}
    except json.JSONDecodeError:
        return {'status': 'err', 'data': resp_raw}


def _callgraph_step_error(step: dict, req: dict, message: str) -> dict:
    """Build a local validation error result for callgraph steps."""
    return {
        'step': step,
        'command': json.dumps(req, ensure_ascii=False),
        'response': {'status': 'err', 'data': message},
        'status': 'error',
    }


def _callgraph_local_result(step: dict, req: dict, state: dict) -> dict:
    """Build a successful local callgraph-usecase result."""
    return {
        'step': step,
        'command': json.dumps(req, ensure_ascii=False),
        'response': {
            'status': 'ok',
            'data': json.dumps(state, ensure_ascii=False),
            'state': state,
        },
        'status': 'ok',
    }


def _coerce_callgraph_targets(value: object) -> list[str]:
    """Normalize a callgraph target/functions value to a non-empty name list."""
    if value is None:
        return []

    if isinstance(value, str):
        raw_items: list[object] = value.split(',')
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = [value]

    result: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        name = str(item).strip()
        if not name or name in seen:
            continue
        result.append(name)
        seen.add(name)
    return result


def _dedupe_callgraph_targets(values: list[str]) -> list[str]:
    """Remove duplicate callgraph targets while preserving order."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        target = str(value).strip()
        if not target or target in seen:
            continue
        result.append(target)
        seen.add(target)
    return result


def _coerce_callgraph_locations(step: dict) -> list[dict]:
    """Normalize file/line inputs for callgraph impact analysis."""
    locations: list[dict] = []
    raw_locations = step.get('locations')

    if isinstance(raw_locations, dict):
        locations.append(raw_locations)
    elif isinstance(raw_locations, (list, tuple)):
        locations.extend(item for item in raw_locations if isinstance(item, dict))

    file_value = step.get('file_path', step.get('file'))
    line_value = step.get('line')
    if file_value is not None or line_value is not None:
        locations.append({
            'file': file_value,
            'line': line_value,
        })

    for change in _coerce_callgraph_changes(step):
        file_value = change.get('file_path', change.get('file', change.get('path')))
        line_value = change.get(
            'line',
            change.get('start_line', change.get('new_line', change.get('old_line'))),
        )
        if file_value is not None or line_value is not None:
            locations.append({
                'file': file_value,
                'line': line_value,
            })

    return locations


def _coerce_callgraph_changes(step: dict) -> list[dict]:
    """Normalize change records from review/diff style inputs."""
    raw_changes = step.get('changes', step.get('changed', step.get('changed_locations')))
    if raw_changes is None:
        return []
    if isinstance(raw_changes, dict):
        raw_items = [raw_changes]
    elif isinstance(raw_changes, (list, tuple)):
        raw_items = list(raw_changes)
    else:
        return []
    return [item for item in raw_items if isinstance(item, dict)]


def _callgraph_project_root(step: dict, script_metadata: dict) -> Path | None:
    """Return an optional root used to resolve relative callgraph source paths."""
    raw_root = (
        step.get('base_dir') or
        step.get('project_path') or
        script_metadata.get('base_dir') or
        script_metadata.get('project_path')
    )
    if not raw_root:
        return None

    root = Path(str(raw_root)).expanduser()
    if root.suffix.lower() in ('.dproj', '.dpr', '.dpk', '.pas'):
        root = root.parent
    return root.resolve()


_PASCAL_ROUTINE_RE = re.compile(
    r'^\s*(?:(?:class|static)\s+)?'
    r'(?:procedure|function|constructor|destructor|operator)\s+'
    r'([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\b',
    re.IGNORECASE,
)


def _strip_pascal_line_comment(line: str) -> str:
    """Remove the common // suffix comment form for lightweight scanning."""
    return line.split('//', 1)[0]


def _find_pascal_routine_at_line(source: str, line_number: int) -> str | None:
    """Find the Pascal routine containing a 1-based source line."""
    lines = source.splitlines()
    if line_number < 1 or line_number > len(lines):
        return None

    has_implementation = any(
        re.match(r'^\s*implementation\b', line, re.IGNORECASE)
        for line in lines
    )
    in_implementation = not has_implementation
    routines: list[tuple[int, str]] = []

    for index, raw_line in enumerate(lines, start=1):
        line = _strip_pascal_line_comment(raw_line).strip()
        if re.match(r'^implementation\b', line, re.IGNORECASE):
            in_implementation = True
            continue
        if not in_implementation:
            continue
        match = _PASCAL_ROUTINE_RE.match(line)
        if match:
            routines.append((index, match.group(1)))

    if not routines:
        return None

    for index, (start_line, name) in enumerate(routines):
        end_line = routines[index + 1][0] - 1 if index + 1 < len(routines) else len(lines)
        if start_line <= line_number <= end_line:
            return name
    return None


def _resolve_callgraph_location(location: dict, root: Path | None) -> tuple[str | None, dict | None]:
    """Resolve one file/line location to a Pascal routine name."""
    file_value = location.get('file_path', location.get('file', location.get('path')))
    line_value = location.get('line')
    unresolved_base = {
        'file': str(file_value or ''),
        'line': line_value,
    }

    if not file_value or line_value is None:
        unresolved_base['error_code'] = 'missing_file_or_line'
        return None, unresolved_base

    try:
        line_number = int(line_value)
    except (TypeError, ValueError):
        unresolved_base['error_code'] = 'invalid_line'
        return None, unresolved_base
    if line_number < 1:
        unresolved_base['error_code'] = 'invalid_line'
        return None, unresolved_base

    path = Path(str(file_value)).expanduser()
    if not path.is_absolute():
        if root is None:
            unresolved_base['error_code'] = 'relative_path_requires_base_dir'
            return None, unresolved_base
        path = root / path
    try:
        resolved_path = path.resolve()
    except OSError:
        unresolved_base['error_code'] = 'path_resolve_failed'
        return None, unresolved_base

    if root is not None:
        try:
            resolved_path.relative_to(root)
        except ValueError:
            unresolved_base['error_code'] = 'path_outside_project'
            return None, unresolved_base

    unresolved_base['file'] = str(resolved_path)
    try:
        try:
            source = resolved_path.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:
            source = resolved_path.read_text(encoding='mbcs')
    except OSError as exc:
        unresolved_base['error_code'] = 'source_read_failed'
        unresolved_base['message'] = str(exc)
        return None, unresolved_base

    routine = _find_pascal_routine_at_line(source, line_number)
    if not routine:
        unresolved_base['error_code'] = 'no_function_at_line'
        return None, unresolved_base

    return routine, None


def _resolve_callgraph_impact_targets(
    step: dict,
    script_metadata: dict,
) -> tuple[list[str], list[dict], list[dict]]:
    """Resolve explicit functions and optional file/line locations."""
    targets = _coerce_callgraph_targets(step.get('functions', step.get('targets', step.get('target'))))
    targets.extend(_coerce_callgraph_targets(
        step.get('changed_functions', step.get('changed_targets')),
    ))
    for change in _coerce_callgraph_changes(step):
        targets.extend(_coerce_callgraph_targets(
            change.get('function', change.get('routine', change.get('symbol', change.get('target')))),
        ))
    unresolved: list[dict] = []
    resolved_locations: list[dict] = []
    root = _callgraph_project_root(step, script_metadata)

    for location in _coerce_callgraph_locations(step):
        routine, unresolved_location = _resolve_callgraph_location(location, root)
        if unresolved_location is not None:
            unresolved.append(unresolved_location)
            continue
        if routine:
            targets.append(routine)
            resolved_locations.append({
                'file': str(location.get('file_path', location.get('file', location.get('path', '')))),
                'line': location.get('line'),
                'function': routine,
            })

    return _dedupe_callgraph_targets(targets), unresolved, resolved_locations


def _coerce_callgraph_bool(value: object) -> bool:
    """Parse common JSON/script boolean spellings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'y', 'on')
    return False


def _callgraph_edge_limit_from_step(step: dict) -> int | None:
    """Validate optional callgraph edge_limit from a script step."""
    if 'edge_limit' not in step:
        return None
    try:
        edge_limit = int(step.get('edge_limit'))
    except (TypeError, ValueError):
        raise ValueError('callgraph edge_limit must be an integer') from None
    if edge_limit < 1 or edge_limit > 5000:
        raise ValueError('callgraph edge_limit must be between 1 and 5000')
    return edge_limit


def _callgraph_max_paths_from_step(step: dict) -> int | None:
    """Validate optional callgraph_path max_paths from a script step."""
    if 'max_paths' not in step:
        return None
    try:
        max_paths = int(step.get('max_paths'))
    except (TypeError, ValueError):
        raise ValueError('callgraph_path max_paths must be an integer') from None
    if max_paths < 1 or max_paths > 100:
        raise ValueError('callgraph_path max_paths must be between 1 and 100')
    return max_paths


def _first_present_dict_value(*sources: dict, keys: tuple[str, ...], default: object = None) -> object:
    """Return the first present value from source dictionaries."""
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            if key in source:
                return source[key]
    return default


def _callgraph_diagnostics_enabled(step: dict, script_metadata: dict) -> bool:
    """Return whether failure callgraph diagnostics should run for this step."""
    diagnostics = script_metadata.get('diagnostics', {})
    diag_value = None
    if isinstance(diagnostics, dict) and 'callgraph' in diagnostics:
        diag_value = diagnostics.get('callgraph')
    value = _first_present_dict_value(
        step,
        script_metadata,
        keys=('callgraph_diagnostics', 'callgraph_diag', 'diagnose_callgraph'),
        default=diag_value,
    )
    return _coerce_callgraph_bool(value)


def _callgraph_failure_target(step: dict, script_metadata: dict) -> str:
    """Resolve the function target used for failure callgraph diagnostics."""
    target_map = script_metadata.get('callgraph_targets', {})
    target = str(step.get('target', step.get('name', ''))).strip()
    if isinstance(target_map, dict) and target in target_map:
        mapped = str(target_map.get(target) or '').strip()
        if mapped:
            return mapped

    for key in ('callgraph_target', 'handler', 'entry', 'function', 'routine'):
        value = str(step.get(key, '') or '').strip()
        if value:
            return value

    if step.get('target_is_handler') and target:
        return target
    return ''


def _callgraph_option_source(script_metadata: dict) -> dict:
    """Return script-level callgraph diagnostic options."""
    options = script_metadata.get('callgraph_options', {})
    return options if isinstance(options, dict) else {}


def _callgraph_prefixed_option(
    step: dict,
    script_metadata: dict,
    key: str,
    default: object = None,
) -> object:
    """Read a callgraph diagnostic option from step, callgraph_options, or metadata."""
    options = _callgraph_option_source(script_metadata)
    return _first_present_dict_value(
        step,
        options,
        script_metadata,
        keys=(f'callgraph_{key}', key),
        default=default,
    )


def _callgraph_prefix_text(value: object) -> str:
    """Normalize include/exclude prefix option to pipe protocol text."""
    if value is None:
        return ''
    if isinstance(value, (list, tuple)):
        return ','.join(str(item) for item in value)
    return str(value)


def _callgraph_int_option(value: object, default: int, min_value: int, max_value: int) -> int:
    """Parse and clamp an integer diagnostic option."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def _callgraph_failure_request(
    step: dict,
    script_metadata: dict,
    req_id: str,
) -> tuple[dict | None, dict | None]:
    """Build a bounded callgraph request for a failed step."""
    target = _callgraph_failure_target(step, script_metadata)
    if not target:
        return None, {
            'enabled': True,
            'status': 'skipped',
            'warnings': ['callgraph_target_unresolved'],
        }

    direction = str(_callgraph_prefixed_option(
        step, script_metadata, 'direction', 'callers')).strip().lower()
    aliases = {
        'caller': 'callers',
        'callers': 'callers',
        'up': 'callers',
        'in': 'callers',
        'callee': 'callees',
        'callees': 'callees',
        'down': 'callees',
        'out': 'callees',
    }
    warnings = []
    if direction not in aliases:
        warnings.append('invalid_direction_defaulted_to_callers')
        direction = 'callers'
    else:
        direction = aliases[direction]

    max_depth = _callgraph_int_option(
        _callgraph_prefixed_option(step, script_metadata, 'max_depth', 2), 2, 0, 20)
    edge_limit = _callgraph_int_option(
        _callgraph_prefixed_option(step, script_metadata, 'edge_limit', 20), 20, 1, 5000)

    req = {
        'reqId': f'{req_id}_callgraph_diag',
        'cmd': 'callgraph',
        'target': target,
        'direction': direction,
        'max_depth': str(max_depth),
        'edge_limit': str(edge_limit),
    }

    project_only = _callgraph_prefixed_option(step, script_metadata, 'project_only', None)
    if project_only is not None:
        req['project_only'] = '1' if _coerce_callgraph_bool(project_only) else '0'

    exclude_text = _callgraph_prefix_text(
        _callgraph_prefixed_option(step, script_metadata, 'exclude_prefixes', None))
    if exclude_text:
        req['exclude_prefixes'] = exclude_text

    include_text = _callgraph_prefix_text(
        _callgraph_prefixed_option(step, script_metadata, 'include_prefixes', None))
    if include_text:
        req['include_prefixes'] = include_text

    pre_diag = {
        'enabled': True,
        'target': target,
        'direction': direction,
        'max_depth': max_depth,
        'edge_limit': edge_limit,
    }
    if warnings:
        pre_diag['warnings'] = warnings
    return req, pre_diag


def _callgraph_diagnostic_from_response(req: dict, resp_json: dict, pre_diag: dict) -> dict:
    """Build the report diagnostic payload from a callgraph response."""
    state = {}
    if resp_json.get('data'):
        try:
            parsed = json.loads(resp_json['data'])
            if isinstance(parsed, dict):
                state = parsed
        except (json.JSONDecodeError, TypeError):
            state = {}

    edges = _callgraph_edges(state)
    diag = dict(pre_diag)
    diag.update({
        'status': resp_json.get('status', 'err'),
        'edge_count': int(state.get('edge_count', len(edges))) if isinstance(state, dict) else len(edges),
        'returned_count': int(state.get('returned_count', len(edges))) if isinstance(state, dict) else len(edges),
        'truncated': bool(state.get('truncated', False)) if isinstance(state, dict) else False,
        'calls': edges,
    })
    if isinstance(state, dict):
        for key in ('error_code', 'map_warning'):
            if state.get(key):
                diag[key] = state.get(key)
    if resp_json.get('status') not in ('ok', 'ack'):
        diag.setdefault('warnings', []).append('callgraph_query_failed')
    if req:
        diag['request'] = {
            'target': req.get('target', ''),
            'direction': req.get('direction', ''),
            'max_depth': req.get('max_depth', ''),
            'edge_limit': req.get('edge_limit', ''),
        }
    return diag


def _attach_failure_callgraph_diagnostic(
    result: dict,
    req_id: str,
    script_metadata: dict,
) -> None:
    """Optionally attach callgraph diagnostics to a failed step result."""
    if not _callgraph_diagnostics_enabled(result.get('step', {}), script_metadata):
        return

    req, pre_diag = _callgraph_failure_request(result.get('step', {}), script_metadata, req_id)
    if req is None:
        result.setdefault('diagnostics', {})['callgraph'] = pre_diag or {}
        return

    try:
        raw = _send_command(json.dumps(req, ensure_ascii=False))
        resp_json = _decode_response(raw)
    except Exception as exc:
        result.setdefault('diagnostics', {})['callgraph'] = {
            **(pre_diag or {}),
            'status': 'err',
            'warnings': ['callgraph_query_exception'],
            'error': f'{exc.__class__.__name__}: {exc}',
        }
        return

    result.setdefault('diagnostics', {})['callgraph'] = _callgraph_diagnostic_from_response(
        req, resp_json, pre_diag or {})


def _resolve_snapshot_child_path(
    snapshots_dir: str,
    path_value: object,
    field_name: str,
    *,
    allow_absolute: bool = False,
    add_json_suffix: bool = False,
) -> tuple[Path, Path]:
    """Resolve a snapshot file path and ensure it stays under snapshots_dir."""
    name = str(path_value or '').strip()
    if not name:
        raise ValueError(f'{field_name} cannot be empty')

    path = Path(name)
    if add_json_suffix and path.suffix.lower() != '.json':
        path = path.with_suffix('.json')

    root = Path(snapshots_dir).resolve()
    is_absolute = path.is_absolute() or bool(path.drive) or bool(path.root)
    if is_absolute:
        if not allow_absolute:
            raise ValueError(f'{field_name} must be a relative path under snapshots_dir')
        resolved = path.resolve()
    else:
        if any(part == '..' for part in path.parts):
            raise ValueError(f'{field_name} must stay under snapshots_dir')
        resolved = (root / path).resolve()

    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f'{field_name} must stay under snapshots_dir') from exc
    if resolved == root:
        raise ValueError(f'{field_name} must name a file under snapshots_dir')
    return resolved, relative


def _read_callgraph_baseline(value: object, snapshots_dir: str) -> object:
    """Load a callgraph baseline from a dict/list, JSON string, or JSON file."""
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        raise TypeError('callgraph_diff baseline must be an object, JSON string, or file path')

    raw = value.strip()
    if not raw:
        raise ValueError('callgraph_diff baseline cannot be empty')

    if raw[0] in ('{', '['):
        return json.loads(raw)

    path, _ = _resolve_snapshot_child_path(
        snapshots_dir,
        raw,
        'callgraph_diff baseline_path',
        allow_absolute=True,
    )
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _callgraph_edges(state: object) -> list[dict]:
    """Return the calls array from a callgraph state-like value."""
    if isinstance(state, dict):
        calls = state.get('calls', [])
    elif isinstance(state, list):
        calls = state
    else:
        calls = []
    return [edge for edge in calls if isinstance(edge, dict)]


def _callgraph_edge_key(edge: dict, compare_by: str = 'name') -> tuple[str, ...]:
    """Stable key for comparing callgraph edges."""
    if compare_by == 'name':
        return (
            str(edge.get('from', '')),
            str(edge.get('to', '')),
        )
    if compare_by == 'addr':
        return (
            str(edge.get('from_addr', '')),
            str(edge.get('to_addr', '')),
        )
    if compare_by != 'full':
        raise ValueError('callgraph_diff compare_by must be name, addr, or full')
    return (
        str(edge.get('from', '')),
        str(edge.get('to', '')),
        str(edge.get('from_addr', '')),
        str(edge.get('to_addr', '')),
        str(edge.get('call_addr', '')),
        str(edge.get('call_file', '')),
        str(edge.get('call_line', '')),
    )


def _diff_callgraphs(baseline: object, current: dict, compare_by: str = 'name') -> dict:
    """Compare two callgraph states and return added/removed/unchanged edges."""
    compare_mode = compare_by.strip().lower()
    if compare_mode not in ('name', 'addr', 'full'):
        raise ValueError('callgraph_diff compare_by must be name, addr, or full')

    baseline_edges = _callgraph_edges(baseline)
    current_edges = _callgraph_edges(current)
    baseline_map = {_callgraph_edge_key(edge, compare_mode): edge for edge in baseline_edges}
    current_map = {_callgraph_edge_key(edge, compare_mode): edge for edge in current_edges}

    added_keys = [key for key in current_map if key not in baseline_map]
    removed_keys = [key for key in baseline_map if key not in current_map]
    unchanged_keys = [key for key in current_map if key in baseline_map]

    return {
        'baseline_root': baseline.get('root', '') if isinstance(baseline, dict) else '',
        'current_root': current.get('root', '') if isinstance(current, dict) else '',
        'direction': current.get('direction', '') if isinstance(current, dict) else '',
        'compare_by': compare_mode,
        'added': [current_map[key] for key in added_keys],
        'removed': [baseline_map[key] for key in removed_keys],
        'unchanged': [current_map[key] for key in unchanged_keys],
        'counts': {
            'added': len(added_keys),
            'removed': len(removed_keys),
            'unchanged': len(unchanged_keys),
            'baseline': len(baseline_edges),
            'current': len(current_edges),
        },
    }


def _build_callgraph_impact_state(
    target_states: list[dict],
    initial_unresolved: list[dict] | None = None,
    resolved_locations: list[dict] | None = None,
) -> dict:
    """Build an impact summary from caller-direction callgraph states."""
    entries: list[dict] = []
    unresolved: list[dict] = list(initial_unresolved or [])
    warnings: list[dict] = []
    seen_entries: set[tuple[str, str]] = set()
    targets: list[dict] = []

    for item in target_states:
        target = str(item.get('target', ''))
        response_status = str(item.get('status', 'err'))
        state = item.get('state') if isinstance(item.get('state'), dict) else {}
        edges = _callgraph_edges(state)
        error_code = str(state.get('error_code') or '')

        target_summary = {
            'target': target,
            'status': response_status,
            'edge_count': len(edges),
        }
        if error_code:
            target_summary['error_code'] = error_code
        targets.append(target_summary)

        if error_code and error_code not in ('no_edges', 'filtered_empty'):
            unresolved.append({
                'target': target,
                'error_code': error_code,
                'status': response_status,
            })
        elif response_status not in ('ok', 'ack'):
            unresolved.append({
                'target': target,
                'error_code': 'callgraph_response_error',
                'status': response_status,
            })
        elif error_code in ('no_edges', 'filtered_empty'):
            warnings.append({
                'target': target,
                'warning': error_code,
            })

        for edge in edges:
            caller_name = str(edge.get('from') or '').strip()
            if not caller_name:
                continue
            key = (caller_name, target)
            if key in seen_entries:
                continue
            seen_entries.add(key)
            entries.append({
                'name': caller_name,
                'target': target,
                'via': edge,
            })

    return {
        'mode': 'impact',
        'targets': targets,
        'entries': entries,
        'entry_count': len(entries),
        'unresolved': unresolved,
        'warnings': warnings,
        'resolved_locations': list(resolved_locations or []),
    }


def _load_callgraph_json_value(value: object, snapshots_dir: str) -> object:
    """Load JSON-like callgraph input from an object, JSON text, or file path."""
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        raise TypeError('value must be an object, JSON string, or file path')

    raw = value.strip()
    if not raw:
        raise ValueError('value cannot be empty')
    if raw[0] in ('{', '['):
        return json.loads(raw)

    path, _ = _resolve_snapshot_child_path(
        snapshots_dir,
        raw,
        'callgraph input path',
        allow_absolute=True,
    )
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _callgraph_state_from_step(step: dict, snapshots_dir: str, *keys: str) -> object:
    """Read the first present callgraph state-like field from a step."""
    for key in keys:
        if key in step:
            return _load_callgraph_json_value(step[key], snapshots_dir)
    raise ValueError('missing callgraph state input')


def _save_callgraph_snapshot(snapshots_dir: str, save_as: object, payload: object) -> dict:
    """Save a callgraph payload under snapshots_dir with path traversal protection."""
    path, rel = _resolve_snapshot_child_path(
        snapshots_dir,
        save_as,
        'save_as',
        add_json_suffix=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return {
        'path': rel.as_posix(),
        'edge_count': len(_callgraph_edges(payload)),
    }


def _coerce_callgraph_test_specs(value: object) -> list[dict]:
    """Normalize test script metadata for callgraph-based test selection."""
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]
    result: list[dict] = []
    for item in raw_items:
        if isinstance(item, str):
            result.append({'name': item, 'handler': item})
        elif isinstance(item, dict):
            name = str(item.get('name') or item.get('script') or item.get('path') or '').strip()
            handler = str(item.get('handler') or item.get('entry') or '').strip()
            tags = item.get('tags', [])
            if isinstance(tags, str):
                tags = [part.strip() for part in tags.split(',') if part.strip()]
            result.append({
                **item,
                'name': name or handler,
                'handler': handler,
                'tags': [str(tag) for tag in tags] if isinstance(tags, list) else [],
            })
    return [item for item in result if item.get('name') or item.get('handler')]


def _impact_name_sets(impact: object) -> tuple[set[str], set[str]]:
    """Return impacted caller and target names from an impact state."""
    callers: set[str] = set()
    targets: set[str] = set()
    if not isinstance(impact, dict):
        return callers, targets
    for entry in impact.get('entries', []):
        if not isinstance(entry, dict):
            continue
        if entry.get('name'):
            callers.add(str(entry['name']))
        if entry.get('target'):
            targets.add(str(entry['target']))
    for target in impact.get('targets', []):
        if isinstance(target, dict) and target.get('target'):
            targets.add(str(target['target']))
    return callers, targets


def _build_callgraph_test_selection(impact: object, tests: object) -> dict:
    """Select regression tests whose handler metadata intersects impact entries."""
    callers, targets = _impact_name_sets(impact)
    specs = _coerce_callgraph_test_specs(tests)
    selected: list[dict] = []
    selected_handlers: set[str] = set()

    for spec in specs:
        handler = str(spec.get('handler') or '')
        tags = set(str(tag) for tag in spec.get('tags', []))
        reasons: list[str] = []
        if handler and handler in callers:
            reasons.append('handler_is_impacted_entry')
        if handler and handler in targets:
            reasons.append('handler_is_changed_target')
        matched_tags = sorted(tags.intersection(targets))
        if matched_tags:
            reasons.append('tag_matches_changed_target')
        if not reasons:
            continue
        selected_handlers.add(handler)
        selected.append({
            'name': spec.get('name', handler),
            'handler': handler,
            'path': spec.get('path', spec.get('script', '')),
            'reasons': reasons,
            'matched_tags': matched_tags,
        })

    covered_targets = sorted(target for target in targets if target in selected_handlers)
    return {
        'mode': 'test_selection',
        'selected': selected,
        'selected_count': len(selected),
        'uncovered_targets': sorted(targets.difference(selected_handlers)),
        'covered_targets': covered_targets,
        'warnings': [] if selected else ['no_tests_selected'],
    }


def _match_prefix(value: str, prefixes: object) -> bool:
    """Return whether value starts with any configured prefix."""
    if prefixes is None:
        return True
    if isinstance(prefixes, str):
        prefixes = [prefixes]
    if not isinstance(prefixes, list):
        return False
    return any(value.startswith(str(prefix)) for prefix in prefixes)


def _build_callgraph_boundary_check(graph: object, rules: object) -> dict:
    """Check callgraph edges against prefix-based architecture boundary rules."""
    raw_rules = rules if isinstance(rules, list) else [rules] if isinstance(rules, dict) else []
    violations: list[dict] = []
    for edge in _callgraph_edges(graph):
        caller = str(edge.get('from', ''))
        callee = str(edge.get('to', ''))
        for rule in raw_rules:
            if not isinstance(rule, dict):
                continue
            policy = str(rule.get('policy', rule.get('action', 'forbid'))).lower()
            if policy not in ('forbid', 'deny'):
                continue
            if not _match_prefix(caller, rule.get('from_prefix', rule.get('from_prefixes'))):
                continue
            if not _match_prefix(callee, rule.get('to_prefix', rule.get('to_prefixes'))):
                continue
            violations.append({
                'rule': rule.get('name', ''),
                'from': caller,
                'to': callee,
                'edge': edge,
            })

    return {
        'mode': 'boundary_check',
        'violations': violations,
        'violation_count': len(violations),
        'edge_count': len(_callgraph_edges(graph)),
    }


def _build_callgraph_refactor_check(impact: object, targets: list[str]) -> dict:
    """Build a conservative refactor safety summary from impact data."""
    callers, impacted_targets = _impact_name_sets(impact)
    target_set = set(targets) or impacted_targets
    impacted = [
        entry for entry in (impact.get('entries', []) if isinstance(impact, dict) else [])
        if isinstance(entry, dict) and (not target_set or str(entry.get('target', '')) in target_set)
    ]
    return {
        'mode': 'refactor_check',
        'targets': sorted(target_set),
        'impacted_callers': sorted(callers),
        'impacted_entries': impacted,
        'risk': 'medium' if impacted else 'low',
        'warnings': [
            'static_direct_call_graph_only',
            'virtual_methods_events_rtti_may_be_missing',
        ],
    }


def _build_callgraph_orphan_candidates(symbols: object, graph: object, entries: object) -> dict:
    """Find no-caller candidates from a supplied symbol list and callgraph edges."""
    symbol_names = _coerce_callgraph_targets(symbols)
    entry_names = set(_coerce_callgraph_targets(entries))
    called = {str(edge.get('to', '')) for edge in _callgraph_edges(graph) if edge.get('to')}
    candidates = []
    for symbol in symbol_names:
        if symbol in entry_names or symbol in called:
            continue
        candidates.append({
            'name': symbol,
            'confidence': 'low',
            'reason': 'not_seen_as_callee_in_direct_callgraph',
        })
    return {
        'mode': 'orphan_candidates',
        'candidates': candidates,
        'candidate_count': len(candidates),
        'warnings': [
            'candidate_only_not_safe_to_delete',
            'events_exports_virtual_methods_and_rtti_may_be_missing',
        ],
    }


def _coerce_exception_stack(value: object) -> list[str]:
    """Normalize exception stack input to a list of frame/function strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value)
    return [line.strip() for line in text.splitlines() if line.strip()]


def _build_callgraph_exception_explanation(stack: object, graph: object, impact: object) -> dict:
    """Explain an exception stack with optional callgraph context."""
    frames = _coerce_exception_stack(stack)
    top = frames[0] if frames else ''
    edges = _callgraph_edges(graph)
    upstream = [
        edge for edge in edges
        if top and str(edge.get('to', '')).endswith(top)
    ]
    downstream = [
        edge for edge in edges
        if top and str(edge.get('from', '')).endswith(top)
    ]
    impact_entries = []
    if isinstance(impact, dict):
        impact_entries = [
            entry for entry in impact.get('entries', [])
            if isinstance(entry, dict) and top and str(entry.get('target', '')).endswith(top)
        ]
    return {
        'mode': 'exception_explanation',
        'top_frame': top,
        'frames': frames,
        'upstream': upstream,
        'downstream': downstream,
        'impact_entries': impact_entries,
        'warnings': [] if top else ['empty_stack'],
    }


def _target_with_client_xy(target: str, step: dict) -> str:
    """Encode click x/y fields into the inline-unit target@x,y convention."""
    x_val = step.get('x')
    y_val = step.get('y')
    if x_val is None or y_val is None or '@' in target:
        return target
    return f'{target}@{x_val},{y_val}' if target else f'@{x_val},{y_val}'


def _parse_gui_script(script) -> tuple[list[dict], dict]:
    """Parse a GUI automation script and return steps plus optional metadata."""
    if isinstance(script, str):
        script = script.strip()
        if os.path.isfile(script):
            with open(script, 'r', encoding='utf-8-sig') as f:
                parsed = json.load(f)
        else:
            parsed = json.loads(script)
    else:
        parsed = script

    if isinstance(parsed, list):
        _validate_gui_steps(parsed)
        return parsed, {}

    if isinstance(parsed, dict):
        steps = parsed.get('steps')
        if not isinstance(steps, list):
            raise ValueError("script object must contain a list field named 'steps'")
        metadata = {k: v for k, v in parsed.items() if k != 'steps'}
        _validate_gui_steps(steps)
        return steps, metadata

    raise TypeError('script 须为文件路径、JSON 字符串、步骤列表或包含 steps 的对象')


def _validate_gui_steps(steps: list) -> None:
    """Validate automation step shape before any command is sent to the app."""
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"step {index} must be an object")
        if 'assert' in step:
            raise ValueError(
                f"step {index} uses unsupported field 'assert'; "
                "use 'assert_expr' for executable Python checks"
            )


def _get_assert_expression(step: dict) -> tuple[str, str]:
    """Return the executable assertion expression and its source field."""
    if step.get('assert_expr'):
        return str(step.get('assert_expr', '')).strip(), 'assert_expr'
    return '', ''


def _check_assert(step: dict, resp: dict) -> dict:
    """评估 Python 断言表达式。

    step['assert_expr'] 为 Python 表达式字符串，可用变量:
      actual  — 从步骤响应中提取的实际值
      re      — re 模块
      len/str/int/float/bool — 内置函数

    自然语言说明写入 expected/note，只把可执行 Python 表达式写入 assert_expr。

    示例:
      {"assert_expr": "actual == True"}
      {"assert_expr": "0 < float(actual) < 100"}
      {"assert_expr": "'保存' in actual"}
      {"assert_expr": "'保存' in actual and '成功' in actual"}
      {"assert_expr": "len(actual) > 0"}
      {"assert_expr": "re.search(r'\\\\d+', actual)"}

    Returns:
        {passed: bool, expression: str, source: str, actual: str, message?: str}
    """
    expression, source = _get_assert_expression(step)
    if not expression:
        return {'passed': True}

    cmd = step.get('cmd', '')
    actual = _extract_actual(cmd, resp)

    try:
        ast.parse(expression, mode='eval')
        loc = {
            'actual': actual,
            're': __import__('re'),
            'len': len, 'str': str, 'int': int,
            'float': float, 'bool': bool,
        }
        result = bool(eval(expression, {"__builtins__": {}}, loc))
    except SyntaxError as e:
        return {
            'passed': False,
            'expression': expression,
            'source': source,
            'actual': str(actual)[:200],
            'message': (
                "assert expression syntax error: {}. "
                "Use assert_expr for Python expressions and put natural-language "
                "checks in expected/note."
            ).format(e.msg),
        }
    except Exception as e:
        return {
            'passed': False,
            'expression': expression,
            'source': source,
            'actual': str(actual)[:200],
            'message': f"assert error: {e}",
        }

    out = {
        'passed': result,
        'expression': expression,
        'source': source,
        'actual': str(actual)[:200],
    }
    if not result:
        out['message'] = f"assert failed: {expression}  (actual={actual!r})"
    return out


def _failure_signal(result: dict) -> str:
    """Classify a failed automation result for report consumers."""
    if result.get('status') == 'skipped':
        return 'skipped'
    response = result.get('response', {})
    data = str(response.get('data', ''))
    ast_result = result.get('assert_result', {})
    if result.get('status') == 'assert_fail':
        return 'assertion_failed'
    if result.get('capture_response', {}).get('status') == 'err':
        return 'capture_failed'
    if data.startswith('TIMEOUT:'):
        return 'timeout'
    if data.startswith('NF:'):
        return 'target_not_found'
    if data.startswith('NP:'):
        return 'property_not_found'
    if data.startswith('UIA_ERROR:'):
        return 'uia_error'
    if data.startswith('uiautomation 未安装'):
        return 'uia_not_available'
    if ast_result.get('message'):
        return 'assertion_failed'
    if response.get('status') == 'err':
        return 'command_error'
    return 'unknown'


def _failure_recommendations(signal: str) -> list[str]:
    """Return concise recovery actions for an automation failure signal."""
    table = {
        'assertion_failed': [
            'Compare actual with expected and decide whether the app logic or the test expectation is wrong.',
            'Switch to coding mode if the expected behavior comes from source analysis.',
        ],
        'capture_failed': [
            'Check whether the window is visible and the snapshots_dir is writable.',
            'Run capture as a standalone step after listwnd/formsum.',
        ],
        'timeout': [
            'Capture current UI state, inspect msgscan/formsum, then increase waitfor only if the app is still progressing.',
            'Switch to coding mode if the expected state never appears.',
        ],
        'target_not_found': [
            'Run formsum or dumpstate to refresh control names before retrying.',
            'Switch to coding mode if the control was renamed or not created.',
        ],
        'property_not_found': [
            'Run rinspect on the target and update the property path.',
            'Prefer rget on a simple published property.',
        ],
        'command_error': [
            'Check response.data, capture the current state, and retry with the lowest-risk command.',
            'Switch to coding mode for deterministic application errors.',
        ],
        'uia_error': [
            'Run uiascan to verify the UIA tree is accessible.',
            'Use inspect.exe to confirm the control has a matching Name property.',
        ],
        'uia_not_available': [
            'Install uiautomation: pip install daofy-for-delphi[uia].',
            'Restart the MCP server to reload the import.',
        ],
        'skipped': [
            'Fix the preceding failure before executing this dependent step.',
        ],
    }
    return table.get(signal, ['Capture current state, inspect response.data, and stop before continuing dependent steps.'])


def _make_failure(index: int, result: dict) -> dict:
    """Build a structured failure entry for a report."""
    step = result.get('step', {})
    response = result.get('response', {})
    ast_result = result.get('assert_result', {})
    signal = _failure_signal(result)
    failure = {
        'index': index,
        'phase': step.get('phase', ''),
        'cmd': step.get('cmd', ''),
        'target': step.get('target', step.get('name', '')),
        'signal': signal,
        'response_status': response.get('status', ''),
        'response_data': str(response.get('data', ''))[:500],
        'expected': step.get('expected', ''),
        'note': step.get('note', ''),
        'recommendations': _failure_recommendations(signal),
    }
    if ast_result.get('message'):
        failure['assertion'] = {
            'expression': ast_result.get('expression', ''),
            'source': ast_result.get('source', ''),
            'actual': ast_result.get('actual', ''),
            'message': ast_result.get('message', ''),
        }
    if result.get('capture'):
        failure['evidence'] = {
            'capture': result.get('capture'),
            'capture_response': result.get('capture_response'),
        }
    if result.get('diagnostics'):
        failure['diagnostics'] = result.get('diagnostics')
    return failure


def _make_report(results: list, total_steps: int, duration_seconds: float) -> dict:
    """从执行结果生成结构化测试报告。"""
    passed = 0
    failed = 0
    skipped = 0
    steps_detail = []
    failures = []

    for index, r in enumerate(results):
        step = r.get('step', {})
        ast = r.get('assert_result', {})
        raw_status = r.get('status', '')
        if raw_status == 'skipped':
            status = 'skip'
        else:
            status = 'pass' if (raw_status == 'ok' and ast.get('passed', True)) else 'fail'
        passed += status == 'pass'
        failed += status == 'fail'
        skipped += status == 'skip'
        d = {
            'index': index,
            'phase': step.get('phase', ''),
            'cmd': step.get('cmd', ''),
            'target': step.get('target', step.get('name', '')),
            'status': status,
            'response_status': r.get('response', {}).get('status', ''),
        }
        if ast.get('message'):
            d['error'] = ast['message']
        elif r.get('response', {}).get('status') == 'err':
            d['error'] = str(r.get('response', {}).get('data', ''))[:200]
        steps_detail.append(d)
        if status == 'fail':
            failures.append(_make_failure(index, r))

    solution_status = 'requires_fix' if failures else 'passed'
    return {
        'total': total_steps, 'passed': passed, 'failed': failed, 'skipped': skipped,
        'executed': passed + failed,
        'duration_seconds': round(duration_seconds, 2),
        'success_rate': f'{passed/total_steps*100:.0f}%' if total_steps > 0 else '0%',
        'executed_success_rate': f'{passed/(passed + failed)*100:.0f}%' if (passed + failed) > 0 else '0%',
        'steps': steps_detail,
        'first_failure': failures[0] if failures else None,
        'failures': failures,
        'solution': {
            'status': solution_status,
            'next_mode': 'coding' if failures else 'automation_complete',
            'summary': (
                'Fix the first deterministic failure, then rerun this script from the failing step.'
                if failures else
                'No fix required. Save the passing script and report.'
            ),
            'recommendations': failures[0]['recommendations'] if failures else [],
        },
    }


# ═════════════════════════════════════════════════════════════
# Form Summary — 从 dumpstate JSON 生成紧凑的窗体摘要
# ═════════════════════════════════════════════════════════════

def _curated_control(ctrl: dict) -> dict:
    """从 dumpstate 的 control dict 中提取关键字段，展平到顶层。

    Args:
        ctrl: dumpstate 返回的单个控件 dict（含 name/class/props/children）

    Returns:
        精简后的 dict：关键字段直接展平，props 不嵌套，children → Controls。
    """
    out = {}
    out['Name'] = ctrl.get('name', '?')
    out['Class'] = ctrl.get('class', '?')

    p = ctrl.get('props', {})

    # 文本值：优先 Text，其次 Caption
    if 'Text' in p:
        out['Text'] = p['Text']
    elif 'Caption' in p:
        out['Caption'] = p['Caption']

    # 状态
    for k in ('Enabled', 'Visible'):
        v = p.get(k)
        if v is not None:
            out[k] = v

    # 布局
    for k in ('TabOrder', 'Left', 'Top', 'Width', 'Height'):
        v = p.get(k)
        if v is not None:
            out[k] = v

    # 递归子控件
    raw_children = ctrl.get('children', [])
    if raw_children:
        out['Controls'] = [_curated_control(c) for c in raw_children]

    return out


def _format_form_summary(state: dict) -> dict:
    """将 dumpstate JSON 提炼为纯净的窗体摘要 JSON。

    输出格式与 dumpstate 的关键区别：
    - 只保留关键业务+布局字段（Name/Class/Text/Caption/Enabled/Visible/
      TabOrder/Left/Top/Width/Height），摒弃数百个 RTTI 属性
    - 字段展平到对象顶层，无 props 嵌套
    - 子控件用 Controls（大写 C，匹配用户习惯）
    - 窗体级属性（WindowState/BorderStyle 等）展平到根

    Returns:
        dict: {
            "name": "MainForm", "class": "TMainForm", "caption": "...",
            "WindowState": "wsNormal", "Width": 800, "Height": 600,
            "Controls": [ { "name": "...", "class": "...", ... }, ... ]
        }
    """
    out = {}
    out['Name'] = state.get('form', '?')
    out['Class'] = state.get('class', '?')
    cap = state.get('caption', '')
    if cap:
        out['Caption'] = cap

    # 窗体级属性（展平）
    p = state.get('props', {})
    for k in ('WindowState', 'BorderStyle', 'Position', 'Width', 'Height'):
        v = p.get(k)
        if v is not None:
            out[k] = v

    # 控件列表
    raw_controls = state.get('controls', [])
    # 跳过非可视化组件（菜单/Timer/ImageList 等）
    non_ctrl = {'TMainMenu', 'TPopupMenu', 'TTimer',
                'TImageList', 'TActionList', 'TrayIcon'}
    vis_ctrl = [c for c in raw_controls if c.get('class') not in non_ctrl]
    comp_ctrl = [c for c in raw_controls if c.get('class') in non_ctrl]

    if vis_ctrl:
        out['Controls'] = [_curated_control(c) for c in vis_ctrl]

    # 非可视化组件单独列出
    if comp_ctrl:
        out['Components'] = [
            {'Name': c.get('name', '?'), 'Class': c.get('class', '?')}
            for c in comp_ctrl
        ]

    return out


def _ensure_process(app_path: str, wait_for_pipe: float) -> tuple[bool, str]:
    """确保 app_path 对应的进程在运行。返回 (是否新建, 错误信息)。"""
    _cleanup_stale_processes()

    with _pool_lock:
        if app_path in _process_pool:
            entry = _process_pool[app_path]
            if entry['proc'].poll() is None:
                entry['last_used'] = time.time()
                return False, ''  # 复用已有进程
            # 进程已死，移除
            del _process_pool[app_path]

    # 启动新进程（锁外执行，避免阻塞其他线程）
    try:
        proc = subprocess.Popen(
            [app_path],
            cwd=os.path.dirname(app_path) or None,
        )
    except Exception as e:
        return True, f'启动失败: {e}'

    if not _wait_for_pipe(wait_for_pipe):
        try:
            proc.kill()
        except Exception:
            pass
        return True, f'Delphi 程序未在 {wait_for_pipe}s 内创建管道'

    # 双重检查：锁内确认其他线程未提前注册同一 app_path
    with _pool_lock:
        if app_path in _process_pool:
            # 其他线程已注册，关掉我们新建的进程，复用它
            try:
                proc.kill()
            except Exception:
                pass
            _process_pool[app_path]['last_used'] = time.time()
            return False, ''
        _process_pool[app_path] = {
            'proc': proc,
            'last_used': time.time(),
        }
    return True, ''


def _kill_process(app_path: str):
    """强制终止指定进程。"""
    with _pool_lock:
        entry = _process_pool.pop(app_path, None)
    if entry:
        try:
            entry['proc'].kill()
        except Exception:
            pass


# ── 控制台进程池（独立于 GUI 命名管道池）──

_console_pool: dict[str, dict] = {}
_console_pool_lock = Lock()


def _console_ensure_process(
    app_path: str,
    extra_args: list[str] | None = None,
) -> tuple[bool, str]:
    """确保控制台进程在运行，返回 (是否新建, 错误信息)。

    与 GUI 进程池分离，独立管理。
    """
    _cleanup_stale_console_processes()
    key = f'console:{app_path}'

    with _console_pool_lock:
        if key in _console_pool:
            entry = _console_pool[key]
            if entry['proc'].poll() is None:
                entry['last_used'] = time.time()
                return False, ''  # 复用
            del _console_pool[key]

    # 启动新进程
    cmd = [app_path]
    if extra_args:
        cmd.extend(extra_args)
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(app_path) or None,
        )
    except Exception as e:
        return True, f'启动失败: {e}'

    with _console_pool_lock:
        _console_pool[key] = {
            'proc': proc,
            'last_used': time.time(),
        }
    return True, ''


def _cleanup_stale_console_processes():
    """清理超时未用的控制台进程。"""
    now = time.time()
    with _console_pool_lock:
        stale = [k for k, v in _console_pool.items()
                 if now - v['last_used'] > PROCESS_KEEPALIVE_TIMEOUT]
        for key in stale:
            entry = _console_pool.pop(key)
            try:
                entry['proc'].kill()
            except Exception:
                pass


def _console_kill_process(app_path: str):
    """强制终止指定控制台进程。"""
    key = f'console:{app_path}'
    with _console_pool_lock:
        entry = _console_pool.pop(key, None)
    if entry:
        try:
            entry['proc'].kill()
        except Exception:
            pass


# ── 公共入口 ──

def execute_automation(action: str, **kwargs) -> dict:
    """统一的自动化入口，按 action 分发。

    Args:
        action: "gui" - 命名管道 GUI 自动化
                "console" - subprocess 控制台交互
        **kwargs: 各 action 的参数

    Returns:
        dict 执行结果（各 action 返回格式一致）。
    """
    requested_action = action
    if action == 'gui':
        result = execute_script(**kwargs)
    elif action == 'console':
        result = console_execute(**kwargs)
    else:
        return {'status': 'error', 'message': f'未知 action: {action}', 'requested_action': requested_action}

    if isinstance(result, dict):
        result.setdefault('requested_action', requested_action)
        result.setdefault('resolved_action', action)
    return result


def console_execute(
    app_path: str,
    input_text: str = '',
    expect: str = '',
    timeout: float = 30.0,
    keep_alive: bool = False,
    args: list[str] | None = None,
) -> dict:
    """执行控制台程序交互。

    Args:
        app_path: exe 路径
        input_text: 发送到 stdin 的文本
        expect: 等待的输出正则模式
        timeout: 超时秒数
        keep_alive: True=执行完后保持进程运行供后续复用
        args: 额外命令行参数

    Returns:
        dict: {status, stdout, stderr, exit_code, matched, timed_out}
    """

    is_new, err = _console_ensure_process(app_path, args)
    if err:
        return {'status': 'error', 'message': err}

    key = f'console:{app_path}'
    with _console_pool_lock:
        entry = _console_pool.get(key)
    if not entry:
        return {'status': 'error', 'message': '进程已意外终止'}

    proc: subprocess.Popen = entry['proc']
    matched = False
    timed_out = False
    stdout_buf = io.BytesIO()
    stderr_buf = io.BytesIO()

    try:
        # 发送输入
        if input_text:
            data = input_text.encode('utf-8') if isinstance(input_text, str) else input_text
            proc.stdin.write(data)
            proc.stdin.flush()
            # expect 模式：关 stdin 发 EOF，进程读完输入后自然结束
            if expect:
                try:
                    proc.stdin.close()
                except Exception:
                    pass

        if expect:
            # ── expect 模式：线程 + Queue 实现 Windows 兼容非阻塞读取 ──
            stdout_queue: queue.Queue = queue.Queue()
            stderr_queue: queue.Queue = queue.Queue()
            _stop_reader = threading.Event()

            def _reader_thread(src, dst_queue):
                while not _stop_reader.is_set():
                    try:
                        chunk = src.read(65536)
                        if not chunk:
                            break
                        dst_queue.put(chunk)
                    except Exception:
                        break

            stdout_thread = threading.Thread(
                target=_reader_thread, args=(proc.stdout, stdout_queue), daemon=True)
            stderr_thread = threading.Thread(
                target=_reader_thread, args=(proc.stderr, stderr_queue), daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    chunk = stdout_queue.get(timeout=0.3)
                    stdout_buf.write(chunk)
                    decoded = chunk.decode('utf-8', errors='replace')
                    if re.search(expect, decoded):
                        matched = True
                        break
                except queue.Empty:
                    if proc.poll() is not None:
                        break

            if not matched:
                timed_out = True

            _stop_reader.set()
            stdout_thread.join(timeout=2)
            while True:
                try:
                    stdout_buf.write(stdout_queue.get_nowait())
                except queue.Empty:
                    break
            stderr_thread.join(timeout=1)
            while True:
                try:
                    stderr_buf.write(stderr_queue.get_nowait())
                except queue.Empty:
                    break

            # 如果进程仍在运行，杀死或等待
            if proc.poll() is None:
                if not keep_alive:
                    proc.kill()
                    proc.wait(timeout=5)
                else:
                    proc.wait(timeout=timeout)
        else:
            # ── 无 expect：直接用 communicate ──
            try:
                out, err = proc.communicate(timeout=timeout)
                stdout_buf.write(out)
                stderr_buf.write(err)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    out, err = proc.communicate(timeout=5)
                    stdout_buf.write(out)
                    stderr_buf.write(err)
                except Exception:
                    pass

    except Exception as e:
        if not keep_alive:
            _console_kill_process(app_path)
        return {'status': 'error', 'message': f'控制台交互失败: {e}'}

    exit_code = proc.poll()

    if not keep_alive:
        _console_kill_process(app_path)
    else:
        with _console_pool_lock:
            if key in _console_pool:
                _console_pool[key]['last_used'] = time.time()

    return {
        'status': 'ok' if exit_code == 0 else 'error' if exit_code is not None else 'running',
        'stdout': stdout_buf.getvalue().decode('utf-8', errors='replace'),
        'stderr': stderr_buf.getvalue().decode('utf-8', errors='replace'),
        'exit_code': exit_code if exit_code is not None else -1,
        'matched': matched,
        'timed_out': timed_out,
    }


def execute_script(app_path: str, script,
                   snapshots_dir: str = '',
                   wait_for_pipe: float = 10.0,
                   keep_alive: bool = False,
                   stop_on_failure: bool = True) -> dict:
    """Execute one GUI automation script through the fixed Daofy pipe."""
    with _gui_execution_lock:
        return _execute_script_unlocked(
            app_path,
            script,
            snapshots_dir=snapshots_dir,
            wait_for_pipe=wait_for_pipe,
            keep_alive=keep_alive,
            stop_on_failure=stop_on_failure,
        )


def _execute_script_unlocked(app_path: str, script,
                             snapshots_dir: str = '',
                             wait_for_pipe: float = 10.0,
                             keep_alive: bool = False,
                             stop_on_failure: bool = True) -> dict:
    """执行自动化脚本。

    支持进程池复用：同一个 app_path 在 keep_alive=True 后保持运行，
    后续调用直接复用已有进程。

    Args:
        app_path: Delphi exe 路径
        script: JSON 脚本（文件路径 / JSON 字符串 / list）
        snapshots_dir: 截图输出目录（默认 docs/copyright/snapshots）
        wait_for_pipe: 等待管道超时秒数
        keep_alive: True=执行完后保持进程运行供后续复用
        stop_on_failure: True=首个失败后停止执行后续依赖步骤，并在报告中标为 skipped

    Returns:
        dict 执行结果，包含 process_reused 指示是否复用了已有进程。
    """
    if not snapshots_dir:
        snapshots_dir = str(DEFAULT_SNAPSHOTS_DIR)
    Path(snapshots_dir).mkdir(parents=True, exist_ok=True)
    run_started = time.monotonic()

    # 解析脚本
    try:
        steps, script_metadata = _parse_gui_script(script)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as e:
        return {'status': 'error', 'message': f'脚本解析失败: {e}'}

    # 获取或创建进程
    is_new, err = _ensure_process(app_path, wait_for_pipe)
    if err:
        return {'status': 'error', 'message': err}
    _begin_pipe_session()

    # 新建进程时需要设置截图目录
    if is_new:
        _send_command(json.dumps(
            {"reqId": "init", "cmd": "snapdir", "target": snapshots_dir},
            ensure_ascii=False))
        time.sleep(0.2)

    results = []
    success = True
    req_index = 0

    for step in steps:
        if not success and stop_on_failure:
            results.append({
                'step': step,
                'command': '',
                'response': {'status': 'skip', 'data': 'skipped_after_failure'},
                'status': 'skipped',
                'skip_reason': 'previous_step_failed',
            })
            continue

        cmd = step.get('cmd', '')
        target = step.get('target', step.get('name', ''))
        ms = step.get('ms', step.get('wait', 500))
        capture_name = step.get('capture', '')
        req_id = f'step_{req_index}'
        req_index += 1
        _is_formsum = False
        callgraph_diff_baseline = None
        callgraph_diff_compare_by = 'name'

        # 构造 JSON 请求
        req = {'reqId': req_id, 'cmd': cmd}
        if target:
            req['target'] = target

        # ── UIA 命令路由：Python 端直接执行，不走 Delphi 管道 ──
        _via = step.get('via', '')
        if cmd in _UIA_PREFIX_CMDS or (_via == 'uia' and cmd in _UIA_CAPABLE_CMDS):
            # Already inside _gui_execution_lock (acquired in execute_gui_script),
            # so no inner lock needed — prevents RLock deadlock.
            resp_json, step_ok, ok = _execute_uia_step(step, req, req_id)
            results.append({
                'step': step, 'command': json.dumps(req, ensure_ascii=False),
                'response': resp_json,
                'status': 'ok' if step_ok else 'error',
                'uia_resolved': True,
            })
            assert_result = _check_assert(step, resp_json)
            results[-1]['assert_result'] = assert_result
            if not assert_result.get('passed', True):
                results[-1]['status'] = 'assert_fail'
                step_ok = False
            if not step_ok:
                _attach_failure_callgraph_diagnostic(results[-1], req_id, script_metadata)
            if not step_ok:
                success = False
            time.sleep(0.3)
            continue

        if cmd in (
            'callgraph_select_tests',
            'callgraph_failure_diag',
            'callgraph_boundary_check',
            'callgraph_refactor_check',
            'callgraph_orphan_candidates',
            'callgraph_explain_exception',
        ):
            try:
                if cmd == 'callgraph_select_tests':
                    impact_state = _callgraph_state_from_step(step, snapshots_dir, 'impact', 'state')
                    tests_value = step.get('tests', step.get('test_map'))
                    local_state = _build_callgraph_test_selection(impact_state, tests_value)
                elif cmd == 'callgraph_failure_diag':
                    graph_state = _callgraph_state_from_step(step, snapshots_dir, 'callgraph', 'graph', 'state')
                    failure = step.get('failure', step.get('failed_step', {}))
                    edges = _callgraph_edges(graph_state)
                    local_state = {
                        'mode': 'failure_diagnostic',
                        'failure': failure,
                        'diagnostics': {
                            'callgraph': {
                                'root': graph_state.get('root', '') if isinstance(graph_state, dict) else '',
                                'direction': graph_state.get('direction', '') if isinstance(graph_state, dict) else '',
                                'edge_count': len(edges),
                                'truncated': bool(graph_state.get('truncated', False)) if isinstance(graph_state, dict) else False,
                                'error_code': graph_state.get('error_code', '') if isinstance(graph_state, dict) else '',
                            }
                        },
                        'warnings': [] if edges else ['callgraph_empty_or_unavailable'],
                    }
                elif cmd == 'callgraph_boundary_check':
                    graph_state = _callgraph_state_from_step(step, snapshots_dir, 'callgraph', 'graph', 'state')
                    local_state = _build_callgraph_boundary_check(graph_state, step.get('rules', []))
                elif cmd == 'callgraph_refactor_check':
                    impact_state = _callgraph_state_from_step(step, snapshots_dir, 'impact', 'state')
                    targets = _coerce_callgraph_targets(step.get('targets', step.get('functions', step.get('target'))))
                    local_state = _build_callgraph_refactor_check(impact_state, targets)
                elif cmd == 'callgraph_orphan_candidates':
                    graph_state = step.get('callgraph', step.get('graph', step.get('state', {'calls': []})))
                    if isinstance(graph_state, (str, dict, list)):
                        graph_state = _load_callgraph_json_value(graph_state, snapshots_dir)
                    local_state = _build_callgraph_orphan_candidates(
                        step.get('symbols', []),
                        graph_state,
                        step.get('entries', step.get('entry_points', [])),
                    )
                else:
                    graph_state = step.get('callgraph', step.get('graph', {'calls': []}))
                    impact_state = step.get('impact', {})
                    if isinstance(graph_state, (str, dict, list)):
                        graph_state = _load_callgraph_json_value(graph_state, snapshots_dir)
                    if isinstance(impact_state, (str, dict, list)):
                        impact_state = _load_callgraph_json_value(impact_state, snapshots_dir)
                    local_state = _build_callgraph_exception_explanation(
                        step.get('stack', step.get('exception_stack')),
                        graph_state,
                        impact_state,
                    )
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                results.append(_callgraph_step_error(step, req, f'{cmd} input invalid: {exc}'))
                success = False
                time.sleep(0.3)
                continue

            results.append(_callgraph_local_result(step, req, local_state))
            assert_result = _check_assert(step, results[-1]['response'])
            results[-1]['assert_result'] = assert_result
            if not assert_result.get('passed', True):
                results[-1]['status'] = 'assert_fail'
                success = False
            time.sleep(0.3)
            continue

        if cmd == 'callgraph_impact':
            targets, input_unresolved, resolved_locations = _resolve_callgraph_impact_targets(
                step, script_metadata
            )
            req['targets'] = targets
            req['direction'] = 'callers'
            if input_unresolved:
                req['unresolved'] = input_unresolved
            if resolved_locations:
                req['resolved_locations'] = resolved_locations

            if not targets and not input_unresolved:
                results.append(_callgraph_step_error(
                    step, req, 'callgraph_impact requires functions, targets, target, file/line, or locations'))
                success = False
                time.sleep(0.3)
                continue

            max_depth_val = step.get('max_depth', step.get('depth', 5))
            try:
                max_depth_int = int(max_depth_val)
            except (TypeError, ValueError):
                results.append(_callgraph_step_error(
                    step, req, 'callgraph max_depth must be an integer'))
                success = False
                time.sleep(0.3)
                continue
            if max_depth_int < 0 or max_depth_int > 20:
                results.append(_callgraph_step_error(
                    step, req, 'callgraph max_depth must be between 0 and 20'))
                success = False
                time.sleep(0.3)
                continue
            req['max_depth'] = str(max_depth_int)

            try:
                edge_limit_int = _callgraph_edge_limit_from_step(step)
            except ValueError as exc:
                results.append(_callgraph_step_error(step, req, str(exc)))
                success = False
                time.sleep(0.3)
                continue
            if edge_limit_int is not None:
                req['edge_limit'] = str(edge_limit_int)

            common_options: dict[str, str] = {
                'direction': 'callers',
                'max_depth': str(max_depth_int),
            }
            if edge_limit_int is not None:
                common_options['edge_limit'] = str(edge_limit_int)
            if 'project_only' in step:
                project_only_value = '1' if _coerce_callgraph_bool(step.get('project_only')) else '0'
                req['project_only'] = project_only_value
                common_options['project_only'] = project_only_value

            exclude_val = step.get('exclude_prefixes', step.get('exclude'))
            if exclude_val is not None:
                if isinstance(exclude_val, (list, tuple)):
                    exclude_text = ','.join(str(item) for item in exclude_val)
                else:
                    exclude_text = str(exclude_val)
                req['exclude_prefixes'] = exclude_text
                common_options['exclude_prefixes'] = exclude_text

            include_val = step.get('include_prefixes', step.get('include'))
            if include_val is not None:
                if isinstance(include_val, (list, tuple)):
                    include_text = ','.join(str(item) for item in include_val)
                else:
                    include_text = str(include_val)
                req['include_prefixes'] = include_text
                common_options['include_prefixes'] = include_text

            subcommands = []
            target_states = []
            for target_index, impact_target in enumerate(targets):
                subreq = {
                    'reqId': f'{req_id}_{target_index}',
                    'cmd': 'callgraph',
                    'target': impact_target,
                    **common_options,
                }
                subcommands.append(subreq)
                sub_raw = _send_command(json.dumps(subreq, ensure_ascii=False))
                sub_json = _decode_response(sub_raw)
                parsed_state = {}
                if sub_json.get('data'):
                    try:
                        parsed = json.loads(sub_json['data'])
                        if isinstance(parsed, dict):
                            parsed_state = parsed
                            sub_json['state'] = parsed_state
                    except (json.JSONDecodeError, TypeError):
                        pass
                target_states.append({
                    'target': impact_target,
                    'status': sub_json.get('status', 'err'),
                    'state': parsed_state,
                    'response': sub_json,
                })

            impact_state = _build_callgraph_impact_state(
                target_states,
                initial_unresolved=input_unresolved,
                resolved_locations=resolved_locations,
            )
            resp_json = {
                'status': 'ok',
                'data': json.dumps(impact_state, ensure_ascii=False),
                'state': impact_state,
            }
            results.append({
                'step': step,
                'command': json.dumps(req, ensure_ascii=False),
                'subcommands': subcommands,
                'response': resp_json,
                'status': 'ok',
            })

            assert_result = _check_assert(step, resp_json)
            results[-1]['assert_result'] = assert_result
            if not assert_result.get('passed', True):
                results[-1]['status'] = 'assert_fail'
                success = False
            time.sleep(0.3)
            continue

        if cmd == 'click':
            req['target'] = _target_with_client_xy(target, step)
        elif cmd == 'type':
            req['value'] = step.get('text', step.get('value', target))
        elif cmd == 'wait':
            req['ms'] = str(ms)
        elif cmd in ('rget',):
            parts = target.split('.', 1)
            req['target'] = parts[0]
            if len(parts) > 1:
                req['prop'] = parts[1]
            else:
                req['prop'] = step.get('prop', '')
        elif cmd in ('rset',):
            parts = target.split('.', 1)
            req['target'] = parts[0]
            req['prop'] = parts[1] if len(parts) > 1 else step.get('prop', '')
            req['value'] = step.get('value', step.get('text', ''))
        elif cmd == 'rcall':
            req['method'] = step.get('method', target)
            params_val = step.get('params')
            if params_val is not None:
                req['params'] = json.dumps(params_val, ensure_ascii=False)
        elif cmd == 'move':
            if target:
                req['target'] = target
            x_val = step.get('x')
            y_val = step.get('y')
            if x_val is not None:
                req['x'] = str(x_val)
            if y_val is not None:
                req['y'] = str(y_val)
        elif cmd == 'capture':
            if not target:
                req['target'] = step.get('name', '')
        elif cmd == 'dumpstate':
            req['target'] = step.get('name', target)
            props_val = step.get('props', '')
            if props_val:
                req['props'] = props_val
        elif cmd == 'formsum':
            # formsum = dumpstate → Python 端格式化摘要
            cmd = 'dumpstate'  # 实际发往 Delphi 的是 dumpstate
            req['cmd'] = 'dumpstate'
            req['target'] = step.get('name', target)
            props_val = step.get('props', '')
            if props_val:
                req['props'] = props_val
            _is_formsum = True
        elif cmd == 'waitfor':
            req['prop'] = step.get('prop', '')
            req['value'] = str(step.get('value', ''))
            timeout_val = step.get('timeout', 5000)
            interval_val = step.get('interval', 100)
            req['timeout'] = str(timeout_val)
            req['interval'] = str(interval_val)
        elif cmd == 'key':
            req['key'] = step.get('key', target)
            if target:
                req['target'] = target
        elif cmd == 'drag':
            req['source'] = step.get('source', target)
            tgt = step.get('target', '')
            if tgt:
                req['target'] = tgt
            x_val = step.get('x')
            y_val = step.get('y')
            if x_val is not None:
                req['x'] = str(x_val)
            if y_val is not None:
                req['y'] = str(y_val)
        elif cmd == 'dlgfile':
            path_val = step.get('path', '')
            if path_val:
                req['path'] = path_val
        elif cmd in ('callgraph', 'callgraph_diff', 'callgraph_path'):
            if cmd == 'callgraph_path':
                source_value = step.get('source', step.get('from'))
                target_value = step.get('target', step.get('to', target))
                if source_value is None or str(source_value).strip() == '':
                    results.append(_callgraph_step_error(
                        step, req, 'callgraph_path requires source and target'))
                    success = False
                    time.sleep(0.3)
                    continue
                if target_value is None or str(target_value).strip() == '':
                    results.append(_callgraph_step_error(
                        step, req, 'callgraph_path requires source and target'))
                    success = False
                    time.sleep(0.3)
                    continue
                req['source'] = str(source_value)
                req['target'] = str(target_value)

                try:
                    max_paths_int = _callgraph_max_paths_from_step(step)
                except ValueError as exc:
                    results.append(_callgraph_step_error(step, req, str(exc)))
                    success = False
                    time.sleep(0.3)
                    continue
                if max_paths_int is not None:
                    req['max_paths'] = str(max_paths_int)

            if cmd == 'callgraph_diff':
                req['cmd'] = 'callgraph'
                compare_by = str(step.get('compare_by', 'name')).strip().lower()
                if compare_by not in ('name', 'addr', 'full'):
                    results.append(_callgraph_step_error(
                        step, req, 'callgraph_diff compare_by must be name, addr, or full'))
                    success = False
                    time.sleep(0.3)
                    continue
                callgraph_diff_compare_by = compare_by
                req['compare_by'] = compare_by

                baseline_value = step.get('baseline', step.get('baseline_path'))
                if baseline_value is None:
                    results.append(_callgraph_step_error(
                        step, req, 'callgraph_diff requires baseline or baseline_path'))
                    success = False
                    time.sleep(0.3)
                    continue
                try:
                    callgraph_diff_baseline = _read_callgraph_baseline(baseline_value, snapshots_dir)
                except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    results.append(_callgraph_step_error(
                        step, req, f'callgraph_diff baseline invalid: {exc}'))
                    success = False
                    time.sleep(0.3)
                    continue

            direction_val = step.get('direction', step.get('mode'))
            if direction_val is not None:
                direction = str(direction_val).strip().lower()
                aliases = {
                    'callee': 'callees',
                    'callees': 'callees',
                    'down': 'callees',
                    'out': 'callees',
                    'caller': 'callers',
                    'callers': 'callers',
                    'up': 'callers',
                    'in': 'callers',
                }
                if direction not in aliases:
                    results.append(_callgraph_step_error(
                        step, req, 'callgraph direction must be callers or callees'))
                    success = False
                    time.sleep(0.3)
                    continue
                req['direction'] = aliases[direction]

            if 'project_only' in step:
                req['project_only'] = '1' if _coerce_callgraph_bool(step.get('project_only')) else '0'

            exclude_val = step.get('exclude_prefixes', step.get('exclude'))
            if exclude_val is not None:
                if isinstance(exclude_val, (list, tuple)):
                    req['exclude_prefixes'] = ','.join(str(item) for item in exclude_val)
                else:
                    req['exclude_prefixes'] = str(exclude_val)

            include_val = step.get('include_prefixes', step.get('include'))
            if include_val is not None:
                if isinstance(include_val, (list, tuple)):
                    req['include_prefixes'] = ','.join(str(item) for item in include_val)
                else:
                    req['include_prefixes'] = str(include_val)

            max_depth_val = step.get('max_depth', step.get('depth'))
            if max_depth_val is not None:
                try:
                    max_depth_int = int(max_depth_val)
                except (TypeError, ValueError):
                    resp_json = {
                        'status': 'err',
                        'data': 'callgraph max_depth must be an integer',
                    }
                    results.append({
                        'step': step,
                        'command': json.dumps(req, ensure_ascii=False),
                        'response': resp_json,
                        'status': 'error',
                    })
                    success = False
                    time.sleep(0.3)
                    continue
                if max_depth_int < 0 or max_depth_int > 20:
                    resp_json = {
                        'status': 'err',
                        'data': 'callgraph max_depth must be between 0 and 20',
                    }
                    results.append({
                        'step': step,
                        'command': json.dumps(req, ensure_ascii=False),
                        'response': resp_json,
                        'status': 'error',
                    })
                    success = False
                    time.sleep(0.3)
                    continue
                req['max_depth'] = str(max_depth_int)

            if cmd != 'callgraph_path':
                try:
                    edge_limit_int = _callgraph_edge_limit_from_step(step)
                except ValueError as exc:
                    results.append(_callgraph_step_error(step, req, str(exc)))
                    success = False
                    time.sleep(0.3)
                    continue
                if edge_limit_int is not None:
                    req['edge_limit'] = str(edge_limit_int)

        cmd_str = json.dumps(req, ensure_ascii=False)
        resp_raw = _send_command(cmd_str)

        # 解析 JSON 响应
        resp_json = _decode_response(resp_raw)
        resp_status = resp_json.get('status', 'err')

        ok = resp_status in ('ok', 'ack')

        # ── 异步命令 ack 后短轮询 peekresult ──
        if cmd in _ASYNC_CMDS and resp_status == 'ack':
            await_result = bool(step.get('await_result', False))
            _peek_timeout = float(step.get(
                'async_timeout',
                _ASYNC_PEEK_TIMEOUT if await_result or cmd not in _UI_ASYNC_CMDS
                else _UI_ASYNC_PEEK_TIMEOUT,
            ))
            _poll_interval = 0.05
            _deadline = time.time() + max(_peek_timeout, 0.0)
            while time.time() < _deadline:
                _peek_raw = _send_command(json.dumps(
                    {"reqId": f"{req_id}_peek", "cmd": "peekresult", "target": req_id},
                    ensure_ascii=False))
                _peek_json = _decode_response(_peek_raw)
                if _peek_json.get('status') == 'ok':
                    resp_json = _peek_json
                    resp_status = 'ok'
                    ok = True
                    break
                if (_peek_json.get('status') == 'err' and
                        str(_peek_json.get('data', '')).startswith('NR:')):
                    time.sleep(_poll_interval)
                    continue
                resp_json = _peek_json
                resp_status = _peek_json.get('status', 'err')
                ok = resp_status in ('ok', 'ack')
                break

        capture_resp_json = None
        capture_ok = True

        # dumpstate/dlgscan 返回 JSON 字符串；msgscan 检测到弹窗时把弹窗 JSON 写入 _formstate.json。
        if cmd in ('callgraph', 'callgraph_diff', 'callgraph_path') and resp_json.get('data'):
            try:
                parsed = json.loads(resp_json['data'])
                resp_json['state'] = parsed
                if cmd == 'callgraph_diff' and ok and isinstance(parsed, dict):
                    diff_state = _diff_callgraphs(
                        callgraph_diff_baseline,
                        parsed,
                        callgraph_diff_compare_by,
                    )
                    if step.get('save_as') is not None:
                        try:
                            diff_state['saved'] = _save_callgraph_snapshot(
                                snapshots_dir,
                                step.get('save_as'),
                                parsed,
                            )
                        except (OSError, ValueError) as exc:
                            diff_state.setdefault('warnings', []).append(
                                f'save_as_failed: {exc}'
                            )
                    resp_json['callgraph'] = parsed
                    resp_json['state'] = diff_state
                    resp_json['data'] = json.dumps(diff_state, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                pass
        elif cmd in ('dumpstate', 'dlgscan') and ok and resp_json.get('data'):
            try:
                parsed = json.loads(resp_json['data'])
                resp_json['state'] = parsed
            except (json.JSONDecodeError, TypeError):
                pass
        elif cmd == 'msgscan' and ok and resp_json.get('data') == 'OK':
            state_path = Path(snapshots_dir) / '_formstate.json'
            try:
                resp_json['state'] = json.loads(
                    state_path.read_text(encoding='utf-8-sig')
                )
            except (OSError, json.JSONDecodeError):
                pass
        # uiascan 返回 JSON 控件树 → 自动反序列化到 state 字段
        elif cmd in ('uiascan', 'scan') and ok and resp_json.get('data'):
            try:
                raw = resp_json['data']
                if isinstance(raw, str):
                    parsed = json.loads(raw)
                    resp_json['state'] = parsed
                elif isinstance(raw, dict):
                    resp_json['state'] = raw
            except (json.JSONDecodeError, TypeError):
                pass

        # formsum：将 dumpstate JSON 格式化为紧凑摘要
        if _is_formsum and ok and resp_json.get('state'):
            try:
                resp_json['summary'] = _format_form_summary(resp_json['state'])
            except Exception:
                resp_json['summary'] = '(form summary failed)'

        if capture_name and cmd != 'capture':
            capture_raw = _send_command(json.dumps(
                {"reqId": f"cap_{req_id}", "cmd": "capture", "target": capture_name},
                ensure_ascii=False))
            capture_resp_json = _decode_response(capture_raw)
            capture_ok = capture_resp_json.get('status', 'err') in ('ok', 'ack')

        step_ok = ok and capture_ok
        results.append({
            'step': step, 'command': cmd_str,
            'response': resp_json,
            'status': 'ok' if step_ok else 'error',
        })
        if capture_name and cmd != 'capture':
            results[-1]['capture'] = capture_name
            results[-1]['capture_response'] = capture_resp_json

        # ⭐ Assert 检查 — Python 端后置验证
        assert_result = _check_assert(step, resp_json)
        results[-1]['assert_result'] = assert_result
        if not assert_result.get('passed', True):
            results[-1]['status'] = 'assert_fail'
            step_ok = False

        if not step_ok:
            _attach_failure_callgraph_diagnostic(results[-1], req_id, script_metadata)
            success = False
        time.sleep(0.3)

    # keep_alive=False：确保进程退出（脚本没 exit 则自动发送）
    if not keep_alive:
        has_exit = any(
            r.get('step', {}).get('cmd') == 'exit' and r.get('status') != 'skipped'
            for r in results
        )
        if not has_exit:
            _send_command(json.dumps(
                {"reqId": "auto_exit", "cmd": "exit"}, ensure_ascii=False))
            time.sleep(0.5)
        # 给进程一点时间退出，从池中移除
        time.sleep(0.5)
        with _pool_lock:
            _process_pool.pop(app_path, None)

    _end_pipe_session()

    return {
        'status': 'ok' if success else 'partial',
        'app_path': app_path,
        'snapshots_dir': snapshots_dir,
        'steps_total': len(steps),
        'script_metadata': script_metadata,
        'process_reused': not is_new,
        'process_alive': app_path in _process_pool,
        'results': results,
        'resolved_action': 'gui',
        'report': _make_report(results, len(steps), time.monotonic() - run_started),
    }
