#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Delphi 源码知识库扫描器
扫描 Delphi 官方源码目录,建立索引供 CodeArts 使用
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Optional, Callable
from multiprocessing import cpu_count
import re
import time

try:
    from ...utils.progress_tracker import ProgressTracker, ProgressInfo
except ImportError:
    # 如果相对导入失败，使用绝对导入
    from src.utils.progress_tracker import ProgressTracker, ProgressInfo


def _analyze_file_worker(args: tuple) -> Optional[Dict]:
    """
    分析单个文件的工作函数（用于多进程）
    
    Args:
        args: (file_path_str, source_dir_str)
        
    Returns:
        文件信息字典或None
    """
    file_path_str, source_dir_str = args
    file_path = Path(file_path_str)
    source_dir = Path(source_dir_str)
    
    try:
        # 计算文件哈希
        md5_hash = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                md5_hash.update(chunk)
        file_hash = md5_hash.hexdigest()
        
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            lines = content.split('\n')
            line_count = len(lines)
        
        # 相对路径
        rel_path = file_path.relative_to(source_dir)
        
        # 提取文件信息
        file_info = {
            'path': str(rel_path).replace('\\', '/'),
            'full_path': str(file_path),
            'extension': file_path.suffix.lower(),
            'size': file_path.stat().st_size,
            'line_count': line_count,
            'hash': file_hash,
            'last_modified': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
            'units': _extract_units(content),
            'uses': _extract_uses(content),
            'classes': _extract_classes(content),
            'functions': _extract_functions(content),
            'constants': _extract_constants(content),
            'types': _extract_types(content)
        }
        
        return file_info
        
    except Exception as e:
        print(f"分析文件失败 {file_path}: {e}")
        return None


def _extract_units(content: str) -> List[str]:
    """提取 unit 名称"""
    pattern = r'^\s*unit\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*;'
    matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
    return matches


def _extract_uses(content: str) -> List[str]:
    """提取 uses 子句中的单元"""
    pattern = r'^\s*uses\s+([^;]+);'
    matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
    units = []
    for match in matches:
        items = [item.strip() for item in match.split(',')]
        units.extend(items)
    return units


def _extract_classes(content: str) -> List[Dict]:
    """提取类定义"""
    classes = []
    
    # 1. 匹配 class 类型
    class_pattern = r'^\s*(T[a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*class\s*(?:\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\))?\s*(?:sealed|abstract)?'
    matches = re.finditer(class_pattern, content, re.MULTILINE | re.IGNORECASE)
    
    for match in matches:
        class_name = match.group(1)
        base_class = match.group(2) if match.group(2) else 'TObject'
        line_num = content[:match.start()].count('\n') + 1
        classes.append({
            'name': class_name,
            'base_class': base_class,
            'line': line_num,
            'type_kind': 'class'
        })
    
    # 2. 匹配 record 类型
    record_pattern = r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*record\s*(?:\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\))?'
    matches = re.finditer(record_pattern, content, re.MULTILINE | re.IGNORECASE)
    
    for match in matches:
        record_name = match.group(1)
        base_record = match.group(2) if match.group(2) else None
        line_num = content[:match.start()].count('\n') + 1
        classes.append({
            'name': record_name,
            'base_class': base_record,
            'line': line_num,
            'type_kind': 'record'
        })
    
    # 3. 匹配 interface 类型
    interface_pattern = r'^\s*(I[a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*interface\s*(?:\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\))?'
    matches = re.finditer(interface_pattern, content, re.MULTILINE | re.IGNORECASE)
    
    for match in matches:
        interface_name = match.group(1)
        base_interface = match.group(2) if match.group(2) else None
        line_num = content[:match.start()].count('\n') + 1
        classes.append({
            'name': interface_name,
            'base_class': base_interface,
            'line': line_num,
            'type_kind': 'interface'
        })
    
    return classes


