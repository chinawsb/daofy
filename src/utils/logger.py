"""
日志工具模块

提供统一的日志配置和获取方法
功能:
- 按日期分文件日志 (delphi_mcp_YYYY-MM-DD.log)
- 历史日志自动 7z 压缩归档
- API 调用参数/返回值日志 (受配置开关控制)
"""

import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from ..constants import TIMEOUT_ARCHIVE_7Z


# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------

@dataclass
class LogConfig:
    """日志配置"""
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_api_calls: bool = False
    archive_old_logs: bool = True
    keep_days: int = 7
    console_logging: bool = False


_CONFIG_FILE_NAME = "config/logging_config.json"
_LOG_FORMAT = "%(asctime)s - PID:%(process)d - %(name)s - %(levelname)s - %(message)s"
_LOG_FILE_PREFIX = "delphi_mcp"

# 缓存配置
_log_config: Optional[LogConfig] = None


def _log_nonfatal(message: str, exc: Exception) -> None:
    """Log best-effort cleanup errors without requiring module logger setup."""
    logging.getLogger("delphi_mcp").debug(message, str(exc))


def _get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent.parent


def _load_log_config() -> LogConfig:
    """从 config/logging_config.json 加载日志配置"""
    global _log_config
    if _log_config is not None:
        return _log_config

    cfg_path = _get_project_root() / _CONFIG_FILE_NAME
    config = LogConfig()
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            config.log_level = data.get("log_level", config.log_level).upper()
            config.log_dir = data.get("log_dir", config.log_dir)
            config.log_api_calls = data.get("log_api_calls", config.log_api_calls)
            config.archive_old_logs = data.get("archive_old_logs", config.archive_old_logs)
            config.keep_days = int(data.get("keep_days", config.keep_days))
            config.console_logging = data.get("console_logging", config.console_logging)
        except Exception as e:
            _log_nonfatal("忽略非致命异常: %s", e)
    _log_config = config
    return config


def reload_log_config() -> LogConfig:
    """重新加载日志配置（运行时更新用）"""
    global _log_config
    _log_config = None
    return _load_log_config()


def should_log_api_calls() -> bool:
    """检查是否启用了 API 调用日志"""
    return _load_log_config().log_api_calls


# ---------------------------------------------------------------------------
# 历史日志 7z 归档
# ---------------------------------------------------------------------------

