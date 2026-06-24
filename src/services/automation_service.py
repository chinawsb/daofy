r"""
自动化测试服务 — GUI 命名管道 + 控制台 subprocess 交互。

通信方式：命名管道 \\.\pipe\daofy_auto（Delphi server -> Python client）
使用 ctypes 直接调用 Windows API，零外部依赖。

协议：JSON 请求/响应 (REST-style)
  请求: {"reqId":"step_0","cmd":"goto","target":"TForm1"}
  响应: {"reqId":"step_0","status":"ok","data":"OK"}
    (async 命令: click/rclick/dblclick/hover/move/drag/msgclick/dlgclick/rcall/key/rset/type 返回 ACK，
    同步命令: goto/capture/waitfor/wait/dumpstate/listwnd/dlgscan/msgscan/msgclose/dlgfile/snapdir/exit/rget/rinspect 阻塞等待返回。
    异步结果通过后续 peekresult 命令或 waitfor/rget/capture 验证获取，无文件落盘。)

进程池复用：
  通过 keep_alive 参数让 Delphi 进程常驻，后续调用直接复用。
  进程超过 PROCESS_KEEPALIVE_TIMEOUT 未被使用会自动清理。
"""

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
from threading import Lock

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

# ── 进程池 ──
_process_pool: dict[str, dict] = {}
_pool_lock = Lock()
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


def _send_command_to_pipe(pipe_name: str, cmd: str, timeout_ms: int = PIPE_TIMEOUT_MS) -> str:
    """发送命令到指定的 Delphi 命名管道。"""
    handle = _open_pipe(pipe_name, timeout_ms)
    if handle is None:
        return f'ERR:pipe_unavailable (err={_GetLastError()})'

    try:
        if not _write_pipe(handle, cmd.encode('utf-8')):
            return f'ERR:write_failed (err={_GetLastError()})'

        raw = _read_pipe_message(handle)
        if raw is None:
            return f'ERR:read_failed (err={_GetLastError()})'
        return raw.decode('utf-8', errors='replace').strip()
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
    return str(resp.get('data', ''))


def _decode_response(resp_raw: str) -> dict:
    """Decode a pipe response, preserving raw text on JSON failure."""
    try:
        return json.loads(resp_raw) if resp_raw else {}
    except json.JSONDecodeError:
        return {'status': 'err', 'data': resp_raw}


def _check_assert(step: dict, resp: dict) -> dict:
    """评估 Python 断言表达式。

    step['assert'] 为 Python 表达式字符串，可用变量:
      actual  — 从步骤响应中提取的实际值
      re      — re 模块
      len/str/int/float/bool — 内置函数

    注意: 此接口由前端 LLM 调用，LLM 已可执行任意 Python 脚本，
    因此 eval 不做沙箱限制，仅需清晰说明可用的命名空间。

    示例:
      {"assert": "actual == True"}
      {"assert": "0 < float(actual) < 100"}
      {"assert": "'保存' in actual"}
      {"assert": "'保存' in actual and '成功' in actual"}
      {"assert": "len(actual) > 0"}
      {"assert": "re.search(r'\\\\d+', actual)"}

    Returns:
        {passed: bool, expression: str, actual: str, message?: str}
    """
    expression = step.get('assert', '')
    if not expression:
        return {'passed': True}

    cmd = step.get('cmd', '')
    actual = _extract_actual(cmd, resp)

    try:
        loc = {
            'actual': actual,
            're': __import__('re'),
            'len': len, 'str': str, 'int': int,
            'float': float, 'bool': bool,
        }
        result = bool(eval(expression, {"__builtins__": {}}, loc))
    except Exception as e:
        return {
            'passed': False,
            'expression': expression,
            'actual': str(actual)[:200],
            'message': f"assert error: {e}",
        }

    out = {
        'passed': result,
        'expression': expression,
        'actual': str(actual)[:200],
    }
    if not result:
        out['message'] = f"assert failed: {expression}  (actual={actual!r})"
    return out