def _extract_functions(content: str) -> List[Dict]:
    """提取函数和过程"""
    functions = []
    
    # 匹配 function/procedure
    patterns = [
        (r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*:\s*([^\s;]+)', 'function'),
        (r'^\s*procedure\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)', 'procedure'),
        (r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([^\s;]+)', 'function'),
        (r'^\s*procedure\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'procedure'),
    ]
    
    for pattern, func_type in patterns:
        matches = re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE)
        for match in matches:
            func_name = match.group(1)
            return_type = match.group(2) if match.lastindex and match.lastindex >= 2 else ''
            line_num = content[:match.start()].count('\n') + 1
            
            functions.append({
                'name': func_name,
                'return_type': return_type,
                'kind': func_type,
                'line': line_num
            })
    
    return functions


def _extract_constants(content: str) -> List[Dict]:
    """提取常量定义"""
    constants = []
    
    pattern = r'^\s*(const|resourcestring)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([^\n;]+)'
    matches = re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE)
    
    for match in matches:
        const_name = match.group(2)
        const_value = match.group(3).strip()
        line_num = content[:match.start()].count('\n') + 1
        
        constants.append({
            'name': const_name,
            'value': const_value,
            'line': line_num
        })
    
    return constants


def _extract_types(content: str) -> List[Dict]:
    """提取类型定义"""
    types = []
    
    # 匹配 type 块中的类型定义
    patterns = [
        r'^\s*type\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.*?)(?:;|$)',
        r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(array|record|set|file|class|interface)\b',
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE)
        for match in matches:
            type_name = match.group(1)
            type_def = match.group(2) if match.lastindex >= 2 else ''
            line_num = content[:match.start()].count('\n') + 1
            
            types.append({
                'name': type_name,
                'definition': type_def,
                'line': line_num
            })
    
    return types


class DelphiSourceScanner:
    def __init__(self, source_dir: str, output_dir: str, progress_callback: Optional[Callable[[ProgressInfo], None]] = None):
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)
        self.index_file = self.output_dir / "index" / "source_index.json"
        self.metadata_file = self.output_dir / "index" / "metadata.json"
        self.file_extensions = {'.pas', '.dpr', '.dpk', '.inc', '.hpp', '.h'}
        self.progress_callback = progress_callback

        # 创建必要的目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "index").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "data").mkdir(parents=True, exist_ok=True)

    def scan_directory(self) -> Dict:
        """扫描源码目录,收集文件信息（多进程版本）"""
        print(f"开始扫描目录: {self.source_dir}")
        
        # 首先收集所有要扫描的文件路径
        file_paths = []
        for root, dirs, files in os.walk(self.source_dir):
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix.lower() in self.file_extensions:
                    file_paths.append((str(file_path), str(self.source_dir)))
        
        total_files = len(file_paths)
        print(f"预计扫描 {total_files} 个文件...")
        
        # Create progress tracker
        tracker = None
        if self.progress_callback and total_files > 0:
            tracker = ProgressTracker(total_files, self.progress_callback, update_interval=0.5)
        
        # Rule 1: Calculate max processes: min(max(1, files/50), cpu_count-1)
        cpu_cores = cpu_count()
        max_needed = max(1, total_files // 50)
        max_possible = max(1, cpu_cores - 1)
        max_workers = min(max_needed, max_possible)
        
        print(f"Processing: files={total_files}, workers={max_workers}")
        
        import time
        from concurrent.futures import ProcessPoolExecutor
        
        source_files = []
        file_count = 0
        total_lines = 0
        
        # Calculate optimal chunk size for IPC efficiency
        # Larger chunks = less IPC overhead
        chunk_size = max(50, total_files // (max_workers * 4))
        
        # Use ProcessPoolExecutor with larger chunksize to reduce IPC overhead
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            results = executor.map(_analyze_file_worker, file_paths, chunksize=chunk_size)
            
            for file_info in results:
                if file_info:
                    source_files.append(file_info)
                    file_count += 1
                    total_lines += file_info.get('line_count', 0)
                    
                    if tracker and file_count % 100 == 0:
                        tracker.update(file_count, f"Scanning: {file_count}/{total_files}")
        
        if tracker:
            tracker.update(total_files, f"Scanning completed: {file_count} files")
        
        print(f"Scanning completed! Found {file_count} source files, {total_lines} lines of code")

        return {
            'files': source_files,
            'statistics': {
                'total_files': file_count,
                'total_lines': total_lines,
                'scan_time': datetime.now().isoformat()
            }
        }

    def analyze_file(self, file_path: Path) -> Dict:
        """分析单个文件"""
        try:
            # 计算文件哈希
            file_hash = self.calculate_file_hash(file_path)

            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')
                line_count = len(lines)

            # 相对路径
            rel_path = file_path.relative_to(self.source_dir)

            # 提取文件信息
            file_info = {
                'path': str(rel_path).replace('\\', '/'),
                'full_path': str(file_path),
                'extension': file_path.suffix.lower(),
                'size': file_path.stat().st_size,
                'line_count': line_count,
                'hash': file_hash,
                'last_modified': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                'units': self.extract_units(content),
                'uses': self.extract_uses(content),
                'classes': self.extract_classes(content),
                'functions': self.extract_functions(content),
                'constants': self.extract_constants(content),
                'types': self.extract_types(content)
            }

            return file_info

        except Exception as e:
            print(f"分析文件失败 {file_path}: {e}")
            return None

    def calculate_file_hash(self, file_path: Path) -> str:
        """计算文件内容的 MD5 哈希"""
        md5_hash = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()

    def extract_units(self, content: str) -> List[str]:
        """提取 unit 名称"""
        # 匹配 unit UnitName;
        pattern = r'^\s*unit\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*;'
        matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
        return matches

    def extract_uses(self, content: str) -> List[str]:
        """提取 uses 子句中的单元"""
        # 匹配 uses Unit1, Unit2, ...;
        pattern = r'^\s*uses\s+([^;]+);'
        matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
        units = []
        for match in matches:
            # 分割逗号分隔的单元名
            items = [item.strip() for item in match.split(',')]
            units.extend(items)
        return units

    def extract_classes(self, content: str) -> List[Dict]:
        """提取类定义（包含 class、record、interface 等类型）"""
        classes = []

        # 1. 匹配 class 类型: TClassName = class(TBaseClass)
        class_pattern = r'^\s*(T[a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*class\s*(?:\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\))?\s*(?:sealed|abstract)?'
        matches = re.finditer(class_pattern, content, re.MULTILINE | re.IGNORECASE)

        for match in matches:
            class_name = match.group(1)
            base_class = match.group(2) if match.group(2) else 'TObject'
            line_num = content[:match.start()].count('\n') + 1

            classes.append({
                'name': class_name,
                'base_class': base_class,
                'line': line_num,
                'type_kind': 'class'
            })

        # 2. 匹配 record 类型: TRecordName = record 或 TRecordName = record(TBaseRecord)
        record_pattern = r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*record\s*(?:\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\))?'
        matches = re.finditer(record_pattern, content, re.MULTILINE | re.IGNORECASE)

        for match in matches:
            record_name = match.group(1)
            base_record = match.group(2) if match.group(2) else None
            line_num = content[:match.start()].count('\n') + 1

            classes.append({
                'name': record_name,
                'base_class': base_record,
                'line': line_num,
                'type_kind': 'record'
            })

        # 3. 匹配 interface 类型: IInterfaceName = interface(IBaseInterface)
        interface_pattern = r'^\s*(I[a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*interface\s*(?:\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\))?'
        matches = re.finditer(interface_pattern, content, re.MULTILINE | re.IGNORECASE)

        for match in matches:
            interface_name = match.group(1)
            base_interface = match.group(2) if match.group(2) else None
            line_num = content[:match.start()].count('\n') + 1

            classes.append({
                'name': interface_name,
                'base_class': base_interface,
                'line': line_num,
                'type_kind': 'interface'
            })

        # 4. 匹配 enum 类型: TEnumName = (value1, value2, ...)
        enum_pattern = r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\(([^)]+)\)\s*;'
        matches = re.finditer(enum_pattern, content, re.MULTILINE | re.IGNORECASE)

        for match in matches:
            enum_name = match.group(1)
            values = match.group(2).strip()
            # 检查是否是枚举类型（包含逗号分隔的值）
            if ',' in values:
                line_num = content[:match.start()].count('\n') + 1
                classes.append({
                    'name': enum_name,
                    'base_class': None,
                    'line': line_num,
                    'type_kind': 'enum'
                })

        return classes

    def extract_functions(self, content: str) -> List[Dict]:
        """提取函数/过程定义"""
        functions = []

        # 匹配 function/procedure 声明
        patterns = [
            r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
            r'^\s*procedure\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
            r'^\s*class\s+function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
            r'^\s*class\s+procedure\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE)
            for match in matches:
                func_name = match.group(1)
                line_num = content[:match.start()].count('\n') + 1

                functions.append({
                    'name': func_name,
                    'line': line_num,
                    'type': 'function' if 'function' in match.group(0).lower() else 'procedure'
                })

        return functions

    def extract_constants(self, content: str) -> List[Dict]:
        """提取常量定义"""
        constants = []

        # 匹配 const 块中的常量
        const_pattern = r'^\s*const\s*$'
        const_start = None

        for match in re.finditer(const_pattern, content, re.MULTILINE | re.IGNORECASE):
            const_start = match.end()
            break

        if const_start:
            # 提取 const 块后的内容 (直到下一个关键字)
            const_content = content[const_start:]
            const_end = re.search(r'^(?:type|var|begin|implementation|initialization|finalization)\s*$',
                                 const_content, re.MULTILINE | re.IGNORECASE)
            if const_end:
                const_content = const_content[:const_end.start()]

            # 匹配常量定义
            pattern = r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([^;]+);'
            matches = re.finditer(pattern, const_content, re.MULTILINE)

            for match in matches:
                const_name = match.group(1)
                const_value = match.group(2).strip()
                line_num = const_content[:match.start()].count('\n') + 1

                constants.append({
                    'name': const_name,
                    'value': const_value,
                    'line': line_num
                })

        return constants

    def extract_types(self, content: str) -> List[Dict]:
        """提取类型定义"""
        types = []

        # 匹配 type 块中的类型定义
        type_pattern = r'^\s*type\s*$'
        type_start = None

        for match in re.finditer(type_pattern, content, re.MULTILINE | re.IGNORECASE):
            type_start = match.end()
            break

        if type_start:
            # 提取 type 块后的内容 (直到下一个关键字)
            type_content = content[type_start:]
            type_end = re.search(r'^(?:var|begin|implementation|initialization|finalization)\s*$',
                                type_content, re.MULTILINE | re.IGNORECASE)
            if type_end:
                type_content = type_content[:type_end.start()]

            # 匹配简单的类型定义
            pattern = r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([^;]+);'
            matches = re.finditer(pattern, type_content, re.MULTILINE)

            for match in matches:
                type_name = match.group(1)
                type_def = match.group(2).strip()
                line_num = type_content[:match.start()].count('\n') + 1

                types.append({
                    'name': type_name,
                    'definition': type_def,
                    'line': line_num
                })

        return types

    def save_index(self, scan_result: Dict):
        """保存索引到文件"""
        # 保存详细索引
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(scan_result, f, ensure_ascii=False, indent=2)

        # 保存元数据
        metadata = {
            'version': '1.0',
            'source_directory': str(self.source_dir),
            'scan_date': datetime.now().isoformat(),
            'statistics': scan_result['statistics']
        }

        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        print(f"索引已保存到: {self.index_file}")
        print(f"元数据已保存到: {self.metadata_file}")

    def create_category_index(self, scan_result: Dict):
        """创建分类索引"""
        categories = {}

        for file_info in scan_result['files']:
            # 按目录分类
            path_parts = file_info['path'].split('/')
            if len(path_parts) > 1:
                category = path_parts[0]
            else:
                category = 'root'

            if category not in categories:
                categories[category] = []

            categories[category].append({
                'path': file_info['path'],
                'unit': file_info['units'][0] if file_info['units'] else None,
                'classes': file_info['classes'],
                'functions': file_info['functions']
            })

        # 保存分类索引
        category_file = self.output_dir / "index" / "category_index.json"
        with open(category_file, 'w', encoding='utf-8') as f:
            json.dump(categories, f, ensure_ascii=False, indent=2)

        print(f"分类索引已保存到: {category_file}")

    def run(self):
        """执行扫描"""
        print("=" * 60)
        print("Delphi 源码知识库扫描器")
        print("=" * 60)

        # 扫描目录
        scan_result = self.scan_directory()

        # 保存索引
        self.save_index(scan_result)

        # 创建分类索引
        self.create_category_index(scan_result)

        print("=" * 60)
        print("扫描完成!")
        print("=" * 60)
        print(f"总计文件: {scan_result['statistics']['total_files']}")
        print(f"总代码行数: {scan_result['statistics']['total_lines']}")
        print(f"索引文件: {self.index_file}")


def main():
    # 配置
    DELPHI_SOURCE_DIR = r"C:\Program Files (x86)\Embarcadero\Studio\22.0\source"
    OUTPUT_DIR = r"c:\User\diandaxia\delphi-knowledge-base"

    # 执行扫描
    scanner = DelphiSourceScanner(DELPHI_SOURCE_DIR, OUTPUT_DIR)
    scanner.run()


if __name__ == "__main__":
    main()
