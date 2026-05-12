"""
Delphi 版本号与名称映射工具

提供统一的版本名称查询，避免多处重复定义。
所有新旧版本映射应集中在此维护。
"""

import re
from typing import Optional

# 注册表版本键 → 产品名称（完整映射）
DELPHI_VERSION_NAMES: dict[str, str] = {
    "37.0": "Delphi 13 Florence",
    "23.0": "Delphi 12 Athens",
    "22.0": "Delphi 11 Alexandria",
    "21.0": "Delphi 10.4 Sydney",
    "20.0": "Delphi 10.3 Rio",
    "19.0": "Delphi 10.2 Tokyo",
    "18.0": "Delphi 10.1 Berlin",
    "17.0": "Delphi 10 Seattle",
    "16.0": "Delphi XE8",
    "15.0": "Delphi XE7",
    "14.0": "Delphi XE6",
    "12.0": "Delphi XE5",
    "11.0": "Delphi XE4",
    "10.0": "Delphi XE3",
    "9.0": "Delphi XE2",
    "8.0": "Delphi XE",
    "7.0": "Delphi 2010",
    "6.0": "Delphi 2009",
    "5.0": "Delphi 2007",
    "4.0": "Delphi 2006",
    "3.0": "Delphi 2005",
}

# .dproj 版本前缀(整数部分) → 产品名称
# 用于 get_compiler_for_project 匹配编译器
PROJECT_VERSION_PREFIX_MAP: dict[str, str] = {
    "37": "Delphi 13 Florence",
    "23": "Delphi 12 Athens",
    "22": "Delphi 11 Alexandria",
    "21": "Delphi 10.4 Sydney",
    "20": "Delphi 10.3 Rio",
    "19": "Delphi 10.2 Tokyo",
    "18": "Delphi 10.1 Berlin",
    "17": "Delphi 10 Seattle",
    "16": "Delphi XE8",
    "15": "Delphi XE7",
    "14": "Delphi XE6",
    "12": "Delphi XE5",
    "11": "Delphi XE4",
    "10": "Delphi XE3",
    "9": "Delphi XE2",
    "8": "Delphi XE",
}


def get_version_name(version_key: str) -> str:
    """根据版本号键获取 Delphi 产品名称"""
    return DELPHI_VERSION_NAMES.get(version_key, f"Delphi {version_key}")


def get_version_name_from_path(delphi_path: str) -> str:
    """从安装路径（末尾含版本号）提取版本并获取名称"""
    path = delphi_path.rstrip("\\/")
    match = re.search(r"(\d+\.\d+)$", path)
    if not match:
        return "Delphi Unknown"
    return get_version_name(match.group(1))


def get_project_version_name(version_prefix: str) -> str | None:
    """根据 .dproj 版本前缀获取 Delphi 产品名称"""
    return PROJECT_VERSION_PREFIX_MAP.get(version_prefix)


# ============================================================
# dcc32 --version 输出中的编译器版本 → 注册表版本号
# 当注册表不可用时，通过运行编译器 --version 并映射此表获取版本
# ============================================================
# dcc32 --version 输出示例:
#   Embarcadero Delphi for Win32 compiler version 35.0
# 编译器版本 35.0 → 注册表版本 22.0 (Delphi 11 Alexandria)
DCC_VERSION_TO_REGISTRY: dict[str, str] = {
    "35.0": "22.0",   # Delphi 11 Alexandria
    "36.0": "23.0",   # Delphi 12 Athens
    "37.0": "37.0",   # Delphi 13 Florence
    "34.0": "21.0",   # Delphi 10.4 Sydney
    "33.0": "20.0",   # Delphi 10.3 Rio
    "32.0": "19.0",   # Delphi 10.2 Tokyo
    "31.0": "18.0",   # Delphi 10.1 Berlin
}


def parse_compiler_version_from_output(output: str) -> Optional[str]:
    """
    从 dcc32 --version 输出中提取编译器版本号。

    Args:
        output: dcc32 --version 的 stdout 输出

    Returns:
        编译器版本号如 "35.0"，解析失败返回 None
    """
    match = re.search(r'compiler version (\d+\.\d+)', output)
    return match.group(1) if match else None


def detect_registry_version_from_compiler(compiler_path: str, timeout: int = 10) -> Optional[str]:
    """
    运行编译器 --version 并解析输出，映射到注册表版本号。

    适用于注册表不可用时（如手动配置的编译器、PATH 中找到的等）。
    结果会被缓存到 CompilerConfig.registry_version 中，无需重复调用。

    Args:
        compiler_path: dcc32.exe/dcc64.exe 完整路径
        timeout: 超时秒数

    Returns:
        注册表版本号如 "22.0"，检测失败返回 None
    """
    import subprocess
    try:
        result = subprocess.run(
            [compiler_path, '--version'],
            capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode != 0:
            return None

        compiler_ver = parse_compiler_version_from_output(result.stdout)
        if not compiler_ver:
            return None

        # 已知版本映射表精确匹配
        if compiler_ver in DCC_VERSION_TO_REGISTRY:
            return DCC_VERSION_TO_REGISTRY[compiler_ver]

        # 未知版本：尝试公式推算
        # 已知规律: registry_version ≈ compiler_version - 13
        # 如 35.0 - 13 = 22.0, 36.0 - 13 = 23.0
        try:
            parts = compiler_ver.split('.')
            major = int(parts[0])
            estimated = major - 13
            if 3 <= estimated <= 40:  # 合理范围
                return f"{estimated}.0"
        except (ValueError, IndexError):
            pass

        return None
    except (subprocess.TimeoutExpired, OSError):
        return None
