"""
编译服务

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

核心业务逻辑,协调参数生成、进程执行、结果解析等组件
"""

import os
import tempfile
import time
import winreg
from datetime import datetime
from pathlib import Path
from typing import Optional
from ..constants import (
    REG_KEY_EMBARCADERO_BDS,
    TIMEOUT_DELPHI_COMPILE,
    TIMEOUT_MSBUILD_DISCOVERY,
    TIMEOUT_PROCESS_QUERY,
)
from ..models.compile_request import ProjectCompileRequest, FileCompileRequest, TargetPlatform, CompileOptions, OutputType, RuntimeLibrary
from ..models.compile_result import CompileResult, CompileStatus
from ..models.command_args import CommandArgs
from ..models.compile_history import CompileHistoryEntry
from ..models.compiler_config import CompilerConfig
from .args_generator import ArgsGenerator
from .process_manager import ProcessManager
from .config_manager import ConfigManager
from .project_settings import ProjectSettings, load_project_settings
from ..utils import get_console_encoding
from ..utils.delphi_env import (
    EnvOptionsLibraryStatus,
    build_env_options_overlay,
    get_delphi_public_studio_root,
    get_delphi_version as _get_delphi_version_env,
    inspect_env_options_library_paths,
)
from ..utils.delphi_versions import (
    detect_registry_version_from_compiler,
    normalize_registry_version,
    normalize_version_key,
    project_version_to_registry_version,
)
from ..utils.parser import OutputParser
from ..utils.validator import Validator
from ..utils.dproj_parser import DprojParser
from ..utils.unit_dependency_analyzer import SmartLibraryPathResolver
from ..utils.logger import get_logger

logger = get_logger(__name__)