def _find_7z_path() -> Optional[str]:
    """查找 7z 可执行文件路径"""
    # 优先用项目自带的 tools/7z/7z.exe
    builtin = _get_project_root() / "tools" / "7z" / "7z.exe"
    if builtin.exists():
        return str(builtin)
    for name in ("7z", "7z.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def archive_old_logs(log_dir: Optional[str] = None) -> None:
    """
    将历史日志文件压缩为 7z 并删除原文件。
    每天只保留一个 7z 归档。超过 keep_days 天的旧归档自动删除。

    多进程安全: 使用 pid 文件互斥，避免同时归档。

    Args:
        log_dir: 日志目录，默认从配置读取
    """
    config = _load_log_config()
    if not config.archive_old_logs:
        return

    log_path = Path(log_dir) if log_dir else _get_project_root() / config.log_dir
    if not log_path.exists():
        return

    seven_z = _find_7z_path()
    if not seven_z:
        return  # 无 7z 工具，跳过归档

    # 多进程互斥锁: 用 .archive_lock 文件防止并行归档
    lock_file = log_path / ".archive_lock"
    if lock_file.exists():
        return  # 其他进程正在归档，跳过
    try:
        lock_file.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        return

    try:
        today_str = date.today().isoformat()  # YYYY-MM-DD
        keep_days = max(config.keep_days, 1)

        # ---------------------------------------------------------------
        # 1) 删除超出保留天数的旧 .7z 归档
        # ---------------------------------------------------------------
        for archive_file in sorted(log_path.glob(f"{_LOG_FILE_PREFIX}_*.7z")):
            stem = archive_file.stem
            date_part = stem.replace(f"{_LOG_FILE_PREFIX}_", "")
            try:
                file_date = date.fromisoformat(date_part)
                if (date.today() - file_date).days > keep_days:
                    archive_file.unlink()
            except (ValueError, OverflowError):
                pass  # 文件名格式不符，跳过

        # ---------------------------------------------------------------
        # 2) 压缩旧 .log 文件到 .7z
        # ---------------------------------------------------------------
        for log_file in sorted(log_path.glob(f"{_LOG_FILE_PREFIX}_*.log")):
            # 从文件名提取日期: delphi_mcp_YYYY-MM-DD.log
            stem = log_file.stem  # delphi_mcp_YYYY-MM-DD
            date_part = stem.replace(f"{_LOG_FILE_PREFIX}_", "")
            if date_part == today_str:
                continue  # 今天的日志不归档

            archive_name = log_path / f"{stem}.7z"
            if archive_name.exists():
                # 已存在归档，删掉源文件（可能上次压缩成功但没删掉）
                try:
                    log_file.unlink()
                except Exception as e:
                    _log_nonfatal("忽略非致命异常: %s", e)
                continue

            # 用 7z 压缩
            try:
                result = subprocess.run(
                    [seven_z, "a", "-t7z", "-mx=5", str(archive_name), str(log_file)],
                    capture_output=True, text=True, timeout=TIMEOUT_ARCHIVE_7Z,
                )
                if result.returncode == 0 and archive_name.exists():
                    log_file.unlink()
            except Exception as e:
                _log_nonfatal("忽略非致命异常: %s", e)
    finally:
        # 释放锁
        try:
            lock_file.unlink()
        except Exception as e:
            _log_nonfatal("忽略非致命异常: %s", e)


# ---------------------------------------------------------------------------
# Logger 核心
# ---------------------------------------------------------------------------

def _resolve_log_level(level_str: str = "INFO") -> int:
    mapping = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return mapping.get(level_str.upper(), logging.INFO)


def _get_today_log_path(log_dir: Path) -> Path:
    """生成当天的日志文件路径: logs/delphi_mcp_YYYY-MM-DD.log"""
    today_str = date.today().isoformat()
    return log_dir / f"{_LOG_FILE_PREFIX}_{today_str}.log"


_initialized = False


_root_handlers_initialized = False
_file_logging_warning_emitted = False


def _warn_file_logging_unavailable(log_path: Path, exc: OSError) -> None:
    """Report a file logging failure without depending on logger setup."""
    global _file_logging_warning_emitted
    if _file_logging_warning_emitted:
        return

    _file_logging_warning_emitted = True
    try:
        print(
            "[Daofy] 日志目录无法写入: "
            f"{log_path.parent}；需宿主授权写入或配置可写目录，"
            f"后续文件日志将被忽略。原因: {exc}",
            file=sys.stderr,
            flush=True,
        )
    except Exception:
        # stderr 已关闭/编码不支持：警告本身也不能让启动失败
        pass


# ---------------------------------------------------------------------------
# stderr 处理器：MCP stdio 场景下的安全网
# ---------------------------------------------------------------------------
# 背景（真实故障）：
#   MCP stdio 服务器把 stderr 当旁路诊断通道，但客户端不保证持续排空它。
#   管道写满后，logging 的同步 emit 会永久阻塞；而 logging 是在 asyncio 事件
#   循环线程里被同步调用的，于是整个 server 卡死——连 initialize 都回应不了，
#   客户端只看到请求超时，然后反复重启 server，形成死循环。
#   并且 handler 是同步串行调用的：控制台处理器若排在文件处理器之前，
#   stderr 一卡，文件日志也一起停摆。
#
#   故本模块的约束是：
#     1) 文件处理器必须先挂；
#     2) stderr 只在"确认可写"或"可取消"的前提下写，调用方永不阻塞；
#     3) 后台消化线程不会永久卡在 write 上（卡太久就取消它），否则解释器退出
#        时会等这个线程，进程退不出去（Python 3.12+ 的 finalization 行为）。
# ---------------------------------------------------------------------------

# POSIX 管道一次可安全写入的字节数（PIPE_BUF 的最小保证值）。只要剩余空间
# 不少于这个数，写请求就不会阻塞。宁可分片/丢日志，也不冒卡死的风险。
# Windows 侧不用这个值，走 NtQueryInformationFile 的可写配额。
_PIPE_BUF_HINT = 512
# 一次写超过这个时长仍未返回，就认定管道堵了（客户端不读了）
_WRITE_STUCK_SECONDS = 2.0
# 判定堵死后，暂停 stderr 写多久再试探
_STDERR_BLOCKED_COOLDOWN = 30.0

# 惰性构造的"管道可写配额"查询器缓存：None=未初始化，False=不可用
_pipe_quota_probe = None


def _probe_stderr(stream) -> "tuple[str, int]":
    """探测 stderr 的写入安全性。

    Returns:
        ("pipe", free)  free > 0：可安全写入的字节数（保守估计）
                        free == 0：管道已满，现在不能写
                        free == -1：确认是管道，但剩余空间无法得知（配额查询失败）
        ("other", 0)    普通文件/控制台/内存流：写入不会因"无人读取"而阻塞
        ("unknown", 0)  无法判定（按最坏情况处理：不写）
    """
    try:
        fd = stream.fileno()
    except Exception:
        # 内存流（StringIO 等）没有 fd，但写它不会阻塞
        return "other", 0

    if os.name != "nt":
        try:
            import select as _select
            import stat as _stat

            if not _stat.S_ISFIFO(os.fstat(fd).st_mode):
                return "other", 0
            _, writable, _ = _select.select([], [fd], [], 0)
            return "pipe", (_PIPE_BUF_HINT if writable else 0)
        except Exception:
            return "unknown", 0

    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        handle = wintypes.HANDLE(msvcrt.get_osfhandle(fd))
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        if kernel32.GetFileType(handle) != 3:  # FILE_TYPE_PIPE
            return "other", 0
        # PeekNamedPipe 要的是读端句柄，对写端调用必然失败（实测
        # ERROR_ACCESS_DENIED=5）；改用 NtQueryInformationFile 读可写配额，
        # 拿不到就报 -1（空间未知），由可取消的后台写兜底。
        quota_probe = _get_pipe_quota_probe()
        free = quota_probe(handle) if quota_probe else None
        return "pipe", (free if free is not None else -1)
    except Exception:
        return "unknown", 0


def _get_pipe_quota_probe():
    """惰性构造"管道可写配额"查询器；平台不支持时返回 None。

    写端句柄不能用 PeekNamedPipe（那是读端接口），但 NtQueryInformationFile 的
    FilePipeLocalInformation 会给出 WriteQuotaAvailable —— 当前还能写多少字节。
    实测：空管道=4096、写满=0、读走 2KB 后=2048。
    """
    global _pipe_quota_probe
    if _pipe_quota_probe is not None:
        return _pipe_quota_probe or None
    try:
        import ctypes
        from ctypes import wintypes

        class IO_STATUS_BLOCK(ctypes.Structure):
            _fields_ = [("Status", ctypes.c_void_p), ("Information", ctypes.c_size_t)]

        class FILE_PIPE_LOCAL_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("NamedPipeType", wintypes.ULONG),
                ("NamedPipeConfiguration", wintypes.ULONG),
                ("MaximumInstances", wintypes.ULONG),
                ("CurrentInstances", wintypes.ULONG),
                ("InboundQuota", wintypes.ULONG),
                ("ReadDataAvailable", wintypes.ULONG),
                ("OutboundQuota", wintypes.ULONG),
                ("WriteQuotaAvailable", wintypes.ULONG),
                ("NamedPipeState", wintypes.ULONG),
                ("NamedPipeEnd", wintypes.ULONG),
            ]

        ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
        ntdll.NtQueryInformationFile.restype = ctypes.c_long
        ntdll.NtQueryInformationFile.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(IO_STATUS_BLOCK),
            ctypes.c_void_p,
            wintypes.ULONG,
            ctypes.c_int,
        ]

        def probe(handle) -> "Optional[int]":
            iosb = IO_STATUS_BLOCK()
            info = FILE_PIPE_LOCAL_INFORMATION()
            status = ntdll.NtQueryInformationFile(
                handle,
                ctypes.byref(iosb),
                ctypes.byref(info),
                ctypes.sizeof(info),
                0x18,  # FilePipeLocalInformation
            )
            if status != 0:
                return None
            return int(info.WriteQuotaAvailable)

        _pipe_quota_probe = probe
    except Exception:
        _pipe_quota_probe = False  # 明确标记不可用
    return _pipe_quota_probe or None