def _make_report(results: list, total_steps: int) -> dict:
    """从执行结果生成结构化测试报告。"""
    import time
    passed = 0
    failed = 0
    steps_detail = []
    start = time.time()

    for r in results:
        step = r.get('step', {})
        ast = r.get('assert_result', {})
        status = 'pass' if (r['status'] == 'ok' and ast.get('passed', True)) else 'fail'
        passed += status == 'pass'
        failed += status == 'fail'
        d = {'cmd': step.get('cmd', ''), 'target': step.get('target', ''), 'status': status}
        if ast.get('message'):
            d['error'] = ast['message']
        steps_detail.append(d)

    dur = time.time() - start
    return {
        'total': total_steps, 'passed': passed, 'failed': failed,
        'duration_seconds': round(dur, 2),
        'success_rate': f'{passed/total_steps*100:.0f}%' if total_steps > 0 else '0%',
        'steps': steps_detail,
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
    if action == 'gui':
        return execute_script(**kwargs)
    elif action == 'console':
        return console_execute(**kwargs)
    else:
        return {'status': 'error', 'message': f'未知 action: {action}'}


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
                   keep_alive: bool = False) -> dict:
    """执行自动化脚本。

    支持进程池复用：同一个 app_path 在 keep_alive=True 后保持运行，
    后续调用直接复用已有进程。

    Args:
        app_path: Delphi exe 路径
        script: JSON 脚本（文件路径 / JSON 字符串 / list）
        snapshots_dir: 截图输出目录（默认 docs/copyright/snapshots）
        wait_for_pipe: 等待管道超时秒数
        keep_alive: True=执行完后保持进程运行供后续复用

    Returns:
        dict 执行结果，包含 process_reused 指示是否复用了已有进程。
    """
    if not snapshots_dir:
        snapshots_dir = str(DEFAULT_SNAPSHOTS_DIR)
    Path(snapshots_dir).mkdir(parents=True, exist_ok=True)

    # 解析脚本
    if isinstance(script, str):
        script = script.strip()
        steps = json.loads(open(script, 'r', encoding='utf-8')) if os.path.isfile(script) else json.loads(script)
    elif isinstance(script, list):
        steps = script
    else:
        return {'status': 'error', 'message': 'script 须为文件路径、JSON 字符串或列表'}

    # 获取或创建进程
    is_new, err = _ensure_process(app_path, wait_for_pipe)
    if err:
        return {'status': 'error', 'message': err}

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
        cmd = step.get('cmd', '')
        target = step.get('target', step.get('name', ''))
        ms = step.get('ms', step.get('wait', 500))
        capture_name = step.get('capture', '')
        req_id = f'step_{req_index}'
        req_index += 1
        _is_formsum = False

        # 构造 JSON 请求
        req = {'reqId': req_id, 'cmd': cmd}
        if target:
            req['target'] = target

        if cmd == 'type':
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
        elif cmd == 'formsum':
            # formsum = dumpstate → Python 端格式化摘要
            cmd = 'dumpstate'  # 实际发往 Delphi 的是 dumpstate
            req['cmd'] = 'dumpstate'
            req['target'] = step.get('name', target)
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

        cmd_str = json.dumps(req, ensure_ascii=False)
        resp_raw = _send_command(cmd_str)

        # 解析 JSON 响应
        resp_json = _decode_response(resp_raw)
        resp_status = resp_json.get('status', 'err')

        ok = resp_status in ('ok', 'ack')

        # ── 异步命令 ack 后轮询 peekresult 取回真实结果 ──
        if cmd in _ASYNC_CMDS and resp_status == 'ack':
            _peek_timeout = 6.0
            _poll_interval = 0.05
            _deadline = time.time() + _peek_timeout
            while time.time() < _deadline:
                _peek_raw = _send_command(json.dumps(
                    {"reqId": f"{req_id}_peek", "cmd": "peekresult", "target": req_id},
                    ensure_ascii=False))
                _peek_json = _decode_response(_peek_raw)
                if _peek_json.get('status') == 'ok':
                    # 取到真实结果，替换 ack
                    resp_json = _peek_json
                    resp_status = 'ok'
                    ok = True
                    break
                # 仅当 status=err + data 以 NR: 开头时继续轮询（尚未就绪）
                if not (_peek_json.get('status') == 'err' and
                        str(_peek_json.get('data', '')).startswith('NR:')):
                    break  # 非预期响应，停止
                time.sleep(_poll_interval)

        capture_resp_json = None
        capture_ok = True

        # dumpstate/dlgscan 返回的就是 JSON 字符串，存到响应的 state 字段
        if cmd in ('dumpstate', 'dlgscan') and ok and resp_json.get('data'):
            try:
                parsed = json.loads(resp_json['data'])
                resp_json['state'] = parsed
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
            success = False
        time.sleep(0.3)

    # keep_alive=False：确保进程退出（脚本没 exit 则自动发送）
    if not keep_alive:
        has_exit = any(s.get('cmd') == 'exit' for s in steps)
        if not has_exit:
            _send_command(json.dumps(
                {"reqId": "auto_exit", "cmd": "exit"}, ensure_ascii=False))
            time.sleep(0.5)
        # 给进程一点时间退出，从池中移除
        time.sleep(0.5)
        with _pool_lock:
            _process_pool.pop(app_path, None)

    return {
        'status': 'ok' if success else 'partial',
        'app_path': app_path,
        'snapshots_dir': snapshots_dir,
        'steps_total': len(steps),
        'process_reused': not is_new,
        'process_alive': app_path in _process_pool,
        'results': results,
        'report': _make_report(results, len(steps)),
    }
