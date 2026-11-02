"""集中式工具路径参数绝对路径校验。

在 MCP 接口边界（server.call_tool）统一校验，避免相对路径导致的 CWD 不一致问题。
仅对真正代表文件系统路径的字段做强制校验，跳过 JSONPath、项目相对（如 delphi_project.sources）等字段。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple


# 每个工具需要校验的路径字段（字段值可以是 string 或 list[str]）
# 采用白名单方式：未列出的字段不会强制要求绝对路径。
# 有意排除的项目相对字段：delphi_project.sources/form_units/source_file/main_source、
# structured_content.path（JSONPath）、code_hosting.dir/files（仓库相对/当前目录）。
TOOL_PATH_FIELDS: Dict[str, Tuple[str, ...]] = {
    # Delphi
    "delphi_file": ("file_path", "project_path", "config_path"),
    "file_tool": ("file_path", "project_path", "config_path"),
    "delphi_project": ("project_path", "file_path", "base_dir", "output_path"),
    "compile_project": ("project_path", "file_path", "base_dir", "output_path"),
    "delphi_kb": ("project_path", "file_path", "directory"),
    "manage_component": ("target_dfm", "target_pas"),
    "package": ("package_path",),
    "check_environment": ("install_dir",),
    "automate_delphi": ("app_path", "snapshots_dir", "script"),
    "delphi_rtti": ("app_path",),
    # Core
    "structured_content": ("file_path", "proto_file"),
    "generate_copyright": ("project_path", "output_dir"),
    "ocr": ("image_path", "template_path", "baseline", "current", "output_dir"),
    # Lazarus
    "lazarus_compile": ("project_path",),
    "lazarus_project": ("project_path",),
    "lazarus_file": ("file_path",),
    "lazarus_kb": ("file_path",),
}


# 有意排除的项目相对字段（不加入上面的白名单）：
#   delphi_project.sources / form_units / source_file / main_source
#   structured_content.path（JSONPath）
#   code_hosting.dir / files（当前目录或仓库相对路径）


def _is_path_like_string(s: str) -> bool:
    """判断字符串是否可能是文件系统路径（而不是 JSON/脚本等）。"""
    if not s:
        return False
    # 脚本 JSON 通常以 { 或 [ 开头
    stripped = s.lstrip()
    if stripped and stripped[0] in "{[":
        return False
    # 明显是 JSON 字符串整体
    if (stripped.startswith('"') and stripped.endswith('"')) or (
        stripped.startswith("'") and stripped.endswith("'")
    ):
        # 可能是被转义的 JSON，先尝试解析
        try:
            loaded = json.loads(stripped)
            if isinstance(loaded, (dict, list)):
                return False
        except (json.JSONDecodeError, TypeError):
            pass
    # 包含路径分隔符或常见扩展名更像路径
    lower = s.lower()
    if "\\" in s or "/" in s:
        return True
    if lower.endswith((
        ".pas",
        ".dfm",
        ".dpr",
        ".dpk",
        ".dproj",
        ".groupproj",
        ".lpr",
        ".lpi",
        ".inc",
        ".fmx",
        ".lfm",
        ".exe",
        ".dll",
        ".bpl",
        ".json",
        ".xml",
        ".proto",
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".txt",
    )):
        return True
    # Windows 盘符
    if len(s) >= 2 and s[1] == ":":
        return True
    # UNC 路径
    if s.startswith("\\\\"):
        return True
    return False


def _is_absolute_path(p: str) -> bool:
    """判断路径是否为绝对路径（支持 Windows 盘符/UNC 与 POSIX 风格）。"""
    if not isinstance(p, str):
        return True  # 非字符串交由调用方处理
    p_stripped = p.strip()
    if not p_stripped:
        return True  # 空值跳过
    # Windows 盘符
    if len(p_stripped) >= 2 and p_stripped[1] == ":" and p_stripped[0].isalpha():
        # 盘符绝对路径（C:\... 或 C:/...）
        rest = p_stripped[2:]
        if rest and rest[0] in "\\/":
            return True
        # 仅 "C:" 也视为不完整的绝对路径形式，按相对处理更安全
        return False
    # UNC 路径 \\server\share
    if p_stripped.startswith("\\\\"):
        return True
    # POSIX 绝对路径
    if p_stripped.startswith("/"):
        return True
    # URL 类等不视为本地文件路径
    if "://" in p_stripped:
        return False
    return False


def _validate_single_path(tool_name: str, field: str, value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        # 列表由调用方遍历处理
        return None
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    # automate_delphi.script 只有在看起来像文件路径时才校验
    if tool_name == "automate_delphi" and field == "script":
        if not _is_path_like_string(v):
            return None
    if _is_absolute_path(v):
        return None
    # 相对路径 -> 拒绝
    if os.name == "nt":
        example = "C:\\project\\Unit1.pas"
    else:
        example = "/home/user/project/Unit1.pas"
    return (
        f"工具 '{tool_name}' 的参数 '{field}' 必须传入绝对路径（MCP 无法获取客户端当前工作目录）。"
        f"当前值: '{v}'。请使用形如 '{example}' 的绝对路径。"
    )


def validate_tool_paths(tool_name: str, arguments: Dict[str, Any]) -> Optional[str]:
    """校验工具参数中的文件系统路径字段是否为绝对路径。

    Args:
        tool_name: MCP 工具名。
        arguments: 调用该工具时传入的参数字典。

    Returns:
        Optional[str]: 校验失败时返回可直接展示给用户的错误信息；通过时返回 None。
    """
    if not isinstance(arguments, dict):
        return None
    fields = TOOL_PATH_FIELDS.get(tool_name)
    if not fields:
        return None
    for field in fields:
        if field not in arguments:
            continue
        value = arguments.get(field)
        if value is None:
            continue
        # 列表
        if isinstance(value, (list, tuple)):
            # automate_delphi 的 script 列表是步骤数组，不是路径列表
            if tool_name == "automate_delphi" and field == "script":
                continue
            for item in value:
                if isinstance(item, str):
                    err = _validate_single_path(tool_name, field, item)
                    if err:
                        return err
            continue
        if isinstance(value, str):
            err = _validate_single_path(tool_name, field, value)
            if err:
                return err
        # 其他类型忽略
    return None
