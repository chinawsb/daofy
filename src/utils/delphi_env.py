"""
Delphi 环境工具函数

提供 Delphi 相关的路径和环境变量处理功能
"""

import logging
import os
import re
import winreg
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Sequence

from ..constants import REG_KEY_EMBARCADERO_BDS, REG_KEY_EMBARCADERO_STUDIO

logger = logging.getLogger(__name__)

_MSBUILD_XML_NAMESPACE = "http://schemas.microsoft.com/developer/msbuild/2003"


@dataclass(frozen=True)
class EnvOptionsLibraryStatus:
    """Comparison result for registry and EnvOptions Delphi library paths."""

    state: Literal[
        "current", "missing", "stale", "unknown", "registry_missing",
    ]
    env_options_path: Optional[Path]
    registry_paths: tuple[str, ...]
    env_options_paths: tuple[str, ...]


def get_public_documents_dir() -> Optional[Path]:
    """Return the Windows Public Documents directory when it is available."""
    public_root = os.environ.get("PUBLIC")
    if not public_root:
        return None
    return Path(public_root) / "Documents"


def get_delphi_public_studio_root() -> Optional[Path]:
    """Return the shared Embarcadero Studio root under Public Documents."""
    public_docs = get_public_documents_dir()
    if public_docs is None:
        return None
    return public_docs / "Embarcadero" / "Studio"


def get_delphi_common_dir(version: Optional[str] = None) -> Optional[Path]:
    """Return $(BDSCOMMONDIR) for the requested Delphi version."""
    if not version:
        version = get_delphi_version()
    if not version:
        return None
    root = get_delphi_public_studio_root()
    if root is None:
        return None
    return root / version


def get_delphi_bpl_dir(version: Optional[str] = None) -> Optional[Path]:
    """Return the shared BPL output directory for the requested Delphi version."""
    common_dir = get_delphi_common_dir(version)
    if common_dir is None:
        return None
    return common_dir / "Bpl"


def get_delphi_version() -> Optional[str]:
    """
    获取当前系统安装的 Delphi 版本
     
    Returns:
        Delphi 版本号 (如 "23.0")，未安装则返回 None
    """
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, 
            REG_KEY_EMBARCADERO_BDS
        )
        
        # 枚举所有已安装的版本
        versions = []
        i = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, i)
                # 尝试解析版本号
                if subkey_name.replace('.', '').isdigit():
                    versions.append(subkey_name)
                i += 1
            except WindowsError:
                break
        
        winreg.CloseKey(key)
        
        # 返回最新的版本
        if versions:
            return sorted(versions, key=lambda x: tuple(int(p) for p in x.split('.')), reverse=True)[0]
    except Exception as e:
        logger.debug("读取Delphi版本失败: %s", str(e))
    
    return None


def get_delphi_root_dir(version: Optional[str] = None) -> Optional[str]:
    """
    获取 Delphi 安装根目录
     
    Args:
        version: Delphi 版本号，默认获取最新版本
        
    Returns:
        Delphi 根目录路径
    """
    if not version:
        version = get_delphi_version()
        if not version:
            return None
    
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, 
            f"{REG_KEY_EMBARCADERO_BDS}\\{version}"
        )
        root_dir, _ = winreg.QueryValueEx(key, "RootDir")
        winreg.CloseKey(key)
        return root_dir
    except Exception:
        return None


def get_delphi_env_vars(version: Optional[str] = None) -> Dict[str, str]:
    """
    获取 Delphi 环境变量
     
    Args:
        version: Delphi 版本号，默认获取最新版本
        
    Returns:
        环境变量字典
    """
    env_vars = {}
    
    if not version:
        version = get_delphi_version()
        if not version:
            return env_vars
    
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, 
            f"{REG_KEY_EMBARCADERO_BDS}\\{version}\\Environment Variables"
        )
        
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
                env_vars[name] = value
                i += 1
            except WindowsError:
                break
        
        winreg.CloseKey(key)
    except Exception as e:
        logger.debug("读取环境变量失败: %s", str(e))
    
    return env_vars


