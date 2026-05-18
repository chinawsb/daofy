#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试文件备份工具 — src/utils/file_backup.py

覆盖:
  - create_backup: 新文件/已存在文件/文件不存在/编码检测
  - list_backups: 有备份/无备份/版本排序
  - restore_backup: 恢复最新版/指定版本/版本不存在
  - detect_encoding: UTF-8/GBK/UTF-16/UTF-8-BOM
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.file_backup import (
    create_backup, list_backups, restore_backup, detect_encoding
)


# ============================================================
# Fixtures
# ============================================================

def _make_temp_file(content: str = "unit Test;\nbegin\nend.\n",
                    encoding: str = "utf-8") -> str:
    """创建临时文件并返回路径"""
    fd, path = tempfile.mkstemp(suffix=".pas")
    os.close(fd)
    with open(path, "w", encoding=encoding) as f:
        f.write(content)
    return path


# ============================================================
# detect_encoding
# ============================================================

def test_detect_encoding_utf8():
    path = _make_temp_file("hello world", "utf-8")
    try:
        enc = detect_encoding(path)
        assert enc == "utf-8", f"expected utf-8, got {enc}"
    finally:
        os.unlink(path)


def test_detect_encoding_gbk():
    # GBK 编码的中文字符
    gbk_bytes = "中文测试".encode("gbk")
    fd, path = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(gbk_bytes)
        enc = detect_encoding(path)
        assert enc == "gbk", f"expected gbk, got {enc}"
    finally:
        os.unlink(path)


def test_detect_encoding_utf16():
    utf16_bytes = "hello".encode("utf-16-le")
    fd, path = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            # utf-16 BOM
            f.write(b'\xff\xfe' + utf16_bytes)
        enc = detect_encoding(path)
        assert enc == "utf-16", f"expected utf-16, got {enc}"
    finally:
        os.unlink(path)


def test_detect_encoding_utf8_bom():
    fd, path = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(b'\xef\xbb\xbfunit Test;')
        enc = detect_encoding(path)
        assert enc == "utf-8-sig", f"expected utf-8-sig, got {enc}"
    finally:
        os.unlink(path)


def test_detect_encoding_nonexistent_file():
    enc = detect_encoding(r"C:\nonexistent\file.pas")
    assert enc == "utf-8", "should fallback to utf-8"


# ============================================================
# create_backup
# ============================================================

def test_create_backup_new_file():
    path = _make_temp_file("unit Test;\nbegin\nend.\n")
    history_dir = os.path.join(os.path.dirname(path), "__history")
    try:
        bp = create_backup(path)
        assert bp is not None, "backup path should not be None"
        assert os.path.isfile(bp), f"backup file not found: {bp}"
        # 验证命名: filename.~1~
        base = os.path.basename(path)
        expected = os.path.join(os.path.dirname(path), "__history", f"{base}.~1~")
        assert bp == expected, f"unexpected backup path: {bp}"
    finally:
        shutil.rmtree(history_dir, ignore_errors=True)
        os.unlink(path)


def test_create_backup_version_increment():
    path = _make_temp_file("version1")
    history_dir = os.path.join(os.path.dirname(path), "__history")
    try:
        bp1 = create_backup(path)
        assert bp1.endswith(".~1~")

        # 修改文件后再次备份
        with open(path, "w") as f:
            f.write("version2")
        bp2 = create_backup(path)
        assert bp2.endswith(".~2~"), f"expected .~2~, got {bp2}"

        # 第三次
        with open(path, "w") as f:
            f.write("version3")
        bp3 = create_backup(path)
        assert bp3.endswith(".~3~"), f"expected .~3~, got {bp3}"
    finally:
        shutil.rmtree(history_dir, ignore_errors=True)
        os.unlink(path)


def test_create_backup_file_not_exist():
    bp = create_backup(r"C:\nonexistent\file.pas")
    assert bp is None, "should return None for nonexistent file"


def test_create_backup_preserves_content():
    original = "unit Test;\nconst ANSWER = 42;\nbegin\nend.\n"
    path = _make_temp_file(original)
    history_dir = os.path.join(os.path.dirname(path), "__history")
    try:
        bp = create_backup(path)
        with open(bp, "r") as f:
            backed = f.read()
        assert backed == original, "backup content mismatch"
    finally:
        shutil.rmtree(history_dir, ignore_errors=True)
        os.unlink(path)


# ============================================================
# list_backups
# ============================================================

def test_list_backups_empty():
    path = _make_temp_file("hello")
    try:
        backups = list_backups(path)
        assert backups == [], f"expected empty list, got {backups}"
    finally:
        os.unlink(path)


