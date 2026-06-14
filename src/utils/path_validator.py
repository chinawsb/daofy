"""
路径校验器 — 白名单式路径访问控制 (Path Sandbox)

允许访问的域:
1. 项目目录 (project_path 所在目录 或 CWD)
2. 从 .dproj 解析的第三方库搜索路径
3. Delphi 官方安装路径（注册表读取）
4. 其它明确允许的路径（手动添加）

Usage:
    from src.utils.path_validator import get_path_validator
    validator = get_path_validator()
    validator.resolve(project_path="/path/to/project.dproj")
    err = validator.validate("/some/file.pas")
    if err:
        ...  # 拒绝访问

线程安全: resolve() 内部有锁保护，允许多次调用（仅有首次会实际解析）。
"""

import os
import threading
from pathlib import Path
from typing import List, Optional, Set

# ── 全局默认校验器（单例）────────────────────────────────
_default_validator: Optional["PathValidator"] = None
_init_lock = threading.Lock()


def get_path_validator() -> "PathValidator":
    """获取全局默认 PathValidator 单例"""
    global _default_validator
    if _default_validator is None:
        with _init_lock:
            if _default_validator is None:
                _default_validator = PathValidator()
    return _default_validator


def _norm_path(path: str) -> str:
    """归一化路径：绝对路径 + 大小写统一"""
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _get_system_temp_dirs() -> List[str]:
    """获取系统临时目录列表

    临时目录是受信任的系统级路径，用于 DFM 转换、编译临时文件等。
    """
    dirs: List[str] = []
    for env_var in ('TMP', 'TEMP', 'USERPROFILE'):
        val = os.environ.get(env_var)
        if val and os.path.isdir(val):
            dirs.append(val)
    return dirs


class PathValidator:
    """白名单式路径校验器"""

    def __init__(self):
        self._allowed_dirs: List[str] = []
        self._extra_dirs: List[str] = []
        self._resolved = False
        self._resolve_lock = threading.Lock()

    # ── 公开 API ──────────────────────────────────────────

    def add_allowed_dir(self, directory: str) -> None:
        """添加一个明确允许的目录（在 resolve 前调用）

        Args:
            directory: 允许访问的目录路径
        """
        norm = _norm_path(directory)
        if norm not in self._extra_dirs:
            self._extra_dirs.append(norm)

    def resolve(self, project_path: Optional[str] = None) -> None:
        """解析确定所有允许域（线程安全，仅首次实际解析）

        Args:
            project_path: 项目路径(.dproj/.dpr/.dpk)，不传则自动检测
        """
        if self._resolved:
            return
        with self._resolve_lock:
            if self._resolved:
                return
            self._do_resolve(project_path)
            self._resolved = True

    def resolve_forced(self, project_path: Optional[str] = None) -> None:
        """强制重新解析（项目切换时调用）"""
        with self._resolve_lock:
            self._allowed_dirs = []
            self._resolved = False
            self._do_resolve(project_path)
            self._resolved = True

    def validate(self, file_path: str) -> Optional[str]:
        """校验文件路径是否在允许域内

        Args:
            file_path: 待校验的文件路径

        Returns:
            None 表示安全，错误字符串表示拒绝原因
        """
        # 1. 基础安全校验
        if '\0' in file_path:
            return "路径包含 null 字节"

        # 2. 解析绝对路径
        try:
            resolved = os.path.abspath(os.path.realpath(file_path))
        except (OSError, ValueError) as e:
            return f"路径解析失败: {e}"

        # 3. 自动解析（首次）
        if not self._resolved:
            self.resolve()

        # 4. 检查是否在任一允许域内
        for allowed_dir in self._allowed_dirs:
            try:
                rel = os.path.relpath(resolved, allowed_dir)
                if not rel.startswith('..') and not os.path.isabs(rel):
                    return None  # 在允许域内
            except ValueError:
                continue

        # 5. 拒绝
        return (
            "路径不在允许的访问目录内。"
            "允许的目录: 项目目录、Delphi 安装目录、第三方库搜索路径"
        )

    def allowed_dirs_summary(self) -> List[str]:
        """返回当前允许的目录列表（用于调试/日志）"""
        if not self._resolved:
            return []  # 未解析时不构造
        return list(self._allowed_dirs)

    # ── 内部方法 ──────────────────────────────────────────

    def _do_resolve(self, project_path: Optional[str] = None) -> None:
        """实际解析逻辑"""
        collected: List[str] = []

        # 1. 项目根目录
        project_root = self._resolve_project_root(project_path)
        if project_root:
            collected.append(project_root)

        # 2. 从 .dproj 解析第三方库搜索路径
        search_paths = self._resolve_dproj_paths(project_root) if project_root else []
        collected.extend(search_paths)

        # 3. Delphi 官方安装路径
        delphi_paths = self._resolve_delphi_paths()
        collected.extend(delphi_paths)

        # 4. 系统临时目录（DFM 转换、编译等需要）
        collected.extend(_get_system_temp_dirs())

        # 5. 显式添加的额外路径
        collected.extend(self._extra_dirs)

        # 6. 归一化 + 去重 + 仅保留存在的目录
        seen: Set[str] = set()
        for raw in collected:
            try:
                norm = _norm_path(raw)
                if norm not in seen and os.path.isdir(norm):
                    seen.add(norm)
                    self._allowed_dirs.append(norm)
            except (OSError, ValueError):
                continue

        logger = _get_logger()
        logger.info(
            "PathValidator 已解析 %d 个允许目录 (project_path=%s)",
            len(self._allowed_dirs),
            project_path,
        )

    @staticmethod
    def _resolve_project_root(project_path: Optional[str] = None) -> Optional[str]:
        """解析项目根目录

        优先级:
          1. 传入的 project_path
          2. CWD 或祖先目录中的第一个 .dproj 所在目录
          3. CWD 本身（兜底）
        """
        if project_path:
            p = Path(project_path)
            if p.exists():
                return str(p.parent if p.is_file() else p.resolve())

        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents):
            dproj_files = list(parent.glob("*.dproj"))
            if dproj_files:
                return str(parent)
        return str(cwd)

    @staticmethod
    def _resolve_dproj_paths(project_root: str) -> List[str]:
        """从项目目录下的 .dproj 解析第三方库搜索路径"""
        paths: List[str] = []
        try:
            from src.utils.dproj_parser import DprojParser  # noqa: lazy, avoid circular

            for dproj_file in Path(project_root).glob("*.dproj"):
                parser = DprojParser(str(dproj_file))
                if parser.parse():
                    for p in parser.get_unit_search_paths():
                        if Path(p).is_dir():
                            paths.append(p)
        except Exception:
            pass
        return paths

    @staticmethod
    def _resolve_delphi_paths() -> List[str]:
        """解析 Delphi 安装路径

        从注册表读取所有已安装 Delphi 版本的:
          - RootDir (安装根目录)
          - Library Search Path (库搜索路径)
        """
        paths: List[str] = []
        try:
            from src.utils.delphi_env import (  # noqa: lazy
                get_delphi_version,
                get_delphi_root_dir,
                get_delphi_library_paths,
            )

            # 获取所有已安装的 Delphi 版本
            version = get_delphi_version()
            if version:
                root = get_delphi_root_dir(version)
                if root:
                    paths.append(root)
                lib_paths = get_delphi_library_paths(version)
                paths.extend(p for p in lib_paths if Path(p).is_dir())
        except Exception:
            pass
        return paths


def _get_logger():
    """延迟获取 logger，避免导入时循环"""
    from src.utils.logger import get_logger  # noqa: lazy

    return get_logger(__name__)
