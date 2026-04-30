"""
Delphi 知识库服务

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

提供 Delphi 源码知识库的构建、管理和查询功能
"""

import os
import sys

os.environ['PYTHONIOENCODING'] = 'utf-8'

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable

# 添加当前目录到 Python 路径
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from sqlite_vector_query_knowledge_base import SQLiteVectorKnowledgeBase
from smart_cache_knowledge_base import SmartCacheKnowledgeBase


class DelphiKnowledgeBaseService:
    """Delphi 知识库服务"""

    def __init__(self, kb_dir: Optional[str] = None, progress_callback: Optional[Callable] = None):
        """
        初始化知识库服务

        Args:
            kb_dir: 知识库目录路径,如果为 None 则使用默认路径
            progress_callback: 进度回调函数
        """
        if kb_dir is None:
            # 默认路径: MCP 服务器目录下的 data/delphi-knowledge-base
            # 获取 MCP 服务器根目录 (src/services/knowledge_base -> ../../../)
            server_root = Path(__file__).parent.parent.parent.parent
            kb_dir = str(server_root / "data" / "delphi-knowledge-base")
        else:
            kb_dir = str(kb_dir)

        self.kb_dir: Path = Path(kb_dir)
        self.kb_instance = None
        self.source_dir = None
        self.delphi_versions = []
        self.progress_callback = progress_callback

        # 创建必要的目录
        self.kb_dir.mkdir(parents=True, exist_ok=True)

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

    def build_knowledge_base(self, version: Optional[str] = None, force_rebuild: bool = False, incremental: bool = False) -> bool:
        """
        构建知识库

        Args:
            version: Delphi 版本,如果为 None 则选择最新版本
            force_rebuild: 是否强制重建
            incremental: 是否增量构建

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

        # 使用智能缓存方案
        return self._build_with_smart_cache(force_rebuild, incremental=incremental)
    
    def _build_with_smart_cache(self, force_rebuild: bool = False, incremental: bool = False) -> bool:
        """使用智能缓存方案构建知识库"""
        if incremental and not force_rebuild:
            print("使用智能缓存方案增量构建知识库...")
        else:
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
                "incremental_hash_mode": "mtime_size",
                "parallel_workers": 4,
                "batch_size": 1000
            }
        }
        
        config_path = self.kb_dir / "config.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        # 初始化智能缓存知识库
        start_time = time.time()
        self.kb_instance = SmartCacheKnowledgeBase(str(self.kb_dir), config, progress_callback=self.progress_callback)
        
        # 异步重建
        self.kb_instance.rebuild_async(incremental=incremental and not force_rebuild)
        
        elapsed = (time.time() - start_time) * 1000
        print(f"知识库初始化完成! 耗时: {elapsed:.2f}ms")
        print("向量正在后台构建中，知识库已可用...")
        
        return True
    
    def load_knowledge_base(self) -> bool:
        """
        加载知识库

        Returns:
            是否加载成功
        """
        try:
            if self.kb_instance is None:
                # 读取 config.json 获取数据库文件名
                config_path = self.kb_dir / "config.json"
                db_file = "knowledge.sqlite"  # 默认值
                if config_path.exists():
                    import json
                    try:
                        with open(config_path, encoding='utf-8') as f:
                            config = json.load(f)
                        db_file = config.get('database', {}).get('file', 'knowledge.sqlite')
                    except Exception as e:
                        print(f"[WARNING] 读取config.json失败: {e}, 使用默认数据库")
                
                self.kb_instance = SQLiteVectorKnowledgeBase(str(self.kb_dir), db_file=db_file)
            return True
        except Exception as e:
            print(f"加载知识库失败: {e}")
            return False

    def search_by_name(self, name: str) -> List[Dict]:
        """根据名称搜索符号 (返回所有类型)"""
        if not self.load_knowledge_base():
            return []
        return self.kb_instance.search_by_name(name)
    def search_by_keyword(self, keyword: str) -> List[Dict]:
        """根据关键词搜索"""
        if not self.load_knowledge_base():
            return []
        
        results = self.kb_instance.semantic_search(keyword, top_k=10)
        return [{'name': r['name'], 'type': r['type_name'], 'similarity': r['similarity']} for r in results]

    def search_by_unit_name(self, unit_name: str) -> List[Dict]:
        """根据单元名搜索"""
        if not self.load_knowledge_base():
            return []
        return self.kb_instance.search_by_unit_name(unit_name)

    def semantic_search_classes(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """语义搜索类"""
        if not self.load_knowledge_base():
            return []
        
        # 使用 SQLiteVectorKnowledgeBase 的语义搜索
        results = self.kb_instance.semantic_search_classes(query, top_k)
        return results

    def semantic_search_functions(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """语义搜索函数"""
        if not self.load_knowledge_base():
            return []
        
        # 使用 SQLiteVectorKnowledgeBase 的语义搜索
        results = self.kb_instance.semantic_search_functions(query, top_k)
        return results

    def get_statistics(self) -> Dict:
        """获取知识库统计信息"""
        # 读取 config.json 获取数据库文件名
        import sqlite3
        config_path = self.kb_dir / "config.json"
        db_file_name = "knowledge.sqlite"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                db_file_name = config.get("database", {}).get("file", "knowledge.sqlite")
            except:
                pass
        
        db_file = self.kb_dir / db_file_name
        
        if not self.load_knowledge_base():
            return {}
        
        if not db_file.exists():
            return {}

        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        stats = {}
        try:
            # 检查表结构
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files'")
            has_files = cursor.fetchone() is not None
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vocabularies'")
            has_vocab = cursor.fetchone() is not None

            if has_files:
                cursor.execute("SELECT COUNT(*) FROM files")
                stats["files"] = cursor.fetchone()[0]

            if has_vocab:
                cursor.execute("SELECT COUNT(*) FROM vocabularies")
                stats["vocabulary_size"] = cursor.fetchone()[0]

                # 使用统一双字母类型代码
                cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type IN ('TC', 'TR', 'TI', 'TE', 'TS', 'TY', 'TH')")
                stats["classes"] = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type = 'FF'")
                stats["functions"] = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type = 'FP'")
                stats["procedures"] = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type IN ('CC', 'CR')")
                stats["constants"] = cursor.fetchone()[0]

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
