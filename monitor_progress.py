#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实时监控构建进度"""

import time
import os
from pathlib import Path

kb_dir = Path(r"c:\User\cloudAttendance\service\delphi-complier-mcp-server\data\help-knowledge-base")
index_dir = kb_dir / "index"
extracted_dir = kb_dir / "extracted"

print("=" * 80)
print("Delphi帮助知识库构建进度监控")
print("=" * 80)

# 检查解压进度
if extracted_dir.exists():
    help_names = ['vcl', 'fmx', 'system', 'libraries', 'data', 'codeexamples', 'topics', 'Indy10', 'TeeChart']
    extracted_count = sum(1 for name in help_names if (extracted_dir / name).exists())
    print(f"\n[CHM解压] {extracted_count}/9 个帮助文件已解压")
    
    # 统计HTML文件
    total_html = 0
    for name in help_names:
        help_dir = extracted_dir / name
        if help_dir.exists():
            count = sum(1 for root, dirs, files in os.walk(help_dir) 
                       for f in files if f.endswith(('.html', '.htm')))
            total_html += count
    print(f"[HTML文件] 总计 {total_html:,} 个HTML文件")

# 检查索引构建进度
if index_dir.exists():
    source_index = index_dir / "source_index.json"
    if source_index.exists():
        import json
        stat = source_index.stat()
        mtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
        
        data = json.load(open(source_index, encoding='utf-8'))
        stats = data['statistics']
        
        print(f"\n[索引构建] 已完成")
        print(f"  - 构建时间: {stats['build_time']}")
        print(f"  - 文档数: {stats['total_files']:,}")
        print(f"  - 类: {stats['total_classes']:,}")
        print(f"  - 函数: {stats['total_functions']:,}")
        print(f"  - 属性: {stats['total_properties']:,}")
        print(f"  - 事件: {stats['total_events']:,}")
        print(f"  - 接口: {stats['total_interfaces']:,}")
        print(f"  - 类型: {stats['total_types']:,}")
        print(f"  - 代码示例: {stats['total_code_examples']:,}")
        
        # 计算进度
        if total_html > 0:
            progress = (stats['total_files'] / total_html) * 100
            print(f"\n[总体进度] {progress:.1f}% ({stats['total_files']:,}/{total_html:,})")
    else:
        print(f"\n[索引构建] 未开始")

# 检查数据库
db_file = index_dir / "knowledge_base_vector.sqlite"
if db_file.exists():
    size_mb = db_file.stat().st_size / (1024 * 1024)
    print(f"\n[数据库] {size_mb:.2f} MB")

print("\n" + "=" * 80)
