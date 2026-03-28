#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试帮助知识库搜索性能
"""

import sys
import os
import time

os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.services.knowledge_base.help_knowledge_base import DelphiHelpKnowledgeBase
from src.services.knowledge_base.sqlite_vector_query_knowledge_base import SQLiteVectorKnowledgeBase


def test_search():
    print("=" * 60)
    print("帮助知识库搜索性能测试")
    print("=" * 60)
    
    # 初始化
    help_kb = DelphiHelpKnowledgeBase()
    print(f"KB dir: {help_kb.kb_dir}")
    kb = SQLiteVectorKnowledgeBase(str(help_kb.kb_dir))
    print(f"KB instance: {kb}")
    print(f"KB vocabulary: {len(kb.vocabulary) if kb.vocabulary else 0}")
    
    # 测试查询
    test_queries = [
        # 类搜索
        ("类名搜索", "TButton"),
        ("类名搜索", "TForm"),
        ("类名搜索", "TStringList"),
        ("类名搜索", "EIdSocketError"),
        
        # 函数搜索
        ("函数搜索", "ShowMessage"),
        ("函数搜索", "StrToInt"),
        ("函数搜索", "FormatDateTime"),
        
        # 关键词搜索
        ("关键词搜索", "button onclick"),
        ("关键词搜索", "database connection"),
        ("关键词搜索", "file I/O"),
        
        # 语义搜索
        ("语义搜索-类", "button component"),
        ("语义搜索-类", "form window"),
        ("语义搜索-函数", "convert string to integer"),
    ]
    
    print(f"\n数据库统计:")
    stats = help_kb.get_statistics()
    print(f"  文件数: {stats.get('total_documents', 0)}")
    print(f"  类定义: {stats.get('total_classes', 0)}")
    print(f"  函数定义: {stats.get('total_functions', 0)}")
    print(f"  数据库大小: {stats.get('database_size_mb', 0):.2f} MB")
    
    print("\n" + "=" * 60)
    print("搜索性能测试")
    print("=" * 60)
    
    total_time = 0
    test_count = 0
    
    for query_type, query in test_queries:
        start = time.time()
        
        if "类名搜索" in query_type:
            results = kb.search_by_class_name(query)[:10]
        elif "函数搜索" in query_type:
            results = kb.search_by_function_name(query)[:10]
        elif "语义搜索-类" in query_type:
            results = kb.semantic_search_classes(query)[:10]
        elif "语义搜索-函数" in query_type:
            results = kb.semantic_search_functions(query)[:10]
        else:
            results = kb.search_by_keyword(query)[:10]
        
        elapsed = time.time() - start
        total_time += elapsed
        test_count += 1
        
        result_count = len(results) if results else 0
        print(f"[{elapsed*1000:8.2f}ms] {query_type}: '{query}' -> {result_count} 结果")
    
    avg_time = (total_time / test_count) * 1000
    print("\n" + "=" * 60)
    print(f"平均查询时间: {avg_time:.2f}ms")
    print(f"总测试数: {test_count}")
    print("=" * 60)
    
    # 批量搜索测试
    print("\n批量搜索测试 (100次搜索)...")
    batch_start = time.time()
    for i in range(100):
        kb.search_by_keyword("test")[:10]
    batch_elapsed = time.time() - batch_start
    print(f"100次搜索耗时: {batch_elapsed*1000:.2f}ms")
    print(f"平均每次: {batch_elapsed*10:.2f}ms")


if __name__ == "__main__":
    test_search()
