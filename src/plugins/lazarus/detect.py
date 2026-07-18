"""
Lazarus/FPC 路径检测 — 单一入口，所有模块共用。

搜索顺序:
  1. PATH 环境变量
  2. 常见安装目录
  3. 开始菜单快捷方式（解析 .lnk 目标）
  4. Windows 注册表（Uninstall 信息）
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from ...utils.logger import get_logger

logger = get_logger(__name__)


# ── 常见安装目录（所有检测逻辑共用）──

_LAZARUS_COMMON_DIRS: List[Path] = [
    Path("C:/lazarus"),
    Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Lazarus",
    Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Lazarus",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Lazarus",
]


# ── 开始菜单路径（Windows 特有）──

_START_MENU_DIRS: List[Path] = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Lazarus",
    Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Lazarus",
]


def _resolve_lnk_target(lnk_path: Path) -> Optional[str]:
    """通过 PowerShell 解析 .lnk 快捷方式的目标路径。"""
    try:
        cmd = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$sc = $ws.CreateShortcut("{lnk_path}"); '
            f'Write-Output $sc.TargetPath'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            target = result.stdout.strip()
            if target and Path(target).exists():
                return target
    except Exception as e:
        logger.debug(f"解析 .lnk 失败: {lnk_path}: {e}")
    return None


def _resolve_start_menu_lazbuild() -> Optional[Path]:
    """从开始菜单的 Lazarus 快捷方式反查安装路径。"""
    for menu_dir in _START_MENU_DIRS:
        if not menu_dir.is_dir():
            continue
        for lnk in menu_dir.glob("*.lnk"):
            if "lazarus" in lnk.stem.lower() and "uninstall" not in lnk.stem.lower():
                target = _resolve_lnk_target(lnk)
                if target:
                    lazbuild = Path(target).parent / "lazbuild.exe"
                    if lazbuild.exists():
                        logger.info(f"通过开始菜单找到 lazbuild: {lazbuild}")
                        return lazbuild
    return None


def _resolve_registry_lazbuild() -> Optional[Path]:
    """从 Windows 注册表 Uninstall 信息查找 Lazarus 安装路径。"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        )
        try:
            i = 0
            while True:
                subkey_name = winreg.EnumKey(key, i)
                i += 1
                try:
                    sk = winreg.OpenKey(key, subkey_name)
                    try:
                        name, _ = winreg.QueryValueEx(sk, "DisplayName")
                        if name and "lazarus" in name.lower():
                            install_loc, _ = winreg.QueryValueEx(sk, "InstallLocation")
                            if install_loc:
                                lazbuild = Path(install_loc) / "lazbuild.exe"
                                if lazbuild.exists():
                                    logger.info(f"通过注册表找到 lazbuild: {lazbuild}")
                                    return lazbuild
                    except FileNotFoundError:
                        pass
                    finally:
                        winreg.CloseKey(sk)
                except FileNotFoundError:
                    continue
        except OSError:
            pass
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        logger.debug(f"注册表检测失败: {e}")
    return None


# ── 公开 API ──


def find_lazbuild() -> List[Path]:
    """返回所有找到的 lazbuild.exe 路径列表（去重）。
    
    搜索顺序: PATH → 常见目录 → 开始菜单 → 注册表
    """
    seen: set[str] = set()
    candidates: List[Path] = []

    def _add(p: Path) -> None:
        resolved = str(p.resolve())
        if resolved not in seen:
            seen.add(resolved)
            candidates.append(p)

    # 1. PATH
    path_result = shutil.which("lazbuild")
    if path_result:
        _add(Path(path_result))

    # 2. 常见安装目录
    for d in _LAZARUS_COMMON_DIRS:
        lb = d / "lazbuild.exe"
        if lb.exists():
            _add(lb)

    # 3. 开始菜单
    sm = _resolve_start_menu_lazbuild()
    if sm:
        _add(sm)

    # 4. 注册表
    reg = _resolve_registry_lazbuild()
    if reg:
        _add(reg)

    return candidates


def find_lazarus_root() -> Optional[Path]:
    """返回 Lazarus 安装根目录（lazbuild.exe 所在目录的父目录）。"""
    lazbuild_paths = find_lazbuild()
    if lazbuild_paths:
        return lazbuild_paths[0].parent
    return None


def is_lazarus_available() -> bool:
    """快速检查 Lazarus 是否已安装（不解析 .lnk/注册表）。"""
    # PATH
    if shutil.which("lazbuild"):
        return True
    # 常见目录（仅检查 exe 是否存在，不解析快捷方式）
    for d in _LAZARUS_COMMON_DIRS:
        if (d / "lazbuild.exe").exists():
            return True
    # 开始菜单（快捷方式存在即可，不解析目标）
    for menu_dir in _START_MENU_DIRS:
        if menu_dir.is_dir() and any(
            "lazarus" in lnk.stem.lower() and "uninstall" not in lnk.stem.lower()
            for lnk in menu_dir.glob("*.lnk")
        ):
            return True
    # 注册表
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        )
        try:
            i = 0
            while True:
                subkey_name = winreg.EnumKey(key, i)
                i += 1
                try:
                    sk = winreg.OpenKey(key, subkey_name)
                    try:
                        name, _ = winreg.QueryValueEx(sk, "DisplayName")
                        if name and "lazarus" in name.lower():
                            return True
                    except FileNotFoundError:
                        pass
                    finally:
                        winreg.CloseKey(sk)
                except FileNotFoundError:
                    continue
        except OSError:
            pass
        finally:
            winreg.CloseKey(key)
    except Exception:
        pass
    return False


def find_lazarus_source_dirs() -> List[dict]:
    """返回 Lazarus/FPC 源码目录列表（供 KB 构建使用）。"""
    root = find_lazarus_root()
    if not root:
        return []

    # 确保 root 是 lazarus 安装根目录（不是 bin 目录）
    lazarus_root = root.parent if root.name == "bin" else root
    # 检查是否是真正的 lazarus 根目录
    if not (lazarus_root / "lcl").is_dir():
        # 可能 root 本身就是 lazarus 根
        if (root / "lcl").is_dir():
            lazarus_root = root
        else:
            return []

    sources: List[dict] = []

    # LCL
    lcl = lazarus_root / "lcl"
    if lcl.is_dir():
        sources.append({"path": str(lcl), "label": "LCL (Lazarus Component Library)"})

    # Components
    components = lazarus_root / "components"
    if components.is_dir():
        sources.append({"path": str(components), "label": "Lazarus bundled components"})

    # FPC 源码
    fpc_root = lazarus_root / "fpc"
    if fpc_root.is_dir():
        for ver_dir in sorted(fpc_root.iterdir(), reverse=True):
            src = ver_dir / "source"
            if src.is_dir():
                sources.append({"path": str(src), "label": f"FPC RTL {ver_dir.name}"})
                break
            elif ver_dir.is_dir():
                sources.append({"path": str(ver_dir), "label": f"FPC {ver_dir.name}"})
                break

    return sources
