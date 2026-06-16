"""
示例知识库服务

为 Delphi 官方 Demos 和三方库 Demos 提供独立的全文检索知识库：
1. 自动发现 Delphi 官方 Demo 目录（注册表 RootDir/Samples、公共文档路径）
2. 从 thirdparty_paths.json 发现三方库 Demo 目录（父/祖父级兄弟目录）
3. 按文档模式（全文 + FTS5）存储，不做 class/function 结构化提取
"""

import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from src.services.knowledge_base.schema import create_document_tables
from src.services.knowledge_base.fts5_lazy_manager import FTS5LazyManager
from src.utils.logger import get_logger
from src.utils.delphi_env import get_delphi_root_dir, get_delphi_version

logger = get_logger(__name__)


class ExampleKnowledgeBase:
    """示例知识库管理器"""

    # 扫描的 Delphi 源文件扩展名
    DELPHI_EXTENSIONS = {'.pas', '.dpr', '.dpk', '.dfm', '.fmx', '.inc'}

    # 扫描时跳过的目录名（全小写，因为对比时会 lower()）
    SKIP_DIR_NAMES = {
        '.git', '__pycache__', 'win32', 'win64',
        '__history', '__recovery', 'backup', '.svn', 'node_modules',
    }

    # 三方库 Demo 兄弟目录的候选名（大小写不敏感）
    DEMO_DIR_NAMES = {
        'demos', 'demo', 'samples', 'sample',
        'examples', 'example', 'tests', 'test', 'testunits',
    }

    def __init__(
        self,
        kb_dir: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ):
        """
        初始化示例知识库

        Args:
            kb_dir: 知识库目录，默认 data/example-knowledge-base/
            progress_callback: 进度回调 (percent, message)
        """
        if kb_dir is None:
            project_root = Path(__file__).parent.parent.parent.parent
            kb_dir = project_root / "data" / "example-knowledge-base"
        else:
            kb_dir = Path(kb_dir)

        self.kb_dir = kb_dir
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self.progress_callback = progress_callback
        self._db: Optional[sqlite3.Connection] = None

        # FTS5 管理器（延迟初始化）
        self.fts5: Optional[FTS5LazyManager] = None

        logger.info("示例知识库初始化完成: %s", self.kb_dir)

    # ──────────────────────────────────────────────
    # 数据库连接与初始化
    # ──────────────────────────────────────────────

    def _get_db_path(self) -> str:
        return str(self.kb_dir / "knowledge.sqlite")

    def _get_db(self) -> sqlite3.Connection:
        """获取数据库连接（懒初始化 + 缓存）"""
        if self._db is None:
            db_path = self._get_db_path()
            self._db = sqlite3.connect(db_path)
            self._db.row_factory = sqlite3.Row
        return self._db

    def _close_db(self):
        if self._db is not None:
            try:
                self._db.close()
            except Exception:
                pass
            self._db = None

    def _init_database(self, cursor: sqlite3.Cursor):
        """
        初始化数据库表结构

        复用文档 KB 的 documents + metadata 表，
        额外创建 demo_sources 表追踪来源。
        """
        # 复用文档 KB 的标准表（documents / document_entities / metadata）
        create_document_tables(cursor)

        # 额外：full_path 上建立唯一索引，用于 INSERT OR REPLACE
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_fp ON documents(full_path)"
        )

        # 来源目录记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS demo_sources (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                source_path  TEXT NOT NULL UNIQUE,
                source_type  TEXT NOT NULL,
                label        TEXT,
                file_count   INTEGER DEFAULT 0,
                last_scanned TEXT,
                created_at   REAL DEFAULT (julianday('now'))
            )
        """)

    def _init_fts5(self):
        """初始化 FTS5 懒加载管理器"""
        if self.fts5 is None:
            self.fts5 = FTS5LazyManager(
                db_path=self._get_db_path(),
                main_table='documents',
                fts_table='documents_fts',
                columns=['title', 'content'],
                tokenize='unicode61',
            )
            # 创建 FTS5 虚拟表（如果不存在）
            with self._get_db() as conn:
                self.fts5.create_fts_table(conn)

    # ──────────────────────────────────────────────
    # Demo 路径发现
    # ──────────────────────────────────────────────

    def discover_delphi_official_demos(
        self, version: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        从注册表发现 Delphi 官方 Demos 路径。

        Args:
            version: Delphi 版本号，默认自动检测最新版本

        Returns:
            [{"path": "C:\\...", "label": "Delphi 12 Athens"}, ...]
        """
        if version is None:
            version = get_delphi_version()
        if version is None:
            logger.info("未检测到 Delphi 版本，跳过官方 Demo 发现")
            return []

        root_dir = get_delphi_root_dir(version)
        if not root_dir:
            logger.warning("无法获取 Delphi 根目录")
            return []

        root = Path(root_dir)
        from src.utils.delphi_versions import get_version_name
        version_name = get_version_name(version)

        candidates: List[Path] = []

        # $(RootDir)\Samples\ 和 $(RootDir)\Demos\
        for sub in ('Samples', 'Demos'):
            candidates.append(root / sub)
            candidates.append(root.parent / sub)  # 有时 Demo 在 RootDir 的父级

        # C:\Users\Public\Documents\Embarcadero\Studio\<ver>\Samples\
        pub = (
            Path(os.path.expanduser("~\\Documents"))
            / "Embarcadero" / "Studio" / version / "Samples"
        )
        candidates.append(pub)

        found: List[Dict[str, str]] = []
        seen: Set[str] = set()

        for c in candidates:
            try:
                resolved = c.resolve()
                if resolved.exists() and str(resolved) not in seen:
                    seen.add(str(resolved))
                    found.append({
                        "path": str(resolved),
                        "label": f"Delphi {version_name}",
                    })
            except (OSError, PermissionError):
                continue

        logger.info(
            "发现 %d 个 Delphi 官方 Demo 目录 (version=%s)",
            len(found), version,
        )
        return found

    def discover_thirdparty_demos(self) -> List[Dict[str, str]]:
        """
        从 thirdparty_paths.json 发现三方库 Demos 路径。

        对每条注册路径，检查其父目录和祖父目录下是否存在
        Demos/Samples/Examples/Tests 等兄弟目录。

        Returns:
            [{"path": "C:\\...", "label": "FastReports"}, ...]
        """
        project_root = Path(__file__).parent.parent.parent.parent
        paths_file = (
            project_root / "data" / "thirdparty-knowledge-base"
            / "thirdparty_paths.json"
        )

        if not paths_file.exists():
            logger.info("三方库路径文件不存在，跳过三方库 Demo 发现")
            return []

        try:
            with open(paths_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("读取三方库路径文件失败: %s", e)
            return []

        registered_paths: list = data.get("paths", [])
        if not registered_paths:
            return []

        found_map: Dict[str, str] = {}  # path -> label

        demo_names_lower = self.DEMO_DIR_NAMES

        for rp in registered_paths:
            path = Path(rp)
            if not path.exists():
                continue

            # 只检查在项目目录外的路径（项目内的 Demo 应由项目 KB 处理）
            # 先做判定，避免误扫项目自己的 Demo
            try:
                path.resolve().relative_to(project_root.resolve())
                # 在项目目录内，跳过
                continue
            except ValueError:
                pass  # 在项目目录外，继续

            parent = path.parent
            grandparent = parent.parent

            for level, level_label in [(parent, parent.name), (grandparent, grandparent.name)]:
                if level == path or not level.exists():
                    continue
                try:
                    for child in level.iterdir():
                        if child.is_dir() and child.name.lower() in demo_names_lower:
                            resolved = str(child.resolve())
                            if resolved not in found_map:
                                found_map[resolved] = level_label
                except (OSError, PermissionError):
                    continue

        result = [{"path": p, "label": label} for p, label in found_map.items()]
        logger.info("发现 %d 个三方库 Demo 目录", len(result))
        return result

    # ──────────────────────────────────────────────
    # 文件扫描与入库
    # ──────────────────────────────────────────────

    def _flush_batch(
        self, cursor: sqlite3.Cursor, batch: List[Tuple[Any, ...]]
    ):
        """批量写入 documents 表"""
        cursor.executemany("""
            INSERT OR REPLACE INTO documents
                (title, title_lower, title_rev, full_path, path,
                 extension, content, size, line_count, hash,
                 last_modified, content_type, url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, batch)

    def _scan_directory(
        self,
        demo_path: str,
        label: str,
        source_type: str,
        cursor: sqlite3.Cursor,
        rebuild: bool = False,
    ) -> Dict[str, int]:
        """
        扫描单个 Demo 目录，将文件入库。

        Args:
            demo_path: 要扫描的目录
            label: 显示标签（如 "Delphi 12 Athens"）
            source_type: 来源类型（"delphi_official" / "thirdparty"）
            cursor: 数据库游标
            rebuild: 是否强制重建（跳过增量检测）

        Returns:
            {"files_scanned": 本次入库数, "total": 累计总数}
        """
        # 增量模式：加载已有文件 hash
        existing: Dict[str, str] = {}
        if not rebuild:
            url_prefix = f"{source_type}:{label}"
            cursor.execute(
                "SELECT full_path, hash FROM documents WHERE url = ?",
                (url_prefix,),
            )
            for row in cursor.fetchall():
                existing[row[0]] = row[1]

        new_files = updated_files = skipped_files = 0
        batch: List[Tuple] = []
        total_in_dir = 0

        for root, dirs, files in os.walk(demo_path):
            dirs[:] = [d for d in dirs if d.lower() not in self.SKIP_DIR_NAMES]

            for file in files:
                ext = Path(file).suffix.lower()
                if ext not in self.DELPHI_EXTENSIONS:
                    continue

                full_path = str(Path(root) / file)
                try:
                    fp = Path(full_path)
                    stat = fp.stat()
                    content = fp.read_text(encoding='utf-8', errors='replace')
                    file_hash = hashlib.md5(
                        content.encode('utf-8')
                    ).hexdigest()

                    if not rebuild and full_path in existing:
                        if existing[full_path] == file_hash:
                            skipped_files += 1
                            continue
                        updated_files += 1
                    else:
                        new_files += 1

                    rel_path = str(
                        Path(full_path).relative_to(Path(demo_path))
                    ).replace(os.sep, '/')

                    batch.append((
                        fp.stem,                   # title
                        fp.stem.lower(),            # title_lower
                        fp.stem.lower()[::-1],      # title_rev
                        full_path,                  # full_path
                        rel_path,                   # path
                        ext,                        # extension
                        content,                    # content
                        len(content),               # size
                        content.count('\n') + 1,    # line_count
                        file_hash,                  # hash
                        datetime.fromtimestamp(
                            stat.st_mtime
                        ).isoformat(),              # last_modified
                        'delphi_demo',              # content_type
                        f"{source_type}:{label}",   # url
                    ))

                    if len(batch) >= 100:
                        self._flush_batch(cursor, batch)
                        batch = []

                    total_in_dir += 1

                except (OSError, PermissionError) as e:
                    logger.debug("读取文件失败 %s: %s", full_path, e)

        # 写入剩余批次
        if batch:
            self._flush_batch(cursor, batch)

        # 记录/更新来源
        cursor.execute("""
            INSERT OR REPLACE INTO demo_sources
                (source_path, source_type, label, file_count, last_scanned)
            VALUES (?, ?, ?, ?, ?)
        """, (
            demo_path,
            source_type,
            label,
            total_in_dir,
            datetime.now().isoformat(),
        ))

        logger.info(
            "  %s: %d 新增, %d 更新, %d 跳过 (共 %d 文件)",
            label, new_files, updated_files, skipped_files, total_in_dir,
        )
        return {"files_scanned": total_in_dir}

    # ──────────────────────────────────────────────
    # 全量构建
    # ──────────────────────────────────────────────

    def build_example_knowledge_base(
        self, rebuild: bool = False
    ) -> bool:
        """
        全量构建示例知识库。

        流程：
        1. 初始化数据库
        2. 发现 Delphi 官方 Demos
        3. 发现三方库 Demos
        4. 扫描所有 Demo 文件入库
        5. 构建 FTS5 全文索引

        Args:
            rebuild: 是否强制重建

        Returns:
            是否构建成功
        """
        _build_start = time.time()
        conn = self._get_db()
        cursor = conn.cursor()
        self._init_database(cursor)

        if rebuild:
            cursor.execute("DELETE FROM documents")
            cursor.execute("DELETE FROM demo_sources")
            cursor.execute("DELETE FROM metadata")
            conn.commit()
            logger.info("强制重建，已清空旧数据")

        # ── 发现 Demo 路径 ──
        self._report_progress(5, "发现 Demo 路径...")
        official = self.discover_delphi_official_demos()
        thirdparty = self.discover_thirdparty_demos()

        all_dirs: List[Tuple[str, str, str]] = []
        all_dirs.extend(
            (d["path"], d["label"], "delphi_official") for d in official
        )
        all_dirs.extend(
            (d["path"], d["label"], "thirdparty") for d in thirdparty
        )

        if not all_dirs:
            logger.warning("未发现任何 Demo 目录，跳过构建")
            self._report_progress(100, "未发现 Demo 目录")
            return False

        logger.info("共发现 %d 个 Demo 目录", len(all_dirs))

        # ── 扫描文件 ──
        total_files = 0
        dir_count = len(all_dirs)
        for i, (demo_path, label, source_type) in enumerate(all_dirs):
            pct = 10 + (i / dir_count) * 75
            self._report_progress(
                pct, f"扫描 [{i+1}/{dir_count}]: {label}"
            )
            logger.info("扫描 Demo 目录 [%d/%d]: %s (%s)", i + 1, dir_count, label, demo_path)

            info = self._scan_directory(
                demo_path, label, source_type, cursor, rebuild=rebuild,
            )
            total_files += info["files_scanned"]

        conn.commit()

        # ── FTS5 全文索引 ──
        self._report_progress(87, "构建 FTS5 全文索引...")
        self._init_fts5()
        try:
            with self._get_db() as c:
                self.fts5.create_fts_table(c)  # type: ignore[union-attr]
            self.fts5.rebuild_full()  # type: ignore[union-attr]
        except Exception as e:
            logger.warning("FTS5 索引构建失败（搜索将降级为 LIKE 查询）: %s", e)

        # ── 元数据 ──
        current_ts = datetime.now().timestamp()
        build_duration = int(time.time() - _build_start)
        cursor.execute("DELETE FROM metadata")
        for key, val in [
            ('total_files', str(total_files)),
            ('build_time', datetime.now().isoformat()),
            ('last_build_time', datetime.now().isoformat()),
            ('last_build_duration', str(build_duration)),
            ('delphi_demo_dirs', str(len(official))),
            ('thirdparty_demo_dirs', str(len(thirdparty))),
        ]:
            cursor.execute(
                "INSERT INTO metadata (key, value, updated_at) VALUES (?, ?, ?)",
                (key, val, current_ts),
            )
        conn.commit()

        logger.info(
            "示例知识库构建完成: %d 个文件, 耗时 %d 秒",
            total_files, build_duration,
        )
        self._report_progress(
            100,
            f"示例 KB 构建完成: {total_files} 文件, {len(all_dirs)} 来源",
        )
        return True

    # ──────────────────────────────────────────────
    # 搜索
    # ──────────────────────────────────────────────

    def search(
        self, query: str, top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """
        全文搜索示例知识库。

        优先使用 FTS5，失败时降级为 LIKE 模糊搜索。

        Args:
            query: 搜索关键词
            top_k: 最大返回数

        Returns:
            [{"title": "...", "full_path": "...", "source": "...",
              "snippet": "...", "line_count": ...}, ...]
        """
        self._init_fts5()
        conn = self._get_db()
        cursor = conn.cursor()

        # 确保 FTS5 表存在
        try:
            with self._get_db() as c:
                self.fts5.create_fts_table(c)  # type: ignore[union-attr]
        except Exception:
            pass

        # ── FTS5 搜索 ──
        # 对查询做简单转义：把用户输入包在双引号内做短语搜索
        escaped = query.replace('"', '""')
        fts_query = f'"{escaped}"'

        try:
            cursor.execute("""
                SELECT d.id, d.title, d.full_path, d.url, d.line_count,
                       snippet(documents_fts, 1, '<mark>', '</mark>', '...', 40) AS snippet
                FROM documents_fts
                JOIN documents d ON d.id = documents_fts.rowid
                WHERE documents_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, top_k))

            rows = cursor.fetchall()
            if rows:
                results = []
                for row in rows:
                    results.append({
                        "title": row["title"],
                        "full_path": row["full_path"],
                        "source": row["url"] or "",
                        "line_count": row["line_count"],
                        "snippet": row["snippet"],
                    })
                return results
        except Exception as e:
            logger.debug("FTS5 搜索失败，降级到 LIKE: %s", e)

        # ── 降级：LIKE 模糊搜索 ──
        like_pattern = f"%{query}%"
        try:
            cursor.execute("""
                SELECT id, title, full_path, url, line_count,
                       substr(content, 1, 200) AS snippet
                FROM documents
                WHERE content LIKE ? OR title LIKE ?
                ORDER BY line_count ASC
                LIMIT ?
            """, (like_pattern, like_pattern, top_k))

            results = []
            for row in cursor.fetchall():
                results.append({
                    "title": row["title"],
                    "full_path": row["full_path"],
                    "source": row["url"] or "",
                    "line_count": row["line_count"],
                    "snippet": row["snippet"],
                })
            return results
        except Exception as e:
            logger.error("LIKE 搜索也失败: %s", e)
            return []

    # ──────────────────────────────────────────────
    # 统计
    # ──────────────────────────────────────────────

    def get_statistics(self) -> Dict[str, Any]:
        """获取知识库统计信息"""
        conn = self._get_db()
        cursor = conn.cursor()
        self._init_database(cursor)

        stats: Dict[str, Any] = {}

        try:
            cursor.execute("SELECT COUNT(*) FROM documents")
            stats["files"] = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COALESCE(extension, '(no ext)') AS ext,
                       COUNT(*) AS cnt
                FROM documents
                GROUP BY ext ORDER BY cnt DESC
            """)
            stats["by_extension"] = dict(cursor.fetchall())

            # FTS5 覆盖
            self._init_fts5()
            if self.fts5:
                fts_stats = self.fts5.get_statistics()
                stats["fts_coverage"] = fts_stats.get("coverage", 0.0)

            # 来源统计
            cursor.execute(
                "SELECT source_type, COUNT(*) AS cnt "
                "FROM demo_sources GROUP BY source_type"
            )
            stats["sources"] = {
                row["source_type"]: {
                    "dir_count": row["cnt"],
                    "file_count": 0,
                }
                for row in cursor.fetchall()
            }
            # 补充每个来源的文件数
            for st in stats.get("sources", {}):
                cursor.execute(
                    "SELECT COUNT(*) FROM documents WHERE content_type=?",
                    (f"delphi_demo",),
                )
                stats["sources"][st]["file_count"] = cursor.fetchone()[0]

            # DB 大小
            db_path = self._get_db_path()
            if os.path.exists(db_path):
                stats["database_size_mb"] = (
                    os.path.getsize(db_path) / (1024 * 1024)
                )

            # 末次构建
            try:
                cursor.execute(
                    "SELECT value FROM metadata WHERE key='last_build_time'"
                )
                row = cursor.fetchone()
                stats["last_build_time"] = row[0] if row else None
                cursor.execute(
                    "SELECT value FROM metadata WHERE key='last_build_duration'"
                )
                row = cursor.fetchone()
                stats["last_build_duration"] = (
                    int(row[0]) if row else None
                )
            except Exception:
                pass

        except Exception as e:
            logger.warning("获取统计信息失败: %s", e)

        return stats

    # ──────────────────────────────────────────────
    # 生命周期
    # ──────────────────────────────────────────────

    def close(self):
        """关闭数据库连接"""
        self._close_db()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ──────────────────────────────────────────────
    # 内部工具
    # ──────────────────────────────────────────────

    def _report_progress(self, percent: float, message: str) -> None:
        """进度回调（安全调用）"""
        if self.progress_callback:
            try:
                self.progress_callback(percent, message)
            except Exception as e:
                logger.debug("进度回调异常（忽略）: %s", e)
