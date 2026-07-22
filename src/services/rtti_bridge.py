r"""
Delphi RTTI 桥接服务 — 管理 Delphi 应用的 RTTI 能力发现和调用。

使用已有的 automation_service 命名管道通信，
将 Delphi 端的 RTTI 发现结果转换为 MCP 可用格式。

通信协议：
  请求: {"reqId":"...", "cmd":"rtti_discover", "target":"TMainForm"}
  响应: {"reqId":"...", "status":"ok", "data":{...JSON...}}

进程注册发现：
  Delphi 应用启动时写入 %TEMP%\daofy-rtti-{PID}.json，
  MCP 扫描这些文件自动发现运行中的应用。
"""

import glob
import json
import logging
import os
import time
from ctypes import wintypes
from typing import Optional

from src.constants import POLL_INTERVAL_AUTOMATION
from src.services.automation_service import (
    PIPE_NAME,
    _send_command,
    _send_command_to_pipe,
    _ensure_process,
    _process_pipe_name,
    _pool_lock,
    _process_pool,
    _WaitNP,
)

logger = logging.getLogger(__name__)


def _send_rtti_command(app_path: str, command: str) -> str:
    """Send RTTI traffic to the pooled process without breaking legacy mocks."""
    pipe_name = _process_pipe_name(app_path)
    if pipe_name == PIPE_NAME:
        return _send_command(command)
    return _send_command_to_pipe(pipe_name, command)

# ── 注册文件发现（%TEMP%\daofy-rtti-*.json）──

REGISTRY_PATTERN = "daofy-rtti-*.json"

# ctypes for PID liveness check (OpenProcess)
_k32 = __import__("ctypes", fromlist=[""]).windll.kernel32
_OpenProcess = _k32.OpenProcess
_OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_OpenProcess.restype = wintypes.HANDLE
_CloseHandle = _k32.CloseHandle
_CloseHandle.argtypes = [wintypes.HANDLE]
_CloseHandle.restype = wintypes.BOOL
PROCESS_QUERY_INFORMATION = 0x0400
SYNCHRONIZE = 0x00100000


def _is_pid_alive(pid: int) -> bool:
    """检查 PID 是否存活（通过 OpenProcess）。"""
    h = _OpenProcess(PROCESS_QUERY_INFORMATION | SYNCHRONIZE, False, pid)
    if h:
        _CloseHandle(h)
        return True
    return False


def scan_running_apps() -> list[dict]:
    """扫描注册文件，返回运行中的 Delphi 应用列表。

    Returns:
        list[dict]: [{pipe, pid, name, timestamp}, ...]
    """
    apps = []
    temp_dir = os.environ.get("TEMP", "")
    if not temp_dir:
        return apps

    pattern = os.path.join(temp_dir, REGISTRY_PATTERN)
    for filepath in glob.glob(pattern):
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        pid = data.get("pid")
        pipe = data.get("pipe")
        name = data.get("name", "Unknown")

        if not pid or not pipe:
            continue

        # 检查 PID 是否存活
        if not _is_pid_alive(pid):
            continue

        # 验证管道可连接
        try:
            if not _WaitNP(pipe, 1000):
                continue
        except Exception:
            continue

        apps.append({
            "pipe": pipe,
            "pid": pid,
            "name": name,
            "timestamp": data.get("timestamp", 0),
        })

    return apps


