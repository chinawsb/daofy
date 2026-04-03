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
        (self.kb_dir / "index").mkdir(exist_ok=True)
        (self.kb_dir / "data").mkdir(exist_ok=True)

        # 元数据文件
        self.metadata_file = self.kb_dir / "thirdparty_metadata.json"
        self.paths_file = self.kb_dir / "index" / "thirdparty_paths.json"

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
        # 获取第三方库路径
        thirdparty_paths = self.get_library_paths(version)

        if not thirdparty_paths:
            logger.warning("未找到第三方库路径")
            return False

        # 检查是否需要重建
        if not force_rebuild and self.kb_instance is not None:
            logger.info("知识库已存在,使用 force_rebuild=true 强制重建")
            return True

        # 合并所有路径进行扫描
        all_source_files = []
        total_files = 0
        total_lines = 0

        for path in thirdparty_paths:
            logger.info(f"扫描路径: {path}")

            try:
                # 创建临时扫描器
                scanner = DelphiSourceScanner(path, self.kb_dir)

                # 扫描目录
                result = scanner.scan_directory()

                if result and result.get('files'):
                    file_count = len(result['files'])
                    total_files += file_count
                    # 计算总行数
                    for file_info in result['files']:
                        total_lines += file_info.get('line_count', 0)
                    all_source_files.extend(result['files'])
                    logger.info(f"  找到 {file_count} 个源文件")

            except Exception as e:
                logger.warning(f"扫描路径失败 {path}: {e}")
                continue

        logger.info(f"总共找到 {total_files} 个源文件, {total_lines} 行代码")

        if not all_source_files:
            logger.warning("未找到任何源文件")
            return False

        # 去重：使用相对路径(path)作为唯一标识（因为SQLite中path是主键）
        seen_paths = set()
        unique_files = []
        for file_info in all_source_files:
            # 使用相对路径作为唯一标识
            rel_path = file_info.get('path', '')
            if rel_path and rel_path not in seen_paths:
                seen_paths.add(rel_path)
                unique_files.append(file_info)
            elif not rel_path:
                # 如果没有相对路径，使用完整路径
                full_path = file_info.get('full_path', '')
                if full_path and full_path not in seen_paths:
                    seen_paths.add(full_path)
                    unique_files.append(file_info)

        unique_count = len(unique_files)
        if unique_count < total_files:
            logger.info(f"去重后剩余 {unique_count} 个唯一文件")

        # 保存合并的索引 (使用 source_index.json 以兼容 SQLiteVectorKnowledgeBase)
        scan_result = {
            'files': unique_files,
            'statistics': {
                'total_files': unique_count,
                'total_lines': total_lines,
                'total_paths': len(thirdparty_paths),
                'scan_time': datetime.now().isoformat()
            }
        }

        # 保存索引 (使用标准文件名)
        index_file = self.kb_dir / "index" / "source_index.json"
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(scan_result, f, ensure_ascii=False, indent=2)

        logger.info(f"索引已保存到: {index_file}")

        # 创建 metadata.json (SQLiteVectorKnowledgeBase 需要)
        metadata = {
            "name": "Delphi ThirdParty Knowledge Base",
            "version": version if version else (self.delphi_versions[0]["version"] if self.delphi_versions else "unknown"),
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "source_directory": str(self.kb_dir / "data"),
            "source_type": "thirdparty",
            "statistics": {
                "total_files": total_files,
                "total_paths": len(thirdparty_paths),
                "scan_time": datetime.now().isoformat()
            }
        }

        metadata_file = self.kb_dir / "index" / "metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"元数据已保存到: {metadata_file}")

        # 构建 SQLite 向量索引
        logger.info("开始构建 SQLite 向量索引...")
        start_time = time.time()

        try:
            self.kb_instance = SQLiteVectorKnowledgeBase(str(self.kb_dir), force_rebuild=force_rebuild)
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"索引构建完成! 耗时: {elapsed:.2f}ms")
        except Exception as e:
            logger.error(f"构建向量索引失败: {e}")
            return False

        # 更新元数据
        self.metadata["total_paths"] = len(thirdparty_paths)
        self.metadata["scanned_paths"] = thirdparty_paths
        self._save_metadata()

        return True

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
        return self.kb_instance.search_by_class_name(class_name)

    def search_by_function_name(self, function_name: str) -> List[Dict]:
        """根据函数名搜索"""
        if not self.load_knowledge_base():
            return []
        return self.kb_instance.search_by_function_name(function_name)

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
        if not self.load_knowledge_base():
            return {}

        import sqlite3
        db_file = self.kb_dir / "knowledge.sqlite"
        if not db_file.exists():
            return {}

        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()

        stats = {}
        try:
            cursor.execute("SELECT COUNT(*) FROM classes")
            stats["classes"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM functions")
            stats["functions"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM files")
            stats["files"] = cursor.fetchone()[0]

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