def _cancel_thread_io(thread) -> bool:
    """取消某个线程正在进行的同步 I/O（Windows CancelSynchronousIo）。

    把"卡在管道 write 上的后台线程"解救出来，保证进程可以正常退出。
    非 Windows 或取消失败时返回 False。
    """
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenThread.restype = wintypes.HANDLE
        kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.CancelSynchronousIo.restype = wintypes.BOOL
        kernel32.CancelSynchronousIo.argtypes = [wintypes.HANDLE]
        thread_terminate = 0x0001
        handle = kernel32.OpenThread(
            thread_terminate, False, ctypes.c_ulong(thread.ident or 0)
        )
        if not handle:
            return False
        try:
            return bool(kernel32.CancelSynchronousIo(handle))
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return False


class _SafeStderrHandler(logging.StreamHandler):
    """写 stderr 的控制台处理器：能确认空间才直写，其余交给可取消的后台写。

    - 继承 StreamHandler，保持 isinstance 语义与标准库一致；
    - 文件/控制台/内存流：直接写，日志即时可见；
    - POSIX 管道：先探测可写空间，够就写、不够就丢（写请求不会阻塞）；
    - Windows 管道：用 NtQueryInformationFile 取可写配额（见 _probe_stderr）；
      配额查询不到时退回后台线程写，并用 CancelSynchronousIo 看门狗取消卡住的写。
      因此 emit（业务线程）永不阻塞，也不会留下一个永久卡在 write 上的线程——
      否则解释器退出时会等它，进程退不出去。
    """

    _MAX_QUEUE = 128

    def __init__(self, stream, level: int = logging.NOTSET) -> None:
        super().__init__(stream)
        self.setLevel(level)
        self._queue: "queue.Queue[str]" = queue.Queue(maxsize=self._MAX_QUEUE)
        self._writing = False
        self._write_started = 0.0
        self._closing = False
        self._blocked_until = 0.0
        self._thread = threading.Thread(
            target=self._pump, name="daofy-stderr-writer", daemon=True
        )
        self._thread.start()

    # -- 内部工具 ---------------------------------------------------------
    def _write_now(self, text: str) -> None:
        """尽力写一段；任何异常（管道满/EAGAIN/被取消/已关闭）都吞掉。"""
        try:
            self.stream.write(text)
            self.stream.flush()
        except Exception:
            pass

    def _write_best_effort(self, text: str) -> None:
        """分片写完整条记录；空间不足立即放弃剩余部分，绝不阻塞。"""
        while text:
            kind, free = _probe_stderr(self.stream)
            if kind == "unknown":
                return
            if kind == "pipe":
                if free < 0:
                    # 空间未知（Windows 管道写端）：整条交给一次可取消的写
                    self._write_now(text)
                    return
                if free == 0:
                    return  # 客户端不读了：丢弃剩余，宁可丢日志也不能卡死
                chunk, text = text[:free], text[free:]
            else:
                chunk, text = text, ""
            self._write_now(chunk)

    def _pump(self) -> None:
        while True:
            if self._closing:
                return
            text = self._queue.get()
            if text is None:
                return
            if time.monotonic() < self._blocked_until:
                continue  # 刚判定管道堵死：这段时间直接丢日志
            self._writing = True
            self._write_started = time.monotonic()
            try:
                self._write_best_effort(text)
            finally:
                self._writing = False

    def _cancel_stuck_write(self, force: bool = False) -> None:
        """写卡太久就取消它，避免线程永久阻塞（进程退出也就不会挂住）。"""
        if not self._writing:
            return
        if not force and time.monotonic() - self._write_started <= _WRITE_STUCK_SECONDS:
            return
        if _cancel_thread_io(self._thread):
            self._blocked_until = time.monotonic() + _STDERR_BLOCKED_COOLDOWN

    # -- logging.Handler 接口 --------------------------------------------
    def emit(self, record: logging.LogRecord) -> None:
        self._cancel_stuck_write()
        try:
            text = self.format(record) + "\n"
        except Exception:
            return

        kind, free = _probe_stderr(self.stream)
        if kind == "other":
            self._write_now(text)
            return
        if kind == "pipe" and 0 < free and len(text) <= free:
            self._write_now(text)
            return
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            # 客户端读不过来就丢日志，宁可丢日志也不能卡死服务
            pass

    def flush(self) -> None:
        # 直写路径自带 flush；这里保持 no-op，避免退出期去 flush 一个卡住的流
        pass

    def handleError(self, record: logging.LogRecord) -> None:
        # 默认实现会把异常再打到 stderr（可能继续阻塞或递归），直接吞掉
        pass

    def close(self) -> None:
        # 先发退出信号（队列满时靠 _closing 兜底），再取消在飞的阻塞写：
        # Python 3.12+ 退出时会等 daemon 线程，留一个卡在 write 上的线程
        # 会让进程退不出去。
        self._closing = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        for _ in range(2):
            self._cancel_stuck_write(force=True)
            try:
                self._thread.join(timeout=0.5)
            except Exception:
                pass
            if not self._thread.is_alive():
                break
        # 不能调 StreamHandler.close()：它会把 self.stream（也就是 sys.stderr）
        # 一起 close()，导致进程后续所有 stderr 输出失效。
        logging.Handler.close(self)


