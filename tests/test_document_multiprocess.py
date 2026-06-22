#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试文档知识库多进程功能
"""

import sys
import os
import tempfile
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.services.knowledge_base.scan_generic_documents import GenericDocumentScanner


def test_multiprocess_scan():
    """测试多进程扫描"""
    print("=" * 60)
    print("测试 1: 多进程扫描")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "docs"
        test_dir.mkdir()
        
        for i in range(100):
            (test_dir / f"test{i}.txt").write_text(f"内容{i}" * 10, encoding='utf-8')
        
        db_path = Path(tmpdir) / "test.db"
        scanner = GenericDocumentScanner(str(db_path.parent), config={'database': {'file': 'test.db'}})
        
        print(f"\n开始扫描 100 个文件...")
        start = time.time()
        result = scanner.scan_directory(str(test_dir), max_workers=4)
        elapsed = time.time() - start
        
        print(f"\n  处理文件: {result['processed']}/{result['total_files']}")
        print(f"  失败文件: {result['failed']}")
        print(f"  耗时: {elapsed:.3f}s")
        
        assert result['processed'] == 100, f"应处理 100 个文件"
        assert result['failed'] == 0, f"不应有失败"
        
        stats = scanner.get_statistics()
        assert stats['total_documents'] == 100, f"应有 100 个文档"
        
        print(f"\n  ✓ 多进程扫描正常")
        
    pass


def test_parallel_workers_config():
    """测试 parallel_workers 配置"""
    print("\n" + "=" * 60)
    print("测试 2: parallel_workers 配置")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "docs"
        test_dir.mkdir()
        
        for i in range(50):
            (test_dir / f"test{i}.txt").write_text(f"内容{i}", encoding='utf-8')
        
        configs = [
            {'database': {'file': 'test1.db'}, 'build': {'parallel_workers': 2}},
            {'database': {'file': 'test2.db'}, 'build': {'parallel_workers': 8}},
        ]
        
        for config in configs:
            workers = config['build']['parallel_workers']
            db_file = config['database']['file']
            
            scanner = GenericDocumentScanner(tmpdir, config)
            
            print(f"\n配置 parallel_workers={workers}...")
            start = time.time()
            result = scanner.scan_directory(str(test_dir))
            elapsed = time.time() - start
            
            print(f"  处理文件: {result['processed']}")
            print(f"  耗时: {elapsed:.3f}s")
            
            assert result['processed'] == 50
        
        print(f"\n  ✓ parallel_workers 配置生效")
        
    pass


def test_large_files_multiprocess():
    """测试大量文件多进程处理"""
    print("\n" + "=" * 60)
    print("测试 3: 大量文件多进程处理")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "docs"
        test_dir.mkdir()
        
        for i in range(200):
            (test_dir / f"test{i}.txt").write_text(f"内容{i}" * 50, encoding='utf-8')
        
        db_path = Path(tmpdir) / "test.db"
        scanner = GenericDocumentScanner(str(db_path.parent), config={'database': {'file': 'test.db'}})
        
        print(f"\n开始扫描 200 个文件...")
        start = time.time()
        result = scanner.scan_directory(str(test_dir))
        elapsed = time.time() - start
        
        print(f"\n  处理文件: {result['processed']}/{result['total_files']}")
        print(f"  失败文件: {result['failed']}")
        print(f"  耗时: {elapsed:.3f}s")
        print(f"  速度: {result['processed']/elapsed:.1f} 文件/秒")
        
        assert result['processed'] == 200
        assert result['failed'] == 0
        
        stats = scanner.get_statistics()
        assert stats['total_documents'] == 200
        
        print(f"\n  ✓ 大量文件多进程处理正常")
        
    pass


def test_mixed_file_types():
    """测试混合文件类型多进程处理"""
    print("\n" + "=" * 60)
    print("测试 4: 混合文件类型多进程处理")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "docs"
        test_dir.mkdir()
        
        for i in range(30):
            (test_dir / f"text{i}.txt").write_text(f"文本内容{i}", encoding='utf-8')
            (test_dir / f"markdown{i}.md").write_text(f"# 标题{i}\n\n内容{i}", encoding='utf-8')
            (test_dir / f"page{i}.html").write_text(f"<html><body>内容{i}</body></html>", encoding='utf-8')
        
        db_path = Path(tmpdir) / "test.db"
        scanner = GenericDocumentScanner(str(db_path.parent), config={'database': {'file': 'test.db'}})
        
        print(f"\n开始扫描 90 个混合类型文件...")
        start = time.time()
        result = scanner.scan_directory(str(test_dir))
        elapsed = time.time() - start
        
        print(f"\n  处理文件: {result['processed']}/{result['total_files']}")
        print(f"  耗时: {elapsed:.3f}s")
        
        stats = scanner.get_statistics()
        print(f"\n按类型统计:")
        for content_type, count in stats['by_type'].items():
            print(f"  {content_type}: {count}")
        
        assert result['processed'] == 90
        assert stats['total_documents'] == 90
        
        print(f"\n  ✓ 混合文件类型多进程处理正常")
        
    pass


def main():
    """运行所有多进程测试"""
    print("=" * 60)
    print("文档知识库多进程功能测试")
    print("=" * 60)
    
    tests = [
        ("多进程扫描", test_multiprocess_scan),
        ("parallel_workers配置", test_parallel_workers_config),
        ("大量文件处理", test_large_files_multiprocess),
        ("混合文件类型", test_mixed_file_types),
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
