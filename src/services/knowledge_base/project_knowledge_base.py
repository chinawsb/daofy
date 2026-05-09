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

        # 项目知识库目录 - 存放在项目目录下
        self.kb_dir = self.project_dir / ".delphi-kb"
        self.kb_dir.mkdir(parents=True, exist_ok=True)

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

    def _get_shared_thirdparty_paths(self) -> Set[str]:
        """
        读取 MCP 服务器共享第三方知识库中已扫描的路径列表。

        共享知识库路径:
          C:/User/delphi-complier-mcp-server/data/thirdparty-knowledge-base/thirdparty_paths.json

        Returns:
            已扫描的路径集合 (绝对路径,已规范化)
        """
        shared_paths_file = Path(
            r"C:\User\delphi-complier-mcp-server\data\thirdparty-knowledge-base\thirdparty_paths.json"
        )
        if not shared_paths_file.exists():
            logger.info("共享第三方知识库路径文件不存在,跳过检查")
            return set()

        try:
            with open(shared_paths_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            raw_paths = data.get("paths", [])
            # 规范化所有路径 (解析真实大小写)
            normalized = set()
            for p in raw_paths:
                try:
                    normalized.add(str(Path(p).resolve()))
                except Exception:
                    normalized.add(p)
            logger.info(f"从共享知识库读取到 {len(normalized)} 个已扫描路径")
            return normalized
        except Exception as e:
            logger.warning(f"读取共享第三方知识库路径失败: {e}")
            return set()

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

        # 读取共享第三方知识库中已扫描的路径，过滤掉已存在的
        shared_scanned = self._get_shared_thirdparty_paths()
        if shared_scanned:
            before = len(thirdparty_paths)
            thirdparty_paths = [
                p for p in thirdparty_paths
                if str(Path(p).resolve()) not in shared_scanned
            ]
            skipped = before - len(thirdparty_paths)
            if skipped > 0:
                logger.info(f"共享知识库已包含 {skipped} 个路径,跳过扫描")
            else:
                logger.info("所有路径均未被共享知识库收录,继续完整扫描")

        if not thirdparty_paths:
            logger.info("所有三方库路径已在共享知识库中,无需重复构建")
            return True

        logger.info(f"开始构建三方库知识库,共 {len(thirdparty_paths)} 个目录")
        self._report_progress(5, "扫描三方库源码目录...")

        # 合并所有三方库源码到一个临时目录或直接扫描
        thirdparty_kb_dir = self.kb_dir / "thirdparty"
        thirdparty_kb_dir.mkdir(parents=True, exist_ok=True)

        # 扫描所有三方库目录
        all_files = []
        seen_paths = set()  # 用于去重
        total_dirs = len(thirdparty_paths)

        for idx, path in enumerate(thirdparty_paths):
            pct = 5 + (idx / total_dirs) * 35
            self._report_progress(pct, f"扫描三方库 [{idx+1}/{total_dirs}]: {Path(path).name}")
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

        # 直接写入 SQLite (统一Schema,与 build_project_knowledge_base 一致)
        import sqlite3
        self._report_progress(40, f"保存 {len(all_files)} 个三方库文件到数据库...")
        logger.info("保存三方库源码到数据库...")
        db_file = thirdparty_kb_dir / "knowledge.sqlite"
        if db_file.exists():
            db_file.unlink()
        conn = None
        try:
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()

            current_time = datetime.now().timestamp()

            # 创建统一Schema表
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

            # 插入文件数据
            for file_info in all_files:
                units = file_info.get('units', [])
                if isinstance(units, list):
                    units = ','.join(units)
                uses = file_info.get('uses', [])
                if isinstance(uses, list):
                    uses = ','.join(uses)

                cursor.execute("""
                    INSERT INTO files (full_path, relative_path, extension, size, line_count, hash, 
                        last_modified, category, units_defined, units_imported, description, 
                        scan_timestamp, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    file_info.get('full_path', ''),
                    file_info.get('path', ''),
                    file_info.get('extension', '.pas'),
                    file_info.get('size', 0),
                    file_info.get('line_count', 0),
                    file_info.get('hash', ''),
                    file_info.get('last_modified', ''),
                    'thirdparty',
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
                'TC', cls.get('name', ''), cls.get('name', '').lower() if cls.get('name') else '',
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
                    'FF', func.get('name', ''), func.get('name', '').lower() if func.get('name') else '',
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
                    'CC', const.get('name', ''), const.get('name', '').lower() if const.get('name') else '',
                    const.get('name', '').lower()[::-1] if const.get('name') else '',
                    file_id, const.get('line', 0), '', const.get('definition', ''),
                    None, 'pending', None, current_time, current_time
                ))

            # 统计
            cursor.execute("SELECT COUNT(*) FROM files WHERE category='thirdparty'")
            source_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='TC'")
            class_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='FF'")
            func_count = cursor.fetchone()[0]

            # 保存元数据
            cursor.execute("DELETE FROM metadata")
            cursor.execute("INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?)",
                ('total_files', str(source_count), current_time))
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

            logger.info(f"三方库知识库构建完成!")
            logger.info(f"  源文件: {source_count}")
            logger.info(f"  类: {class_count}")
            logger.info(f"  函数: {func_count}")
            self._report_progress(80, f"三方库: {source_count} 文件, {class_count} 类, {func_count} 函数")
        except Exception:
            raise
        finally:
            if conn:
                conn.close()

        # 构建向量索引 (加载 SQLiteVectorKnowledgeBase 用于查询)
        logger.info("加载三方库向量索引...")
        self.thirdparty_kb = SQLiteVectorKnowledgeBase(str(thirdparty_kb_dir))

        # 更新元数据
        self.metadata["thirdparty_paths"] = thirdparty_paths
        self.metadata["thirdparty_hash"] = current_hash
        self._save_metadata()

        logger.info("三方库知识库构建完成")
        # 自动构建 embedding 向量
        try:
            self.build_vectors()
        except Exception:
            pass
        return True

    def _get_shared_exclude_prefixes(self) -> List[Path]:
        """
        获取共享知识库中属于当前项目目录的路径前缀列表。

        只返回在 self.project_dir 下的路径,用于 rglob 时的跳过判断。

        Returns:
            需要跳过的目录前缀 (Path 列表)
        """
        all_scanned = self._get_shared_thirdparty_paths()
        prefixes = []
        for p in all_scanned:
            try:
                pp = Path(p).resolve()
                pp.relative_to(self.project_dir.resolve())
                prefixes.append(pp)
            except ValueError:
                pass  # 不在项目目录内,不会出现在 rglob 结果中
        if prefixes:
            logger.info(f"项目源码扫描将跳过 {len(prefixes)} 个共享知识库已收录的目录")
        return prefixes

    def _should_skip_shared_path(self, file_path: Path, exclude_prefixes: List[Path]) -> bool:
        """检查文件是否在需要跳过的共享知识库路径下"""
        if not exclude_prefixes:
            return False
        file_str = str(file_path.resolve())
        for prefix in exclude_prefixes:
            prefix_str = str(prefix)
            # 检查 file_path 是否以 prefix 开头 (作为目录前缀)
            if file_str == prefix_str or file_str.startswith(prefix_str + os.sep):
                return True
        return False

    def build_project_knowledge_base(self, force_rebuild: bool = False) -> bool:
        """
        构建项目源码知识库

        Args:
            force_rebuild: 是否强制重建

        Returns:
            是否构建成功
        """
        import sqlite3
        
        # 计算源码哈希
        current_hash = self._calculate_source_hash(self.project_dir)
        cached_hash = self.metadata.get("source_hash")

        # 检查是否需要重建
        if not force_rebuild and cached_hash == current_hash:
            db_file = self.kb_dir / "knowledge.sqlite"
            if db_file.exists():
                logger.info("项目源码知识库已是最新,跳过构建")
                return True

        logger.info("开始构建项目源码知识库")
        self._report_progress(5, "扫描项目源码文件...")

        # 项目源码知识库目录
        project_kb_dir = self.kb_dir
        project_kb_dir.mkdir(parents=True, exist_ok=True)

        # 读取共享 KB 中已收录的路径前缀(仅项目内),用于跳过
        exclude_prefixes = self._get_shared_exclude_prefixes()

        # 直接扫描 (单线程,避免多进程问题)
        all_source_files = []
        total_files = 0
        total_lines = 0
        skipped_files = 0
        
        scanner = DelphiSourceScanner(str(self.project_dir), str(project_kb_dir), self.progress_callback)

        def _scan_files(extension: str):
            nonlocal total_files, total_lines, skipped_files
            for file_path in self.project_dir.rglob(f'*{extension}'):
                if self._should_skip_shared_path(file_path, exclude_prefixes):
                    skipped_files += 1
                    continue
                try:
                    file_info = scanner.analyze_file(file_path)
                    if file_info:
                        all_source_files.append(file_info)
                        total_files += 1
                        total_lines += file_info.get('line_count', 0)
                except Exception as e:
                    logger.debug(f"分析文件失败: {file_path}, {e}")
        
        # 依次扫描所有 Delphi 相关源文件
        _scan_files('.pas')
        _scan_files('.dpr')
        _scan_files('.dpk')
        _scan_files('.dfm')
        _scan_files('.fmx')
        _scan_files('.inc')

        if skipped_files > 0:
            logger.info(f"跳过 {skipped_files} 个已在共享知识库中的文件")

        logger.info(f"总共找到 {total_files} 个源文件, {total_lines} 行代码")

        if not all_source_files:
            logger.warning("未找到任何源文件")
            return False

        # 直接保存到 SQLite (统一Schema)
        db_file = self.kb_dir / "knowledge.sqlite"
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        
        current_time = datetime.now().timestamp()
        
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
        self._report_progress(50, f"保存 {total_files} 个项目源文件到数据库...")
        logger.info("保存源文件到数据库...")
        batch_size = 1000
        for i, file_info in enumerate(all_source_files):
            units = file_info.get('units', [])
            if isinstance(units, list):
                units = ','.join(units)
            uses = file_info.get('uses', [])
            if isinstance(uses, list):
                uses = ','.join(uses)
            
            cursor.execute("""
                INSERT INTO files (full_path, relative_path, extension, size, line_count, hash, 
                    last_modified, category, units_defined, units_imported, description, 
                    scan_timestamp, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_info.get('full_path', ''),
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
                    'TC', cls.get('name', ''), cls.get('name', '').lower() if cls.get('name') else '',
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
                    'FF', func.get('name', ''), func.get('name', '').lower() if func.get('name') else '',
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
                    'CC', const.get('name', ''), const.get('name', '').lower() if const.get('name') else '',
                    const.get('name', '').lower()[::-1] if const.get('name') else '',
                    file_id, const.get('line', 0), '', const.get('definition', ''),
                    None, 'pending', None, current_time, current_time
                ))

        conn.commit()
        
        # 统计
        cursor.execute("SELECT COUNT(*) FROM files WHERE category='source'")
        source_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='TC'")
        class_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='FF'")
        func_count = cursor.fetchone()[0]
        
        # 保存元数据
        cursor.execute("DELETE FROM metadata")
        cursor.execute("INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?)", 
            ('total_files', str(source_count), current_time))
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
        
        logger.info(f"项目知识库构建完成!")
        logger.info(f"  源文件: {source_count}")
        logger.info(f"  类: {class_count}")
        logger.info(f"  函数: {func_count}")
        self._report_progress(95, f"项目 KB: {source_count} 文件, {class_count} 类, {func_count} 函数")

        # 更新元数据
        self.metadata["source_hash"] = current_hash
        self._save_metadata()

        self._report_progress(100, "项目知识库构建完成")
        # 自动构建 embedding 向量（异步，不阻塞构建流程）
        try:
            self._report_progress(99, "构建 embedding 向量...")
            self.build_vectors()
        except Exception:
            pass
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
            # 加载项目源码知识库 - 支持两种格式:
            # 1. 新格式: 直接存放在 .delphi-kb/knowledge.sqlite (由 build_project_knowledge_base 创建)
            # 2. 旧格式: 存放在 .delphi-kb/project/index/source_index.json

            # 优先检测新格式 (SQLite vector format)
            new_format_db = self.kb_dir / "knowledge.sqlite"
            if new_format_db.exists():
                self.project_kb = SQLiteVectorKnowledgeBase(str(self.kb_dir))
                logger.info(f"项目源码知识库加载成功 (新格式): {new_format_db}")
            else:
                # 回退检测旧格式 (JSON index format)
                project_kb_dir = self.kb_dir / "project"
                if (project_kb_dir / "index" / "source_index.json").exists():
                    self.project_kb = SQLiteVectorKnowledgeBase(str(project_kb_dir))
                    logger.info("项目源码知识库加载成功 (旧格式)")

            # 加载三方库知识库 - 同样支持两种格式
            # 新格式: .delphi-kb/thirdparty/knowledge.sqlite
            thirdparty_new_db = self.kb_dir / "thirdparty" / "knowledge.sqlite"
            if thirdparty_new_db.exists():
                self.thirdparty_kb = SQLiteVectorKnowledgeBase(str(self.kb_dir / "thirdparty"))
                logger.info(f"三方库知识库加载成功 (新格式): {thirdparty_new_db}")
            else:
                # 旧格式
                thirdparty_kb_dir = self.kb_dir / "thirdparty"
                if (thirdparty_kb_dir / "index" / "source_index.json").exists():
                    self.thirdparty_kb = SQLiteVectorKnowledgeBase(str(thirdparty_kb_dir))
                    logger.info("三方库知识库加载成功 (旧格式)")

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
                    # 新 schema: vocabularies 表 + type 列
                    try:
                        cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='TC'")
                        project_stats["classes"] = cursor.fetchone()[0]
                    except Exception:
                        # 旧 schema: classes 表
                        try:
                            cursor.execute("SELECT COUNT(*) FROM classes")
                            project_stats["classes"] = cursor.fetchone()[0]
                        except Exception:
                            project_stats["classes"] = 0

                    try:
                        cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='FF'")
                        project_stats["functions"] = cursor.fetchone()[0]
                    except Exception:
                        try:
                            cursor.execute("SELECT COUNT(*) FROM functions")
                            project_stats["functions"] = cursor.fetchone()[0]
                        except Exception:
                            project_stats["functions"] = 0

                    try:
                        cursor.execute("SELECT COUNT(*) FROM files")
                        project_stats["files"] = cursor.fetchone()[0]
                    except Exception:
                        project_stats["files"] = 0

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
                    # 新 schema: vocabularies 表 + type 列
                    try:
                        cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='TC'")
                        thirdparty_stats["classes"] = cursor.fetchone()[0]
                    except Exception:
                        try:
                            cursor.execute("SELECT COUNT(*) FROM classes")
                            thirdparty_stats["classes"] = cursor.fetchone()[0]
                        except Exception:
                            thirdparty_stats["classes"] = 0

                    try:
                        cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='FF'")
                        thirdparty_stats["functions"] = cursor.fetchone()[0]
                    except Exception:
                        try:
                            cursor.execute("SELECT COUNT(*) FROM functions")
                            thirdparty_stats["functions"] = cursor.fetchone()[0]
                        except Exception:
                            thirdparty_stats["functions"] = 0

                    try:
                        cursor.execute("SELECT COUNT(*) FROM files")
                        thirdparty_stats["files"] = cursor.fetchone()[0]
                    except Exception:
                        thirdparty_stats["files"] = 0

                    thirdparty_stats["database_size_mb"] = db_file.stat().st_size / (1024 * 1024)

                    conn.close()
                    stats["thirdparty"] = thirdparty_stats
            except Exception as e:
                logger.warning(f"获取三方库知识库统计失败: {e}")

        return stats

    def _report_progress(self, percent: float, message: str) -> None:
        """报告进度（安全调用 progress_callback）"""
        if self.progress_callback:
            try:
                self.progress_callback(percent, message)
            except Exception:
                pass

    def build_vectors(self, progress_callback=None) -> dict:
        """
        为项目 KB 和三方库 KB 构建 embedding 向量

        Args:
            progress_callback: 进度回调 (percent, message)

        Returns:
            {"project": count, "thirdparty": count}
        """
        results = {}
        pc = progress_callback or self.progress_callback

        if self.project_kb:
            if pc:
                pc(5, "构建项目 KB 向量...")
            count = self.project_kb.build_vectors(progress_callback=pc)
            results["project"] = count
            if pc:
                pc(50, f"项目 KB 向量: {count}")

        if self.thirdparty_kb:
            if pc:
                pc(55, "构建三方库 KB 向量...")
            count = self.thirdparty_kb.build_vectors(progress_callback=pc)
            results["thirdparty"] = count
            if pc:
                pc(100, f"向量构建完成: {results}")

        return results

    def close(self):
        """关闭知识库连接"""
        if self.project_kb:
            self.project_kb.close()
            self.project_kb = None

        if self.thirdparty_kb:
            self.thirdparty_kb.close()
            self.thirdparty_kb = None
