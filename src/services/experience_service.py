"""
经验记忆服务层 — 保存/搜索/管理 AI 成功解决问题的经验

复用 embedding_service 做语义搜索，SQLite 存储，线程安全连接。
"""

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.constants import SQLITE_BUSY_TIMEOUT_MS

logger = logging.getLogger(__name__)

# numpy 可选依赖
np: Any = None
try:
    import numpy
    np = numpy
except ImportError:
    pass

# embedding 服务（可选，不可用时降级为关键词搜索）
try:
    from .knowledge_base.embedding_service import (
        encode_single,
        cosine_similarity,
        blob_to_vector,
        is_available as _embedding_available,
        is_model_loaded as _embedding_model_loaded,
    )
except ImportError:
    encode_single = None
    cosine_similarity = None
    blob_to_vector = None
    _embedding_available = lambda: False
    _embedding_model_loaded = lambda: False


def _embedding_ok() -> bool:
    """检查 embedding 是否可用（模型已加载且依赖齐全）

    与知识库保持一致：仅在模型已加载后才走 embedding 路径，
    避免 save/search 触发懒加载导致超时。
    """
    try:
        # 必须模型已加载（不触发懒加载）
        if not (_embedding_model_loaded and callable(_embedding_model_loaded)
                and _embedding_model_loaded()):
            return False
        # 依赖库可 import
        if _embedding_available and callable(_embedding_available):
            return _embedding_available()
    except Exception as e:
        logger.debug("embedding 可用性检查失败（视为不可用）: %s", e)
    return False


def _now() -> str:
    """返回 ISO 格式时间戳"""
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    """返回短 UUID"""
    return uuid.uuid4().hex[:12]


_STORE_FILENAME = "experiences.sqlite"


