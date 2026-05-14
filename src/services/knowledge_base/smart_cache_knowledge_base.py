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
import re
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count


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
            logger.info(f"创建缓存目录: {files_dir}")
        
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
        'KS': 'string literal',
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
        
        # 源码路径解析器
        self.path_resolver = SourcePathResolver(self.kb_dir, self.config)
        
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
    
    def _get_connection(self, use_wal: bool = False) -> sqlite3.Connection:
        """获取数据库连接
        
        Args:
            use_wal: 是否使用WAL模式（构建时用WAL获得更好写入性能，查询时用DELETE避免.wal文件残留）
        """
        from .schema import get_connection
        conn = get_connection(str(self.db_path), use_wal=use_wal)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_database(self):
        """初始化数据库——使用统一 schema（使用 WAL 模式避免与已有连接冲突）"""
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        
        conn = self._get_connection(use_wal=True)
        cursor = conn.cursor()
        
        # 检测旧 schema：files 表无 relative_path 列视为超旧版，重建
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(files)")
            files_cols = {row[1] for row in cursor.fetchall()}
            if 'relative_path' not in files_cols:
                from .schema import drop_source_tables
                drop_source_tables(cursor)
        
        # 使用统一 schema
        from .schema import create_source_tables
        create_source_tables(cursor)
        
        conn.commit()
        conn.close()
    
    def rebuild_async(self, incremental: bool = False, source_paths: Optional[List[str]] = None):
        """同步重建知识库（TF-IDF 已废弃，仅执行实体扫描入库）"""
        if source_paths is not None:
            from pathlib import Path
            resolved_paths = [Path(p) for p in source_paths]
        else:
            resolved_paths = self.path_resolver.get_source_paths()
        logger.info(f"源码路径: {[str(p) for p in resolved_paths]}")
        
        import time
        _start = time.time()
        logger.info("阶段1：初始化...")
        self._rebuild_init(resolved_paths, incremental=incremental, build_start_time=_start)
        
        logger.info("知识库构建完成")
    
    @staticmethod
    def _parse_delphi_file_static(file_path_str: str) -> Tuple[str, List[Dict], int, List[str]]:
        """静态方法：解析Delphi源文件（用于多进程）
        
        Returns:
            (file_path_str, items, line_count, uses_list)
        """
        import re
        from pathlib import Path
        from src.services.knowledge_base.scan_delphi_sources import _extract_all_entities, _extract_uses
        
        file_path = Path(file_path_str)
        items = []
        line_count = 0
        uses_list = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            line_count = content.count('\n') + 1
            uses_list = _extract_uses(content)
            
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
        
        return (file_path_str, items, line_count, uses_list)
    

    
    def _rebuild_init(self, source_paths: List[Path], incremental: bool = False, build_start_time: float = None):
        """重建初始化阶段
        
        Args:
            source_paths: 源码路径列表
            incremental: 是否增量构建(跳过未变化的文件)
            build_start_time: time.time() 起始时间，用于计算构建耗时
        """
        conn = self._get_connection(use_wal=True)  # 构建时用WAL，提升写入性能
        cursor = conn.cursor()
        
        try:
            if incremental:
                cursor.execute("DELETE FROM metadata")
                conn.commit()
                cursor.execute("SELECT id, full_path, hash FROM files")
                existing_files = {row[1]: (row[0], row[2]) for row in cursor.fetchall()}
                logger.info(f"  增量模式: 数据库中已有 {len(existing_files)} 个文件记录")
            else:
                cursor.execute("DELETE FROM vocabularies")
                cursor.execute("DELETE FROM files")
                cursor.execute("DELETE FROM metadata")
                conn.commit()
                existing_files = {}
            
            logger.info("  扫描文件...")
            
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
                    logger.warning(f"  路径不存在 {source_path}")
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
                                        (stat.st_size, file_hash, str(stat.st_mtime), old_id))
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
                                0,  # 行数在解析后回填
                                new_hash,
                                str(stat.st_mtime),  # 实际修改时间
                                category,
                                '[]',  # units_defined 在解析后回填
                                '[]',  # units_imported 在解析后回填
                                ''
                            ))
                        except Exception as e:
                            pass
            
            if incremental:
                logger.info(f"  增量模式: 跳过 {skipped} 个未变化文件, 更新 {updated} 个已修改文件, 新增 {len(files_data)} 个文件")
            else:
                logger.info(f"  扫描到 {len(files_data)} 个文件")
            
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
                    logger.info("  增量模式: 所有文件均未变化，无需更新")
                    conn.commit()
                    return
            
            # 获取文件路径到ID的映射
            cursor.execute("SELECT id, full_path FROM files")
            file_path_to_id = {row[1]: row[0] for row in cursor.fetchall()}
            
            # 解析文件
            logger.info("  并行解析文件...")
            
            if self.progress_callback:
                self.progress_callback(10, "阶段1/2: 解析文件...")
            
            n_workers = max(2, cpu_count() - 1)
            file_chunksize = max(500, len(all_files_to_parse) // n_workers)
            
            logger.info(f"  使用 {n_workers} 进程并行解析 (chunksize={file_chunksize})...")
            
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
            file_updates = {}  # (file_id, line_count, [unit_names], [uses])
            for file_path_str, parsed_items, line_count, uses_list in parsed_results:
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
                
                # 收集回填数据
                file_updates[file_id] = (line_count, [unit_name], uses_list)
            
            logger.info(f"  提取到 {len(items_data)} 个词汇项目")
            
            if items_data:
                cursor.executemany("""
                    INSERT OR IGNORE INTO vocabularies (type, name, name_lower, file_id, line,
                                             base_class, description, vector_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, items_data)
            
            # 回填 files 表的 line_count、units_defined、units_imported
            for fid, (line_cnt, unit_names, uses_list) in file_updates.items():
                cursor.execute(
                    "UPDATE files SET line_count=?, units_defined=?, units_imported=? WHERE id=?",
                    (line_cnt,
                     json.dumps(unit_names, ensure_ascii=False),
                     json.dumps(uses_list, ensure_ascii=False) if uses_list else '[]',
                     fid)
                )
            
            logger.info("  实体入库完成")
            cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('total_files', ?)", (str(total_files),))
            cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('total_items', ?)", (str(len(items_data)),))
            cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_build_time', ?)",
                (datetime.now().isoformat(),))
            if build_start_time:
                import time
                duration = int(time.time() - build_start_time)
                cursor.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_build_duration', ?)",
                    (str(duration),))
            # 记录 schema 版本号
            from src.services.knowledge_base import set_schema_version_in_db
            set_schema_version_in_db(cursor)
            
            conn.commit()
            
            # 保持 WAL 模式（不切 DELETE），避免与已有连接冲突
            
            logger.info(f"  初始化完成：{len(all_files_to_parse)}个文件需处理，{len(items_data)}个项目")
        finally:
            conn.close()
    
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
    
    def search_by_name(self, name: str) -> List[Dict]:
        """按名称搜索 (返回所有类型)，也搜索 description（支持 DF 属性值）"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        name_lower = name.lower()
        # 转义 LIKE 通配符
        escaped = name_lower.replace('%', '\\%').replace('_', '\\_')
        
        # 精确匹配 name_lower + 查询 description 中匹配的 DF/KS 项
        cursor.execute("""
            SELECT v.*, f.relative_path, f.category
            FROM vocabularies v
            LEFT JOIN files f ON v.file_id = f.id
            WHERE v.name_lower = ?
               OR (v.type IN ('DF', 'KS') AND v.description IS NOT NULL AND v.description != ''
                   AND v.description LIKE '%' || ? || '%' ESCAPE '\\')
        """, (name_lower, escaped))
        
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
        
        # 词汇表大小（TF-IDF 已废弃）
        stats['vocabulary_size'] = 0
        
        # 末次构建信息
        cursor.execute("SELECT value FROM metadata WHERE key='last_build_time'")
        row = cursor.fetchone()
        stats['last_build_time'] = row['value'] if row else None
        cursor.execute("SELECT value FROM metadata WHERE key='last_build_duration'")
        row = cursor.fetchone()
        stats['last_build_duration'] = int(row['value']) if row else None
        
        conn.close()
        return stats
