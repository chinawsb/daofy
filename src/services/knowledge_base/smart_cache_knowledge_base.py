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
    
    # 类型编码映射
    TYPE_MAP = {
        'c': 'class',
        'e': 'enum',
        'r': 'record',
        'i': 'interface',
        's': 'const',
        'f': 'function',
        'p': 'procedure',
        'u': 'unit',
        'k': 'keyword',
        't': 'type'
    }
    TYPE_REVERSE_MAP = {v: k for k, v in TYPE_MAP.items()}
    
    def __init__(self, kb_dir: str, config: Dict = None):
        self.kb_dir = Path(kb_dir)
        self.config = config or self._load_config()
        
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
    
    def rebuild_async(self):
        """异步重建知识库"""
        if self._building:
            print("构建已在进行中...")
            return
        
        # 获取源码路径
        source_paths = self.path_resolver.get_source_paths()
        print(f"源码路径: {[str(p) for p in source_paths]}")
        
        # 阶段1：初始化（同步）
        print("\n阶段1：初始化...")
        self._rebuild_init(source_paths)
        
        # 阶段2：启动异步构建
        print("\n阶段2：启动异步向量构建...")
        self._start_async_build()
        
        print("\n知识库已可用，向量正在后台构建中...")
    
    @staticmethod
    def _parse_delphi_file_static(file_path_str: str) -> Tuple[str, List[Dict]]:
        """静态方法：解析Delphi源文件（用于多进程）"""
        import re
        from pathlib import Path
        
        file_path = Path(file_path_str)
        items = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 提取类定义
            class_pattern = r'(T[A-Z][a-zA-Z0-9]*)\s*=\s*class\s*\(([^)]+)\)'
            for match in re.finditer(class_pattern, content):
                class_name = match.group(1)
                base_class = match.group(2)
                line_num = content[:match.start()].count('\n') + 1
                
                items.append({
                    'type': 'c',
                    'name': class_name,
                    'line': line_num,
                    'base_class': base_class,
                    'description': f"Class {class_name} inherits from {base_class}"
                })
            
            # 提取函数/过程定义
            func_pattern = r'(procedure|function)\s+([A-Za-z][a-zA-Z0-9]*)\s*\('
            for match in re.finditer(func_pattern, content):
                func_type = match.group(1)
                func_name = match.group(2)
                line_num = content[:match.start()].count('\n') + 1
                
                if func_name in ['Create', 'Destroy', 'AfterConstruction', 'BeforeDestruction']:
                    continue
                
                type_code = 'p' if func_type == 'procedure' else 'f'
                
                items.append({
                    'type': type_code,
                    'name': func_name,
                    'line': line_num,
                    'base_class': None,
                    'description': f"{func_type} {func_name}"
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
                    'type': 'c',  # class
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
                
                type_code = 'p' if func_type == 'procedure' else 'f'
                
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
    
    def _rebuild_init(self, source_paths: List[Path]):
        """重建初始化阶段"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 清空表
        cursor.execute("DELETE FROM vocabularies")
        cursor.execute("DELETE FROM files")
        cursor.execute("DELETE FROM vocabulary")
        cursor.execute("DELETE FROM build_queue")
        cursor.execute("DELETE FROM metadata")
        conn.commit()
        
        # 扫描文件
        print("  扫描文件...")
        files_data = []
        items_data = []
        
        extensions = self.config['source'].get('extensions', ['.pas'])
        
        for source_path in source_paths:
            if not source_path.exists():
                print(f"  警告: 路径不存在 {source_path}")
                continue
            
            category = source_path.name
            
            for file_path in source_path.rglob('*'):
                if file_path.is_file() and file_path.suffix in extensions:
                    try:
                        stat = file_path.stat()
                        rel_path = file_path.relative_to(source_path)
                        
                        files_data.append((
                            str(file_path),
                            str(rel_path),
                            file_path.suffix,
                            stat.st_size,
                            0,  # line_count
                            '',  # hash
                            '',  # last_modified
                            category,
                            '[]',  # units_defined
                            '[]',  # units_imported
                            str(file_path)
                        ))
                    except Exception as e:
                        pass
        
        print(f"  扫描到 {len(files_data)} 个文件")
        
        # 插入files表
        if files_data:
            cursor.executemany("""
                INSERT INTO files (full_path, relative_path, extension, size,
                                  line_count, hash, last_modified, category,
                                  units_defined, units_imported, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, files_data)
            
            # 解析文件，提取类、函数等（使用多进程并行）
            print("  并行解析文件...")
            
            # 动态计算worker数和chunksize（参考已有实现）
            n_workers = max(2, min(8, cpu_count() - 1))
            file_chunksize = max(500, len(files_data) // n_workers)
            
            print(f"  使用 {n_workers} 进程并行解析 (chunksize={file_chunksize})...")
            
            # 准备文件路径列表
            file_paths = [file_data[0] for file_data in files_data]
            
            # 使用多进程并行解析
            with ProcessPoolExecutor(max_workers=n_workers) as executor:
                parsed_results = list(executor.map(
                    self._parse_delphi_file_static,
                    file_paths,
                    chunksize=file_chunksize
                ))
            
            # 合并解析结果
            for i, (file_data, (file_path_str, parsed_items)) in enumerate(zip(files_data, parsed_results)):
                file_id = i + 1
                file_path = Path(file_data[0])
                
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
                
                # 添加unit类型
                unit_name = file_path.stem
                items_data.append((
                    'u',  # type: unit
                    unit_name,
                    unit_name.lower(),
                    file_id,
                    0,  # line
                    None,  # base_class
                    f"Unit {unit_name} in {file_data[1]}",
                    'pending'
                ))
        
        print(f"  提取到 {len(items_data)} 个词汇项目")
        
        # 插入vocabularies表
        if items_data:
            cursor.executemany("""
                INSERT INTO vocabularies (type, name, name_lower, file_id, line,
                                         base_class, description, vector_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, items_data)
        
        # 构建词汇表
        print("  构建词汇表...")
        self._build_vocabulary_table(cursor, items_data)
        
        # 更新元数据
        cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('build_status', 'pending')")
        cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('build_progress', '0')")
        cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('total_files', ?)", (str(len(files_data)),))
        cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('total_items', ?)", (str(len(items_data)),))
        
        conn.commit()
        conn.close()
        
        print(f"  初始化完成：{len(files_data)}个文件，{len(items_data)}个项目")
    
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
                INSERT INTO vocabulary (id, word, idf_weight, document_frequency)
                VALUES (?, ?, ?, ?)
            """, vocab_data)
        
        print(f"  词汇表大小: {len(vocab_data)}")
    
    def _start_async_build(self):
        """启动异步构建线程"""
        self._building = True
        
        # 更新状态
        conn = self._get_connection()
        conn.execute("UPDATE metadata SET value='building' WHERE key='build_status'")
        conn.commit()
        conn.close()
        
        # 启动构建线程
        self._build_thread = threading.Thread(target=self._async_build_worker, daemon=True)
        self._build_thread.start()
    
    def _async_build_worker(self):
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
            n_workers = max(2, min(8, cpu_count() - 1))
            batch_size = self.config['build'].get('batch_size', 1000)
            vector_chunksize = max(500, batch_size // n_workers)
            
            print(f"  使用 {n_workers} 进程并行计算向量 (chunksize={vector_chunksize})...")
            
            processed = 0
            vocab = self.vocabulary
            idf_weights = self.idf_weights
            
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
                
                # 更新进度
                progress = int(processed / total * 100)
                cursor.execute("UPDATE metadata SET value=? WHERE key='build_progress'", (str(progress),))
                conn.commit()
                
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
    
    def search_by_name(self, name: str, item_types: List[str] = None) -> List[Dict]:
        """按名称搜索"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        name_lower = name.lower()
        
        if item_types:
            type_placeholders = ','.join(['?' for _ in item_types])
            cursor.execute(f"""
                SELECT v.*, f.relative_path, f.category
                FROM vocabularies v
                LEFT JOIN files f ON v.file_id = f.id
                WHERE v.name_lower = ?
                  AND v.type IN ({type_placeholders})
            """, (name_lower,) + tuple(item_types))
        else:
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


def main():
    """测试入口"""
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python smart_cache_knowledge_base.py <知识库目录> [命令]")
        print("命令: rebuild | search <查询> | status | stats")
        return
    
    kb_dir = sys.argv[1]
    command = sys.argv[2] if len(sys.argv) > 2 else 'status'
    
    kb = SmartCacheKnowledgeBase(kb_dir)
    
    if command == 'rebuild':
        kb.rebuild_async()
        # 等待构建完成
        while True:
            status = kb.get_build_status()
            print(f"状态: {status['status']}, 进度: {status['progress']}%")
            if status['status'] in ['completed', 'failed', 'stopped']:
                break
            time.sleep(2)
    
    elif command == 'search':
        query = sys.argv[3] if len(sys.argv) > 3 else 'button'
        results = kb.semantic_search(query, top_k=10)
        print(f"\n搜索 '{query}' 的结果:")
        for i, r in enumerate(results, 1):
            print(f"{i}. {r['name']} ({r['type_name']}) - 相似度: {r['similarity']:.3f}")
            print(f"   描述: {r['description'][:80]}...")
    
    elif command == 'status':
        status = kb.get_build_status()
        print(f"构建状态: {status}")
    
    elif command == 'stats':
        stats = kb.get_statistics()
        print(f"统计信息: {json.dumps(stats, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
