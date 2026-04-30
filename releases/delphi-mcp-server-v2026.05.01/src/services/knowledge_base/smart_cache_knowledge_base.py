#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能缓存知识库实现
- 只存储稀疏向量（BLOB格式），不预构建密集向量
- 查询时按需构建向量，使用LRU缓存加速
- 支持异步后台构建向量
- 支持链接模式和缓存模式
"""

import json
import os
import sqlite3
import math
import struct
import threading
import time
import re
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from collections import Counter, OrderedDict
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count


class LRUCache:
    """LRU缓存实现"""
    
    def __init__(self, maxsize: int = 10000):
        self.maxsize = maxsize
        self.cache: OrderedDict = OrderedDict()
    
    def get(self, key: int) -> Optional[Dict]:
        if key in self.cache:
            # 移到最后（最近使用）
            self.cache.move_to_end(key)
            return self.cache[key]
        return None
    
    def set(self, key: int, value: Dict):
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.maxsize:
                # 删除最旧的
                self.cache.popitem(last=False)
        self.cache[key] = value
    
    def __contains__(self, key: int) -> bool:
        return key in self.cache
    
    def __len__(self) -> int:
        return len(self.cache)


class SourcePathResolver:
    """源码路径解析器"""
    
    def __init__(self, kb_dir: Path, config: Dict):
        self.kb_dir = kb_dir
        self.config = config
        self.source_config = config.get('source', {})
    
    def get_source_paths(self) -> List[Path]:
        """获取源码路径列表"""
        source_type = self.source_config.get('type', 'link')
        
        if source_type == 'link':
            return self._resolve_link_paths()
        elif source_type == 'cache':
            return self._resolve_cache_paths()
        else:
            raise ValueError(f"未知的源码类型: {source_type}")
    
    def _resolve_link_paths(self) -> List[Path]:
        """解析链接路径（直接链接到外部目录）"""
        paths = []
        
        # 单一路径
        if 'path' in self.source_config:
            path = self.source_config['path']
            # 支持相对路径
            if not Path(path).is_absolute():
                path = self.kb_dir / path
            paths.append(Path(path))
        
        # 多个路径（第三方库）
        if 'paths' in self.source_config:
            for item in self.source_config['paths']:
                path = item['path']
                if not Path(path).is_absolute():
                    path = self.kb_dir / path
                paths.append(Path(path))
        
        return paths
    
    def _resolve_cache_paths(self) -> List[Path]:
        """解析缓存路径（使用files子目录）"""
        # 使用files子目录
        files_dir = self.kb_dir / "files"
        
        # 如果files目录不存在，创建它
        if not files_dir.exists():
            files_dir.mkdir(parents=True, exist_ok=True)
            print(f"创建缓存目录: {files_dir}")
        
        return [files_dir]
    
    def should_use_files_dir(self) -> bool:
        """是否使用files子目录"""
        return self.source_config.get('use_files_dir', False)


class SmartCacheKnowledgeBase:
    """智能缓存知识库"""
    
    # 类型编码映射 (统一使用双字母代码)
    TYPE_MAP = {
        # 类型定义
        'TC': 'class',
        'TR': 'record', 
        'TI': 'interface',
        'TE': 'enum',
        'TS': 'set of',
        'TY': 'type alias',
        # 过程/函数
        'FF': 'function',
        'FP': 'procedure',
        'PT': 'procedure type',
        # 成员
        'MM': 'method',
        'MF': 'field',
        'MP': 'property',
        'ME': 'event',
        # 其他
        'CC': 'const',
        'CR': 'resourcestring',
        'UI': 'unit',
        'TH': 'helper',
        'AT': 'attribute',
        'GT': 'generic type',
    }
    # 反向映射
    TYPE_REVERSE_MAP = {v: k for k, v in TYPE_MAP.items()}
    
    def __init__(self, kb_dir: str, config: Dict = None, progress_callback: callable = None):
        self.kb_dir = Path(kb_dir)
        self.config = config or self._load_config()
        self.progress_callback = progress_callback
        
        # 数据库
        self.db_path = self.kb_dir / self.config['database']['file']
        self._init_database()
        
        # 向量缓存（LRU）
        cache_size = self.config['database'].get('cache_size', 10000)
        self._vector_cache = LRUCache(maxsize=cache_size)
        
        # 词汇表
        self.vocabulary: Dict[str, int] = {}
        self.idf_weights: Dict[str, float] = {}
        
        # 构建状态
        self._building = False
        self._build_thread: Optional[threading.Thread] = None
        
        # 源码路径解析器
        self.path_resolver = SourcePathResolver(self.kb_dir, self.config)
        
        # 加载词汇表
        self._load_vocabulary()
    
    def _load_config(self) -> Dict:
        """加载配置文件"""
        config_path = self.kb_dir / "config.json"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # 默认配置
            return {
                'database': {'file': 'knowledge_base.sqlite', 'cache_size': 10000},
                'source': {'type': 'link', 'path': 'files'},
                'build': {'parallel_workers': 4, 'batch_size': 1000}
            }
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        
        # 性能优化
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA busy_timeout=10000")  # 等待锁最长10秒，避免 database is locked
        
        return conn
    
    def _init_database(self):
        """初始化数据库"""
        # 确保目录存在
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 创建表结构
        self._create_tables(cursor)
        conn.commit()
        conn.close()
    
    def _create_tables(self, cursor):
        """创建数据库表"""
        # 检测旧schema并删除旧表(force_rebuild时由调用方处理)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(files)")
            files_columns = [row[1] for row in cursor.fetchall()]
            if 'relative_path' not in files_columns:
                cursor.execute("DROP TABLE IF EXISTS build_queue")
                cursor.execute("DROP TABLE IF EXISTS vocabularies")
                cursor.execute("DROP TABLE IF EXISTS vocabulary")
                cursor.execute("DROP TABLE IF EXISTS metadata")
                cursor.execute("DROP TABLE IF EXISTS files")
        
        # files表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_path TEXT UNIQUE NOT NULL,
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
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now'))
            )
        """)
        
        # vocabularies表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vocabularies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                name_lower TEXT NOT NULL,
                name_lower_rev TEXT,
                file_id INTEGER,
                line INTEGER,
                base_class TEXT,
                description TEXT,
                vector BLOB,
                vector_status TEXT DEFAULT 'pending',
                attributes TEXT,
                created_at REAL DEFAULT (julianday('now')),
                updated_at REAL DEFAULT (julianday('now')),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            )
        """)
        
        # vocabulary表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vocabulary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT UNIQUE NOT NULL,
                idf_weight REAL,
                document_frequency INTEGER,
                is_stopword INTEGER DEFAULT 0,
                created_at REAL DEFAULT (julianday('now'))
            )
        """)
        
        # metadata表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at REAL DEFAULT (julianday('now'))
            )
        """)
        
        # build_queue表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS build_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                item_type TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                created_at REAL DEFAULT (julianday('now')),
                processed_at REAL,
                FOREIGN KEY (item_id) REFERENCES vocabularies(id) ON DELETE CASCADE
            )
        """)
        
        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files(relative_path)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_category ON files(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocabularies_type ON vocabularies(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocabularies_name ON vocabularies(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocabularies_name_lower ON vocabularies(name_lower)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocabularies_name_lower_rev ON vocabularies(name_lower_rev)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocabularies_file_id ON vocabularies(file_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocabularies_vector_status ON vocabularies(vector_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocabulary_word ON vocabulary(word)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_build_queue_status ON build_queue(status)")
    
    def _load_vocabulary(self):
        """加载词汇表"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT id, word, idf_weight FROM vocabulary")
            for row in cursor.fetchall():
                self.vocabulary[row['word']] = row['id']
                self.idf_weights[row['word']] = row['idf_weight']
        except:
            pass
        finally:
            conn.close()
    
    def tokenize(self, text: str) -> List[str]:
        """分词函数 - 支持驼峰命名和蛇形命名"""
        if not text:
            return []
        
        # 处理驼峰命名
        text = re.sub(r'(?<!^)(?=[A-Z])', ' ', text)
        # 替换下划线为空格
        text = text.replace('_', ' ')
        # 转换为小写
        text = text.lower()
        # 提取单词
        words = re.findall(r'[a-z]+', text)
        
        # 停用词
        stop_words = {'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
                      'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                      'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                      'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                      'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                      'through', 'during', 'before', 'after', 'above', 'below',
                      'between', 'under', 'and', 'but', 'or', 'yet', 'so'}
        
        return [w for w in words if len(w) > 2 and w not in stop_words]
    
    def text_to_vector(self, text: str) -> Dict[int, float]:
        """将文本转换为TF-IDF稀疏向量"""
        words = self.tokenize(text)
        if not words:
            return {}
        
        word_freq = Counter(words)
        vector = {}
        
        for word, freq in word_freq.items():
            if word in self.vocabulary:
                tf = freq / len(words)
                idf = self.idf_weights.get(word, 1.0)
                vector[self.vocabulary[word]] = tf * idf
        
        return vector
    
    def _pack_vector(self, vec: Dict[int, float]) -> bytes:
        """打包向量为二进制格式"""
        if not vec:
            return struct.pack('I', 0)
        
        items = sorted(vec.items())
        count = len(items)
        packed = struct.pack('I', count)
        for word_id, weight in items:
            packed += struct.pack('If', word_id, weight)
        return packed
    
    def _unpack_vector(self, data: bytes) -> Dict[int, float]:
        """解包稀疏向量"""
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
    
    def _cosine_similarity(self, vec1: Dict[int, float], vec2: Dict[int, float]) -> float:
        """计算余弦相似度"""
        # 点积
        dot_product = sum(vec1[k] * vec2[k] for k in vec1 if k in vec2)
        
        # 范数
        norm1 = math.sqrt(sum(v * v for v in vec1.values()))
        norm2 = math.sqrt(sum(v * v for v in vec2.values()))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def rebuild_async(self, incremental: bool = False, source_paths: Optional[List[str]] = None):
        """异步重建知识库
        
        Args:
            incremental: 是否增量构建(跳过未变化的文件)
            source_paths: 外部指定的源码路径列表(为None时使用config中的路径)
        """
        if self._building:
            print("构建已在进行中...")
            return
        
        # 获取源码路径
        if source_paths is not None:
            from pathlib import Path
            resolved_paths = [Path(p) for p in source_paths]
        else:
            resolved_paths = self.path_resolver.get_source_paths()
        print(f"源码路径: {[str(p) for p in resolved_paths]}")
        
        # 阶段1：初始化（同步）
        print("\n阶段1：初始化...")
        self._rebuild_init(resolved_paths, incremental=incremental)
        
        # 阶段2：启动异步构建
        print("\n阶段2：启动异步向量构建...")
        self._start_async_build(self.progress_callback)
        
        print("\n知识库已可用，向量正在后台构建中...")
    
    @staticmethod
    def _parse_delphi_file_static(file_path_str: str) -> Tuple[str, List[Dict]]:
        """静态方法：解析Delphi源文件（用于多进程）- 复用 _extract_all_entities"""
        import re
        from pathlib import Path
        from src.services.knowledge_base.scan_delphi_sources import _extract_all_entities
        
        file_path = Path(file_path_str)
        items = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 核心实体复用 _extract_all_entities
            entities = _extract_all_entities(content)
            
            # 补充提取: 细分类型 (先收集, 用于覆盖 TY 中被泛化匹配的条目)
            _array_names = set()
            _pointer_names = set()
            _anon_method_names = set()
            _subrange_names = set()
            
            # 数组类型 (AT)
            array_pattern = r'\b([A-Z][a-zA-Z0-9]*)\s*=\s*array\s*(?:\[([^\]]+)\])?\s*of\s+([^;]+)\s*;'
            for match in re.finditer(array_pattern, content, re.IGNORECASE):
                arr_name = match.group(1)
                arr_range = match.group(2) or ''
                arr_type = match.group(3).strip()
                line_num = content[:match.start()].count('\n') + 1
                desc = f"Array {arr_name} = array[{arr_range}] of {arr_type}" if arr_range else f"Array {arr_name} = array of {arr_type}"
                _array_names.add(arr_name)
                items.append({
                    'type': 'AT',
                    'name': arr_name,
                    'line': line_num,
                    'base_class': None,
                    'description': desc
                })
            
            # 子界类型 (MF)
            subrange_pattern = r'\b([A-Z][a-zA-Z0-9]*)\s*=\s*(\d+)\.\.(\d+)\s*;'
            for match in re.finditer(subrange_pattern, content):
                sr_name = match.group(1)
                r_start = match.group(2)
                r_end = match.group(3)
                line_num = content[:match.start()].count('\n') + 1
                _subrange_names.add(sr_name)
                items.append({
                    'type': 'MF',
                    'name': sr_name,
                    'line': line_num,
                    'base_class': None,
                    'description': f"Subrange {sr_name} = {r_start}..{r_end}"
                })
            
            # 指针类型 (PT)
            pointer_pattern = r'\b(P[A-Z][a-zA-Z0-9]*)\s*=\s*\^([A-Z][a-zA-Z0-9]*)\s*;'
            for match in re.finditer(pointer_pattern, content):
                ptr_name = match.group(1)
                tgt_type = match.group(2)
                line_num = content[:match.start()].count('\n') + 1
                _pointer_names.add(ptr_name)
                items.append({
                    'type': 'PT',
                    'name': ptr_name,
                    'line': line_num,
                    'base_class': None,
                    'description': f"Pointer {ptr_name} = ^{tgt_type}"
                })
            
            # 匿名方法类型 (MM): reference to procedure/function
            anon_method_pattern = r'\b([A-Z][a-zA-Z0-9]*)\s*=\s*reference\s+to\s+(procedure|function)'
            for match in re.finditer(anon_method_pattern, content, re.IGNORECASE):
                m_name = match.group(1)
                m_kind = match.group(2).lower()
                line_num = content[:match.start()].count('\n') + 1
                _anon_method_names.add(m_name)
                items.append({
                    'type': 'MM',
                    'name': m_name,
                    'line': line_num,
                    'base_class': None,
                    'description': f"Anonymous Method {m_name} = reference to {m_kind}"
                })
            
            # 方法指针类型 (MM): procedure/function of object
            method_ptr_pattern = r'\b([A-Z][a-zA-Z0-9]*)\s*=\s*(procedure|function)\s*\([^)]*\)\s*of\s+object'
            for match in re.finditer(method_ptr_pattern, content, re.IGNORECASE):
                m_name = match.group(1)
                m_kind = match.group(2).lower()
                line_num = content[:match.start()].count('\n') + 1
                _anon_method_names.add(m_name)
                items.append({
                    'type': 'MM',
                    'name': m_name,
                    'line': line_num,
                    'base_class': None,
                    'description': f"Method Pointer {m_name} = {m_kind} of object"
                })
            
            # 过程/函数类型 (PT, 非 of object)
            proc_type_pattern = r'\b([A-Z][a-zA-Z0-9]*)\s*=\s*(procedure|function)\s*\('
            for match in re.finditer(proc_type_pattern, content, re.IGNORECASE):
                remaining = content[match.start():match.start()+200]
                if 'of object' not in remaining and 'reference to' not in remaining:
                    p_name = match.group(1)
                    p_kind = match.group(2).lower()
                    if p_name not in _anon_method_names:
                        line_num = content[:match.start()].count('\n') + 1
                        _pointer_names.add(p_name)
                        items.append({
                            'type': 'PT',
                            'name': p_name,
                            'line': line_num,
                            'base_class': None,
                            'description': f"Type {p_name} = {p_kind}"
                        })
            
            _override_names = _array_names | _pointer_names | _anon_method_names | _subrange_names
            
            for ent in entities:
                kind = ent['kind']
                name = ent['name']
                parent = ent.get('parent')
                line = ent['line']
                definition = ent.get('definition', '')
                
                # TY 被 AT/PT/MM/MF(subrange) 覆盖
                if kind == 'TY' and name in _override_names:
                    continue
                
                type_code = kind
                desc = definition
                if kind == 'TC':
                    desc = f"Class {name} inherits from {parent}" if parent else f"Class {name}"
                elif kind == 'TR':
                    desc = f"Record {name}"
                elif kind == 'TI':
                    desc = f"Interface {name} extends {parent}" if parent else f"Interface {name}"
                elif kind == 'TH':
                    desc = f"Helper {name} for {parent}" if parent else f"Helper {name}"
                elif kind == 'TE':
                    desc = f"Enum {name}"
                elif kind == 'TS':
                    desc = f"Set {name}"
                elif kind == 'FF':
                    desc = definition if definition else f"Function {name}"
                elif kind == 'FP':
                    desc = definition if definition else f"Procedure {name}"
                elif kind == 'CC':
                    desc = f"Const {name} = {definition}" if definition else f"Const {name}"
                elif kind == 'CR':
                    desc = f"ResourceString {name} = {definition}" if definition else f"ResourceString {name}"
                elif kind == 'TY':
                    desc = definition if definition else f"Type {name}"
                
                items.append({
                    'type': type_code,
                    'name': name,
                    'line': line,
                    'base_class': parent,
                    'description': desc
                })
            
            # ========== 补充提取类成员（属性、字段、事件） ==========
            
            # 属性定义（区分事件和普通属性）
            property_pattern = r'\bproperty\s+([A-Z][a-zA-Z0-9]*)\s*:\s*([^;=]+)'
            for match in re.finditer(property_pattern, content, re.IGNORECASE):
                prop_name = match.group(1)
                prop_type = match.group(2).strip()
                line_num = content[:match.start()].count('\n') + 1
                
                is_event = (
                    prop_name.startswith('On') or 
                    prop_name.startswith('Before') or 
                    prop_name.startswith('After') or
                    (prop_type.startswith('T') and (
                        'Event' in prop_type or
                        'Handler' in prop_type or
                        'Callback' in prop_type or
                        'Notify' in prop_type
                    ))
                )
                
                if is_event:
                    items.append({
                        'type': 'MP',
                        'name': prop_name,
                        'line': line_num,
                        'base_class': None,
                        'description': f"Event {prop_name}: {prop_type}"
                    })
                else:
                    items.append({
                        'type': 'TY',
                        'name': prop_name,
                        'line': line_num,
                        'base_class': None,
                        'description': f"Property {prop_name}: {prop_type}"
                    })
            
            # 类成员字段（以F开头，在type块内）
            field_pattern = r'\b(F[A-Z][a-zA-Z0-9]*)\s*:\s*([a-zA-Z][a-zA-Z0-9]*)\s*;'
            for match in re.finditer(field_pattern, content):
                field_name = match.group(1)
                field_type = match.group(2)
                line_num = content[:match.start()].count('\n') + 1
                
                before_content = content[:match.start()]
                type_keyword_pos = before_content.rfind('type')
                in_type_block = type_keyword_pos != -1
                
                var_keyword_pos = before_content.rfind('\nvar ')
                const_keyword_pos = before_content.rfind('\nconst ')
                res_keyword_pos = before_content.rfind('\nresourcestring ')
                in_var_block = var_keyword_pos != -1 and var_keyword_pos > type_keyword_pos if type_keyword_pos != -1 else var_keyword_pos != -1
                in_const_block = const_keyword_pos != -1 and const_keyword_pos > type_keyword_pos if type_keyword_pos != -1 else const_keyword_pos != -1
                in_res_block = res_keyword_pos != -1 and res_keyword_pos > type_keyword_pos if type_keyword_pos != -1 else res_keyword_pos != -1
                
                if in_type_block and not (in_var_block or in_const_block or in_res_block):
                    items.append({
                        'type': 'MF',
                        'name': field_name,
                        'line': line_num,
                        'base_class': None,
                        'description': f"Field {field_name}: {field_type}"
                    })
            
            # 全局变量（var块中，不以F开头）
            var_block_pattern = r'\bvar\s*\n((?:\s*[A-Z][a-zA-Z0-9]*(?:\s*,\s*[A-Z][a-zA-Z0-9]*)*\s*:\s*[^;]+;\s*\n)+)'
            for match in re.finditer(var_block_pattern, content, re.IGNORECASE):
                var_block = match.group(1)
                line_start = content[:match.start()].count('\n') + 1
                
                var_line_pattern = r'^\s*([A-Z][a-zA-Z0-9]*(?:\s*,\s*[A-Z][a-zA-Z0-9]*)*)\s*:\s*([^;]+)\s*;'
                for item_match in re.finditer(var_line_pattern, var_block, re.MULTILINE):
                    var_names = item_match.group(1)
                    var_type = item_match.group(2).strip()
                    line_num = line_start + var_block[:item_match.start()].count('\n')
                    
                    for var_name in var_names.split(','):
                        var_name = var_name.strip()
                        if not var_name.startswith('F'):
                            items.append({
                                'type': 'MF',
                                'name': var_name,
                                'line': line_num,
                                'base_class': None,
                                'description': f"Var {var_name}: {var_type}"
                            })
            
        except Exception as e:
            pass
        
        return (file_path_str, items)
    
    @staticmethod
    def _compute_vector_static(item: tuple, vocab: dict, idf_weights: dict) -> tuple:
        """静态方法：计算TF-IDF向量（用于多进程）"""
        import re
        from collections import Counter
        import struct
        
        item_id, description = item
        
        # 本地tokenize（避免pickle问题）
        def tokenize(text):
            text = re.sub(r'(?<!^)(?=[A-Z])', ' ', text)
            text = text.replace('_', ' ')
            words = re.findall(r'[a-z]+', text.lower())
            stop_words = {'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
                          'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                          'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                          'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                          'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                          'through', 'during', 'before', 'after', 'above', 'below',
                          'between', 'under', 'and', 'but', 'or', 'yet', 'so'}
            return [w for w in words if len(w) > 2 and w not in stop_words]
        
        words = tokenize(description)
        if not words:
            return (item_id, struct.pack('I', 0))
        
        word_freq = Counter(words)
        vector = {}
        for word, freq in word_freq.items():
            if word in vocab:
                tf = freq / len(words)
                idf = idf_weights.get(word, 1.0)
                vector[vocab[word]] = tf * idf
        
        # 打包为二进制格式
        if not vector:
            packed = struct.pack('I', 0)
        else:
            items_sorted = sorted(vector.items())
            count = len(items_sorted)
            packed = struct.pack('I', count)
            for word_id, weight in items_sorted:
                packed += struct.pack('If', word_id, weight)
        
        return (item_id, packed)
    
    def _parse_delphi_file(self, file_path: Path) -> List[Dict]:
        """解析Delphi源文件，提取类、函数等"""
        items = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 提取类定义
            class_pattern = r'(T[A-Z][a-zA-Z0-9]*)\s*=\s*class\s*\(([^)]+)\)'
            for match in re.finditer(class_pattern, content):
                class_name = match.group(1)
                base_class = match.group(2)
                # 找到类定义的行号
                line_num = content[:match.start()].count('\n') + 1
                
                items.append({
                    'type': 'TC',  # class
                    'name': class_name,
                    'line': line_num,
                    'base_class': base_class,
                    'description': f"Class {class_name} inherits from {base_class}"
                })
            
            # 提取函数/过程定义
            func_pattern = r'(procedure|function)\s+([A-Za-z][a-zA-Z0-9]*)\s*\('
            for match in re.finditer(func_pattern, content):
                func_type = match.group(1)  # procedure or function
                func_name = match.group(2)
                line_num = content[:match.start()].count('\n') + 1
                
                # 跳过构造函数、析构函数等特殊方法
                if func_name in ['Create', 'Destroy', 'AfterConstruction', 'BeforeDestruction']:
                    continue
                
                type_code = 'FP' if func_type == 'procedure' else 'FF'
                
                items.append({
                    'type': type_code,
                    'name': func_name,
                    'line': line_num,
                    'base_class': None,
                    'description': f"{func_type} {func_name}"
                })
            
        except Exception as e:
            print(f"  解析文件失败 {file_path}: {e}")
        
        return items
    
    def _rebuild_init(self, source_paths: List[Path], incremental: bool = False):
        """重建初始化阶段
        
        Args:
            source_paths: 源码路径列表
            incremental: 是否增量构建(跳过未变化的文件)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if incremental:
                cursor.execute("DELETE FROM vocabulary")
                cursor.execute("DELETE FROM build_queue")
                cursor.execute("DELETE FROM metadata")
                conn.commit()
                cursor.execute("SELECT id, full_path, hash FROM files")
                existing_files = {row[1]: (row[0], row[2]) for row in cursor.fetchall()}
                print(f"  增量模式: 数据库中已有 {len(existing_files)} 个文件记录")
            else:
                cursor.execute("DELETE FROM vocabularies")
                cursor.execute("DELETE FROM files")
                cursor.execute("DELETE FROM vocabulary")
                cursor.execute("DELETE FROM build_queue")
                cursor.execute("DELETE FROM metadata")
                conn.commit()
                existing_files = {}
            
            print("  扫描文件...")
            
            if self.progress_callback:
                self.progress_callback(0, "阶段1/2: 初始化...")
            
            files_data = []
            changed_file_ids = []
            skipped = 0
            updated = 0
            
            extensions = self.config['source'].get('extensions', ['.pas'])
            hash_mode = self.config.get('build', {}).get('incremental_hash_mode', 'mtime_size')
            
            total_files = 0
            for source_path in source_paths:
                if not source_path.exists():
                    print(f"  警告: 路径不存在 {source_path}")
                    continue
                
                category = source_path.name
                file_count = sum(1 for f in source_path.rglob('*') if f.is_file() and f.suffix in extensions)
                total_files += file_count
                
                for file_path in source_path.rglob('*'):
                    if file_path.is_file() and file_path.suffix in extensions:
                        try:
                            stat = file_path.stat()
                            rel_path = file_path.relative_to(source_path)
                            fp = str(file_path)
                            
                            if incremental and fp in existing_files:
                                old_id, old_hash = existing_files[fp]
                                if hash_mode == 'md5':
                                    file_hash = hashlib.md5(open(file_path, 'rb').read()).hexdigest()
                                else:
                                    file_hash = f"{stat.st_mtime}:{stat.st_size}"
                                if old_hash == file_hash:
                                    skipped += 1
                                    continue
                                else:
                                    cursor.execute("DELETE FROM vocabularies WHERE file_id = ?", (old_id,))
                                    cursor.execute("""UPDATE files SET size=?, hash=?, last_modified=?,
                                        updated_at=julianday('now') WHERE id=?""",
                                        (stat.st_size, file_hash, '', old_id))
                                    changed_file_ids.append((old_id, fp))
                                    updated += 1
                                    continue
                            
                            # 计算hash用于后续增量比较
                            if hash_mode == 'md5':
                                new_hash = hashlib.md5(open(file_path, 'rb').read()).hexdigest()
                            else:
                                new_hash = f"{stat.st_mtime}:{stat.st_size}"
                            
                            files_data.append((
                                fp,
                                str(rel_path),
                                file_path.suffix,
                                stat.st_size,
                                0,
                                new_hash,
                                '',
                                category,
                                '[]',
                                '[]',
                                str(file_path)
                            ))
                        except Exception as e:
                            pass
            
            if incremental:
                print(f"  增量模式: 跳过 {skipped} 个未变化文件, 更新 {updated} 个已修改文件, 新增 {len(files_data)} 个文件")
            else:
                print(f"  扫描到 {len(files_data)} 个文件")
            
            if self.progress_callback:
                self.progress_callback(15, f"扫描完成: {len(files_data) + len(changed_file_ids)} 个文件需处理，开始解析...")
            
            # 插入新文件到files表
            if files_data:
                cursor.executemany("""
                    INSERT OR IGNORE INTO files (full_path, relative_path, extension, size,
                                      line_count, hash, last_modified, category,
                                      units_defined, units_imported, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, files_data)
            
            # 收集需要解析的文件路径
            all_files_to_parse = [f[0] for f in files_data]
            all_files_to_parse.extend(fp for _, fp in changed_file_ids)
            
            if not all_files_to_parse:
                if incremental:
                    print("  增量模式: 所有文件均未变化，无需更新")
                    conn.commit()
                    return
            
            # 获取文件路径到ID的映射
            cursor.execute("SELECT id, full_path FROM files")
            file_path_to_id = {row[1]: row[0] for row in cursor.fetchall()}
            
            # 解析文件
            print("  并行解析文件...")
            
            if self.progress_callback:
                self.progress_callback(10, "阶段1/2: 解析文件...")
            
            n_workers = max(2, cpu_count() - 1)
            file_chunksize = max(500, len(all_files_to_parse) // n_workers)
            
            print(f"  使用 {n_workers} 进程并行解析 (chunksize={file_chunksize})...")
            
            with ProcessPoolExecutor(max_workers=n_workers) as executor:
                parsed_results = list(executor.map(
                    self._parse_delphi_file_static,
                    all_files_to_parse,
                    chunksize=file_chunksize
                ))
            
            if self.progress_callback:
                self.progress_callback(55, f"解析完成: {len(all_files_to_parse)} 个文件，正在入库...")
            
            # 合并解析结果
            items_data = []
            for file_path_str, parsed_items in parsed_results:
                file_id = file_path_to_id.get(file_path_str, 0)
                if file_id == 0:
                    continue
                file_path = Path(file_path_str)
                
                for item in parsed_items:
                    items_data.append((
                        item['type'],
                        item['name'],
                        item['name'].lower(),
                        file_id,
                        item['line'],
                        item.get('base_class'),
                        item['description'],
                        'pending'
                    ))
                
                unit_name = file_path.stem
                items_data.append((
                    'UI',
                    unit_name,
                    unit_name.lower(),
                    file_id,
                    0,
                    None,
                    f"Unit {unit_name}",
                    'pending'
                ))
            
            print(f"  提取到 {len(items_data)} 个词汇项目")
            
            if items_data:
                cursor.executemany("""
                    INSERT OR IGNORE INTO vocabularies (type, name, name_lower, file_id, line,
                                             base_class, description, vector_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, items_data)
            
            print("  构建词汇表...")
            
            if self.progress_callback:
                self.progress_callback(70, "阶段1/2: 构建词汇表...")
            
            self._build_vocabulary_table(cursor, items_data)
            
            if self.progress_callback:
                self.progress_callback(91, "阶段1/2: 完成，准备启动向量构建...")
            
            cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('build_status', 'pending')")
            cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('build_progress', '0')")
            cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('total_files', ?)", (str(total_files),))
            cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('total_items', ?)", (str(len(items_data)),))
            # 记录 schema 版本号
            from src.services.knowledge_base import set_schema_version_in_db
            set_schema_version_in_db(cursor)
            
            conn.commit()
            
            print(f"  初始化完成：{len(all_files_to_parse)}个文件需处理，{len(items_data)}个项目")
        finally:
            conn.close()
    
    def _build_vocabulary_table(self, cursor, items_data: List):
        """构建词汇表"""
        # 收集所有文档
        documents = []
        for item in items_data:
            if item[6]:  # description
                documents.append(item[6])
        
        if not documents:
            return
        
        # 统计词频
        doc_freq: Dict[str, int] = {}
        for doc in documents:
            words = set(self.tokenize(doc))
            for word in words:
                doc_freq[word] = doc_freq.get(word, 0) + 1
        
        # 计算IDF
        doc_count = len(documents)
        vocab_data = []
        
        for i, (word, freq) in enumerate(sorted(doc_freq.items())):
            idf = math.log(doc_count / (freq + 1)) + 1
            vocab_data.append((i, word, idf, freq))
            self.vocabulary[word] = i
            self.idf_weights[word] = idf
        
        # 插入vocabulary表
        if vocab_data:
            cursor.executemany("""
                INSERT OR REPLACE INTO vocabulary (id, word, idf_weight, document_frequency)
                VALUES (?, ?, ?, ?)
            """, vocab_data)
        
        print(f"  词汇表大小: {len(vocab_data)}")
    
    def _start_async_build(self, progress_callback: callable = None):
        """启动异步构建线程"""
        self._building = True
        
        # 更新状态
        conn = self._get_connection()
        conn.execute("UPDATE metadata SET value='building' WHERE key='build_status'")
        conn.commit()
        conn.close()
        
        # 启动构建线程，传递进度回调
        self._build_thread = threading.Thread(
            target=self._async_build_worker, 
            daemon=True,
            args=(progress_callback,)
        )
        self._build_thread.start()
    
    def _async_build_worker(self, progress_callback: callable = None):
        """异步构建工作线程（使用多进程并行计算向量）"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 获取待构建项目总数
            cursor.execute("SELECT COUNT(*) FROM vocabularies WHERE vector_status='pending'")
            total = cursor.fetchone()[0]
            
            if total == 0:
                print("  没有需要构建的项目")
                return
            
            print(f"  开始构建向量，共{total}个项目...")
            
            # 动态计算worker数和chunksize
            parallel_workers_config = self.config.get('build', {}).get('parallel_workers')
            if parallel_workers_config:
                n_workers = max(1, parallel_workers_config)
            else:
                n_workers = max(2, cpu_count() - 1)
            batch_size = self.config.get('build', {}).get('batch_size', 1000)
            vector_chunksize = max(500, batch_size // n_workers)
            
            print(f"  使用 {n_workers} 进程并行计算向量 (chunksize={vector_chunksize})...")
            
            processed = 0
            vocab = self.vocabulary
            idf_weights = self.idf_weights
            
            # 报告向量构建开始（映射到90-100%范围）
            if progress_callback:
                progress_callback(92, f"阶段2/2: 开始构建向量...")
            
            # 使用多进程并行计算向量
            from functools import partial
            
            while self._building:
                # 获取一批待构建项目
                cursor.execute("""
                    SELECT id, description
                    FROM vocabularies
                    WHERE vector_status='pending'
                    LIMIT ?
                """, (batch_size,))
                
                items = cursor.fetchall()
                if not items:
                    break
                
                # 准备计算任务
                compute_items = [(row['id'], row['description']) for row in items]
                
                # 使用partial传递词汇表和IDF权重
                compute_func = partial(
                    SmartCacheKnowledgeBase._compute_vector_static,
                    vocab=vocab,
                    idf_weights=idf_weights
                )
                
                # 并行计算向量
                with ProcessPoolExecutor(max_workers=n_workers) as executor:
                    results = list(executor.map(
                        compute_func,
                        compute_items,
                        chunksize=vector_chunksize
                    ))
                
                # 更新数据库
                for item_id, packed_vector in results:
                    cursor.execute("""
                        UPDATE vocabularies
                        SET vector=?, vector_status='built', updated_at=julianday('now')
                        WHERE id=?
                    """, (packed_vector, item_id))
                    processed += 1
                
# 更新进度（映射到92-100%范围）
                progress = int(92 + (processed / total * 8))
                cursor.execute("UPDATE metadata SET value=? WHERE key='build_progress'", (str(progress),))
                conn.commit()
                
                # 调用进度回调（向任务管理器报告进度，每批次更新）
                if progress_callback:
                    progress_callback(progress, f"构建向量中：{processed}/{total}")
                
                if processed % 1000 == 0 or processed == total:
                    print(f"  构建进度：{processed}/{total} ({progress}%)")
            
            # 完成
            cursor.execute("UPDATE metadata SET value='completed' WHERE key='build_status'")
            cursor.execute("UPDATE metadata SET value='100' WHERE key='build_progress'")
            conn.commit()
            
            print(f"  向量构建完成：{processed}/{total}")
            
        except Exception as e:
            print(f"  构建错误: {e}")
            cursor.execute("UPDATE metadata SET value='failed' WHERE key='build_status'")
            conn.commit()
        finally:
            self._building = False
            conn.close()
    
    def semantic_search(self, query: str, top_k: int = 10,
                       item_types: List[str] = None) -> List[Dict]:
        """语义搜索（智能缓存）"""
        # 计算查询向量
        query_vector = self.text_to_vector(query)
        
        if not query_vector:
            return []
        
        # 快速筛选候选集
        candidates = self._get_candidates(query, item_types)
        
        results = []
        conn = self._get_connection()
        cursor = conn.cursor()
        
        for item in candidates:
            # 获取向量（缓存或构建）
            vector = self._get_or_build_vector(cursor, item['id'], item['description'])
            
            if vector:
                # 计算相似度
                similarity = self._cosine_similarity(query_vector, vector)
                if similarity > 0.1:
                    results.append({
                        'id': item['id'],
                        'name': item['name'],
                        'type': item['type'],
                        'type_name': self.TYPE_MAP.get(item['type'], 'unknown'),
                        'file_id': item['file_id'],
                        'description': item['description'],
                        'similarity': similarity
                    })
        
        conn.close()
        
        # 排序返回
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]
    
    def _get_candidates(self, query: str, item_types: List[str] = None) -> List[Dict]:
        """快速筛选候选集"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query_lower = query.lower()
        
        if item_types:
            type_placeholders = ','.join(['?' for _ in item_types])
            cursor.execute(f"""
                SELECT id, type, name, description, file_id
                FROM vocabularies
                WHERE name_lower LIKE ?
                  AND type IN ({type_placeholders})
                LIMIT 1000
            """, (f'%{query_lower}%',) + tuple(item_types))
        else:
            cursor.execute("""
                SELECT id, type, name, description, file_id
                FROM vocabularies
                WHERE name_lower LIKE ?
                LIMIT 1000
            """, (f'%{query_lower}%',))
        
        candidates = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return candidates
    
    def _get_or_build_vector(self, cursor, item_id: int, description: str) -> Optional[Dict]:
        """获取或构建向量（带缓存）"""
        # 检查缓存
        cached = self._vector_cache.get(item_id)
        if cached is not None:
            return cached
        
        # 从数据库获取
        cursor.execute("""
            SELECT vector, vector_status FROM vocabularies WHERE id=?
        """, (item_id,))
        
        row = cursor.fetchone()
        if row and row['vector']:
            # 解包向量
            vector = self._unpack_vector(row['vector'])
            self._vector_cache.set(item_id, vector)
            return vector
        
        # 实时构建
        vector = self.text_to_vector(description)
        
        # 缓存
        self._vector_cache.set(item_id, vector)
        
        return vector
    
    def get_build_status(self) -> Dict:
        """获取构建状态"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT key, value FROM metadata")
        metadata = {row['key']: row['value'] for row in cursor.fetchall()}
        
        conn.close()
        
        return {
            'status': metadata.get('build_status', 'unknown'),
            'progress': int(metadata.get('build_progress', '0')),
            'total_files': int(metadata.get('total_files', '0')),
            'total_items': int(metadata.get('total_items', '0'))
        }
    
    def stop_build(self):
        """停止构建"""
        self._building = False
        if self._build_thread:
            self._build_thread.join(timeout=5)
        
        conn = self._get_connection()
        conn.execute("UPDATE metadata SET value='stopped' WHERE key='build_status'")
        conn.commit()
        conn.close()
    
    def search_by_name(self, name: str) -> List[Dict]:
        """按名称搜索 (返回所有类型)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        name_lower = name.lower()
        
        cursor.execute("""
            SELECT v.*, f.relative_path, f.category
            FROM vocabularies v
            LEFT JOIN files f ON v.file_id = f.id
            WHERE v.name_lower = ?
        """, (name_lower,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row['id'],
                'name': row['name'],
                'type': row['type'],
                'type_name': self.TYPE_MAP.get(row['type'], 'unknown'),
                'file_id': row['file_id'],
                'line': row['line'],
                'base_class': row['base_class'],
                'description': row['description'],
                'relative_path': row['relative_path'],
                'category': row['category']
            })
        
        conn.close()
        return results
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # 文件数
        cursor.execute("SELECT COUNT(*) FROM files")
        stats['total_files'] = cursor.fetchone()[0]
        
        # 项目数
        cursor.execute("SELECT COUNT(*) FROM vocabularies")
        stats['total_items'] = cursor.fetchone()[0]
        
        # 各类型数量
        cursor.execute("SELECT type, COUNT(*) as count FROM vocabularies GROUP BY type")
        stats['by_type'] = {row['type']: row['count'] for row in cursor.fetchall()}
        
        # 向量构建状态
        cursor.execute("SELECT vector_status, COUNT(*) as count FROM vocabularies GROUP BY vector_status")
        stats['vector_status'] = {row['vector_status']: row['count'] for row in cursor.fetchall()}
        
        # 词汇表大小
        cursor.execute("SELECT COUNT(*) FROM vocabulary")
        stats['vocabulary_size'] = cursor.fetchone()[0]
        
        # 缓存大小
        stats['cache_size'] = len(self._vector_cache)
        
        conn.close()
        return stats
