"""
Delphi 环境工具函数

提供 Delphi 相关的路径和环境变量处理功能
"""

import os
import re
import winreg
from typing import Dict, Optional, List


def get_delphi_version() -> Optional[str]:
    """
    获取当前系统安装的 Delphi 版本
     
    Returns:
        Delphi 版本号 (如 "23.0")，未安装则返回 None
    """
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, 
            r"SOFTWARE\Embarcadero\BDS"
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
    except Exception:
        pass
    
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
            rf"SOFTWARE\Embarcadero\BDS\{version}"
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
            rf"SOFTWARE\Embarcadero\BDS\{version}\Environment Variables"
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
    except Exception:
        pass
    
    return env_vars


def get_delphi_library_paths(version: Optional[str] = None, platform: str = "Win32") -> List[str]:
    """
    获取 Delphi 库搜索路径
     
    Args:
        version: Delphi 版本号，默认获取最新版本
        platform: 目标平台 (Win32/Win64)
        
    Returns:
        搜索路径列表
    """
    paths = []
    
    if not version:
        version = get_delphi_version()
        if not version:
            return paths
    
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, 
            rf"SOFTWARE\Embarcadero\BDS\{version}\Library\{platform}"
        )
        
        search_path, _ = winreg.QueryValueEx(key, "Search Path")
        winreg.CloseKey(key)
        
        if search_path:
            paths = [p.strip() for p in search_path.split(';') if p.strip()]
    except Exception:
        pass
    
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
    user_docs = os.path.expanduser("~\\Documents")
    
    # 构建默认宏字典
    macros: Dict[str, str] = {}
    
    if bds_root:
        macros['$(BDS)'] = bds_root
        macros['$(BDSBIN)'] = os.path.join(bds_root, 'bin')
        macros['$(BDSLIB)'] = os.path.join(bds_root, 'lib')
    
    if user_docs:
        public_docs = user_docs.replace('\\' + user_docs.split('\\')[-1], '')
        
        macros['$(BDSUSERDIR)'] = user_docs + '\\Embarcadero\\Studio\\' + (version or '23.0')
        macros['$(BDSCOMMONDIR)'] = public_docs + '\\Embarcadero\\Studio\\' + (version or '23.0')
        macros['$(BDSCatalogRepository)'] = user_docs + '\\Embarcadero\\Studio\\' + (version or '23.0') + '\\CatalogRepository'
        macros['$(PublicDocuments)'] = public_docs
    
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
    catalog_base = user_docs + '\\Embarcadero\\Studio\\' + (version or '23.0') + '\\CatalogRepository'
    
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
