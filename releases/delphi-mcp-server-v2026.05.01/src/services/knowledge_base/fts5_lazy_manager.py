#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FTS5 懒加载管理器
支持按需增量构建全文索引，避免构建时生成索引数据
"""

import sqlite3
import threading
import time
import logging
from typing import Optional, List, Dict, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class FTS5LazyManager:
    """
    FTS5 懒加载管理器
    
    使用策略：
    1. 构建时：创建 FTS5 虚拟表（空）
    2. 搜索时：检查覆盖率，决定使用 FTS5 还是降级搜索
    3. 后台构建：降级搜索时触发异步增量构建
    
    示例：
        manager = FTS5LazyManager(
            db_path='data/knowledge.sqlite',
            main_table='documents',
            fts_table='documents_fts',
            columns=['title', 'content']
        )
        
        results = manager.search(
            query='CREATE TABLE',
            search_func=lambda q: fallback_search(q)  # 降级搜索函数
        )
    """
    
    def __init__(
        self,
        db_path: str,
        main_table: str,
        fts_table: str,
        columns: List[str],
        coverage_threshold: float = 0.5,
        tokenize: str = 'porter unicode61'
    ):
        """
        初始化 FTS5 懒加载管理器
        
        Args:
            db_path: 数据库路径
            main_table: 主表名（如 'documents'）
            fts_table: FTS5 虚拟表名（如 'documents_fts'）
            columns: 要索引的列名列表（如 ['title', 'content']）
            coverage_threshold: 覆盖率阈值（默认 0.5，即 50%）
            tokenize: 分词器配置（默认 'porter unicode61'）
        """
        self.db_path = db_path
        self.main_table = main_table
        self.fts_table = fts_table
        self.columns = columns
        self.coverage_threshold = coverage_threshold
        self.tokenize = tokenize
        
        self._building = False
        self._build_lock = threading.Lock()
        self._last_build_time = 0
        
    def create_fts_table(self, conn: sqlite3.Connection):
        """
        创建 FTS5 虚拟表（如果不存在）
        
        Args:
            conn: 数据库连接
        """
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (self.fts_table,)
        )
        if cursor.fetchone():
            return
        
        # 创建 FTS5 虚拟表
        columns_def = ', '.join(self.columns)
        sql = f"""
            CREATE VIRTUAL TABLE {self.fts_table} USING fts5(
                {columns_def},
                tokenize='{self.tokenize}'
            )
        """
        cursor.execute(sql)
        conn.commit()
        logger.info(f"创建 FTS5 表: {self.fts_table}")
    
    def get_coverage(self) -> float:
        """
        获取 FTS5 索引覆盖率
        
        Returns:
            覆盖率（0.0 - 1.0）
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 获取 FTS5 文档数
            cursor.execute(f"SELECT COUNT(*) FROM {self.fts_table}")
            fts_count = cursor.fetchone()[0]
            
            # 获取主表文档数
            cursor.execute(f"SELECT COUNT(*) FROM {self.main_table}")
            total_count = cursor.fetchone()[0]
            
            conn.close()
            
            return fts_count / total_count if total_count > 0 else 0.0
        except Exception as e:
            logger.error(f"获取覆盖率失败: {e}")
            return 0.0
    
    def search(
        self,
        query: str,
        search_func: Optional[Callable[[str], List[Dict]]] = None,
        top_k: int = 10,
        use_bM25: bool = True
    ) -> List[Dict]:
        """
        搜索文档（自动选择 FTS5 或降级搜索）
        
        Args:
            query: 搜索查询
            search_func: 降级搜索函数（当 FTS5 未就绪时使用）
            top_k: 返回结果数
            use_bM25: 是否使用 BM25 排序（默认 True）
        
        Returns:
            搜索结果列表
        """
        coverage = self.get_coverage()
        
        # 决策：使用 FTS5 还是降级搜索
        if coverage >= self.coverage_threshold:
            # FTS5 搜索
            logger.debug(f"FTS5 搜索 (覆盖率: {coverage:.1%})")
            return self._fts_search(query, top_k, use_bM25)
        else:
            # 降级搜索
            logger.debug(f"降级搜索 (覆盖率: {coverage:.1%})")
            
            if search_func is None:
                # 默认降级搜索（LIKE）
                results = self._fallback_search(query, top_k)
            else:
                results = search_func(query)
            
            # 触发后台构建
            self.trigger_background_build()
            
            return results
    
    def _fts_search(self, query: str, top_k: int, use_bM25: bool) -> List[Dict]:
        """
        FTS5 MATCH 搜索
        
        Args:
            query: 搜索查询
            top_k: 返回结果数
            use_bM25: 是否使用 BM25 排序
        
        Returns:
            搜索结果列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            safe_query = self._escape_fts_query(query)
            
            if use_bM25:
                sql = f"""
                    SELECT m.*, bm25({self.fts_table}) as score
                    FROM {self.fts_table} f
                    JOIN {self.main_table} m ON f.rowid = m.id
                    WHERE {self.fts_table} MATCH ?
                    ORDER BY bm25({self.fts_table})
                    LIMIT ?
                """
            else:
                sql = f"""
                    SELECT m.*
                    FROM {self.fts_table} f
                    JOIN {self.main_table} m ON f.rowid = m.id
                    WHERE {self.fts_table} MATCH ?
                    LIMIT ?
                """
            
            cursor.execute(sql, (safe_query, top_k))
            results = [dict(row) for row in cursor.fetchall()]
            
            conn.close()
            return results
        except Exception as e:
            logger.error(f"FTS5 搜索失败: {e}")
            return []
    
    def _fallback_search(self, query: str, top_k: int) -> List[Dict]:
        """
        降级搜索（LIKE 全表扫描）
        
        Args:
            query: 搜索查询
            top_k: 返回结果数
        
        Returns:
            搜索结果列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 构建 LIKE 条件
            conditions = [f"{col} LIKE ?" for col in self.columns]
            where_clause = " OR ".join(conditions)
            params = [f'%{query}%' for _ in self.columns]
            
            sql = f"""
                SELECT *
                FROM {self.main_table}
                WHERE {where_clause}
                LIMIT ?
            """
            params.append(top_k)
            
            cursor.execute(sql, params)
            results = [dict(row) for row in cursor.fetchall()]
            
            conn.close()
            return results
        except Exception as e:
            logger.error(f"降级搜索失败: {e}")
            return []
    
    def _escape_fts_query(self, query: str) -> str:
        """
        转义 FTS5 查询特殊字符
        
        Args:
            query: 原始查询
        
        Returns:
            转义后的查询
        """
        # FTS5 特殊字符：* " ' ( ) [ ]
        # 简单处理：用双引号包裹
        # 如果查询包含空格，拆分为多个词
        words = query.split()
        escaped = ['"' + w.replace('"', '""') + '"' for w in words]
        return ' OR '.join(escaped)
    
    def trigger_background_build(self):
        """
        触发后台增量构建
        """
        with self._build_lock:
            if self._building:
                logger.debug("后台构建已在进行中")
                return
            
            # 避免频繁构建（至少间隔 5 秒）
            now = time.time()
            if now - self._last_build_time < 5:
                logger.debug("构建间隔过短，跳过")
                return
            
            self._building = True
            self._last_build_time = now
        
        # 启动后台线程
        thread = threading.Thread(target=self._background_build_worker, daemon=True)
        thread.start()
        logger.info("触发后台 FTS5 构建")
    
    def _background_build_worker(self):
        """
        后台构建工作线程
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 检查未索引的文档数
            cursor.execute(f"""
                SELECT COUNT(*) FROM {self.main_table}
                WHERE id NOT IN (SELECT rowid FROM {self.fts_table})
            """)
            unindexed_count = cursor.fetchone()[0]
            
            if unindexed_count == 0:
                logger.debug("所有文档已索引，跳过构建")
                conn.close()
                return
            
            logger.info(f"后台构建: 索引 {unindexed_count} 个文档...")
            
            # 批量索引未索引的文档
            columns_list = ', '.join(self.columns)
            cursor.execute(f"""
                INSERT INTO {self.fts_table}(rowid, {columns_list})
                SELECT id, {columns_list}
                FROM {self.main_table}
                WHERE id NOT IN (SELECT rowid FROM {self.fts_table})
            """)
            conn.commit()
            
            # 获取最终覆盖率
            cursor.execute(f"SELECT COUNT(*) FROM {self.fts_table}")
            fts_count = cursor.fetchone()[0]
            
            cursor.execute(f"SELECT COUNT(*) FROM {self.main_table}")
            total_count = cursor.fetchone()[0]
            
            coverage = fts_count / total_count if total_count > 0 else 0.0
            
            logger.info(f"后台构建完成: {fts_count}/{total_count} 个文档已索引 (覆盖率: {coverage:.1%})")
            
            conn.close()
        except Exception as e:
            logger.error(f"后台构建失败: {e}")
        finally:
            with self._build_lock:
                self._building = False
    
    def rebuild_full(self):
        """
        全量重建 FTS5 索引（同步）
        """
        logger.info(f"全量重建 FTS5 索引: {self.fts_table}")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 清空 FTS5 表
        cursor.execute(f"DELETE FROM {self.fts_table}")
        
        # 重新索引所有文档
        columns_list = ', '.join(self.columns)
        cursor.execute(f"""
            INSERT INTO {self.fts_table}(rowid, {columns_list})
            SELECT id, {columns_list}
            FROM {self.main_table}
        """)
        conn.commit()
        
        # 获取统计
        cursor.execute(f"SELECT COUNT(*) FROM {self.fts_table}")
        count = cursor.fetchone()[0]
        
        conn.close()
        logger.info(f"全量重建完成: {count} 个文档已索引")
    
    def get_statistics(self) -> Dict:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT COUNT(*) FROM {self.main_table}")
            total_count = cursor.fetchone()[0]
            
            cursor.execute(f"SELECT COUNT(*) FROM {self.fts_table}")
            fts_count = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'main_table': self.main_table,
                'fts_table': self.fts_table,
                'total_documents': total_count,
                'indexed_documents': fts_count,
                'coverage': fts_count / total_count if total_count > 0 else 0.0,
                'is_building': self._building
            }
        except Exception as e:
            logger.error(f"获取统计失败: {e}")
            return {}
