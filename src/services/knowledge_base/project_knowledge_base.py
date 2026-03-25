"""
项目知识库服务

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

为用户项目提供知识库功能:
1. 从 .dproj 文件读取三方库目录并构建知识库
2. 为项目源码构建知识库,支持增量更新
"""

import os
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set, Callable
from datetime import datetime

from .scan_delphi_sources import DelphiSourceScanner
from .sqlite_vector_query_knowledge_base import SQLiteVectorKnowledgeBase
from ...utils.dproj_parser import DprojParser
from ...utils.logger import get_logger

logger = get_logger(__name__)


class ProjectKnowledgeBase:
    """项目知识库管理器"""

    def __init__(self, project_path: str, progress_callback: Optional[Callable] = None):
        """
        初始化项目知识库

        Args:
            project_path: 项目文件路径 (.dproj 或 .dpr)
            progress_callback: 进度回调函数
        """
        self.project_path = Path(project_path)
        self.project_dir = self.project_path.parent
        self.project_name = self.project_path.stem
        self.progress_callback = progress_callback

        # 项目知识库目录
        self.kb_dir = self.project_dir / ".delphi-kb"
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        (self.kb_dir / "index").mkdir(exist_ok=True)
        (self.kb_dir / "data").mkdir(exist_ok=True)

        # 知识库实例
        self.project_kb: Optional[SQLiteVectorKnowledgeBase] = None
        self.thirdparty_kb: Optional[SQLiteVectorKnowledgeBase] = None

        # 元数据文件
        self.metadata_file = self.kb_dir / "project_metadata.json"

        # 加载元数据
        self.metadata = self._load_metadata()

        logger.info(f"项目知识库初始化: {self.project_name}")

    def _load_metadata(self) -> Dict:
        """加载项目元数据"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载元数据失败: {e}")

        return {
            "project_name": self.project_name,
            "project_path": str(self.project_path),
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "thirdparty_paths": [],
            "source_hash": None,
            "thirdparty_hash": None
        }

    def _save_metadata(self):
        """保存项目元数据"""
        self.metadata["last_updated"] = datetime.now().isoformat()
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def _get_delphi_install_paths(self) -> Set[str]:
        """
        获取 Delphi 安装路径列表

        Returns:
            Delphi 安装路径集合
        """
        delphi_paths = set()

        try:
            import winreg

            # 打开 Delphi 注册表键
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Embarcadero\BDS")

            # 遍历所有版本
            i = 0
            while True:
                try:
                    version_key = winreg.EnumKey(key, i)
                    i += 1

                    # 获取版本信息
                    version_path = winreg.OpenKey(key, version_key)
                    try:
                        root_dir = winreg.QueryValueEx(version_path, "RootDir")[0]
                        if root_dir:
                            # 添加 Delphi 安装路径及其子目录
                            delphi_paths.add(Path(root_dir).resolve())
                    except:
                        pass
                    finally:
                        winreg.CloseKey(version_path)

                except WindowsError:
                    break

            winreg.CloseKey(key)

        except Exception as e:
            logger.warning(f"获取 Delphi 安装路径失败: {e}")

        return delphi_paths

    def get_thirdparty_paths_from_dproj(self) -> List[str]:
        """
        从 .dproj 文件中提取三方库路径

        Returns:
            三方库路径列表
        """
        if self.project_path.suffix.lower() != '.dproj':
            logger.warning("项目文件不是 .dproj 格式,无法提取三方库路径")
            return []

        parser = DprojParser(str(self.project_path))
        if not parser.parse():
            logger.error("解析 .dproj 文件失败")
            return []

        # 获取单元搜索路径
        unit_paths = parser.get_unit_search_paths()

        # 获取 Delphi 安装路径（用于排除）
        delphi_install_paths = self._get_delphi_install_paths()

        # 过滤出三方库路径 (排除项目自身目录和 Delphi 安装目录)
        thirdparty_paths = []
        for path in unit_paths:
            path_obj = Path(path)

            # 检查路径是否存在
            if not path_obj.exists():
                continue

            # 解析为绝对路径
            path_obj = path_obj.resolve()

            # 检查是否在 Delphi 安装目录下
            is_delphi_path = False
            for delphi_path in delphi_install_paths:
                try:
                    path_obj.relative_to(delphi_path)
                    is_delphi_path = True
                    break
                except ValueError:
                    pass

            if is_delphi_path:
                # 跳过 Delphi 安装目录下的路径
                continue

            # 检查是否在项目目录外
            try:
                # 相对路径检查
                path_obj.relative_to(self.project_dir)
            except ValueError:
                # 在项目目录外,是三方库
                thirdparty_paths.append(str(path_obj))
            else:
                # 在项目目录内,检查是否是常见的三方库目录名
                path_lower = str(path_obj).lower()
                thirdparty_keywords = ['thirdpart', 'thirdparty', 'vendor', 'lib', 'libs', 'packages', 'components']
                if any(kw in path_lower for kw in thirdparty_keywords):
                    thirdparty_paths.append(str(path_obj))

        logger.info(f"从 .dproj 提取到 {len(thirdparty_paths)} 个三方库路径")
        return thirdparty_paths

    def _calculate_paths_hash(self, paths: List[str]) -> str:
        """计算路径列表的哈希值"""
        hash_str = ";".join(sorted(paths))
        return hashlib.md5(hash_str.encode()).hexdigest()

    def _calculate_source_hash(self, source_dir: Path, extensions: Set[str] = None) -> str:
        """
        计算源码目录的哈希值 (基于文件修改时间和大小)

        Args:
            source_dir: 源码目录
            extensions: 文件扩展名集合

        Returns:
            哈希值
        """
        if extensions is None:
            extensions = {'.pas', '.dpr', '.dpk', '.inc', '.hpp', '.h'}

        hash_parts = []
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix.lower() in extensions:
                    try:
                        stat = file_path.stat()
                        hash_parts.append(f"{file_path}:{stat.st_mtime}:{stat.st_size}")
                    except Exception:
                        pass

        hash_str = "|".join(sorted(hash_parts))
        return hashlib.md5(hash_str.encode()).hexdigest()

    def build_thirdparty_knowledge_base(self, force_rebuild: bool = False) -> bool:
        """
        构建三方库知识库

        Args:
            force_rebuild: 是否强制重建

        Returns:
            是否构建成功
        """
        # 获取三方库路径
        thirdparty_paths = self.get_thirdparty_paths_from_dproj()

        if not thirdparty_paths:
            logger.warning("未找到三方库路径")
            return False

        # 计算哈希值
        current_hash = self._calculate_paths_hash(thirdparty_paths)
        cached_hash = self.metadata.get("thirdparty_hash")

        # 检查是否需要重建
        if not force_rebuild and cached_hash == current_hash:
            # 检查知识库是否存在
            thirdparty_kb_dir = self.kb_dir / "thirdparty"
            if (thirdparty_kb_dir / "index" / "source_index.json").exists():
                logger.info("三方库知识库已是最新,跳过构建")
                return True

        logger.info(f"开始构建三方库知识库,共 {len(thirdparty_paths)} 个目录")

        # 合并所有三方库源码到一个临时目录或直接扫描
        thirdparty_kb_dir = self.kb_dir / "thirdparty"
        thirdparty_kb_dir.mkdir(parents=True, exist_ok=True)

        # 扫描所有三方库目录
        all_files = []
        seen_paths = set()  # 用于去重

        for path in thirdparty_paths:
            scanner = DelphiSourceScanner(path, str(thirdparty_kb_dir), self.progress_callback)
            scan_result = scanner.scan_directory()

            # 为每个文件添加唯一路径标识，避免重复
            for file_info in scan_result['files']:
                # 使用完整路径作为唯一标识
                full_path = file_info.get('full_path', '')
                if full_path and full_path not in seen_paths:
                    seen_paths.add(full_path)
                    # 使用完整路径的哈希作为相对路径，确保唯一性
                    path_hash = hashlib.md5(full_path.encode()).hexdigest()[:8]
                    file_info['path'] = f"{path_hash}/{file_info['path']}"
                    all_files.append(file_info)

        # 合并结果
        combined_result = {
            'files': all_files,
            'statistics': {
                'total_files': len(all_files),
                'total_lines': sum(f.get('line_count', 0) for f in all_files),
                'scan_time': datetime.now().isoformat()
            }
        }

        # 保存合并后的索引
        index_file = thirdparty_kb_dir / "index" / "source_index.json"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(combined_result, f, ensure_ascii=False, indent=2)

        # 保存元数据
        metadata_file = thirdparty_kb_dir / "index" / "metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump({
                'version': '1.0',
                'source_directory': ';'.join(thirdparty_paths),
                'scan_date': datetime.now().isoformat(),
                'statistics': combined_result['statistics']
            }, f, ensure_ascii=False, indent=2)

        # 构建向量索引
        logger.info("构建三方库向量索引...")
        self.thirdparty_kb = SQLiteVectorKnowledgeBase(str(thirdparty_kb_dir), force_rebuild=True)

        # 更新元数据
        self.metadata["thirdparty_paths"] = thirdparty_paths
        self.metadata["thirdparty_hash"] = current_hash
        self._save_metadata()

        logger.info("三方库知识库构建完成")
        return True

    def build_project_knowledge_base(self, force_rebuild: bool = False) -> bool:
        """
        构建项目源码知识库

        Args:
            force_rebuild: 是否强制重建

        Returns:
            是否构建成功
        """
        # 计算源码哈希
        current_hash = self._calculate_source_hash(self.project_dir)
        cached_hash = self.metadata.get("source_hash")

        # 检查是否需要重建
        if not force_rebuild and cached_hash == current_hash:
            # 检查知识库是否存在
            project_kb_dir = self.kb_dir / "project"
            if (project_kb_dir / "index" / "source_index.json").exists():
                logger.info("项目源码知识库已是最新,跳过构建")
                return True

        logger.info("开始构建项目源码知识库")

        # 项目源码知识库目录
        project_kb_dir = self.kb_dir / "project"
        project_kb_dir.mkdir(parents=True, exist_ok=True)

        # 扫描项目源码
        scanner = DelphiSourceScanner(str(self.project_dir), str(project_kb_dir), self.progress_callback)
        scan_result = scanner.scan_directory()

        # 保存索引
        scanner.save_index(scan_result)

        # 构建向量索引
        logger.info("构建项目源码向量索引...")
        self.project_kb = SQLiteVectorKnowledgeBase(str(project_kb_dir), force_rebuild=True)

        # 更新元数据
        self.metadata["source_hash"] = current_hash
        self._save_metadata()

        logger.info("项目源码知识库构建完成")
        return True

    def check_and_update_project_kb(self) -> bool:
        """
        检查项目源码是否有变动,如有则更新知识库

        Returns:
            是否需要更新
        """
        current_hash = self._calculate_source_hash(self.project_dir)
        cached_hash = self.metadata.get("source_hash")

        if current_hash != cached_hash:
            logger.info("检测到项目源码变动,更新知识库...")
            return self.build_project_knowledge_base(force_rebuild=True)

        return False

    def load_knowledge_bases(self) -> bool:
        """
        加载知识库

        Returns:
            是否加载成功
        """
        try:
            # 加载项目源码知识库
            project_kb_dir = self.kb_dir / "project"
            if (project_kb_dir / "index" / "source_index.json").exists():
                self.project_kb = SQLiteVectorKnowledgeBase(str(project_kb_dir))
                logger.info("项目源码知识库加载成功")

            # 加载三方库知识库
            thirdparty_kb_dir = self.kb_dir / "thirdparty"
            if (thirdparty_kb_dir / "index" / "source_index.json").exists():
                self.thirdparty_kb = SQLiteVectorKnowledgeBase(str(thirdparty_kb_dir))
                logger.info("三方库知识库加载成功")

            return True
        except Exception as e:
            logger.error(f"加载知识库失败: {e}")
            return False

    def search_class(self, class_name: str, search_in: str = "all") -> List[Dict]:
        """
        搜索类

        Args:
            class_name: 类名
            search_in: 搜索范围 ("project", "thirdparty", "all")

        Returns:
            搜索结果
        """
        results = []

        # 检查并更新项目知识库
        self.check_and_update_project_kb()

        if search_in in ("project", "all") and self.project_kb:
            results.extend(self.project_kb.search_by_class_name(class_name))

        if search_in in ("thirdparty", "all") and self.thirdparty_kb:
            results.extend(self.thirdparty_kb.search_by_class_name(class_name))

        return results

    def search_function(self, function_name: str, search_in: str = "all") -> List[Dict]:
        """
        搜索函数

        Args:
            function_name: 函数名
            search_in: 搜索范围 ("project", "thirdparty", "all")

        Returns:
            搜索结果
        """
        results = []

        # 检查并更新项目知识库
        self.check_and_update_project_kb()

        if search_in in ("project", "all") and self.project_kb:
            results.extend(self.project_kb.search_by_function_name(function_name))

        if search_in in ("thirdparty", "all") and self.thirdparty_kb:
            results.extend(self.thirdparty_kb.search_by_function_name(function_name))

        return results

    def semantic_search(self, query: str, top_k: int = 10, search_in: str = "all") -> Dict:
        """
        语义搜索

        Args:
            query: 搜索查询
            top_k: 返回结果数量
            search_in: 搜索范围 ("project", "thirdparty", "all")

        Returns:
            搜索结果 {"classes": [...], "functions": [...]}
        """
        # 检查并更新项目知识库
        self.check_and_update_project_kb()

        result = {
            "classes": [],
            "functions": []
        }

        if search_in in ("project", "all") and self.project_kb:
            class_results = self.project_kb.semantic_search_classes(query, top_k)
            func_results = self.project_kb.semantic_search_functions(query, top_k)

            for class_name, score in class_results:
                exact = self.project_kb.search_by_class_name(class_name)
                if exact:
                    result["classes"].append({
                        "source": "project",
                        "score": score,
                        "data": exact[0]
                    })

            for func_name, score in func_results:
                exact = self.project_kb.search_by_function_name(func_name)
                if exact:
                    result["functions"].append({
                        "source": "project",
                        "score": score,
                        "data": exact[0]
                    })

        if search_in in ("thirdparty", "all") and self.thirdparty_kb:
            class_results = self.thirdparty_kb.semantic_search_classes(query, top_k)
            func_results = self.thirdparty_kb.semantic_search_functions(query, top_k)

            for class_name, score in class_results:
                exact = self.thirdparty_kb.search_by_class_name(class_name)
                if exact:
                    result["classes"].append({
                        "source": "thirdparty",
                        "score": score,
                        "data": exact[0]
                    })

            for func_name, score in func_results:
                exact = self.thirdparty_kb.search_by_function_name(func_name)
                if exact:
                    result["functions"].append({
                        "source": "thirdparty",
                        "score": score,
                        "data": exact[0]
                    })

        # 按相似度排序
        result["classes"].sort(key=lambda x: x["score"], reverse=True)
        result["functions"].sort(key=lambda x: x["score"], reverse=True)

        return result

    def get_statistics(self) -> Dict:
        """
        获取知识库统计信息

        Returns:
            统计信息
        """
        stats = {
            "project": None,
            "thirdparty": None
        }

        if self.project_kb:
            try:
                import sqlite3
                db_file = Path(self.project_kb.db_file)
                if db_file.exists():
                    conn = sqlite3.connect(str(db_file))
                    cursor = conn.cursor()

                    project_stats = {}
                    cursor.execute("SELECT COUNT(*) FROM classes")
                    project_stats["classes"] = cursor.fetchone()[0]

                    cursor.execute("SELECT COUNT(*) FROM functions")
                    project_stats["functions"] = cursor.fetchone()[0]

                    cursor.execute("SELECT COUNT(*) FROM files")
                    project_stats["files"] = cursor.fetchone()[0]

                    project_stats["database_size_mb"] = db_file.stat().st_size / (1024 * 1024)

                    conn.close()
                    stats["project"] = project_stats
            except Exception as e:
                logger.warning(f"获取项目知识库统计失败: {e}")

        if self.thirdparty_kb:
            try:
                import sqlite3
                db_file = Path(self.thirdparty_kb.db_file)
                if db_file.exists():
                    conn = sqlite3.connect(str(db_file))
                    cursor = conn.cursor()

                    thirdparty_stats = {}
                    cursor.execute("SELECT COUNT(*) FROM classes")
                    thirdparty_stats["classes"] = cursor.fetchone()[0]

                    cursor.execute("SELECT COUNT(*) FROM functions")
                    thirdparty_stats["functions"] = cursor.fetchone()[0]

                    cursor.execute("SELECT COUNT(*) FROM files")
                    thirdparty_stats["files"] = cursor.fetchone()[0]

                    thirdparty_stats["database_size_mb"] = db_file.stat().st_size / (1024 * 1024)

                    conn.close()
                    stats["thirdparty"] = thirdparty_stats
            except Exception as e:
                logger.warning(f"获取三方库知识库统计失败: {e}")

        return stats

    def close(self):
        """关闭知识库连接"""
        if self.project_kb:
            self.project_kb.close()
            self.project_kb = None

        if self.thirdparty_kb:
            self.thirdparty_kb.close()
            self.thirdparty_kb = None
