#!/usr/bin/env python3
"""Daofy MCP Server 安装/卸载脚本 - 配置 AI Agent"""

VERSION = "2026-06-07 10:30"  # 版本号随实际修改时间更新

import argparse
import ctypes
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
import winreg
from pathlib import Path

MCP_SERVER_NAME = "daofy"
LEGACY_SERVER_NAME = "delphi-compiler"

# 退出码契约（install.bat 根据 errorlevel 区分提示）
# 0 = 成功（MCP Server 已配置/卸载）
# 1 = 失败（前置条件不满足、输入无效、所有配置都失败等）
# 2 = 用户主动取消（按 q 退出、确认卸载时按 n 等，不算失败也不算成功）
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_CANCELLED = 2


def _encode_toml_value(value) -> str:
    """将 Python 值编码为 TOML 内联格式。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
        return f'"{escaped}"'
    if isinstance(value, list):
        items = ", ".join(_encode_toml_value(v) for v in value)
        return f"[{items}]"
    if isinstance(value, dict):
        items = ", ".join(f'{k} = {_encode_toml_value(v)}' for k, v in value.items())
        return "{" + items + "}"
    return str(value)


def _toml_dumps_section(section_name: str, entries: dict) -> str:
    """将 {name: {fields...}} 字典序列化为 TOML [[section]] 格式。"""
    lines: list[str] = []
    for name, fields in entries.items():
        lines.append(f"[{section_name}.{name}]")
        for k, v in fields.items():
            lines.append(f'{k} = {_encode_toml_value(v)}')
        lines.append("")
    return "\n".join(lines)


def _toml_parse(text: str) -> dict:
    """简易 TOML 解析（仅限 mcp_servers 场景）。"""
    import re
    result: dict = {}
    current_key = None
    current_val = None
    section_pattern = re.compile(r'^\[(\S+)\]$')
    kv_pattern = re.compile(r'^(\w[\w_]*)\s*=\s*(.+)$')
    inline_table_pattern = re.compile(r'^\{(.*)\}$')

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        m = section_pattern.match(line)
        if m:
            if current_key and current_val is not None:
                parts = current_key.split(".", 1)
                if len(parts) == 2:
                    top = parts[0]
                    sub = parts[1]
                    if top not in result:
                        result[top] = {}
                    result[top][sub] = current_val
            current_key = m.group(1)
            current_val = None
            continue
        m = kv_pattern.match(line)
        if m and current_key is not None:
            key = m.group(1)
            raw = m.group(2)
            # 简单值解析
            if raw.lower() == "true":
                val = True
            elif raw.lower() == "false":
                val = False
            elif raw.startswith('"') and raw.endswith('"'):
                val = raw[1:-1].replace('\\"', '"').replace('\\\\', '\\')
            elif raw.startswith('{') and raw.endswith('}'):
                # 内联表
                inner = raw[1:-1].strip()
                val = {}
                if inner:
                    for part in inner.split(","):
                        part = part.strip()
                        if "=" in part:
                            k, v = part.split("=", 1)
                            k = k.strip()
                            v = v.strip()
                            if v.startswith('"') and v.endswith('"'):
                                val[k] = v[1:-1].replace('\\"', '"').replace('\\\\', '\\')
                            elif v.lower() == "true":
                                val[k] = True
                            elif v.lower() == "false":
                                val[k] = False
                            else:
                                val[k] = v
            elif raw.startswith('[') and raw.endswith(']'):
                inner = raw[1:-1].strip()
                val = []
                if inner:
                    for item in inner.split(","):
                        item = item.strip()
                        if item.startswith('"') and item.endswith('"'):
                            val.append(item[1:-1].replace('\\"', '"').replace('\\\\', '\\'))
                        else:
                            val.append(item)
            else:
                val = raw
            if current_val is None:
                current_val = {}
            current_val[key] = val

    if current_key and current_val is not None:
        parts = current_key.split(".", 1)
        if len(parts) == 2:
            top = parts[0]
            sub = parts[1]
            if top not in result:
                result[top] = {}
            result[top][sub] = current_val

    return result


def _enable_ansi() -> bool:
    """启用 Windows CMD ANSI 支持，返回是否成功"""
    if sys.platform != "win32":
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        for handle_id in (-11, -12):
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        return True
    except Exception:
        return False


_HAS_COLOR = _enable_ansi()

# ANSI 颜色
GREEN = "\033[92m" if _HAS_COLOR else ""
YELLOW = "\033[93m" if _HAS_COLOR else ""
RED = "\033[91m" if _HAS_COLOR else ""
CYAN = "\033[96m" if _HAS_COLOR else ""
GRAY = "\033[90m" if _HAS_COLOR else ""
RESET = "\033[0m" if _HAS_COLOR else ""


def cprint(msg: str, color: str = "") -> None:
    print(f"{color}{msg}{RESET}")


def success(msg: str) -> None:
    cprint(f"[SUCCESS] {msg}", GREEN)


def info(msg: str) -> None:
    cprint(msg, CYAN)


def warn(msg: str) -> None:
    cprint(f"[WARNING] {msg}", YELLOW)


def error(msg: str) -> None:
    cprint(f"[ERROR] {msg}", RED)


def separator(title: str = "") -> None:
    line = "=" * 60
    if title:
        cprint(line, CYAN)
        cprint(f"  {title}", CYAN)
        cprint(line, CYAN)
    else:
        cprint(line, CYAN)


def get_script_dir() -> Path:
    return Path(__file__).resolve().parent


def get_python_exe() -> str:
    """返回可用的 Python 解释器路径（>= 3.10），优先 venv，否则搜索系统。"""

    # 优先 venv，但检查版本是否满足要求
    venv = get_script_dir() / "venv" / "Scripts" / "python.exe"
    if venv.exists():
        try:
            r = subprocess.run(
                [str(venv), "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"],
                capture_output=True, timeout=15
            )
            if r.returncode == 0:
                return str(venv)
            warn("虚拟环境 Python 版本过低（需要 3.10+），继续搜索系统 Python")
        except Exception as e:
            warn(f"虚拟环境 Python 不可用: {e}，继续搜索系统 Python")

    # 当前解释器——验证版本，且不能是 WindowsApps 占位
    candidates: list[str] = []
    this_py = sys.executable
    if this_py and os.path.exists(this_py) and "windowsapps" not in this_py.lower():
        candidates.append(this_py)

    # 从 PATH 搜索（跳过 WindowsApps）
    try:
        r = subprocess.run(["where", "python"], capture_output=True, text=True, timeout=10, errors='replace')
        if r.returncode == 0:
            for p in r.stdout.strip().splitlines():
                p = p.strip()
                if p and "windowsapps" not in p.lower() and p not in candidates:
                    candidates.append(p)
    except Exception:
        pass

    # 逐个验证版本
    for p in candidates:
        try:
            r = subprocess.run(
                [p, "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"],
                capture_output=True, timeout=15
            )
            if r.returncode == 0:
                return p
        except Exception:
            continue

    error("未找到 Python 3.10+，请先安装 Python 3.10 或更高版本")
    error("下载地址: https://www.python.org/downloads/")
    sys.exit(EXIT_FAILURE)


# ============================================================
# JSON 读写
# ============================================================

def read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _is_toml_config(config_type: str) -> bool:
    """判断是否为 TOML 格式的配置文件（如 Codex CLI）。"""
    return config_type == "Codex"


def _mcp_node_key(config_type: str) -> str:
    """OpenCode 使用 'mcp' 键，其他 Agent 使用 'mcpServers' 键，Codex 使用 'mcp_servers'"""
    if config_type == "OpenCode":
        return "mcp"
    if _is_toml_config(config_type):
        return "mcp_servers"
    return "mcpServers"


def _read_config(config_path: str, config_type: str) -> dict:
    if _is_toml_config(config_type):
        with open(config_path, "r", encoding="utf-8") as f:
            return _toml_parse(f.read())
    return read_json(config_path)


def _write_config(config_path: str, data: dict, config_type: str) -> None:
    if _is_toml_config(config_type):
        node_key = _mcp_node_key(config_type)
        mcp_servers = data.get(node_key, {})
        other_sections = {k: v for k, v in data.items() if k != node_key}
        # 将其他 section 写回时保持兼容（仅保留 mcp_servers 部分的修改）
        text = _toml_dumps_section(node_key, mcp_servers)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(text)
            f.write("\n")
    else:
        write_json(config_path, data)


def is_mcp_configured(config_path: str, server_name: str, config_type: str) -> bool:
    if not os.path.exists(config_path):
        return False
    try:
        data = _read_config(config_path, config_type)
        node = data.get(_mcp_node_key(config_type), {})
        return server_name in node
    except Exception:
        return False


def is_mcp_configured_any(config_path: str, config_type: str) -> bool:
    return (
        is_mcp_configured(config_path, MCP_SERVER_NAME, config_type)
        or is_mcp_configured(config_path, LEGACY_SERVER_NAME, config_type)
    )


def add_mcp_config(config_path: str, server_name: str, mcp_config: dict, config_type: str) -> None:
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    if os.path.exists(config_path):
        data = _read_config(config_path, config_type)
    else:
        data = {}
    node_key = _mcp_node_key(config_type)
    if node_key not in data:
        data[node_key] = {}
    data[node_key][server_name] = mcp_config
    _write_config(config_path, data, config_type)


def remove_mcp_config(config_path: str, server_name: str, config_type: str) -> bool:
    if not os.path.exists(config_path):
        return False
    data = _read_config(config_path, config_type)
    node_key = _mcp_node_key(config_type)
    node = data.get(node_key, {})
    if server_name not in node:
        return False
    del node[server_name]
    if not node:
        del data[node_key]
    _write_config(config_path, data, config_type)
    return True


# ============================================================
# AI Agent 检测
# ============================================================

def _env(name: str) -> str:
    return os.environ.get(name, "")


def _userprofile() -> str:
    return _env("USERPROFILE") or _env("HOME") or str(Path.home())


def _get_trae_config_path() -> str:
    """获取 Trae IDE 的 MCP 配置文件路径

    优先级: 新版 Roaming 目录 → 旧版 .trae-cn 目录 → 默认返回新版路径
    (Trae 升级后配置从 ~/.trae-cn/mcp_config.json 迁到 %APPDATA%\\Trae CN\\User\\mcp.json)
    """
    # 新版 Trae 使用 Roaming 目录
    roaming_path = os.path.join(_env("APPDATA"), "Trae CN", "User", "mcp.json")
    if os.path.exists(roaming_path):
        return roaming_path
    # 兜底：旧版路径
    legacy_path = os.path.join(_userprofile(), ".trae-cn", "mcp_config.json")
    if os.path.exists(legacy_path):
        return legacy_path
    # 默认返回新版路径（未安装时也用此路径写新配置）
    return roaming_path


def _detect_path(paths: list[str], agent_name: str = "") -> str | None:
    """检测可执行文件是否存在（优先直接路径，其次快捷方式，最后注册表）。"""

    # 根据 agent_name 确定要搜索的关键词
    keywords_map = {
        "Trae": ["trae cn", "trae-cn"],
        "TRAE SOLO CN": ["trae solo", "solo cn"],
        "Claude Desktop": ["claude"],
        "CodeArts Agent": ["codearts"],
        "Cursor": ["cursor"],
        "OpenCode": ["opencode"],
        "Windsurf": ["windsurf"],
        "Cline": ["cline"],
        "Qoder": ["qoder"],
        "Qoder CN": ["qoder cn", "qodercn", "qoder-cn", "qoder_cn"],
    }
    keywords = keywords_map.get(agent_name, [])

    # 1. 先检查直接路径（优先）
    for p in paths:
        if p and os.path.isfile(p):
            return p

    # 2. 检查 Start Menu 快捷方式（仅搜索匹配的关键词）
    if not keywords:
        return None

    start_menu_paths = [
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "Microsoft", "Windows", "Start Menu", "Programs"),
    ]

    def parse_lnk_shortcut(path: str) -> str | None:
        """解析 .lnk 文件获取目标路径（纯 Python 实现）。"""
        try:
            with open(path, "rb") as f:
                data = f.read()
                if len(data) < 0x4C:
                    return None
                if data[:4] != b'\x4c\x00\x00\x00':
                    return None
                match = re.search(rb"([A-Za-z]:\\[^\x00]+\.exe)", data)
                if match:
                    return match.group(0).decode("utf-8", errors="ignore")
        except Exception:
            pass
        return None

    def find_exe_in_shortcut(folder: str, kwlist: list[str]) -> str | None:
        """在文件夹中递归搜索包含关键词的快捷方式。"""
        if not os.path.isdir(folder):
            return None
        for root, _, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(".lnk"):
                    full_path = os.path.join(root, f)
                    matched = any(kw.lower() in f.lower() for kw in kwlist)
                    if matched:
                        target = parse_lnk_shortcut(full_path)
                        if target and os.path.isfile(target):
                            return target
        return None

    # 搜索关键词对应的快捷方式
    for folder in start_menu_paths:
        result = find_exe_in_shortcut(folder, keywords)
        if result:
            return result

    # 3. 检查注册表 Uninstall 项
    registry_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    def find_exe_in_registry(hkey: int, subkey: str, kwlist: list[str]) -> str | None:
        try:
            with winreg.OpenKey(hkey, subkey, 0, winreg.KEY_READ) as key:
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(key, i)
                        i += 1
                        for kw in kwlist:
                            if kw.lower() in name.lower():
                                with winreg.OpenKey(key, name) as sub:
                                    try:
                                        exe_path, _ = winreg.QueryValueEx(sub, "DisplayIcon")
                                        if exe_path and os.path.isfile(exe_path):
                                            return exe_path
                                    except Exception:
                                        pass
                    except OSError:
                        break
        except Exception:
            pass
        return None

    for hkey, subkey in registry_keys:
        result = find_exe_in_registry(hkey, subkey, keywords)
        if result:
            return result

    return None


AGENT_DEFINITIONS = {
    "Claude Desktop": {
        "config_type": "Standard",
        "doc_url": "https://support.claude.com/en/articles/10949351",
        "config_path": lambda: os.path.join(_env("APPDATA"), "Claude", "claude_desktop_config.json"),
        "detect_paths": lambda: [
            os.path.join(_env("LOCALAPPDATA"), "Programs", "Claude", "Claude.exe"),
            os.path.join(_env("ProgramFiles"), "Claude", "Claude.exe"),
        ],
    },
    "Trae": {
        "config_type": "Standard",
        "doc_url": "https://docs.trae.ai/ide/add-mcp-servers",
        "config_path": _get_trae_config_path,
        "detect_paths": lambda: [],  # 现在通过快捷方式和注册表检测
    },
    "TRAE SOLO CN": {
        "config_type": "Standard",
        "doc_url": "https://docs.trae.com/",
        "config_path": lambda: os.path.join(_env("APPDATA"), "TRAE SOLO CN", "User", "mcp.json"),
        "detect_paths": lambda: [],  # 通过快捷方式检测
    },
    "CodeArts Agent": {
        "config_type": "Standard",
        "modes": ["project"],
        "doc_url": "https://support.huaweicloud.com/usermanual-codeartssnap/codeartsdoer_ug_0010.html",
        "config_path": lambda: (
            p if os.path.exists(p := os.path.join(str(get_script_dir()), ".codeartsdoer", "mcp", "mcp_settings.json"))
            else os.path.join(_userprofile(), ".codeartsdoer", "mcp", "mcp_settings.json")
        ),
        "detect_paths": lambda: [
            os.path.join(_env("LOCALAPPDATA"), "Programs", "CodeArts", "CodeArts.exe"),
            os.path.join(_env("ProgramFiles"), "CodeArts", "CodeArts.exe"),
            os.path.join(_env("APPDATA"), "codearts-agent"),
        ],
    },
    "Cursor": {
        "config_type": "Standard",
        "doc_url": "https://cursor.com/help/customization/mcp",
        "config_path": lambda: os.path.join(_userprofile(), ".cursor", "mcp.json"),
        "detect_paths": lambda: [
            os.path.join(_env("LOCALAPPDATA"), "Programs", "Cursor", "Cursor.exe"),
            os.path.join(_env("ProgramFiles"), "Cursor", "Cursor.exe"),
            os.path.join(_env("APPDATA"), "Cursor"),
        ],
    },
    "OpenCode": {
        "config_type": "OpenCode",
        "modes": ["global", "project"],
        "doc_url": "https://mintlify.com/opencode-ai/opencode/core-concepts/configuration",
        "config_path": lambda: (
            p if os.path.exists(p := os.path.join(_userprofile(), ".config", "opencode", "opencode.jsonc"))
            else p if os.path.exists(p := os.path.join(_userprofile(), ".config", "opencode", "opencode.json"))
            else os.path.join(_userprofile(), ".opencode.json")
        ),
        "project_config_relpath": ".opencode.json",
        "detect_paths": lambda: [],
        "detect_command": lambda: shutil.which("opencode") is not None,
    },
    "Codex CLI": {
        # OpenAI Codex CLI — 原生 Rust 终端编码代理
        # 安装方式: npm install -g @openai/codex / brew install --cask codex / 直接下载二进制
        # 配置格式: TOML，~/.codex/config.toml，[mcp_servers] 节
        # 项目级: <project>/.codex/config.toml
        # 文档: https://developers.openai.com/codex
        "config_type": "Codex",
        "modes": ["global", "project"],
        "doc_url": "https://developers.openai.com/codex",
        "config_path": lambda: os.path.join(_userprofile(), ".codex", "config.toml"),
        "project_config_relpath": os.path.join(".codex", "config.toml"),
        "detect_paths": lambda: [
            # npm 全局安装的 codex CLI（优先 .cmd 以便 Windows 执行）
            os.path.join(_env("APPDATA"), "npm", "codex.cmd"),
            os.path.join(_env("LOCALAPPDATA"), "npm", "codex.cmd"),
            os.path.join(_env("ProgramFiles"), "codex", "codex.exe"),
            os.path.join(_userprofile(), ".codex"),
        ],
        "detect_command": lambda: shutil.which("codex") is not None,
        "detect_npm": lambda: (
            os.path.exists(os.path.join(_env("APPDATA"), "npm", "node_modules", "@openai", "codex"))
            or os.path.exists(os.path.join(_env("LOCALAPPDATA"), "npm", "node_modules", "@openai", "codex"))
        ),
    },
    "Windsurf": {
        "config_type": "Standard",
        "doc_url": "https://docs.open.cx/mcp/clients/windsurf",
        "config_path": lambda: os.path.join(_userprofile(), ".codeium", "windsurf", "mcp_config.json"),
        "detect_paths": lambda: [
            os.path.join(_env("LOCALAPPDATA"), "Programs", "Windsurf", "Windsurf.exe"),
            os.path.join(_env("ProgramFiles"), "Windsurf", "Windsurf.exe"),
            os.path.join(_env("APPDATA"), "Windsurf"),
        ],
    },
    "Cline": {
        "config_type": "Standard",
        "doc_url": "https://docs.cline.bot/getting-started/config",
        "config_path": lambda: (
            p if os.path.exists(p := os.path.join(_userprofile(), ".cline", "data", "settings", "cline_mcp_settings.json"))
            else os.path.join(_env("APPDATA"), "Code", "User", "globalStorage",
                              "saoudrizwan.claude-dev", "settings", "cline_mcp_settings.json")
        ),
        "detect_paths": lambda: [],
        "detect_vscode_ext": lambda: "saoudrizwan.claude-dev",
    },
    "Roo Code": {
        "config_type": "Standard",
        "doc_url": "",
        "config_path": lambda: os.path.join(_userprofile(), ".roo", "mcp.json"),
        "detect_paths": lambda: [],
        "detect_vscode_ext": lambda: "rooveterinaryinc.roo-cline",
    },
    "通义灵码": {
        "config_type": "Standard",
        "doc_url": "",
        "config_path": lambda: os.path.join(_userprofile(), ".tongyi", "mcp.json"),
        "detect_paths": lambda: [],
        "detect_vscode_ext": lambda: "tongyi",
        "experimental": True,
    },
    "豆包": {
        "config_type": "Standard",
        "doc_url": "",
        "config_path": lambda: os.path.join(_userprofile(), ".doubao", "mcp.json"),
        "detect_paths": lambda: [
            os.path.join(_env("LOCALAPPDATA"), "Programs", "Doubao", "Doubao.exe"),
        ],
        "experimental": True,
    },
    "Kimi": {
        "config_type": "Standard",
        "doc_url": "https://moonshotai.github.io/kimi-cli/zh/customization/mcp.html",
        "config_path": lambda: os.path.join(_userprofile(), ".kimi", "mcp.json"),
        "detect_paths": lambda: [
            os.path.join(_env("LOCALAPPDATA"), "Programs", "Kimi", "Kimi.exe"),
        ],
        "experimental": True,
    },
    "智谱清言": {
        "config_type": "Standard",
        "doc_url": "",
        "config_path": lambda: os.path.join(_userprofile(), ".chatglm", "mcp.json"),
        "detect_paths": lambda: [
            os.path.join(_env("LOCALAPPDATA"), "Programs", "ChatGLM", "ChatGLM.exe"),
        ],
        "experimental": True,
    },
    "Qoder": {
        # 阿里云通义团队出品的 Agentic Coding Platform（国际版）
        # 独立 IDE，支持 STDIO/SSE/Streamable HTTP 三种 MCP 传输
        # 配置文件: %APPDATA%\Qoder\mcp-settings.json（mcpServers 键）
        # 注: 国际版路径来自 docs.qoder.com 文档调研，本机未实测（测试机装的是 Qoder CN）。
        # 文档: https://docs.qoder.com/user-guide/chat/model-context-protocol
        "config_type": "Standard",
        "doc_url": "https://docs.qoder.com/user-guide/chat/model-context-protocol",
        "config_path": lambda: os.path.join(_env("APPDATA"), "Qoder", "mcp-settings.json"),
        "detect_paths": lambda: [
            os.path.join(_env("LOCALAPPDATA"), "Programs", "Qoder", "Qoder.exe"),
        ],
        "modes": ["global"],
    },
    "Qoder CN": {
        # Qoder 国内版（Qoder CN）——通过阿里云通义灵码（Lingma）集成
        # 实际安装路径: C:\Users\<user>\AppData\Local\Programs\QoderCN\QoderCN.exe
        # 实际 MCP 配置: %APPDATA%\QoderCN\SharedClientCache\extension\local\mcp.json
        #   （外层含 mcpServers 键 + userConfigMD5 字段；mcpServers.daofy 内部还有
        #    identifier/disabled/source/version/createAt 等元数据，重写会被简化版覆盖，
        #    Qoder CN 重启时会自动重建这些元数据）
        # 简化版缓存: %APPDATA%\QoderCN\SharedClientCache\mcp.json
        # 文档: https://help.aliyun.com/zh/lingma/qoder-cn/user-guide/guide-for-using-mcp
        "config_type": "Standard",
        "doc_url": "https://help.aliyun.com/zh/lingma/qoder-cn/user-guide/guide-for-using-mcp",
        "config_path": lambda: os.path.join(
            _env("APPDATA"), "QoderCN", "SharedClientCache", "extension", "local", "mcp.json",
        ),
        "detect_paths": lambda: [
            os.path.join(_env("LOCALAPPDATA"), "Programs", "QoderCN", "QoderCN.exe"),
        ],
        "experimental": True,  # extension\local\mcp.json 含元数据，重写会清空 identifier/source
    },
}


def _get_project_relative_config_path(agent_name: str, agent_defn: dict | None = None) -> str:
    """获取项目级 Agent 在项目目录下的相对配置文件路径"""
    # 优先从 agent 定义中的 project_config_relpath 读取
    if agent_defn and agent_defn.get("project_config_relpath"):
        return agent_defn["project_config_relpath"]
    # 静态映射兜底
    mapping: dict[str, str] = {
        "CodeArts Agent": os.path.join(".codeartsdoer", "mcp", "mcp_settings.json"),
        "OpenCode": ".opencode.json",
    }
    return mapping.get(agent_name, "")


def _check_vscode_ext(pattern: str) -> bool:
    ext_dir = os.path.join(_userprofile(), ".vscode", "extensions")
    if not os.path.isdir(ext_dir):
        return False
    for d in os.listdir(ext_dir):
        if pattern.lower() in d.lower():
            return True
    return False


def detect_agents() -> list[dict]:
    """检测所有已注册 AI Agent 的安装状态和 MCP 配置情况。

    Returns:
        每个 Agent 的检测结果列表，包含：name, installed, path,
        config_path, config_type, modes, doc_url, experimental, was_configured。
    """
    results = []
    for name, defn in AGENT_DEFINITIONS.items():
        installed = False
        install_path = None

        # 1. 首先检查可执行文件是否存在（必须要有）
        paths = defn.get("detect_paths", lambda: [])()
        install_path = _detect_path(paths, name)
        if install_path:
            installed = True

        # 2. 检查命令行（仅适用于 CLI 工具如 OpenCode / Codex）
        if not installed and defn.get("detect_command", lambda: False)():
            installed = True
            which_path = shutil.which(name.lower().split()[0])
            install_path = which_path or "CLI"

        # 2.5 检查 npm 全局安装（Codex CLI 等）
        if not installed and defn.get("detect_npm", lambda: False)():
            installed = True
            install_path = shutil.which(name.lower().split()[0]) or "npm global"

        # 3. 检查 VS Code 扩展
        # 注意: detect_vscode_ext 是 lambda (如 "lambda: 'saoudrizwan.claude-dev'"),
        #      必须调用 () 拿到字符串,否则 .lower() 会在函数对象上炸 (Issue: ...)
        ext_pattern_fn = defn.get("detect_vscode_ext", None)
        ext_pattern = ext_pattern_fn() if callable(ext_pattern_fn) else ext_pattern_fn
        if not installed and ext_pattern and _check_vscode_ext(ext_pattern):
            installed = True

        # 4. 特殊处理 Trae: 检查配置目录 (作为快捷方式/注册表未命中的兜底)
        if not installed and name == "Trae":
            traecfg_dir = os.path.join(_userprofile(), ".trae-cn")
            if os.path.isdir(traecfg_dir):
                installed = True
                install_path = "Trae IDE (detected via config dir)"

        # 4. 配置文件存在时，检查是否有 MCP 配置（但仅作为"已配置"标记，
        #    不作为"已安装"的唯一依据——必须有可执行文件才算已安装）
        config_path = defn["config_path"]()
        was_configured = False
        if os.path.exists(config_path):
            try:
                if _is_toml_config(defn["config_type"]):
                    data = _read_config(config_path, defn["config_type"])
                else:
                    data = read_json(config_path)
                node_key = _mcp_node_key(defn["config_type"])
                node = data.get(node_key, {})
                was_configured = MCP_SERVER_NAME in node or LEGACY_SERVER_NAME in node
            except Exception:
                pass

        experimental = defn.get("experimental", False)
        results.append({
            "name": name,
            "installed": installed,
            "path": install_path,
            "config_path": config_path,
            "config_type": defn["config_type"],
            "modes": defn.get("modes", ["global"]),
            "project_config_relpath": defn.get("project_config_relpath", ""),
            "doc_url": defn["doc_url"],
            "experimental": experimental,
            "was_configured": was_configured,  # 曾配置过 MCP（即使应用已卸载）
        })
    return results


# ============================================================
# MCP 配置生成
# ============================================================

def get_mcp_config(python_exe: str, config_type: str, project_dir: str = "",
                   use_pip: bool = False) -> dict:
    """生成 MCP Server 配置字典。

    OpenCode 使用专用格式（mcp 键 / type: local / command 数组 / environment），
    Codex 使用 TOML 格式（mcp_servers 节 / command + args + env），
    其他 Standard Agent 使用统一格式（mcpServers 键 / command 字符串 + args / env）。
    """
    script_dir = str(get_script_dir())
    server_script = os.path.join(script_dir, "src", "server.py")
    cwd = project_dir if project_dir and os.path.isdir(project_dir) else script_dir

    if config_type == "OpenCode":
        # OpenCode 格式：type: local, command: [数组], enabled: bool, environment: {}
        base = {
            "command": ["daofy"] if use_pip else [python_exe, server_script],
            "enabled": True,
            "environment": {
                "PYTHONUNBUFFERED": "1",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            },
        }
        # OpenCode 的 command 是数组，没有单独的 args 和 cwd
        # type 字段 Optional，local 是默认值
        return base

    if _is_toml_config(config_type):
        # Codex CLI 格式：TOML [mcp_servers] 节，command 字符串 + args 数组 + env 内联表
        base = {
            "command": "daofy" if use_pip else python_exe,
            "args": [] if use_pip else [server_script],
            "env": {
                "PYTHONUNBUFFERED": "1",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            },
            "enabled": True,
        }
        if not use_pip:
            base["cwd"] = cwd
        return base

    # Standard 格式（Claude / Cursor / Windsurf 等）
    base = {
        "command": "daofy" if use_pip else python_exe,
        "env": {
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        },
    }

    if not use_pip:
        # 源码安装模式：通过 python 解释器执行 src/server.py
        base["args"] = [server_script]
        base["cwd"] = cwd

    return base


# ============================================================
# 交互选择
# ============================================================

# ============================================================
# 安装
# ============================================================


def _get_process_pids(exe_name: str) -> list[str]:
    """通过 tasklist 获取指定可执行文件的所有进程 PID。

    特殊处理 .cmd/.bat 包装器：实际进程可能是 cmd.exe 或 node.exe，
    此时搜索包含 exe_name 命令行的进程作为兜底。
    """
    pids = _get_process_pids_by_image(exe_name)
    if not pids and (exe_name.lower().endswith(".cmd") or exe_name.lower().endswith(".bat")):
        # .cmd/.bat 包装器：实际进程可能是 cmd.exe / node.exe，按命令行搜索
        pids = _get_process_pids_by_cmdline(exe_name)
    return pids


def _get_process_pids_by_image(exe_name: str) -> list[str]:
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH", "/FI", f"IMAGENAME eq {exe_name}"],
            capture_output=True, text=True, timeout=10, errors='replace'
        )
        pids: list[str] = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.strip('"').split('","')
            if len(parts) >= 2:
                pids.append(parts[1])
        return pids
    except Exception:
        return []


def _get_process_pids_by_cmdline(exe_name: str) -> list[str]:
    """通过 WMI 按命令行包含 exe_name 搜索进程 PID。"""
    script = (
        f'Get-CimInstance Win32_Process -Filter "Name like \'%cmd.exe%\' or Name like \'%node.exe%\'" '
        f'| Where-Object {{ $_.CommandLine -like \'*{exe_name}*\' }} '
        f'| ForEach-Object {{ $_.ProcessId }}'
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=15, errors='replace'
        )
        if r.returncode != 0 or not r.stdout.strip():
            return []
        return [pid.strip() for pid in r.stdout.strip().splitlines() if pid.strip().isdigit()]
    except Exception:
        return []


def _get_process_info(pid: str) -> dict | None:
    """通过 WMI 查询进程的完整命令行。

    Returns:
        {"command_line": str} 或 None。WMI 的 WorkingDirectory 不可靠，不依赖。
    """
    script = (
        f'$p = Get-CimInstance Win32_Process -Filter "ProcessId = {pid}" 2>$null; '
        f'if ($p) {{ Write-Output $p.CommandLine }}'
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=10, errors='replace'
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        cmdline = r.stdout.strip()
        return {"command_line": cmdline} if cmdline else None
    except Exception:
        return None


def _restart_agent(agent: dict) -> bool:
    """重启指定 AI Agent 进程（先录参数，再杀，再按原参数启）。

    通过 WMI 查询运行中进程的原始命令行和启动目录，
    重启时恢复相同参数和目录。
    """
    exe_path = agent.get("path")
    if not exe_path or not os.path.isfile(exe_path):
        return False

    exe_name = os.path.basename(exe_path)
    pids = _get_process_pids(exe_name)
    if not pids:
        # 没有运行中的进程，直接启动
        try:
            subprocess.Popen([exe_path])
            return True
        except Exception:
            return False

    # 收集第一个匹配进程的参数和启动目录
    proc_info = _get_process_info(pids[0])

    # 杀进程
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/PID", pid],
                           capture_output=True, timeout=10)
        except Exception:
            pass

    time.sleep(1)

    # 按原参数启动（不依赖 cwd，WMI 的 WorkingDirectory 不可靠）
    try:
        if proc_info and proc_info.get("command_line"):
            if sys.platform == "win32":
                subprocess.Popen(proc_info["command_line"], shell=True)
            else:
                import shlex
                subprocess.Popen(shlex.split(proc_info["command_line"]))
        else:
            subprocess.Popen([exe_path])
        return True
    except Exception:
        try:
            subprocess.Popen([exe_path])
            return True
        except Exception:
            return False


def _prompt_restart(agents: list[dict], auto_restart: bool | None = None) -> None:
    """提示是否重启已操作的 Agent。auto_restart=None 时交互询问。"""
    if not agents:
        return

    restartable = [a for a in agents if a.get("path") and os.path.isfile(a["path"])]
    if not restartable:
        info("请手动重启 AI Agent 使配置生效")
        return

    names = ", ".join(a["name"] for a in restartable)
    should_restart = auto_restart

    if should_restart is None:
        try:
            choice = input(f"{CYAN}是否自动重启 {names}？[y/N]: {RESET}").strip().lower()
            should_restart = choice == "y"
        except EOFError:
            should_restart = False

    if should_restart:
        ok = 0
        for a in restartable:
            if _restart_agent(a):
                ok += 1
            else:
                warn(f"{a['name']} 重启失败，请手动重启")
        if ok:
            success(f"已自动重启 {ok} 个 AI Agent")
    else:
        info("请手动重启 AI Agent 使配置生效")


def do_install(python_exe: str, project_dir: str = "", agent_filter: str = "All",
               force: bool = False, restart: bool | None = None,
               use_pip: bool = False) -> None:
    """安装/配置 MCP Server 到指定 AI Agent。

    Args:
        python_exe: Python 解释器路径。
        project_dir: 项目目录（项目级 MCP 配置使用）。
        agent_filter: Agent 名称过滤器（"All" 或特定名称）。
        force: 是否强制重新配置已存在的 MCP Server。
        restart: 重启策略，None=交互询问，True=自动重启，False=不重启。
        use_pip: 是否使用 pip 安装模式（直接使用 daofy CLI 命令）。
    """
    separator("Daofy for Delphi 安装脚本")
    info(f"版本: {VERSION}")

    if not use_pip:
        server_script = os.path.join(str(get_script_dir()), "src", "server.py")
        if not os.path.exists(server_script):
            error(f"MCP Server 脚本不存在: {server_script}")
            sys.exit(EXIT_FAILURE)

    agents = detect_agents()

    # 预先设置 target，确保在第二个 agent_filter 检查块中始终有定义
    target = agent_filter

    # 按过滤器筛选
    if agent_filter != "All":
        filter_map = {
            "Claude": "Claude Desktop", "Trae": "Trae", "TRAE SOLO": "TRAE SOLO CN", "CodeArts": "CodeArts Agent",
            "Cursor": "Cursor", "OpenCode": "OpenCode", "Windsurf": "Windsurf",
            "Cline": "Cline", "Roo": "Roo Code", "Tongyi": "通义灵码",
            "Doubao": "豆包", "Kimi": "Kimi", "ChatGLM": "智谱清言",
            "Qoder": "Qoder", "QoderCN": "Qoder CN", "Qoder CN": "Qoder CN",
            "Codex": "Codex CLI",
        }
        target = filter_map.get(agent_filter, agent_filter)
        agents = [a for a in agents if a["name"] == target]

    installed_agents = [a for a in agents if a["installed"]]
    not_installed_agents = [a for a in agents if not a["installed"]]

    if not installed_agents:
        warn("未检测到任何已安装的 AI Agent")
        error("请先安装 Claude Desktop、Cursor、CodeArts Agent、Codex CLI 等任意一个 AI Agent")
        sys.exit(EXIT_FAILURE)

    # ================================================================
    # 分两组展示：全局配置 / 项目级配置
    # 支持两种模式的 Agent 会同时出现在两个组中（以不同编号区分）
    # ================================================================
    display_items: list[tuple[dict, str]] = []  # (agent, implied_mode)
    for a in installed_agents:
        if "global" in a["modes"]:
            display_items.append((a, "global"))
    project_start = len(display_items) + 1
    for a in installed_agents:
        if "project" in a["modes"]:
            display_items.append((a, "project"))

    info("已安装的 AI Agent（输入编号选择，a=全选，q=退出）:")
    info("")
    info("--- 全局配置（选择后将配置到默认路径）---")
    for i, (a, _) in enumerate(display_items, 1):
        if i == project_start:
            info("")
            info("--- 项目级配置（选择后需指定项目目录）---")
        is_project_item = i >= project_start
        exp = " [Experimental]" if a["experimental"] else ""
        if is_project_item:
            # 项目级：安装时不知道路径，不显示状态和路径
            cprint(f"  [{i:2d}] {a['name']}{exp}", YELLOW)
        else:
            was_configured = a.get("was_configured", False)
            if a["installed"]:
                status = "已安装 (MCP 已配置)" if was_configured else "已安装"
            elif was_configured:
                status = "配置文件存在（应用未安装）"
            else:
                status = "未安装"
            cprint(f"  [{i:2d}] {a['name']}{exp} ({status})", GREEN)
            if a["path"] and a["path"] != "Unknown":
                cprint(f"        路径: {a['path']}", GRAY)
            if was_configured:
                cfg_label = "MCP 已配置" if a["installed"] else "曾配置过 MCP"
                cprint(f"        配置: {a['config_path']} ({cfg_label})", GRAY)
            else:
                cprint(f"        配置: {a['config_path']}", GRAY)

    if not_installed_agents:
        names = ", ".join(a["name"] for a in not_installed_agents)
        info(f"未安装的 AI Agent: {names}")

    # 交互选择
    if agent_filter != "All":
        # target 和 agents 已在之前的 agent_filter 检查中筛选完毕
        selected = [a for a in installed_agents if a["name"] == target]
        # 自动推断 implied_mode
        for a in selected:
            a["_implied_mode"] = "project" if "project" in a["modes"] and "global" not in a["modes"] else "global"
    else:
        if len(display_items) <= 1:
            selected = [a for a, _ in display_items]
        else:
            info("")
            info("请选择要配置的 AI Agent（多选用逗号分隔，如 1,3,5）")
            info("输入 a 或 all 全选，输入 q 退出")
            try:
                choice = input(f"{CYAN}选择 [1-{len(display_items)}/a/q]: {RESET}").strip()
            except EOFError:
                choice = "q"
            if not choice or choice.lower() == "q":
                info("已取消")
                sys.exit(EXIT_CANCELLED)
            if choice.lower() in ("a", "all"):
                # 全选：每个 display 项独立复制，保留各自的 implied_mode
                selected = []
                for agent, implied_mode in display_items:
                    entry = dict(agent)
                    entry["_implied_mode"] = implied_mode
                    selected.append(entry)
            else:
                selected = []
                for part in choice.replace(" ", ",").split(","):
                    part = part.strip()
                    if part.isdigit():
                        idx = int(part)
                        if 1 <= idx <= len(display_items):
                            agent, implied_mode = display_items[idx - 1]
                            entry = dict(agent)
                            entry["_implied_mode"] = implied_mode
                            selected.append(entry)
                        else:
                            warn(f"忽略无效选择: {idx}")
                if not selected:
                    warn("未选择任何有效的 Agent")
                    sys.exit(EXIT_FAILURE)

    # agent_filter 模式或未设置 _implied_mode 的自动推断
    for a in selected:
        if "_implied_mode" not in a:
            a["_implied_mode"] = "project" if "project" in a["modes"] and "global" not in a["modes"] else "global"

    # 项目级 Agent 始终需要用户输入项目目录
    need_path = [a for a in selected if a["_implied_mode"] == "project" and not project_dir]
    if need_path:
        # 非交互模式（--agent 指定或非 TTY）下直接报错退出
        if agent_filter != "All" or not sys.stdin.isatty():
            error("项目级 Agent 需要 --project-dir 参数指定项目目录")
            for a in need_path:
                rel = _get_project_relative_config_path(a["name"], a)
                error(f"  {a['name']} 的配置相对路径: {rel}")
            sys.exit(EXIT_FAILURE)
        default_dir = str(get_script_dir())
        info("")
        info("以下 Agent 需要指定项目目录：")
        for a in need_path:
            rel = _get_project_relative_config_path(a["name"], a)
            cprint(f"  - {a['name']} ({rel})", YELLOW)
        try:
            user_input = input(f"{CYAN}项目目录 [默认: {default_dir}]: {RESET}").strip()
        except EOFError:
            user_input = ""
        project_dir = user_input if user_input else default_dir
    # 根据 project_dir 更新项目级 Agent 的配置文件路径
    if project_dir:
        for a in selected:
            if a["_implied_mode"] == "project":
                rel_path = _get_project_relative_config_path(a["name"], a)
                if rel_path:
                    a["config_path"] = os.path.join(project_dir, rel_path)

    info("")
    info("将配置以下 Agent:")
    for a in selected:
        cprint(f"  - {a['name']}", GREEN)

    if use_pip:
        # pip 安装模式：直接安装 daofy-for-delphi 包
        separator("安装 Daofy for Delphi")
        mirror = "https://pypi.tuna.tsinghua.edu.cn/simple"
        try:
            info("正在通过 pip 安装 daofy-for-delphi ...")
            result = subprocess.run(
                [python_exe, "-m", "pip", "install", "daofy-for-delphi", "-i", mirror],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                success("daofy-for-delphi 安装完成")
            else:
                error(f"pip install 失败 (return code {result.returncode})")
                for line in result.stderr.strip().splitlines():
                    if line.strip():
                        error(f"  {line.strip()}")
                error("请手动运行: pip install daofy-for-delphi")
        except subprocess.TimeoutExpired:
            error("pip install 超时（>120s）")
        except Exception as e:
            error(f"安装 daofy-for-delphi 时出错: {e}")
    else:
        # 源码安装模式：安装 requirements.txt 依赖
        separator("安装 Python 依赖")
        req_file = os.path.join(str(get_script_dir()), "requirements.txt")
        if os.path.exists(req_file):
            info("正在通过 pip 安装依赖 ...")
            try:
                mirror = "https://pypi.tuna.tsinghua.edu.cn/simple"
                result = subprocess.run(
                    [python_exe, "-m", "pip", "install", "-r", req_file, "-i", mirror],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0:
                    success("Python 依赖安装完成")
                    for line in result.stdout.strip().splitlines():
                        if line.strip():
                            info(f"  {line.strip()}")
                else:
                    error(f"pip install 失败 (return code {result.returncode})")
                    for line in result.stderr.strip().splitlines():
                        if line.strip():
                            error(f"  {line.strip()}")
                    error("请手动运行: pip install -r requirements.txt")
            except subprocess.TimeoutExpired:
                error("pip install 超时（>120s）")
            except Exception as e:
                error(f"安装依赖时出错: {e}")
        else:
            warn(f"未找到 requirements.txt: {req_file}")

    separator("配置 MCP Server")
    success_count = 0

    for a in selected:
        info(f"正在配置 {a['name']}...")
        info(f"配置文件: {a['config_path']}")

        configured = is_mcp_configured_any(a["config_path"], a["config_type"])
        if configured and not force:
            info(f"{a['name']} 已配置 MCP Server，跳过（使用 --force 强制重新配置）")
            success_count += 1
            continue

        if force and configured:
            for sn in (MCP_SERVER_NAME, LEGACY_SERVER_NAME):
                remove_mcp_config(a["config_path"], sn, a["config_type"])

        mcp_cfg = get_mcp_config(python_exe, a["config_type"], project_dir, use_pip=use_pip)
        try:
            add_mcp_config(a["config_path"], MCP_SERVER_NAME, mcp_cfg, a["config_type"])
            success(f"已配置 MCP Server 到: {a['config_path']}")
            success_count += 1
        except Exception as e:
            error(f"配置失败: {e}")

    separator("安装结果")
    info(f"成功配置: {success_count} 个 AI Agent")
    if success_count > 0:
        success("MCP Server 安装完成！")
        _prompt_restart(selected, restart)
    else:
        error("所有选中的 Agent 都未能成功配置")
        sys.exit(EXIT_FAILURE)


# ============================================================
# 卸载
# ============================================================

def do_uninstall(agent_filter: str = "All", project_dir: str = "",
                 restart: bool | None = None) -> None:
    """从指定 AI Agent 卸载 MCP Server 配置。

    Args:
        agent_filter: Agent 名称过滤器（"All" 或特定名称）。
        project_dir: 项目目录（项目级 MCP 配置使用）。
        restart: 重启策略，None=交互询问，True=自动重启，False=不重启。
    """
    separator("Daofy for Delphi 卸载脚本")

    agents = detect_agents()

    # 如果 CLI 指定了 project_dir，预先设置配置文件路径（但不改变 installed 状态）
    # 这样项目级 Agent 会在选择时显示正确的配置路径，但需要用户主动选择才安装
    if project_dir:
        for a in agents:
            if "project" in a["modes"]:
                rel_path = _get_project_relative_config_path(a["name"], a)
                if rel_path:
                    a["config_path"] = os.path.join(project_dir, rel_path)

    # 只显示尚有 MCP 配置可卸载的 Agent（应用已装但无配置的无需列出）
    display_items: list[tuple[dict, str]] = []
    for a in agents:
        if "global" in a["modes"] and a.get("was_configured"):
            display_items.append((a, "global"))
    project_start = len(display_items) + 1
    for a in agents:
        if "project" in a["modes"] and a.get("was_configured"):
            display_items.append((a, "project"))

    if not display_items:
        info("没有需要卸载的 AI Agent")
        sys.exit(EXIT_SUCCESS)

    # ================================================================
    # 分两组展示：全局配置 / 项目级配置（同安装流程）
    # ================================================================

    info("（输入编号选择，a=全选，q=退出）")
    info("")
    info("--- 全局配置 ---")
    for i, (a, _) in enumerate(display_items, 1):
        if i == project_start:
            info("")
            info("--- 项目级配置（选择后需指定项目目录）---")
        is_project_item = i >= project_start
        exp = " [Experimental]" if a["experimental"] else ""
        if is_project_item and not project_dir:
            cprint(f"  [{i:2d}] {a['name']}{exp}", YELLOW)
        else:
            was_configured = a.get("was_configured", False)
            if a["installed"]:
                status = "已安装 (MCP 已配置)" if was_configured else "已安装"
                color = GREEN
            elif was_configured:
                status = "配置文件存在（应用未安装）"
                color = YELLOW
            else:
                status = "未安装"
                color = YELLOW
            cprint(f"  [{i:2d}] {a['name']}{exp} ({status})", color)
            if was_configured:
                cfg_label = "MCP 已配置" if a["installed"] else "曾配置过 MCP"
                cprint(f"      配置: {a['config_path']} ({cfg_label})", GRAY)
            else:
                cprint(f"      配置: {a['config_path']}", GRAY)

    # 交互选择
    if agent_filter != "All":
        filter_map = {
            "Claude": "Claude Desktop", "Trae": "Trae", "TRAE SOLO": "TRAE SOLO CN", "CodeArts": "CodeArts Agent",
            "Cursor": "Cursor", "OpenCode": "OpenCode", "Windsurf": "Windsurf",
            "Cline": "Cline", "Roo": "Roo Code", "Tongyi": "通义灵码",
            "Doubao": "豆包", "Kimi": "Kimi", "ChatGLM": "智谱清言",
            "Qoder": "Qoder", "QoderCN": "Qoder CN", "Qoder CN": "Qoder CN",
            "Codex": "Codex CLI",
        }
        target = filter_map.get(agent_filter, agent_filter)
        selected = [a for a in agents if a["name"] == target and a.get("was_configured")]
        for a in selected:
            a["_implied_mode"] = "project" if "project" in a["modes"] and "global" not in a["modes"] else "global"
    else:
        if len(display_items) <= 1:
            selected_with_modes = display_items
        else:
            info("")
            info("请选择要卸载的 AI Agent（多选用逗号分隔，如 1,3,5）")
            info("输入 a 或 all 全选，输入 q 退出")
            try:
                choice = input(f"{CYAN}选择 [1-{len(display_items)}/a/q]: {RESET}").strip()
            except EOFError:
                choice = "q"
            if not choice or choice.lower() == "q":
                info("已取消")
                sys.exit(EXIT_CANCELLED)
            if choice.lower() in ("a", "all"):
                selected_with_modes = display_items
            else:
                selected_with_modes = []
                for part in choice.replace(" ", ",").split(","):
                    part = part.strip()
                    if part.isdigit():
                        idx = int(part)
                        if 1 <= idx <= len(display_items):
                            selected_with_modes.append(display_items[idx - 1])
                        else:
                            warn(f"忽略无效选择: {idx}")
                if not selected_with_modes:
                    warn("未选择任何有效的 Agent")
                    sys.exit(EXIT_FAILURE)
        # 转为独立 dict 列表，保留 implied_mode
        selected = []
        for agent, implied_mode in selected_with_modes:
            entry = dict(agent)
            entry["_implied_mode"] = implied_mode
            selected.append(entry)

    if not selected:
        sys.exit(EXIT_SUCCESS)

    # 为项目级 Agent 补充路径检测（选中后才提示）
    for a in selected:
        if a["_implied_mode"] == "project" and not project_dir:
            # 非交互模式下直接报错退出
            if agent_filter != "All" or not sys.stdin.isatty():
                error("项目级 Agent 需要 --project-dir 参数指定项目目录")
                rel = _get_project_relative_config_path(a["name"], a)
                error(f"  {a['name']} 的配置相对路径: {rel}")
                sys.exit(EXIT_FAILURE)
            info("")
            rel = _get_project_relative_config_path(a["name"], a)
            info(f"{a['name']} 使用项目级 MCP 配置（{rel}），请输入项目目录")
            default_dir = str(get_script_dir())
            try:
                user_input = input(f"{CYAN}项目目录 [默认: {default_dir}]: {RESET}").strip()
            except EOFError:
                user_input = ""
            project_dir = user_input or default_dir
            rel_path = _get_project_relative_config_path(a["name"], a)
            if rel_path:
                a["config_path"] = os.path.join(project_dir, rel_path)

    # 过滤出实际已配置的 Agent
    to_uninstall = []
    for a in selected:
        configured = is_mcp_configured_any(a["config_path"], a["config_type"])
        if not configured:
            if a["_implied_mode"] == "project" and "global" not in a["modes"]:
                warn(f"{a['name']} 在 {a['config_path']} 未找到 MCP 配置，跳过")
            else:
                info(f"{a['name']} 未配置此 MCP Server，跳过")
            continue
        to_uninstall.append(a)

    if not to_uninstall:
        info("没有需要卸载的 MCP 配置")
        sys.exit(EXIT_SUCCESS)

    info("")
    warn("将卸载以下 Agent 的 MCP Server 配置:")
    for a in to_uninstall:
        cprint(f"  - {a['name']}", YELLOW)
        cprint(f"      配置: {a['config_path']}", GRAY)
    try:
        confirm = input(f"{RED}确认卸载? [y/N]: {RESET}").strip()
    except EOFError:
        confirm = "n"
    if confirm.lower() != "y":
        info("已取消")
        sys.exit(EXIT_CANCELLED)

    separator("卸载 MCP Server")
    success_count = 0
    uninstalled_agents: list[dict] = []

    for a in to_uninstall:
        info(f"正在卸载 {a['name']}...")
        removed_any = False
        for sn in (MCP_SERVER_NAME, LEGACY_SERVER_NAME):
            if is_mcp_configured(a["config_path"], sn, a["config_type"]):
                if remove_mcp_config(a["config_path"], sn, a["config_type"]):
                    removed_any = True
        if removed_any:
            success(f"已从 {a['name']} 移除 MCP Server 配置")
            success_count += 1
            uninstalled_agents.append(a)
        else:
            info(f"{a['name']} 未配置此 MCP Server，跳过")

    separator("卸载结果")
    info(f"成功卸载: {success_count} 个 AI Agent")
    if success_count > 0:
        success("MCP Server 卸载完成！")
        _prompt_restart(uninstalled_agents, restart)


# ============================================================
# 入口
# ============================================================

# ============================================================
# 自安装：检查当前目录是否为 MCP Server 目录
# ============================================================

GITHUB_REPO = "chinawsb/daofy"
RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def _is_server_dir() -> bool:
    """检查当前目录是否包含 MCP Server 核心文件"""
    script_dir = get_script_dir()
    return (script_dir / "src" / "server.py").exists() and (script_dir / "requirements.txt").exists()


MAX_RETRY = 5   # 每个 URL 最多重试次数（已有镜像回退，无需 30 次）
RETRY_DELAY = 2  # 秒
DOWNLOAD_TIMEOUT = 30  # 单次下载超时（秒），urlretrieve 无默认超时

# ============================================================
# 多镜像源 + 测速（用于加速下载和失败回退）
# ============================================================

# GitHub 国内镜像代理
GITHUB_MIRRORS: list[str] = [
    "",  # 原始源
    "https://ghproxy.net",  # 国内 GitHub 代理
]

# Gitee 镜像仓库（国内用户首选）
GITEE_REPO = "zuoyouruanjian/daofy"
GITEE_API = f"https://gitee.com/api/v5/repos/{GITEE_REPO}/releases/latest"


def _measure_speed(url: str, timeout: int = 5) -> float | None:
    """测量 URL 响应速度（秒），不可达返回 None"""
    import time
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "daofy-installer"})
        start = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as _:
            return time.time() - start
    except Exception:
        return None


def _sort_urls_by_speed(urls: list[str]) -> list[str]:
    """测速排序：按响应时间升序（最快优先），不可达排在最后"""
    results: list[tuple[float, str]] = []
    for url in urls:
        speed = _measure_speed(url)
        results.append((speed if speed is not None else float('inf'), url))
    results.sort()
    return [url for _, url in results]


def _build_mirror_urls(url: str) -> list[str]:
    """将 GitHub URL 扩展为多镜像 URL 列表（原始源 + 国内代理）。

    ghproxy 风格：https://proxy/原始GitHub完整URL
    """
    urls: list[str] = []
    for m in GITHUB_MIRRORS:
        if not m:
            urls.append(url)
        else:
            urls.append(f"{m}/{url}")
    # 去重（保留顺序）
    seen: set[str] = set()
    result: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


def _retry_urlopen(url: str, headers: dict | None = None, timeout: int = 15, max_retry: int = MAX_RETRY) -> bytes:
    """带重试的 urllib 请求，最多重试 max_retry 次"""

    last_err = None
    for attempt in range(1, max_retry + 1):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < max_retry:
                wait = RETRY_DELAY * min(attempt, 10)
                warn(f"请求失败(第{attempt}次): {e}，{wait}秒后重试...")
                time.sleep(wait)
    raise last_err  # type: ignore[misc]


def _build_api_urls() -> list[str]:
    """构建所有镜像源的 release API URL 列表"""
    api_urls = _build_mirror_urls(RELEASE_API)
    # 追加 Gitee API（结构不同，单独添加）
    for m in GITHUB_MIRRORS:
        if m:
            api_urls.append(f"{m}/{GITEE_API}" if "://" in m else f"{m}/{GITEE_API}")
    api_urls.append(GITEE_API)
    # 去重
    seen: set[str] = set()
    result: list[str] = []
    for u in api_urls:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


def _build_download_urls(download_url: str, version: str) -> list[str]:
    """根据原始 GitHub 下载 URL 和版本，构建所有镜像源的下载 URL"""
    urls = _build_mirror_urls(download_url)
    # Gitee 下载 URL：从 tag + 文件名构建
    filename = download_url.rstrip("/").split("/")[-1]
    gitee_dl = f"https://gitee.com/{GITEE_REPO}/releases/download/{version}/{filename}"
    for m in GITHUB_MIRRORS:
        if m:
            urls.append(f"{m}/{gitee_dl}" if "://" in m else gitee_dl)
    urls.append(gitee_dl)
    # 去重
    seen: set[str] = set()
    result: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


def _parse_release_data(data: dict) -> tuple[str, str] | None:
    """从 release API 响应中解析 (download_url, version)，兼容 GitHub 和 Gitee 格式"""
    tag_name = data.get("tag_name", "")
    if not tag_name:
        return None
    # 尝试 assets 列表（GitHub 格式 + Gitee 格式）
    assets = data.get("assets") or []
    for asset in assets:
        name = asset.get("name", "")
        if name.endswith(".zip"):
            url = (asset.get("browser_download_url") or
                   asset.get("zipball_url") or "")
            if url:
                return url, tag_name
    # 无 assets 时构造 zipball URL（GitHub 格式）
    zip_url = data.get("zipball_url", "")
    if zip_url:
        return zip_url, tag_name
    return None


def _get_latest_release_url() -> tuple[str, str]:
    """获取最新 release 的 zip 下载地址和版本号（自动测速 + 多镜像回退）"""
    api_urls = _build_api_urls()

    # 测速排序：先测量各镜像响应速度，从最快开始尝试
    info("正在测速选择最佳镜像源...")
    sorted_urls = _sort_urls_by_speed(api_urls)
    fastest = sorted_urls[0] if sorted_urls else ""
    if fastest and fastest != api_urls[0]:
        info(f"最佳镜像: {fastest.split('/')[2] if '://' in fastest else '直接连接'}")

    last_err: Exception | None = None
    for api_url in sorted_urls:
        try:
            data = json.loads(
                _retry_urlopen(api_url, headers={"User-Agent": "daofy-installer"}).decode("utf-8")
            )
            result = _parse_release_data(data)
            if result:
                return result
        except Exception as e:
            last_err = e
            warn(f"从镜像获取 Release 信息失败: {api_url} — {e}")
            continue
    if last_err:
        warn(f"所有镜像获取 Release 信息均失败: {last_err}")
    return "", ""


def _download_file(url: str, dest: str, version: str = "") -> bool:
    """下载文件到指定路径，带测速 + 多镜像回退"""

    # 构造多镜像 URL 列表并测速排序
    raw_urls = _build_download_urls(url, version) if version else _build_mirror_urls(url)
    info("正在测速选择最佳下载源...")
    download_urls = _sort_urls_by_speed(raw_urls)
    if download_urls:
        fastest_host = download_urls[0].split("/")[2] if "://" in download_urls[0] else "直接连接"
        info(f"最佳下载源: {fastest_host}")

    last_err: Exception | None = None
    for dl_url in download_urls:
        info(f"正在下载: {dl_url}")
        for attempt in range(1, MAX_RETRY + 1):
            try:
                if attempt > 1:
                    info(f"重试下载(第{attempt}次): {dl_url}")
                # 使用 urlopen 替代 urlretrieve，支持 timeout 参数
                req = urllib.request.Request(dl_url, headers={"User-Agent": "daofy-installer"})
                with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
                    with open(dest, "wb") as f:
                        shutil.copyfileobj(resp, f)
                return True
            except urllib.error.HTTPError as e:
                last_err = e
                if os.path.exists(dest):
                    os.remove(dest)
                warn(f"HTTP {e.code} — {dl_url}")
                break  # HTTP 错误无需重试（404/403 重试也没用），切下一个镜像
            except Exception as e:
                last_err = e
                if os.path.exists(dest):
                    os.remove(dest)
                if attempt < MAX_RETRY:
                    wait = RETRY_DELAY * min(attempt, 5)
                    warn(f"下载失败(第{attempt}次): {e}，{wait}秒后重试...")
                    time.sleep(wait)
        warn(f"镜像源失败，尝试下一个: {dl_url}")
    error(f"所有镜像源下载失败: {last_err}")
    return False


def ensure_server_files() -> bool:
    """检查当前目录是否为 MCP Server 安装目录，如果不是则下载并解压最新 release。

    返回 True 表示文件就绪（已有或已安装），False 表示失败。
    不会覆盖当前正在执行的 bat 文件。
    """
    if _is_server_dir():
        return True

    separator("MCP Server 文件未找到")
    info("当前目录不包含 MCP Server 核心文件 (src/server.py)")
    info("将自动下载最新 Release 并解压到当前目录")
    info("")

    zip_url, version = _get_latest_release_url()
    if not zip_url:
        error("无法获取最新 Release 下载地址")
        error(f"请手动下载: https://github.com/{GITHUB_REPO}/releases")
        return False

    info(f"最新版本: {version}")

    with tempfile.TemporaryDirectory(prefix="daofy-install-") as tmp_dir:
        zip_path = os.path.join(tmp_dir, f"daofy-for-delphi-{version}.zip")
        if not _download_file(zip_url, zip_path, version=version):
            return False

        info("正在解压...")
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_dir)
        except Exception as e:
            error(f"解压失败: {e}")
            return False

        # 找到解压后的子目录（release zip 通常包含一个顶层目录）
        src_dir = tmp_dir
        entries = os.listdir(tmp_dir)
        extracted_dirs = [e for e in entries if e != os.path.basename(zip_path) and os.path.isdir(os.path.join(tmp_dir, e))]
        if len(extracted_dirs) == 1:
            src_dir = os.path.join(tmp_dir, extracted_dirs[0])
        elif len(extracted_dirs) > 1:
            # 找包含 src/server.py 的目录
            for d in extracted_dirs:
                if os.path.exists(os.path.join(tmp_dir, d, "src", "server.py")):
                    src_dir = os.path.join(tmp_dir, d)
                    break

        if not os.path.exists(os.path.join(src_dir, "src", "server.py")):
            error("解压后未找到 src/server.py")
            return False

        # 复制文件到当前目录，跳过 .bat 文件（正在运行）
        dest_dir = str(get_script_dir())
        bat_files = set()
        info(f"正在安装文件到: {dest_dir}")
        for root, dirs, files in os.walk(src_dir):
            rel_root = os.path.relpath(root, src_dir)
            for f in files:
                src_file = os.path.join(root, f)
                if rel_root == ".":
                    dest_file = os.path.join(dest_dir, f)
                else:
                    dest_file = os.path.join(dest_dir, rel_root, f)

                # 跳过正在运行的 .bat 文件，稍后覆盖
                if f.lower().endswith(".bat"):
                    bat_files.add((src_file, dest_file))
                    continue

                os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                shutil.copy2(src_file, dest_file)

        # 最后覆盖 .bat 文件（bat 已读入内存，覆盖不影响本次执行）
        for src_bat, dest_bat in bat_files:
            shutil.copy2(src_bat, dest_bat)

        success(f"MCP Server {version} 安装完成")
        return True


def main() -> None:
    """安装/卸载脚本入口函数，解析命令行参数并执行对应操作。"""
    if sys.platform != "win32":
        error("此脚本仅支持 Windows 系统")
        sys.exit(EXIT_FAILURE)

    parser = argparse.ArgumentParser(description="Daofy for Delphi 安装/卸载脚本")
    parser.add_argument("--uninstall", action="store_true", help="卸载模式")
    parser.add_argument("--agent", default="All",
                        choices=["Claude", "Trae", "CodeArts", "Cursor", "OpenCode",
                                 "Windsurf", "Cline", "Roo", "Tongyi", "Doubao",
                                 "Kimi", "ChatGLM", "Qoder", "QoderCN", "All"],
                        help="指定 AI Agent")
    parser.add_argument("--force", action="store_true", help="强制重新配置")
    parser.add_argument("--restart", action="store_true", help="操作后自动重启 AI Agent（不交互询问）")
    parser.add_argument("--no-restart", action="store_true", help="操作后不重启 AI Agent（不交互询问）")
    parser.add_argument("--python", default="", help="Python 解释器路径")
    parser.add_argument("--project-dir", default="",
                        help="项目目录路径（项目级 MCP 配置的 Agent 使用，不传则交互式输入）")
    parser.add_argument("--pip", action="store_true",
                        help="使用 pip 安装模式（从 PyPI 安装 daofy-for-delphi）")
    args = parser.parse_args()

    # 确定重启策略
    if args.restart:
        restart = True
    elif args.no_restart:
        restart = False
    else:
        restart = None  # 交互询问

    if args.uninstall:
        do_uninstall(agent_filter=args.agent, project_dir=args.project_dir, restart=restart)
    else:
        # 检查 MCP Server 文件是否存在，不存在则自动下载解压
        if not ensure_server_files():
            error("MCP Server 文件准备失败")
            sys.exit(EXIT_FAILURE)

        python_exe = args.python or get_python_exe()
        if not os.path.exists(python_exe):
            error(f"Python 不存在: {python_exe}")
            sys.exit(EXIT_FAILURE)
        do_install(python_exe, project_dir=args.project_dir,
                   agent_filter=args.agent, force=args.force, restart=restart,
                   use_pip=args.pip)


if __name__ == "__main__":
    main()
