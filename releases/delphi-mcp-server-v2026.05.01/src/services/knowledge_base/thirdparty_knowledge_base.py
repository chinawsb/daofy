"""
第三方库知识库服务

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

为 Delphi 第三方库提供知识库功能:
1. 从注册表读取 Delphi 版本的 Library 路径
2. 解析 Browsing Path 和 Search Path
3. 展开环境变量并去重
4. 排除 Delphi 自带路径
5. 构建第三方库知识库
"""

import os
import re
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set, Callable
from datetime import datetime

try:
    from .scan_delphi_sources import DelphiSourceScanner
    from .sqlite_vector_query_knowledge_base import SQLiteVectorKnowledgeBase
    from ...utils.logger import get_logger
    from ...utils.delphi_env import expand_delphi_path_macros, get_delphi_version, get_catalog_repository_paths
    logger = get_logger(__name__)
except ImportError:
    # 支持直接运行测试
    from scan_delphi_sources import DelphiSourceScanner
    from sqlite_vector_query_knowledge_base import SQLiteVectorKnowledgeBase
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        logger.addHandler(handler)


class ThirdPartyKnowledgeBase:
    """第三方库知识库管理器"""

    def __init__(self, kb_dir: Optional[str] = None, progress_callback: Optional[Callable] = None):
        """
        初始化第三方库知识库

        Args:
            kb_dir: 知识库目录路径,如果为 None 则使用默认路径
            progress_callback: 进度回调函数
        """
        if kb_dir is None:
            # 默认路径: MCP 服务器目录下的 data/thirdparty-knowledge-base
            server_root = Path(__file__).parent.parent.parent.parent
            kb_dir = server_root / "data" / "thirdparty-knowledge-base"
        else:
            kb_dir = Path(kb_dir)

        self.kb_dir = kb_dir
        self.kb_instance = None
        self.delphi_versions = []
        self.environment_variables = {}  # 环境变量缓存
        self.progress_callback = progress_callback

        # 创建必要的目录
        self.kb_dir.mkdir(parents=True, exist_ok=True)

        # 元数据文件
        self.metadata_file = self.kb_dir / "thirdparty_metadata.json"
        self.paths_file = self.kb_dir / "thirdparty_paths.json"

        # 加载元数据
        self.metadata = self._load_metadata()

        # 检测 Delphi 版本
        self.detect_delphi_versions()

        logger.info("第三方库知识库初始化完成")

    def _load_metadata(self) -> Dict:
        """加载元数据"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载元数据失败: {e}")

        return {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "version": "1.0",
            "total_paths": 0,
            "scanned_paths": []
        }

    def _save_metadata(self):
        """保存元数据"""
        self.metadata["last_updated"] = datetime.now().isoformat()
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def detect_delphi_versions(self) -> List[Dict]:
        """
        检测已安装的 Delphi 版本

        Returns:
            Delphi 版本列表
        """
        import winreg

        versions = []

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Embarcadero\BDS")

            i = 0
            while True:
                try:
                    version_key = winreg.EnumKey(key, i)
                    i += 1

                    version_path = winreg.OpenKey(key, version_key)
                    try:
                        root_dir = winreg.QueryValueEx(version_path, "RootDir")[0]
                    except:
                        continue
                    finally:
                        winreg.CloseKey(version_path)

                    version_name = self._get_delphi_version_name(version_key)

                    versions.append({
                        "version": version_key,
                        "name": version_name,
                        "root_dir": root_dir
                    })

                except WindowsError:
                    break

            winreg.CloseKey(key)

        except Exception as e:
            logger.warning(f"检测 Delphi 版本失败: {e}")

        self.delphi_versions = versions
        return versions

    def get_latest_version(self) -> Optional[Dict]:
        """获取最新安装的 Delphi 版本"""
        if not self.delphi_versions:
            return None
        # 按版本号排序，返回最新版本
        sorted_versions = sorted(
            self.delphi_versions,
            key=lambda x: tuple(int(p) for p in x["version"].split('.')),
            reverse=True
        )
        return sorted_versions[0]

    def _get_delphi_version_name(self, version_key: str) -> str:
        """获取 Delphi 版本名称"""
        version_names = {
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
            "3.0": "Delphi 2005"
        }
        return version_names.get(version_key, f"Delphi {version_key}")

    def _load_environment_variables(self, version: str) -> Dict[str, str]:
        """
        加载指定 Delphi 版本的环境变量

        Args:
            version: Delphi 版本号 (如 "37.0")

        Returns:
            环境变量字典
        """
        import winreg

        env_vars = {}

        try:
            key_path = rf"SOFTWARE\Embarcadero\BDS\{version}\Environment Variables"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)

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
            logger.warning(f"加载环境变量失败 (版本 {version}): {e}")

        return env_vars

    def _expand_path_variables(self, path: str, env_vars: Dict[str, str]) -> str:
        """
        展开路径中的环境变量

        Args:
            path: 原始路径 (可能包含 $(VAR) 格式)
            env_vars: 环境变量字典

        Returns:
            展开后的路径
        """
        # 匹配 $(VAR) 格式的变量
        pattern = r'\$\(([^)]+)\)'

        def replace_var(match):
            var_name = match.group(1)
            if var_name in env_vars:
                return env_vars[var_name]
            # 保留未定义的变量
            return match.group(0)

        return re.sub(pattern, replace_var, path)

    def _is_delphi_system_path(self, path: str, version_key: Optional[str] = None) -> bool:
        """
        检查路径是否是 Delphi 系统路径

        Args:
            path: 路径字符串
            version_key: Delphi 版本号

        Returns:
            是否是系统路径
        """
        import os
        path_lower = path.lower()

        # 检查是否包含 Delphi 系统路径变量
        system_vars = ['$(bdsccommondir)', '$(bdslib)', '$(bds)', '$(bdsbin)', '$(bdsuserdir)']
        for var in system_vars:
            if var in path_lower:
                return True

        # 检查是否在 Delphi 安装目录下
        for version in self.delphi_versions:
            root_dir = version.get("root_dir", "")
            if root_dir and path_lower.startswith(root_dir.lower()):
                return True

        # 检查是否是公共文档下的 Delphi 系统目录
        user_docs = os.path.expanduser("~\\Documents").lower()
        delphi_common_dirs = ['imports', 'bpl', 'dcp', 'bpl\\win32', 'bpl\\win64', 'dcp\\win32', 'dcp\\win64']
        if path_lower.startswith(user_docs + '\\embarcadero\\studio\\'):
            relative = path_lower[len(user_docs + '\\embarcadero\\studio\\'):]
            for sys_dir in delphi_common_dirs:
                if relative.startswith(sys_dir):
                    return True

        return False

    def get_library_paths(self, version: Optional[str] = None) -> List[str]:
        """
        获取指定 Delphi 版本的 Library 路径

        Args:
            version: Delphi 版本号,如果为 None 则使用最新版本

        Returns:
            第三方库路径列表
        """
        import winreg

        # 选择 Delphi 版本
        if not self.delphi_versions:
            logger.error("未检测到 Delphi 版本")
            return []

        if version is None:
            selected_version = self.get_latest_version()
        else:
            selected_version = None
            for v in self.delphi_versions:
                if v["version"] == version or v["name"] == version:
                    selected_version = v
                    break

        if not selected_version:
            logger.error(f"未找到 Delphi 版本: {version}")
            return []

        version_key = selected_version["version"]
        logger.info(f"使用 Delphi 版本: {selected_version['name']} ({version_key})")

        # 加载环境变量
        env_vars = self._load_environment_variables(version_key)
        self.environment_variables = env_vars

        all_paths = []

        # 读取 BDS Library 路径
        try:
            library_key_path = rf"SOFTWARE\Embarcadero\BDS\{version_key}\Library"
            library_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, library_key_path)
            all_paths.extend(self._read_library_paths(library_key, version_key))
            winreg.CloseKey(library_key)
        except Exception as e:
            logger.debug(f"读取 BDS Library 路径失败: {e}")

        # 读取 Studio Library 路径（公共库路径）
        try:
            studio_key_path = rf"SOFTWARE\Embarcadero\Studio\{version_key}\Library"
            studio_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, studio_key_path)
            all_paths.extend(self._read_library_paths(studio_key, version_key))
            winreg.CloseKey(studio_key)
        except Exception as e:
            logger.debug(f"读取 Studio Library 路径失败: {e}")

        # 去重并保持顺序
        seen = set()
        unique_paths = []
        for path in all_paths:
            if path not in seen:
                seen.add(path)
                unique_paths.append(path)

        logger.info(f"从注册表读取到 {len(unique_paths)} 个唯一路径")

        # 展开环境变量并过滤
        thirdparty_paths = []
        for path in unique_paths:
            # 跳过 Delphi 系统路径
            if self._is_delphi_system_path(path):
                logger.debug(f"跳过 Delphi 系统路径: {path}")
                continue

            # 展开环境变量（使用 delphi_env 工具，支持更多宏）
            try:
                expanded_path = expand_delphi_path_macros(path, version=version_key)
            except Exception:
                # 回退到原有的展开方法
                expanded_path = self._expand_path_variables(path, env_vars)

            # 检查路径是否存在
            path_obj = Path(expanded_path)
            if path_obj.exists():
                thirdparty_paths.append(str(path_obj.resolve()))
            else:
                # 尝试展开 GetIt CatalogRepository 路径
                if 'CatalogRepository' in expanded_path:
                    logger.debug(f"GetIt 路径不存在: {expanded_path}")

        # 最终去重
        seen = set()
        final_paths = []
        for path in thirdparty_paths:
            if path not in seen:
                seen.add(path)
                final_paths.append(path)

        logger.info(f"过滤后得到 {len(final_paths)} 个第三方库路径")

        # 额外添加 GetIt CatalogRepository 中的组件源码路径
        try:
            getit_paths = get_catalog_repository_paths(version_key)
            for getit_path in getit_paths:
                if getit_path not in final_paths:
                    final_paths.append(getit_path)
                    logger.debug(f"添加 GetIt 组件路径: {getit_path}")
        except Exception as e:
            logger.warning(f"获取 GetIt 路径失败: {e}")

        logger.info(f"最终得到 {len(final_paths)} 个第三方库路径")

        # 保存路径列表
        self._save_paths(final_paths, selected_version)

        return final_paths

    def _read_library_paths(self, library_key, version_key: str) -> List[str]:
        """从注册表 Library 键读取路径"""
        import winreg
        paths = []
        
        # 遍历所有平台 (Win32, Win64, etc.)
        i = 0
        while True:
            try:
                platform_name = winreg.EnumKey(library_key, i)
                i += 1

                platform_key = winreg.OpenKey(library_key, platform_name)

                try:
                    # 读取 Browsing Path
                    try:
                        browsing_path = winreg.QueryValueEx(platform_key, "Browsing Path")[0]
                        if browsing_path:
                            p_list = [p.strip() for p in browsing_path.split(';') if p.strip()]
                            paths.extend(p_list)
                            logger.debug(f"平台 {platform_name} Browsing Path: {len(p_list)} 个路径")
                    except:
                        pass

                    # 读取 Search Path
                    try:
                        search_path = winreg.QueryValueEx(platform_key, "Search Path")[0]
                        if search_path:
                            p_list = [p.strip() for p in search_path.split(';') if p.strip()]
                            paths.extend(p_list)
                            logger.debug(f"平台 {platform_name} Search Path: {len(p_list)} 个路径")
                    except:
                        pass

                finally:
                    winreg.CloseKey(platform_key)

            except WindowsError:
                break
        
        return paths

    def _save_paths(self, paths: List[str], version_info: Dict):
        """保存路径列表"""
        data = {
            "version": version_info,
            "paths": paths,
            "count": len(paths),
            "saved_at": datetime.now().isoformat()
        }

        with open(self.paths_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"路径列表已保存到: {self.paths_file}")

    def build_thirdparty_knowledge_base(self, version: Optional[str] = None, force_rebuild: bool = False) -> bool:
        """
        构建第三方库知识库

        Args:
            version: Delphi 版本,如果为 None 则使用最新版本
            force_rebuild: 是否强制重建

        Returns:
            是否构建成功
        """
        import sqlite3
        
        # 获取第三方库路径
        thirdparty_paths = self.get_library_paths(version)

        if not thirdparty_paths:
            logger.warning("未找到第三方库路径")
            return False

        # 检查是否需要重建
        if not force_rebuild and self.kb_instance is not None:
            logger.info("知识库已存在,使用 force_rebuild=true 强制重建")
            return True

        # force_rebuild时关闭旧连接并清空旧数据
        if force_rebuild:
            if self.kb_instance is not None:
                self.kb_instance.close()
                self.kb_instance = None

        # 合并所有路径进行扫描
        all_source_files = []
        all_help_docs = []
        total_files = 0
        total_lines = 0

        for path in thirdparty_paths:
            logger.info(f"扫描路径: {path}")

            try:
                # 直接单线程扫描 (避免多进程问题)
                source_dir = Path(path)
                if not source_dir.exists():
                    continue
                    
                for file_path in source_dir.rglob('*.pas'):
                    try:
                        scanner = DelphiSourceScanner(str(file_path.parent), self.kb_dir)
                        file_info = scanner.analyze_file(file_path)
                        if file_info:
                            all_source_files.append(file_info)
                            total_files += 1
                            total_lines += file_info.get('line_count', 0)
                    except Exception as e:
                        logger.debug(f"分析文件失败: {file_path}, {e}")
                        
                logger.info(f"  找到 {total_files} 个源文件")

                # 扫描帮助文档
                help_docs = self._scan_help_documents(path)
                if help_docs:
                    all_help_docs.extend(help_docs)
                    logger.info(f"  找到 {len(help_docs)} 个帮助文档")

            except Exception as e:
                logger.warning(f"扫描路径失败 {path}: {e}")
                continue

        logger.info(f"总共找到 {total_files} 个源文件, {total_lines} 行代码")
        logger.info(f"总共找到 {len(all_help_docs)} 个帮助文档")

        if not all_source_files and not all_help_docs:
            logger.warning("未找到任何源文件或帮助文档")
            return False

        # 去重：使用完整路径(full_path)作为唯一标识
        seen_paths = set()
        unique_files = []
        for file_info in all_source_files:
            full_path = file_info.get('full_path', '')
            if full_path and full_path not in seen_paths:
                seen_paths.add(full_path)
                unique_files.append(file_info)

        unique_count = len(unique_files)
        if unique_count < total_files:
            logger.info(f"去重后剩余 {unique_count} 个唯一文件")

        # 直接保存到 SQLite (统一Schema)
        db_file = self.kb_dir / "knowledge.sqlite"
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        
        current_time = datetime.now().timestamp()
        
        # force_rebuild时清空旧数据
        if force_rebuild:
            try:
                cursor.execute("DELETE FROM files")
                cursor.execute("DELETE FROM vocabularies")
                cursor.execute("DELETE FROM vocabulary")
                cursor.execute("DELETE FROM metadata")
                conn.commit()
                logger.info("已清空旧知识库数据")
            except Exception:
                pass
        
        # 增量构建：加载现有文件的hash
        existing_files = {}
        if not force_rebuild:
            cursor.execute("SELECT id, full_path, hash FROM files")
            for row in cursor.fetchall():
                existing_files[row[1]] = {'id': row[0], 'hash': row[2]}
            logger.info(f"现有文件数: {len(existing_files)}")
        
        # 增量构建：加载现有文件的hash
        existing_files = {}
        if not force_rebuild:
            cursor.execute("SELECT id, full_path, hash FROM files")
            for row in cursor.fetchall():
                existing_files[row[1]] = {'id': row[0], 'hash': row[2]}
            logger.info(f"现有文件数: {len(existing_files)}")
        
        # 确保表存在
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_path TEXT,
                relative_path TEXT,
                extension TEXT,
                size INTEGER,
                line_count INTEGER,
                hash TEXT,
                last_modified TEXT,
                category TEXT,
                units_defined TEXT,
                units_imported TEXT,
                description TEXT,
                scan_timestamp REAL,
                created_at REAL,
                updated_at REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vocabularies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                name TEXT,
                name_lower TEXT,
                name_lower_rev TEXT,
                file_id INTEGER,
                line INTEGER,
                base_class TEXT,
                description TEXT,
                vector BLOB,
                vector_status TEXT,
                attributes TEXT,
                created_at REAL,
                updated_at REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at REAL
            )
        """)
        
        # 插入源文件
        logger.info("保存源文件到数据库...")
        batch_size = 1000
        skipped_files = 0
        updated_files = 0
        new_files = 0
        deleted_files = 0
        
        # 构建新文件路径集合（用于检测已删除的文件）
        new_file_paths = set(file_info.get('full_path', '') for file_info in unique_files)
        
        # 检测已删除的文件（保留，仅记录日志）
        if not force_rebuild:
            for old_path in existing_files:
                if old_path not in new_file_paths:
                    deleted_files += 1
            if deleted_files > 0:
                logger.info(f"检测到 {deleted_files} 个文件已删除（保留记录）")
        
        for i, file_info in enumerate(unique_files):
            full_path = file_info.get('full_path', '')
            new_hash = file_info.get('hash', '')
            
            # 增量构建：检查文件是否变更
            if not force_rebuild and full_path in existing_files:
                existing_info = existing_files[full_path]
                if existing_info['hash'] == new_hash:
                    # 2. 已存在未变更，直接跳过
                    skipped_files += 1
                    continue
                
                # 3. 已存在已变更，删除旧的vocabularies和FTS信息
                old_file_id = existing_info['id']
                cursor.execute("DELETE FROM vocabularies WHERE file_id = ?", (old_file_id,))
                # 注意：第三方库知识库暂无FTS索引，如有需要在此添加
                updated_files += 1
            else:
                # 1. 不存在，直接插入
                new_files += 1
            
            # 转换 units 和 uses 为字符串
            units = file_info.get('units', [])
            if isinstance(units, list):
                units = ','.join(units)
            uses = file_info.get('uses', [])
            if isinstance(uses, list):
                uses = ','.join(uses)
            
            cursor.execute("""
                INSERT OR REPLACE INTO files (full_path, relative_path, extension, size, line_count, hash, 
                    last_modified, category, units_defined, units_imported, description, 
                    scan_timestamp, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                full_path,
                file_info.get('path', ''),
                file_info.get('extension', '.pas'),
                file_info.get('size', 0),
                file_info.get('line_count', 0),
                file_info.get('hash', ''),
                file_info.get('last_modified', ''),
                'source',
                str(units) if units else '',
                str(uses) if uses else '',
                file_info.get('description', '')[:500],
                current_time,
                current_time,
                current_time
            ))
            
            file_id = cursor.lastrowid
            
            # 插入 vocabularies (类)
            for cls in file_info.get('classes', []):
                cursor.execute("""
INSERT INTO vocabularies (type, name, name_lower, name_lower_rev, file_id, line, base_class, 
    description, vector, vector_status, attributes, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    'class', cls.get('name', ''), cls.get('name', '').lower() if cls.get('name') else '',
                    cls.get('name', '').lower()[::-1] if cls.get('name') else '',
                    file_id, cls.get('line', 0), cls.get('base_class', ''), cls.get('definition', ''),
                    None, 'pending', None, current_time, current_time
                ))
            
            # 插入 vocabularies (函数)
            for func in file_info.get('functions', []):
                cursor.execute("""
INSERT INTO vocabularies (type, name, name_lower, name_lower_rev, file_id, line, base_class, 
    description, vector, vector_status, attributes, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    'function', func.get('name', ''), func.get('name', '').lower() if func.get('name') else '',
                    func.get('name', '').lower()[::-1] if func.get('name') else '',
                    file_id, func.get('line', 0), '', func.get('definition', ''),
                    None, 'pending', None, current_time, current_time
                ))
            
            # 插入 vocabularies (常量)
            for const in file_info.get('constants', []):
                cursor.execute("""
INSERT INTO vocabularies (type, name, name_lower, name_lower_rev, file_id, line, base_class, 
    description, vector, vector_status, attributes, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    'constant', const.get('name', ''), const.get('name', '').lower() if const.get('name') else '',
                    const.get('name', '').lower()[::-1] if const.get('name') else '',
                    file_id, const.get('line', 0), '', const.get('definition', ''),
                    None, 'pending', None, current_time, current_time
                ))
            
            if (i + 1) % batch_size == 0:
                conn.commit()
                logger.info(f"  已处理 {i+1}/{len(unique_files)} 源文件")
        
        if not force_rebuild:
            logger.info(f"增量构建: 新增 {new_files} 个, 更新 {updated_files} 个, 跳过 {skipped_files} 个, 删除 {deleted_files} 个（保留）")

        # 插入帮助文档
        if all_help_docs:
            logger.info("保存帮助文档到数据库...")
            for help_doc in all_help_docs:
                full_path = help_doc.get('full_path', '')
                
                # 增量构建：删除已存在的帮助文档
                if not force_rebuild and full_path in existing_files:
                    old_file_id = existing_files[full_path]['id']
                    cursor.execute("DELETE FROM vocabularies WHERE file_id = ?", (old_file_id,))
                
                cursor.execute("""
                    INSERT OR REPLACE INTO files (full_path, relative_path, extension, size, line_count, hash, 
                        last_modified, category, units_defined, units_imported, description, 
                        scan_timestamp, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    full_path,
                    help_doc.get('path', ''),
                    help_doc.get('extension', '.html'),
                    help_doc.get('size', 0),
                    help_doc.get('line_count', 0),
                    '',
                    help_doc.get('last_modified', ''),
                    'help',
                    '',
                    '',
                    help_doc.get('title', ''),
                    current_time,
                    current_time,
                    current_time
                ))
                
                file_id = cursor.lastrowid
                
                # 插入 vocabularies (类)
                for cls in help_doc.get('classes', []):
                    cursor.execute("""
                        INSERT INTO vocabularies (type, name, name_lower, name_lower_rev, file_id, line, base_class, 
                            description, vector, vector_status, attributes, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        'class', cls.get('name', ''), cls.get('name', '').lower() if cls.get('name') else '',
                        cls.get('name', '').lower()[::-1] if cls.get('name') else '',
                        file_id, 0, cls.get('base_class', ''), cls.get('description', ''),
                        None, 'pending', None, current_time, current_time
                    ))
                
                # 插入 vocabularies (函数)
                for func in help_doc.get('functions', []):
                    cursor.execute("""
                        INSERT INTO vocabularies (type, name, name_lower, name_lower_rev, file_id, line, base_class, 
                            description, vector, vector_status, attributes, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        'function', func.get('name', ''), func.get('name', '').lower() if func.get('name') else '',
                        func.get('name', '').lower()[::-1] if func.get('name') else '',
                        file_id, 0, '', func.get('description', ''),
                        None, 'pending', None, current_time, current_time
                    ))
                
                # 插入 vocabularies (属性)
                for prop in help_doc.get('properties', []):
                    cursor.execute("""
                        INSERT INTO vocabularies (type, name, name_lower, name_lower_rev, file_id, line, base_class, 
                            description, vector, vector_status, attributes, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        'property', prop.get('name', ''), prop.get('name', '').lower() if prop.get('name') else '',
                        prop.get('name', '').lower()[::-1] if prop.get('name') else '',
                        file_id, 0, '', prop.get('description', ''),
                        None, 'pending', None, current_time, current_time
                    ))
                
                # 插入 vocabularies (事件)
                for event in help_doc.get('events', []):
                    cursor.execute("""
                        INSERT INTO vocabularies (type, name, name_lower, name_lower_rev, file_id, line, base_class, 
                            description, vector, vector_status, attributes, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        'event', event.get('name', ''), event.get('name', '').lower() if event.get('name') else '',
                        event.get('name', '').lower()[::-1] if event.get('name') else '',
                        file_id, 0, '', event.get('description', ''),
                        None, 'pending', None, current_time, current_time
                    ))

            conn.commit()
        
        # 统计
        cursor.execute("SELECT COUNT(*) FROM files WHERE category='source'")
        source_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM files WHERE category='help'")
        help_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='class'")
        class_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='function'")
        func_count = cursor.fetchone()[0]
        
        # 保存元数据
        cursor.execute("DELETE FROM metadata")
        cursor.execute("INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?)", 
            ('total_files', str(source_count + help_count), current_time))
        cursor.execute("INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?)", 
            ('source_files', str(source_count), current_time))
        cursor.execute("INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?)", 
            ('help_docs', str(help_count), current_time))
        cursor.execute("INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?)", 
            ('total_classes', str(class_count), current_time))
        cursor.execute("INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?)", 
            ('total_functions', str(func_count), current_time))
        cursor.execute("INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?)", 
            ('build_time', datetime.now().isoformat(), current_time))
        # 记录 schema 版本号
        from src.services.knowledge_base import set_schema_version_in_db
        set_schema_version_in_db(cursor)
        
        conn.commit()
        conn.close()
        
        logger.info(f"知识库构建完成!")
        logger.info(f"  源文件: {source_count}")
        logger.info(f"  帮助文档: {help_count}")
        logger.info(f"  类: {class_count}")
        logger.info(f"  函数: {func_count}")

        # 更新元数据
        self.metadata["total_paths"] = len(thirdparty_paths)
        self.metadata["scanned_paths"] = thirdparty_paths
        self._save_metadata()

        return True

    def _scan_help_documents(self, base_path: str) -> List[Dict]:
        """
        扫描帮助文档 (HTML/CHM)
        
        Args:
            base_path: 基础路径
            
        Returns:
            帮助文档列表
        """
        help_docs = []
        
        # 扫描 HTML 文件 - 更宽松的扫描
        for root, dirs, files in os.walk(base_path):
            # 跳过隐藏目录和常见无关目录
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in [
                'node_modules', 'vendor', 'lib', 'dist', 'bin', 'obj', '__pycache__'
            ]]
            
            for file in files:
                if file.lower().endswith(('.html', '.htm')):
                    # 跳过索引文件
                    if file.lower() in ['index.html', 'index.htm', 'toc.html', 'contents.html']:
                        continue
                    
                    file_path = os.path.join(root, file)
                    try:
                        # 只处理较小的文件 (帮助文档通常不会太大)
                        if os.path.getsize(file_path) > 5 * 1024 * 1024:  # 5MB
                            continue
                            
                        doc = self._parse_html_help(file_path, base_path)
                        if doc and (doc.get('classes') or doc.get('functions')):
                            help_docs.append(doc)
                    except Exception as e:
                        logger.debug(f"解析帮助文档失败: {file_path}, {e}")
        
        return help_docs

    def _parse_html_help(self, file_path: str, base_path: str) -> Optional[Dict]:
        """
        解析 HTML 帮助文档
        
        Args:
            file_path: 文件路径
            base_path: 基础路径
            
        Returns:
            解析后的文档
        """
        try:
            from bs4 import BeautifulSoup
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # 提取标题
            title = ''
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text().strip()
            if not title:
                title_elem = soup.find('title')
                if title_elem:
                    title = title_elem.get_text().strip()
            if not title:
                title = os.path.basename(file_path)
            
            # 提取类名 (从标题或内容中)
            classes = []
            functions = []
            properties = []
            events = []
            
            # 常见模式: TClassName, TInterfaceName
            import re
            class_pattern = re.compile(r'\b(T[A-Z][A-Za-z0-9_]+)\b')
            
            # 从标题提取
            if title:
                matches = class_pattern.findall(title)
                for match in matches:
                    if match not in [c['name'] for c in classes]:
                        classes.append({
                            'name': match,
                            'base_class': '',
                            'description': title
                        })
            
            # 从内容提取
            text = soup.get_text()
            matches = class_pattern.findall(text)
            for match in matches:
                if match not in [c['name'] for c in classes]:
                    classes.append({
                        'name': match,
                        'base_class': '',
                        'description': ''
                    })
            
            # 提取函数/方法
            func_pattern = re.compile(r'\b([A-Z][a-zA-Z0-9_]+)\s*\([^)]*\)\s*(?:of\s+object)?;?', re.IGNORECASE)
            func_matches = func_pattern.findall(text)
            for func_name in func_matches[:20]:  # 限制数量
                if func_name not in [f['name'] for f in functions]:
                    functions.append({
                        'name': func_name,
                        'description': ''
                    })
            
            # 提取属性
            prop_pattern = re.compile(r'\bproperty\s+([A-Za-z_][A-Za-z0-9_]*)', re.IGNORECASE)
            prop_matches = prop_pattern.findall(text)
            for prop_name in prop_matches[:20]:
                if prop_name not in [p['name'] for p in properties]:
                    properties.append({
                        'name': prop_name,
                        'description': ''
                    })
            
            # 提取事件
            event_pattern = re.compile(r'\bOn([A-Z][a-zA-Z0-9_]+)', re.IGNORECASE)
            event_matches = event_pattern.findall(text)
            for event_name in event_matches[:20]:
                full_name = 'On' + event_name
                if full_name not in [e['name'] for e in events]:
                    events.append({
                        'name': full_name,
                        'description': ''
                    })
            
            stat = os.stat(file_path)
            
            return {
                'full_path': file_path,
                'path': os.path.relpath(file_path, base_path),
                'extension': '.html',
                'size': stat.st_size,
                'line_count': content.count('\n'),
                'last_modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'title': title,
                'classes': classes,
                'functions': functions,
                'properties': properties,
                'events': events
            }
            
        except Exception as e:
            logger.debug(f"解析HTML失败: {file_path}, {e}")
            return None

    def load_knowledge_base(self) -> bool:
        """
        加载知识库

        Returns:
            是否加载成功
        """
        try:
            if self.kb_instance is None:
                self.kb_instance = SQLiteVectorKnowledgeBase(str(self.kb_dir))
            return True
        except Exception as e:
            logger.error(f"加载知识库失败: {e}")
            return False

    def search_by_class_name(self, class_name: str) -> List[Dict]:
        """根据类名搜索"""
        if not self.load_knowledge_base():
            return []
        results = self.kb_instance.search_by_name(class_name)
        return [r for r in results if r.get('kind_code', '') == 'TC']

    def search_by_function_name(self, function_name: str) -> List[Dict]:
        """根据函数名搜索"""
        if not self.load_knowledge_base():
            return []
        results = self.kb_instance.search_by_name(function_name)
        return [r for r in results if r.get('kind_code', '') in ('FF', 'FP')]

    def semantic_search_classes(self, query: str, top_k: int = 10) -> List:
        """语义搜索类"""
        if not self.load_knowledge_base():
            return []
        return self.kb_instance.semantic_search_classes(query, top_k)

    def semantic_search_functions(self, query: str, top_k: int = 10) -> List:
        """语义搜索函数"""
        if not self.load_knowledge_base():
            return []
        return self.kb_instance.semantic_search_functions(query, top_k)

    def get_statistics(self) -> Dict:
        """获取知识库统计信息"""
        import sqlite3
        
        if not self.load_knowledge_base():
            return {}

        db_file = self.kb_dir / "knowledge.sqlite"
        if not db_file.exists():
            return {}

        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()

        stats = {}
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            
            if 'classes' in tables:
                cursor.execute("SELECT COUNT(*) FROM classes")
                stats["classes"] = cursor.fetchone()[0]

            if 'functions' in tables:
                cursor.execute("SELECT COUNT(*) FROM functions")
                stats["functions"] = cursor.fetchone()[0]

            if 'files' in tables:
                cursor.execute("SELECT COUNT(*) FROM files")
                stats["files"] = cursor.fetchone()[0]

            if 'vocabulary' in tables:
                cursor.execute("SELECT COUNT(*) FROM vocabulary")
                stats["vocabulary_size"] = cursor.fetchone()[0]
            
            stats["database_size_mb"] = db_file.stat().st_size / (1024 * 1024)

        finally:
            conn.close()

        # 添加路径信息
        if self.paths_file.exists():
            try:
                with open(self.paths_file, 'r', encoding='utf-8') as f:
                    paths_data = json.load(f)
                    stats["thirdparty_paths_count"] = paths_data.get("count", 0)
                    stats["delphi_version"] = paths_data.get("version", {}).get("name", "Unknown")
            except:
                pass

        return stats

    def close(self):
        """关闭知识库连接"""
        if self.kb_instance:
            self.kb_instance.close()
            self.kb_instance = None