def test_list_backups_multiple():
    path = _make_temp_file("v1")
    history_dir = os.path.join(os.path.dirname(path), "__history")
    try:
        create_backup(path)
        with open(path, "w") as f:
            f.write("v2")
        create_backup(path)
        with open(path, "w") as f:
            f.write("v3")
        create_backup(path)

        backups = list_backups(path)
        assert len(backups) == 3, f"expected 3 backups, got {len(backups)}"
        # 按版本降序
        versions = [b["version"] for b in backups]
        assert versions == [3, 2, 1], f"expected [3,2,1], got {versions}"
        for b in backups:
            assert "path" in b
            assert "size" in b
            assert "mtime" in b
    finally:
        shutil.rmtree(history_dir, ignore_errors=True)
        os.unlink(path)


def test_list_backups_nonexistent_dir():
    path = r"C:\nonexistent\file.pas"
    backups = list_backups(path)
    assert backups == []


# ============================================================
# restore_backup
# ============================================================

def test_restore_backup_latest():
    path = _make_temp_file("original")
    history_dir = os.path.join(os.path.dirname(path), "__history")
    try:
        create_backup(path)
        # 修改文件
        with open(path, "w") as f:
            f.write("modified")
        # 再备份一次（restore_backup 会先备份当前版本）
        create_backup(path)
        # 修改内容并验证
        with open(path, "w") as f:
            f.write("lost")

        bp = restore_backup(path)  # 恢复到最新备份
        assert bp is not None, "restore should succeed"
        with open(path, "r") as f:
            content = f.read()
        assert content == "modified", f"expected 'modified', got '{content}'"
    finally:
        shutil.rmtree(history_dir, ignore_errors=True)
        os.unlink(path)


def test_restore_backup_specific_version():
    path = _make_temp_file("v1")
    history_dir = os.path.join(os.path.dirname(path), "__history")
    try:
        create_backup(path)  # v1
        with open(path, "w") as f:
            f.write("v2")
        create_backup(path)  # v2
        with open(path, "w") as f:
            f.write("v3")

        bp = restore_backup(path, version=1)
        assert bp is not None
        with open(path, "r") as f:
            content = f.read()
        assert content == "v1", f"expected 'v1', got '{content}'"
    finally:
        shutil.rmtree(history_dir, ignore_errors=True)
        os.unlink(path)


def test_restore_backup_version_not_found():
    path = _make_temp_file("hello")
    history_dir = os.path.join(os.path.dirname(path), "__history")
    try:
        create_backup(path)
        bp = restore_backup(path, version=99)
        assert bp is None, "should return None for nonexistent version"
    finally:
        shutil.rmtree(history_dir, ignore_errors=True)
        os.unlink(path)


def test_restore_backup_no_backups():
    path = _make_temp_file("hello")
    try:
        bp = restore_backup(path)
        assert bp is None, "should return None when no backups exist"
    finally:
        os.unlink(path)


# ============================================================
# Edge cases
# ============================================================

def test_backup_file_with_spaces():
    """文件名含空格"""
    tmp_dir = tempfile.mkdtemp()
    path = os.path.join(tmp_dir, "my unit.pas")
    with open(path, "w", encoding="utf-8") as f:
        f.write("unit Test;")
    try:
        bp = create_backup(path)
        assert bp is not None
        assert os.path.isfile(bp)
        assert "my unit.pas.~1~" in bp
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# 补充测试：编码检测 + 边界场景
# ============================================================


def test_detect_encoding_utf16_le_no_bom():
    """UTF-16 LE 无 BOM 应被检测为 utf-16-le"""
    # ASCII 内容 — 奇数位集中出现空字节
    text = "unit Test;\nbegin\nend.\n"
    utf16_bytes = text.encode('utf-16-le')
    fd, path = tempfile.mkstemp(suffix=".pas")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(utf16_bytes)
        enc = detect_encoding(path)
        assert enc == "utf-16-le", f"expected utf-16-le, got {enc}"
        # 验证解码正确
        with open(path, 'r', encoding=enc) as f:
            assert "unit Test" in f.read()
    finally:
        os.unlink(path)


def test_detect_encoding_utf16_be_no_bom():
    """UTF-16 BE 无 BOM 应被检测为 utf-16-be"""
    text = "unit Test;\nbegin\nend.\n"
    utf16_bytes = text.encode('utf-16-be')
    fd, path = tempfile.mkstemp(suffix=".pas")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(utf16_bytes)
        enc = detect_encoding(path)
        assert enc == "utf-16-be", f"expected utf-16-be, got {enc}"
        # 验证解码正确
        with open(path, 'r', encoding=enc) as f:
            assert "unit Test" in f.read()
    finally:
        os.unlink(path)