class ExperienceMemoryService:
    """经验记忆服务。

    提供经验的 CRUD 和语义搜索。线程安全。embedding 降级友好的设计。

    Args:
        kb_dir: 存储目录，默认为 data/experience-knowledge-base/
    """

    def __init__(self, kb_dir: Optional[str] = None):
        if kb_dir is None:
            # 默认存到 data/ 下
            kb_dir = str(Path(__file__).parent.parent.parent / "data" / "experience-knowledge-base")
        self._kb_dir = Path(kb_dir)
        self._kb_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = str(self._kb_dir / _STORE_FILENAME)
        self._local = threading.local()
        self._init_db()

    # ── 连接管理 ──

    def _get_conn(self):
        """获取当前线程的数据库连接"""
        import sqlite3
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
            # 确保表存在
            self._init_tables(conn)
        else:
            try:
                self._local.conn.execute("SELECT 1")
            except Exception:
                conn = sqlite3.connect(self._db_path)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
                conn.row_factory = sqlite3.Row
                self._local.conn = conn
                self._init_tables(conn)
        return self._local.conn

    def _init_db(self):
        """初始化数据库（首次创建表）"""
        import sqlite3
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            self._init_tables(conn)
            conn.close()
        except Exception as e:
            logger.error("初始化经验库失败: %s", e)

    def _init_tables(self, conn):
        """创建表（幂等）"""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS experiences (
                id          TEXT PRIMARY KEY,
                problem     TEXT NOT NULL,
                solution    TEXT NOT NULL,
                tools_used  TEXT DEFAULT '[]',
                context     TEXT DEFAULT '{}',
                tags        TEXT DEFAULT '[]',
                embedding   BLOB,
                hit_count   INTEGER DEFAULT 1,
                score       REAL DEFAULT 1.0,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_exp_created
            ON experiences(created_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_exp_updated
            ON experiences(updated_at)
        """)
        conn.commit()

    def close(self):
        """关闭当前线程的连接"""
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            try:
                self._local.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception as e:
                logger.debug("WAL checkpoint 失败（连接将正常关闭）: %s", e)
            try:
                self._local.conn.close()
            except Exception as e:
                logger.debug("关闭 sqlite 连接失败: %s", e)
            self._local.conn = None

    # ── 内部 helpers ──

    def _row_to_dict(self, row) -> dict:
        """sqlite3.Row → dict（解析 JSON 字段）"""
        d = dict(row)
        for field in ("tools_used", "context", "tags"):
            if isinstance(d.get(field), str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        # embedding 不返回
        d.pop("embedding", None)
        return d

    def _maybe_encode(self, text: str, prefix: str = "passage"):
        """尝试编码文本为 embedding BLOB"""
        if not _embedding_ok() or encode_single is None or np is None:
            return None
        try:
            vec = encode_single(text, prefix=prefix)
            if vec is not None:
                return np.array(vec, dtype=np.float32).tobytes()
        except Exception as e:
            logger.warning("编码 embedding 失败: %s", e)
        return None

    # ── 核心操作 ──

    def save(
        self,
        problem: str,
        solution: str,
        tools_used: Optional[list] = None,
        context: Optional[dict] = None,
        tags: Optional[list] = None,
    ) -> dict:
        """保存经验（自动去重合并：embedding 相似度 >0.85 则更新旧记录而非新增）。

        Args:
            problem: 问题描述
            solution: 解决步骤
            tools_used: 用到的工具名列表
            context: 上下文信息（项目路径、文件等）
            tags: 标签列表

        Returns:
            创建/更新的经验记录 dict，附带 _merged 标记
        """
        now = _now()

        # ── 去重：搜索语义相似的已有经验 ──
        merged = self._search_embedding(problem, top_k=1, tags=None)
        if merged:
            best = merged[0]
            sim = best.get("similarity", 0)
            if sim > 0.85:
                # 合并不创建新记录
                best_id = best["id"]
                merged_solution = best["solution"] + "\n" + solution
                merged_tags = list(set(best.get("tags", []) + (tags or [])))
                merged_tools = list(set(best.get("tools_used", []) + (tools_used or [])))

                conn = self._get_conn()
                conn.execute(
                    """UPDATE experiences SET solution = ?, tags = ?, tools_used = ?,
                       updated_at = ?, score = MIN(1.0, score + 0.05),
                       embedding = COALESCE(?, embedding)
                       WHERE id = ?""",
                    (
                        merged_solution,
                        json.dumps(merged_tags, ensure_ascii=False),
                        json.dumps(merged_tools, ensure_ascii=False),
                        now,
                        self._maybe_encode(problem, prefix="passage"),
                        best_id,
                    ),
                )
                conn.commit()
                result = best.copy()
                result.update({
                    "solution": merged_solution,
                    "tags": merged_tags,
                    "tools_used": merged_tools,
                    "updated_at": now,
                    "_merged": True,
                    "_merged_from": best_id,
                })
                logger.info("经验已合并到 %s — %s", best_id, problem[:80])
                return result

        # ── 无相似记录，新建 ──
        exp_id = _uuid()
        embedding_blob = self._maybe_encode(problem, prefix="passage")

        conn = self._get_conn()
        conn.execute(
            """INSERT INTO experiences
               (id, problem, solution, tools_used, context, tags,
                embedding, hit_count, score, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1.0, ?, ?)""",
            (
                exp_id,
                problem,
                solution,
                json.dumps(tools_used or [], ensure_ascii=False),
                json.dumps(context or {}, ensure_ascii=False),
                json.dumps(tags or [], ensure_ascii=False),
                embedding_blob,
                now,
                now,
            ),
        )
        conn.commit()

        result = {
            "id": exp_id,
            "problem": problem,
            "solution": solution,
            "tools_used": tools_used or [],
            "context": context or {},
            "tags": tags or [],
            "hit_count": 1,
            "score": 1.0,
            "created_at": now,
            "updated_at": now,
            "_merged": False,
        }
        logger.info("经验已保存: %s — %s", exp_id, problem[:80])
        return result

    def search(self, query: str, top_k: int = 5, tags: Optional[list] = None) -> list:
        """语义搜索经验。

        优先使用 embedding 做真语义搜索，不可用时降级到 LIKE 关键词匹配。
        如果 embedding 模型已加载但搜不到结果（可能是旧记录缺少向量），
        自动触发 rebuild_embeddings() 补全后重试。

        Args:
            query: 搜索关键词
            top_k: 返回条数
            tags: 按标签过滤（结果必须命中所有指定标签）

        Returns:
            [{id, problem, solution, tools_used, tags, similarity, ...}, ...]
        """
        # 尝试 embedding 语义搜索
        emb_results = self._search_embedding(query, top_k, tags)
        if emb_results:
            return emb_results

        # embedding 可用但无结果 → 可能是旧记录缺少向量，自动重建后重试
        if _embedding_ok():
            rebuilt = self.rebuild_embeddings()
            if rebuilt.get("rebuilt", 0) > 0:
                logger.info("自动重建了 %d 条缺失向量，重试语义搜索", rebuilt["rebuilt"])
                emb_results = self._search_embedding(query, top_k, tags)
                if emb_results:
                    return emb_results

        # 降级：关键词 LIKE 搜索
        return self._search_keyword(query, top_k, tags)

    def _search_embedding(self, query: str, top_k: int, tags: Optional[list]) -> list:
        """基于 embedding 的语义搜索"""
        if not _embedding_ok() or encode_single is None or cosine_similarity is None:
            return []

        query_emb = encode_single(query, prefix="query")
        if query_emb is None:
            return []

        conn = self._get_conn()
        cursor = conn.cursor()
        # 限制扫描行数，避免全表扫描随数据增长越来越慢
        scan_limit = max(top_k * 10, 200)
        cursor.execute(
            "SELECT id, problem, solution, tools_used, context, tags, "
            "hit_count, score, created_at, updated_at, embedding "
            "FROM experiences WHERE embedding IS NOT NULL "
            "ORDER BY updated_at DESC LIMIT ?",
            (scan_limit,)
        )
        rows = cursor.fetchall()
        if not rows:
            return []

        # 收集向量和行
        vecs = []
        valid_rows = []
        for row in rows:
            vec = blob_to_vector(row["embedding"])
            if vec is not None:
                vecs.append(vec)
                valid_rows.append(row)

        if not vecs:
            return []

        # 计算余弦相似度
        _np_local = np
        embs = _np_local.array(vecs, dtype=_np_local.float32)
        sims = cosine_similarity(query_emb, embs)
        if sims is None:
            return []

        # 排序
        scored = []
        for row, sim in zip(valid_rows, sims):
            entry = self._row_to_dict(row)
            entry["similarity"] = round(float(sim), 4)
            # 标签过滤
            if tags:
                row_tags = entry.get("tags", [])
                if not isinstance(row_tags, list):
                    row_tags = []
                if not all(t in row_tags for t in tags):
                    continue
            scored.append(entry)

        scored.sort(key=lambda x: -x["similarity"])
        return scored[:top_k]

    def _search_keyword(self, query: str, top_k: int, tags: Optional[list]) -> list:
        """关键词 LIKE 降级搜索"""
        conn = self._get_conn()
        cursor = conn.cursor()

        like = f"%{query}%"
        cursor.execute(
            "SELECT id, problem, solution, tools_used, context, tags, "
            "hit_count, score, created_at, updated_at "
            "FROM experiences WHERE problem LIKE ? OR solution LIKE ? "
            "ORDER BY updated_at DESC LIMIT ?",
            (like, like, top_k * 2),
        )
        results = []
        for row in cursor.fetchall():
            entry = self._row_to_dict(row)
            if tags:
                row_tags = entry.get("tags", [])
                if not isinstance(row_tags, list):
                    row_tags = []
                if not all(t in row_tags for t in tags):
                    continue
            results.append(entry)
            if len(results) >= top_k:
                break

        # 关键词搜索不给 similarity 分数
        for r in results:
            r["similarity"] = 0.0
        return results

    def get(self, exp_id: str) -> Optional[dict]:
        """获取经验详情，递增 hit_count。

        Args:
            exp_id: 经验 ID

        Returns:
            经验 dict 或 None
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, problem, solution, tools_used, context, tags, "
            "hit_count, score, created_at, updated_at "
            "FROM experiences WHERE id = ?",
            (exp_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        # 递增 hit_count
        conn.execute(
            "UPDATE experiences SET hit_count = hit_count + 1 WHERE id = ?",
            (exp_id,),
        )
        conn.commit()

        return self._row_to_dict(row)

    def list(
        self,
        tags: Optional[list] = None,
        sort_by: str = "updated_at",
        limit: int = 20,
    ) -> list:
        """浏览经验列表。

        Args:
            tags: 按标签过滤
            sort_by: 排序字段，默认 updated_at，可选 created_at / hit_count / score
            limit: 返回条数

        Returns:
            [{id, problem, solution, ...}, ...]
        """
        allowed_sort = {"updated_at", "created_at", "hit_count", "score"}
        if sort_by not in allowed_sort:
            sort_by = "updated_at"

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, problem, solution, tools_used, context, tags, "
            f"hit_count, score, created_at, updated_at "
            f"FROM experiences ORDER BY {sort_by} DESC LIMIT ?",
            (limit * 2,),
        )

        results = []
        for row in cursor.fetchall():
            entry = self._row_to_dict(row)
            if tags:
                row_tags = entry.get("tags", [])
                if not isinstance(row_tags, list):
                    row_tags = []
                if not all(t in row_tags for t in tags):
                    continue
            results.append(entry)
            if len(results) >= limit:
                break

        return results

    def update(
        self,
        exp_id: str,
        solution: Optional[str] = None,
        tags: Optional[list] = None,
        problem: Optional[str] = None,
    ) -> Optional[dict]:
        """更新经验。

        Args:
            exp_id: 经验 ID
            solution: 新的解决步骤（可选）
            tags: 新的标签列表（可选）
            problem: 新的问题描述（可选，会重新生成 embedding）

        Returns:
            更新后的经验 dict，不存在返回 None
        """
        existing = self.get(exp_id)
        if existing is None:
            return None

        now = _now()
        updates = []
        params = []

        if problem is not None:
            updates.append("problem = ?")
            params.append(problem)
            # 重新生成 embedding
            blob = self._maybe_encode(problem, prefix="passage")
            updates.append("embedding = ?")
            params.append(blob)

        if solution is not None:
            updates.append("solution = ?")
            params.append(solution)

        if tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(tags, ensure_ascii=False))

        updates.append("updated_at = ?")
        params.append(now)
        params.append(exp_id)

        conn = self._get_conn()
        conn.execute(
            f"UPDATE experiences SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()

        # 重新读取
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, problem, solution, tools_used, context, tags, "
            "hit_count, score, created_at, updated_at "
            "FROM experiences WHERE id = ?",
            (exp_id,),
        )
        row = cursor.fetchone()
        return self._row_to_dict(row) if row else None

    def merge(self, ids: list, keep: Optional[str] = None) -> Optional[dict]:
        """合并多条经验为一条，删除其余。

        Args:
            ids: 待合并的经验 ID 列表
            keep: 保留的 ID（其余删除），None 则创建新条目

        Returns:
            合并后的经验 dict，失败返回 None
        """
        records = []
        for eid in ids:
            r = self.get(eid)
            if r:
                records.append(r)

        if len(records) < 2:
            logger.warning("merge 需要至少 2 条有效记录")
            return None

        # 合并字段
        problems = "\n".join(r["problem"] for r in records)
        solutions = "\n".join(r["solution"] for r in records)
        all_tags = list(set(t for r in records for t in r.get("tags", [])))
        all_tools = list(set(t for r in records for t in r.get("tools_used", [])))
        hit_total = sum(r.get("hit_count", 1) for r in records)
        now = _now()

        if keep and keep in [r["id"] for r in records]:
            # 更新到 keep 的记录
            target_id = keep
            conn = self._get_conn()
            conn.execute(
                """UPDATE experiences SET problem = ?, solution = ?, tags = ?,
                   tools_used = ?, hit_count = ?, score = 1.0,
                   embedding = COALESCE(?, embedding), updated_at = ?
                   WHERE id = ?""",
                (
                    problems,
                    solutions,
                    json.dumps(all_tags, ensure_ascii=False),
                    json.dumps(all_tools, ensure_ascii=False),
                    hit_total,
                    self._maybe_encode(problems, prefix="passage"),
                    now,
                    target_id,
                ),
            )
            conn.commit()
        else:
            # 创建新条目
            target_id = _uuid()
            conn = self._get_conn()
            conn.execute(
                """INSERT INTO experiences
                   (id, problem, solution, tags, tools_used,
                    hit_count, score, embedding, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?)""",
                (
                    target_id,
                    problems,
                    solutions,
                    json.dumps(all_tags, ensure_ascii=False),
                    json.dumps(all_tools, ensure_ascii=False),
                    hit_total,
                    self._maybe_encode(problems, prefix="passage"),
                    now,
                    now,
                ),
            )
            conn.commit()

        # 删除其他记录
        delete_ids = [r["id"] for r in records if r["id"] != target_id]
        for did in delete_ids:
            self.delete(did)

        # 重新读取
        return self.get(target_id)

    def _compute_experience_value(self, row) -> float:
        """计算经验价值分数（用于 prune 排序）

        考虑因素：
        - hit_count: 复用次数越多越有价值
        - score: 分数越高越有价值
        - recency: 越新越有价值（30 天内无使用则衰减）
        """
        hit = row.get("hit_count", 1)
        score = row.get("score", 1.0)
        recency = row.get("updated_at", "")
        value = hit * score
        # 时间衰减：超过 30 天未更新，价值减半
        if recency:
            try:
                updated = datetime.fromisoformat(recency)
                days_since = (datetime.now(timezone.utc) - updated).days
                if days_since > 30:
                    value *= 0.5 ** (days_since / 30)
            except Exception as e:
                logger.debug("时间衰减计算失败（保留原始 score）: %s", e)
        return round(value, 4)

    def prune_list(self, limit: int = 20) -> list:
        """列出低价值经验，按价值分升序排列。

        Args:
            limit: 返回条数

        Returns:
            [{id, problem, tags, hit_count, value, ...}, ...]
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, problem, tags, hit_count, score, created_at, updated_at "
            "FROM experiences"
        )
        rows = cursor.fetchall()
        scored = []
        for row in rows:
            d = self._row_to_dict(row)
            d["value"] = self._compute_experience_value(d)
            scored.append(d)
        scored.sort(key=lambda x: x["value"])
        return scored[:limit]

    def delete(self, exp_id: str) -> bool:
        """删除经验。

        Args:
            exp_id: 经验 ID

        Returns:
            是否成功删除
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM experiences WHERE id = ?", (exp_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("经验已删除: %s", exp_id)
        return deleted

    def rebuild_embeddings(self) -> dict:
        """重建所有缺少 embedding 的经验记录的向量。

        在模型已加载后调用，为之前因模型未加载而保存的无向量记录补生成 embedding。
        已有 embedding 的记录不受影响。

        Returns:
            {total: 总记录数, rebuilt: 重建数, skipped: 已有向量数, failed: 失败数}
        """
        if not _embedding_ok() or encode_single is None or np is None:
            return {
                "total": 0,
                "rebuilt": 0,
                "skipped": 0,
                "failed": 0,
                "error": "embedding 模型未加载，请先调用 delphi_kb(action=build_embedding) 加载模型",
            }

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, problem FROM experiences WHERE embedding IS NULL"
        )
        rows = cursor.fetchall()

        total = len(rows)
        rebuilt = 0
        failed = 0

        # 也扫描已有 embedding 的记录数
        cursor.execute("SELECT COUNT(*) as cnt FROM experiences WHERE embedding IS NOT NULL")
        skipped = cursor.fetchone()["cnt"]

        for row in rows:
            exp_id = row["id"]
            problem = row["problem"]
            try:
                blob = self._maybe_encode(problem, prefix="passage")
                if blob is not None:
                    conn.execute(
                        "UPDATE experiences SET embedding = ? WHERE id = ?",
                        (blob, exp_id),
                    )
                    rebuilt += 1
                else:
                    failed += 1
            except Exception as e:
                logger.warning("重建 embedding 失败 (id=%s): %s", exp_id, e)
                failed += 1

        if rebuilt > 0:
            conn.commit()

        logger.info("经验 embedding 重建完成: rebuilt=%d, skipped=%d, failed=%d", rebuilt, skipped, failed)
        return {
            "total": total + skipped,
            "rebuilt": rebuilt,
            "skipped": skipped,
            "failed": failed,
        }


# 全局单例
_instance: Optional[ExperienceMemoryService] = None
_instance_lock = threading.Lock()


def get_experience_service(kb_dir: Optional[str] = None) -> ExperienceMemoryService:
    """获取全局 ExperienceMemoryService 实例（单例）"""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ExperienceMemoryService(kb_dir=kb_dir)
    return _instance


def cleanup():
    """清理资源（服务关闭时调用）"""
    global _instance
    if _instance is not None:
        _instance.close()
        _instance = None
