#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Delphi 知识库服务补充测试

测试版本排序、版本选择、schema 版本管理等关键逻辑
"""

import sys
import sqlite3
from pathlib import Path
import io
import contextlib
import logging

try:
    project_root = Path(__file__).parent.parent
except NameError:
    project_root = Path('.')
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def suppress_logs():
    """临时提升日志级别以抑制 warning/info 输出"""
    logger = logging.getLogger('src.services.knowledge_base')
    old_level = logger.level
    logger.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        logger.setLevel(old_level)


def test_version_sorting_descending():
    """测试版本号降序排序：确保 [0] 始终是最新版"""
    versions = [
        {"version": "23.0", "name": "Delphi 12 Athens"},
        {"version": "22.1", "name": "Delphi 11 Update 1"},
        {"version": "37.0", "name": "Delphi 13 Florence"},
        {"version": "22.0", "name": "Delphi 11 Alexandria"},
        {"version": "21.0", "name": "Delphi 10.4 Sydney"},
    ]
    versions.sort(key=lambda x: tuple(int(p) for p in x["version"].split('.')), reverse=True)
    
    assert versions[0]["version"] == "37.0", "最新版应在首位"
    assert versions[-1]["version"] == "21.0", "最旧版应在末位"
    assert versions[1]["version"] == "23.0"
    assert versions[2]["version"] == "22.1"
    assert versions[3]["version"] == "22.0"


def test_version_sorting_with_subversions():
    """测试含子版本的排序（如 22.0 vs 22.1）"""
    versions = [
        {"version": "22.0", "name": "Delphi 11"},
        {"version": "22.1", "name": "Delphi 11 Update 1"},
        {"version": "22.2", "name": "Delphi 11 Update 2"},
    ]
    versions.sort(key=lambda x: tuple(int(p) for p in x["version"].split('.')), reverse=True)
    
    assert versions[0]["version"] == "22.2"
    assert versions[1]["version"] == "22.1"
    assert versions[2]["version"] == "22.0"


def test_version_sorting_single_version():
    """测试单版本情况"""
    versions = [{"version": "22.0", "name": "Delphi 11"}]
    versions.sort(key=lambda x: tuple(int(p) for p in x["version"].split('.')), reverse=True)
    
    assert len(versions) == 1
    assert versions[0]["version"] == "22.0"


def test_version_sorting_empty():
    """测试空列表排序"""
    versions = []
    versions.sort(key=lambda x: tuple(int(p) for p in x["version"].split('.')), reverse=True)
    
    assert len(versions) == 0


def test_select_delphi_version_returns_latest():
    """测试 select_delphi_version(None) 返回最新版本"""
    from src.services.knowledge_base.service import DelphiKnowledgeBaseService
    
    service = DelphiKnowledgeBaseService.__new__(DelphiKnowledgeBaseService)
    service.delphi_versions = [
        {"version": "22.0", "name": "Delphi 11 Alexandria"},
        {"version": "23.0", "name": "Delphi 12 Athens"},
        {"version": "37.0", "name": "Delphi 13 Florence"},
    ]
    
    result = service.select_delphi_version(None)
    assert result is not None
    assert result["version"] == "37.0", "None 参数应返回第一个元素（假定已排序）"


def test_select_delphi_version_by_version_number():
    """测试按版本号精确匹配"""
    from src.services.knowledge_base.service import DelphiKnowledgeBaseService
    
    service = DelphiKnowledgeBaseService.__new__(DelphiKnowledgeBaseService)
    service.delphi_versions = [
        {"version": "37.0", "name": "Delphi 13 Florence"},
        {"version": "23.0", "name": "Delphi 12 Athens"},
        {"version": "22.0", "name": "Delphi 11 Alexandria"},
    ]
    
    result = service.select_delphi_version("22.0")
    assert result is not None
    assert result["name"] == "Delphi 11 Alexandria"


def test_select_delphi_version_by_name():
    """测试按名称匹配"""
    from src.services.knowledge_base.service import DelphiKnowledgeBaseService
    
    service = DelphiKnowledgeBaseService.__new__(DelphiKnowledgeBaseService)
    service.delphi_versions = [
        {"version": "23.0", "name": "Delphi 12 Athens"},
        {"version": "22.0", "name": "Delphi 11 Alexandria"},
    ]
    
    result = service.select_delphi_version("Delphi 11 Alexandria")
    assert result is not None
    assert result["version"] == "22.0"


def test_select_delphi_version_not_found():
    """测试指定版本不存在时返回 None"""
    from src.services.knowledge_base.service import DelphiKnowledgeBaseService
    
    service = DelphiKnowledgeBaseService.__new__(DelphiKnowledgeBaseService)
    service.delphi_versions = [
        {"version": "22.0", "name": "Delphi 11 Alexandria"},
    ]
    
    result = service.select_delphi_version("99.0")
    assert result is None


def test_select_delphi_version_empty_list():
    """测试版本列表为空时返回 None"""
    from src.services.knowledge_base.service import DelphiKnowledgeBaseService
    
    service = DelphiKnowledgeBaseService.__new__(DelphiKnowledgeBaseService)
    service.delphi_versions = []
    
    result = service.select_delphi_version(None)
    assert result is None


def test_get_schema_version_from_db():
    """测试从数据库读取 schema 版本"""
    from src.services.knowledge_base import get_schema_version_from_db, SCHEMA_VERSION_KEY
    
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT, updated_at REAL)")
    conn.execute(f"INSERT INTO metadata (key, value) VALUES ('{SCHEMA_VERSION_KEY}', '1')")
    
    version = get_schema_version_from_db(conn.cursor())
    assert version == 1
    
    conn.close()


def test_get_schema_version_from_old_db():
    """测试读取无版本信息的旧库返回 0"""
    from src.services.knowledge_base import get_schema_version_from_db
    
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT, updated_at REAL)")
    
    version = get_schema_version_from_db(conn.cursor())
    assert version == 0, "旧库无版本信息应返回 0"
    
    conn.close()


def test_set_schema_version_in_db():
    """测试写入 schema 版本到数据库"""
    from src.services.knowledge_base import set_schema_version_in_db, SCHEMA_VERSION_KEY
    
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT, updated_at REAL)")
    
    set_schema_version_in_db(conn.cursor(), version=2)
    conn.commit()
    
    cursor = conn.cursor()
    cursor.execute(f"SELECT value FROM metadata WHERE key = '{SCHEMA_VERSION_KEY}'")
    row = cursor.fetchone()
    assert row is not None
    assert int(row[0]) == 2
    
    conn.close()


def test_check_schema_version_match():
    """测试 schema 版本匹配时返回 True"""
    from src.services.knowledge_base import check_schema_version, SCHEMA_VERSION, SCHEMA_VERSION_KEY
    
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT, updated_at REAL)")
    conn.execute(f"INSERT INTO metadata (key, value) VALUES ('{SCHEMA_VERSION_KEY}', '{SCHEMA_VERSION}')")
    
    with suppress_logs():
        result = check_schema_version(conn.cursor(), "test_kb")
    assert result is True
    
    conn.close()


def test_check_schema_version_old_db():
    """测试旧库（无版本信息）返回 True（兼容处理）"""
    from src.services.knowledge_base import check_schema_version
    
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT, updated_at REAL)")
    
    with suppress_logs():
        result = check_schema_version(conn.cursor(), "old_kb")
    assert result is True, "旧库无版本信息应假定兼容"
    
    conn.close()


def test_check_schema_version_mismatch():
    """测试 schema 版本不匹配时返回 False"""
    from src.services.knowledge_base import check_schema_version, SCHEMA_VERSION_KEY
    
    if SCHEMA_VERSION_KEY == 'schema_version':
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT, updated_at REAL)")
        conn.execute(f"INSERT INTO metadata (key, value) VALUES ('{SCHEMA_VERSION_KEY}', '999')")
        
        with suppress_logs():
            result = check_schema_version(conn.cursor(), "future_kb")
        assert result is False, "版本不匹配应返回 False"
        
        conn.close()


def run_all_tests():
    """运行所有测试"""
    import traceback
    
    tests = [
        ("版本降序排序", test_version_sorting_descending),
        ("版本排序（含子版本）", test_version_sorting_with_subversions),
        ("版本排序（单版本）", test_version_sorting_single_version),
        ("版本排序（空列表）", test_version_sorting_empty),
        ("select_delphi_version(None) 返回最新", test_select_delphi_version_returns_latest),
        ("select_delphi_version 按版本号匹配", test_select_delphi_version_by_version_number),
        ("select_delphi_version 按名称匹配", test_select_delphi_version_by_name),
        ("select_delphi_version 版本不存在", test_select_delphi_version_not_found),
        ("select_delphi_version 空列表", test_select_delphi_version_empty_list),
        ("get_schema_version_from_db", test_get_schema_version_from_db),
        ("get_schema_version_from_old_db", test_get_schema_version_from_old_db),
        ("set_schema_version_in_db", test_set_schema_version_in_db),
        ("check_schema_version 匹配", test_check_schema_version_match),
        ("check_schema_version 旧库", test_check_schema_version_old_db),
        ("check_schema_version 不匹配", test_check_schema_version_mismatch),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            print(f"  [OK] {name}")
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {type(e).__name__}: {e}")
            failed += 1
    
    print(f"\n结果: {passed}/{len(tests)} 通过")
    return failed == 0


if __name__ == "__main__":
    print("=" * 60)
    print("Delphi 知识库服务补充测试")
    print("=" * 60)
    print()
    success = run_all_tests()
    sys.exit(0 if success else 1)
