#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
边界条件和潜在 Bug 测试
"""

import sys
import os
import shutil
import tempfile
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.services.knowledge_base.scan_generic_documents import (
    GenericDocumentScanner,
    TextProcessor,
    MarkdownProcessor,
    HTMLProcessor,
)


def test_empty_file():
    """测试空文件"""
    print("\n测试 1: 空文件处理")
    
    processor = TextProcessor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        empty_file = Path(tmpdir) / "empty.txt"
        empty_file.write_text("", encoding='utf-8')
        
        result = processor.process(empty_file)
        
        if result:
            print(f"  空文件标题: '{result['title']}'")
            print(f"  空文件内容: '{result['content']}'")
            assert result['content'] == "", "空文件内容应为空字符串"
            assert result['line_count'] >= 0, "行数应 >= 0"
            print("  ✓ 测试通过")
        else:
            print("  空文件返回 None (可接受)")
    
    pass


def test_large_file():
    """测试大文件"""
    print("\n测试 2: 大文件处理")
    
    processor = TextProcessor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        large_file = Path(tmpdir) / "large.txt"
        large_content = "标题\n" + "内容行\n" * 10000
        large_file.write_text(large_content, encoding='utf-8')
        
        result = processor.process(large_file)
        
        assert result is not None, "大文件应能处理"
        assert result['line_count'] >= 10000, f"行数应 >= 10000, 实际 {result['line_count']}"
        print(f"  大文件行数: {result['line_count']}")
        print(f"  大文件大小: {result['size']} 字节")
        print("  ✓ 测试通过")
    
    pass


def test_unicode_filename():
    """测试 Unicode 文件名"""
    print("\n测试 3: Unicode 文件名")
    
    processor = TextProcessor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        unicode_file = Path(tmpdir) / "测试文件_中文.txt"
        unicode_file.write_text("测试内容", encoding='utf-8')
        
        result = processor.process(unicode_file)
        
        assert result is not None, "Unicode 文件名应能处理"
        print(f"  Unicode 文件处理成功")
        print("  ✓ 测试通过")
    
    pass


def test_special_characters_in_content():
    """测试特殊字符内容"""
    print("\n测试 4: 特殊字符内容")
    
    processor = MarkdownProcessor()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        special_file = Path(tmpdir) / "special.md"
        special_content = "# 标题\n\n```\n特殊字符: \t\n\r\x00\x01\n```"
        special_file.write_text(special_content, encoding='utf-8')
        
        result = processor.process(special_file)
        
        assert result is not None, "特殊字符内容应能处理"
        print(f"  特殊字符处理成功")
        print("  ✓ 测试通过")
    
    pass


def test_nonexistent_directory():
    """测试不存在的目录"""
    print("\n测试 5: 不存在的目录")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        scanner = GenericDocumentScanner(str(db_path.parent), config={'database': {'file': 'test.db'}})
        
        result = scanner.scan_directory("/nonexistent/path/12345")
        
        assert 'error' in result, "应返回错误信息"
        print(f"  错误信息: {result['error']}")
        print("  ✓ 测试通过")
    
    pass


def test_empty_directory():
    """测试空目录"""
    print("\n测试 6: 空目录")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        empty_dir = Path(tmpdir) / "empty"
        empty_dir.mkdir()
        
        db_path = Path(tmpdir) / "test.db"
        scanner = GenericDocumentScanner(str(db_path.parent), config={'database': {'file': 'test.db'}})
        
        result = scanner.scan_directory(str(empty_dir))
        
        assert result['total_files'] == 0, "空目录应返回 0 文件"
        assert result['processed'] == 0, "处理数应为 0"
        print(f"  空目录处理成功")
        print("  ✓ 测试通过")
    
    pass


def test_search_empty_query():
    """测试空查询"""
    print("\n测试 7: 空查询字符串")
    
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = Path(tmpdir) / "test.db"
        scanner = GenericDocumentScanner(str(db_path.parent), config={'database': {'file': 'test.db'}})
        
        results = scanner.search("")
        
        print(f"  空查询返回 {len(results)} 个结果")
        print("  ✓ 测试通过")
    finally:
        # 确保 scanner 和所有连接释放后再删除临时目录
        del scanner
        import gc
        gc.collect()
        gc.collect()
        shutil.rmtree(tmpdir, ignore_errors=True)
    
    pass


def test_search_sql_injection():
    """测试 SQL 注入防护"""
    print("\n测试 8: SQL 注入防护")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "docs"
        test_dir.mkdir()
        
        (test_dir / "test.txt").write_text("正常内容", encoding='utf-8')
        
        db_path = Path(tmpdir) / "test.db"
        scanner = GenericDocumentScanner(str(db_path.parent), config={'database': {'file': 'test.db'}})
        scanner.scan_directory(str(test_dir))
        
        malicious_queries = [
            "'; DROP TABLE documents; --",
            "test' OR '1'='1",
            "test; DELETE FROM documents;",
        ]
        
        for query in malicious_queries:
            results = scanner.search(query)
            print(f"  查询 '{query[:20]}...' 返回 {len(results)} 个结果")
        
        stats = scanner.get_statistics()
        assert stats['total_documents'] == 1, "数据应未被删除"
        print("  SQL 注入防护测试通过")
        print("  ✓ 测试通过")
    
    pass


def test_concurrent_access():
    """测试并发访问"""
    print("\n测试 9: 并发访问")
    
    import threading
    import time
    
    tmpdir = tempfile.mkdtemp()
    try:
        test_dir = Path(tmpdir) / "docs"
        test_dir.mkdir()
        
        for i in range(10):
            (test_dir / f"test{i}.txt").write_text(f"内容{i}", encoding='utf-8')
        
        db_path = Path(tmpdir) / "test.db"
        scanner = GenericDocumentScanner(str(db_path.parent), config={'database': {'file': 'test.db'}})
        
        results = []
        errors = []
        
        def search_task():
            try:
                r = scanner.search("内容")
                results.append(len(r))
            except Exception as e:
                errors.append(str(e))
        
        threads = [threading.Thread(target=search_task) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"并发访问出错: {errors}"
        print(f"  5 个并发查询全部成功")
        print("  ✓ 测试通过")
    finally:
        del scanner
        import gc
        gc.collect()
        gc.collect()
        shutil.rmtree(tmpdir, ignore_errors=True)
    
    pass


def test_database_init():
    """测试 ZVec 存储初始化"""
    print("\n测试 10: ZVec 存储初始化")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        scanner = GenericDocumentScanner(str(tmpdir))
        
        # 创建一个受支持的文件类型用于扫描验证
        src = Path(tmpdir) / "src"
        src.mkdir()
        (src / "test.txt").write_text("This is a test document for scanner initialization.", encoding='utf-8')
        
        result = scanner.scan_directory(str(src))
        
        stats = scanner.get_statistics()
        assert stats['total_documents'] >= 1
        
        print("  ZVec 存储初始化成功，已写入文档")
        print("  ✓ 测试通过")
    
    pass


def main():
    """运行所有边界条件测试"""
    print("=" * 60)
    print("边界条件和潜在 Bug 测试")
    print("=" * 60)
    
    tests = [
        ("空文件", test_empty_file),
        ("大文件", test_large_file),
        ("Unicode文件名", test_unicode_filename),
        ("特殊字符", test_special_characters_in_content),
        ("不存在目录", test_nonexistent_directory),
        ("空目录", test_empty_directory),
        ("空查询", test_search_empty_query),
        ("SQL注入", test_search_sql_injection),
        ("并发访问", test_concurrent_access),
        ("数据库初始化", test_database_init),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
        except AssertionError as e:
            print(f"  ✗ 断言失败: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"通过: {passed}")
    print(f"失败: {failed}")
    print(f"总计: {len(tests)}")
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
