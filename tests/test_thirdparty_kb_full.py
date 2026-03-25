#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试全局第三方库知识库完整功能
"""

import sys
import os

# 切换到 MCP 服务器目录
mcp_server_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
os.chdir(mcp_server_dir)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.knowledge_base.thirdparty_knowledge_base import ThirdPartyKnowledgeBase
import pytest

@pytest.fixture(scope="module")
def kb():
    """共享的知识库 fixture"""
    print("\n初始化第三方库知识库...")
    return ThirdPartyKnowledgeBase()

def test_build_knowledge_base():
    """测试构建第三方库知识库"""
    print("=" * 70)
    print("测试 1: 构建全局第三方库知识库")
    print("=" * 70)
    print()
    
    kb = ThirdPartyKnowledgeBase()
    
    print("开始构建第三方库知识库...")
    print("(这可能需要几分钟时间，取决于第三方库的数量和大小)")
    print()
    
    success = kb.build_thirdparty_knowledge_base(force_rebuild=True)
    
    if success:
        print("✓ 知识库构建成功!")
        print()
        return kb
    else:
        print("✗ 知识库构建失败")
        return None

def test_get_stats(kb):
    """测试获取统计信息"""
    print("=" * 70)
    print("测试 2: 获取第三方库知识库统计")
    print("=" * 70)
    print()
    
    stats = kb.get_statistics()
    
    if not stats:
        print("✗ 无法获取统计信息")
        return
    
    print("第三方库知识库统计:")
    print(f"  - 类数量: {stats.get('classes', 0)}")
    print(f"  - 函数数量: {stats.get('functions', 0)}")
    print(f"  - 文件数量: {stats.get('files', 0)}")
    print(f"  - 词汇表大小: {stats.get('vocabulary_size', 0)}")
    print(f"  - 数据库大小: {stats.get('database_size_mb', 0):.2f} MB")
    print(f"  - 第三方库路径数: {stats.get('thirdparty_paths_count', 0)}")
    print(f"  - Delphi 版本: {stats.get('delphi_version', 'Unknown')}")
    print()

def test_search_class(kb):
    """测试搜索类"""
    print("=" * 70)
    print("测试 3: 搜索第三方库类")
    print("=" * 70)
    print()
    
    # 测试搜索常见的第三方库类
    test_classes = ['TUniButton', 'TfrxReport', 'TChart', 'THTMLLabel']
    
    for class_name in test_classes:
        print(f"搜索类 '{class_name}':")
        results = kb.search_by_class_name(class_name)
        
        if results:
            print(f"  ✓ 找到 {len(results)} 个结果")
            for i, result in enumerate(results[:3], 1):  # 只显示前3个
                print(f"    {i}. {result['class']['name']}")
                print(f"       文件: {result['file']['path']}")
                print(f"       基类: {result['class']['base_class']}")
        else:
            print(f"  - 未找到")
        print()

def test_search_function(kb):
    """测试搜索函数"""
    print("=" * 70)
    print("测试 4: 搜索第三方库函数")
    print("=" * 70)
    print()
    
    # 测试搜索常见的函数
    test_functions = ['Create', 'Destroy', 'LoadFromFile', 'SaveToFile']
    
    for func_name in test_functions:
        print(f"搜索函数 '{func_name}':")
        results = kb.search_by_function_name(func_name)
        
        if results:
            print(f"  ✓ 找到 {len(results)} 个结果")
            for i, result in enumerate(results[:3], 1):  # 只显示前3个
                print(f"    {i}. {result['function']['name']}")
                print(f"       文件: {result['file']['path']}")
                print(f"       类型: {result['function']['type']}")
        else:
            print(f"  - 未找到")
        print()

def test_semantic_search(kb):
    """测试语义搜索"""
    print("=" * 70)
    print("测试 5: 语义搜索第三方库")
    print("=" * 70)
    print()
    
    # 测试语义搜索
    test_queries = [
        'database connection',
        'chart component',
        'web framework',
        'report generation'
    ]
    
    for query in test_queries:
        print(f"语义搜索 '{query}':")
        
        # 搜索类
        class_results = kb.semantic_search_classes(query, top_k=5)
        if class_results:
            print(f"  相关类 (Top {len(class_results)}):")
            for class_name, score in class_results[:3]:
                print(f"    - {class_name} (相似度: {score:.3f})")
        
        # 搜索函数
        func_results = kb.semantic_search_functions(query, top_k=5)
        if func_results:
            print(f"  相关函数 (Top {len(func_results)}):")
            for func_name, score in func_results[:3]:
                print(f"    - {func_name} (相似度: {score:.3f})")
        
        if not class_results and not func_results:
            print(f"  - 未找到相关结果")
        
        print()

def test_get_paths(kb):
    """测试获取路径列表"""
    print("=" * 70)
    print("测试 6: 获取第三方库路径")
    print("=" * 70)
    print()
    
    paths = kb.get_library_paths()
    
    print(f"总共找到 {len(paths)} 个第三方库路径:")
    print()
    
    # 按库分组显示
    libs = {}
    for path in paths:
        # 提取库名（从路径中）
        parts = path.split('\\')
        if 'Libs' in parts:
            idx = parts.index('Libs')
            if idx + 1 < len(parts):
                lib_name = parts[idx + 1]
                if lib_name not in libs:
                    libs[lib_name] = []
                libs[lib_name].append(path)
    
    for lib_name, lib_paths in sorted(libs.items()):
        print(f"  {lib_name}: {len(lib_paths)} 个路径")
        for path in lib_paths[:2]:  # 只显示前2个
            print(f"    - {path}")
        if len(lib_paths) > 2:
            print(f"    ... 等共 {len(lib_paths)} 个路径")
    
    print()

def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("全局第三方库知识库完整功能测试")
    print("=" * 70)
    print()
    
    # 测试1: 构建知识库
    kb = test_build_knowledge_base()
    if not kb:
        print("构建知识库失败，停止后续测试")
        return
    
    # 测试2: 获取统计
    test_get_stats(kb)
    
    # 测试3: 搜索类
    test_search_class(kb)
    
    # 测试4: 搜索函数
    test_search_function(kb)
    
    # 测试5: 语义搜索
    test_semantic_search(kb)
    
    # 测试6: 获取路径
    test_get_paths(kb)
    
    # 关闭知识库
    kb.close()
    
    print("=" * 70)
    print("所有测试完成!")
    print("=" * 70)

if __name__ == "__main__":
    main()