def get_delphi_library_paths(version: Optional[str] = None, platform: str = "Win32") -> List[str]:
    """
    获取 Delphi 库搜索路径（合并 BDS + Studio 注册表配置单元）

    Args:
        version: Delphi 版本号，默认获取最新版本
        platform: 目标平台 (Win32/Win64)

    Returns:
        搜索路径列表
    """
    paths: list[str] = []
    seen: set[str] = set()

    if not version:
        version = get_delphi_version()
        if not version:
            return paths

    registries = [
        f"{REG_KEY_EMBARCADERO_BDS}\\{version}\\Library\\{platform}",
        f"{REG_KEY_EMBARCADERO_STUDIO}\\{version}\\Library\\{platform}",
    ]

    for reg_path in registries:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path)
            search_path, _ = winreg.QueryValueEx(key, "Search Path")
            winreg.CloseKey(key)
            if search_path:
                for p in search_path.split(';'):
                    p = p.strip()
                    if p and p not in seen:
                        paths.append(p)
                        seen.add(p)
        except Exception as e:
            logger.debug("读取 %s 的 Search Path 失败: %s", reg_path, str(e))

    return paths


def expand_delphi_path_macros(
    path: str, 
    version: Optional[str] = None,
    platform: Optional[str] = None,
    env_vars: Optional[Dict[str, str]] = None
) -> str:
    """
    展开 Delphi 路径中的宏变量
    
    支持的宏:
    - $(BDS) - Delphi 根目录
    - $(BDSCOMMONDIR) - 公共文档目录
    - $(BDSUSERDIR) - 用户文档目录
    - $(BDSBIN) - Delphi bin 目录
    - $(BDSLIB) - Delphi lib 目录
    - $(BDSCatalogRepository) - GetIt 组件目录
    - $(PublicDocuments) - 公共文档目录
    - $(Platform) - 目标平台
    
    Args:
        path: 原始路径，可能包含宏
        version: Delphi 版本号，默认获取最新版本
        platform: 目标平台，默认 Win32
        env_vars: 额外的环境变量
        
    Returns:
        展开后的路径
    """
    if not version:
        version = get_delphi_version()
    if not platform:
        platform = "Win32"
    
    # 获取 Delphi 根目录
    bds_root = get_delphi_root_dir(version)
    user_docs = Path.home() / "Documents"
    public_docs = get_public_documents_dir()
    
    # 构建默认宏字典
    macros: Dict[str, str] = {}
    
    if bds_root:
        macros['$(BDS)'] = bds_root
        macros['$(BDSBIN)'] = os.path.join(bds_root, 'bin')
        macros['$(BDSLIB)'] = os.path.join(bds_root, 'lib')
    
    if user_docs:
        if version:
            macros['$(BDSUSERDIR)'] = str(user_docs / "Embarcadero" / "Studio" / version)
            common_dir = get_delphi_common_dir(version)
            if common_dir is not None:
                macros['$(BDSCOMMONDIR)'] = str(common_dir)
            macros['$(BDSCatalogRepository)'] = str(
                user_docs / "Embarcadero" / "Studio" / version / "CatalogRepository"
            )
        if public_docs is not None:
            macros['$(PublicDocuments)'] = str(public_docs)
    
    # 添加平台宏
    macros['$(Platform)'] = platform
    
    # 合并用户定义的环境变量（键名需要加 $() 前缀才能被 str.replace 正确匹配）
    if env_vars:
        for k, v in env_vars.items():
            macros[f'$({k})'] = v
    
    # 添加注册表中的环境变量（同上，注册表键名如 SKIADIR 需转为 $(SKIADIR)）
    reg_env_vars = get_delphi_env_vars(version)
    for k, v in reg_env_vars.items():
        macros[f'$({k})'] = v
    
    # 展开路径
    result = path
    
    # 多次替换，确保嵌套宏也能展开
    max_iterations = 5
    for _ in range(max_iterations):
        new_result = result
        for macro, value in macros.items():
            new_result = new_result.replace(macro, value)
        
        # 如果没有变化，停止迭代
        if new_result == result:
            break
        result = new_result
    
    # 检测并警告未解析的宏
    unresolved = re.findall(r'\$\([^)]+\)', result)
    if unresolved:
        import logging
        logging.getLogger(__name__).warning(
            "路径中存在未解析的宏变量 %s: %s", list(set(unresolved)), path
        )
    
    # 清理未解析的宏（避免返回含 $(...) 的无效路径）
    result = re.sub(r'\$\([^)]+\)', '', result)
    
    return result


