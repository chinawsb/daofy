#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分析帮助知识库筛选条件 - 检查误伤和符合条件的情况
优化版 - 使用更高效的方法
"""

import sys
import os
from pathlib import Path
from collections import defaultdict
import multiprocessing

os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def analyze_single_file(args):
    """分析单个文件"""
    f, kb_dir = args
    file_name = f.name.lower()
    path_str = str(f).replace('\\', '/').lower()
    
    try:
        file_size = f.stat().st_size
    except:
        return 'error', str(f)
    
    # 1. 文件太小
    if file_size < 100:
        return 'too_small', str(f.relative_to(kb_dir))
    
    # 2. 路径模式
    skip_path_patterns = [
        '/scripts/', '/styles/', '/css/', '/js/', '/assets/',
        '/_private/', '/images/', '/image/', '/img/', '/icons/', '/fonts/'
    ]
    for pattern in skip_path_patterns:
        if pattern in path_str:
            return 'skip_path', (pattern, str(f.relative_to(kb_dir)))
    
    # 3. 文件名
    skip_files = [
        'index.htm', 'index.html', 'index.xhtml',
        'search.htm', 'search.html',
        'toc.htm', 'toc.html',
        'nav.htm', 'nav.html',
        '.htaccess', 'robots.txt',
        'favicon.ico', 'favicon.png',
        'sitemap.xml', 'sitemap.html',
    ]
    if file_name in skip_files:
        return 'skip_file', (file_name, str(f.relative_to(kb_dir)))
    
    # 4. 错误关键词
    error_patterns = ['404', 'error', 'redirect', 'notfound', 'accessdenied']
    if any(p in file_name for p in error_patterns):
        return 'error_keyword', str(f.relative_to(kb_dir))
    
    return 'passed', str(f.relative_to(kb_dir))

def main():
    kb_dir = Path(__file__).parent / "data" / "help-knowledge-base"
    extracted_dir = kb_dir / "extracted"
    
    if not extracted_dir.exists():
        print(f"目录不存在: {extracted_dir}")
        return
    
    # 收集所有HTML文件
    print("正在收集HTML文件...")
    all_html_files = []
    for ext in ['*.html', '*.htm']:
        for f in extracted_dir.rglob(ext):
            all_html_files.append(f)
    
    total = len(all_html_files)
    print(f"总HTML文件数: {total}")
    
    if total == 0:
        return
    
    # 准备参数
    args_list = [(f, kb_dir) for f in all_html_files]
    
    # 多进程处理
    print("正在分析文件...")
    cpu_count = multiprocessing.cpu_count()
    workers = max(1, min(8, cpu_count - 1))
    
    stats = {
        'total': total,
        'too_small': 0,
        'skip_path': defaultdict(int),
        'skip_file': defaultdict(int),
        'error_keyword': 0,
        'passed': 0,
        'error': 0,
    }
    
    # 单进程模式（更稳定）
    for i, args in enumerate(args_list):
        category, data = analyze_single_file(args)
        if category == 'too_small':
            stats['too_small'] += 1
        elif category == 'skip_path':
            stats['skip_path'][data[0]] += 1
        elif category == 'skip_file':
            stats['skip_file'][data[0]] += 1
        elif category == 'error_keyword':
            stats['error_keyword'] += 1
        elif category == 'passed':
            stats['passed'] += 1
        else:
            stats['error'] += 1
        
        if (i + 1) % 5000 == 0:
            print(f"已处理 {i+1}/{total}")
    
    # 打印结果
    print("\n" + "="*60)
    print("筛选条件分析结果")
    print("="*60)
    
    print(f"\n总文件数: {stats['total']}")
    print(f"通过筛选: {stats['passed']} ({stats['passed']/stats['total']*100:.1f}%)")
    
    # 误伤统计
    print("\n--- 误伤详情 ---")
    
    total_skipped = 0
    
    print(f"\n1. 文件太小 (<100字节): {stats['too_small']} 个")
    total_skipped += stats['too_small']
    
    skip_path_total = sum(stats['skip_path'].values())
    print(f"\n2. 路径跳过: {skip_path_total} 个")
    for pattern, count in sorted(stats['skip_path'].items(), key=lambda x: -x[1]):
        print(f"   {pattern}: {count} 个")
    total_skipped += skip_path_total
    
    skip_file_total = sum(stats['skip_file'].values())
    print(f"\n3. 文件名跳过: {skip_file_total} 个")
    for name, count in sorted(stats['skip_file'].items(), key=lambda x: -x[1]):
        print(f"   {name}: {count} 个")
    total_skipped += skip_file_total
    
    print(f"\n4. 错误关键词: {stats['error_keyword']} 个")
    total_skipped += stats['error_keyword']
    
    print(f"\n5. 处理错误: {stats['error']} 个")
    total_skipped += stats['error']
    
    print(f"\n总误伤: {total_skipped} ({total_skipped/stats['total']*100:.1f}%)")
    print(f"符合条件: {stats['passed']} ({stats['passed']/stats['total']*100:.1f}%)")

if __name__ == "__main__":
    main()
