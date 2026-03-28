#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查被错误关键词误伤的文件
"""

import sys
import os
from pathlib import Path

os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def main():
    kb_dir = Path(__file__).parent / "data" / "help-knowledge-base"
    extracted_dir = kb_dir / "extracted"
    
    # 收集所有HTML文件
    all_html_files = []
    for ext in ['*.html', '*.htm']:
        for f in extracted_dir.rglob(ext):
            all_html_files.append(f)
    
    error_patterns = ['404', 'error', 'redirect', 'notfound', 'accessdenied']
    
    # 按模式分类统计
    stats = {p: [] for p in error_patterns}
    
    for f in all_html_files:
        file_name = f.name.lower()
        
        for p in error_patterns:
            if p in file_name:
                stats[p].append(str(f.relative_to(kb_dir)))
    
    print("被错误关键词过滤的文件分析:")
    print("="*60)
    
    total = 0
    for pattern in error_patterns:
        count = len(stats[pattern])
        total += count
        print(f"\n'{pattern}': {count} 个")
        if count > 0:
            # 打印前10个示例
            for f in stats[pattern][:10]:
                print(f"  - {f}")
            if count > 10:
                print(f"  ... 还有 {count - 10} 个")
    
    print(f"\n总计: {total} 个")
    
    # 手动检查一些被过滤的文件是否真的没用
    print("\n" + "="*60)
    print("抽样检查被过滤的文件内容:")
    print("="*60)
    
    # 检查包含 "error" 的文件（可能是误伤最多的）
    sample_files = stats['error'][:5]
    for f in sample_files:
        full_path = kb_dir / f
        try:
            size = full_path.stat().st_size
            print(f"\n{f} (大小: {size} bytes)")
            # 读取前500个字符
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as fp:
                content = fp.read()[:500]
                print(content[:300])
        except Exception as e:
            print(f"  读取失败: {e}")

if __name__ == "__main__":
    main()
