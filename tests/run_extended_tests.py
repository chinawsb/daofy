#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行补充测试"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import sqlite3
import logging

from src.services.knowledge_base import (
    get_schema_version_from_db,
    set_schema_version_in_db,
    check_schema_version,
    SCHEMA_VERSION,
    SCHEMA_VERSION_KEY,
)
from src.services.knowledge_base.service import DelphiKnowledgeBaseService


def suppress_logs():
    logging.getLogger('src.services.knowledge_base').setLevel(logging.CRITICAL)


def test_version_sorting():
    """版本降序排序"""
    versions = [
        {"version": "23.0", "name": "Delphi 12"},
        {"version": "37.0", "name": "Delphi 13"},
        {"version": "22.0", "name": "Delphi 11"},
    ]
    versions.sort(key=lambda x: tuple(int(p) for p in x["version"].split('.')), reverse=True)
    assert versions[0]["version"] == "37.0"
    assert versions[-1]["version"] == "22.0"


def test_select_latest_version():
    """select_delphi_version(None) 返回第一个"""
    service = DelphiKnowledgeBaseService.__new__(DelphiKnowledgeBaseService)
    service.delphi_versions = [
        {"version": "37.0", "name": "Delphi 13"},
        {"version": "23.0", "name": "Delphi 12"},
    ]
    result = service.select_delphi_version(None)
    assert result["version"] == "37.0"


def test_select_by_version():
    """按版本号选择"""
    service = DelphiKnowledgeBaseService.__new__(DelphiKnowledgeBaseService)
    service.delphi_versions = [
        {"version": "23.0", "name": "Delphi 12"},
        {"version": "22.0", "name": "Delphi 11"},
    ]
    result = service.select_delphi_version("22.0")
    assert result["name"] == "Delphi 11"


def test_select_not_found():
    """版本不存在返回 None"""
    service = DelphiKnowledgeBaseService.__new__(DelphiKnowledgeBaseService)
    service.delphi_versions = [{"version": "22.0", "name": "Delphi 11"}]
    result = service.select_delphi_version("99.0")
    assert result is None


def test_schema_version_read():
    """读取 schema 版本"""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT, updated_at REAL)")
    conn.execute(f"INSERT INTO metadata (key, value) VALUES ('{SCHEMA_VERSION_KEY}', '1')")
    version = get_schema_version_from_db(conn.cursor())
    assert version == 1
    conn.close()


def test_schema_version_old_db():
    """旧库无版本返回 0"""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT, updated_at REAL)")
    version = get_schema_version_from_db(conn.cursor())
    assert version == 0
    conn.close()


def test_schema_version_write():
    """写入 schema 版本"""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT, updated_at REAL)")
    set_schema_version_in_db(conn.cursor(), version=2)
    conn.commit()
    cursor = conn.cursor()
    cursor.execute(f"SELECT value FROM metadata WHERE key = '{SCHEMA_VERSION_KEY}'")
    assert int(cursor.fetchone()[0]) == 2
    conn.close()


def test_check_schema_match():
    """版本匹配返回 True"""
    suppress_logs()
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT, updated_at REAL)")
    conn.execute(f"INSERT INTO metadata (key, value) VALUES ('{SCHEMA_VERSION_KEY}', '{SCHEMA_VERSION}')")
    result = check_schema_version(conn.cursor(), "test")
    assert result is True
    conn.close()


def test_check_schema_old():
    """旧库返回 True"""
    suppress_logs()
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT, updated_at REAL)")
    result = check_schema_version(conn.cursor(), "old")
    assert result is True
    conn.close()


def test_check_schema_mismatch():
    """版本不匹配返回 False"""
    suppress_logs()
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT, updated_at REAL)")
    conn.execute(f"INSERT INTO metadata (key, value) VALUES ('{SCHEMA_VERSION_KEY}', '999')")
    result = check_schema_version(conn.cursor(), "future")
    assert result is False
    conn.close()


if __name__ == "__main__":
    tests = [
        ("版本排序", test_version_sorting),
        ("选择最新版本", test_select_latest_version),
        ("按版本号选择", test_select_by_version),
        ("版本不存在", test_select_not_found),
        ("读取schema版本", test_schema_version_read),
        ("旧库schema版本", test_schema_version_old_db),
        ("写入schema版本", test_schema_version_write),
        ("检查版本匹配", test_check_schema_match),
        ("检查旧库", test_check_schema_old),
        ("检查版本不匹配", test_check_schema_mismatch),
    ]
    
    passed = 0
    for name, func in tests:
        try:
            func()
            print(f"[OK] {name}")
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {name}: {e}")
        except Exception as e:
            print(f"[FAIL] {name}: {type(e).__name__}: {e}")
    
    print(f"\n{passed}/{len(tests)} 通过")
    sys.exit(0 if passed == len(tests) else 1)
