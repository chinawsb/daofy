#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分析新的筛选规则的影响
规则：
1. 跳过所有非HTML文件
2. 跳过 .htaccess, robots.txt, sitemap.xml, [index|toc|nav|menu|footer].[x]htm[l]
"""

import sys
import os
from pathlib import Path
import re

os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def main():
    kb_dir = Path(__file__).parent / "data" / "help-knowledge-base"
    extracted_dir = kb_dir / "extracted"
    
    # 收集所有文件（非仅HTML）
    all_files = []
    for f in extracted_dir.rglob("*"):
        if f.is_file():
            all_files.append(f)
    
    print(f"总文件数: {len(all_files)}")
    
    # 统计
    html_files = []
    non_html_files = []
    skipped_by_new_rule = []
    passed = []
    
    # 新规则：跳过这些文件名
    skip_patterns = [
        r'^\.htaccess$',
        r'^robots\.txt$',
        r'^sitemap\.xml$',
        r'^(index|toc|nav|menu|footer)\.[x]?html?$',
    ]
    
    for f in all_files:
        rel_path = str(f.relative_to(extracted_dir))
        file_name = f.name.lower()
        
        # 1. 检查是否为HTML文件
        if f.suffix.lower() not in ['.html', '.htm', '.xhtml']:
            non_html_files.append(rel_path)
            continue
        
        # 2. 检查是否匹配跳过规则
        skipped = False
        for pattern in skip_patterns:
            if re.match(pattern, file_name, re.IGNORECASE):
                skipped_by_new_rule.append(rel_path)
                skipped = True
                break
        
        if skipped:
            continue
        
        # 通过
        passed.append(rel_path)
    
    # 打印结果
    print("\n" + "="*60)
    print("新规则影响分析")
    print("="*60)
    
    print(f"\n总文件数: {len(all_files)}")
    print(f"HTML文件: {len(html_files) + len(non_html_files) + len(skipped_by_new_rule) + len(passed) - len(non_html_files)}")
    
    print("\n--- 按类型统计 ---")
    print(f"HTML文件: {len(passed) + len(skipped_by_new_rule)}")
    print(f"非HTML文件: {len(non_html_files)}")
    
    print("\n--- 非HTML文件类型分布 ---")
    ext_counts = {}
    for f in non_html_files:
        ext = Path(f).suffix.lower() or '(无后缀)'
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
    
    for ext, count in sorted(ext_counts.items(), key=lambda x: -x[1])[:20]:
        print(f"  {ext}: {count} 个")
    
    print("\n--- 被新规则跳过的HTML文件 ---")
    print(f"共: {len(skipped_by_new_rule)} 个")
    
    # 按模式分类
    pattern_counts = {}
    for f in skipped_by_new_rule:
        fname = Path(f).name.lower()
        if fname == '.htaccess':
            pattern_counts['.htaccess'] = pattern_counts.get('.htaccess', 0) + 1
        elif fname == 'robots.txt':
            pattern_counts['robots.txt'] = pattern_counts.get('robots.txt', 0) + 1
        elif fname == 'sitemap.xml':
            pattern_counts['sitemap.xml'] = pattern_counts.get('sitemap.xml', 0) + 1
        elif re.match(r'^(index|toc|nav|menu|footer)\.[x]?html?$', fname):
            # 进一步分类
            base = re.match(r'^(index|toc|nav|menu|footer)', fname).group(1)
            pattern_counts[base + '.*'] = pattern_counts.get(base + '.*', 0) + 1
    
    for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        print(f"  {pattern}: {count} 个")
    
    # 抽样展示
    if skipped_by_new_rule:
        print("\n被跳过文件示例:")
        for f in skipped_by_new_rule[:15]:
            print(f"  - {f}")
    
    print("\n--- 新规则 vs 旧规则对比 ---")
    
    # 旧规则统计
    old_skipped = len(non_html_files)  # 非HTML
    
    error_patterns = ['error', '404', 'redirect', 'notfound', 'accessdenied']
    old_error_skipped = 0
    for f in passed:  # 从新规则通过的文件中找旧规则会跳过的
        fname = Path(f).name.lower()
        if any(p in fname for p in error_patterns):
            old_error_skipped += 1
    
    print(f"\n旧规则跳过: ~{old_skipped + old_error_skipped} 个 (非HTML + error关键词)")
    print(f"新规则跳过: {len(non_html_files) + len(skipped_by_new_rule)} 个 (非HTML + 指定文件名)")
    
    print(f"\n旧规则通过: {len(all_files) - old_skipped - old_error_skipped} 个")
    print(f"新规则通过: {len(passed)} 个")
    
    print("\n--- 结论 ---")
    diff = len(passed) - (len(all_files) - old_skipped - old_error_skipped)
    if diff > 0:
        print(f"✅ 新规则比旧规则多保留 {diff} 个文件 (+{diff/len(all_files)*100:.1f}%)")
    else:
        print(f"⚠️ 新规则比旧规则少保留 {-diff} 个文件 ({diff/len(all_files)*100:.1f}%)")

if __name__ == "__main__":
    main()
