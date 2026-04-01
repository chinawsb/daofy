#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Delphi 知识库查询接口 (SQLite + 内置向量扩展)
使用纯 Python 实现的向量搜索功能,无需外部依赖
"""

import json
import sqlite3
import math
import struct
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, Counter
import time
import hashlib
import threading


class SQLiteVectorKnowledgeBase:
    def __init__(self, kb_dir: str, force_rebuild: bool = False):
        self.kb_dir = Path(kb_dir)
        self.index_dir = self.kb_dir / "index"
        self.db_file = self.kb_dir / "knowledge.sqlite"
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
        self.load_index(force_rebuild)

    def _get_connection(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接"""
        if not hasattr(self._thread_local, 'conn') or self._thread_local.conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # SQLite性能优化
            conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
            conn.execute("PRAGMA synchronous=NORMAL")  # 更快的同步模式
            conn.execute("PRAGMA cache_size=-64000")  # 64MB缓存
            conn.execute("PRAGMA temp_store=MEMORY")  # 临时表在内存中
            conn.execute("PRAGMA mmap_size=268435456")  # 256MB内存映射
            self._thread_local.conn = conn
        return self._thread_local.conn

    def _close_connection(self):
        """关闭当前线程的数据库连接"""
        if hasattr(self._thread_local, 'conn') and self._thread_local.conn is not None:
            self._thread_local.conn.close()
            self._thread_local.conn = None

    def load_index(self, force_rebuild: bool = False):
        """加载知识库索引"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'")
            if not cursor.fetchone() or force_rebuild:
                self.build_vector_index(incremental=False)
            else:
                # 从 metadata 表读取（key-value 格式）
                cursor.execute("SELECT value FROM metadata WHERE key = 'total_files'")
                row = cursor.fetchone()
                if row:
                    print(f"知识库加载成功! 包含 {row[0]} 个文件")
                else:
                    print("知识库加载成功!")

                print("使用缓存的索引")
                self.load_vocabulary()

        except Exception as e:
            print(f"加载知识库失败: {e}")
            self._close_connection()
            raise

    def get_index_hash(self) -> str:
        """计算原始索引的哈希值 - 从SQLite获取"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT hash FROM metadata LIMIT 1")
        row = cursor.fetchone()
        if row:
            return row['hash']
        return ""

    def load_files_and_entities(self) -> Dict:
        """从 files 和 entities 表加载数据"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        files = []
        cursor.execute("SELECT * FROM files")
        for row in cursor.fetchall():
            file_id = row['id']
            
            cursor.execute("SELECT name, kind, parent, line, definition FROM entities WHERE file_id = ?", (file_id,))
            entities = [{'name': r['name'], 'kind': r['kind'], 'parent': r['parent'], 'line': r['line'], 'definition': r['definition']} for r in cursor.fetchall()]
            
            files.append({
                'path': row['path'],
                'full_path': row['full_path'],
                'extension': row['extension'],
                'size': row['size'],
                'line_count': row['line_count'],
                'hash': row['hash'],
                'last_modified': row['last_modified'],
                'entities': entities
            })
        
        cursor.execute("SELECT value FROM metadata WHERE key = 'total_lines'")
        row = cursor.fetchone()
        total_lines = int(row['value']) if row else 0
        
        return {'files': files, 'statistics': {'total_files': len(files), 'total_lines': total_lines}}

    def _load_existing_vectors(self) -> Tuple[Dict[str, bytes], Dict[str, bytes]]:
        """
        加载现有的向量数据（用于增量构建）
        
        Returns:
            (class_vectors_dict, function_vectors_dict) - 以 (file_path, name) 为key
        """
        class_vectors = {}
        func_vectors = {}
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 加载类向量
            cursor.execute("SELECT name, file_path, vector FROM classes WHERE vector IS NOT NULL")
            for row in cursor.fetchall():
                if row['vector']:
                    key = (row['file_path'], row['name'])
                    class_vectors[key] = row['vector']
            
            # 加载函数向量
            cursor.execute("SELECT name, file_path, vector FROM functions WHERE vector IS NOT NULL")
            for row in cursor.fetchall():
                if row['vector']:
                    key = (row['file_path'], row['name'])
                    func_vectors[key] = row['vector']
            
            print(f"  已加载现有向量: {len(class_vectors)} 类, {len(func_vectors)} 函数")
            
        except Exception as e:
            print(f"  加载现有向量失败: {e}")
        
        return class_vectors, func_vectors

    def _check_vectors_need_rebuild(self) -> bool:
        """
        检查向量是否需要重建
        
        Returns:
            True if full rebuild needed, False if can use incremental
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='classes'")
            if not cursor.fetchone():
                return True
            
            # 检查向量表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='class_vectors'")
            # 如果没有单独的向量表，检查 classes 表是否有 vector 列
            cursor.execute("PRAGMA table_info(classes)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'vector' not in columns:
                return True
                
            return False
        except:
            return True

    def tokenize(self, text: str) -> List[str]:
        """简单的分词函数 - 支持驼峰命名和蛇形命名"""
        import re

        # 先处理驼峰命名（在转小写之前）
        # 在大写字母前插入空格（除了单词开头）
        text = re.sub(r'(?<!^)(?=[A-Z])', ' ', text)

        # 替换下划线为空格（蛇形命名）
        text = text.replace('_', ' ')

        # 转换为小写
        text = text.lower()

        # 提取单词（只保留字母）
        words = re.findall(r'[a-z]+', text)

        # 过滤太短和常见的停用词
        stop_words = {'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
                      'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                      'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                      'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                      'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                      'through', 'during', 'before', 'after', 'above', 'below',
                      'between', 'under', 'and', 'but', 'or', 'yet', 'so',
                      'if', 'because', 'although', 'though', 'while', 'where',
                      'when', 'that', 'which', 'who', 'whom', 'whose', 'what',
                      'this', 'these', 'those', 'i', 'me', 'my', 'myself', 'we',
                      'our', 'ours', 'ourselves', 'you', 'your', 'yours',
                      'yourself', 'yourselves', 'he', 'him', 'his', 'himself',
                      'she', 'her', 'hers', 'herself', 'it', 'its', 'itself',
                      'they', 'them', 'their', 'theirs', 'themselves', 's'}

        result = []
        for word in words:
            if len(word) > 2 and word not in stop_words:
                result.append(word)

        return result

    def build_vocabulary(self, documents: List[str]) -> Tuple[Dict[str, int], Dict[str, float]]:
        """构建词汇表和 IDF 权重"""
        # 统计词频
        doc_freq = defaultdict(int)
        word_freq_per_doc = []

        for doc in documents:
            words = set(self.tokenize(doc))
            for word in words:
                doc_freq[word] += 1
            word_freq_per_doc.append(Counter(self.tokenize(doc)))

        # 计算 IDF
        idf_weights = {}
        doc_count = len(documents)
        for word, freq in doc_freq.items():
            idf_weights[word] = math.log(doc_count / (freq + 1)) + 1

        # 构建词汇表
        vocabulary = {word: idx for idx, word in enumerate(sorted(doc_freq.keys()))}

        return vocabulary, idf_weights

    def text_to_vector(self, text: str) -> Dict[int, float]:
        """将文本转换为 TF-IDF 稀疏向量 (使用字典存储)"""
        words = self.tokenize(text)
        word_freq = Counter(words)

        # 构建稀疏向量 (只存储非零值)
        vector = {}
        for word, freq in word_freq.items():
            if word in self.vocabulary:
                tf = freq / len(words)
                idf = self.idf_weights.get(word, 1.0)
                vector[self.vocabulary[word]] = tf * idf

        return vector

    @staticmethod
    def compute_class_vector(item: tuple, vocab: dict, idf_weights: dict) -> tuple:
        """并行计算类向量"""
        import re
        from collections import Counter
        import struct
        
        cls, full_path, desc = item
        
        # 本地tokenize
        def tokenize(text):
            text = re.sub(r'(?<!^)(?=[A-Z])', ' ', text)
            text = re.sub(r'[_\-]', ' ', text)
            words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9]*\b', text.lower())
            return [w for w in words if len(w) >= 2]
        
        words = tokenize(desc)
        word_freq = Counter(words)
        vector = {}
        for word, freq in word_freq.items():
            if word in vocab:
                tf = freq / len(words) if words else 0
                idf = idf_weights.get(word, 1.0)
                vector[vocab[word]] = tf * idf
        
        # 打包为二进制格式
        packed = SQLiteVectorKnowledgeBase._pack_vector_static(vector)
        
        return (
            cls['name'].lower(),
            cls['name'],
            cls['base_class'],
            cls.get('type_kind', 'class'),
            cls['line'],
            full_path,
            desc,
            cls.get('definition', ''),
            packed
        )
    
    @staticmethod
    def _pack_vector_static(vec: Dict[int, float]) -> bytes:
        """静态方法：打包向量为二进制"""
        if not vec:
            return struct.pack('I', 0)
        
        items = sorted(vec.items())
        count = len(items)
        packed = struct.pack('I', count)
        for word_id, weight in items:
            packed += struct.pack('If', word_id, weight)
        return packed
    
    @staticmethod
    def compute_func_vector(item: tuple, vocab: dict, idf_weights: dict) -> tuple:
        """并行计算函数向量"""
        import re
        from collections import Counter
        import struct
        
        func, full_path, desc = item
        
        # 本地tokenize
        def tokenize(text):
            text = re.sub(r'(?<!^)(?=[A-Z])', ' ', text)
            text = re.sub(r'[_\-]', ' ', text)
            words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9]*\b', text.lower())
            return [w for w in words if len(w) >= 2]
        
        words = tokenize(desc)
        word_freq = Counter(words)
        vector = {}
        for word, freq in word_freq.items():
            if word in vocab:
                tf = freq / len(words) if words else 0
                idf = idf_weights.get(word, 1.0)
                vector[vocab[word]] = tf * idf
        
        # 打包为二进制格式
        packed = SQLiteVectorKnowledgeBase._pack_vector_static(vector)
        
        return (
            func['name'].lower(),
            func['name'],
            func['line'],
            func.get('type', 'function'),
            full_path,
            desc,
            packed
        )

    def cosine_similarity(self, vec1: Dict[int, float], vec2: Dict[int, float]) -> float:
        """计算稀疏向量的余弦相似度"""
        # 计算点积
        dot_product = 0.0
        for idx, val in vec1.items():
            if idx in vec2:
                dot_product += val * vec2[idx]

        # 计算范数
        norm1 = math.sqrt(sum(val * val for val in vec1.values()))
        norm2 = math.sqrt(sum(val * val for val in vec2.values()))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def _pack_vector(self, vec: Dict[int, float]) -> bytes:
        """
        将稀疏向量打包为二进制格式
        格式: [count:4bytes][id1:4bytes][val1:4bytes][id2:4bytes][val2:4bytes]...
        """
        if not vec:
            return struct.pack('I', 0)
        
        items = sorted(vec.items())
        count = len(items)
        fmt = f'I{count}f'  # count个 (id, float) 对
        packed = struct.pack('I', count)
        for word_id, weight in items:
            packed += struct.pack('If', word_id, weight)
        return packed

    def _unpack_vector(self, data: bytes) -> Dict[int, float]:
        """
        从二进制格式解包稀疏向量
        """
        if not data or len(data) < 4:
            return {}
        
        count = struct.unpack('I', data[:4])[0]
        if count == 0:
            return {}
        
        vec = {}
        offset = 4
        for _ in range(count):
            word_id, weight = struct.unpack('If', data[offset:offset+8])
            vec[word_id] = weight
            offset += 8
        return vec

    def _create_tables(self, cursor):
        """创建所有数据库表（辅助方法）"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                hash TEXT PRIMARY KEY,
                timestamp REAL,
                total_files INTEGER,
                total_lines INTEGER,
                vector_size INTEGER,
                source_directory TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vocabulary (
                id INTEGER PRIMARY KEY,
                word TEXT UNIQUE,
                idf_weight REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                full_path TEXT PRIMARY KEY,
                path TEXT,
                extension TEXT,
                size INTEGER,
                line_count INTEGER,
                hash TEXT,
                last_modified TEXT,
                units TEXT,
                uses TEXT,
                description TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_lower TEXT,
                name TEXT,
                base_class TEXT,
                type_kind TEXT DEFAULT 'class',
                line INTEGER,
                file_path TEXT,
                description TEXT,
                definition TEXT,
                vector BLOB,
                FOREIGN KEY (file_path) REFERENCES files(full_path)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS functions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_lower TEXT,
                name TEXT,
                line INTEGER,
                type TEXT,
                file_path TEXT,
                description TEXT,
                vector BLOB,
                FOREIGN KEY (file_path) REFERENCES files(full_path)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_lower TEXT,
                name TEXT,
                file_path TEXT,
                description TEXT,
                FOREIGN KEY (file_path) REFERENCES files(full_path)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword_lower TEXT,
                keyword TEXT,
                file_path TEXT,
                FOREIGN KEY (file_path) REFERENCES files(full_path)
            )
        """)
        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_classes_name_lower ON classes(name_lower)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_classes_name ON classes(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_functions_name_lower ON functions(name_lower)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_units_name_lower ON units(name_lower)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_keywords_keyword_lower ON keywords(keyword_lower)")

    def build_vector_index(self, incremental: bool = False):
        """
        构建向量索引
        
        Args:
            incremental: 是否使用增量模式（保留现有向量，只计算新增/变化的）
        """
        print("正在构建 SQLite 向量索引...")
        start_time = time.time()

        conn = self._get_connection()
        cursor = conn.cursor()

        # 性能优化: 启用SQLite WAL模式和性能调优
        cursor.execute("PRAGMA journal_mode=WAL")  # WAL模式提升并发性能
        cursor.execute("PRAGMA synchronous=NORMAL")  # 减少fsync调用
        cursor.execute("PRAGMA cache_size=-64000")  # 64MB缓存
        cursor.execute("PRAGMA temp_store=MEMORY")  # 临时表存储在内存中

        if incremental:
            # 增量模式：检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'")
            if not cursor.fetchone():
                # 表不存在，创建表后完整构建
                self._create_tables(cursor)
                incremental = False  # 降级为完整构建
            else:
                # 增量模式：加载源索引获取当前文件列表 (从SQLite)
                source_index = self.load_files_and_entities()
                
                current_files = {f['full_path'] for f in source_index['files']}
                
                # 获取数据库中现有的文件列表
                cursor.execute("SELECT full_path FROM files")
                existing_files = {row[0] for row in cursor.fetchall()}
                
                # 找出已删除的文件
                deleted_files = existing_files - current_files
                
                if deleted_files:
                    print(f"  发现 {len(deleted_files)} 个已删除文件，清理关联数据...")
                    # 删除已不存在文件的向量数据
                    for del_file in deleted_files:
                        cursor.execute("DELETE FROM classes WHERE file_path=?", (del_file,))
                        cursor.execute("DELETE FROM functions WHERE file_path=?", (del_file,))
                    cursor.execute("DELETE FROM files WHERE full_path IN ({})".format(
                        ','.join('?' * len(deleted_files))
                    ), tuple(deleted_files))
                    print(f"  清理完成：删除 {len(deleted_files)} 个文件的向量数据")
                
                # 只清空 files/keywords/units，重新插入
                cursor.execute("DELETE FROM files")
                cursor.execute("DELETE FROM keywords")
                cursor.execute("DELETE FROM units")
                print("  增量模式：保留现有向量和词汇表")
        else:
            # 完整模式：删除现有表并重建
            cursor.execute("DROP TABLE IF EXISTS metadata")
            cursor.execute("DROP TABLE IF EXISTS files")
            cursor.execute("DROP TABLE IF EXISTS classes")
            cursor.execute("DROP TABLE IF EXISTS functions")
            cursor.execute("DROP TABLE IF EXISTS units")
            cursor.execute("DROP TABLE IF EXISTS keywords")
            cursor.execute("DROP TABLE IF EXISTS vocabulary")
            cursor.execute("DROP TABLE IF EXISTS class_vectors")
            cursor.execute("DROP TABLE IF EXISTS function_vectors")
            self._create_tables(cursor)
            
            # 完整模式需要创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_classes_name_lower ON classes(name_lower)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_classes_name ON classes(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_functions_name_lower ON functions(name_lower)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_units_name_lower ON units(name_lower)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_keywords_keyword_lower ON keywords(keyword_lower)")

        # 加载原始索引 (从SQLite)
        source_index = self.load_files_and_entities()

        # 收集所有文档用于构建词汇表
        all_documents = []

        for file_info in source_index['files']:
            file_path = file_info['path']

            # 处理类
            for cls in file_info.get('classes', []):
                class_desc = f"Class {cls['name']} inherits from {cls['base_class']} at line {cls['line']} in {file_path}"
                all_documents.append(class_desc)

            # 处理函数
            for func in file_info.get('functions', []):
                func_desc = f"{func.get('type', 'function')} {func['name']} at line {func['line']} in {file_path}"
                all_documents.append(func_desc)

        # 构建词汇表
        print("正在构建词汇表...")
        
        # 增量模式：加载现有词汇表
        existing_vocab = {}
        existing_idf = {}
        vocab_loaded = False
        if incremental:
            try:
                cursor.execute("SELECT word, id, idf_weight FROM vocabulary")
                rows = cursor.fetchall()
                if rows:
                    for row in rows:
                        existing_vocab[row['word']] = row['id']
                        existing_idf[row['word']] = row['idf_weight']
                    print(f"  已加载现有词汇: {len(existing_vocab)}")
                    vocab_loaded = True
            except:
                pass
        
        # 检查是否需要重建词汇表（当源文件变化时需要重建）
        need_rebuild_vocab = not vocab_loaded or not existing_vocab
        
        if not need_rebuild_vocab and incremental:
            # 词汇表已存在且完整，直接使用
            self.vocabulary = existing_vocab
            self.idf_weights = existing_idf
            print(f"  使用现有词汇表: {len(self.vocabulary)}")
        else:
            # 构建新词汇表
            new_vocab, new_idf = self.build_vocabulary(all_documents)
            
            # 合并词汇表（只在需要添加新词时）
            if incremental and existing_vocab:
                max_id = max(existing_vocab.values()) if existing_vocab else 0
                next_id = max_id + 1
                new_count = 0
                
                for word, word_id in new_vocab.items():
                    if word not in existing_vocab:
                        existing_vocab[word] = next_id
                        existing_idf[word] = new_idf[word]
                        next_id += 1
                        new_count += 1
                
                self.vocabulary = existing_vocab
                self.idf_weights = existing_idf
                print(f"  词汇表: 现有 {len(existing_vocab)}, 新增 {new_count}, 总计 {len(self.vocabulary)}")
            else:
                self.vocabulary = new_vocab
                self.idf_weights = new_idf

        # 保存词汇表到数据库 (批量插入)
        print("正在保存词汇表...")
        vocab_data = [(word_id, word, self.idf_weights[word]) for word, word_id in self.vocabulary.items()]
        
        if incremental:
            # 增量模式：先清空再插入（因为词汇表已被合并）
            cursor.execute("DELETE FROM vocabulary")
        
        cursor.executemany("""
            INSERT INTO vocabulary (id, word, idf_weight)
            VALUES (?, ?, ?)
        """, vocab_data)
        conn.commit()

        # 插入/更新元数据
        source_dir = source_index.get('source_directory', '')
        if incremental:
            cursor.execute("""
                UPDATE metadata SET hash=?, timestamp=?, total_files=?, total_lines=?, vector_size=?, source_directory=?
            """, (
                self.get_index_hash(),
                time.time(),
                source_index['statistics']['total_files'],
                source_index['statistics']['total_lines'],
                len(self.vocabulary),
                source_dir
            ))
        else:
            cursor.execute("""
                INSERT INTO metadata (hash, timestamp, total_files, total_lines, vector_size, source_directory)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                self.get_index_hash(),
                time.time(),
                source_index['statistics']['total_files'],
                source_index['statistics']['total_lines'],
                len(self.vocabulary),
                source_dir
            ))

        # 处理文件和插入数据 (批量插入,带进度显示)
        print("正在处理文件和构建向量...")
        
        # 去重：使用完整路径 (full_path) 作为唯一键，保留最后一个出现的
        # 注意：不能使用相对路径 path，因为不同目录下可能有同名文件
        unique_files = {}
        duplicates = []
        for file_info in source_index['files']:
            full_path = file_info.get('full_path', file_info['path'])
            if full_path in unique_files:
                duplicates.append((full_path, file_info['path']))
            unique_files[full_path] = file_info
        
        deduped_files = list(unique_files.values())
        if len(deduped_files) < len(source_index['files']):
            print(f"去重: 从 {len(source_index['files'])} 个文件减少到 {len(deduped_files)} 个")
            if duplicates:
                print(f"  发现 {len(duplicates)} 个重复项（基于完整路径）")
                for full_path, path in duplicates[:5]:  # 只显示前5个
                    print(f"    - {path}")
                if len(duplicates) > 5:
                    print(f"    ... 还有 {len(duplicates) - 5} 个")
        
        total_files = len(deduped_files)
        
        # 第一阶段：收集不需要向量计算的数据
        files_data = []
        units_data = []
        keywords_data = []
        
        print("第一阶段: 收集文件、单元和关键词数据...")
        
        for file_info in deduped_files:
            file_path = file_info['path']
            full_path = file_info.get('full_path', file_path)
            file_desc = f"{file_info['path']} {file_info.get('units', [])} {len(file_info.get('classes', []))} classes {len(file_info.get('functions', []))} functions"

            files_data.append((
                full_path,
                file_info['path'],
                file_info['extension'],
                file_info['size'],
                file_info['line_count'],
                file_info['hash'],
                file_info['last_modified'],
                json.dumps(file_info.get('units', [])),
                json.dumps(file_info.get('uses', [])),
                file_desc
            ))

            # 单元数据
            for unit in file_info.get('units', []):
                units_data.append((
                    unit.lower(),
                    unit,
                    full_path,
                    f"Unit {unit} in {file_path}"
                ))

            # 关键词数据
            keywords = set()
            for unit in file_info.get('units', []):
                keywords.add(unit.lower())
            for cls in file_info.get('classes', []):
                keywords.add(cls['name'].lower())
            for func in file_info.get('functions', []):
                keywords.add(func['name'].lower())

            for keyword in keywords:
                keywords_data.append((keyword, keyword, full_path))
        
        print(f"  文件: {len(files_data)}, 单元: {len(units_data)}, 关键词: {len(keywords_data)}")
        
        # 第二阶段：并行计算向量（支持增量构建）
        print("第二阶段: 并行计算向量...")
        
        from concurrent.futures import ProcessPoolExecutor
        from multiprocessing import cpu_count
        
        vocab = self.vocabulary
        idf_weights = self.idf_weights
        vector_size = len(vocab)
        
        # 加载现有向量（用于增量构建）
        existing_class_vectors, existing_func_vectors = self._load_existing_vectors()
        
        # 准备需要计算向量的项
        class_items = []  # (cls, full_path, file_path)
        func_items = []  # (func, full_path, file_path)
        
        # 统计信息
        total_classes = 0
        total_funcs = 0
        
        for file_info in deduped_files:
            file_path = file_info['path']
            full_path = file_info.get('full_path', file_path)
            total_classes += len(file_info.get('classes', []))
            total_funcs += len(file_info.get('functions', []))
            
            for cls in file_info.get('classes', []):
                # 增量构建：检查向量是否已存在
                key = (full_path, cls['name'])
                if key not in existing_class_vectors:
                    type_kind = cls.get('type_kind', 'class')
                    user_desc = cls.get('description', '')
                    if user_desc:
                        class_desc = f"{type_kind.capitalize()} {cls['name']}: {user_desc}"
                    else:
                        class_desc = f"{type_kind.capitalize()} {cls['name']} inherits from {cls['base_class']} at line {cls['line']} in {file_path}"
                    class_items.append((cls, full_path, class_desc))
            
            for func in file_info.get('functions', []):
                # 增量构建：检查向量是否已存在
                key = (full_path, func['name'])
                if key not in existing_func_vectors:
                    user_desc = func.get('description', '')
                    if user_desc:
                        func_desc = f"{func.get('type', 'function')} {func['name']}: {user_desc}"
                    else:
                        func_desc = f"{func.get('type', 'function')} {func['name']} at line {func['line']} in {file_path}"
                    func_items.append((func, full_path, func_desc))
        
        # 增量模式早期返回：所有向量已存在
        if incremental and len(class_items) == 0 and len(func_items) == 0:
            print(f"  所有向量已存在，跳过向量计算!")
            print(f"  复用向量: {total_classes} 类, {total_funcs} 函数")
            
            # 更新元数据和时间戳
            source_dir = source_index.get('source_directory', '')
            cursor.execute("""
                UPDATE metadata SET hash = ?, timestamp = ?, total_files = ?, total_lines = ?, vector_size = ?, source_directory = ?
            """, (
                self.get_index_hash(),
                time.time(),
                source_index['statistics']['total_files'],
                source_index['statistics']['total_lines'],
                len(self.vocabulary),
                source_dir
            ))
            conn.commit()
            
            elapsed = time.time() - start_time
            print(f"增量索引构建完成! 耗时: {elapsed*1000:.2f}ms")
            return
        
        # 报告向量计算情况
        if len(class_items) == 0 and len(func_items) == 0:
            print(f"  所有向量已存在，跳过向量计算!")
            print(f"  复用向量: {total_classes} 类, {total_funcs} 函数")
        else:
            print(f"  需要计算向量: {len(class_items)} 类 (新增), {len(func_items)} 函数 (新增)")
            print(f"  复用向量: {total_classes - len(class_items)} 类, {total_funcs - len(func_items)} 函数")
        
        # 动态计算worker数和chunksize
        # 目标：减少IPC开销，每个chunk处理更多数据
        n_workers = max(2, min(8, cpu_count() - 1))
        
        # 动态chunksize: 基于项目数量，使用更大chunksize减少IPC开销
        # 公式: chunksize = max(500, items // workers) - 每个worker至少处理500个
        class_chunksize = max(500, len(class_items) // n_workers)
        func_chunksize = max(500, len(func_items) // n_workers)
        
        print(f"  使用 {n_workers} 进程并行计算 (类chunksize={class_chunksize}, 函数chunksize={func_chunksize})...")
        
        def compute_class_vector(item):
            cls, full_path, desc = item
            vector = self.text_to_vector(desc)
            return (
                cls['name'].lower(),
                cls['name'],
                cls['base_class'],
                cls.get('type_kind', 'class'),
                cls['line'],
                full_path,
                desc,
                cls.get('definition', ''),
                json.dumps(vector)
            )
        
        classes_data = []
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            # 使用partial传递vocab和idf_weights
            from functools import partial
            func = partial(SQLiteVectorKnowledgeBase.compute_class_vector, vocab=vocab, idf_weights=idf_weights)
            results = list(executor.map(func, class_items, chunksize=class_chunksize))
            classes_data = results
        
        print(f"  类向量计算完成: {len(classes_data)}")
        
        # 并行计算函数向量
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            from functools import partial
            func = partial(SQLiteVectorKnowledgeBase.compute_func_vector, vocab=vocab, idf_weights=idf_weights)
            results = list(executor.map(func, func_items, chunksize=func_chunksize))
            functions_data = results
        
        print(f"  函数向量计算完成: {len(functions_data)}")

        # 批量插入数据 - 使用单事务提高性能
        print("正在批量插入数据...")
        
        try:
            print(f"  - 插入文件数据 ({len(files_data)} 条)...")
            cursor.executemany("""
                INSERT INTO files (
                    full_path, path, extension, size, line_count,
                    hash, last_modified, units, uses, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, files_data)
            print(f"  - 文件数据插入完成")

            print(f"  - 插入类数据 ({len(classes_data)} 条)...")
            # 增量模式下先删除已存在的类
            if incremental and classes_data:
                for cd in classes_data:
                    cursor.execute("DELETE FROM classes WHERE file_path=? AND name=?", (cd[5], cd[1]))
            cursor.executemany("""
                INSERT INTO classes (name_lower, name, base_class, type_kind, line, file_path, description, definition, vector)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, classes_data)
            print(f"  - 类数据插入完成")

            print(f"  - 插入函数数据 ({len(functions_data)} 条)...")
            # 增量模式下先删除已存在的函数
            if incremental and functions_data:
                for fd in functions_data:
                    cursor.execute("DELETE FROM functions WHERE file_path=? AND name=?", (fd[3], fd[0]))
            cursor.executemany("""
                INSERT INTO functions (name_lower, name, line, type, file_path, description, vector)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, functions_data)
            print(f"  - 函数数据插入完成")

            print(f"  - 插入单元数据 ({len(units_data)} 条)...")
            cursor.executemany("""
                INSERT INTO units (name_lower, name, file_path, description)
                VALUES (?, ?, ?, ?)
            """, units_data)
            print(f"  - 单元数据插入完成")

            print(f"  - 插入关键词数据 ({len(keywords_data)} 条)...")
            cursor.executemany("""
                INSERT INTO keywords (keyword_lower, keyword, file_path)
                VALUES (?, ?, ?)
            """, keywords_data)
            print(f"  - 关键词数据插入完成")
            
            conn.commit()
            print("  - 数据提交完成")
            
        except Exception as e:
            conn.rollback()
            print(f"  - 数据插入失败: {e}")
            raise

        # 提交事务
        conn.commit()

        # 优化数据库
        cursor.execute("ANALYZE")
        conn.commit()

        elapsed = (time.time() - start_time) * 1000
        print(f"SQLite 向量索引构建完成! 耗时: {elapsed:.2f}ms")
        print(f"词汇表大小: {len(self.vocabulary)}")

    def load_vocabulary(self):
        """从数据库加载词汇表"""
        print("正在加载词汇表...")
        conn = self._get_connection()
        cursor = conn.cursor()

        # 检查 vocabulary 表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vocabulary'")
        if cursor.fetchone():
            cursor.execute("SELECT id, word, idf_weight FROM vocabulary")
            for row in cursor.fetchall():
                self.vocabulary[row['word']] = row['id']
                self.idf_weights[row['word']] = row['idf_weight']
            print(f"词汇表加载完成! 大小: {len(self.vocabulary)}")
        else:
            print("词汇表不存在，跳过加载（精确查询仍可用）")

    def semantic_search_classes(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """语义搜索类"""
        query_vector = self.text_to_vector(query)

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, vector FROM classes")

        results = []
        for row in cursor.fetchall():
            stored_vector = self._unpack_vector(row['vector'])
            similarity = self.cosine_similarity(query_vector, stored_vector)
            if similarity > 0:
                results.append((row['name'], similarity))

        # 排序并返回 top-k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def semantic_search_functions(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """语义搜索函数"""
        query_vector = self.text_to_vector(query)

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, vector FROM functions")

        results = []
        for row in cursor.fetchall():
            stored_vector = self._unpack_vector(row['vector'])
            similarity = self.cosine_similarity(query_vector, stored_vector)
            if similarity > 0:
                results.append((row['name'], similarity))

        # 排序并返回 top-k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def search(self, query: str, search_type: str = 'all') -> List[Dict]:
        """
        统一搜索接口
        
        Args:
            query: 搜索查询
            search_type: 搜索类型 ('all', 'class', 'function', 'unit', 'keyword')
        
        Returns:
            搜索结果列表
        """
        results = []
        
        if search_type in ('all', 'class'):
            class_results = self.search_by_class_name(query)
            for r in class_results:
                r['result_type'] = 'class'
                r['definition'] = r.get('class', {}).get('definition', '')
            results.extend(class_results)
        
        if search_type in ('all', 'function'):
            func_results = self.search_by_function_name(query)
            for r in func_results:
                r['result_type'] = 'function'
            results.extend(func_results)
        
        if search_type in ('all', 'unit'):
            unit_results = self.search_by_unit_name(query)
            for r in unit_results:
                r['result_type'] = 'unit'
            results.extend(unit_results)
        
        return results

    def search_by_class_name(self, class_name: str) -> List[Dict]:
        """根据类名搜索 (精确匹配)"""
        class_name_lower = class_name.lower()
        conn = self._get_connection()
        cursor = conn.cursor()

        # 使用 entities 表（3表结构）
        cursor.execute("""
            SELECT e.name, e.kind, e.parent, e.line, e.definition, f.path, f.full_path, 
                   f.extension, f.size, f.line_count, f.hash, f.last_modified, f.units, f.uses
            FROM entities e
            INNER JOIN files f ON e.file_id = f.id
            WHERE LOWER(e.name) = ? AND e.kind IN ('TC', 'TR', 'TI', 'TE', 'TS', 'TY', 'TH')
        """, (class_name_lower,))

        results = []
        for row in cursor.fetchall():
            results.append({
                'name': row['name'],
                'kind': row['kind'],
                'parent': row['parent'],
                'line': row['line'],
                'definition': row['definition'] or '',
                'file': {
                    'path': row['path'],
                    'full_path': row['full_path'],
                    'extension': row['extension'],
                    'size': row['size'],
                    'line_count': row['line_count'],
                    'hash': row['hash'],
                    'last_modified': row['last_modified'],
                    'units': json.loads(row['units']) if row['units'] else [],
                    'uses': json.loads(row['uses']) if row['uses'] else []
                }
            })

        return results

    def search_by_function_name(self, function_name: str) -> List[Dict]:
        """根据函数名搜索 (精确匹配)"""
        function_name_lower = function_name.lower()
        conn = self._get_connection()
        cursor = conn.cursor()

        # 使用 entities 表（3表结构）
        cursor.execute("""
            SELECT e.name, e.kind, e.definition, e.line, f.path, f.full_path, 
                   f.extension, f.size, f.line_count, f.hash, f.last_modified, f.units, f.uses
            FROM entities e
            INNER JOIN files f ON e.file_id = f.id
            WHERE LOWER(e.name) = ? AND e.kind IN ('FF', 'FP')
        """, (function_name_lower,))

        results = []
        file_cache = {}
        
        for row in cursor.fetchall():
            file_path = row['full_path']
            line_num = row['line']
            
            if file_path not in file_cache:
                file_cache[file_path] = self._get_file_types(file_path)
            
            parent = self._find_parent_from_cache(file_path, line_num, file_cache[file_path])
            
            results.append({
                'name': row['name'],
                'kind': row['kind'],
                'definition': row['definition'] or '',
                'line': row['line'],
                'parent': parent,
                'file': {
                    'path': row['path'],
                    'full_path': row['full_path'],
                    'extension': row['extension'],
                    'size': row['size'],
                    'line_count': row['line_count'],
                    'hash': row['hash'],
                    'last_modified': row['last_modified'],
                    'units': json.loads(row['units']) if row['units'] else [],
                    'uses': json.loads(row['uses']) if row['uses'] else []
                }
            })

        return results

    def search_by_keywords(self, keywords: List[str], kind_filter: str = None) -> List[Dict]:
        """
        多关键词模糊搜索 (使用反转字符串匹配)
        
        Args:
            keywords: 关键词列表，如 ["create", "button"]
            kind_filter: 可选的类型过滤 ('TC', 'FF', 'FP', etc.)
        
        Returns:
            匹配的结果列表
        """
        if not keywords:
            return []
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        rev_keywords = [k[::-1].lower() for k in keywords]
        
        conditions = ["name_lower_rev LIKE ?" for _ in rev_keywords]
        where_clause = " AND ".join(conditions)
        
        if kind_filter:
            if isinstance(kind_filter, list):
                kind_list = "'" + "','".join(kind_filter) + "'"
                where_clause += f" AND kind IN ({kind_list})"
            else:
                where_clause += f" AND kind = '{kind_filter}'"
        
        cursor.execute(f"""
            SELECT e.name, e.kind, e.parent, e.definition, e.line, f.path, f.full_path,
                   f.extension, f.size, f.line_count, f.hash, f.last_modified, f.units, f.uses
            FROM entities e
            INNER JOIN files f ON e.file_id = f.id
            WHERE {where_clause}
        """, tuple([f'%{k}%' for k in rev_keywords]))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'name': row['name'],
                'kind': row['kind'],
                'parent': row['parent'],
                'definition': row['definition'] or '',
                'line': row['line'],
                'file': {
                    'path': row['path'],
                    'full_path': row['full_path'],
                    'extension': row['extension'],
                    'size': row['size'],
                    'line_count': row['line_count'],
                    'hash': row['hash'],
                    'last_modified': row['last_modified'],
                    'units': json.loads(row['units']) if row['units'] else [],
                    'uses': json.loads(row['uses']) if row['uses'] else []
                }
            })
        
        return results
    
    def _get_file_types(self, file_path: str) -> Optional[List[Dict]]:
        """获取文件中的所有类型定义及其范围"""
        if not file_path:
            return None
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT name, start_line, start_offset
                FROM entities
                WHERE file_id = (
                    SELECT id FROM files WHERE full_path = ?
                )
                AND kind IN ('TC', 'TR', 'TI', 'TH')
                AND start_line IS NOT NULL
                AND start_offset IS NOT NULL
                ORDER BY start_line
            """, (file_path,))
            
            types = list(cursor.fetchall())
            if not types:
                return None
            
            if not os.path.exists(file_path):
                return None
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            type_ranges = []
            for i, row in enumerate(types):
                type_name = row['name']
                start_line = row['start_line']
                start_offset = row['start_offset']
                
                # 计算 end_line: 使用下一个类型的 start_line - 1
                # 这样可以正确处理 interface (其内部的 end; 会导致错误范围)
                if i + 1 < len(types):
                    next_start_line = types[i + 1]['start_line']
                else:
                    next_start_line = float('inf')
                
                type_ranges.append((type_name, start_line, next_start_line - 1))
            
            return type_ranges
            
        except Exception:
            return None
    
    def _find_parent_from_cache(self, file_path: str, line_num: int, type_ranges: Optional[List[tuple]]) -> Optional[str]:
        """从缓存的类型范围中查找父类"""
        if not type_ranges:
            return None
        
        for type_name, start_line, end_line in reversed(type_ranges):
            if start_line < line_num <= end_line:
                return type_name
        
        return None

    def _find_parent_by_line_fast(self, file_path: str, line_num: int) -> Optional[str]:
        """快速查找父类 - 优先SQL"""
        if not file_path:
            return None
            
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 简单SQL查询：用start_line判断
            cursor.execute("""
                SELECT name, start_line
                FROM entities
                WHERE file_id = (
                    SELECT id FROM files WHERE full_path = ?
                )
                AND kind IN ('TC', 'TR', 'TI', 'TH')
                AND start_line IS NOT NULL
                ORDER BY start_line
            """, (file_path,))
            
            types = list(cursor.fetchall())
            for i, row in enumerate(types):
                if row['start_line'] < line_num:
                    next_line = types[i + 1]['start_line'] if i + 1 < len(types) else float('inf')
                    if line_num < next_line:
                        return row['name']
            
        except Exception:
            pass
            
        return None

    def _find_parent_by_line(self, file_path: str, line_num: int) -> Optional[str]:
        """
        根据行号查找所属的类或记录
        优化版本：一次读取文件，找到所有类型的end位置，精确判断嵌套关系
        """
        if not file_path:
            return None
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 获取文件中所有类型定义及其偏移（按行号排序）
            cursor.execute("""
                SELECT name, start_line, start_offset
                FROM entities
                WHERE file_id = (
                    SELECT id FROM files WHERE full_path = ?
                )
                AND kind IN ('TC', 'TR', 'TI', 'TH')
                AND start_line IS NOT NULL
                AND start_offset IS NOT NULL
                ORDER BY start_line
            """, (file_path,))
            
            types = list(cursor.fetchall())
            if not types:
                return None
            
            # 一次读取文件，找到所有类型的end位置
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            type_ranges = []
            
            for row in types:
                type_name = row['name']
                start_line = row['start_line']
                start_offset = row['start_offset']
                
                # 从 start_offset 开始查找 end;
                remaining = content[start_offset:]
                
                # 找到第一个 end; (可能嵌套)
                end_pos = remaining.find('end;')
                if end_pos >= 0:
                    end_line = start_line + remaining[:end_pos].count('\n')
                else:
                    end_line = float('inf')
                
                type_ranges.append((type_name, start_line, end_line))
            
            # 从后向前查找：找到最后一个 start_line < method_line 的类型
            for type_name, start_line, end_line in reversed(type_ranges):
                if start_line < line_num <= end_line:
                    return type_name
            
        except Exception:
            pass
            
        return None

    def search_by_unit_name(self, unit_name: str) -> List[Dict]:
        """根据单元名搜索 (精确匹配)"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 搜索 files 表的 units JSON 字段
        cursor.execute("""
            SELECT path, full_path, extension, size, line_count, hash, last_modified, units, uses
            FROM files
            WHERE units LIKE ?
        """, (f'%"{unit_name}"%',))

        results = []
        for row in cursor.fetchall():
            units = json.loads(row['units']) if row['units'] else []
            if unit_name.lower() in [u.lower() for u in units]:
                results.append({
                    'name': unit_name,
                    'file': {
                        'path': row['path'],
                        'full_path': row['full_path'],
                        'extension': row['extension'],
                        'size': row['size'],
                        'line_count': row['line_count'],
                        'hash': row['hash'],
                        'last_modified': row['last_modified'],
                        'units': units,
                        'uses': json.loads(row['uses']) if row['uses'] else []
                    }
                })

        return results

    def search_by_keyword(self, keyword: str, search_in: Optional[List[str]] = None) -> List[Dict]:
        """根据关键词搜索 (在实体名称中搜索)"""
        keyword_lower = keyword.lower()
        conn = self._get_connection()
        cursor = conn.cursor()

        # 在 entities 表中搜索名称包含关键词的实体
        cursor.execute("""
            SELECT e.name, e.kind, e.definition, e.line, f.path, f.full_path
            FROM entities e
            INNER JOIN files f ON e.file_id = f.id
            WHERE LOWER(e.name) LIKE ?
            LIMIT 100
        """, (f'%{keyword_lower}%',))

        results = []
        for row in cursor.fetchall():
            results.append({
                'name': row['name'],
                'kind': row['kind'],
                'definition': row['definition'],
                'line': row['line'],
                'file': row['full_path']
            })

        return results

    def search_members(self, class_name: str, include_inherited: bool = False) -> List[Dict]:
        """
        搜索类的成员（按需解析）
        
        Args:
            class_name: 类名
            include_inherited: 是否包含继承的成员
        
        Returns:
            成员列表
        """
        import re
        from pathlib import Path
        from src.utils.delphi_parser import extract_class_members
        
        if not hasattr(self, '_member_cache'):
            self._member_cache = {}
        
        if class_name in self._member_cache:
            cached_members = self._member_cache[class_name]
            if include_inherited:
                return cached_members
            else:
                own_members = [m for m in cached_members if m.get('source_class') == class_name]
                return own_members
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name, file_path, definition, base_class, type_kind 
            FROM classes WHERE name = ?
        """, (class_name,))
        
        row = cursor.fetchone()
        if not row:
            return []
        
        file_path = row['file_path']
        definition = row['definition']
        
        members = []
        parsed_classes = set()
        
        def parse_and_get_members(cls_name: str):
            if cls_name in parsed_classes:
                return []
            parsed_classes.add(cls_name)
            
            cursor.execute("""
                SELECT name, file_path, definition, base_class 
                FROM classes WHERE name = ?
            """, (cls_name,))
            
            row = cursor.fetchone()
            if not row:
                return []
            
            fp = row['file_path']
            defn = row['definition']
            parent = row['base_class']
            
            cache_key = (fp, cls_name)
            if cache_key in self._member_cache:
                return self._member_cache[cache_key]
            
            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except:
                return []
            
            class_members = extract_class_members(content)
            cls_members = class_members.get(cls_name, [])
            
            for m in cls_members:
                m['source_class'] = cls_name
                m['source_file'] = fp
            
            self._member_cache[cache_key] = cls_members
            
            result = list(cls_members)
            
            if parent and include_inherited:
                parent_members = parse_and_get_members(parent)
                result.extend(parent_members)
            
            return result
        
        all_members = parse_and_get_members(class_name)
        
        self._member_cache[class_name] = all_members
        
        if not include_inherited:
            return [m for m in all_members if m.get('source_class') == class_name]
        
        return all_members

    def close(self):
        """关闭数据库连接"""
        self._close_connection()

    def __del__(self):
        """析构函数,确保数据库连接关闭"""
        self.close()


def main():
    """命令行查询接口"""
    import argparse

    parser = argparse.ArgumentParser(description='Delphi 知识库查询工具 (SQLite 向量扩展版)')
    parser.add_argument('--kb-dir', default=r'c:\User\diandaxia\delphi-knowledge-base',
                       help='知识库目录')
    parser.add_argument('--search-type', choices=['unit', 'class', 'function', 'keyword', 'semantic'],
                       default='semantic', help='搜索类型')
    parser.add_argument('--query', required=True, help='搜索查询')
    parser.add_argument('--top-k', type=int, default=10, help='语义搜索返回结果数量')
    parser.add_argument('--rebuild', action='store_true', help='强制重新构建索引')

    args = parser.parse_args()

    # 初始化知识库
    kb = SQLiteVectorKnowledgeBase(args.kb_dir, force_rebuild=args.rebuild)

    try:
        # 执行搜索
        if args.search_type == 'semantic':
            # 语义搜索
            class_results = kb.semantic_search_classes(args.query, top_k=args.top_k)
            function_results = kb.semantic_search_functions(args.query, top_k=args.top_k)

            print(f"语义搜索 '{args.query}' 的结果:")
            print(f"\n最相关的类:")
            for class_name, score in class_results[:5]:
                exact_results = kb.search_by_class_name(class_name)
                if exact_results:
                    result = exact_results[0]
                    print(f"  {result['class']['name']} (相似度: {score:.3f}) - {result['file']['path']}")

            print(f"\n最相关的函数:")
            for func_name, score in function_results[:5]:
                exact_results = kb.search_by_function_name(func_name)
                if exact_results:
                    result = exact_results[0]
                    print(f"  {result['function']['name']} (相似度: {score:.3f}) - {result['file']['path']}")

        elif args.search_type == 'class':
            results = kb.search_by_class_name(args.query)
            print(f"找到 {len(results)} 个类: '{args.query}'")
            for i, result in enumerate(results[:10], 1):
                print(f"\n{i}. {result['file']['path']}")
                print(f"   - 类: {result['class']['name']}")

        elif args.search_type == 'function':
            results = kb.search_by_function_name(args.query)
            print(f"找到 {len(results)} 个函数: '{args.query}'")
            for i, result in enumerate(results[:10], 1):
                print(f"\n{i}. {result['file']['path']}")
                print(f"   - 函数: {result['function']['name']}")

        elif args.search_type == 'keyword':
            results = kb.search_by_keyword(args.query)
            print(f"找到 {len(results)} 个文件包含关键词: '{args.query}'")
            for i, result in enumerate(results[:10], 1):
                print(f"\n{i}. {result['path']}")

    finally:
        kb.close()


if __name__ == "__main__":
    main()
