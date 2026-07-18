"""
配置管理器

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

负责编译器配置和编译历史的读写
"""

import json
import os
import shutil
import subprocess
import winreg
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from ..constants import REG_KEY_EMBARCADERO_BDS
from ..models.compiler_config import CompilerConfig, ConfigFile
from ..models.compile_history import CompileHistoryEntry, HistoryFile
from ..utils.delphi_versions import PROJECT_VERSION_PREFIX_MAP
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_path: Optional[str] = None, history_path: Optional[str] = None):
        """
        初始化配置管理器

        Args:
            config_path: 编译器配置文件路径，默认从 src/config/ 或项目根 config/ 自动查找
                （两个候选位置都支持，按存在性自动选择并输出提示）
            history_path: 编译历史文件路径，默认与 config_path 同目录下的 history.json
        """
        if config_path is None:
            # 自愈路径: AGENTS.md 文档与历史部署位置不一致
            # 候选: (1) src/config/compilers.json  (2) <项目根>/config/compilers.json
            # 选择第一个存在的, 都不存在时回退到 (1) 以便后续 _auto_detect_compilers 写入
            _default_root = Path(__file__).parent.parent  # src/
            _candidates = [
                _default_root / "config" / "compilers.json",           # src/config/  (历史内置)
                _default_root.parent / "config" / "compilers.json",    # 项目根 config/ (AGENTS.md 描述)
            ]
            config_path = str(_candidates[0])  # 默认: src/config/
            for _candidate in _candidates:
                if _candidate.exists():
                    config_path = str(_candidate)
                    if _candidate != _candidates[0]:
                        # 仅在切换到非默认位置时输出提示（首次启动/迁移后）
                        logger.info(
                            "compilers.json 默认路径 (%s) 不存在,已自愈切换到: %s",
                            _candidates[0], config_path,
                        )
                    break
            else:
                logger.debug(
                    "compilers.json 候选路径均不存在,将使用默认位置: %s（_auto_detect_compilers 将创建）",
                    config_path,
                )
        if history_path is None:
            if config_path is None:
                _default_root = Path(__file__).parent.parent
            else:
                _default_root = Path(config_path).parent
            history_path = str(_default_root / "history.json")
        self.config_path = Path(config_path)
        self.history_path = Path(history_path)
        self.config: ConfigFile = self._load_config()
        self.history: HistoryFile = self._load_history()

        # 如果没有配置编译器,自动检测
        if not self.config.compilers:
            logger.info("未检测到编译器配置,开始自动检测...")
            self._auto_detect_compilers()

        logger.info(f"配置管理器初始化完成")
        logger.debug(f"配置文件路径: {self.config_path}")
        logger.debug(f"历史文件路径: {self.history_path}")

    def _load_config(self) -> ConfigFile:
        """加载编译器配置"""
        if not self.config_path.exists():
            logger.info("配置文件不存在,创建默认配置")
            return ConfigFile()

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                config = ConfigFile.from_dict(data)
                logger.info(f"加载配置成功,共 {len(config.compilers)} 个编译器配置")
                return config
        except Exception as e:
            logger.error(f"加载配置失败: {str(e)}", exc_info=True)
            return ConfigFile()

    def _load_history(self) -> HistoryFile:
        """加载编译历史"""
        if not self.history_path.exists():
            logger.info("历史文件不存在,创建空历史")
            return HistoryFile()

        try:
            with open(self.history_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                history = HistoryFile.from_dict(data)
                logger.info(f"加载历史成功,共 {len(history.entries)} 条记录")
                return history
        except Exception as e:
            logger.error(f"加载历史失败: {str(e)}", exc_info=True)
            return HistoryFile()

    def save_config(self):
        """保存编译器配置"""
        try:
            # 确保目录存在
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config.to_dict(), f, indent=2, ensure_ascii=False)

            logger.info(f"配置保存成功: {self.config_path}")
        except Exception as e:
            logger.error(f"保存配置失败: {str(e)}")
            raise

    def save_history(self):
        """保存编译历史"""
        try:
            # 确保目录存在
            self.history_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.history_path, 'w', encoding='utf-8') as f:
                json.dump(self.history.to_dict(), f, indent=2, ensure_ascii=False)

            logger.debug(f"历史保存成功: {self.history_path}")
        except Exception as e:
            logger.error(f"保存历史失败: {str(e)}")
            raise

    def get_compiler(self, name: Optional[str] = None) -> Optional[CompilerConfig]:
        """
        获取编译器配置

        Args:
            name: 编译器名称,如果为 None 则返回默认编译器

        Returns:
            编译器配置,如果不存在则返回 None
        """
        if name:
            compiler = self.config.get_compiler(name)
            if compiler:
                logger.debug(f"获取编译器配置: {name}")
            else:
                logger.warning(f"编译器配置不存在: {name}")
            return compiler
        else:
            compiler = self.config.get_default_compiler()
            if compiler:
                logger.debug(f"获取默认编译器配置: {compiler.name}")
            else:
                logger.warning("未配置默认编译器")
            return compiler

    PROJECT_VERSION_MAP = PROJECT_VERSION_PREFIX_MAP.copy()

    def get_compiler_for_project(self, project_version: str, platform: str = "win32") -> Optional[CompilerConfig]:
        """
        根据项目版本自动匹配最适配的编译器

        Args:
            project_version: 项目版本号(如 "19.2", "21.0" 等)
            platform: 目标平台(win32/win64),默认 win32

        Returns:
            最适配的编译器配置,如果未找到则返回默认编译器
        """
        if not project_version:
            logger.warning("项目版本号为空,使用最新编译器")
            return self.get_newest_compiler() or self.get_compiler()

        delphi_version = self._map_project_version_to_delphi(project_version)
        if not delphi_version:
            logger.warning(f"无法识别的项目版本: {project_version},使用最新编译器")
            return self.get_newest_compiler() or self.get_compiler()

        compilers = self.config.compilers
        if not compilers:
            logger.warning("未配置任何编译器")
            return None

        matching_compilers = [c for c in compilers if delphi_version.lower() in c.version.lower()]

        if matching_compilers:
            if platform == "win64":
                for c in matching_compilers:
                    if "win64" in c.name.lower():
                        logger.info(f"匹配到编译器(Win64): {c.name}")
                        return c
            else:
                for c in matching_compilers:
                    if "win32" in c.name.lower():
                        logger.info(f"匹配到编译器(Win32): {c.name}")
                        return c
                return matching_compilers[0]

        logger.warning(f"未找到匹配版本 {delphi_version} 的编译器,使用最新编译器")
        return self.get_newest_compiler() or self.get_compiler()

    def _map_project_version_to_delphi(self, project_version: str) -> Optional[str]:
        """
        将项目版本号映射到 Delphi 版本名称

        Args:
            project_version: 项目版本号

        Returns:
            Delphi 版本名称
        """
        version_prefix = project_version.split(".")[0]
        return self.PROJECT_VERSION_MAP.get(version_prefix)

    def add_compiler(self, compiler: CompilerConfig):
        """
        添加编译器配置

        Args:
            compiler: 编译器配置
        """
        # 如果没有 registry_version，尝试从编译器 --version 输出检测
        if not compiler.registry_version and compiler.path:
            try:
                from ..utils.delphi_versions import detect_registry_version_from_compiler
                detected = detect_registry_version_from_compiler(compiler.path)
                if detected:
                    compiler.registry_version = detected
                    logger.info(f"通过编译器输出检测到版本: {compiler.name} → {detected}")
            except Exception:
                logger.debug("通过编译器输出检测版本失败: %s", compiler.path, exc_info=True)

        self.config.add_compiler(compiler)
        self.save_config()
        logger.info(f"添加编译器配置: {compiler.name}")

    def update_compiler(self, name: str, compiler: CompilerConfig):
        """
        更新编译器配置

        Args:
            name: 原编译器名称
            compiler: 新的编译器配置
        """
        # 删除旧配置
        self.config.remove_compiler(name)
        # 添加新配置
        self.config.add_compiler(compiler)
        self.save_config()
        logger.info(f"更新编译器配置: {name} -> {compiler.name}")

    def remove_compiler(self, name: str) -> bool:
        """
        删除编译器配置

        Args:
            name: 编译器名称

        Returns:
            是否删除成功
        """
        result = self.config.remove_compiler(name)
        if result:
            self.save_config()
            logger.info(f"删除编译器配置: {name}")
        else:
            logger.warning(f"删除编译器配置失败,不存在: {name}")
        return result

    def set_default_compiler(self, name: str) -> bool:
        """
        设置默认编译器

        Args:
            name: 编译器名称

        Returns:
            是否设置成功
        """
        result = self.config.set_default_compiler(name)
        if result:
            self.save_config()
            logger.info(f"设置默认编译器: {name}")
        else:
            logger.warning(f"设置默认编译器失败,不存在: {name}")
        return result

    def get_newest_compiler(self) -> Optional[CompilerConfig]:
        """
        获取最新安装的编译器（按 registry_version 数值最大者）。

        当用户未指定编译器版本时，默认使用最新版本，而非"默认编译器"。
        """
        compilers = self.config.compilers
        if not compilers:
            return None

        def sort_key(c: CompilerConfig) -> tuple:
            if c.registry_version:
                try:
                    parts = c.registry_version.split('.')
                    return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
                except (ValueError, IndexError):
                    return (0, 0)
            return (0, 0)

        return max(compilers, key=sort_key)

    def get_all_compilers(self) -> List[CompilerConfig]:
        """获取所有编译器配置"""
        return self.config.compilers

    def get_show_timing(self) -> bool:
        """工具返回中是否包含 timing 字段"""
        return self.config.show_timing

    def add_history_entry(self, entry: CompileHistoryEntry):
        """
        添加编译历史记录

        Args:
            entry: 编译历史记录
        """
        self.history.add_entry(entry)
        self.save_history()
        logger.debug(f"添加编译历史记录: {entry.project_path}")

    def get_history(self, limit: int = 10) -> List[CompileHistoryEntry]:
        """
        获取编译历史记录

        Args:
            limit: 最大记录数

        Returns:
            编译历史记录列表
        """
        return self.history.get_recent_entries(limit)

    def clear_history(self):
        """清空编译历史"""
        self.history.clear()
        self.save_history()
        logger.info("清空编译历史")

    def _auto_detect_compilers(self):
        """自动检测 Delphi 和 Lazarus 编译器"""
        detected_compilers = []

        # 首先清空旧的编译器配置，避免旧配置干扰
        logger.info("清空旧编译器配置，准备重新检测...")
        self.config.compilers = []
        self.config.default_compiler = None

        # 通过注册表检测 Delphi 安装路径
        delphi_installations = self._detect_delphi_from_registry()

        for version, install_path in delphi_installations.items():
            logger.info(f"检测到 Delphi {version}: {install_path}")
            compilers = self._detect_compilers_from_path(install_path, version)
            detected_compilers.extend(compilers)

        # 检测 Lazarus/FPC 安装
        lazarus_compilers = self._detect_lazarus()
        detected_compilers.extend(lazarus_compilers)

        if detected_compilers:
            # 添加所有检测到的编译器
            for compiler in detected_compilers:
                self.config.add_compiler(compiler)
                logger.info(f"自动配置编译器: {compiler.name}")

            # 设置第一个为默认编译器
            if detected_compilers:
                self.config.set_default_compiler(detected_compilers[0].name)
                logger.info(f"设置默认编译器: {detected_compilers[0].name}")

            # 保存配置
            self.save_config()
            logger.info(f"自动检测完成,共检测到 {len(detected_compilers)} 个编译器")
        else:
            logger.warning("未检测到任何编译器,请手动配置")

    def _detect_delphi_from_registry(self) -> dict:
        """
        从注册表检测 Delphi 安装路径

        同时扫描 HKCU (用户级) 和 HKLM (系统级), HKCU 优先级更高
        (用户的 RAD Studio 设置通常覆盖机器级配置).

        Returns:
            字典,键为版本号,值为安装路径
        """
        installations: Dict[str, str] = {}

        # 扫描顺序: HKCU 先 (用户级优先), HKLM 后 (系统级兜底)
        # 配合下方 "version not in installations" 跳过逻辑,
        # 同版本号时 HKCU 的路径会胜出, HKLM 跳过.
        registry_roots = [
            (winreg.HKEY_CURRENT_USER, REG_KEY_EMBARCADERO_BDS, "HKCU"),
            (winreg.HKEY_LOCAL_MACHINE, REG_KEY_EMBARCADERO_BDS, "HKLM"),
        ]

        for hive, subkey, hive_name in registry_roots:
            try:
                key = winreg.OpenKey(
                    hive,
                    subkey,
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_32KEY,
                )
            except FileNotFoundError:
                logger.debug(f"注册表 {hive_name}\\{subkey} 不存在,跳过")
                continue
            except Exception as e:
                logger.warning(f"打开注册表 {hive_name}\\{subkey} 失败: {e}")
                continue

            try:
                # 枚举所有子项(版本号)
                index = 0
                while True:
                    try:
                        version = winreg.EnumKey(key, index)
                        index += 1
                    except OSError:
                        # 枚举结束
                        break

                    try:
                        version_key = winreg.OpenKey(key, version)
                    except Exception as e:
                        logger.debug(f"打开 {hive_name}\\{subkey}\\{version} 失败: {e}")
                        continue

                    try:
                        # 读取 RootDir 值
                        try:
                            root_dir, _ = winreg.QueryValueEx(version_key, "RootDir")
                        except FileNotFoundError:
                            logger.debug(f"Delphi {version} 没有 RootDir 值")
                            continue

                        if root_dir and os.path.exists(root_dir):
                            if version not in installations:
                                installations[version] = root_dir
                                logger.debug(f"从 {hive_name} 检测到 Delphi {version}: {root_dir}")
                            else:
                                logger.debug(
                                    f"Delphi {version} 已在 HKCU 优先注册,跳过 {hive_name} 路径: {root_dir}"
                                )

                    finally:
                        try:
                            winreg.CloseKey(version_key)
                        except Exception:
                            pass
            finally:
                try:
                    winreg.CloseKey(key)
                except Exception:
                    pass

        if not installations:
            logger.debug("HKLM/HKCU 均未找到 Embarcadero BDS 安装")

        return installations

    def _detect_compilers_from_path(self, delphi_path: str, registry_version: str = None) -> List[CompilerConfig]:
        """
        从 Delphi 安装路径检测编译器

        Args:
            delphi_path: Delphi 安装路径
            registry_version: 从注册表获取的版本号（如果有则优先使用）

        Returns:
            检测到的编译器配置列表
        """
        compilers = []
        bin_path = os.path.join(delphi_path, "bin")

        if not os.path.exists(bin_path):
            logger.warning(f"bin 目录不存在: {bin_path}")
            return compilers

        # 检测编译器版本名称和注册表版本号
        effective_registry_version = registry_version
        if not effective_registry_version:
            from ..utils.delphi_versions import detect_registry_version_from_compiler
            # 先通过 bin 下的任意一个 dcc*.exe 尝试 --version 检测
            if os.path.exists(bin_path):
                for fname in os.listdir(bin_path):
                    if fname.lower().startswith('dcc') and fname.lower().endswith('.exe'):
                        detected = detect_registry_version_from_compiler(os.path.join(bin_path, fname))
                        if detected:
                            effective_registry_version = detected
                            logger.info(f"通过编译器输出检测到版本: {effective_registry_version}")
                        break

        if effective_registry_version:
            from src.utils.delphi_versions import get_version_name
            version_name = get_version_name(effective_registry_version)
        else:
            version_name = self._get_delphi_version_name(delphi_path)
        # 注意: 此映射应与 compiler_service._get_platform_compiler_name 保持一致
        # 新平台添加时两处必须同步更新
        filename_to_platform = {
            "dcc32": "Win32",
            "dcc64": "Win64",
            "dccaarm": "Android32",
            "dccaarm64": "Android64",
            "dccaac64": "Android64",     # Delphi 12+ 新增
            "dcclinux64": "Linux64",
            "dccosx64": "OSX64",
            "dccosxarm64": "OSXARM64",
            "dcciosarm64": "iOSARM64",
            "dcciossimarm64": "iOSSimARM64",
            "dccarm": "ARM32",
            "dccarm64": "ARM64",
            "dcclinux": "Linux64",
        }

        # 扫描 bin 目录下所有 dcc*.exe，自动识别平台
        if os.path.exists(bin_path):
            for filename in os.listdir(bin_path):
                lower_filename = filename.lower()
                if lower_filename.startswith("dcc") and lower_filename.endswith(".exe"):
                    base_name = lower_filename[:-4]  # 去掉 .exe
                    platform_name = filename_to_platform.get(base_name)
                    if not platform_name:
                        platform_name = base_name.replace("dcc", "").upper()

                    full_path = os.path.join(bin_path, filename)
                    compiler = CompilerConfig(
                        name=f"{version_name} {platform_name}",
                        path=full_path,
                        is_default=False,
                        version=version_name,
                        registry_version=effective_registry_version,
                    )
                    compilers.append(compiler)
                    logger.debug(f"检测到 {platform_name} 编译器: {full_path}")

        return compilers

    def _get_delphi_version_name(self, delphi_path: str) -> str:
        """
        获取 Delphi 版本名称

        Args:
            delphi_path: Delphi 安装路径

        Returns:
            Delphi 版本名称
        """
        from src.utils.delphi_versions import get_version_name_from_path
        return get_version_name_from_path(delphi_path)

    def _detect_lazarus(self) -> List[CompilerConfig]:
        """
        检测 Lazarus/FPC 编译器安装

        委托 src.plugins.lazarus.detect.find_lazbuild() 统一查找，
        然后补充版本号和 FPC 路径检测。
        """
        from src.plugins.lazarus.detect import find_lazbuild

        compilers: List[CompilerConfig] = []
        candidates = find_lazbuild()

        if not candidates:
            logger.debug("未检测到 Lazarus/FPC 安装")
            return compilers

        for lazbuild_path in candidates:
            lazarus_dir = lazbuild_path.parent
            version = self._get_lazarus_version(str(lazbuild_path))
            compiler_name = f"Lazarus FPC {version}" if version else "Lazarus FPC"

            fpc_path = self._find_fpc_in_lazarus(lazarus_dir)

            compilers.append(CompilerConfig(
                name=compiler_name,
                path=str(lazbuild_path),
                is_default=False,
                version=version,
                compiler_type="lazarus",
            ))
            if fpc_path:
                compilers.append(CompilerConfig(
                    name=f"FPC {version}" if version else "FPC",
                    path=str(fpc_path),
                    is_default=False,
                    version=version,
                    compiler_type="lazarus",
                ))
            logger.debug(f"检测到 Lazarus: {lazbuild_path}, version={version}")

        return compilers

    def _get_lazarus_version(self, lazbuild_path: str) -> str:
        """通过 lazbuild --version 获取 Lazarus 版本号"""
        import subprocess
        try:
            result = subprocess.run(
                [lazbuild_path, "--version"],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                # 输出形如 "Lazarus 4.8"
                if line.lower().startswith("lazarus"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1]
        except Exception as e:
            logger.debug(f"获取 Lazarus 版本失败: {e}")
        return ""

    def _find_fpc_in_lazarus(self, lazarus_dir: Path) -> Optional[str]:
        """在 Lazarus 安装目录中查找 fpc.exe"""
        fpc_base = lazarus_dir / "fpc"
        if not fpc_base.exists():
            return None
        # 目录结构: fpc/<version>/bin/x86_64-win64/fpc.exe
        for ver_dir in sorted(fpc_base.iterdir(), reverse=True):
            if not ver_dir.is_dir():
                continue
            for arch_dir in (ver_dir / "bin").glob("*"):
                fpc_exe = arch_dir / "fpc.exe"
                if fpc_exe.exists():
                    return str(fpc_exe)
        return None

