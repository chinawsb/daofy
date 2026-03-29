"""
Delphi 知识库服务

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

提供 Delphi 源码知识库的构建、管理和查询功能
"""

import os
import sys
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable
from collections import defaultdict

# 添加当前目录到 Python 路径
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from sqlite_vector_query_knowledge_base import SQLiteVectorKnowledgeBase
from smart_cache_knowledge_base import SmartCacheKnowledgeBase


class DelphiKnowledgeBaseService:
    """Delphi 知识库服务"""

    def __init__(self, kb_dir: Optional[str] = None, progress_callback: Optional[Callable] = None,
                 use_smart_cache: bool = True):
        """
        初始化知识库服务

        Args:
            kb_dir: 知识库目录路径,如果为 None 则使用默认路径
            progress_callback: 进度回调函数
            use_smart_cache: 是否使用智能缓存方案（默认True）
        """
        if kb_dir is None:
            # 默认路径: MCP 服务器目录下的 data/delphi-knowledge-base
            # 获取 MCP 服务器根目录 (src/services/knowledge_base -> ../../../)
            server_root = Path(__file__).parent.parent.parent.parent
            kb_dir = server_root / "data" / "delphi-knowledge-base"
        else:
            kb_dir = Path(kb_dir)

        self.kb_dir = kb_dir
        self.kb_instance = None
        self.source_dir = None
        self.delphi_versions = []
        self.progress_callback = progress_callback
        self.use_smart_cache = use_smart_cache

        # 创建必要的目录
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        (self.kb_dir / "index").mkdir(exist_ok=True)
        (self.kb_dir / "data").mkdir(exist_ok=True)

        # 检测已安装的 Delphi 版本
        self.detect_delphi_versions()

    def detect_delphi_versions(self) -> List[Dict]:
        """
        检测已安装的 Delphi 版本

        Returns:
            Delphi 版本列表
        """
        import winreg

        versions = []

        try:
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
                    except:
                        continue
                    finally:
                        winreg.CloseKey(version_path)

                    # 获取版本名称
                    version_name = self.get_delphi_version_name(version_key)

                    # 检查源码目录
                    source_dir = Path(root_dir) / "source"
                    if source_dir.exists():
                        versions.append({
                            "version": version_key,
                            "name": version_name,
                            "root_dir": root_dir,
                            "source_dir": str(source_dir)
                        })

                except WindowsError:
                    break

            winreg.CloseKey(key)

        except Exception as e:
            print(f"检测 Delphi 版本失败: {e}")

        self.delphi_versions = versions
        return versions

    def get_delphi_version_name(self, version_key: str) -> str:
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

    def select_delphi_version(self, version: Optional[str] = None) -> Optional[Dict]:
        """
        选择 Delphi 版本

        Args:
            version: 版本号,如果为 None 则选择最新版本

        Returns:
            选中的版本信息
        """
        if not self.delphi_versions:
            return None

        if version is None:
            # 选择最新版本
            return self.delphi_versions[0]

        # 查找指定版本
        for v in self.delphi_versions:
            if v["version"] == version or v["name"] == version:
                return v

        return None

    def build_knowledge_base(self, version: Optional[str] = None, force_rebuild: bool = False) -> bool:
        """
        构建知识库

        Args:
            version: Delphi 版本,如果为 None 则选择最新版本
            force_rebuild: 是否强制重建

        Returns:
            是否构建成功
        """
        # 选择 Delphi 版本
        selected_version = self.select_delphi_version(version)
        if not selected_version:
            print("未找到可用的 Delphi 版本")
            return False

        self.source_dir = selected_version["source_dir"]
        print(f"使用 Delphi 版本: {selected_version['name']} ({selected_version['version']})")
        print(f"源码目录: {self.source_dir}")

        # 检查源码目录是否存在
        if not Path(self.source_dir).exists():
            print(f"源码目录不存在: {self.source_dir}")
            return False

        if self.use_smart_cache:
            # 使用智能缓存方案
            return self._build_with_smart_cache(force_rebuild)
        else:
            # 使用原有方案
            return self._build_with_legacy(force_rebuild)
    
    def _build_with_smart_cache(self, force_rebuild: bool = False) -> bool:
        """使用智能缓存方案构建知识库"""
        print("使用智能缓存方案构建知识库...")
        
        # 创建配置文件
        config = {
            "name": "delphi-knowledge-base",
            "type": "delphi-source",
            "version": "2.0",
            "source": {
                "type": "link",
                "path": str(self.source_dir),
                "extensions": [".pas", ".dfm", ".inc"],
                "encoding": "utf-8",
                "use_files_dir": False
            },
            "database": {
                "file": "knowledge_base.sqlite",
                "enable_vector_cache": True,
                "cache_size": 10000,
                "vector_build_mode": "ondemand"
            },
            "build": {
                "auto_rebuild": False,
                "incremental": not force_rebuild,
                "parallel_workers": 4,
                "batch_size": 1000
            }
        }
        
        config_path = self.kb_dir / "config.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        # 初始化智能缓存知识库
        start_time = time.time()
        self.kb_instance = SmartCacheKnowledgeBase(str(self.kb_dir), config)
        
        # 异步重建
        self.kb_instance.rebuild_async()
        
        elapsed = (time.time() - start_time) * 1000
        print(f"知识库初始化完成! 耗时: {elapsed:.2f}ms")
        print("向量正在后台构建中，知识库已可用...")
        
        return True
    
    def _build_with_legacy(self, force_rebuild: bool = False) -> bool:
        """使用原有方案构建知识库"""
        # 导入扫描模块
        from scan_delphi_sources import DelphiSourceScanner

        # 初始化扫描器（带进度回调和增量构建选项）
        scanner = DelphiSourceScanner(self.source_dir, self.kb_dir, self.progress_callback, force_rebuild=force_rebuild)

        # 扫描源码
        print("开始扫描 Delphi 源码...")
        start_time = time.time()
        scanner.run()
        elapsed = (time.time() - start_time) * 1000
        print(f"扫描完成! 耗时: {elapsed:.2f}ms")

        # 构建 SQLite 向量索引
        print("开始构建 SQLite 向量索引...")
        start_time = time.time()
        self.kb_instance = SQLiteVectorKnowledgeBase(str(self.kb_dir), force_rebuild=force_rebuild)
        elapsed = (time.time() - start_time) * 1000
        print(f"索引构建完成! 耗时: {elapsed:.2f}ms")

        return True

    def load_knowledge_base(self) -> bool:
        """
        加载知识库

        Returns:
            是否加载成功
        """
        try:
            if self.kb_instance is None:
                if self.use_smart_cache:
                    # 使用智能缓存方案
                    self.kb_instance = SmartCacheKnowledgeBase(str(self.kb_dir))
                else:
                    # 使用原有方案
                    self.kb_instance = SQLiteVectorKnowledgeBase(str(self.kb_dir))
            return True
        except Exception as e:
            print(f"加载知识库失败: {e}")
            return False

    def search_by_class_name(self, class_name: str) -> List[Dict]:
        """根据类名搜索"""
        if not self.load_knowledge_base():
            return []
        
        if self.use_smart_cache:
            # 智能缓存方案：使用统一的search_by_name
            return self.kb_instance.search_by_name(class_name, item_types=['c'])
        else:
            return self.kb_instance.search_by_class_name(class_name)

    def search_by_function_name(self, function_name: str) -> List[Dict]:
        """根据函数名搜索"""
        if not self.load_knowledge_base():
            return []
        
        if self.use_smart_cache:
            # 智能缓存方案：使用统一的search_by_name
            return self.kb_instance.search_by_name(function_name, item_types=['f', 'p'])
        else:
            return self.kb_instance.search_by_function_name(function_name)

    def search_by_keyword(self, keyword: str) -> List[Dict]:
        """根据关键词搜索"""
        if not self.load_knowledge_base():
            return []
        
        if self.use_smart_cache:
            # 智能缓存方案：使用语义搜索
            results = self.kb_instance.semantic_search(keyword, top_k=10)
            return [{'name': r['name'], 'type': r['type_name'], 'similarity': r['similarity']} for r in results]
        else:
            return self.kb_instance.search_by_keyword(keyword)

    def semantic_search_classes(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """语义搜索类"""
        if not self.load_knowledge_base():
            return []
        
        if self.use_smart_cache:
            results = self.kb_instance.semantic_search(query, top_k=top_k, item_types=['c'])
            return [(r['name'], r['similarity']) for r in results]
        else:
            return self.kb_instance.semantic_search_classes(query, top_k)

    def semantic_search_functions(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """语义搜索函数"""
        if not self.load_knowledge_base():
            return []
        
        if self.use_smart_cache:
            results = self.kb_instance.semantic_search(query, top_k=top_k, item_types=['f', 'p'])
            return [(r['name'], r['similarity']) for r in results]
        else:
            return self.kb_instance.semantic_search_functions(query, top_k)

    def get_statistics(self) -> Dict:
        """获取知识库统计信息"""
        if not self.load_knowledge_base():
            return {}
        
        if self.use_smart_cache:
            # 智能缓存方案
            return self.kb_instance.get_statistics()
        else:
            # 原有方案
            # 从数据库获取统计信息
            import sqlite3
            db_file = self.kb_dir / "index" / "knowledge_base_vector.sqlite"
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

                # 获取文件大小
                stats["database_size_mb"] = db_file.stat().st_size / (1024 * 1024)

            finally:
                conn.close()

            return stats

    def close(self):
        """关闭知识库连接"""
        if self.kb_instance:
            self.kb_instance.close()
            self.kb_instance = None