def test_detect_encoding_utf16_mixed_chinese_no_bom():
    """UTF-16 LE 含中文无 BOM — 中文高低字节均非空，但连续 ASCII 段产生密集的空字节"""
    text = "unit Test;\n// 中文注释\nend.\n"
    utf16_bytes = text.encode('utf-16-le')
    fd, path = tempfile.mkstemp(suffix=".pas")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(utf16_bytes)
        enc = detect_encoding(path)
        # 中文 UTF-16 可能降低空字节占比，检测可能回退到 GBK
        # 但只要能正确解码即可
        assert enc in ("utf-16-le", "utf-16", "gbk", "utf-8"), f"unexpected: {enc}"
        with open(path, 'r', encoding=enc) as f:
            content = f.read()
            assert "unit Test" in content
            assert "中文" in content
    finally:
        os.unlink(path)


def test_detect_encoding_empty_file():
    """空文件应返回 utf-8"""
    fd, path = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        enc = detect_encoding(path)
        assert enc == "utf-8", f"expected utf-8 for empty file, got {enc}"
    finally:
        os.unlink(path)


def test_detect_encoding_binary_data():
    """二进制（非文本）文件应回退到 utf-8（不会报错）"""
    fd, path = tempfile.mkstemp(suffix=".bin")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(b'\x00\x01\x02\xff\xfe\xfd\xfc\xfb')
        enc = detect_encoding(path)
        # 二进制数据通常解码失败，回退到 utf-8
        assert enc == "utf-8", f"expected utf-8 fallback, got {enc}"
    finally:
        os.unlink(path)


def test_detect_encoding_utf8_with_unicode_chars():
    """UTF-8 含 Unicode 字符（非 ASCII）"""
    fd, path = tempfile.mkstemp(suffix=".pas")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("unit Test;\n// © 2026 测试\nend.\n")
        enc = detect_encoding(path)
        assert enc == "utf-8", f"expected utf-8, got {enc}"
    finally:
        os.unlink(path)


def test_detect_encoding_utf8_bom_only_ascii():
    """UTF-8 BOM + 纯 ASCII 内容"""
    fd, path = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(b'\xef\xbb\xbfHello World')
        enc = detect_encoding(path)
        assert enc == "utf-8-sig", f"expected utf-8-sig, got {enc}"
    finally:
        os.unlink(path)


def test_create_backup_in_subdir():
    """备份应在源文件同级目录创建 __history"""
    tmp_dir = tempfile.mkdtemp()
    sub_dir = os.path.join(tmp_dir, "src", "units")
    os.makedirs(sub_dir)
    path = os.path.join(sub_dir, "Unit1.pas")
    with open(path, "w", encoding="utf-8") as f:
        f.write("unit Unit1;")
    try:
        bp = create_backup(path)
        assert bp is not None
        # __history 应该在 sub_dir 下
        expected_history = os.path.join(sub_dir, "__history")
        assert os.path.isdir(expected_history)
        assert bp.startswith(expected_history)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_list_backups_with_corrupt_files():
    """备份目录中有损坏文件（命名不规范）应被跳过"""
    tmp_dir = tempfile.mkdtemp()
    path = os.path.join(tmp_dir, "TestUnit.pas")
    history_dir = os.path.join(tmp_dir, "__history")
    os.makedirs(history_dir)
    with open(path, "w", encoding="utf-8") as f:
        f.write("unit TestUnit;")
    try:
        # 创建规范备份
        create_backup(path)
        # 创建损坏文件（命名不规范）
        with open(os.path.join(history_dir, "TestUnit.pas.~bad~"), "w") as f:
            f.write("garbage")
        with open(os.path.join(history_dir, "random_file.txt"), "w") as f:
            f.write("noise")
        # 创建第二个规范备份
        with open(path, "w", encoding="utf-8") as f:
            f.write("unit TestUnit; // v2")
        create_backup(path)

        backups = list_backups(path)
        assert len(backups) == 2, f"expected 2 valid backups, got {len(backups)}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_restore_backup_creates_backup_first():
    """restore_backup 应在恢复前先创建当前文件的备份（安全网）"""
    tmp_dir = tempfile.mkdtemp()
    path = os.path.join(tmp_dir, "TestUnit.pas")
    history_dir = os.path.join(tmp_dir, "__history")
    with open(path, "w", encoding="utf-8") as f:
        f.write("v1 original")
    try:
        # 创建备份
        create_backup(path)
        # 修改文件
        with open(path, "w", encoding="utf-8") as f:
            f.write("v2 modified")
        # 恢复前应该有 1 个备份
        assert len(list_backups(path)) == 1
        # 恢复
        restore_backup(path)
        # 恢复后应有 2 个备份（原来的 + 恢复前自动创建的当前文件备份）
        backups = list_backups(path)
        assert len(backups) == 2, f"expected 2 backups after restore, got {len(backups)}"
        # 文件内容为 v1
        with open(path, "r") as f:
            assert f.read() == "v1 original"
    finally:
        shutil.rmtree(history_dir, ignore_errors=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)
