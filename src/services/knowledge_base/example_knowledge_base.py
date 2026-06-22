"""
示例知识库服务

为 Delphi 官方 Demos 和三方库 Demos 提供独立的全文检索知识库：
1. 自动发现 Delphi 官方 Demo 目录（注册表 RootDir/Samples、公共文档路径）
2. 从 thirdparty_paths.json 发现三方库 Demo 目录（父/祖父级兄弟目录）
3. 直接写入 ZVec 集合，不经过 SQLite
"""

import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import zvec

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

        logger.info("示例知识库初始化完成: %s", self.kb_dir)

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

    def _scan_directory(
        self,
        demo_path: str,
        label: str,
        source_type: str,
        rebuild: bool = False,
    ) -> Dict[str, int]:
        """
        扫描单个 Demo 目录，返回待入库的文档列表。

        Args:
            demo_path: 要扫描的目录
            label: 显示标签（如 "Delphi 12 Athens"）
            source_type: 来源类型（"delphi_official" / "thirdparty"）
            rebuild: 是否强制重建（跳过增量检测）

        Returns:
            {"files_scanned": 本次入库数, "total": 累计总数, "docs": chunked ZVec docs}
        """
        url_prefix = f"{source_type}:{label}"

        new_files = updated_files = skipped_files = 0
        chunked_docs: List[zvec.Doc] = []
        total_in_dir = 0
        CHUNK_LINES = 5000

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

                    new_files += 1
                    title = fp.stem
                    rel_path = str(
                        Path(full_path).relative_to(Path(demo_path))
                    ).replace(os.sep, '/')

                    # 按行切块
                    lines = content.split('\n')
                    for ci in range(0, len(lines), CHUNK_LINES):
                        chunk = "\n".join(lines[ci:ci + CHUNK_LINES])
                        chunk_id = hashlib.md5(f"{full_path}#chunk{ci//CHUNK_LINES}".encode()).hexdigest()[:16]
                        chunked_docs.append(zvec.Doc(
                            id=chunk_id,
                            fields={
                                'chunk_text': (title[:200] + "\n" + chunk)[:100000],
                                'title': title[:500],
                                'path': full_path[:500],
                                'extension': ext[:20],
                                'url': url_prefix[:500],
                            }
                        ))

                    total_in_dir += 1

                except (OSError, PermissionError) as e:
                    logger.debug("读取文件失败 %s: %s", full_path, e)

        logger.info(
            "  %s: %d 文件, %d 个段落 (共 %d 行)",
            label, total_in_dir, len(chunked_docs),
        )
        return {"files_scanned": total_in_dir, "docs": chunked_docs}

    # ──────────────────────────────────────────────
    # 全量构建
    # ──────────────────────────────────────────────

    def build_example_knowledge_base(
        self, rebuild: bool = False
    ) -> bool:
        """
        全量构建示例知识库。

        流程：
        1. 清理旧 ZVec 数据（若 rebuild）
        2. 发现 Delphi 官方 Demos
        3. 发现三方库 Demos
        4. 扫描所有 Demo 文件，直接写入 ZVec
        5. 构建 ZVec 全文索引

        Args:
            rebuild: 是否强制重建

        Returns:
            是否构建成功
        """
        _build_start = time.time()

        if rebuild:
            self._clean_zvec_files()
            logger.info("强制重建，已清空旧 ZVec 数据")

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

        # ── 扫描文件并直接写入 ZVec ──
        all_chunked_docs: List[zvec.Doc] = []
        dir_count = len(all_dirs)
        for i, (demo_path, label, source_type) in enumerate(all_dirs):
            pct = 10 + (i / dir_count) * 75
            self._report_progress(
                pct, f"扫描 [{i+1}/{dir_count}]: {label}"
            )
            logger.info("扫描 Demo 目录 [%d/%d]: %s (%s)", i + 1, dir_count, label, demo_path)

            info = self._scan_directory(
                demo_path, label, source_type, rebuild=rebuild,
            )
            if info.get("docs"):
                all_chunked_docs.extend(info["docs"])

        if not all_chunked_docs:
            logger.warning("未扫描到任何文件")
            self._report_progress(100, "未扫描到文件")
            return False

        # ── 写入 ZVec（用临时子目录避免 create_and_open 路径已存在）──
        self._report_progress(87, "写入 ZVec 集合...")
        schema = zvec.CollectionSchema("example_kb", fields=[
            zvec.FieldSchema("chunk_text", zvec.DataType.STRING),
            zvec.FieldSchema("title", zvec.DataType.STRING),
            zvec.FieldSchema("path", zvec.DataType.STRING),
            zvec.FieldSchema("extension", zvec.DataType.STRING),
            zvec.FieldSchema("url", zvec.DataType.STRING),
        ])

        import uuid
        tmp_zvec_name = f".zvec_tmp_{uuid.uuid4().hex[:8]}"
        tmp_zvec_path = self.kb_dir / tmp_zvec_name
        col = zvec.create_and_open(str(tmp_zvec_path), schema=schema)
        try:
            BATCH_SIZE = 500
            for i in range(0, len(all_chunked_docs), BATCH_SIZE):
                batch = all_chunked_docs[i:i + BATCH_SIZE]
                col.insert(batch)
            col.flush()

            # 全文索引
            self._report_progress(92, "构建全文索引...")
            col.create_index("chunk_text", zvec.FtsIndexParam(tokenizer_name="jieba"))
            col.optimize()
            col.flush()
        finally:
            try:
                col.close()
            except Exception:
                pass
            # 合并 ZVec 文件到 kb_dir
            self._clean_zvec_files()
            if tmp_zvec_path.exists():
                for item in tmp_zvec_path.iterdir():
                    target = self.kb_dir / item.name
                    if item.is_dir():
                        import shutil
                        try:
                            shutil.copytree(str(item), str(target), dirs_exist_ok=True)
                        except Exception:
                            pass
                    else:
                        try:
                            import shutil
                            shutil.copy2(str(item), str(target))
                        except Exception:
                            pass
                import shutil
                shutil.rmtree(str(tmp_zvec_path), ignore_errors=True)

        build_duration = int(time.time() - _build_start)
        logger.info(
            "示例知识库构建完成: %d 文件, %d 个段落, 耗时 %d 秒",
            len([d for d in all_chunked_docs if d.fields.get("path")]),
            len(all_chunked_docs), build_duration,
        )

        self._report_progress(
            100,
            f"示例 KB 构建完成: {len(all_chunked_docs)} 段落, {len(all_dirs)} 来源",
        )
        return True

    def _clean_zvec_files(self):
        """清除 kb_dir 下的 ZVec 数据文件"""
        import shutil
        for item in list(self.kb_dir.iterdir()):
            name = item.name
            if name.startswith(("scalar", "fts", "idmap", "del.", "manifest", "LOCK", "LOG", "CURRENT", "IDENTITY", "OPTIONS", "zvec_tmp")):
                if item.is_dir():
                    shutil.rmtree(str(item), ignore_errors=True)
                else:
                    try:
                        item.unlink()
                    except Exception:
                        pass

    # ════════════════════════════════════════
    # 搜索
    # ════════════════════════════════════════

    def search(
        self, query: str, top_k: int = 20
    ) -> List[Dict[str, Any]]:
        """
        全文搜索示例知识库（ZVec 全文搜索）。

        Args:
            query: 搜索关键词
            top_k: 最大返回数

        Returns:
            [{"title": "...", "full_path": "...", "source": "...",
              "snippet": "...", "line_count": ...}, ...]
        """
        try:
            col = zvec.open(str(self.kb_dir))
            results = col.query(
                zvec.Query(field_name="chunk_text", fts=zvec.Fts(match_string=query)),
                topk=top_k * 2,
            )

            zvec_list = []
            seen_paths = set()
            for r in results:
                path_val = r.fields.get('path', '')
                if path_val in seen_paths:
                    continue
                seen_paths.add(path_val)

                chunk_text = r.fields.get('chunk_text', '')
                title = r.fields.get('title', chunk_text[:80] if chunk_text else "")
                zvec_list.append({
                    "title": title,
                    "full_path": path_val,
                    "source": r.fields.get('url', ''),
                    "line_count": 0,
                    "snippet": chunk_text[:200],
                })

                if len(zvec_list) >= top_k:
                    break

            return zvec_list
        except Exception as e:
            logger.debug("ZVec 搜索失败: %s", e)
            return []

    # ──────────────────────────────────────────────
    # 生命周期
    # ──────────────────────────────────────────────

    def load_knowledge_base(self) -> bool:
        """检查 ZVec 数据是否存在"""
        if not self.kb_dir.exists():
            return False
        return any(f.name.startswith("manifest") for f in self.kb_dir.iterdir())

    # ──────────────────────────────────────────────
    # 统计
    # ──────────────────────────────────────────────

    def get_statistics(self) -> Dict[str, Any]:
        """获取知识库统计信息"""
        stats: Dict[str, Any] = {}

        try:
            col = zvec.open(str(self.kb_dir))
            stats["files"] = col.stats.doc_count

            # 按扩展名分布统计（需 FTS 查询，若查询失败则跳过分布）
            if stats["files"] > 0:
                try:
                    all_docs = col.query(
                        zvec.Query(field_name="chunk_text", fts=zvec.Fts(query_string="*")),
                        topk=min(stats["files"], 2000),
                    )
                    ext_counts: Dict[str, int] = {}
                    for d in all_docs:
                        ext = d.fields.get('extension', '(no ext)')
                        ext_counts[ext] = ext_counts.get(ext, 0) + 1
                    stats["by_extension"] = ext_counts
                except Exception:
                    stats["by_extension"] = {}
            else:
                stats["by_extension"] = {}

            # ZVec 文件总大小
            total_size = 0
            for f in self.kb_dir.iterdir():
                if f.is_file() and not f.name.startswith('.'):
                    total_size += f.stat().st_size
            stats["database_size_mb"] = round(total_size / (1024 * 1024), 2)

        except Exception as e:
            logger.warning("获取统计信息失败: %s", e)
            stats["files"] = 0
            stats["by_extension"] = {}
            stats["database_size_mb"] = 0

        return stats

    # ──────────────────────────────────────────────
    # 生命周期
    # ──────────────────────────────────────────────

    def close(self):
        """清理资源（ZVec 无状态，无需操作）"""
        pass

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
