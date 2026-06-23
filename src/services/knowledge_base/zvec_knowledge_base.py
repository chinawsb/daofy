"""
ZVec 知识库服务 — 基于 ZVec 的 Delphi 源码搜索

功能:
  - 构建: 将 Delphi 源码 chunk 后导入 ZVec Collection
  - 搜索: 支持 FTS（全文）+ filter（类型/基类）混合搜索
  - 增量更新: 检测文件变更后局部重建

依赖: pip install zvec numpy
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class ZVecKnowledgeBase:
    """ZVec 知识库服务"""

    def __init__(self, kb_dir: str):
        """
        Args:
            kb_dir: 知识库存储目录
        """
        self.kb_dir = Path(kb_dir)
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self._collection = None
        self._db_path = str(self.kb_dir)

    # ════════════════════════════════════════
    # 构建
    # ════════════════════════════════════════

    def build(self,
              file_paths: List[str],
              progress_callback: Optional[Callable] = None) -> Dict:
        """
        构建知识库。

        流程:
          1. Chunk 所有文件
          2. 导入 ZVec Collection
          3. 建 FTS / InvertIndex

        Args:
            file_paths: .pas 文件路径列表
            progress_callback: 进度回调 (percent, message)

        Returns:
            统计信息
        """
        start_time = time.time()

        # ── Chunk ──
        from .delphi_chunker import chunk_file_list

        if progress_callback:
            progress_callback(5, "Chunking 文件...")

        chunks = chunk_file_list(file_paths)
        if not chunks:
            return {"status": "error", "message": "没有产生任何 chunk"}

        logger.info(f"Chunk 完成: {len(chunks)} chunks 来自 {len(file_paths)} 文件")

        # ── 导入 ZVec ──
        if progress_callback:
            progress_callback(30, f"导入 {len(chunks)} 个 chunk 到 ZVec...")

        import zvec
        from zvec import (CollectionSchema, FieldSchema, DataType,
                          FtsIndexParam, InvertIndexParam, Doc)

        # 创建或打开 collection
        col = self._open_collection(zvec)

        # Step 1: 插入所有数据
        if progress_callback:
            progress_callback(25, f"插入 {len(chunks)} chunks...")

        BATCH = 500
        inserted = 0
        for offset in range(0, len(chunks), BATCH):
            batch = chunks[offset:offset + BATCH]
            docs = []
            for i, c in enumerate(batch):
                docs.append(Doc(
                    id=f"c{offset + i:07d}",
                    fields={
                        # 将 entity_name 合并到 chunk_text 前端，确保 FTS 可搜索
                        "chunk_text": c['entity_name'][:500] + "\n" + str(c['chunk_text'])[:99480],
                        "chunk_type": c['chunk_type'],
                        "base_class": c['base_class'][:200],
                        "file_path": c['file_path'][:500],
                        "start_line": c['start_line'],
                        "end_line": c['end_line'],
                    },
                ))
            col.insert(docs)
            inserted += len(batch)

            if progress_callback and (offset + BATCH) % 4000 == 0:
                pct = 25 + int((offset + BATCH) / len(chunks) * 50)
                progress_callback(pct, f"插入 {offset + BATCH}/{len(chunks)}...")

        col.flush()

        # Step 2: 建单个 FTS 索引（ZVec 仅最后一个 FTS 索引能持久化）
        if progress_callback:
            progress_callback(80, "建索引...")
        # 合并所有可搜索文本到一个字段，避免多 FTS 索引 BUG
        col.create_index("chunk_text", FtsIndexParam(tokenizer_name="jieba"))
        col.create_index("chunk_type", InvertIndexParam())
        col.create_index("base_class", InvertIndexParam())

        # Step 3: optimize 确保持久化
        col.optimize()
        col.flush()

        elapsed = time.time() - start_time
        stats = {
            "status": "ok",
            "files": len(file_paths),
            "chunks": len(chunks),
            "time_seconds": round(elapsed, 1),
            "dir": str(self.kb_dir),
        }

        if progress_callback:
            progress_callback(100, f"构建完成: {len(chunks)} chunks 耗时 {elapsed:.1f}s")

        return stats

    def _open_collection(self, zvec):
        """打开或创建 ZVec Collection（合并字段版）"""
        from zvec import CollectionSchema, FieldSchema, DataType

        schema = CollectionSchema("delphi_kb", fields=[
            FieldSchema("chunk_text", DataType.STRING),   # 含 entity_name 前缀
            FieldSchema("chunk_type", DataType.STRING),
            FieldSchema("base_class", DataType.STRING),
            FieldSchema("file_path", DataType.STRING),
            FieldSchema("start_line", DataType.INT32),
            FieldSchema("end_line", DataType.INT32),
        ])

        # 不存在则创建，存在则打开
        if os.path.exists(self._db_path):
            self._collection = zvec.open(self._db_path)
        else:
            self._collection = zvec.create_and_open(
                path=self._db_path, schema=schema
            )
        return self._collection

    # ════════════════════════════════════════
    # 搜索
    # ════════════════════════════════════════

    def search(self,
               query: str,
               chunk_type: Optional[str] = None,
               base_class: Optional[str] = None,
               unit_name: Optional[str] = None,
               file_path: Optional[str] = None,
               top_k: int = 10,
               output_fields: Optional[List[str]] = None) -> Dict:
        """
        搜索知识库。

        Args:
            query: 搜索文本
            chunk_type: 过滤 chunk 类型（class/record/interface/unit）
            base_class: 过滤基类名
            unit_name: 过滤单元名
            file_path: 过滤文件路径
            top_k: 返回结果数
            output_fields: 返回字段

        Returns:
            {"results": [...], "total": N, "time_ms": M}
        """
        col = self._get_collection()
        if col is None:
            return {"results": [], "total": 0, "error": "知识库未构建"}

        if output_fields is None:
            output_fields = [
                "chunk_text", "chunk_type", "base_class",
                "file_path", "start_line", "end_line"
            ]

        # 构建 filter 表达式
        filter_parts = []
        if chunk_type:
            filter_parts.append(f"chunk_type = '{chunk_type}'")
        if base_class:
            filter_parts.append(f"base_class = '{base_class}'")
        if unit_name:
            filter_parts.append(f"chunk_text LIKE '%{unit_name}%'")
        if file_path:
            filter_parts.append(f"file_path = '{file_path}'")
        filter_expr = " AND ".join(filter_parts) if filter_parts else None

        t0 = time.perf_counter()

        from zvec import Query, Fts

        # 单字段 FTS 搜索（chunk_text 已含 entity_name 前缀）
        results = col.query(
            Query(field_name="chunk_text", fts=Fts(match_string=query)),
            topk=top_k * 2,
            filter=filter_expr,
            output_fields=output_fields,
        )

        elapsed = (time.perf_counter() - t0) * 1000

        return {
            "results": [
                {
                    "id": r.id,
                    "score": r.score,
                    "fields": dict(r.fields) if r.fields else {},
                }
                for r in results[:top_k]
            ],
            "total": min(len(results), top_k),
            "time_ms": round(elapsed, 1),
        }

    def _get_collection(self):
        """获取已打开的 collection（无参数版本）"""
        if self._collection is None:
            if os.path.exists(self._db_path):
                import zvec
                self._collection = zvec.open(self._db_path)
        return self._collection

    # ════════════════════════════════════════
    # 管理
    # ════════════════════════════════════════

    def get_statistics(self) -> Dict:
        """获取知识库统计"""
        import zvec

        col = self._get_collection()
        if col is None:
            return {"status": "not_built"}

        return {
            "status": "ok",
            "doc_count": col.stats.doc_count,
            "dir": str(self.kb_dir),
            "has_indexes": True,
        }

    def close(self):
        """关闭知识库"""
        if self._collection:
            try:
                self._collection.close()
            except Exception:
                pass
            self._collection = None

    def __del__(self):
        self.close()
