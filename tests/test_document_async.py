#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试文档知识库异步功能
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


def test_async_scan():
    """测试异步扫描"""
    print("=" * 60)
    print("测试 1: 异步扫描文档目录")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "docs"
        test_dir.mkdir()
        
        for i in range(10):
            (test_dir / f"test{i}.txt").write_text(f"内容{i}", encoding='utf-8')
        
        db_path = Path(tmpdir) / "test.db"
        scanner = GenericDocumentScanner(str(db_path.parent), config={'database': {'file': 'test.db'}})
        
        callback_result = []
        
        def callback(result):
            callback_result.append(result)
            print(f"  回调: 处理完成 {result['processed']}/{result['total_files']}")
        
        print(f"\n启动异步扫描...")
        scanner.scan_directory_async(str(test_dir), callback=callback)
        
        assert scanner.is_scanning() or len(callback_result) > 0, "应正在扫描或已完成"
        print(f"  is_scanning: {scanner.is_scanning()}")
        
        print(f"\n等待扫描完成...")
        completed = scanner.wait_scan_complete(timeout=10)
        
        assert completed, "扫描应在超时前完成"
        assert len(callback_result) > 0, "回调应被调用"
        
        result = callback_result[0]
        assert result['processed'] == 10, f"应处理 10 个文件, 实际 {result['processed']}"
        
        print(f"\n  ✓ 异步扫描完成")
        print(f"  ✓ 回调正确调用")
        print(f"  ✓ 处理文件数: {result['processed']}")
        
    pass


def test_async_scan_progress():
    """测试异步扫描进度回调"""
    print("\n" + "=" * 60)
    print("测试 2: 异步扫描进度回调")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "docs"
        test_dir.mkdir()
        
        for i in range(50):
            (test_dir / f"test{i}.txt").write_text(f"内容{i}" * 10, encoding='utf-8')
        
        db_path = Path(tmpdir) / "test.db"
        
        progress_events = []
        
        def progress_callback(value, message, *_):
            progress_events.append((value, message))
        
        scanner = GenericDocumentScanner(
            str(db_path.parent),
            config={'database': {'file': 'test.db'}},
            progress_callback=progress_callback
        )
        
        print(f"\n启动异步扫描...")
        scanner.scan_directory_async(str(test_dir))
        
        scanner.wait_scan_complete(timeout=30)
        
        print(f"\n  进度事件数: {len(progress_events)}")
        if progress_events:
            for val, msg in progress_events[-3:]:
                print(f"    {val}%: {msg}")
        
        stats = scanner.get_statistics()
        assert stats['total_documents'] == 50, f"应有 50 个文档, 实际 {stats['total_documents']}"
        
        print(f"\n  ✓ 异步扫描完成")
        print(f"  ✓ 文档数: {stats['total_documents']}")
        
    pass


def test_concurrent_scan_prevention():
    """测试并发扫描防护"""
    print("\n" + "=" * 60)
    print("测试 3: 并发扫描防护")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "docs"
        test_dir.mkdir()
        
        for i in range(5):
            (test_dir / f"test{i}.txt").write_text(f"内容{i}", encoding='utf-8')
        
        db_path = Path(tmpdir) / "test.db"
        scanner = GenericDocumentScanner(str(db_path.parent), config={'database': {'file': 'test.db'}})
        
        print(f"\n启动第一个异步扫描...")
        scanner.scan_directory_async(str(test_dir))
        
        time.sleep(0.1)
        
        print(f"尝试启动第二个异步扫描...")
        scanner.scan_directory_async(str(test_dir))
        
        scanner.wait_scan_complete(timeout=10)
        
        stats = scanner.get_statistics()
        assert stats['total_documents'] == 5, f"应有 5 个文档, 实际 {stats['total_documents']}"
        
        print(f"\n  ✓ 并发防护正常")
        print(f"  ✓ 文档数: {stats['total_documents']}")
        
    pass


def test_sync_vs_async():
    """对比同步和异步扫描"""
    print("\n" + "=" * 60)
    print("测试 4: 同步 vs 异步扫描对比")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir) / "docs"
        test_dir.mkdir()
        
        for i in range(20):
            (test_dir / f"test{i}.txt").write_text(f"内容{i}" * 100, encoding='utf-8')
        
        db_path1 = Path(tmpdir) / "sync.db"
        scanner1 = GenericDocumentScanner(str(db_path1.parent), config={'database': {'file': 'sync.db'}})
        
        print(f"\n同步扫描...")
        start = time.time()
        result1 = scanner1.scan_directory(str(test_dir))
        sync_time = time.time() - start
        print(f"  同步耗时: {sync_time:.3f}s")
        print(f"  处理文件: {result1['processed']}")
        
        db_path2 = Path(tmpdir) / "async.db"
        scanner2 = GenericDocumentScanner(str(db_path2.parent), config={'database': {'file': 'async.db'}})
        
        print(f"\n异步扫描...")
        start = time.time()
        scanner2.scan_directory_async(str(test_dir))
        
        time.sleep(0.05)
        print(f"  异步立即返回耗时: {time.time() - start:.3f}s")
        
        scanner2.wait_scan_complete(timeout=30)
        async_total_time = time.time() - start
        print(f"  异步总耗时: {async_total_time:.3f}s")
        
        stats2 = scanner2.get_statistics()
        print(f"  处理文件: {stats2['total_documents']}")
        
        assert result1['processed'] == stats2['total_documents'], "同步和异步应处理相同数量"
        
        print(f"\n  ✓ 同步和异步结果一致")
        print(f"  ✓ 异步立即返回特性正常")
        
    pass


def main():
    """运行所有异步测试"""
    print("=" * 60)
    print("文档知识库异步功能测试")
    print("=" * 60)
    
    tests = [
        ("异步扫描", test_async_scan),
        ("进度回调", test_async_scan_progress),
        ("并发防护", test_concurrent_scan_prevention),
        ("同步vs异步", test_sync_vs_async),
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
