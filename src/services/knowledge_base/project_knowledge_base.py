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
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Set, Callable
from datetime import datetime
from src.utils.logger import get_logger
from src.utils.dproj_parser import DprojParser
from .sqlite_vector_query_knowledge_base import SQLiteVectorKnowledgeBase
from src.services.knowledge_base.schema import get_connection, create_source_tables, get_schema_version_from_db
from src.services.knowledge_base import set_schema_version_in_db

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

        logger.info(f"项目知识库初始化: {self.project_name}")

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
                    except OSError:
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
        """计算路径列表的签名（排序后用分号连接，无需 MD5）"""
        return ";".join(sorted(paths))

    def _calculate_source_hash(self, source_dir: Path, extensions: Set[str] = None) -> str:
        """
        计算源码目录的变更签名（基于文件数量+总大小+最新修改时间）

        跳过第三方库路径和 .delphi-kb 目录，避免将 KB 自身或第三方库的变更
        误判为项目源码变更，同时大幅加快计算速度。

        使用 `文件数|总字节数|最新mtime` 三元组而非 MD5 哈希，因为：
        - 不需要逐文件计算 MD5（IO + CPU 开销大）
        - 文件数/总大小/最新时间的变化能覆盖所有增删改场景
        - config.json 中指定 hash_mode=md5 时才需逐文件 MD5

        Args:
            source_dir: 源码目录
            extensions: 文件扩展名集合

        Returns:
            签名值 (文件数|总大小|最新修改时间)
        """
        if extensions is None:
            extensions = {'.pas', '.dpr', '.dpk', '.dfm', '.fmx', '.inc'}

        # 需要跳过的目录名（第三方库、知识库、系统目录等）
        skip_dir_names = {'.delphi-kb', 'thirdpart', 'vendor', 'lib', 'packages',
                          '__pycache__', '.git', '.svn', 'node_modules', 'dist', 'bin', 'obj',
                          'Win32', 'Win64', '__history', '__recovery', 'backup', 'logs'}

        # 读取共享第三方库路径，精确跳过
        shared_paths = self._get_shared_thirdparty_paths()
        skip_paths_normalized = {str(Path(p).resolve()) for p in shared_paths} if shared_paths else set()

        total_files = 0
        total_size = 0
        latest_mtime = 0.0

        for root, dirs, files in os.walk(source_dir):
            # 跳过不需要的目录（不进入遍历）
            dirs[:] = [d for d in dirs if d.lower() not in skip_dir_names]

            root_normalized = str(Path(root).resolve())
            if root_normalized in skip_paths_normalized:
                dirs[:] = []
                continue

            for file in files:
                if Path(file).suffix.lower() in extensions:
                    try:
                        stat = (Path(root) / file).stat()
                        total_files += 1
                        total_size += stat.st_size
                        if stat.st_mtime > latest_mtime:
                            latest_mtime = stat.st_mtime
                    except Exception as e:
                        logger.debug("忽略非致命异常: %s", str(e))

        return f"{total_files}|{total_size}|{latest_mtime}"

    def _get_shared_thirdparty_paths(self) -> Set[str]:
        """
        读取 MCP 服务器共享第三方知识库中已扫描的路径列表。

        共享知识库路径:
          <项目根>/data/thirdparty-knowledge-base/thirdparty_paths.json

        Returns:
            已扫描的路径集合 (绝对路径,已规范化)
        """
        # 从当前文件位置推导项目根目录: src/services/know_base/ → 上3层 = 项目根
        _project_root = Path(__file__).parent.parent.parent.parent
        shared_paths_file = (
            _project_root / "data" / "thirdparty-knowledge-base" / "thirdparty_paths.json"
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

    def build_project_knowledge_base(self, rebuild: bool = False) -> bool:
        """
        构建项目源码知识库

        Args:
            rebuild: 是否强制重建

        Returns:
            是否构建成功
        """
        _build_start = time.time()
        # 先连接 DB，读取缓存的 source_hash
        db_file = self.kb_dir / "knowledge.sqlite"
        conn = get_connection(str(db_file), use_wal=True)
        cursor = conn.cursor()
        create_source_tables(cursor)
        current_hash = self._calculate_source_hash(self.project_dir)

        # Schema 升级检测：当前版本到最新
        from src.services.knowledge_base import SCHEMA_VERSION as _SV
        if get_schema_version_from_db(cursor) < _SV:
            cursor.execute("""
                DELETE FROM vocabularies WHERE id NOT IN (
                    SELECT MIN(id) FROM vocabularies GROUP BY type, name, file_id
                )
            """)
            if cursor.rowcount > 0:
                logger.info(f"升级 schema v1→v2：清理了 {cursor.rowcount} 条重复词汇记录")
            else:
                logger.info("升级 schema v1→v2：无重复词汇需清理")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_vocabularies_dedup ON vocabularies(type, name, file_id)")

        # 读取缓存 hash，检查是否需要重建
        cached_hash = None
        try:
            cursor.execute("SELECT value FROM metadata WHERE key='source_hash'")
            row = cursor.fetchone()
            if row:
                cached_hash = row[0]
        except Exception as e:
            logger.debug("忽略非致命异常: %s", str(e))

        if not rebuild and cached_hash == current_hash and db_file.exists():
            logger.info("项目源码知识库已是最新,跳过构建")
            conn.close()
            return True
        logger.info("开始构建项目源码知识库")
        self._report_progress(5, "扫描项目源码文件...")
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        exclude_prefixes = self._get_shared_exclude_prefixes()

        existing_files = {}
        if rebuild:
            cursor.execute("DELETE FROM vocabularies")
            cursor.execute("DELETE FROM files")
            cursor.execute("DELETE FROM metadata")
            conn.commit()
            logger.info("强制重建，已清空旧数据")
        else:
            cursor.execute("SELECT id, full_path, hash FROM files")
            for row in cursor.fetchall():
                existing_files[row[1]] = {'id': row[0], 'hash': row[2]}
            logger.info(f"现有文件数: {len(existing_files)}")

        current_time = datetime.now().timestamp()
        skip_dir_names = {'.delphi-kb', 'thirdpart', 'vendor', 'lib', 'packages',
                          '__pycache__', '.git', '.svn', 'node_modules', 'dist', 'bin', 'obj',
                          'Win32', 'Win64', '__history', '__recovery', 'backup', 'logs'}
        delphi_extensions = {'.pas', '.dpr', '.dpk', '.dfm', '.fmx', '.inc'}

        # ================================================================
        # 第一阶段: 收集所有文件（三方库 + 项目源码）
        # ================================================================
        files_to_parse = []       # (file_path_str, source_dir_str)
        file_category = {}        # full_path -> 'thirdparty' | 'source'
        new_file_paths = set()
        new_files = updated_files = skipped_files_inc = total_files = 0

        # --- 1a. 收集三方库文件 ---
        thirdparty_paths = self.get_thirdparty_paths_from_dproj()
        if thirdparty_paths:
            # 读取共享三方库路径过滤
            shared_scanned = self._get_shared_thirdparty_paths()
            if shared_scanned:
                before = len(thirdparty_paths)
                thirdparty_paths = [p for p in thirdparty_paths if str(Path(p).resolve()) not in shared_scanned]
                if before - len(thirdparty_paths) > 0:
                    logger.info(f"共享知识库已包含 {before - len(thirdparty_paths)} 个路径,跳过扫描")

            for tpath in thirdparty_paths:
                path_obj = Path(tpath)
                if not path_obj.exists():
                    continue
                for root, dirs, files in os.walk(path_obj):
                    for f in files:
                        if Path(f).suffix.lower() not in delphi_extensions:
                            continue
                        fp = str(Path(root) / f)
                        if fp not in file_category:
                            file_category[fp] = 'thirdparty'
                            files_to_parse.append((fp, str(path_obj)))
                            total_files += 1

        # --- 1b. 收集项目源码文件 ---
        for root, dirs, files in os.walk(self.project_dir):
            dirs[:] = [d for d in dirs if d.lower() not in skip_dir_names]
            root_path = Path(root)
            if self._should_skip_shared_path(root_path, exclude_prefixes):
                dirs[:] = []
                continue
            for file in files:
                if Path(file).suffix.lower() not in delphi_extensions:
                    continue
                file_path = root_path / file
                total_files += 1
                full_path = str(file_path)
                new_file_paths.add(full_path)

                try:
                    stat = file_path.stat()
                    file_cur_hash = f"{stat.st_mtime}:{stat.st_size}"
                    if not rebuild and full_path in existing_files:
                        if existing_files[full_path]['hash'] == file_cur_hash:
                            skipped_files_inc += 1
                            continue
                        updated_files += 1
                    else:
                        new_files += 1
                    files_to_parse.append((str(file_path), str(self.project_dir)))
                    file_category[full_path] = 'source'
                except Exception as e:
                    logger.debug(f"访问文件失败: {file_path}, {e}")

        logger.info(f"收集完成: {len(files_to_parse)} 个待解析文件 (thirdparty={sum(1 for v in file_category.values() if v=='thirdparty')}, source={sum(1 for v in file_category.values() if v=='source')})")

        # 第二阶段：解析所有文件
        #   ≤50 文件直接解析（避免进程池启动开销）
        #   >50 文件按每50文件开1进程，上限 cpu-1
        if files_to_parse:
            from src.services.knowledge_base.scan_delphi_sources import _analyze_file_worker
            self._report_progress(50, f"解析 {len(files_to_parse)} 个文件...")

            _p_start = time.time()
            parsed_results = []

            if len(files_to_parse) <= 50:
                logger.info(f"文件数少({len(files_to_parse)})，直接解析")
                for i, f in enumerate(files_to_parse):
                    r = _analyze_file_worker(f)
                    if r:
                        parsed_results.append(r)
                    if (i + 1) % 1000 == 0:
                        logger.info(f"日志: 解析进度 {i+1}/{len(files_to_parse)}")
            else:
                from concurrent.futures import ProcessPoolExecutor, as_completed
                n_workers = min(15, max(2, os.cpu_count() or 4))
                chunk_size = max(5, len(files_to_parse) // (n_workers * 4))
                logger.info(f"多进程解析: {len(files_to_parse)} 个文件, {n_workers} 进程 (chunksize={chunk_size})")
                self._report_progress(50, f"多进程解析 {len(files_to_parse)} 个文件...")

                # 诊断：记录当前进程树信息
                # 注意：os 已在模块顶部导入，不要在函数体内 import os（会导致 UnboundLocalError）
                import sys
                logger.info(f"诊断: 父进程PID={os.getppid()}, 当前PID={os.getpid()}, Python={sys.executable}")
                logger.info(f"诊断: MCP Server 启动方式 - __name__={__name__}, argv={sys.argv}")

                parsed_results = []
                _pool_create_ts = time.time()
                logger.info(f"日志: 创建 ProcessPoolExecutor 耗时={_pool_create_ts-_p_start:.3f}s")
                with ProcessPoolExecutor(max_workers=n_workers) as executor:
                    _p_submitted = time.time()
                    logger.info(f"日志: 提交 {len(files_to_parse)} 个任务到 executor.map 耗时={_p_submitted-_pool_create_ts:.3f}s")
                    for i, result in enumerate(executor.map(_analyze_file_worker, files_to_parse, chunksize=chunk_size)):
                        if i == 0:
                            logger.info(f"日志: 首个结果到达耗时={time.time()-_p_submitted:.1f}s")
                        if result:
                            parsed_results.append(result)
                        if (i + 1) % 1000 == 0:
                            logger.info(f"日志: 解析进度 {i+1}/{len(files_to_parse)}")
            _p_end = time.time()
            logger.info(f"多进程解析耗时: {_p_end-_p_start:.1f}s, 结果={len(parsed_results)}")

            # 入库：构建 items_data 统一列表（smart_cache 模式）
            self._report_progress(55, "入库中...")
            _insert_start = time.time()
            items_data = []
            file_records = []  # (full_path, path, ext, size, line_count, hash, last_modified, category, units_str, uses_str, current_time, description)

            for file_info in parsed_results:
                if not file_info:
                    continue
                fp = file_info.get('full_path', '')
                category = file_category.get(fp, 'source')
                file_hash = file_info.get('hash', '')

                # 文件记录
                units = file_info.get('units', [])
                uses = file_info.get('uses', [])
                file_records.append((
                    fp, file_info.get('path', ''), file_info.get('extension', '.pas'),
                    file_info.get('size', 0), file_info.get('line_count', 0),
                    file_hash, file_info.get('last_modified', ''),
                    category,
                    ','.join(units) if isinstance(units, list) else str(units),
                    ','.join(uses) if isinstance(uses, list) else str(uses),
                    current_time,
                    file_info.get('description', '')[:500] or '',
                ))

                # entities 转 items_data
                for ent in file_info.get('entities', []):
                    ename = ent.get('name', '')
                    if not ename:
                        continue
                    items_data.append((
                        ent.get('kind', 'TY'), ename, ename.lower(),
                        ename.lower()[::-1],     # name_lower_rev
                        None, ent.get('line', 0),  # file_id 占位
                        ent.get('parent', '') or '',
                        ent.get('definition', '') if ent.get('kind') == 'KS' else ent.get('definition', '')[:500],
                        'pending'
                    ))

                # 单元名
                unit_names = file_info.get('units', [])
                if not unit_names:
                    unit_names = [Path(file_info.get('path', '')).stem]
                for uname in unit_names:
                    if uname:
                        items_data.append(('UI', uname, uname.lower(), uname.lower()[::-1], None, 0, '', f"Unit {uname}", 'pending'))

            # 先批量插入 files
            if file_records:
                cursor.executemany("""
                    INSERT OR REPLACE INTO files (full_path, relative_path, extension, size, line_count, hash,
                        last_modified, category, units_defined, units_imported, scan_timestamp,
                        description, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, julianday('now'), julianday('now'))
                """, file_records)
                conn.commit()

                # 获取 file_id 映射
                cursor.execute("SELECT id, full_path FROM files")
                fp_to_id = {row[1]: row[0] for row in cursor.fetchall()}

                # 回填 file_id
                filled_items = []
                for item in items_data:
                    # item: (type, name, name_lower, name_lower_rev, file_id, line, ...)
                    # file_id 位置 index=4, 需要从 fp_to_id 查找
                    filled_items.append(item[:4] + (fp_to_id.get(file_records[0][0], 0),) + item[5:])
                    # 上面的 file_records[0][0] 不对，需要用文件名映射

                # 正确的方式: 对每个 item, 查找对应的 file_id
                items_filled = []
                # 重新构建: 收集每个文件的 items
                for file_info in parsed_results:
                    if not file_info:
                        continue
                    fp = file_info.get('full_path', '')
                    fid = fp_to_id.get(fp, 0)
                    if fid == 0:
                        continue
                    for ent in file_info.get('entities', []):
                        ename = ent.get('name', '')
                        if not ename:
                            continue
                        items_filled.append((
                            ent.get('kind', 'TY'), ename, ename.lower(),
                            ename.lower()[::-1], fid, ent.get('line', 0),
                            ent.get('parent', '') or '',
                            ent.get('definition', '') if ent.get('kind') == 'KS' else ent.get('definition', '')[:500], 'pending'
                        ))
                    # 单元名
                    unit_names = file_info.get('units', [])
                    if not unit_names:
                        unit_names = [Path(file_info.get('path', '')).stem]
                    for uname in unit_names:
                        if uname:
                            items_filled.append(('UI', uname, uname.lower(), uname.lower()[::-1], fid, 0, '', f"Unit {uname}", 'pending'))

                if items_filled:
                    cursor.executemany("""
                        INSERT OR IGNORE INTO vocabularies (type, name, name_lower, name_lower_rev, file_id,
                            line, base_class, description, vector_status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, items_filled)
                    conn.commit()

            _insert_end = time.time()
            logger.info(f"入库完成: {len(file_records)} 文件, {len(items_filled)} 实体, 耗时 {_insert_end-_insert_start:.1f}s")

        # 检测已删除的文件（仅在增量模式下）
        deleted_files = 0
        if not rebuild and existing_files:
            for old_path, old_info in existing_files.items():
                if old_path not in new_file_paths:
                    cursor.execute("DELETE FROM vocabularies WHERE file_id = ?", (old_info['id'],))
                    cursor.execute("DELETE FROM files WHERE id = ?", (old_info['id'],))
                    deleted_files += 1
            if deleted_files > 0:
                logger.info(f"检测到 {deleted_files} 个文件已被删除")

        conn.commit()

        # 统计
        cursor.execute("SELECT COUNT(*) FROM files")
        total_file_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='TC'")
        class_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE type='FF'")
        func_count = cursor.fetchone()[0]

        # 元数据
        cursor.execute("DELETE FROM metadata")
        for key, val in [
            ('total_files', str(total_file_count)),
            ('total_classes', str(class_count)),
            ('total_functions', str(func_count)),
            ('build_time', datetime.now().isoformat()),
            ('last_build_time', datetime.now().isoformat()),
            ('last_build_duration', str(int(time.time() - _build_start))),
            ('source_hash', current_hash),
        ]:
            cursor.execute("INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?)", (key, val, current_time))
        set_schema_version_in_db(cursor)
        conn.commit()
        conn.close()

        logger.info(f"项目知识库构建完成!")
        logger.info(f"  文件: {total_file_count}")
        logger.info(f"  类: {class_count}")
        logger.info(f"  函数: {func_count}")
        self._report_progress(95, f"项目 KB: {total_file_count} 文件, {class_count} 类, {func_count} 函数")

        self._report_progress(100, "项目知识库构建完成")

        try:
            self.build_vectors()
        except Exception as e:
            logger.warning("构建 embedding 向量失败（非关键错误）: %s", e)
        return True

    def check_and_update_project_kb(self) -> bool:
        """
        检查项目源码是否有变更

        Returns:
            True 表示知识库最新，False 表示已检测到变更（需要重建）
        """
        current_hash = self._calculate_source_hash(self.project_dir)
        # 从 SQLite metadata 表读取缓存 hash
        cached_hash = None
        try:
            db_file = self.kb_dir / "knowledge.sqlite"
            if db_file.exists():
                conn = get_connection(str(db_file), use_wal=False)
                try:
                    row = conn.execute("SELECT value FROM metadata WHERE key='source_hash'").fetchone()
                    if row:
                        cached_hash = row[0]
                finally:
                    conn.close()
        except Exception as e:
            logger.debug("忽略非致命异常: %s", str(e))

        if current_hash != cached_hash:
            logger.info("检测到项目源码变动（搜索将使用旧知识库，请手动触发重建）")
            return False  # 有变更，但不在搜索时阻塞重建

        return True  # 无变更

    def load_knowledge_bases(self) -> bool:
        """
        加载知识库（合并后统一从 knowledge.sqlite 加载）

        Returns:
            是否加载成功
        """
        try:
            main_db = self.kb_dir / "knowledge.sqlite"
            if main_db.exists():
                self.project_kb = SQLiteVectorKnowledgeBase(str(self.kb_dir), db_file="knowledge.sqlite")
                # 合并后 project_kb 和 thirdparty_kb 指向同一个数据库
                self.thirdparty_kb = self.project_kb
                logger.info(f"知识库加载成功: {main_db}")
                return True

            # 旧格式兼容
            old_project = self.kb_dir / "project" / "index" / "source_index.json"
            old_thirdparty = self.kb_dir / "thirdparty" / "index" / "source_index.json"
            if old_project.exists() or old_thirdparty.exists():
                if old_project.exists():
                    self.project_kb = SQLiteVectorKnowledgeBase(str(self.kb_dir / "project"), db_file="knowledge.sqlite")
                if old_thirdparty.exists():
                    self.thirdparty_kb = SQLiteVectorKnowledgeBase(str(self.kb_dir / "thirdparty"), db_file="knowledge.sqlite")
                logger.info("知识库加载成功 (旧格式)")
                return True

            return False
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
        获取知识库统计信息（合并后统一从 knowledge.sqlite 读取）

        Returns:
            统计信息
        """
        stats = {"project": None, "thirdparty": None}
        db_file = self.kb_dir / "knowledge.sqlite"
        if not db_file.exists():
            return stats

        try:
            conn = get_connection(str(db_file), use_wal=False)
        except Exception as e:
            logger.warning("连接知识库失败（统计跳过）: %s", e)
            return stats

        try:
            cursor = conn.cursor()
            for cat_key, cat_val in [("project", "source"), ("thirdparty", "thirdparty")]:
                try:
                    cursor.execute("SELECT COUNT(*) FROM files WHERE category=?", (cat_val,))
                    file_count = cursor.fetchone()[0]
                    if file_count == 0:
                        continue
                    cursor.execute("""
                        SELECT COUNT(*) FROM vocabularies v
                        JOIN files f ON v.file_id = f.id
                        WHERE f.category=? AND v.type='TC'
                    """, (cat_val,))
                    classes = cursor.fetchone()[0]
                    cursor.execute("""
                        SELECT COUNT(*) FROM vocabularies v
                        JOIN files f ON v.file_id = f.id
                        WHERE f.category=? AND v.type='FF'
                    """, (cat_val,))
                    funcs = cursor.fetchone()[0]
                    stats[cat_key] = {"files": file_count, "classes": classes, "functions": funcs}
                except Exception as e:
                    logger.debug("统计分类 %s 失败: %s", cat_val, e)
        except Exception as e:
            logger.warning("统计查询异常: %s", e)
        finally:
            try:
                conn.close()
            except Exception as e:
                logger.debug("忽略非致命异常: %s", str(e))
        return stats

    def _report_progress(self, percent: float, message: str) -> None:
        """报告进度（安全调用 progress_callback）"""
        if self.progress_callback:
            try:
                self.progress_callback(percent, message)
            except Exception as e:
                logger.warning("progress_callback 执行失败: %s", e)

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
