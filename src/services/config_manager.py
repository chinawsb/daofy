"""
配置管理器

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

负责编译器配置和编译历史的读写
"""

import json
import os
import re
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

        # 仅在配置文件不存在（全新安装首次启动）时自动检测。
        # 用户手动编辑过 compilers.json 时不再自动覆盖，避免用户指定的
        # 自定义路径（如非默认位置的 Lazarus d:\win\lazarus）被自动检测清空。
        if not self.config_path.exists():
            logger.info("配置文件不存在,开始自动检测编译器...")
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

        匹配策略（按优先级）:
          1. 精确匹配: registry_version 与项目版本前缀完全一致
          2. 精确匹配(按产品名): version 字段含目标 Delphi 名称（如 "Delphi 11"）
          3. 回退: 版本 >= 目标的编译器，选择最接近的，保证高版本可编译低版本项目
        """
        if not project_version:
            logger.warning("项目版本号为空,使用最新编译器")
            return self.get_newest_compiler() or self.get_compiler()

        # 从项目版本号提取版本前缀 (如 "19.2" → "19")
        version_prefix = project_version.split(".")[0]
        if not version_prefix or not version_prefix.isdigit():
            logger.warning(f"无法识别的项目版本: {project_version},使用最新编译器")
            return self.get_newest_compiler() or self.get_compiler()

        # 将版本前缀转换为 registry_version 格式 (如 "19" → "19.0")
        target_registry_version = f"{version_prefix}.0"

        # 目标 Delphi 产品名（如 "Delphi 11 Alexandria"），用于按 name/version 匹配
        delphi_name = self._map_project_version_to_delphi(project_version)
        # 产品名数字部分（如 "Delphi 11"）用于版本字段模糊匹配
        delphi_num_name = None
        if version_prefix.isdigit():
            # 从分隔的版本名称中取 "Delphi N" 数字前缀
            from ..utils.delphi_versions import DELPHI_VERSION_NAMES, PROJECT_VERSION_PREFIX_MAP
            # registry_version → 产品名
            product_name = DELPHI_VERSION_NAMES.get(target_registry_version)
            if product_name:
                # 取如 "Delphi 12"
                m = re.match(r"^(Delphi \d+)", product_name)
                if m:
                    delphi_num_name = m.group(1).lower()

        compilers = self.config.compilers
        if not compilers:
            logger.warning("未配置任何编译器")
            return None

        def _pick_by_platform(candidates: list) -> Optional[CompilerConfig]:
            """从候选编译器中按平台优先选择。"""
            if platform == "win64":
                for c in candidates:
                    if "win64" in c.name.lower():
                        return c
                return candidates[0]
            else:
                for c in candidates:
                    if "win32" in c.name.lower():
                        return c
                return candidates[0]

        # ── 1. 精确匹配 registry_version ──
        exact_matches = [c for c in compilers if c.registry_version == target_registry_version]
        if exact_matches:
            pick = _pick_by_platform(exact_matches)
            logger.info(f"精确匹配到编译器: {pick.name} (registry_version={pick.registry_version})")
            return pick

        # ── 2. 精确匹配产品名（version 或 name 字段）──
        name_matches = []
        if delphi_name:
            dl = delphi_name.lower()
            name_matches = [
                c for c in compilers
                if (c.version and dl in c.version.lower())
                or (c.name and dl in c.name.lower())
            ]
        if name_matches:
            pick = _pick_by_platform(name_matches)
            logger.info(f"产品名精确匹配到编译器: {pick.name}")
            return pick

        # ── 3. 数字前缀模糊匹配（如 delphi_name 为 "Delphi 11..." 时匹配 "Delphi 11"）──
        num_matches = []
        if delphi_num_name:
            num_matches = [
                c for c in compilers
                if (c.version and (
                    delphi_num_name in c.version.lower()
                    or f"{delphi_num_name} " in c.version.lower()
                    or c.version.lower().startswith(delphi_num_name)
                ))
                or (c.name and delphi_num_name in c.name.lower())
            ]
        if num_matches:
            pick = _pick_by_platform(num_matches)
            logger.info(f"数字前缀匹配到编译器: {pick.name}")
            return pick

        # ── 4. 回退: 版本 >= 目标，选择最接近的 ──
        # 解析目标版本号用于比较
        try:
            target_ver = float(target_registry_version)
        except ValueError:
            target_ver = 0

        # 为每个编译器推导数值版本（registry_version 优先，其次从 version/name 推导）
        compatible_compilers = []
        for c in compilers:
            ver = self._compiler_numeric_version(c, target_ver)
            if ver is not None and ver >= target_ver:
                compatible_compilers.append((ver, c))

        if compatible_compilers:
            # 按版本号升序，选最接近目标的
            compatible_compilers.sort(key=lambda x: x[0])
            best = _pick_by_platform([c for _, c in compatible_compilers])
            logger.info(f"回退匹配到编译器: {best.name} (版本 >= {target_registry_version})")
            return best

        logger.warning(f"未找到匹配版本 {target_registry_version} 的编译器,使用最新编译器")
        return self.get_newest_compiler() or self.get_compiler()

    def _compiler_numeric_version(self, compiler, target_ver: float) -> Optional[float]:
        """
        提取编译器的数值版本号用于比较。

        优先级:
          1. registry_version（如 "22.0"）
          2. version 字段中的数字（如 "Delphi 11 Alexandria" → 22.0）
          3. name 字段中的数字

        Args:
            compiler: CompilerConfig
            target_ver: 目标版本号（用于数字前缀推导）

        Returns:
            数值版本号（registry_version 格式），无法推导返回 None
        """
        import re as _re

        # 1. registry_version
        if compiler.registry_version:
            try:
                return float(compiler.registry_version)
            except (ValueError, TypeError):
                pass

        # 2/3. 从 version 或 name 解析 "Delphi N" → registry_version
        #     Delphi N → registry.0，如 "Delphi 11" → 22.0
        from ..utils.delphi_versions import PROJECT_VERSION_PREFIX_MAP
        texts = [compiler.version or "", compiler.name or ""]
        for text in texts:
            m = _re.search(r"Delphi\s+(\d+)(?:\s|$)", text, _re.IGNORECASE)
            if m:
                prefix = m.group(1)
                # PROJECT_VERSION_PREFIX_MAP 的键是 .dproj 版本前缀（registry 版本相同）
                # 但 "Delphi 11" 的产品序号 → 其 registry 版本前缀不同
                # 需通过反向映射: 产品序号 → registry_version
                reg_ver = self._map_delphi_num_to_registry(prefix)
                if reg_ver:
                    try:
                        return float(reg_ver)
                    except ValueError:
                        pass

        return None

    @staticmethod
    def _map_delphi_num_to_registry(delphi_num: str) -> Optional[str]:
        """
        将 "Delphi N" 产品序号映射为 registry_version。

        例如: "11" → "22.0", "12" → "23.0", "13" → "37.0"

        Args:
            delphi_num: Delphi 产品序号（如 "11", "12"）

        Returns:
            registry_version（如 "22.0"），映射失败返回 None
        """
        from ..utils.delphi_versions import PROJECT_VERSION_PREFIX_MAP
        # 产品序号 → 注册表版本（registry_version）
        # 映射表: 基于版本历史，产品序号 N 对应的注册表版本号
        num_to_registry = {
            "13": "37.0",   # Delphi 13 Florence
            "12": "23.0",   # Delphi 12 Athens
            "11": "22.0",   # Delphi 11 Alexandria
            "10": "21.0",   # Delphi 10.4 Sydney（10 系列最新）
            "10.4": "21.0",
            "10.3": "20.0",
            "10.2": "19.0",
            "10.1": "18.0",
        }
        return num_to_registry.get(delphi_num)

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
        # ruff: noqa: D205
        """自动检测 Delphi 和 Lazarus 编译器（合并式，不覆盖既有配置）。

        与旧版仅清空后重建不同，此版本：
        - 保留已配置且路径仍然存在的编译器（含用户手动指定的自定义路径，
          如非默认安装位置的 Lazarus ``d:\\win\\lazarus\\bin\\lazbuild.exe``）。
        - 仅丢弃路径已失效的旧配置（指向磁盘上已不存在的文件）。
        - 追加新检测到、且尚未配置的编译器（按规范化路径去重）。
        - 默认编译器在既有默认仍有效时保持不变，否则回退到最新/首个。

        这样避免“自动检测把用户手写的路径整个清掉”的回归。
        """
        # 快照既有编译器：保留路径仍有效者，清理已失效条目
        existing_valid: List[CompilerConfig] = []
        for compiler in list(self.config.compilers):
            if compiler.path and os.path.exists(compiler.path):
                existing_valid.append(compiler)
            else:
                logger.info(
                    "丢弃路径已失效的编译器配置: %s (%s)",
                    compiler.name, compiler.path,
                )
        self.config.compilers = existing_valid

        # 记录既有默认编译器名称（用于检测后保持默认）
        existing_default = self.config.default_compiler
        if existing_default and not self.config.get_compiler(existing_default):
            existing_default = None

        # 通过注册表检测 Delphi 安装路径
        delphi_installations = self._detect_delphi_from_registry()

        for version, install_path in delphi_installations.items():
            logger.info(f"检测到 Delphi {version}: {install_path}")
            compilers = self._detect_compilers_from_path(install_path, version)
            self._merge_detected(compilers)

        # 检测 Lazarus/FPC 安装
        lazarus_compilers = self._detect_lazarus()
        self._merge_detected(lazarus_compilers)

        if self.config.compilers:
            # 默认编译器：保持既有有效默认；否则回退到最新/首个
            if existing_default:
                self.config.set_default_compiler(existing_default)
            else:
                default = self.get_newest_compiler() or self.config.compilers[0]
                self.config.set_default_compiler(default.name)
                logger.info(f"设置默认编译器: {default.name}")

            # 保存配置
            self.save_config()
            logger.info(
                "自动检测完成,共 %d 个编译器（保留既有 %d 个，新增 %d 个）",
                len(self.config.compilers),
                len(existing_valid),
                len(self.config.compilers) - len(existing_valid),
            )
        else:
            logger.warning("未检测到任何编译器,请手动配置")

    def _merge_detected(self, detected: List[CompilerConfig]) -> None:
        """将新检测到的编译器合并进配置，按规范化路径去重。"""
        existing_paths = {
            self._normalize_compiler_path(c.path).casefold()
            for c in self.config.compilers if c.path
        }
        for compiler in detected:
            if not compiler.path:
                continue
            key = self._normalize_compiler_path(compiler.path).casefold()
            if key in existing_paths:
                logger.debug("跳过已配置的编译器: %s", compiler.path)
                continue
            self.config.add_compiler(compiler)
            existing_paths.add(key)
            logger.info(f"自动配置编译器: {compiler.name}")

    @staticmethod
    def _normalize_compiler_path(path: str) -> str:
        """规范化编译器路径用于去重比较。"""
        try:
            return str(Path(path).resolve())
        except Exception:
            return os.path.normcase(os.path.normpath(path))

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