class CompilerService:
    """编译服务"""

    def __init__(self, config_manager: ConfigManager):
        """初始化编译服务
        
        Args:
            config_manager: 配置管理器
        """
        self.config_manager = config_manager
        self.args_generator = ArgsGenerator()
        self.process_manager = ProcessManager()
        self.output_parser = OutputParser()
        self.validator = Validator()
        self.history: list = []
        
        # MSBuild 路径（初始化时先做一次通用探测；编译时再按工程版本重新探测）
        self.msbuild_path = self._find_msbuild()
        self._msbuild_auto_cache: dict[str, Optional[str]] = {}
        
        logger.info("编译服务初始化完成")

    def _lookup_compiler_by_version(
        self,
        version: str,
        platform: TargetPlatform,
    ) -> Optional[CompilerConfig]:
        """按 Delphi 版本查找编译器配置，兼容测试中的裁剪版 config_manager。"""
        config_manager = getattr(self, "config_manager", None)
        getter = getattr(config_manager, "get_compiler_by_registry_version", None)
        if not callable(getter) or not version:
            return None
        try:
            return getter(version, platform.value)
        except TypeError:
            # 兼容只接受一个位置参数的旧签名/桩对象
            try:
                return getter(version)
            except Exception:
                logger.warning("按版本查找编译器失败: %s", version, exc_info=True)
                return None
        except Exception:
            logger.warning("按版本查找编译器失败: %s", version, exc_info=True)
            return None

    def _compiler_from_registry_version(
        self,
        version: str,
        platform: TargetPlatform,
    ) -> Optional[CompilerConfig]:
        """按版本从注册表定位编译器，返回可用于编译的配置对象。"""
        path = self._find_compiler_from_registry(platform, version)
        if not path:
            return None
        return CompilerConfig(
            name=f"Delphi {version}",
            path=path,
            registry_version=version,
        )

    def _lookup_compiler_by_name_or_version(
        self,
        value: str,
        platform: TargetPlatform,
    ) -> Optional[CompilerConfig]:
        """先按编译器名称查找；找不到时把 value 当作 Delphi 版本再查。

        这样 ``compiler_version="11.0"`` / ``"XE4"`` 也能命中 XE4 的编译器，
        而不是直接报“编译器不存在”。
        """
        config_manager = getattr(self, "config_manager", None)
        if config_manager is None or not value:
            return None

        getter = getattr(config_manager, "get_compiler", None)
        if callable(getter):
            try:
                compiler = getter(value)
            except Exception:
                logger.warning("查找编译器配置失败: %s", value, exc_info=True)
                compiler = None
            if compiler:
                return compiler

        version = normalize_version_key(value)
        if version:
            return self._lookup_compiler_by_version(version, platform)
        return None

    def _warn_conflicting_project_versions(
        self,
        project_settings: Optional[ProjectSettings],
    ) -> None:
        """项目同时配置 compiler_version 与 delphi_version 且版本不一致时告警。"""
        if not project_settings:
            return
        if not project_settings.compiler_version or not project_settings.delphi_version:
            return
        compiler = self._lookup_compiler_by_name_or_version(
            project_settings.compiler_version,
            TargetPlatform.WIN32,
        )
        if not compiler or not compiler.registry_version:
            return
        actual = normalize_registry_version(compiler.registry_version)
        if actual and actual != project_settings.delphi_version:
            logger.warning(
                "项目配置 %s 中 compiler_version=%r 对应 Delphi %s，"
                "与 delphi_version=%s 不一致；将以 compiler_version 为准",
                project_settings.source,
                project_settings.compiler_version,
                actual,
                project_settings.delphi_version,
            )

    def _warn_if_direct_compile_version_mismatch(
        self,
        project_path: str,
        compiler: Optional[CompilerConfig],
    ) -> None:
        """直接编译时提示 .dproj 推断版本与实际编译器不一致。"""
        if not compiler or not compiler.registry_version:
            return
        dproj = project_path
        if Path(dproj).suffix.lower() in (".dpr", ".dpk"):
            dproj = str(Path(dproj).with_suffix(".dproj"))
        if not Path(dproj).exists():
            return
        try:
            parser = DprojParser(dproj)
            if not parser.parse():
                return
            project_version = parser.get_project_version()
        except Exception:
            logger.debug("读取 .dproj ProjectVersion 失败: %s", dproj, exc_info=True)
            return
        target = (
            project_version_to_registry_version(project_version)
            if project_version
            else None
        )
        actual = normalize_registry_version(compiler.registry_version)
        if target and actual and target != actual:
            logger.warning(
                "工程 %s 的 .dproj ProjectVersion=%s 对应 Delphi %s，"
                "但直接编译将使用编译器 %s（Delphi %s）；"
                "如需严格匹配，请在工程目录配置 .daofy/project.json 的 delphi_version",
                Path(dproj).name,
                project_version,
                target,
                compiler.name,
                actual,
            )

    def _resolve_project_compiler(
        self,
        project_path: str,
        explicit_name: Optional[str],
        platform: TargetPlatform,
        project_settings: Optional[ProjectSettings] = None,
    ) -> tuple[Optional[CompilerConfig], Optional[str], Optional[str]]:
        """解析工程实际使用的编译器。

        优先级：工具显式参数 > 项目配置 ``compiler_version`` > 项目配置
        ``delphi_version`` > 默认编译器。项目配置指定了版本
        但该版本不可用时返回错误，不回退到其它 Delphi 版本。

        Returns:
            ``(compiler_config, compiler_path, error_message)``；正常时
            ``error_message`` 为 None。只有路径没有注册表配置时
            ``compiler_config`` 为 None、``compiler_path`` 有值。
        """
        settings = (
            project_settings
            if project_settings is not None
            else load_project_settings(project_path)
        )
        if settings and settings.error:
            return None, None, settings.error
        self._warn_conflicting_project_versions(settings)
        name = explicit_name or (settings.compiler_version if settings else None)

        if name:
            compiler = self._lookup_compiler_by_name_or_version(name, platform)
            if compiler:
                if settings is None:
                    self._warn_if_direct_compile_version_mismatch(
                        project_path, compiler
                    )
                return compiler, None, None
            version_hint = normalize_version_key(name)
            if version_hint:
                path = self._find_compiler_from_registry(platform, version_hint)
                if path:
                    return None, path, None
            if not explicit_name and settings and settings.delphi_version:
                logger.warning(
                    "项目配置的 compiler_version=%r 不可用，改用 delphi_version=%s",
                    name,
                    settings.delphi_version,
                )
            elif version_hint:
                return None, None, (
                    f"指定的 Delphi 版本 {name!r} 未安装"
                    f"（找不到 {platform.value} 编译器）；不会回退到其它版本"
                )
            else:
                return None, None, (
                    f"指定的编译器 {name!r} 不存在；不会回退到其它 Delphi 版本"
                )

        if settings and settings.delphi_version:
            compiler = self._lookup_compiler_by_version(settings.delphi_version, platform)
            if compiler:
                return compiler, None, None
            path = self._find_compiler_from_registry(platform, settings.delphi_version)
            if path:
                return None, path, None
            return None, None, (
                f"项目配置指定 Delphi {settings.delphi_version}"
                f"（{settings.source}），但未找到该版本的编译器；"
                "不会回退到其它 Delphi 版本"
            )

        config_manager = getattr(self, "config_manager", None)
        getter = getattr(config_manager, "get_effective_compiler", None)
        if callable(getter):
            try:
                compiler = getter(None, platform.value)
            except TypeError:
                compiler = getter(None)
            except Exception:
                logger.warning("获取生效编译器失败", exc_info=True)
                compiler = None
            if compiler:
                if settings is None:
                    self._warn_if_direct_compile_version_mismatch(
                        project_path, compiler
                    )
                return compiler, None, None

        path = self._find_compiler_from_registry(platform)
        return None, path, None

    def _find_msbuild(self, version: Optional[str] = None) -> Optional[str]:
        """查找 MSBuild 可执行文件（自动探测）。

        搜索优先级：
        1. 老版本 Delphi 对应的 .NET Framework MSBuild（指定版本时）
        2. vswhere.exe（VS 2017+ 官方工具，最准确）
        3. %ProgramFiles(x86)%/Microsoft Visual Studio/Installer/vswhere.exe
        4. 常见 VS 安装路径列表（回退方案）
        5. Delphi 安装目录自带的 MSBuild（指定版本优先）
        6. PATH 中的 msbuild.exe

        Args:
            version: Delphi 注册表版本号，用于优先匹配该版本自带的 MSBuild

        Returns:
            MSBuild 路径,如果未找到则返回 None
        """
        return self._auto_find_msbuild(version)

    def _auto_find_msbuild(self, version: Optional[str] = None) -> Optional[str]:
        """自动探测 MSBuild（不含显式配置）。

        Args:
            version: Delphi 注册表版本号，用于优先匹配该版本自带的 MSBuild

        Returns:
            MSBuild 路径,如果未找到则返回 None
        """
        import subprocess

        # 方法0: 老版本 Delphi 依赖 .NET Framework 自带的 MSBuild。
        # XE4 及更早使用 v3.5，XE5–10 Seattle 使用 v4.0.30319；
        # 让 VS2019/2022 的 MSBuild 编译这些工程通常会失败。
        preferred_version = version
        preferred_target = (
            normalize_registry_version(preferred_version) if preferred_version else None
        )
        if preferred_target:
            major = int(preferred_target.split(".")[0])
            if major <= 17:
                framework_version = "v3.5" if major <= 11 else "v4.0.30319"
                windir = os.environ.get("WINDIR", r"C:\Windows")
                framework_msbuild = (
                    Path(windir) / "Microsoft.NET" / "Framework"
                    / framework_version / "MSBuild.exe"
                )
                if framework_msbuild.is_file():
                    logger.info(
                        "Delphi %s 对应 .NET Framework %s，使用 MSBuild: %s",
                        preferred_target,
                        framework_version,
                        framework_msbuild,
                    )
                    return str(framework_msbuild)
                logger.warning(
                    "Delphi %s 通常需要 .NET Framework %s 的 MSBuild，"
                    "但未找到 %s；将继续尝试其它 MSBuild（可能不兼容）",
                    preferred_target,
                    framework_version,
                    framework_msbuild,
                )

        # 方法1: 使用 vswhere.exe 查询最新 VS 的 MSBuild 路径
        vswhere_candidates = []
        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        if program_files_x86:
            vswhere_candidates.append(
                Path(program_files_x86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
            )
        program_files = os.environ.get("ProgramFiles")
        if program_files:
            vswhere_candidates.append(
                Path(program_files) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
            )
        for vswhere in vswhere_candidates:
            if vswhere.exists():
                try:
                    result = subprocess.run(
                        [
                            str(vswhere),
                            "-latest", "-products", "*",
                            "-requires", "Microsoft.Component.MSBuild",
                            "-find", "MSBuild\\**\\Bin\\MSBuild.exe",
                        ],
                        capture_output=True, text=True, timeout=TIMEOUT_MSBUILD_DISCOVERY,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        for line in result.stdout.strip().splitlines():
                            msbuild_path = line.strip()
                            if msbuild_path and Path(msbuild_path).exists():
                                logger.info(f"通过 vswhere 找到 MSBuild: {msbuild_path}")
                                return msbuild_path
                except (subprocess.TimeoutExpired, OSError) as e:
                    logger.debug(f"vswhere 查询失败: {e}")

        # 方法2: 常见 VS 安装路径列表（回退方案）
        editions = ["BuildTools", "Community", "Professional", "Enterprise"]
        years = ["2019", "2022"]
        possible_paths = []
        for year in years:
            for edition in editions:
                base_root = program_files_x86 if year == "2019" else program_files
                if not base_root:
                    continue
                base = Path(base_root)
                possible_paths.append(
                    str(base / f"Microsoft Visual Studio\\{year}\\{edition}\\MSBuild\\Current\\Bin\\MSBuild.exe")
                )

        for path in possible_paths:
            if Path(path).exists():
                logger.info(f"找到 MSBuild: {path}")
                return path

        # 方法3: Delphi/RAD Studio 自带 MSBuild 回退
        # 无 VS 的机器上 vswhere / VS 路径列表都为空时，检查 Delphi 安装目录
        # 是否随附 MSBuild，避免 .dproj 因找不到 MSBuild 而无法编译。
        try:
            delphi_roots = self._read_delphi_roots_from_hive(
                winreg.HKEY_CURRENT_USER, "HKCU"
            )
            delphi_roots.extend(
                self._read_delphi_roots_from_hive(winreg.HKEY_LOCAL_MACHINE, "HKLM")
            )

            # 指定版本优先，避免 XE4 工程误用其它版本目录里的 MSBuild
            preferred_version = version
            if preferred_version:
                preferred_target = normalize_registry_version(preferred_version)
                delphi_roots.sort(
                    key=lambda item: normalize_registry_version(item[0]) != preferred_target
                )

            for _version_key, root_dir in delphi_roots:
                root_path = Path(root_dir)
                candidates = [
                    root_path / "bin" / "MSBuild.exe",
                    root_path / "bin" / "MSBuild" / "Current" / "Bin" / "MSBuild.exe",
                    root_path / "MSBuild.exe",
                    root_path / "msbuild" / "Current" / "Bin" / "MSBuild.exe",
                ]
                for cand in candidates:
                    if cand.exists():
                        logger.info(f"通过 Delphi 安装目录找到 MSBuild: {cand}")
                        return str(cand)
        except Exception as e:
            logger.debug(f"Delphi 自带 MSBuild 搜索失败: {e}")

        # 方法4: PATH 中的 msbuild.exe（兜底，通常不生效，仅做最后尝试）
        try:
            import shutil
            on_path = shutil.which("msbuild.exe") or shutil.which("msbuild")
            if on_path:
                logger.info(f"通过 PATH 找到 MSBuild: {on_path}")
                return on_path
        except Exception as e:
            logger.debug(f"PATH 搜索 msbuild 失败: {e}")

        logger.warning("未找到 MSBuild，将回退到直接编译")
        return None

    def _resolve_msbuild_path(
        self,
        version: Optional[str] = None,
        project_settings: Optional[ProjectSettings] = None,
    ) -> tuple[Optional[str], str, bool]:
        """按优先级解析本次编译应使用的 MSBuild，并返回来源说明。

        优先级（显式配置命中但路径无效时直接失败，不静默换用其它版本）：
        1. 项目配置 ``.daofy/project.json`` / ``daofy.project.json`` 的 ``msbuild_path``
        2. ``compilers.json`` 的 ``msbuild_by_delphi_version[<版本>]``
        3. 自动探测（按工程 Delphi 版本优先 → vswhere → VS → Delphi → PATH）

        Args:
            version: 本次编译解析出的 Delphi 注册表版本号
            project_settings: 项目级配置（可选）

        Returns:
            ``(msbuild_path, source, explicit_error)``；显式配置无效时 path 为
            None、explicit_error 为 True，调用方应直接失败而不是回退到其它
            MSBuild/直接编译。
        """
        explicit: list[tuple[str, str]] = []

        if project_settings and project_settings.msbuild_path:
            explicit.append(
                (project_settings.msbuild_path, f"项目配置 {project_settings.source}")
            )

        config_manager = getattr(self, "config_manager", None)
        version_getter = getattr(config_manager, "get_msbuild_for_version", None)
        if callable(version_getter) and version:
            try:
                mapped = version_getter(version)
            except Exception:
                logger.warning("读取 msbuild_by_delphi_version 失败", exc_info=True)
                mapped = None
            if mapped:
                explicit.append(
                    (
                        mapped,
                        f"compilers.json msbuild_by_delphi_version[{version}]",
                    )
                )

        for raw_path, source in explicit:
            path = Path(raw_path).expanduser()
            if path.is_file():
                logger.info("使用配置指定的 MSBuild (%s): %s", source, path)
                return str(path), source, False
            logger.error(
                "配置的 MSBuild 路径不存在 (%s): %s；"
                "请修正该配置，或删除它以恢复自动探测",
                source,
                raw_path,
            )
            return None, f"{source} 指向的路径不存在: {raw_path}", True

        # 没有任何显式配置时才自动探测。必须按本次工程的 Delphi 版本
        # 重新探测：初始化时缓存的 msbuild_path 是通用探测结果，直接复用
        # 会让另一个版本的工程仍然用错 MSBuild。
        fallback = getattr(self, "msbuild_path", None)
        if fallback and not Path(fallback).is_absolute():
            # 裸文件名（如测试注入的 "MSBuild.exe"）视为调用方显式指定，交给 PATH
            return fallback, "自动探测", False

        version_key = normalize_registry_version(version) if version else None
        if version_key:
            found = self._auto_find_msbuild_cached(version_key)
            if found:
                return found, f"自动探测（按 Delphi {version_key} 优先）", False

        if fallback:
            return fallback, "自动探测", False

        # 初始化时未探测到（或对象由测试直接构造）时再尝试一次
        found = self._auto_find_msbuild_cached(version_key)
        if found:
            return found, "自动探测", False
        return None, "自动探测未找到 MSBuild", False

    def _auto_find_msbuild_cached(self, version_key: Optional[str]) -> Optional[str]:
        """按版本缓存自动探测结果，避免每次编译都启动 vswhere。"""
        cache = getattr(self, "_msbuild_auto_cache", None)
        if cache is None:
            cache = {}
            try:
                self._msbuild_auto_cache = cache
            except AttributeError:  # pragma: no cover - 防御 __slots__ 子类
                pass
        key = version_key or ""
        if key in cache:
            return cache[key]
        found = self._auto_find_msbuild(version_key)
        # 只缓存成功结果：用户后续安装 MSBuild 后无需重启服务
        if found:
            cache[key] = found
        return found

    @staticmethod
    def _version_sort_key(version_key: str) -> tuple:
        """将 ``"11.0"`` 这类注册表版本键转为可比较的数值元组。

        直接按字符串排序会把 ``"9.0"`` 排到 ``"37.0"`` 之后，导致“最新版本”
        选错，因此必须按数值比较。
        """
        try:
            return tuple(int(part) for part in str(version_key).split("."))
        except (TypeError, ValueError):
            return (0,)

    def _read_delphi_roots_from_hive(self, hive, hive_name: str) -> list:
        """读取单个注册表根下的 Delphi 安装（版本, RootDir）。"""
        roots: list = []
        try:
            key = winreg.OpenKey(
                hive,
                REG_KEY_EMBARCADERO_BDS,
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_32KEY,
            )
        except FileNotFoundError:
            logger.debug("注册表 %s\\%s 不存在,跳过", hive_name, REG_KEY_EMBARCADERO_BDS)
            return roots
        except OSError as exc:
            logger.warning("打开注册表 %s\\%s 失败: %s", hive_name, REG_KEY_EMBARCADERO_BDS, exc)
            return roots

        try:
            index = 0
            while True:
                try:
                    version_key = winreg.EnumKey(key, index)
                    index += 1
                except OSError:
                    break

                try:
                    version_path_key = winreg.OpenKey(key, version_key)
                except OSError as exc:
                    logger.debug(
                        "打开 %s\\%s\\%s 失败: %s",
                        hive_name, REG_KEY_EMBARCADERO_BDS, version_key, exc,
                    )
                    continue

                try:
                    root_dir, _ = winreg.QueryValueEx(version_path_key, "RootDir")
                    if root_dir and Path(root_dir).exists():
                        roots.append((version_key, root_dir))
                except OSError:
                    logger.debug("Delphi %s 没有可用的 RootDir", version_key)
                finally:
                    winreg.CloseKey(version_path_key)
        finally:
            winreg.CloseKey(key)
        return roots

    def _get_delphi_root_from_registry(self, version: Optional[str] = None) -> Optional[str]:
        """
        从注册表获取 Delphi 安装根目录

        HKCU 优先、HKLM 兜底。指定版本未安装时返回 None，不再静默回退到
        最新版本——否则指定 XE4 时会拿到 Tokyo/XE8 的安装目录。

        Args:
            version: Delphi 版本号(如 "22.0")，如果为 None 则使用最新版本

        Returns:
            Delphi 安装根目录，如果未找到则返回 None
        """
        try:
            versions = self._read_delphi_roots_from_hive(winreg.HKEY_CURRENT_USER, "HKCU")
            versions.extend(
                self._read_delphi_roots_from_hive(winreg.HKEY_LOCAL_MACHINE, "HKLM")
            )

            if not versions:
                logger.warning("注册表 HKCU/HKLM 均未找到 Delphi 安装")
                return None

            if version:
                target = normalize_registry_version(version)
                for registered_version, root_dir in versions:
                    if normalize_registry_version(registered_version) == target:
                        return root_dir
                logger.warning("注册表中未找到 Delphi %s，不回退到其它版本", version)
                return None

            versions.sort(
                key=lambda item: self._version_sort_key(item[0]),
                reverse=True,
            )
            return versions[0][1]

        except Exception as e:
            logger.warning(f"从注册表获取 Delphi 路径失败: {e}")
            return None

    def _get_rsvars_path(self, version: Optional[str] = None) -> Optional[str]:
        """
        获取 rsvars.bat 路径

        Args:
            version: Delphi 版本号；为 None 时使用最新安装版本

        Returns:
            rsvars.bat 完整路径，如果未找到则返回 None
        """
        root_dir = self._get_delphi_root_from_registry(version)
        if not root_dir and version:
            # 注册表缺失时，用 compilers.json 中该版本的编译器路径反推根目录
            config_manager = getattr(self, "config_manager", None)
            getter = getattr(config_manager, "get_compiler_by_registry_version", None)
            compiler = None
            if callable(getter):
                try:
                    compiler = getter(version)
                except Exception:
                    logger.debug("按版本查找编译器配置失败: %s", version, exc_info=True)
            if compiler and compiler.path:
                root_dir = str(Path(compiler.path).parent.parent)
                logger.info(
                    "注册表未找到 Delphi %s，改用编译器配置推断根目录: %s",
                    version,
                    root_dir,
                )

        if not root_dir:
            logger.error("无法从注册表获取 Delphi 安装路径")
            return None

        rsvars_path = Path(root_dir) / "bin" / "rsvars.bat"
        if rsvars_path.exists():
            logger.info(f"找到 rsvars.bat: {rsvars_path}")
            return str(rsvars_path)
        else:
            logger.error(f"rsvars.bat 不存在: {rsvars_path}")
            return None

    def _get_effective_delphi_root(self, version: Optional[str] = None) -> Optional[str]:
        """获取当前生效的 Delphi 安装根目录。

        Args:
            version: 指定 Delphi 注册表版本（如 ``"11.0"``）；为 None 时使用
                最新安装版本。包安装/ BPL 查找传入项目配置的版本即可避免与
                其它版本混用。

        Returns:
            Delphi 安装根目录，未找到时返回 None
        """
        root_dir = self._get_delphi_root_from_registry(version)
        if root_dir:
            return root_dir

        # 注册表不可用（手动配置编译器/绿色版）时，从编译器路径反推根目录
        config_manager = getattr(self, "config_manager", None)
        compiler = None
        if version:
            compiler = self._lookup_compiler_by_version(version, TargetPlatform.WIN32)
        else:
            getter = getattr(config_manager, "get_effective_compiler", None)
            if callable(getter):
                try:
                    compiler = getter(None, "win32")
                except Exception:
                    logger.warning("获取生效编译器失败", exc_info=True)
        if compiler and compiler.path:
            inferred = str(Path(compiler.path).parent.parent)
            logger.info(
                "注册表未找到 Delphi %s，改用编译器配置推断根目录: %s",
                version or "默认版本",
                inferred,
            )
            return inferred
        return None

    def _check_process_running(self, process_name: str) -> Optional[dict]:
        """
        检查指定进程是否正在运行
        
        Args:
            process_name: 进程名称（不含.exe扩展名）
            
        Returns:
            如果进程正在运行，返回包含进程信息的字典；否则返回 None
        """
        import subprocess
        import json
        import re
        
        if not re.match(r'^[A-Za-z0-9_.-]+$', process_name):
            logger.warning("进程名包含非法字符，已拒绝: %s", process_name)
            return None
        
        try:
            result = subprocess.run(
                ['powershell', '-Command',
                 "Get-Process -Name '%s' -ErrorAction SilentlyContinue | "
                 "Select-Object Id, ProcessName, Path | ConvertTo-Json" % process_name],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_PROCESS_QUERY,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )
            
            if result.returncode == 0 and result.stdout.strip():
                output = result.stdout.strip()
                
                if output.startswith('['):
                    processes = json.loads(output)
                    if processes:
                        proc = processes[0]
                    else:
                        return None
                elif output.startswith('{'):
                    proc = json.loads(output)
                else:
                    return None
                
                logger.info("检测到进程正在运行: %s (PID: %s)", proc.get('ProcessName'), proc.get('Id'))
                return {
                    'pid': proc.get('Id'),
                    'name': proc.get('ProcessName'),
                    'path': proc.get('Path')
                }
            
            return None
            
        except Exception as e:
            logger.warning("检查进程时发生错误: %s", str(e))
            return None

    def _cleanup_dcu_files(self, file_path: str):
        """
        清理源文件所在目录的 .dcu 文件
        
        Args:
            file_path: 源文件路径
        """
        import glob
        
        file_path_obj = Path(file_path)
        file_dir = file_path_obj.parent
        
        if not file_dir.exists():
            return
        
        dcu_pattern = str(file_dir / "*.dcu")
        dcu_files = glob.glob(dcu_pattern)
        
        if dcu_files:
            logger.info(f"在 {file_dir} 中找到 {len(dcu_files)} 个 .dcu 文件")
            
            total_deleted = 0
            for dcu_file in dcu_files:
                try:
                    os.unlink(dcu_file)
                    logger.debug(f"已删除: {dcu_file}")
                    total_deleted += 1
                except Exception as e:
                    logger.warning(f"删除失败 {dcu_file}: {str(e)}")
            
            if total_deleted > 0:
                logger.info(f"共删除 {total_deleted} 个 .dcu 文件")

    def _execute_build_event(self, event_name: str, event_cmd: str, project_dir: str, 
                            ignore_exit_code: bool = False, timeout: int = 60,
                            context: dict = None) -> tuple:
        """
        执行编译事件

        Args:
            event_name: 事件名称(用于日志)
            event_cmd: 事件命令
            project_dir: 项目目录
            ignore_exit_code: 是否忽略退出码
            timeout: 超时时间(秒)
            context: 上下文变量字典,包含项目信息等

        Returns:
            (success, error_message, output) 元组
        """
        import subprocess
        import tempfile
        import re
        
        logger.info("执行 %s: %s", event_name, event_cmd[:200])
        
        _DANGEROUS_PATTERNS = re.compile(
            r'(?:^|\b)(?:rm\s+/|del\s+/[sq]|format\s+[a-z]:|net\s+user|'
            r'reg(?:edit(?:32)?|\.exe)?\s+add|powershell\s+-enc|'
            r'cmd(?:\.exe)?\s+/c\s*(?:curl|wget|bitsadmin))',
            re.IGNORECASE
        )
        if _DANGEROUS_PATTERNS.search(event_cmd):
            error_msg = "%s 命令包含危险模式，已拒绝执行: %s" % (event_name, event_cmd[:200])
            logger.error(error_msg)
            return (False, error_msg, None)
        
        # 替换 Delphi 支持的变量
        if context:
            # 项目相关变量
            event_cmd = event_cmd.replace('$(PROJECTDIR)', context.get('project_dir', project_dir))
            event_cmd = event_cmd.replace('$(PROJECTPATH)', context.get('project_path', ''))
            event_cmd = event_cmd.replace('$(PROJECTFILENAME)', context.get('project_filename', ''))
            event_cmd = event_cmd.replace('$(PROJECTNAME)', context.get('project_name', ''))
            
            # 输入文件相关变量
            event_cmd = event_cmd.replace('$(INPUTPATH)', context.get('input_path', ''))
            event_cmd = event_cmd.replace('$(INPUTFILENAME)', context.get('input_filename', ''))
            event_cmd = event_cmd.replace('$(INPUTEXT)', context.get('input_ext', ''))
            
            # 输出文件相关变量
            event_cmd = event_cmd.replace('$(OUTPUTDIR)', context.get('output_dir', ''))
            event_cmd = event_cmd.replace('$(OUTPUTPATH)', context.get('output_path', ''))
            event_cmd = event_cmd.replace('$(OUTPUTFILENAME)', context.get('output_filename', ''))
            event_cmd = event_cmd.replace('$(OUTPUTEXT)', context.get('output_ext', ''))
            
            # 配置相关变量
            event_cmd = event_cmd.replace('$(Config)', context.get('config', 'Debug'))
            event_cmd = event_cmd.replace('$(Platform)', context.get('platform', 'Win32'))
            event_cmd = event_cmd.replace('$(DEFINES)', context.get('defines', ''))
            
            # 路径相关变量
            event_cmd = event_cmd.replace('$(DIR)', context.get('dir', project_dir))
            event_cmd = event_cmd.replace('$(INCLUDEPATH)', context.get('include_path', ''))
            event_cmd = event_cmd.replace('$(PATH)', context.get('path', ''))
            
            # Delphi 环境变量
            event_cmd = event_cmd.replace('$(BDS)', context.get('bds', ''))
            event_cmd = event_cmd.replace('$(LOCALCOMMAND)', context.get('local_command', ''))
            
            # 系统变量
            event_cmd = event_cmd.replace('$(SystemRoot)', context.get('system_root', ''))
            event_cmd = event_cmd.replace('$(WINDIR)', context.get('windir', ''))
        
        # 兼容旧版本的变量替换
        event_cmd = event_cmd.replace('$(PROJECTDIR)', project_dir)
        
        try:
            logger.warning("编译事件来自 .dproj 文件配置，请确保项目文件可信")
            # 使用控制台编码（可能为 UTF-8 或 GBK），确保 cmd.exe 正确读取中文路径
            batch_encoding = get_console_encoding()
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.bat', delete=False, encoding=batch_encoding
            ) as bat_f:
                bat_f.write('@echo off\n')
                bat_f.write(event_cmd + '\n')
                bat_path = bat_f.name
            
            try:
                result = subprocess.run(
                    ['cmd.exe', '/c', bat_path],
                    cwd=project_dir,
                    capture_output=True,
                    encoding=get_console_encoding(),
                    timeout=timeout,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
            finally:
                try:
                    os.unlink(bat_path)
                except OSError:
                    pass
            
            if result.returncode != 0 and not ignore_exit_code:
                error_msg = "%s 失败(退出码 %d): %s" % (event_name, result.returncode, result.stderr)
                logger.error(error_msg)
                return (False, error_msg, result.stdout + result.stderr)
            
            logger.info("%s 执行成功", event_name)
            if result.stdout:
                logger.debug("%s 输出: %s", event_name, result.stdout)
            
            return (True, None, result.stdout + result.stderr)
            
        except subprocess.TimeoutExpired:
            error_msg = "%s 执行超时(%d秒)" % (event_name, timeout)
            logger.error(error_msg)
            return (False, error_msg, None)
        except Exception as e:
            error_msg = "%s 执行失败: %s" % (event_name, str(e))
            logger.error(error_msg, exc_info=True)
            return (False, error_msg, None)

    def _extract_config_from_dproj(self, project_path: str, options: 'CompileOptions') -> 'CompileOptions':
        """
        从 .dproj 文件中提取配置

        Args:
            project_path: 项目文件路径(.dproj 或 .dpr)
            options: 原始编译选项

        Returns:
            合并后的编译选项
        """
        # 如果传入的是 .dpr/.dpk 文件,查找对应的 .dproj 文件
        if project_path.endswith('.dpr') or project_path.endswith('.dpk'):
            ext = '.dpr' if project_path.endswith('.dpr') else '.dpk'
            dproj_path = project_path[:-len(ext)] + '.dproj'
            if not Path(dproj_path).exists():
                logger.info(f"未找到对应的 .dproj 文件: {dproj_path}")
                return options
        elif project_path.endswith('.dproj'):
            dproj_path = project_path
        else:
            return options

        # 解析 .dproj 文件
        parser = DprojParser(dproj_path)
        if not parser.parse():
            logger.warning(f"解析 .dproj 文件失败: {dproj_path}")
            return options

        # 获取配置和平台
        config = options.build_configuration
        platform = "Win64" if options.target_platform == TargetPlatform.WIN64 else "Win32"

        # 提取单元搜索路径
        # 1. 先获取基础路径(不限制配置和平台)
        base_unit_paths = parser.get_unit_search_paths()
        # 2. 再获取平台特定路径
        platform_unit_paths = parser.get_unit_search_paths(config, platform)
        # 3. 合并所有路径
        dproj_unit_paths = base_unit_paths + platform_unit_paths
        
        if dproj_unit_paths:
            # 合并用户指定的路径和 .dproj 中的路径
            all_paths = list(options.unit_search_paths) + dproj_unit_paths
            # 去重
            options.unit_search_paths = list(dict.fromkeys(all_paths))
            logger.info(f"从 .dproj 文件中提取了 {len(dproj_unit_paths)} 个单元搜索路径")

        # 提取条件编译符号
        dproj_defines = parser.get_conditional_defines(config, platform)
        if dproj_defines:
            all_defines = list(options.conditional_defines) + dproj_defines
            options.conditional_defines = list(dict.fromkeys(all_defines))
            logger.info(f"从 .dproj 文件中提取了 {len(dproj_defines)} 个条件编译符号")

        # 提取输出路径
        if not options.output_path:
            dproj_output = parser.get_output_path(config, platform)
            if dproj_output:
                options.output_path = dproj_output
                logger.info(f"从 .dproj 文件中提取了输出路径: {dproj_output}")

        # 智能解析第三方库路径
        # 注意：如果用户显式传入了 unit_search_paths，resolver 会直接返回，不会进行智能分析
        try:
            logger.info("开始解析第三方库路径...")
            resolver = SmartLibraryPathResolver()
            
            # 解析 registry_version（与 RTL 库搜索路径共用同一策略），
            # 使第三方库路径按同一 Delphi 版本过滤注册表，避免跨版本混入。
            from ..utils.delphi_versions import resolve_registry_version
            project_settings = load_project_settings(project_path)
            resolver_compiler = options.compiler_version
            if not resolver_compiler and project_settings:
                resolver_compiler = project_settings.compiler_version
            resolver_version = resolve_registry_version(
                resolver_compiler,
                parser.get_project_version(),
                self.config_manager,
                override_version=(
                    project_settings.delphi_version if project_settings else None
                ),
            )
            
            # 传入用户显式指定的路径，resolver 会判断是否跳过智能分析
            user_provided_paths = list(options.unit_search_paths) if options.unit_search_paths else None
            resolved_paths, info = resolver.resolve_library_paths(
                project_path, 
                platform,
                user_search_paths=user_provided_paths,
                version=resolver_version,
            )
            
            if info.get("mode") == "user_provided":
                logger.info(f"使用用户显式传入的 {len(resolved_paths)} 个路径")
            elif resolved_paths:
                options.unit_search_paths = resolved_paths
                logger.info(f"智能解析选择了 {len(resolved_paths)} 个第三方库路径"
                           f"（从 {info.get('total_paths_count', 0)} 个全局路径中筛选，"
                           f"解决了 {info.get('resolved_units', 0)} 个单元依赖）")
                logger.debug(f"解析详情: {info}")
            
            # 记录未找到的单元
            if info.get('still_missing_units'):
                logger.warning(f"仍有 {len(info['still_missing_units'])} 个单元未找到: "
                             f"{info['still_missing_units'][:5]}")
                
        except Exception as e:
            logger.warning(f"智能解析第三方库路径失败: {e}，将使用默认方式")

        return options

    async def compile_dpr_direct(self, request: ProjectCompileRequest) -> CompileResult:
        """
        直接使用 dcc32/dcc64 编译 .dpr 文件（不依赖 .dproj）

        Args:
            request: 工程编译请求

        Returns:
            编译结果
        """
        logger.info(f"直接编译 .dpr 文件: {request.project_path}")
        start_time = time.time()

        # dcc 直编只支持 .dpr/.dpk，.dproj 必须走 MSBuild
        if request.project_path.lower().endswith('.dproj'):
            error_msg = ".dproj 文件不能通过 dcc 直接编译，必须使用 MSBuild"
            logger.error(error_msg)
            return CompileResult(
                status=CompileStatus.FAILED,
                error_code="DPROJ_REQUIRES_MSBUILD",
                error_message=error_msg,
                duration=0
            )

        try:
            # 1. 验证项目路径
            is_valid, error_msg = self.validator.validate_project_path(request.project_path)
            if not is_valid:
                logger.error(f"项目路径验证失败: {error_msg}")
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_PROJECT_PATH",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 1.5 从同目录 .dproj 提取配置（条件编译符号/搜索路径/输出路径）
            # 直接 DCC 编译不会自动读取 .dproj，需手动合并该配置的 DCC_Define，
            # 否则默认配置（如 Debug）的条件编译符号不会生效，编出的 exe 是 "plain"
            try:
                self._extract_config_from_dproj(request.project_path, request.options)
            except Exception as e:
                logger.debug("从 .dproj 提取配置失败（继续直接编译）: %s", e)

            # 2. 确定输出路径 - 默认输出到 Win32/Debug 子目录
            project_dir = str(Path(request.project_path).parent)
            project_name = Path(request.project_path).stem

            if request.options.output_path:
                output_base = request.options.output_path
            else:
                # 优先从同目录 .dproj 读取 DCC_ExeOutput
                dproj_path = Path(request.project_path).with_suffix('.dproj')
                dproj_output = None
                if dproj_path.exists():
                    try:
                        from ..utils.dproj_parser import DprojParser
                        parser = DprojParser(str(dproj_path))
                        if parser.parse():
                            plat_map = {"win32": "Win32", "win64": "Win64"}
                            plat_dir = plat_map.get(request.options.target_platform.lower(), "Win32")
                            cfg = request.options.build_configuration or "Debug"
                            dproj_output = parser.get_output_path(config=cfg, platform=plat_dir)
                    except Exception:
                        logger.debug("读取 .dproj DCC_ExeOutput 失败，使用默认路径")

                if dproj_output:
                    output_base = dproj_output
                else:
                    from ..services.args_generator import ArgsGenerator
                    lib_dir = ArgsGenerator._PLATFORM_LIB_DIR.get(request.options.target_platform, 'Win32')
                    cfg = request.options.build_configuration or "Debug"
                    output_base = str(Path(project_dir) / lib_dir / cfg)

            # 确保输出目录存在
            Path(output_base).mkdir(parents=True, exist_ok=True)

            # 3. 获取编译器配置（显式版本 > 项目配置 > 默认编译器）
            # 项目级配置（.daofy/project.json）优先，保证同一台机器上不同工程
            # 使用各自声明的 Delphi 版本，且项目指定版本缺失时直接失败不静默回退。
            project_settings = load_project_settings(request.project_path)
            if project_settings and project_settings.error:
                logger.error(project_settings.error)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="PROJECT_CONFIG_INVALID",
                    error_message=project_settings.error,
                    duration=int((time.time() - start_time) * 1000),
                )
            compiler_config, compiler_path, compiler_error = self._resolve_project_compiler(
                request.project_path,
                request.options.compiler_version,
                request.options.target_platform,
                project_settings,
            )
            if compiler_error:
                logger.error(compiler_error)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="COMPILER_NOT_FOUND",
                    error_message=compiler_error,
                    duration=int((time.time() - start_time) * 1000)
                )
            if compiler_config:
                compiler_path = compiler_config.path
            if not compiler_path:
                error_msg = "未配置默认编译器且无法自动查找"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="COMPILER_NOT_FOUND",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 4. 根据目标平台选择编译器
            target_platform = request.options.target_platform
            if target_platform != TargetPlatform.WIN32:
                compiler_name = self._get_platform_compiler_name(target_platform)
                bin_dir = Path(compiler_path).parent
                target_compiler = str(bin_dir / compiler_name)
                if Path(target_compiler).exists():
                    compiler_path = target_compiler
                    logger.info(f"切换到 {target_platform.value} 编译器: {compiler_path}")
                else:
                    # 跨平台编译器不存在，回退查找（优先使用当前编译器版本）
                    fallback_version = (
                        compiler_config.registry_version
                        if compiler_config
                        else (project_settings.delphi_version if project_settings else None)
                    )
                    found = self._find_compiler_from_registry(
                        target_platform,
                        fallback_version,
                    )
                    if found:
                        compiler_path = found
                        logger.info(f"从注册表找到 {target_platform.value} 编译器: {compiler_path}")
                    else:
                        logger.warning(f"{target_platform.value} 编译器 ({compiler_name}) 未找到，尝试使用 dcc32")

            # 5. 验证编译器路径
            is_valid, error_msg = self.validator.validate_compiler_path(compiler_path)
            if not is_valid:
                logger.error(f"编译器路径验证失败: {error_msg}")
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_COMPILER_PATH",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 6. 检查目标程序是否正在运行
            running_process = self._check_process_running(project_name)
            if running_process:
                error_msg = f"目标程序 '{project_name}.exe' 正在运行 (PID: {running_process['pid']})，无法编译。请先关闭程序后再试。"
                logger.warning(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="PROCESS_RUNNING",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000),
                    log=f"进程信息: PID={running_process['pid']}, 路径={running_process.get('path', '未知')}"
                )

            # 7. 生成命令行参数
            args = self._generate_dpr_args(request.project_path, request.options, output_base, compiler_path)

            # 8. 验证参数
            if not self.args_generator.validate_args(args):
                logger.error("参数验证失败")
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_ARGS",
                    error_message="编译参数包含非法字符",
                    duration=int((time.time() - start_time) * 1000)
                )

            logger.info(f"编译命令: {compiler_path} {' '.join(args)}")

            # 9. 执行编译
            try:
                return_code, stdout, stderr = await self.process_manager.execute(
                    compiler_path,
                    args,
                    request.options.timeout
                )

                # 10. 解析输出
                errors = self.output_parser.parse_errors(stdout + stderr)
                warnings = self.output_parser.parse_warnings(stdout + stderr)

                # 11. 构建结果
                duration = int((time.time() - start_time) * 1000)
                output_file = str(Path(output_base) / f"{project_name}.exe")

                if return_code == 0:
                    output_files = self._collect_output_files(
                        request.project_path,
                        request.options.target_platform.value,
                        request.options.build_configuration or "Debug",
                        output_base,
                    )
                    result = CompileResult(
                        status=CompileStatus.SUCCESS,
                        output_file=output_file,
                        output_files=output_files,
                        warnings=warnings,
                        errors=errors,
                        duration=duration,
                        log=stdout + stderr
                    )
                    logger.info(f"编译成功,输出文件: {output_file},耗时 {duration}ms")
                else:
                    result = CompileResult(
                        status=CompileStatus.FAILED,
                        error_code="COMPILATION_FAILED",
                        error_message=self.output_parser.extract_error_summary(stdout + stderr),
                        warnings=warnings,
                        errors=errors,
                        duration=duration,
                        log=stdout + stderr
                    )
                    logger.error(f"编译失败,耗时 {duration}ms")

                # 12. 保存编译历史
                self._save_history(request.project_path, result.status.value, duration, result.error_message)

                return result

            except TimeoutError as e:
                duration = int((time.time() - start_time) * 1000)
                logger.error(f"编译超时: {str(e)}")
                result = CompileResult(
                    status=CompileStatus.TIMEOUT,
                    error_code="COMPILATION_TIMEOUT",
                    error_message=str(e),
                    duration=duration
                )
                self._save_history(request.project_path, result.status.value, duration, str(e))
                return result

        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            error_msg = f"直接编译过程发生异常: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result = CompileResult(
                status=CompileStatus.FAILED,
                error_code="INTERNAL_ERROR",
                error_message=error_msg,
                duration=duration
            )
            self._save_history(request.project_path, result.status.value, duration, error_msg)
            return result

    def _generate_dpr_args(self, project_path: str, options: 'CompileOptions', output_base: str,
                           compiler_path: Optional[str] = None) -> list[str]:
        """生成 .dpr 文件的直接编译参数

        Args:
            project_path: .dpr 文件路径
            options: 编译选项
            output_base: 输出目录（存放 .exe 文件）
            compiler_path: 实际选定的 dcc32/dcc64 编译器路径（用于注册表不可用时
                从编译器自身目录推导 RTL 库搜索路径，保证 -U 总能发出）
        """
        from ..utils.delphi_env import (
            expand_delphi_path_macros,
            get_delphi_library_paths,
            get_delphi_root_dir,
        )

        args = []

        # 项目文件
        args.append(project_path)

        # 输出目录（存放 .exe 文件）
        args.append(f'-E{output_base}')

        # 中间文件目录（存放 .dcu 文件）
        dcu_dir = None
        dproj_path_dcu = Path(project_path).with_suffix('.dproj')
        project_version = None  # .dproj <ProjectVersion>，用于推断 registry_version
        if dproj_path_dcu.exists():
            try:
                from ..utils.dproj_parser import DprojParser
                parser = DprojParser(str(dproj_path_dcu))
                if parser.parse():
                    plat_map = {"win32": "Win32", "win64": "Win64"}
                    plat_dir = plat_map.get(options.target_platform.lower(), "Win32")
                    cfg = options.build_configuration or "Debug"
                    dcu_dir = parser.get_dcu_output_path(config=cfg, platform=plat_dir)
                    project_version = parser.get_project_version()
            except Exception:
                logger.debug("读取 .dproj DCC_DcuOutput 失败，使用默认路径")
        if not dcu_dir:
            dcu_dir = output_base
        args.append(f'-N{dcu_dir}')

        # 条件编译符号（注意：defines 语法是 -D，-$D+ 是调试信息开关，二者不可混用）
        if options.conditional_defines:
            defines = ";".join(options.conditional_defines)
            args.append(f'-D{defines}')

        # 命名空间搜索路径 - 默认添加 System 等 RTL/VCL 命名空间，
        # 并合并同目录 .dproj 的 DCC_Namespace（与 compile_file 单文件路径一致），
        # 使 uses SysUtils、uses Classes 等短单元名能解析到 System.SysUtils 等
        default_namespaces = ["System", "Winapi", "System.Win", "Vcl", "Vcl.Imaging",
                              "Vcl.Touch", "Vcl.Samples", "Vcl.Shell", "Data", "Datasnap",
                              "Web", "Soap", "Xml",
                              "Common", "Protocol", "Engine", "Security", "Transport",
                              "Integration", "Platforms"]
        project_namespaces: list[str] = []
        if dproj_path_dcu and dproj_path_dcu.exists():
            try:
                from ..utils.dproj_parser import DprojParser
                ns_parser = DprojParser(str(dproj_path_dcu))
                if ns_parser.parse():
                    project_namespaces = ns_parser.get_namespace() or []
            except Exception:
                logger.debug("读取 .dproj DCC_Namespace 失败，仅使用默认命名空间")
        if project_namespaces:
            namespaces = list(dict.fromkeys(project_namespaces + default_namespaces))
        else:
            namespaces = default_namespaces
        args.append('-NS' + ";".join(namespaces))

        # 单元搜索路径 - 如果未提供，则自动获取 Delphi 默认库搜索路径
        unit_paths = options.unit_search_paths if options.unit_search_paths else []
        if not unit_paths:
            # 自动获取 Delphi 库搜索路径
            # 使用目标平台名（首字母大写，用于注册表查询）
            from ..services.args_generator import ArgsGenerator
            platform = ArgsGenerator._PLATFORM_LIB_DIR.get(options.target_platform, 'Win32')
            # 获取编译器对应的 Delphi 版本号（registry_version），用于读取该版本的搜索路径
            # 与第三方库路径解析共用 resolve_registry_version，保证两处版本过滤策略一致
            from ..utils.delphi_versions import resolve_registry_version
            settings = load_project_settings(project_path)
            resolver_compiler = options.compiler_version
            if not resolver_compiler and settings:
                resolver_compiler = settings.compiler_version
            registry_version = resolve_registry_version(
                resolver_compiler,
                project_version,
                self.config_manager,
                override_version=settings.delphi_version if settings else None,
            )
            # 手动配置的编译器可能没有 registry_version：从安装路径/编译器输出推断
            if not registry_version and compiler_path:
                for parent in Path(compiler_path).parents:
                    inferred = project_version_to_registry_version(parent.name)
                    if inferred:
                        registry_version = inferred
                        break
                if not registry_version:
                    registry_version = detect_registry_version_from_compiler(
                        compiler_path
                    )
            delphi_lib_paths = get_delphi_library_paths(version=registry_version, platform=platform)
            # 展开路径中的宏变量
            for p in delphi_lib_paths:
                expanded = expand_delphi_path_macros(p, version=registry_version, platform=platform)
                if expanded and expanded not in unit_paths:
                    unit_paths.append(expanded)

            # 兜底：注册表/版本解析失败（如无 .dproj 且编译器为手动配置、不在注册表）时，
            # delphi_lib_paths 可能为空。dcc32 不像 IDE 那样有内置默认库搜索路径，
            # 若完全不发 -U，则 uses SysUtils/Classes 等 RTL 单元无法解析导致编译失败。
            # 因此从编译器自身目录推导 RTL 路径：<root>/lib/<platform>/release。
            if not unit_paths:
                rtl_candidates: list[str] = []
                # 1. 从 dcc32/dcc64 所在目录推导（bin/ 的上一级是 Delphi 根目录）
                if compiler_path:
                    compiler_root = Path(compiler_path).resolve().parent.parent
                    rtl_candidates.append(str(compiler_root / "lib" / platform / "release"))
                    rtl_candidates.append(str(compiler_root / "lib" / "win32" / "release"))
                # 2. 尝试从注册表根目录推导
                try:
                    root_dir = get_delphi_root_dir(registry_version) if registry_version else None
                    if not root_dir:
                        root_dir = get_delphi_root_dir()
                    if root_dir:
                        rtl_candidates.append(str(Path(root_dir) / "lib" / platform / "release"))
                except Exception:
                    logger.debug("从注册表根目录推导 RTL 路径失败")
                for cand in rtl_candidates:
                    cand_path = Path(cand)
                    if cand_path.is_dir() and str(cand_path).lower() not in {
                            p.lower() for p in unit_paths}:
                        unit_paths.append(str(cand_path))
                        logger.info("从编译器/注册表目录推导 RTL 单元搜索路径: %s", cand_path)
        
        if unit_paths:
            paths = ";".join(unit_paths)
            args.append(f'-U{paths}')

        # 资源搜索路径
        if options.resource_search_paths:
            paths = ";".join(options.resource_search_paths)
            args.append(f'-R{paths}')

        # 优化选项
        if options.optimize:
            args.append('-$O+')
        else:
            args.append('-$O-')

        # 调试信息
        if options.debug:
            args.append('-$D+')
        else:
            args.append('-$D-')

        # 警告级别
        args.append(f'-$W{options.warning_level}')

        # 禁用警告
        for warning in options.disabled_warnings:
            args.append(f'-$W-{warning}')

        # 输出类型
        output_type_map = {
            OutputType.CONSOLE: "-CC",
            OutputType.GUI: "-CG",
            OutputType.DLL: "-LD"
        }
        args.append(output_type_map[options.output_type])

        # 运行时库
        if options.runtime_library == RuntimeLibrary.DYNAMIC:
            args.append('-$Y+')
        else:
            args.append('-$Y-')

        logger.debug(f"生成的 .dpr 编译参数: {' '.join(args)}")
        return args

    @staticmethod
    @staticmethod
    def _get_platform_compiler_name(platform: TargetPlatform) -> str:
        """根据目标平台返回编译器可执行文件名"""
        _PLATFORM_COMPILER_MAP = {
            TargetPlatform.WIN32: 'dcc32.exe',
            TargetPlatform.WIN64: 'dcc64.exe',
            TargetPlatform.OSX64: 'dccosx64.exe',
            TargetPlatform.OSXARM64: 'dccosxarm64.exe',
            TargetPlatform.IOSDEVICE64: 'dcciosarm64.exe',
            TargetPlatform.IOSDEVICE: 'dcciosarm64.exe',
            TargetPlatform.IOSSIMULATOR: 'dcciosarm64.exe',
            TargetPlatform.ANDROID: 'dccaarm.exe',
            TargetPlatform.ANDROID64: 'dccaac64.exe',
            TargetPlatform.LINUX64: 'dcclinux64.exe',
        }
        return _PLATFORM_COMPILER_MAP.get(platform, 'dcc32.exe')

    def _find_compiler_from_registry(
        self,
        platform: TargetPlatform,
        version: Optional[str] = None,
    ) -> Optional[str]:
        """从注册表查找指定平台的编译器路径

        Args:
            platform: 目标平台
            version: Delphi 注册表版本号；为 None 时使用最新安装版本
        """
        root_dir = self._get_delphi_root_from_registry(version)
        if not root_dir:
            return None

        compiler_name = self._get_platform_compiler_name(platform)
        compiler_path = Path(root_dir) / "bin" / compiler_name
        if compiler_path.exists():
            return str(compiler_path)

        return None

    def _find_dcc32_from_registry(self) -> Optional[str]:
        """从注册表查找 dcc32.exe 路径（向后兼容）"""
        return self._find_compiler_from_registry(TargetPlatform.WIN32)

    @staticmethod
    def _parse_msbuild_property(argument: str) -> Optional[tuple[str, str]]:
        """Parse one MSBuild property argument using any supported prefix."""
        lowered = argument.lower()
        for prefix in ("/p:", "-p:", "/property:", "-property:"):
            if not lowered.startswith(prefix):
                continue
            assignment = argument[len(prefix):]
            if "=" not in assignment:
                return None
            name, value = assignment.split("=", 1)
            if not name:
                return None
            return name.lower(), value
        return None

    def _resolve_msbuild_registry_version(
        self,
        request: ProjectCompileRequest,
        parser: DprojParser,
        project_parsed: bool,
        project_settings: Optional[ProjectSettings] = None,
    ) -> Optional[str]:
        """Resolve the one Delphi registry version used by an MSBuild run.

        Priority: explicit compiler version > project settings (compiler_version /
        delphi_version) > .dproj ProjectVersion inference.
        """
        if project_settings is None:
            project_settings = load_project_settings(request.project_path)

        if project_settings and project_settings.error:
            logger.error(project_settings.error)
            return None

        self._warn_conflicting_project_versions(project_settings)
        explicit_compiler = request.options.compiler_version
        project_compiler = project_settings.compiler_version if project_settings else None
        compiler_version = explicit_compiler or project_compiler

        if compiler_version:
            compiler = None
            compiler_getter = getattr(self.config_manager, "get_compiler", None)
            if callable(compiler_getter):
                try:
                    compiler = compiler_getter(compiler_version)
                except Exception:
                    logger.warning(
                        "查找编译器配置失败: %s", compiler_version, exc_info=True
                    )
            if compiler and compiler.registry_version:
                return compiler.registry_version
            if compiler and compiler.path:
                for parent in Path(compiler.path).parents:
                    registry_version = project_version_to_registry_version(parent.name)
                    if registry_version:
                        logger.info(
                            "从编译器路径推断 registry_version: %s -> %s",
                            compiler.path,
                            registry_version,
                        )
                        return registry_version
                registry_version = detect_registry_version_from_compiler(compiler.path)
                if registry_version:
                    logger.info(
                        "从编译器输出推断 registry_version: %s -> %s",
                        compiler.path,
                        registry_version,
                    )
                    return registry_version

            # 兼容把版本号/产品名直接写进 compiler_version（如 "11.0"、"XE4"）
            version_hint = normalize_version_key(compiler_version)
            if version_hint:
                logger.info(
                    "compiler_version=%r 按 Delphi 版本解释为 registry_version=%s",
                    compiler_version,
                    version_hint,
                )
                return version_hint

            # 项目配置里的 compiler_version 写错时，delphi_version 仍可作为
            # 明确的版本声明；工具调用显式传入的错误值则直接失败，避免掩盖问题。
            if (
                not explicit_compiler
                and project_settings
                and project_settings.delphi_version
            ):
                logger.warning(
                    "项目配置的 compiler_version=%r 无法解析，改用 delphi_version=%s",
                    compiler_version,
                    project_settings.delphi_version,
                )
                return project_settings.delphi_version

            logger.error(
                "无法确定显式编译器 %s 的 registry_version，拒绝回退到其他 Delphi 版本",
                compiler_version,
            )
            return None

        if project_settings and project_settings.delphi_version:
            project_version = parser.get_project_version() if project_parsed else None
            logger.info(
                "使用项目配置 %s 的 delphi_version=%s（忽略 .dproj ProjectVersion=%s）",
                project_settings.source,
                project_settings.delphi_version,
                project_version or "未知",
            )
            return project_settings.delphi_version

        if project_parsed:
            project_version = parser.get_project_version()
            if project_version:
                registry_version = project_version_to_registry_version(project_version)
                if registry_version:
                    return registry_version

        logger.warning(
            "无法确定工程对应的 Delphi registry_version；"
            "将沿用 rsvars 默认选择并跳过 EnvOptions 兼容处理"
        )
        return None

    @staticmethod
    def _write_env_options_overlay(
        status: EnvOptionsLibraryStatus,
        platform: str,
    ) -> str:
        """Write a short-lived EnvOptions overlay for an MSBuild invocation."""
        content = build_env_options_overlay(
            status.env_options_path,
            status.registry_paths,
            platform,
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".proj",
            prefix="daofy-envoptions-",
            delete=False,
            encoding="utf-8",
            newline="\n",
        ) as overlay:
            overlay.write(content)
            return overlay.name

    @staticmethod
    def _remove_temp_file(file_path: Optional[str]) -> None:
        """Remove a compiler temporary file without hiding cleanup failures."""
        if not file_path:
            return
        try:
            os.unlink(file_path)
        except FileNotFoundError:
            return
        except OSError as exc:
            logger.warning("删除临时文件失败 %s: %s", file_path, exc)

    async def compile_project_with_msbuild(self, request: ProjectCompileRequest) -> CompileResult:
        """
        使用 MSBuild 编译 Delphi 工程
        
        Args:
            request: 工程编译请求
            
        Returns:
            编译结果
        """
        logger.info(f"使用 MSBuild 编译工程: {request.project_path}")
        start_time = time.time()
        batch_file: Optional[str] = None
        env_options_overlay: Optional[str] = None
        
        try:
            # 1. 验证项目路径
            is_valid, error_msg = self.validator.validate_project_path(request.project_path)
            if not is_valid:
                logger.error(f"项目路径验证失败: {error_msg}")
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_PROJECT_PATH",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )
            
            # 3. 确定项目文件(.dproj)
            if request.project_path.endswith(('.dpr', '.dpk')):
                ext = '.dpr' if request.project_path.endswith('.dpr') else '.dpk'
                dproj_path = request.project_path[:-len(ext)] + '.dproj'
                if not Path(dproj_path).exists():
                    error_msg = f"未找到对应的 .dproj 文件: {dproj_path}"
                    logger.error(error_msg)
                    return CompileResult(
                        status=CompileStatus.FAILED,
                        error_code="DPROJ_NOT_FOUND",
                        error_message=error_msg,
                        duration=int((time.time() - start_time) * 1000)
                    )
            elif request.project_path.endswith('.dproj'):
                dproj_path = request.project_path
            else:
                error_msg = "项目文件必须是 .dpr、.dpk 或 .dproj 文件"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_PROJECT_FILE",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )
            
            # 3. 加载项目级配置（.daofy/project.json / daofy.project.json）
            # 每个工程可独立指定 Delphi 版本与 MSBuild，避免多版本机器上互相串用。
            project_settings = load_project_settings(dproj_path)
            if project_settings and project_settings.error:
                logger.error(project_settings.error)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="PROJECT_CONFIG_INVALID",
                    error_message=project_settings.error,
                    duration=int((time.time() - start_time) * 1000),
                )

            # 4. 提取并执行编译事件
            _PLATFORM_MSBUILD_MAP = {
                TargetPlatform.WIN32: "Win32",
                TargetPlatform.WIN64: "Win64",
                TargetPlatform.OSX64: "OSX64",
                TargetPlatform.OSXARM64: "OSXARM64",
                TargetPlatform.IOSDEVICE64: "iOSDevice64",
                TargetPlatform.IOSDEVICE: "iOSDevice",
                TargetPlatform.IOSSIMULATOR: "iOSSimulator",
                TargetPlatform.ANDROID: "Android",
                TargetPlatform.ANDROID64: "Android64",
                TargetPlatform.LINUX64: "Linux64",
            }
            platform = _PLATFORM_MSBUILD_MAP.get(request.options.target_platform, "Win32")
            config = request.options.build_configuration or "Debug"
            
            # ── 防御：extra_args 中 /p:Platform 或 /p:Config 与 options 不一致时，以 extra_args 为准 ──
            # （正常路径由 project.py 包装层同步，此处为直接调用 compiler_service 的兜底）
            _extra_args = request.options.extra_args or []
            _found_platform = _found_config = False
            for _ea in reversed(_extra_args):
                _property = self._parse_msbuild_property(_ea)
                if not _property:
                    continue
                _property_name, _property_value = _property
                if not _found_platform and _property_name == 'platform':
                    _extra_plat = _property_value
                    if _extra_plat.lower() != platform.lower():
                        logger.warning(
                            "extra_args /p:Platform=%s 与 options.target_platform=%s冲突，"
                            "以 extra_args 值为准（MSBuild last-wins）",
                            _extra_plat, platform,
                        )
                        platform = _extra_plat
                        try:
                            request.options.target_platform = TargetPlatform(_extra_plat.lower())
                        except ValueError:
                            pass
                    _found_platform = True
                elif not _found_config and _property_name == 'config':
                    _extra_cfg = _property_value
                    if _extra_cfg != config:
                        logger.warning(
                            "extra_args /p:Config=%s 与 build_configuration=%s冲突，"
                            "以 extra_args 值为准",
                            _extra_cfg, config,
                        )
                        config = _extra_cfg
                        request.options.build_configuration = _extra_cfg
                    _found_config = True
                if _found_platform and _found_config:
                    break

            parser = DprojParser(dproj_path)
            project_parsed = parser.parse()
            registry_version = self._resolve_msbuild_registry_version(
                request,
                parser,
                project_parsed,
                project_settings,
            )
            if (
                request.options.compiler_version
                or (project_settings and project_settings.compiler_version)
                or (project_settings and project_settings.error)
            ) and not registry_version:
                error_msg = (
                    project_settings.error
                    if project_settings and project_settings.error
                    else (
                        "无法确定指定编译器/项目配置的 Delphi 注册表版本，"
                        "为避免混用其他 Delphi 版本，已停止编译"
                    )
                )
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="COMPILER_VERSION_UNRESOLVED",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000),
                )
            selected_bds = (
                self._get_delphi_root_from_registry(registry_version)
                if registry_version
                else None
            )
            if registry_version:
                logger.info(
                    "MSBuild 使用 Delphi %s，平台 %s，配置 %s",
                    registry_version,
                    platform,
                    config,
                )

            # 3.5 按工程解析 MSBuild（项目配置 > 版本映射 > 自动探测）
            msbuild_path, msbuild_source, msbuild_explicit_error = (
                self._resolve_msbuild_path(registry_version, project_settings)
            )
            if not msbuild_path:
                error_msg = f"未找到可用的 MSBuild（{msbuild_source}）"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code=(
                        "MSBUILD_CONFIG_INVALID"
                        if msbuild_explicit_error
                        else "MSBUILD_NOT_FOUND"
                    ),
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000),
                )

            # 3.6 先确认目标 Delphi 版本的 rsvars.bat 可用，再执行编译事件。
            # 否则版本未安装时 PreBuildEvent 仍会用错误的 BDS 环境运行。
            if registry_version:
                logger.info("定位 Delphi %s 的 rsvars.bat", registry_version)
            rsvars_path = self._get_rsvars_path(registry_version)
            if not rsvars_path:
                error_msg = (
                    f"无法找到 Delphi {registry_version or '默认版本'} 的 rsvars.bat，"
                    "请检查该版本是否已安装"
                )
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="RSVARS_NOT_FOUND",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000),
                )
            if not selected_bds:
                selected_bds = str(Path(rsvars_path).parent.parent)
            
            project_dir = str(Path(dproj_path).parent)
            project_path = str(Path(dproj_path).parent)
            project_filename = Path(dproj_path).name
            project_name = Path(dproj_path).stem
            
            # 4.5 检查目标程序是否正在运行
            running_process = self._check_process_running(project_name)
            if running_process:
                error_msg = f"目标程序 '{project_name}.exe' 正在运行 (PID: {running_process['pid']})，无法编译。请先关闭程序后再试。"
                logger.warning(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="PROCESS_RUNNING",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000),
                    log=f"进程信息: PID={running_process['pid']}, 路径={running_process.get('path', '未知')}"
                )
            
            # 构建上下文变量（os 已在模块顶部导入）
            context = {
                # 项目相关
                'project_dir': project_dir,
                'project_path': project_path,
                'project_filename': project_filename,
                'project_name': project_name,
                
                # 输入文件相关(对于项目编译,输入文件就是项目文件)
                'input_path': project_path,
                'input_filename': project_filename,
                'input_ext': Path(dproj_path).suffix,
                
                # 输出文件相关
                'output_dir': request.options.output_path or project_dir,
                'output_path': request.options.output_path or project_dir,
                'output_filename': f"{project_name}.exe",
                'output_ext': '.exe',
                
                # 配置相关
                'config': config,
                'platform': platform,
                'defines': ';'.join(request.options.conditional_defines) if request.options.conditional_defines else '',
                
                # 路径相关
                'dir': project_dir,
                'include_path': ';'.join(request.options.unit_search_paths) if request.options.unit_search_paths else '',
                'path': os.environ.get('PATH', ''),
                
                # Delphi 环境变量
                'bds': selected_bds or os.environ.get('BDS') or '',
                'local_command': '',
                
                # 系统变量
                'system_root': os.environ.get('SystemRoot', r'C:\Windows'),
                'windir': os.environ.get('WINDIR', r'C:\Windows'),
            }
            
            # 解析 .dproj 文件获取编译事件
            build_events = {}
            if project_parsed:
                build_events = parser.get_build_events(config, platform)
                
                # 执行 PreBuildEvent
                if build_events.get('pre_build'):
                    success, error_msg, output = self._execute_build_event(
                        "PreBuildEvent",
                        build_events['pre_build'],
                        project_dir,
                        build_events.get('pre_build_ignore_exit_code', False),
                        60,
                        context
                    )
                    
                    if not success:
                        return CompileResult(
                            status=CompileStatus.FAILED,
                            error_code="PRE_BUILD_EVENT_FAILED",
                            error_message=error_msg,
                            duration=int((time.time() - start_time) * 1000),
                            log=output or ""
                        )
            
            # 5. 构建 MSBuild 参数
            args = []
            
            # 项目文件
            args.append(dproj_path)
            
            # ── 从 extra_args 提取属性名，跳过工具生成的同名属性 ──
            # extra_args 中的 MSBuild 属性为唯一来源，避免命令行重复且语义明确。
            _extra_prop_names = set()
            for _ea in (request.options.extra_args or []):
                _property = self._parse_msbuild_property(_ea)
                if _property:
                    _extra_prop_names.add(_property[0])
            
            # 目标平台
            if 'platform' not in _extra_prop_names:
                args.append(f"/p:Platform={platform}")
            
            # 配置(Debug/Release)
            if 'config' not in _extra_prop_names:
                args.append(f"/p:Config={config}")
            
            # 输出路径
            if request.options.output_path and 'dcc_exeoutput' not in _extra_prop_names:
                args.append(f"/p:DCC_ExeOutput={request.options.output_path}")
            
            # 条件编译符号
            if request.options.conditional_defines and 'dcc_define' not in _extra_prop_names:
                defines = ";".join(request.options.conditional_defines)
                # MSBuild 命令行上分号是属性分隔符，必须转义为 %3B
                # 经批处理文件传递时 % 需写为 %% 才能被 cmd.exe 正确展开
                defines = defines.replace(";", "%%3B")
                args.append(f"/p:DCC_Define={defines}")
            
            # 单元搜索路径
            if request.options.unit_search_paths and 'dcc_unitsearchpath' not in _extra_prop_names:
                paths = ";".join(request.options.unit_search_paths)
                args.append(f"/p:DCC_UnitSearchPath={paths}")
            
            # 生成 Detailed 级别 .map 文件（供 StackTrace callgraph 解析）
            if 'dcc_mapfile' not in _extra_prop_names:
                args.append("/p:DCC_MapFile=3")
            
            # Delphi >= XE5 (registry version >= 12.0) 时自动启用响应文件编译
            # 解决 MSBuild 命令行过长 (>32K) 导致编译失败的问题
            if 'dcc_usemsbuildexternally' not in _extra_prop_names:
                try:
                    delphi_ver = registry_version or _get_delphi_version_env()
                    if delphi_ver and float(delphi_ver) >= 12.0:
                        args.append("/p:DCC_UseMSBuildExternally=true")
                        logger.info("检测到 Delphi %s (>=XE5)，已启用 DCC_UseMSBuildExternally", delphi_ver)
                except Exception as e:
                    logger.warning("检测 Delphi 版本失败，不启用 DCC_UseMSBuildExternally: %s", e)

            # 其他参数
            args.append("/v:minimal")  # 最小输出级别

            # 用户参数追加（extra_args 中已覆盖的属性在此提供唯一来源）
            if not self.args_generator.validate_batch_extra_args(request.options.extra_args):
                error_msg = "额外编译参数包含不允许的批处理元字符"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_EXTRA_ARGS",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )
            # 5. rsvars.bat 已在执行编译事件前定位并校验（见 3.6）
            explicit_env_properties = {
                "bds",
                "bdsappdatabasedir",
                "envoptions",
                "importenvoptions",
                "delphilibrarypath",
                "productversion",
            }
            if registry_version and not (_extra_prop_names & explicit_env_properties):
                env_status = inspect_env_options_library_paths(
                    registry_version,
                    platform,
                )
                if env_status.state in ("missing", "stale"):
                    env_options_overlay = self._write_env_options_overlay(
                        env_status,
                        platform,
                    )
                    args.append(f"/p:EnvOptions={env_options_overlay}")
                    logger.warning(
                        "Delphi %s %s 的 EnvOptions 状态为 %s；"
                        "本次编译使用临时 overlay（注册表 %d 项，EnvOptions %d 项）",
                        registry_version,
                        platform,
                        env_status.state,
                        len(env_status.registry_paths),
                        len(env_status.env_options_paths),
                    )
                elif env_status.state == "unknown":
                    logger.warning(
                        "无法可靠检查 Delphi %s %s 的 EnvOptions，跳过自动覆盖",
                        registry_version,
                        platform,
                    )
                elif env_status.state == "registry_missing":
                    logger.debug(
                        "Delphi %s %s 未配置注册表 Library Search Path，沿用 EnvOptions",
                        registry_version,
                        platform,
                    )
            elif _extra_prop_names & explicit_env_properties:
                logger.info("检测到显式 EnvOptions/DelphiLibraryPath 参数，跳过自动兼容处理")

            args.extend(request.options.extra_args)

            # 记录完整编译参数到日志
            # 使用解析出的 MSBuild 绝对路径，而非裸 msbuild（依赖 PATH），
            # 避免 rsvars.bat 未将 VS MSBuild 加入 PATH 时找不到 msbuild.exe。
            msbuild_cmd = f'"{msbuild_path}" {" ".join(args)}'
            logger.info(f"MSBuild 参数: {msbuild_cmd}")
            
            # 6. 创建临时批处理文件来设置环境并执行 MSBuild
            # 将参数中的路径用引号包裹（处理空格）
            quoted_args = []
            for arg in args:
                if ' ' in arg:
                    quoted_args.append('"%s"' % arg)
                else:
                    quoted_args.append(arg)
            # 使用 OEM 代码页编码写 batch 文件，cmd.exe 只认 OEM 编码（不支持 UTF-8）
            batch_encoding = get_console_encoding(oem=True)
            with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False,
                                             encoding=batch_encoding) as f:
                f.write('@echo off\n')
                f.write('call "%s"\n' % rsvars_path)
                f.write('"%s" %s\n' % (msbuild_path, ' '.join(quoted_args)))
                batch_file = f.name
            
            logger.info("创建批处理文件: %s", batch_file)
            logger.debug("=== 完整编译命令 ===\n"
                         "rsp: %s\n%s" % (rsvars_path, msbuild_cmd))
            
            # 6. 执行批处理文件
            try:
                return_code, stdout, stderr = await self.process_manager.execute(
                    'cmd.exe',
                    ['/c', batch_file],
                    request.options.timeout
                )
                
                # 记录 MSBuild 输出中的编译器版本/行数信息
                for line in (stdout or '').split('\n'):
                    line = line.strip()
                    if line and ('Embarcadero Delphi' in line or 'dcc' in line.lower() or 'lines' in line.lower()):
                        logger.debug(f"编译器输出: {line}")
                
                # 6. 解析输出
                errors = self.output_parser.parse_errors(stdout + stderr)
                warnings = self.output_parser.parse_warnings(stdout + stderr)
                
                # 7. 构建结果
                duration = int((time.time() - start_time) * 1000)
                
                if return_code == 0:
                    # 编译成功
                    # 执行 PostBuildEvent
                    if build_events.get('post_build'):
                        # 检查执行条件
                        execute_when = build_events.get('post_build_execute_when', 'Always')
                        should_execute = False
                        
                        if execute_when == 'Always':
                            should_execute = True
                        elif execute_when == 'TargetOutOfDate':
                            # 目标过期时执行(编译成功意味着目标已更新)
                            should_execute = True
                        
                        if should_execute:
                            success, error_msg, output = self._execute_build_event(
                                "PostBuildEvent",
                                build_events['post_build'],
                                project_dir,
                                build_events.get('post_build_ignore_exit_code', False),
                                60,
                                context
                            )
                            
                            if not success:
                                logger.warning(f"PostBuildEvent 失败,但编译已成功: {error_msg}")
                    
                    output_file = self._extract_output_file(stdout, request.options.output_path)
                    output_files = self._collect_output_files(
                        dproj_path,
                        request.options.target_platform.value,
                        config,
                        output_file if (output_file and Path(output_file).parent.exists()) else None,
                    )
                    # 若 _extract_output_file 没找到（MSBuild 输出无 Output: 行），从 output_files 回填
                    if not output_file and output_files:
                        output_file = output_files[0]
                    result = CompileResult(
                        status=CompileStatus.SUCCESS,
                        output_file=output_file,
                        output_files=output_files,
                        warnings=warnings,
                        errors=errors,
                        duration=duration,
                        log=stdout + stderr
                    )
                    logger.info(f"MSBuild 编译成功,耗时 {duration}ms")
                else:
                    # 编译失败
                    result = CompileResult(
                        status=CompileStatus.FAILED,
                        error_code="COMPILATION_FAILED",
                        error_message=self.output_parser.extract_error_summary(stdout + stderr),
                        warnings=warnings,
                        errors=errors,
                        duration=duration,
                        log=stdout + stderr
                    )
                    logger.error(f"MSBuild 编译失败,耗时 {duration}ms")
                
                # 8. 保存编译历史
                self._save_history(request.project_path, result.status.value, duration, result.error_message)
                
                return result
                
            except TimeoutError as e:
                duration = int((time.time() - start_time) * 1000)
                logger.error(f"MSBuild 编译超时: {str(e)}")
                result = CompileResult(
                    status=CompileStatus.TIMEOUT,
                    error_code="COMPILATION_TIMEOUT",
                    error_message=str(e),
                    duration=duration
                )
                self._save_history(request.project_path, result.status.value, duration, str(e))
                return result
                
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            error_msg = f"MSBuild 编译过程发生异常: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result = CompileResult(
                status=CompileStatus.FAILED,
                error_code="INTERNAL_ERROR",
                error_message=error_msg,
                duration=duration
            )
            self._save_history(request.project_path, result.status.value, duration, error_msg)
            return result
        finally:
            self._remove_temp_file(batch_file)
            self._remove_temp_file(env_options_overlay)

    async def compile_with_lazbuild(self, request: ProjectCompileRequest) -> CompileResult:
        """
        使用 lazbuild 编译 Lazarus/Free Pascal 工程

        Args:
            request: 工程编译请求（project_path 为 .lpi 或 .lpr）

        Returns:
            编译结果
        """
        logger.info(f"使用 lazbuild 编译工程: {request.project_path}")
        start_time = time.time()

        try:
            # 1. 查找 lazbuild 路径
            lazbuild_path = self._find_lazbuild()
            if not lazbuild_path:
                error_msg = ("未找到 lazbuild.exe，请安装 Lazarus IDE。"
                             "下载地址: https://www.lazarus-ide.org/")
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="LAZBUILD_NOT_FOUND",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 2. 确定 .lpi 文件路径
            project_path = Path(request.project_path)
            ext = project_path.suffix.lower()
            if ext == '.lpr':
                lpi_path = project_path.with_suffix('.lpi')
                if not lpi_path.exists():
                    error_msg = f"未找到对应的 .lpi 文件: {lpi_path}"
                    logger.error(error_msg)
                    return CompileResult(
                        status=CompileStatus.FAILED,
                        error_code="LPI_NOT_FOUND",
                        error_message=error_msg,
                        duration=int((time.time() - start_time) * 1000)
                    )
            elif ext == '.lpi':
                lpi_path = project_path
            else:
                error_msg = "Lazarus 工程文件必须是 .lpi 或 .lpr 文件"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_LAZARUS_PROJECT",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 3. 检查目标程序是否正在运行
            project_name = project_path.stem
            running_process = self._check_process_running(project_name)
            if running_process:
                error_msg = (f"目标程序 '{project_name}.exe' 正在运行 "
                             f"(PID: {running_process['pid']})，无法编译。"
                             "请先关闭程序后再试。")
                logger.warning(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="PROCESS_RUNNING",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000),
                    log=f"进程信息: PID={running_process['pid']}, "
                        f"路径={running_process.get('path', '未知')}"
                )

            # 4. 构建 lazbuild 命令行
            args = [str(lpi_path)]

            # 编译模式: --build-mode=Default/Release/Debug
            if request.options.build_configuration:
                args.append(f"--build-mode={request.options.build_configuration}")

            # 平台: --ws=win32/win64
            platform_map = {
                TargetPlatform.WIN32: "win32",
                TargetPlatform.WIN64: "win64",
            }
            ws = platform_map.get(request.options.target_platform)
            if ws:
                args.append(f"--ws={ws}")

            logger.info(f"lazbuild 命令: {lazbuild_path} {' '.join(args)}")

            # 5. 执行编译
            return_code, stdout, stderr = await self.process_manager.execute(
                lazbuild_path,
                args,
                request.options.timeout
            )

            # 6. 解析输出
            output_text = stdout + stderr
            errors = self.output_parser.parse_errors(output_text)
            warnings = self.output_parser.parse_warnings(output_text)

            # 7. 构建结果
            duration = int((time.time() - start_time) * 1000)

            if return_code == 0:
                # 查找输出文件
                exe_path = self._find_lazbuild_output(lpi_path)
                result = CompileResult(
                    status=CompileStatus.SUCCESS,
                    output_file=str(exe_path) if exe_path else None,
                    duration=duration,
                    warnings=warnings,
                    log=output_text,
                )
            else:
                error_message = f"lazbuild 编译失败 (退出码: {return_code})"
                if errors:
                    error_message += f"\n{errors[0]}"

                result = CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="LAZBUILD_COMPILE_FAILED",
                    error_message=error_message,
                    duration=duration,
                    errors=errors,
                    warnings=warnings,
                    log=output_text,
                )

            self._save_history(request.project_path, result.status.value,
                               duration, result.error_message or "")
            return result

        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            error_msg = f"lazbuild 编译异常: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result = CompileResult(
                status=CompileStatus.FAILED,
                error_code="INTERNAL_ERROR",
                error_message=error_msg,
                duration=duration,
            )
            self._save_history(request.project_path, result.status.value,
                               duration, error_msg)
            return result

    def _find_lazbuild(self) -> Optional[str]:
        """
        查找 lazbuild.exe 路径

        搜索顺序:
        1. 配置文件中的 Lazarus 编译器路径
        2. 共享检测模块（PATH → 常见目录 → 开始菜单 → 注册表）

        Returns:
            lazbuild.exe 路径,未找到则返回 None
        """
        # 1. 从配置文件查找 Lazarus 编译器
        config = self.config_manager.config
        for compiler in config.compilers:
            if (getattr(compiler, 'compiler_type', None) == 'lazarus'
                    and compiler.path.lower().endswith('lazbuild.exe')):
                if Path(compiler.path).exists():
                    return compiler.path

        # 2. 共享检测模块
        from src.plugins.lazarus.detect import find_lazbuild
        paths = find_lazbuild()
        if paths:
            return str(paths[0])

        return None

    def _find_lazbuild_output(self, lpi_path: Path) -> Optional[Path]:
        """
        查找 lazbuild 编译输出文件

        Args:
            lpi_path: .lpi 文件路径

        Returns:
            输出 exe 路径
        """
        project_dir = lpi_path.parent
        project_name = lpi_path.stem
        exe_name = f"{project_name}.exe"

        # 优先查找 lazarus 默认输出目录
        output_dirs = [
            project_dir / "lib" / project_name,
            project_dir / "output",
            project_dir,
        ]

        for d in output_dirs:
            exe = d / exe_name
            if exe.exists():
                return exe

        return None

    async def compile_project(self, request: ProjectCompileRequest) -> CompileResult:
        """
        编译 Delphi/Lazarus 工程
        
        优先使用 MSBuild 编译 Delphi 工程,如果 MSBuild 不可用或没有 .dproj 文件则回退到直接调用编译器
        对于 Lazarus 工程(.lpi/.lpr),使用 lazbuild 编译

        Args:
            request: 工程编译请求

        Returns:
            编译结果
        """
        logger.info(f"开始编译工程: {request.project_path}")

        # 检查项目类型
        ext = Path(request.project_path).suffix.lower()
        is_source_file = ext in ('.dpr', '.dpk')
        is_dproj = ext == '.dproj'
        is_lpi = ext == '.lpi'
        is_lpr = ext == '.lpr'

        # Lazarus 工程 (.lpi/.lpr) 使用 lazbuild 编译
        if is_lpi or is_lpr:
            return await self.compile_with_lazbuild(request)

        # Delphi 工程 (.dproj) 使用 MSBuild 编译
        if is_dproj:
            logger.info("使用 MSBuild 编译 .dproj 文件")
            # MSBuild 的可用性由 compile_project_with_msbuild 按工程配置解析，
            # 这里不再用初始化时探测到的全局路径做前置判断（多版本机器上可能不同）。
            result = await self.compile_project_with_msbuild(request)
            if result.error_code in ("MSBUILD_NOT_FOUND", "MSBUILD_CONFIG_INVALID"):
                logger.error(
                    "MSBuild 不可用，无法编译 .dproj 文件: %s",
                    result.error_message,
                )
            return result

        # 检查是否存在 .dproj 文件
        dproj_exists = False
        if is_source_file:
            dproj_path = request.project_path[:-len(ext)] + '.dproj'
            dproj_exists = Path(dproj_path).exists()
            if not dproj_exists:
                logger.info(f"未找到 .dproj 文件，将使用 dcc32 直接编译{ext} 文件")

        # .dpr/.dpk 有 .dproj → 优先 MSBuild；MSBuild 不可用时回退 dcc 直编。
        # 但显式配置的 MSBuild 路径无效时必须直接失败，不能悄悄换直编掩盖配置错误。
        if dproj_exists:
            logger.info("使用 MSBuild 编译")
            result = await self.compile_project_with_msbuild(request)
            if result.error_code != "MSBUILD_NOT_FOUND":
                return result
            logger.warning(
                "MSBuild 不可用，回退到 dcc 直接编译: %s",
                result.error_message,
            )

        logger.info(f"使用 dcc 直接编译 {ext} 文件")
        return await self.compile_dpr_direct(request)

    async def compile_file(self, request: FileCompileRequest) -> CompileResult:
        """
        编译单个 Delphi 单元文件(仅语法检查)

        Args:
            request: 单文件编译请求

        Returns:
            编译结果
        """
        logger.info(f"开始编译文件: {request.file_path}")
        start_time = time.time()

        try:
            # 1. 验证文件路径
            is_valid, error_msg = self.validator.validate_file_path(request.file_path)
            if not is_valid:
                logger.error(f"文件路径验证失败: {error_msg}")
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_FILE_PATH",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 2. 获取编译器配置（显式版本 > 项目配置 > 最新安装的）
            # 文件可能属于某个使用旧版 Delphi 的工程，项目级配置优先，
            # 避免用最新安装版本做语法检查导致误报/漏报。
            settings = load_project_settings(request.file_path)
            if settings and settings.error:
                logger.error(settings.error)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="PROJECT_CONFIG_INVALID",
                    error_message=settings.error,
                    duration=int((time.time() - start_time) * 1000),
                )
            compiler_config = None
            if request.compiler_version:
                compiler_config = self._lookup_compiler_by_name_or_version(
                    request.compiler_version,
                    TargetPlatform.WIN32,
                )
            elif settings and settings.compiler_version:
                compiler_config = self._lookup_compiler_by_name_or_version(
                    settings.compiler_version,
                    TargetPlatform.WIN32,
                )
                if not compiler_config and settings.delphi_version:
                    # compiler_version 写错/不可用时，delphi_version 仍是明确声明
                    compiler_config = (
                        self._lookup_compiler_by_version(
                            settings.delphi_version,
                            TargetPlatform.WIN32,
                        )
                        or self._compiler_from_registry_version(
                            settings.delphi_version,
                            TargetPlatform.WIN32,
                        )
                    )
            elif settings and settings.delphi_version:
                compiler_config = (
                    self._lookup_compiler_by_version(
                        settings.delphi_version,
                        TargetPlatform.WIN32,
                    )
                    or self._compiler_from_registry_version(
                        settings.delphi_version,
                        TargetPlatform.WIN32,
                    )
                )
            else:
                compiler_config = self.config_manager.get_newest_compiler()
            if not compiler_config:
                if settings and (settings.compiler_version or settings.delphi_version):
                    error_msg = (
                        f"项目配置指定的 Delphi 版本不可用"
                        f"（{settings.compiler_version or settings.delphi_version}）；"
                        "不会回退到其它版本"
                    )
                else:
                    error_msg = "未找到可用的编译器"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="COMPILER_NOT_FOUND",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 3. 查找项目文件并提取配置
            file_dir = str(Path(request.file_path).parent)
            file_name = Path(request.file_path).stem

            # 尝试查找项目文件
            dproj_path = None
            project_unit_paths = []
            project_include_paths = []
            project_namespaces = []

            # 方法1: 查找同目录下的.dproj文件
            dproj_files = list(Path(file_dir).glob('*.dproj'))
            if dproj_files:
                # 优先选择与文件名匹配的项目，否则选择第一个
                for dproj in dproj_files:
                    if dproj.stem == file_name:
                        dproj_path = str(dproj)
                        break
                if not dproj_path:
                    dproj_path = str(dproj_files[0])

            # 方法2: 检查文件是否在项目的DCCReference中
            if dproj_path:
                try:
                    parser = DprojParser(dproj_path)
                    if parser.parse():
                        # 检查文件是否属于项目
                        if parser.is_file_in_project(Path(request.file_path).name):
                            logger.info(f"文件 {Path(request.file_path).name} 属于项目 {Path(dproj_path).name}")

                            # 提取单元搜索路径
                            project_unit_paths = parser.get_unit_search_paths()
                            logger.info(f"从项目文件中提取了 {len(project_unit_paths)} 个单元搜索路径")

                            # 提取include路径（从单元搜索路径中推断）
                            for path in project_unit_paths:
                                if 'include' in path.lower():
                                    project_include_paths.append(path)

                            # 提取命名空间
                            project_namespaces = parser.get_namespace()
                            if project_namespaces:
                                logger.info(f"从项目文件中提取了 {len(project_namespaces)} 个命名空间")
                        else:
                            logger.info(f"文件 {Path(request.file_path).name} 不属于项目 {Path(dproj_path).name}")
                            dproj_path = None
                except Exception as e:
                    logger.warning(f"解析项目文件失败: {e}")
                    dproj_path = None

            # 4. 删除源文件所在目录的旧版 .dcu 文件
            self._cleanup_dcu_files(request.file_path)

            # 5. 准备命名空间和include路径
            # 合并项目命名空间和默认命名空间
            default_namespaces = [
                "System", "Winapi", "System.Win", "Vcl", "Vcl.Imaging",
                "Vcl.Touch", "Vcl.Samples", "Vcl.Shell", "Data", "Datasnap",
                "Web", "Soap", "Xml"
            ]
            if project_namespaces:
                # 合并并去重
                namespaces = list(dict.fromkeys(project_namespaces + default_namespaces))
            else:
                namespaces = default_namespaces

            # 合并include路径
            default_include_paths = [
                str(Path(file_dir) / "Thirdpart" / "Jedi" / "Jcl" / "source" / "include"),
                str(Path(file_dir) / "Thirdpart" / "Jedi" / "Jcl" / "source" / "include" / "jedi")
            ]
            if project_include_paths:
                include_paths = list(dict.fromkeys(project_include_paths + default_include_paths))
            else:
                include_paths = default_include_paths

            # 合并单元搜索路径
            if project_unit_paths and request.unit_search_paths:
                # 用户提供的路径优先
                all_unit_paths = list(dict.fromkeys(request.unit_search_paths + project_unit_paths))
                logger.info(f"合并单元搜索路径: 用户 {len(request.unit_search_paths)} 个 + 项目 {len(project_unit_paths)} 个")
            elif project_unit_paths:
                all_unit_paths = project_unit_paths
            else:
                all_unit_paths = request.unit_search_paths or []

            # 输出目录 - 使用固定的绝对路径
            output_dir = str(Path(file_dir) / "Win32" / "Debug")

            # 确保输出目录存在
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            # 5. 从编译器配置获取 Delphi 数值版本号，用于标准库路径
            delphi_version = compiler_config.registry_version
            if not delphi_version:
                # 注册表不可用时（如手动配置的编译器），从编译器 --version 输出解析
                from ..utils.delphi_versions import detect_registry_version_from_compiler
                detected = detect_registry_version_from_compiler(compiler_config.path)
                if detected:
                    delphi_version = detected
                    logger.info(f"从编译器输出检测到版本: {delphi_version}")
                else:
                    delphi_version = None

            args = self.args_generator.generate_for_file(
                request.file_path,
                all_unit_paths,
                request.warning_level,
                request.disabled_warnings,
                namespaces=namespaces,
                include_paths=include_paths if include_paths else None,
                output_dir=output_dir,
                delphi_version=delphi_version,
                conditional_defines=request.conditional_defines,
                extra_args=request.extra_args,
            )

            # 5. 执行编译
            return_code, stdout, stderr = await self.process_manager.execute(
                compiler_config.path,
                args,
                timeout=TIMEOUT_DELPHI_COMPILE  # 单文件编译超时时间较短
            )

            # 5. 解析输出
            errors = self.output_parser.parse_errors(stdout + stderr)
            warnings = self.output_parser.parse_warnings(stdout + stderr)

            # 6. 构建结果
            duration = int((time.time() - start_time) * 1000)

            if return_code == 0:
                result = CompileResult(
                    status=CompileStatus.SUCCESS,
                    warnings=warnings,
                    errors=errors,
                    duration=duration,
                    log=stdout + stderr
                )
                logger.info(f"文件编译成功,耗时 {duration}ms")
            else:
                result = CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="SYNTAX_ERROR",
                    error_message=self.output_parser.extract_error_summary(stdout + stderr),
                    warnings=warnings,
                    errors=errors,
                    duration=duration,
                    log=stdout + stderr
                )
                logger.error(f"文件编译失败,耗时 {duration}ms")

            return result

        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            error_msg = f"文件编译过程发生异常: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return CompileResult(
                status=CompileStatus.FAILED,
                error_code="INTERNAL_ERROR",
                error_message=error_msg,
                duration=duration
            )

    def get_args(self, request: ProjectCompileRequest) -> CommandArgs:
        """
        获取命令行参数(不执行编译)

        Args:
            request: 工程编译请求

        Returns:
            命令行参数对象
        """
        logger.info(f"生成命令行参数: {request.project_path}")

        # 获取编译器配置（显式版本 > 项目配置 > 默认编译器）
        settings = load_project_settings(request.project_path)
        compiler_config, compiler_path, compiler_error = self._resolve_project_compiler(
            request.project_path,
            request.options.compiler_version,
            request.options.target_platform,
            settings,
        )
        if compiler_error:
            raise ValueError(compiler_error)
        if compiler_config:
            compiler_path = compiler_config.path
        if not compiler_path:
            raise ValueError(
                f"编译器配置不存在: "
                f"{request.options.compiler_version or '默认编译器'}"
            )

        # 根据目标平台选择编译器
        if request.options.target_platform == TargetPlatform.WIN64:
            # 大小写不敏感匹配 dcc32 可执行文件名（兼容 DCC32.EXE / Dcc32.exe 等手动配置）
            lower_path = compiler_path.lower()
            idx = lower_path.find('dcc32.exe')
            if idx != -1:
                compiler_path = compiler_path[:idx] + 'dcc64.exe' + compiler_path[idx + len('dcc32.exe'):]

        # 生成参数
        args = self.args_generator.generate(request.project_path, request.options)

        # 生成完整命令
        full_command = self.args_generator.format_command(compiler_path, args)

        # 收集警告
        warnings = []
        if request.options.output_path:
            is_valid, error_msg = self.validator.validate_output_path(request.options.output_path)
            if not is_valid:
                warnings.append(f"输出路径警告: {error_msg}")

        return CommandArgs(
            compiler_executable=compiler_path,
            project_file=request.project_path,
            arguments=args,
            full_command=full_command,
            warnings=warnings
        )

    @staticmethod
    def _collect_output_files(
        project_path: str,
        target_platform: str = "win32",
        build_configuration: str = "Debug",
        output_path_override: Optional[str] = None,
    ) -> list[str]:
        """扫描编译产物目录，收集所有生成的文件路径（exe/dll/bpl/bpi/dcp 等）

        Args:
            project_path: .dproj/.dpr/.dpk 文件路径
            target_platform: 目标平台（win32/win64 等）
            build_configuration: 编译配置（Debug/Release）
            output_path_override: 显式指定的输出路径（若提供则优先使用）

        Returns:
            所有存在的输出文件路径列表
        """
        proj = Path(project_path)
        project_name = proj.stem
        project_dir = proj.parent

        # 确定候选输出目录
        plat_map = {"win32": "Win32", "win64": "Win64"}
        plat_dir = plat_map.get(target_platform.lower(), "Win32")
        cfg = build_configuration or "Debug"

        dproj_path = proj.with_suffix('.dproj') if proj.suffix.lower() != '.dproj' else proj
        dproj_output = None
        if dproj_path.exists():
            try:
                from ..utils.dproj_parser import DprojParser
                parser = DprojParser(str(dproj_path))
                if parser.parse():
                    dproj_output = parser.get_output_path(config=cfg, platform=plat_dir)
            except Exception as e:
                logger.debug("DProj 解析失败（继续用候选目录列表）: %s", e)

        # 收集所有可能输出目录（去重、按可信度排序）
        candidate_dirs: list[Path] = []
        if output_path_override:
            candidate_dirs.append(Path(output_path_override))
        if dproj_output:
            candidate_dirs.append(Path(dproj_output))
        candidate_dirs.append(project_dir / plat_dir / cfg)  # Win32/Debug
        candidate_dirs.append(project_dir)                    # 项目根目录（MSBuild 缺省输出）

        # 输出产物列表（StackTrace/callgraph 需要 .map 做符号解析，.drc 不需要）
        extensions = ['.exe', '.dll', '.bpl', '.bpi', '.dcp', '.map', '.tds', '.rsm']
        found: list[str] = []

        for output_dir in candidate_dirs:
            if not output_dir.exists():
                continue
            for ext in extensions:
                candidate = output_dir / f"{project_name}{ext}"
                if candidate.exists() and str(candidate.resolve()) not in found:
                    found.append(str(candidate.resolve()))
            # 也通配查找以项目名开头的 .bpl/.bpi/.dcp（平台后缀变体）
            if not any(f.endswith(('.bpl', '.bpi', '.dcp')) for f in found):
                for ext in ('.bpl', '.bpi', '.dcp'):
                    for p in output_dir.glob(f"{project_name}*{ext}"):
                        if p.exists() and str(p.resolve()) not in found:
                            found.append(str(p.resolve()))

        # 对于 .dpk 包编译，bpl 可能输出到全局 Bpl 目录
        if proj.suffix.lower() == '.dpk' or dproj_path.suffix.lower() == '.dpk':
            bpl_search_dirs = [Path.home() / "Documents" / "Embarcadero" / "Studio"]
            public_studio_root = get_delphi_public_studio_root()
            if public_studio_root is not None:
                bpl_search_dirs.append(public_studio_root)
            for bpl_base in bpl_search_dirs:
                if bpl_base.exists():
                    for ver_dir in sorted(bpl_base.iterdir(), reverse=True):
                        bpl_dir = ver_dir / "Bpl"
                        if bpl_dir.exists():
                            for ext in ('.bpl', '.bpi', '.dcp'):
                                for p in bpl_dir.glob(f"{project_name}*{ext}"):
                                    if p.exists() and str(p.resolve()) not in found:
                                        found.append(str(p.resolve()))
                            break  # 只检查最新版本

        return found

    def _extract_output_file(self, output: str, output_path: Optional[str]) -> Optional[str]:
        """从输出中提取输出文件路径"""
        if output_path:
            return output_path
        # 尝试从 dcc32 输出行解析: "Output: C:\path\to\output.exe"
        for line in output.splitlines():
            if 'Output:' in line and '.exe' in line:
                idx = line.index('Output:') + 7
                path = line[idx:].strip().rstrip('.')
                if os.path.exists(path):
                    return path
        return None

    def _save_history(self, project_path: str, status: str, duration: int, error_message: Optional[str]):
        """保存编译历史"""
        entry = CompileHistoryEntry(
            timestamp=datetime.now(),
            project_path=project_path,
            status=status,
            duration=duration,
            error_message=error_message
        )
        self.config_manager.add_history_entry(entry)