def get_catalog_repository_paths(version: Optional[str] = None) -> List[str]:
    """
    获取 GetIt CatalogRepository 中所有组件的源码路径
    
    Args:
        version: Delphi 版本号，默认获取最新版本
        
    Returns:
        组件源码路径列表
    """
    paths = []
    
    if not version:
        version = get_delphi_version()
        if not version:
            return paths
    
    # 获取 CatalogRepository 路径
    user_docs = os.path.expanduser("~\\Documents")
    catalog_base = user_docs + '\\Embarcadero\\Studio\\' + version + '\\CatalogRepository'
    
    if not os.path.exists(catalog_base):
        return paths
    
    # 遍历所有组件
    for item in os.listdir(catalog_base):
        source_path = os.path.join(catalog_base, item, 'Source')
        if os.path.isdir(source_path):
            paths.append(source_path)
    
    return paths


def resolve_delphi_search_paths(
    version: Optional[str] = None,
    platform: str = "Win32"
) -> List[str]:
    """
    解析 Delphi 所有搜索路径（项目 + 注册表 + GetIt）
    
    Args:
        version: Delphi 版本号，默认获取最新版本
        platform: 目标平台
        
    Returns:
        所有搜索路径列表
    """
    all_paths = []
    seen = set()
    
    # 1. 从注册表获取库搜索路径
    library_paths = get_delphi_library_paths(version, platform)
    for path in library_paths:
        expanded = expand_delphi_path_macros(path, version, platform)
        if os.path.exists(expanded) and expanded not in seen:
            all_paths.append(expanded)
            seen.add(expanded)
    
    # 2. 从 GetIt CatalogRepository 获取组件源码路径
    catalog_paths = get_catalog_repository_paths(version)
    for path in catalog_paths:
        if os.path.exists(path) and path not in seen:
            all_paths.append(path)
            seen.add(path)
    
    return all_paths