def setup_logger(
    name: str = "delphi_mcp",
    level: Optional[int] = None,
    log_file: Optional[str] = None,
    format_string: Optional[str] = None,
) -> logging.Logger:
    """
    配置并返回日志记录器。

    handler 会同时挂载到 root logger，确保所有子模块
    (通过 get_logger(__name__) 获取的独立 logger) 的日志也能正常输出。

    Args:
        name: 日志记录器名称
        level: 日志级别, 不传则从配置读取
        log_file: 日志文件路径, 不传则使用日期文件
        format_string: 日志格式字符串

    Returns:
        配置好的日志记录器
    """
    global _root_handlers_initialized

    logger = logging.getLogger(name)
    if logger.handlers and _root_handlers_initialized:
        return logger

    if level is None:
        level = _resolve_log_level(_load_log_config().log_level)
    logger.setLevel(level)

    if format_string is None:
        format_string = _LOG_FORMAT
    formatter = logging.Formatter(format_string)

    # 文件处理器
    file_handler: Optional[logging.FileHandler] = None
    file_logging_failed = False
    if log_file or _load_log_config().log_dir:
        if log_file:
            log_path = Path(log_file)
        else:
            log_dir = _get_project_root() / _load_log_config().log_dir
            log_path = _get_today_log_path(log_dir)

        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
        except OSError as exc:
            file_logging_failed = True
            _warn_file_logging_unavailable(log_path, exc)

    # 顺序很重要：文件处理器必须先挂。handler 是同步串行调用的，控制台一旦
    # 出问题，排在它后面的文件日志也会一起停摆。
    if file_handler is not None:
        logger.addHandler(file_handler)

    if file_logging_failed:
        # File logging is best-effort.  A NullHandler prevents later log calls
        # from raising or falling back to repeated stderr output.
        logger.addHandler(logging.NullHandler())

    # 控制台处理器 (stderr, 避免干扰 MCP stdio) — 默认关闭。
    # 仅当配置 console_logging=true 时输出到控制台；
    # 否则全部日志（含运行时日志）只写文件。
    # 与文件日志解耦：日志目录不可写时，用户显式请求的控制台输出依然保留。
    # 写入走 _SafeStderrHandler：客户端不排空 stderr 时丢日志，而不是卡死服务。
    if _load_log_config().console_logging:
        console_handler = _SafeStderrHandler(sys.stderr, level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # 同时挂载 handler 到 root logger
    # 否则 get_logger(__name__) 创建的子 logger 日志传播到 root 时，
    # 因 root 无 handler 而丢失。
    if not _root_handlers_initialized:
        root = logging.getLogger()
        # 避免重复添加
        existing = {str(h) for h in root.handlers}
        for h in logger.handlers:
            if str(h) not in existing:
                root.addHandler(h)
        _root_handlers_initialized = True

    # 禁止 delphi_mcp 向上传播到 root，否则 handler 会执行两次造成重复
    if name != "":
        logger.propagate = False

    return logger


def get_logger(name: str = "delphi_mcp") -> logging.Logger:
    """获取日志记录器"""
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# 默认日志记录器
# ---------------------------------------------------------------------------

_default_logger: Optional[logging.Logger] = None


def init_default_logger(log_file: Optional[str] = None) -> logging.Logger:
    """
    初始化默认日志记录器。
    首次调用时自动执行: 加载配置 + 归档旧日志 + 设置日志记录器。

    注意: 各模块通过 get_logger(__name__) 获取独立子 logger，
    它们的级别继承自 root logger。因此必须同时设置 root 级别。
    否则仅设置 "delphi_mcp" 的级别，其他模块的 DEBUG 日志不会被输出。

    Args:
        log_file: 日志文件路径, 不传则使用日期文件

    Returns:
        默认日志记录器
    """
    global _default_logger, _initialized

    if _default_logger is not None and _initialized:
        return _default_logger

    # 1) 加载配置
    config = _load_log_config()
    level = _resolve_log_level(config.log_level)

    # 2) 设置 root logger 级别（确保所有模块的子 logger 继承正确的级别）
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 3) 归档旧日志 (仅首次)
    if not _initialized:
        archive_old_logs()

    # 4) 设置日志
    if log_file is None:
        log_dir = _get_project_root() / config.log_dir
        log_file = str(_get_today_log_path(log_dir))

    _default_logger = setup_logger(log_file=log_file, level=level)
    _default_logger.info(f"日志系统初始化完成 - 级别: {config.log_level}, 文件: {log_file}")
    _initialized = True
    return _default_logger


