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

# 产品名（去掉 "Delphi " 前缀、小写）→ 注册表版本号
# 用于项目配置/版本映射中允许写 "XE4"、"12 Athens" 等易读写法
_VERSION_NAME_ALIASES: dict[str, str] = {}
for _registry_version, _product_name in DELPHI_VERSION_NAMES.items():
    _alias = _product_name.lower()
    if _alias.startswith("delphi "):
        _alias = _alias[len("delphi "):]
    _VERSION_NAME_ALIASES[_alias.strip()] = _registry_version

# .dproj ProjectVersion → 注册表版本号（反向映射）
# 多数版本两者相同，此处仅记录有差异的
PROJECT_VERSION_TO_REGISTRY: dict[str, str] = {
    "14.6": "14.0",   # Delphi XE6：.dproj 14.6 → 注册表 14.0
    "18.2": "18.0",   # Delphi 10.1 Berlin：.dproj 18.2 → 注册表 18.0
    "19.2": "19.0",   # Delphi 10.2 Tokyo：.dproj 19.2 → 注册表 19.0
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


def normalize_registry_version(value: Optional[str]) -> Optional[str]:
    """将用户输入的 Delphi 版本号规范化为 ``major.minor`` 形式。

    接受 ``"11"`` / ``"11.0"`` / ``" 11.0 "`` 等写法，统一返回 ``"11.0"``。
    无法识别（非数字、超出合理范围）时返回 ``None``。

    Args:
        value: 用户输入的版本号，如 ``"11"``、``"11.0"``

    Returns:
        规范化后的版本号（如 ``"11.0"``），无法识别时返回 ``None``
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.fullmatch(r"(\d+)(?:\.(\d+))?", text)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    if not 1 <= major <= 99 or not 0 <= minor <= 99:
        return None
    return f"{major}.{minor}"


def normalize_version_key(value: Optional[str]) -> Optional[str]:
    """将“Delphi 版本标识”规范化为注册表版本号（``major.minor``）。

    与 :func:`normalize_registry_version` 相比，额外接受产品名写法，
    便于在项目配置/版本→MSBuild 映射中直接写 ``"XE4"``、``"Delphi XE4"``
    或 ``"Delphi 12 Athens"``：

    - ``"11"`` / ``"11.0"`` / ``" 11.0 "`` → ``"11.0"``
    - ``"XE4"`` / ``"Delphi XE4"`` → ``"11.0"``
    - ``"14.6"`` / ``"18.2"`` / ``"19.2"``（.dproj ProjectVersion）→ ``"14.0"`` / ``"18.0"`` / ``"19.0"``
    - ``"Delphi 12 Athens"`` → ``"23.0"``

    纯数字仍按注册表版本解释（``"12"`` → ``"12.0"`` = XE5），仅对已知的
    ``.dproj ProjectVersion`` 差异（14.6/18.2/19.2）做映射；非数字写法按产品名匹配。

    Args:
        value: 版本号或 Delphi 产品名

    Returns:
        规范化后的注册表版本号，无法识别时返回 None
    """
    numeric = normalize_registry_version(value)
    if numeric:
        return PROJECT_VERSION_TO_REGISTRY.get(numeric, numeric)
    if value is None:
        return None

    text = str(value).strip().lower()
    if not text:
        return None

    alias = _VERSION_NAME_ALIASES.get(text)
    if alias:
        return alias
    if text.startswith("delphi "):
        alias = _VERSION_NAME_ALIASES.get(text[len("delphi "):].strip())
        if alias:
            return alias

    # 允许产品名后带平台后缀，如 "XE4 Win32"、"Delphi 12 Athens Win64"
    for name, registry in _VERSION_NAME_ALIASES.items():
        for suffix in (" win32", " win64", " 32-bit", " 64-bit"):
            if text == name + suffix:
                return registry
    return None


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


# 注册表版本(registry_version) → .dproj ProjectVersion 映射
# 多数版本两者相同，此处仅记录有差异的
REGISTRY_TO_PROJECT_VERSION: dict[str, str] = {
    "14.0": "14.6",   # Delphi XE6：注册表 14.0，但 .dproj 格式标记为 14.6
    "18.0": "18.2",   # Delphi 10.1 Berlin：注册表 18.0，但 .dproj 格式标记为 18.2
    "19.0": "19.2",   # Delphi 10.2 Tokyo：注册表 19.0，但 .dproj 格式标记为 19.2
}


def registry_to_project_version(registry_ver: str) -> str:
    """
    将 Delphi 注册表版本号映射为 .dproj ProjectVersion。

    Delphi 10.2 及更新版本的 ProjectVersion 与注册表版本号相同。
    Delphi 10.1 Berlin 是特例：注册表 18.0 → ProjectVersion 18.2。

    Args:
        registry_ver: 注册表版本号，如 "22.0"

    Returns:
        .dproj 文件 ProjectVersion 值，如 "22.0"
    """
    return REGISTRY_TO_PROJECT_VERSION.get(registry_ver, registry_ver)


# .dproj ProjectVersion → 注册表版本号（反向映射）
# 定义在文件顶部（normalize_version_key 需要用到）


def resolve_registry_version(
    compiler_version: Optional[str],
    project_version: Optional[str] = None,
    config_manager: Optional[object] = None,
    override_version: Optional[str] = None,
) -> Optional[str]:
    """
    从 compiler_version（或 .dproj ProjectVersion 回退）解析注册表版本号。

    RTL 库搜索路径与第三方库路径共用此策略，保证两者按同一 Delphi 版本
    过滤注册表，避免出现“默认编译器为 Delphi 12 而库路径取 Delphi 13”的错配。

    Args:
        compiler_version: 用户/配置指定的编译器版本名称
        project_version: .dproj ProjectVersion（可选，compiler_version 未指定时回退）
        config_manager: 配置管理器实例（可选，未提供时仅能依靠 project_version 回退）
        override_version: 项目级配置指定的注册表版本号（如 ``"11.0"``），
            仅用于单工程配置，不影响其它工程

    Returns:
        注册表版本号如 "23.0"，无法解析返回 None
    """
    registry_version: Optional[str] = None

    if compiler_version:
        try:
            if config_manager is not None:
                compiler_cfg = config_manager.get_compiler(compiler_version)
                if compiler_cfg is not None:
                    registry_version = compiler_cfg.registry_version
        except Exception:
            registry_version = None

    if not registry_version and override_version:
        registry_version = normalize_version_key(override_version)
    if not registry_version and config_manager is not None:
        # 未显式指定编译器时，回退到"默认编译器"——与 compile_dpr_direct 实际
        # 调用的 config_manager.get_compiler(None) 保持一致。若此处直接返回 None,
        # 调用方 get_delphi_library_paths(None) 会取"最新已安装版本"的库路径,
        # 而实际 dcc32 用的是默认编译器,当默认编译器不是最新版本时两者错配,
        # 导致用 Delphi 12 的 dcc32 却找 Delphi 13 的 .dcu 而编译失败。
        try:
            default_cfg = config_manager.get_compiler(None)
            if default_cfg is not None:
                registry_version = default_cfg.registry_version
        except Exception:
            registry_version = None

    # Fallback: compiler_version 未指定/无法解析时，从 .dproj ProjectVersion 推断
    if not registry_version and project_version:
        registry_version = project_version_to_registry_version(project_version)

    return registry_version


def project_version_to_registry_version(project_ver: str) -> Optional[str]:
    """
    将 .dproj ProjectVersion 映射为注册表版本号（registry_version）。

    用于在 compiler_version 未指定时，从 .dproj 文件推断正确的 Delphi 版本，
    以获取该版本对应的库搜索路径。

    Delphi 10.2 及更新版本两者相同。
    Delphi 10.1 Berlin 是特例：.dproj 18.2 → 注册表 18.0。

    Args:
        project_ver: .dproj 文件 ProjectVersion 值，如 "22.0" 或 "18.2"

    Returns:
        注册表版本号如 "22.0"，无法映射返回 None
    """
    # 精确匹配（处理 Berlin 等例外）
    if project_ver in PROJECT_VERSION_TO_REGISTRY:
        return PROJECT_VERSION_TO_REGISTRY[project_ver]
    # 多数版本两者相同，直接验证是否已知
    if project_ver in DELPHI_VERSION_NAMES:
        return project_ver
    # 尝试整数前缀匹配（如 "19" → "19.0"）
    parts = project_ver.split(".")
    if parts and parts[0].isdigit():
        candidate = f"{parts[0]}.0"
        if candidate in DELPHI_VERSION_NAMES:
            return candidate
    return None
