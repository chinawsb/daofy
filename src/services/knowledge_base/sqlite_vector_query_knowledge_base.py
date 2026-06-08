#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Delphi 知识库查询接口 (SQLite + 内置向量扩展)
使用纯 Python 实现的向量搜索功能,无需外部依赖
"""

import json
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import threading

logger = logging.getLogger(__name__)


class SQLiteVectorKnowledgeBase:
    def __init__(self, kb_dir: str, rebuild: bool = False, db_file: Optional[str] = None):
        self.kb_dir = Path(kb_dir)
        self.index_dir = self.kb_dir / "index"
        # 支持从config指定数据库文件
        if db_file:
            self.db_file = self.kb_dir / db_file
        else:
            self.db_file = self.kb_dir / "knowledge_base.sqlite"
        # 用于构建时读取源数据
        self.source_index_file = self.index_dir / "source_index.json"
        self.source_dir = None

        # 使用线程局部存储，每个线程独立的数据库连接
        self._thread_local = threading.local()
        self._db_path = str(self.db_file)

        # 向量词汇表
        self.vocabulary = {}  # word -> id
        self.idf_weights = {}  # word -> idf weight

        # 加载索引
        self.load_index(rebuild)

    def _get_connection(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接（自动检测关闭的连接并重建）"""
        if not hasattr(self._thread_local, 'conn') or self._thread_local.conn is None:
            self._thread_local.conn = self._create_connection()
            return self._thread_local.conn
        
        try:
            # 健康检查：连接是否仍然有效
            self._thread_local.conn.execute("SELECT 1")
            return self._thread_local.conn
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            # 连接已关闭，重建
            self._thread_local.conn = self._create_connection()
            return self._thread_local.conn

    def _create_connection(self) -> sqlite3.Connection:
        """创建新的数据库连接"""
        from .schema import get_connection
        conn = get_connection(self._db_path, use_wal=True)
        conn.row_factory = sqlite3.Row
        # 额外设置（线程安全 + 大 mmap 用于只读查询）
        conn.execute("PRAGMA mmap_size=268435456")
        return conn

    def _close_connection(self):
        """关闭当前线程的数据库连接（关闭前执行 WAL checkpoint 避免 -wal/-shm 残留）"""
        if hasattr(self._thread_local, 'conn') and self._thread_local.conn is not None:
            try:
                self._thread_local.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception as e:
                logger.debug("忽略非致命异常: %s", str(e))
            try:
                self._thread_local.conn.close()
            except Exception as e:
                logger.debug("忽略非致命异常: %s", str(e))
            self._thread_local.conn = None

    def load_index(self, rebuild: bool = False):
        """加载知识库索引"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 检查 metadata 表是否存在（新 schema 始终有 metadata 表）
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'")
            if not cursor.fetchone():
                # 空数据库：自动初始化 schema，确保搜索方法不会因表不存在而崩溃
                from .schema import create_source_tables
                create_source_tables(cursor)
                conn.commit()
                logger.info("知识库已自动初始化（空库，尚未构建数据）")
            else:
                # 从 metadata 表读取（key-value 格式）
                cursor.execute("SELECT value FROM metadata WHERE key = 'total_files'")
                row = cursor.fetchone()
                if row:
                    logger.info(f"知识库加载成功! 包含 {row[0]} 个文件")
                else:
                    logger.info("知识库加载成功!")

                logger.info("使用缓存的索引")

                # 检查 schema 版本（版本不匹配时重建索引）
                from src.services.knowledge_base import check_schema_version, SCHEMA_VERSION
                if not check_schema_version(cursor, "SQLiteVectorKnowledgeBase"):
                    logger.warning(
                        f"SQLiteVectorKnowledgeBase schema 版本不匹配 "
                        f"(需要 v{SCHEMA_VERSION})，搜索可能不完整"
                    )

                # 迁移: 添加 name_lower_rev 列和索引（如果不存在）
                cursor.execute("PRAGMA table_info(vocabularies)")
                columns = {row[1] for row in cursor.fetchall()}
                if 'name_lower_rev' not in columns:
                    logger.info("迁移: 添加 name_lower_rev 列...")
                    cursor.execute("ALTER TABLE vocabularies ADD COLUMN name_lower_rev TEXT")
                    conn.commit()
                    # 填充反转数据
                    logger.info("迁移: 填充 name_lower_rev 数据...")
                    cursor.execute("SELECT COUNT(*) FROM vocabularies")
                    total = cursor.fetchone()[0]
                    logger.info(f"  共 {total} 行，分批处理...")
                    # 注册反转函数
                    conn.create_function("my_reverse", 1, lambda s: s[::-1] if s else '')
                    cursor.execute("UPDATE vocabularies SET name_lower_rev = my_reverse(name_lower) WHERE name_lower_rev IS NULL")
                    conn.commit()
                    logger.info(f"  填充完成")
                else:
                    # 确保已有列但没有数据的行被填充
                    cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE name_lower_rev IS NULL AND name_lower IS NOT NULL")
                    missing = cursor.fetchone()[0]
                    if missing > 0:
                        logger.info(f"迁移: 补填 {missing} 行 name_lower_rev 数据...")
                        conn.create_function("my_reverse", 1, lambda s: s[::-1] if s else '')
                        cursor.execute("UPDATE vocabularies SET name_lower_rev = my_reverse(name_lower) WHERE name_lower_rev IS NULL AND name_lower IS NOT NULL")
                        conn.commit()
                
                # 确保反转列索引存在
                cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_vocabularies_name_lower_rev'")
                if not cursor.fetchone():
                    logger.info("迁移: 创建 name_lower_rev 索引...")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocabularies_name_lower_rev ON vocabularies(name_lower_rev)")
                    conn.commit()

        except Exception as e:
            logger.error(f"加载知识库失败: {e}")
            self._close_connection()
            raise

    def _semantic_search_embedding(self, query: str, type_filter: tuple, top_k: int = 10) -> List[Tuple[str, float]]:
        """
        使用 embedding 进行真语义搜索
        仅当模型已加载（由 build_embedding/build_vectors 触发）时才启用，不自动加载模型

        Args:
            query: 搜索查询
            type_filter: vocabularies.type 过滤条件，如 ('TC', 'TR')
            top_k: 返回结果数

        Returns:
            [(name, similarity), ...]
        """
        try:
            from .embedding_service import (
                encode_single, cosine_similarity, blob_to_vector, is_model_loaded
            )
        except ImportError:
            return []

        # 只有在模型已加载（之前跑过 build_embedding）时才使用 embedding 搜索
        if not is_model_loaded():
            return []

        query_emb = encode_single(query, prefix="query")
        if query_emb is None:
            return []

        import numpy as np
        conn = self._get_connection()
        cursor = conn.cursor()

        # 分批读取已有向量的 vocabularies
        placeholders = ','.join(['?'] * len(type_filter))
        cursor.execute(f"""
            SELECT id, name, vector FROM vocabularies
            WHERE type IN ({placeholders}) AND vector IS NOT NULL
            ORDER BY id
        """, type_filter)

        batch_size = 5000
        results = []
        batch = []

        for row in cursor.fetchall():
            vid, name, vec_blob = row['id'], row['name'], row['vector']
            vec = blob_to_vector(vec_blob)
            if vec is None:
                continue
            batch.append((vid, name, vec))

            if len(batch) >= batch_size:
                names = [b[1] for b in batch]
                embs = np.array([b[2] for b in batch], dtype=np.float32)
                sims = cosine_similarity(query_emb, embs)
                for n, s in zip(names, sims):
                    results.append((n, float(s)))
                batch = []

        # 处理最后一批
        if batch:
            names = [b[1] for b in batch]
            embs = np.array([b[2] for b in batch], dtype=np.float32)
            sims = cosine_similarity(query_emb, embs)
            for n, s in zip(names, sims):
                results.append((n, float(s)))

        # 去重 + 按相似度排序 + top_k
        seen = set()
        unique = []
        for name, sim in sorted(results, key=lambda x: -x[1]):
            if name not in seen:
                seen.add(name)
                unique.append((name, sim))
            if len(unique) >= top_k:
                break

        return unique

    def semantic_search_classes(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """语义搜索类 —— 优先使用 embedding，不可用时降级到反转索引"""
        # 尝试 embedding
        emb_results = self._semantic_search_embedding(query, ('TC', 'TR', 'TI', 'TE', 'TS', 'TY'), top_k)
        if emb_results:
            return emb_results

        # 降级: 反转索引匹配
        conn = self._get_connection()
        cursor = conn.cursor()

        query_lower = query.lower()
        rev_pattern = query_lower[::-1] + '*'

        cursor.execute("""
            SELECT v.name FROM vocabularies v 
            WHERE v.rowid IN (
                SELECT rowid FROM vocabularies WHERE name_lower_rev GLOB ?
            )
            AND v.type IN ('TC', 'TR', 'TI', 'TE', 'TS', 'TY')
        """, (rev_pattern,))

        results = [(row['name'], 0.8) for row in cursor.fetchall()]

        seen = set()
        unique_results = []
        for name, sim in results:
            if name not in seen:
                seen.add(name)
                unique_results.append((name, sim))

        return unique_results[:top_k]

    def semantic_search_functions(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """语义搜索函数 —— 优先使用 embedding，不可用时降级到反转索引"""
        # 尝试 embedding
        emb_results = self._semantic_search_embedding(query, ('FF', 'FP'), top_k)
        if emb_results:
            return emb_results

        # 降级: 反转索引匹配
        conn = self._get_connection()
        cursor = conn.cursor()

        query_lower = query.lower()
        rev_pattern = query_lower[::-1] + '*'

        cursor.execute("""
            SELECT v.name FROM vocabularies v 
            WHERE v.rowid IN (
                SELECT rowid FROM vocabularies WHERE name_lower_rev GLOB ?
            )
            AND v.type IN ('FF', 'FP')
        """, (rev_pattern,))

        results = [(row['name'], 0.8) for row in cursor.fetchall()]

        seen = set()
        unique_results = []
        for name, sim in results:
            if name not in seen:
                seen.add(name)
                unique_results.append((name, sim))

        return unique_results[:top_k]

    def search_by_name(self, name: str) -> List[Dict]:
        """根据名称搜索符号 (精确匹配+宽泛匹配, 返回所有类型)
        
        搜索策略:
        1. 精确名称匹配: name_lower = ? OR GLOB 前缀通配
        2. 若结果<5条且名称包含 '.'，则尝试按单元名搜索该文件的所有实体
        3. 若结果<3条，则尝试按文件路径匹配（用于"DateUtils"等主题搜索）
        """
        KIND_NAMES = {
            'TC': 'class', 'TR': 'record', 'TI': 'interface', 'TH': 'helper',
            'TE': 'enum', 'TS': 'set', 'TY': 'type', 'AT': 'array',
            'PT': 'pointer', 'MM': 'method', 'MF': 'field',
            'FF': 'function', 'FP': 'procedure', 'CC': 'const', 'CR': 'resourcestring',
            'MP': 'property', 'KS': 'string literal',
        }
        name_lower = name.lower()
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 1. 精确名称 + GLOB 前缀匹配 + DF 属性值匹配
        escaped = name_lower.replace('%', '\\%').replace('_', '\\_')
        cursor.execute("""
            SELECT v.name, v.type, v.base_class, v.description, v.line, 
                   f.relative_path, f.full_path, f.extension, f.size, 
                   f.line_count, f.hash, f.last_modified, f.category 
            FROM vocabularies v 
            INNER JOIN files f ON v.file_id = f.id 
            WHERE v.name_lower = ? OR v.name_lower GLOB ?
               OR (v.type IN ('DF', 'KS') AND v.description IS NOT NULL AND v.description != ''
                   AND v.description LIKE '%' || ? || '%' ESCAPE '\\')
        """, (name_lower, name_lower + '<*', escaped))
        
        results = []
        for row in cursor.fetchall():
            kind_code = row['type']
            kind_name = KIND_NAMES.get(kind_code, kind_code)
            results.append({'name': row['name'], 'kind': kind_name, 'kind_code': kind_code, 
                           'parent': row['base_class'] or '', 'line': row['line'], 
                           'definition': row['description'] or '', 
                           'file': {'path': row['relative_path'], 'full_path': row['full_path'], 
                                    'extension': row['extension'], 'size': row['size'], 
                                    'line_count': row['line_count'], 'hash': row['hash'], 
                                    'last_modified': row['last_modified'], 'category': row['category']}})
        
        # 2. 如果结果少且名称含 '.'，可能是单元名搜索
        if len(results) < 5 and '.' in name:
            try:
                cursor.execute("""
                    SELECT v.name, v.type, v.base_class, v.description, v.line,
                           f.relative_path, f.full_path, f.extension, f.size,
                           f.line_count, f.hash, f.last_modified, f.category
                    FROM vocabularies v
                    INNER JOIN files f ON v.file_id = f.id
                    WHERE f.relative_path LIKE ? OR f.full_path LIKE ?
                """, ('%' + name_lower + '%', '%' + name_lower + '%'))
                added = set()
                for row in cursor.fetchall():
                    key = (row['name'], row['line'], row['full_path'])
                    if key in added:
                        continue
                    added.add(key)
                    kind_code = row['type']
                    kind_name = KIND_NAMES.get(kind_code, kind_code)
                    results.append({'name': row['name'], 'kind': kind_name, 'kind_code': kind_code,
                                   'parent': row['base_class'] or '', 'line': row['line'],
                                   'definition': row['description'] or '',
                                   'file': {'path': row['relative_path'], 'full_path': row['full_path'],
                                            'extension': row['extension'], 'size': row['size'],
                                            'line_count': row['line_count'], 'hash': row['hash'],
                                            'last_modified': row['last_modified'], 'category': row['category']}})
            except Exception as e:
                logger.debug("忽略非致命异常: %s", str(e))
        
        # 3. 如果结果仍然很少，尝试宽泛的文件名匹配（用于"DateUtils"、"Date"等主题搜索）
        if len(results) < 3:
            try:
                cursor.execute("""
                    SELECT v.name, v.type, v.base_class, v.description, v.line,
                           f.relative_path, f.full_path, f.extension, f.size,
                           f.line_count, f.hash, f.last_modified, f.category
                    FROM vocabularies v
                    INNER JOIN files f ON v.file_id = f.id
                    WHERE (f.relative_path LIKE ? OR f.relative_path LIKE ?)
                """, ('%' + name_lower + '.pas%', '%' + name_lower + '%'))
                added = set()
                for row in cursor.fetchall():
                    key = (row['name'], row['line'], row['full_path'])
                    if key in added:
                        continue
                    added.add(key)
                    kind_code = row['type']
                    kind_name = KIND_NAMES.get(kind_code, kind_code)
                    results.append({'name': row['name'], 'kind': kind_name, 'kind_code': kind_code,
                                   'parent': row['base_class'] or '', 'line': row['line'],
                                   'definition': row['description'] or '',
                                   'file': {'path': row['relative_path'], 'full_path': row['full_path'],
                                            'extension': row['extension'], 'size': row['size'],
                                            'line_count': row['line_count'], 'hash': row['hash'],
                                            'last_modified': row['last_modified'], 'category': row['category']}})
            except Exception as e:
                logger.debug("忽略非致命异常: %s", str(e))
        
        return results

    def search_by_unit_name(self, unit_name: str) -> List[Dict]:
        """根据单元名搜索 (精确匹配)
        
        策略1: 优先从 vocabularies.type='UI' 查找（SmartCache 路径）
        策略2: 降级到 files.units_defined 字段查找（项目 KB 路径）
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        name_lower = unit_name.lower()

        # 策略1: vocabularies.type='UI' — 先精确匹配，再后缀匹配（如 "SysUtils" → "System.SysUtils"）
        cursor.execute("""
            SELECT v.name, f.relative_path, f.full_path, f.extension,
                   f.size, f.line_count, f.hash, f.last_modified,
                   f.units_defined, f.units_imported
            FROM vocabularies v
            LEFT JOIN files f ON v.file_id = f.id
            WHERE v.type = 'UI' AND (v.name_lower = ? OR v.name_lower LIKE ?)
        """, (name_lower, f'%.{name_lower}'))

        rows = cursor.fetchall()
        if rows:
            results = []
            for row in rows:
                raw_uses = row['units_imported'] or ''
                try:
                    uses = json.loads(raw_uses) if raw_uses else []
                except (json.JSONDecodeError, TypeError):
                    uses = [u.strip() for u in raw_uses.split(',') if u.strip()]
                results.append({
                    'name': row['name'],
                    'file': {
                        'path': row['relative_path'] or row['full_path'],
                        'full_path': row['full_path'],
                        'extension': row['extension'],
                        'size': row['size'],
                        'line_count': row['line_count'],
                        'hash': row['hash'],
                        'last_modified': row['last_modified'],
                        'units': [row['name']],
                        'uses': uses
                    }
                })
            # 注: 不关闭线程局部连接，由 KB 实例生命周期管理
            return results

        # 策略2: files.units_defined 字段（项目 KB 路径）
        cursor.execute("PRAGMA table_info(files)")
        files_columns = {row[1] for row in cursor.fetchall()}
        path_col = 'relative_path' if 'relative_path' in files_columns else 'path'
        units_col = 'units_defined' if 'units_defined' in files_columns else 'units'
        uses_col = 'units_imported' if 'units_imported' in files_columns else 'uses'

        cursor.execute(f"""
            SELECT {path_col} AS path_col, full_path, extension, size, line_count,
                   hash, last_modified, {units_col} AS units_col, {uses_col} AS uses_col
            FROM files
            WHERE {units_col} LIKE ?
        """, (f'%{name_lower}%',))

        results = []
        for row in cursor.fetchall():
            raw_units = row['units_col'] or ''
            try:
                units = json.loads(raw_units) if raw_units else []
            except (json.JSONDecodeError, TypeError):
                units = [u.strip() for u in raw_units.split(',') if u.strip()]
            if name_lower in [u.lower() for u in units]:
                raw_uses = row['uses_col'] or ''
                try:
                    uses = json.loads(raw_uses) if raw_uses else []
                except (json.JSONDecodeError, TypeError):
                    uses = [u.strip() for u in raw_uses.split(',') if u.strip()]
                results.append({
                    'name': unit_name,
                    'file': {
                        'path': row['path_col'],
                        'full_path': row['full_path'],
                        'extension': row['extension'],
                        'size': row['size'],
                        'line_count': row['line_count'],
                        'hash': row['hash'],
                        'last_modified': row['last_modified'],
                        'units': units,
                        'uses': uses
                    }
                })

        # 注: 不关闭线程局部连接，由 KB 实例生命周期管理
        return results

    def search_usages(self, name: str, namespace_prefixes: Optional[List[str]] = None) -> List[Dict]:
        """
        搜索符号的引用位置 —— 先找定义该符号的单元，再找哪些文件引用了这些单元

        Args:
            name: 符号名或单元名
            namespace_prefixes: 命名空间前缀列表（来自 .dproj 的 DCC_Namespace），
                               用于解析省略前缀的引用。如 ['Vcl','System','Winapi']
                               则 Vcl.Forms 也会匹配简写 Forms

        Returns:
            引用该符号的文件列表
        """
        name_lower = name.lower()
        conn = self._get_connection()
        cursor = conn.cursor()

        # Step 1: 找到包含此符号的单元名
        defining_units = set()

        # 策略1: 通过 vocabularies.type='UI' 定位定义单元（SmartCache 路径）
        cursor.execute("""
            SELECT DISTINCT vu.name
            FROM vocabularies vs
            JOIN vocabularies vu ON vs.file_id = vu.file_id AND vu.type = 'UI'
            WHERE vs.name_lower = ?
        """, (name_lower,))
        for row in cursor.fetchall():
            defining_units.add(row['name'])

        # 策略2: 降级到 files.units_defined（项目 KB 路径）
        if not defining_units:
            cursor.execute("""
                SELECT DISTINCT f.units_defined
                FROM vocabularies v
                INNER JOIN files f ON v.file_id = f.id
                WHERE v.name_lower = ? AND f.units_defined IS NOT NULL AND f.units_defined != ''
            """, (name_lower,))
            for row in cursor.fetchall():
                units = [u.strip() for u in row['units_defined'].split(',') if u.strip()]
                for u in units:
                    if name_lower in u.lower() or u.lower() in name_lower:
                        defining_units.add(u)

        # 如果都没找到，直接用符号名做模糊匹配
        if not defining_units:
            defining_units.add(name)

        # Step 2: 找引用了这些单元的文件
        # 若提供了 namespace_prefixes（来自 .dproj 的 DCC_Namespace），
        # 对含前缀的单元（如 Vcl.Forms）同时搜索简写（Forms）
        # 例如 prefixes=['Vcl','System'] → Vcl.Forms 也匹配 Forms
        results = []
        seen_paths = set()
        for unit_name in defining_units:
            search_terms = [unit_name]

            # 检查是否有已知命名空间前缀可以省略
            if namespace_prefixes and '.' in unit_name:
                prefix = unit_name.split('.')[0]
                short_name = unit_name[len(prefix) + 1:]
                if prefix in namespace_prefixes and short_name:
                    search_terms.append(short_name)

            for term in search_terms:
                cursor.execute("""
                    SELECT DISTINCT f.full_path, f.relative_path, f.extension,
                           f.units_defined, f.units_imported, f.line_count
                    FROM files f
                    WHERE f.units_imported LIKE ?
                    ORDER BY f.full_path
                """, (f'%{term}%',))

            for row in cursor.fetchall():
                fp = row['full_path']
                if fp in seen_paths:
                    continue
                seen_paths.add(fp)

                units_imported = []
                if row['units_imported']:
                    units_imported = [u.strip() for u in row['units_imported'].split(',') if u.strip()]

                results.append({
                    'name': name,
                    'match_reason': f"引用单元 {unit_name}" + (f" / {short_name}" if term == short_name and short_name else ""),
                    'file': {
                        'full_path': row['full_path'],
                        'path': row['relative_path'],
                        'extension': row['extension'],
                        'line_count': row['line_count'],
                    },
                    'imported_by': units_imported[:20],
                })

        return results

    def search_by_keyword(self, keyword: str, search_in: Optional[List[str]] = None) -> List[Dict]:
        """根据关键词搜索 (在实体名称中搜索)"""
        keyword_lower = keyword.lower()
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT v.name, v.type, v.description, v.line, f.relative_path, f.full_path
            FROM vocabularies v
            INNER JOIN files f ON v.file_id = f.id
            WHERE v.name_lower LIKE ?
            LIMIT 100
        """, (f'%{keyword_lower}%',))

        results = []
        for row in cursor.fetchall():
            results.append({
                'name': row['name'],
                'kind': row['type'],
                'definition': row['description'],
                'line': row['line'],
                'file': row['full_path']
            })

        return results

    def search_by_class_name(self, class_name: str) -> List[Dict]:
        """根据类名搜索 (type='TC')"""
        conn = self._get_connection()
        cursor = conn.cursor()
        name_lower = class_name.lower()

        cursor.execute("""
            SELECT v.name, v.type, v.base_class, v.description, v.line,
                   f.relative_path, f.full_path, f.extension, f.size,
                   f.line_count, f.hash, f.last_modified, f.category
            FROM vocabularies v
            INNER JOIN files f ON v.file_id = f.id
            WHERE v.type = 'TC' AND (v.name_lower = ? OR v.name_lower GLOB ?)
            LIMIT 50
        """, (name_lower, name_lower + '<*'))

        results = []
        for row in cursor.fetchall():
            results.append({
                'name': row['name'],
                'kind': 'class',
                'kind_code': 'TC',
                'parent': row['base_class'] or '',
                'line': row['line'],
                'definition': row['description'] or '',
                'file': {
                    'path': row['relative_path'],
                    'full_path': row['full_path'],
                    'extension': row['extension'],
                    'size': row['size'],
                    'line_count': row['line_count'],
                    'hash': row['hash'],
                    'last_modified': row['last_modified'],
                    'category': row['category']
                }
            })

        # 注: 不关闭线程局部连接，由 KB 实例生命周期管理
        return results

    def search_by_function_name(self, function_name: str) -> List[Dict]:
        """根据函数名搜索 (type='FF' 或 'FP')"""
        conn = self._get_connection()
        cursor = conn.cursor()
        name_lower = function_name.lower()

        cursor.execute("""
            SELECT v.name, v.type, v.description, v.line,
                   f.relative_path, f.full_path, f.extension, f.size,
                   f.line_count, f.hash, f.last_modified, f.category
            FROM vocabularies v
            INNER JOIN files f ON v.file_id = f.id
            WHERE v.type IN ('FF', 'FP') AND (v.name_lower = ? OR v.name_lower GLOB ?)
            LIMIT 50
        """, (name_lower, name_lower + '<*'))

        results = []
        for row in cursor.fetchall():
            kind_name = 'function' if row['type'] == 'FF' else 'procedure'
            results.append({
                'name': row['name'],
                'kind': kind_name,
                'kind_code': row['type'],
                'line': row['line'],
                'definition': row['description'] or '',
                'file': {
                    'path': row['relative_path'],
                    'full_path': row['full_path'],
                    'extension': row['extension'],
                    'size': row['size'],
                    'line_count': row['line_count'],
                    'hash': row['hash'],
                    'last_modified': row['last_modified'],
                    'category': row['category']
                }
            })

        # 注: 不关闭线程局部连接，由 KB 实例生命周期管理
        return results

    def count_pending_vectors(self) -> int:
        """统计未构建向量的词条数"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE vector IS NULL OR vector_status='pending'")
            return cursor.fetchone()[0]
        except Exception as e:
            logger.warning("统计待构建向量数失败: %s", e)
            return 0

    def build_vectors(self, progress_callback=None) -> int:
        """
        为所有 pending 状态的 vocabularies 构建 embedding 向量

        Args:
            progress_callback: 进度回调 (percent, message)

        Returns:
            成功构建的数量
        """
        from .embedding_service import is_available, batch_encode_and_store

        if not is_available():
            logger.warning("embedding 依赖未安装，跳过向量构建")
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        # 获取所有 pending 的词条
        cursor.execute("""
            SELECT id, name FROM vocabularies
            WHERE vector IS NULL OR vector_status='pending'
            ORDER BY id
        """)
        all_rows = cursor.fetchall()
        total = len(all_rows)

        if total == 0:
            logger.info("所有词条已有向量，无需构建")
            return 0

        logger.info(f"开始构建 {total} 个词条的 embedding 向量...")

        # 分批处理
        batch_size = 500
        built = 0

        for start in range(0, total, batch_size):
            batch = all_rows[start:start + batch_size]
            count = batch_encode_and_store(cursor, batch, prefix="passage")
            built += count
            conn.commit()

            pct = min(100, (start + len(batch)) / total * 100)
            if progress_callback:
                progress_callback(pct, f"构建向量 [{start+len(batch)}/{total}]")
            if start % 2000 == 0:
                logger.info(f"  向量构建进度: {start+len(batch)}/{total}")

        # 清理标记（vector_status='pending' 但 vector IS NULL 的标记为 failed）
        cursor.execute("""
            UPDATE vocabularies SET vector_status='failed'
            WHERE (vector IS NULL OR vector='') AND vector_status='pending'
        """)
        conn.commit()

        logger.info(f"向量构建完成: {built}/{total}")
        return built

    def close(self):
        """关闭数据库连接"""
        self._close_connection()

    def __del__(self):
        """析构函数,确保数据库连接关闭"""
        self.close()

