"""
ZVec 知识库适配器 — 兼容现有 DelphiKnowledgeBaseService 接口

让 ZVecKnowledgeBase 可以被 server.py / knowledge_base.py 直接使用。
"""
import json
import os
import time
import shutil
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ZVecKnowledgeBaseAdapter:
    """
    适配器：让 ZVecKnowledgeBase 兼容 DelphiKnowledgeBaseService 的接口。

    代理方法:
      search_by_name(query)         → ZVec search
      semantic_search_classes()     → ZVec search + filter class
      semantic_search_functions()   → ZVec search + filter function
      get_statistics()              → ZVec stats
      build_knowledge_base()        → ZVec build
      close()
    """

    def __init__(self, kb_dir: str, source_dirs: Optional[List[str]] = None):
        from .zvec_knowledge_base import ZVecKnowledgeBase

        self.kb_dir = Path(kb_dir)
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self.source_dirs = source_dirs or []

        # 迁移：旧版数据在 kb_dir/delphi_kb/ 子目录，向上提升一级
        old_dir = self.kb_dir / "delphi_kb"
        if old_dir.exists():
            _migrate_old_zvec_data(old_dir, self.kb_dir)

        self._zvec = ZVecKnowledgeBase(str(self.kb_dir))
        self.progress_callback: Optional[Callable] = None

    # ── 构建 ──

    def build_knowledge_base(self, version: str = None, rebuild: bool = False) -> bool:
        """
        构建知识库（兼容旧接口）。

        从 source_dirs 收集 .pas 文件，chunk 后导入 ZVec。
        """
        from .zvec_knowledge_base import ZVecKnowledgeBase

        if not self.source_dirs:
            logger.error("没有配置源码目录，无法构建")
            return False

        # 收集文件
        all_files: List[str] = []
        for sd in self.source_dirs:
            src = Path(sd)
            if src.exists():
                all_files.extend(
                    str(f) for f in src.rglob("*.pas") if f.is_file()
                )

        if not all_files:
            logger.warning(f"未在 {self.source_dirs} 中找到 .pas 文件")
            return False

        logger.info(f"构建 ZVec 知识库: {len(all_files)} 文件")

        # 去旧库（rebuild）
        if rebuild:
            # 重建：删整目录（不 mkdir，让 create_and_open 自行创建）
            import shutil as _shutil
            if self.kb_dir.exists():
                _shutil.rmtree(str(self.kb_dir), ignore_errors=True)
            from .zvec_knowledge_base import ZVecKnowledgeBase
            self._zvec = ZVecKnowledgeBase(str(self.kb_dir))

        # 构建
        stats = self._zvec.build(all_files, progress_callback=self.progress_callback)

        # 保存构建元数据到 metadata.json
        if stats and stats.get("status") == "ok":
            metadata = {
                "files": stats.get("files", 0),
                "classes": stats.get("classes", 0),
                "chunks": stats.get("chunks", 0),
                "time_seconds": stats.get("time_seconds", 0),
            }
            try:
                (self.kb_dir / "metadata.json").write_text(
                    json.dumps(metadata, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
            except Exception as e:
                logger.warning(f"保存 KB metadata 失败: {e}")

        return stats.get("status") == "ok"

    # ── 搜索 ──

    def search_by_name(self, query: str) -> List[Dict]:
        """
        按名称搜索符号（兼容旧接口返回格式）。
        在新 schema 中 chunk_text 已含 entity_name 前缀，直接搜 chunk_text。
        """
        try:
            result = self._zvec.search(query, top_k=50)
        except Exception as e:
            logger.debug(f"ZVec 搜索失败: {e}")
            return []

        symbols = []
        for r in result.get("results", []):
            fields = r.get("fields", {})
            chunk_text = fields.get("chunk_text", "")
            chunk_type = fields.get("chunk_type", "")
            file_path = fields.get("file_path", "")
            start_line = fields.get("start_line", 0)
            base_class = fields.get("base_class", "")

            # 从 chunk_text 首行提取 entity_name
            first_line = chunk_text.split('\n')[0].strip() if chunk_text else ""

            kind_map = {
                "class": "TC", "record": "TR", "interface": "TI",
                "object": "TC", "unit": "UI",
            }
            kind_code = kind_map.get(chunk_type, chunk_type.upper() if chunk_type else "??")

            symbols.append({
                "name": first_line,
                "kind_code": kind_code,
                "kind": chunk_type,
                "type_name": chunk_type,
                "file": {
                    "path": file_path,
                    "full_path": str(Path(self.kb_dir.parent, file_path)) if file_path else "",
                },
                "line": start_line,
                "definition": chunk_text[:300],
                "base_class": base_class,
            })
        return symbols

    def semantic_search_classes(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """语义搜索类 — 用 ZVec FTS + filter"""
        try:
            result = self._zvec.search(query, chunk_type="class", top_k=top_k)
        except Exception as e:
            logger.debug(f"ZVec 语义搜索失败: {e}")
            return []
        return [
            (r["fields"].get("chunk_text", "").split("\n")[0].strip(), r.get("score", 0.0))
            for r in result.get("results", [])
        ]

    def semantic_search_functions(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """语义搜索函数"""
        try:
            result = self._zvec.search(query, top_k=top_k)
        except Exception as e:
            logger.debug(f"ZVec 函数搜索失败: {e}")
            return []
        return [
            (r["fields"].get("chunk_text", "").split("\n")[0].strip(), r.get("score", 0.0))
            for r in result.get("results", [])
        ]

    def search_by_keyword(self, keyword: str) -> List[Dict]:
        """关键词搜索"""
        return self.search_by_name(keyword)

    def search_by_unit_name(self, unit_name: str) -> List[Dict]:
        """按单元名搜索"""
        try:
            result = self._zvec.search(unit_name, chunk_type="unit", top_k=10)
        except Exception as e:
            logger.debug(f"ZVec 单元搜索失败: {e}")
            return []
        return [
            {"name": r["fields"].get("chunk_text", "").split("\n")[0].strip(),
             "file": {"path": r["fields"].get("file_path", ""),
                      "full_path": r["fields"].get("file_path", "")}}
            for r in result.get("results", [])
        ]

    # ── 统计 ──

    def get_statistics(self) -> Dict:
        """获取统计信息（兼容旧接口）"""
        # 优先从 metadata.json 读取实际统计
        metadata_file = self.kb_dir / "metadata.json"
        meta = {"files": 0, "classes": 0, "chunks": 0}
        if metadata_file.exists():
            try:
                meta.update(json.loads(metadata_file.read_text(encoding="utf-8")))
            except Exception:
                pass

        # 获取实时的 ZVec doc_count（chunk 级）
        doc_count = 0
        try:
            stats = self._zvec.get_statistics()
            if isinstance(stats, dict):
                doc_count = stats.get("doc_count", 0)
        except Exception:
            pass

        db_size = _calc_zvec_dir_size(self.kb_dir)

        return {
            "files": meta.get("files", 0),
            "classes": meta.get("classes", 0),
            "chunks": doc_count or meta.get("chunks", 0),
            "database_size_mb": round(db_size / (1024 * 1024), 1),
        }

    def close(self):
        """关闭知识库"""
        self._zvec.close()

    def load_knowledge_base(self) -> bool:
        """兼容接口：检查 ZVec 集合是否存在"""
        return _has_zvec_data(self.kb_dir)

    @property
    def kb_instance(self):
        """兼容接口：返回自身（有些代码用 .kb_instance.search_by_name）"""
        return self


# ══════════════════════════════════════════════════════════════════
# 模块级辅助函数（独立于实例，可被外部代码复用）
# ══════════════════════════════════════════════════════════════════


def _has_zvec_data(dir_path: Path) -> bool:
    """
    检查目录中是否有 ZVec 集合数据。
    ZVec 创建 collection 时至少会生成 manifest.* 文件。
    """
    if not dir_path.exists():
        return False
    try:
        for f in dir_path.iterdir():
            if f.name.startswith("manifest"):
                return True
    except PermissionError:
        pass
    return False


def _clean_zvec_collection(dir_path: Path):
    """清理目录中 ZVec 生成的数据文件和子目录"""
    for item in dir_path.iterdir():
        name = item.name
        # ZVec 内部文件：manifest, scalar.*.ipc, *.sst, *.rocksdb, etc.
        if name.startswith("manifest") or name.startswith("scalar.") or \
           name.startswith("fts.") or name.startswith("scalar.index.") or \
           name.startswith("idmap") or name.startswith("del.") or \
           name == "LOCK":
            _safe_remove(item)
        # RocksDB 子目录
        if item.is_dir() and (name.endswith(".rocksdb") or name.startswith("scalar.")):
            shutil.rmtree(item, ignore_errors=True)


def _safe_remove(path: Path):
    """安全删除文件或目录"""
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    except Exception:
        pass


def _calc_zvec_dir_size(dir_path: Path) -> int:
    """计算 ZVec 数据目录大小（字节）"""
    total = 0
    try:
        for dp, _, fs in os.walk(dir_path):
            for f in fs:
                fp = os.path.join(dp, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _migrate_old_zvec_data(old_dir: Path, new_dir: Path):
    """
    将旧版 delphi_kb/ 子目录中的数据迁移到根目录。

    旧结构: kb_dir/delphi_kb/{zvec_data}
    新结构: kb_dir/{zvec_data}
    """
    if not old_dir.exists() or old_dir == new_dir:
        return

    logger.info("迁移 ZVec 数据: %s → %s", old_dir, new_dir)
    for item in old_dir.iterdir():
        target = new_dir / item.name
        try:
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
        except Exception as e:
            logger.warning("迁移文件失败 %s: %s", item.name, e)

    shutil.rmtree(old_dir, ignore_errors=True)
    logger.info("ZVec 数据迁移完成，已删除旧目录 %s", old_dir)