def get_default_logger() -> logging.Logger:
    """获取默认日志记录器"""
    global _default_logger
    if _default_logger is None:
        _default_logger = init_default_logger()
    return _default_logger


# ---------------------------------------------------------------------------
# API 调用日志 (受开关控制)
# ---------------------------------------------------------------------------

def log_api_call(logger: logging.Logger, tool_name: str, arguments: dict, result) -> None:
    """
    记录 API 调用参数和返回值。
    只在 log_api_calls=True 时生效。

    Args:
        logger: 日志记录器
        tool_name: 工具名
        arguments: 调用参数
        result: 返回值
    """
    if not should_log_api_calls():
        return

    # 过滤敏感参数 (如路径中的密码)
    safe_args = {}
    for k, v in arguments.items():
        if any(sensitive in k.lower() for sensitive in ("password", "secret", "token", "key")):
            safe_args[k] = "****"
        else:
            safe_args[k] = v

    try:
        args_text = json.dumps(safe_args, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        args_text = str(safe_args)
    logger.debug(">>> API 调用: %s | 参数: %s", tool_name, args_text)

    # 记录返回值 (截断避免日志过大)
    result_str = str(result)
    if len(result_str) > 2000:
        result_str = result_str[:2000] + "... (truncated)"

    logger.debug("<<< API 返回: %s | 结果: %s", tool_name, result_str)