class RttiBridge:
    """管理一个或多个 Delphi 应用的 RTTI 桥接。

    每个 app_path 对应一个独立的 Delphi 进程和命名管道。
    使用 keep_alive 保持长连接，避免重复启动。

    Pipe-based discover：
      通过注册文件发现已运行的应用，无需手动指定 app_path。
      使用 scan_running_apps() → list_running_apps() 获取可用应用列表。
    """

    def __init__(self):
        self._cache: dict[str, dict] = {}  # app_path → discovery result
        self._cache_time: dict[str, float] = {}
        self._cache_ttl: float = 300  # 缓存 5 分钟
        self._pipe_cache: dict[str, dict] = {}  # pipe_name → discovery result
        self._pipe_cache_time: dict[str, float] = {}
        self._app_pipe_map: dict[str, str] = {}  # app_name → pipe_name

    def _is_cache_valid(self, app_path: str) -> bool:
        if app_path not in self._cache:
            return False
        return (time.time() - self._cache_time.get(app_path, 0)) < self._cache_ttl

    def list_running_apps(self) -> dict:
        """列出所有通过注册文件发现且管道可达的应用。

        返回:
            dict: {status, apps: [{pipe, pid, name, timestamp}, ...]}
        """
        apps = scan_running_apps()
        return {"status": "ok", "apps": apps}

    def discover_from_pipe(self, pipe_name: str, class_name: str = "",
                           force: bool = False) -> dict:
        r"""通过管道名直接发现 RTTI 能力（不依赖 app_path，仅依赖注册文件）。

        Args:
            pipe_name: 命名管道路径，如 \\.\pipe\daofy_auto
            class_name: 限定的类名，空串则扫描所有
            force: 强制刷新缓存

        Returns:
            dict: {status, classes: [...], ...}
        """
        cache_key = pipe_name

        # 缓存命中
        if not force and cache_key in self._pipe_cache:
            cached = self._pipe_cache[cache_key]
            age = time.time() - self._pipe_cache_time.get(cache_key, 0)
            if age < self._cache_ttl:
                if class_name:
                    for cls in cached.get("classes", []):
                        if cls.get("className") == class_name:
                            return {"status": "ok", "class": cls}
                    return {"status": "ok", "classes": cached.get("classes", [])}
                return {"status": "ok", **cached}

        # 发送 rtti_discover 命令到指定的管道
        req = {
            "reqId": f"disc_{int(time.time() * 1000)}",
            "cmd": "rtti_discover",
            "target": class_name,
        }
        resp_raw = _send_command_to_pipe(pipe_name, json.dumps(req, ensure_ascii=False))
        if resp_raw.startswith("ERR:"):
            return {"status": "error", "message": resp_raw}

        try:
            resp = json.loads(resp_raw)
        except (json.JSONDecodeError, TypeError) as e:
            return {"status": "error", "message": f"无效响应: {resp_raw} ({e})"}

        if resp.get("status") != "ok":
            return {"status": "error", "message": resp.get("data", "未知错误")}

        # 解析 data 字段
        data_raw = resp.get("data", "{}")
        if isinstance(data_raw, str):
            try:
                data = json.loads(data_raw)
            except (json.JSONDecodeError, TypeError):
                data = {"raw": data_raw}
        elif isinstance(data_raw, dict):
            data = data_raw
        else:
            data = {"raw": str(data_raw)}

        # 更新缓存
        if not class_name:
            self._pipe_cache[cache_key] = data
            self._pipe_cache_time[cache_key] = time.time()

        return {"status": "ok", **data}

    def auto_discover_all(self, force: bool = False) -> list[dict]:
        """自动发现所有运行中的 Delphi 应用的能力。

        Args:
            force: 强制刷新缓存

        Returns:
            list[dict]: [{pipe, name, status, result}, ...]
        """
        apps = scan_running_apps()
        results = []
        for app in apps:
            pipe = app["pipe"]
            result = self.discover_from_pipe(pipe, "", force)
            results.append({
                "pipe": pipe,
                "name": app["name"],
                "pid": app["pid"],
                "status": result.get("status"),
            })
            if result.get("status") == "ok":
                self._app_pipe_map[app["name"]] = pipe
        return results

    def connect(self, app_path: str, wait_for_pipe: float = 10.0) -> dict:
        """连接 Delphi 应用（启动进程或复用已有）。

        Args:
            app_path: Delphi exe 路径
            wait_for_pipe: 等待管道就绪的超时秒数

        Returns:
            dict: {status, reused, message}
        """
        is_new, err = _ensure_process(app_path, wait_for_pipe)
        if err:
            return {"status": "error", "message": err}
        return {"status": "ok", "reused": not is_new}

    def discover(self, app_path: str, class_name: str = "",
                 force: bool = False) -> dict:
        """发现 Delphi 应用的 RTTI 能力。

        Args:
            app_path: Delphi exe 路径
            class_name: 限定的类名，空串则扫描所有
            force: 强制刷新缓存

        Returns:
            dict: {status, classes: [...], ...}
        """
        # 缓存命中
        if not force and self._is_cache_valid(app_path):
            cached = self._cache[app_path]
            if class_name:
                for cls in cached.get("classes", []):
                    if cls.get("className") == class_name:
                        return {"status": "ok", "class": cls}
                return {"status": "ok", "classes": cached.get("classes", [])}
            return {"status": "ok", **cached}

        # 确保进程运行
        _, err = _ensure_process(app_path, 10.0)
        if err:
            return {"status": "error", "message": err}
        time.sleep(POLL_INTERVAL_AUTOMATION)  # 给管道一点时间就绪

        # 发送 rtti_discover 命令
        req = {
            "reqId": f"disc_{int(time.time() * 1000)}",
            "cmd": "rtti_discover",
            "target": class_name,
        }
        resp_raw = _send_rtti_command(
            app_path,
            json.dumps(req, ensure_ascii=False),
        )
        if resp_raw.startswith("ERR:"):
            return {"status": "error", "message": resp_raw}

        try:
            resp = json.loads(resp_raw)
        except (json.JSONDecodeError, TypeError) as e:
            return {"status": "error", "message": f"无效响应: {resp_raw} ({e})"}

        if resp.get("status") != "ok":
            return {"status": "error", "message": resp.get("data", "未知错误")}

        # 解析 data 字段中的 JSON（Delphi 端 WriteResp 会序列化 data）
        data_raw = resp.get("data", "{}")
        if isinstance(data_raw, str):
            try:
                data = json.loads(data_raw)
            except (json.JSONDecodeError, TypeError):
                data = {"raw": data_raw}
        elif isinstance(data_raw, dict):
            data = data_raw
        else:
            data = {"raw": str(data_raw)}

        # 更新缓存
        if not class_name:
            self._cache[app_path] = data
            self._cache_time[app_path] = time.time()

        return {"status": "ok", **data}

    def call(self, app_path: str, class_name: str,
             method: str, params: Optional[dict] = None) -> dict:
        """调用 Delphi 应用的 RTTI 暴露方法。

        Args:
            app_path: Delphi exe 路径
            class_name: 类名
            method: 方法名
            params: 参数字典

        Returns:
            dict: {status, data, response}
        """
        # 确保进程运行
        _, err = _ensure_process(app_path, 10.0)
        if err:
            return {"status": "error", "message": err}

        req = {
            "reqId": f"call_{int(time.time() * 1000)}",
            "cmd": "rcall",
            "target": class_name,
            "method": method,
        }
        if params:
            req["params"] = json.dumps(params, ensure_ascii=False)

        resp_raw = _send_rtti_command(
            app_path,
            json.dumps(req, ensure_ascii=False),
        )
        if resp_raw.startswith("ERR:"):
            return {"status": "error", "message": resp_raw}

        try:
            resp = json.loads(resp_raw)
        except (json.JSONDecodeError, TypeError) as e:
            return {"status": "error", "message": f"无效响应: {resp_raw} ({e})"}

        return {
            "status": resp.get("status", "error"),
            "data": resp.get("data", ""),
            "response": resp,
        }

    def clear_cache(self, app_path: Optional[str] = None):
        """清除缓存。"""
        if app_path:
            self._cache.pop(app_path, None)
            self._cache_time.pop(app_path, None)
        else:
            self._cache.clear()
            self._cache_time.clear()


# 全局单例
_rtti_bridge = RttiBridge()


def get_rtti_bridge() -> RttiBridge:
    return _rtti_bridge