def get_env_options_path(
    version: str,
    appdata_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Return the EnvOptions.proj path for one Delphi version.

    Args:
        version: Delphi registry version, such as ``37.0``.
        appdata_dir: Optional APPDATA override used by tests and hosted processes.

    Returns:
        The version-specific EnvOptions path, or ``None`` when APPDATA is unavailable.
    """
    base_dir = appdata_dir
    if base_dir is None:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return None
        base_dir = Path(appdata)
    return base_dir / "Embarcadero" / "BDS" / version / "EnvOptions.proj"


def _platform_condition_matches(condition: str, platform: str) -> Optional[bool]:
    """Evaluate the simple Platform conditions generated in EnvOptions.proj."""
    if not condition:
        return True

    lowered = condition.lower()
    if "$(platform)" not in lowered:
        return None
    if re.search(r"\band\b", lowered):
        return None

    values = re.findall(
        r"['\"]?\$\(\s*platform\s*\)['\"]?\s*==\s*['\"]([^'\"]+)['\"]",
        condition,
        flags=re.IGNORECASE,
    )
    if not values:
        return None
    return any(value.casefold() == platform.casefold() for value in values)


def _read_env_options_library_paths(
    env_options_path: Path,
    platform: str,
) -> tuple[Optional[list[str]], bool]:
    """Read the effective DelphiLibraryPath for a generated EnvOptions file."""
    try:
        root = ET.parse(env_options_path).getroot()
    except (ET.ParseError, OSError) as exc:
        logger.warning("无法解析 EnvOptions 文件 %s: %s", env_options_path, exc)
        return None, False

    library_path: Optional[str] = None
    for group in root.iter():
        if group.tag.rsplit("}", 1)[-1] != "PropertyGroup":
            continue
        group_match = _platform_condition_matches(group.attrib.get("Condition", ""), platform)
        for child in group:
            if child.tag.rsplit("}", 1)[-1] != "DelphiLibraryPath":
                continue
            if group_match is None:
                return None, False
            child_match = _platform_condition_matches(child.attrib.get("Condition", ""), platform)
            if child_match is None:
                return None, False
            if group_match and child_match:
                library_path = child.text or ""

    if library_path is None:
        return [], True
    return [path.strip() for path in library_path.split(";") if path.strip()], True


def _normalize_library_paths(
    paths: Sequence[str],
    version: str,
    platform: str,
) -> tuple[str, ...]:
    """Normalize an ordered Delphi library path list for semantic comparison."""
    normalized: list[str] = []
    seen: set[str] = set()
    for path in paths:
        expanded = expand_delphi_path_macros(path.strip().strip('"'), version, platform)
        if not expanded:
            continue
        key = os.path.normcase(os.path.normpath(expanded))
        if key not in seen:
            normalized.append(key)
            seen.add(key)
    return tuple(normalized)


def inspect_env_options_library_paths(
    version: str,
    platform: str,
    *,
    appdata_dir: Optional[Path] = None,
    registry_paths: Optional[Sequence[str]] = None,
) -> EnvOptionsLibraryStatus:
    """Compare one Delphi version's registry and EnvOptions library paths.

    Args:
        version: Delphi registry version selected for the build.
        platform: Effective MSBuild platform.
        appdata_dir: Optional APPDATA override.
        registry_paths: Optional registry path override for deterministic tests.

    Returns:
        A classified comparison result. The function never falls back to another
        Delphi version when the selected version cannot be inspected.
    """
    resolved_registry_paths = tuple(
        registry_paths
        if registry_paths is not None
        else get_delphi_library_paths(version, platform)
    )
    env_options_path = get_env_options_path(version, appdata_dir)
    if not resolved_registry_paths:
        return EnvOptionsLibraryStatus(
            "registry_missing", env_options_path, (), (),
        )
    if env_options_path is None:
        return EnvOptionsLibraryStatus(
            "unknown", None, resolved_registry_paths, (),
        )
    if not env_options_path.is_file():
        return EnvOptionsLibraryStatus(
            "missing", env_options_path, resolved_registry_paths, (),
        )

    env_paths, parsed = _read_env_options_library_paths(env_options_path, platform)
    if not parsed or env_paths is None:
        return EnvOptionsLibraryStatus(
            "unknown", env_options_path, resolved_registry_paths, (),
        )
    if not env_paths:
        return EnvOptionsLibraryStatus(
            "missing", env_options_path, resolved_registry_paths, (),
        )

    registry_normalized = _normalize_library_paths(
        resolved_registry_paths, version, platform,
    )
    env_normalized = _normalize_library_paths(env_paths, version, platform)
    state: Literal["current", "stale"] = (
        "current" if registry_normalized == env_normalized else "stale"
    )
    return EnvOptionsLibraryStatus(
        state,
        env_options_path,
        resolved_registry_paths,
        tuple(env_paths),
    )


def build_env_options_overlay(
    original_path: Optional[Path],
    registry_paths: Sequence[str],
    platform: str,
) -> str:
    """Build an EnvOptions overlay that preserves project unit search paths.

    Args:
        original_path: Existing EnvOptions file to import, when available.
        registry_paths: Current IDE Library Search Path entries.
        platform: Effective MSBuild platform.

    Returns:
        UTF-8 MSBuild XML that overrides only ``DelphiLibraryPath``.
    """
    ET.register_namespace("", _MSBUILD_XML_NAMESPACE)
    root = ET.Element(f"{{{_MSBUILD_XML_NAMESPACE}}}Project")
    if original_path is not None and original_path.is_file():
        ET.SubElement(
            root,
            f"{{{_MSBUILD_XML_NAMESPACE}}}Import",
            {"Project": str(original_path)},
        )
    group = ET.SubElement(
        root,
        f"{{{_MSBUILD_XML_NAMESPACE}}}PropertyGroup",
        {"Condition": f"'$(Platform)'=='{platform}'"},
    )
    library_path = ET.SubElement(
        group,
        f"{{{_MSBUILD_XML_NAMESPACE}}}DelphiLibraryPath",
    )
    library_path.text = ";".join(registry_paths)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)
