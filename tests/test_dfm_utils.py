#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 DFM 转换工具 — src/tools/dfm_utils.py

覆盖:
  - _detect_dfm_format: 文本/二进制 DFM 检测
  - convert_dfm: 文本↔二进制转换（条件：需要 Delphi 编译器）
  - ensure_dfm_text / ensure_dfm_binary
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.tools.dfm_utils import (
    _detect_dfm_format, convert_dfm, ensure_dfm_text, ensure_dfm_binary,
    set_compiler_path, _find_dcc32
)


# ============================================================
# 文本 DFM 样例
# ============================================================

TEXT_DFM_SIMPLE = """\
object Form1: TForm1
  Left = 0
  Top = 0
  Caption = 'Hello'
  object Button1: TButton
    Left = 10
    Top = 10
    Caption = 'Click Me'
  end
end
"""

TEXT_DFM_INHERITED = """\
inherited Form1: TForm1
  Caption = 'Inherited Form'
end
"""


# ============================================================
# _detect_dfm_format
# ============================================================

def test_detect_text_dfm_object():
    fd, path = tempfile.mkstemp(suffix=".dfm")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(TEXT_DFM_SIMPLE)
        fmt = _detect_dfm_format(path)
        assert fmt == "text", f"expected text, got {fmt}"
    finally:
        os.unlink(path)


def test_detect_text_dfm_inherited():
    fd, path = tempfile.mkstemp(suffix=".dfm")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(TEXT_DFM_INHERITED)
        fmt = _detect_dfm_format(path)
        assert fmt == "text", f"expected text, got {fmt}"
    finally:
        os.unlink(path)


def test_detect_binary_dfm():
    """二进制 DFM 通常以非文本开头"""
    fd, path = tempfile.mkstemp(suffix=".dfm")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(b'\xff\xff\xff\xff' + b'\x00' * 28)
        fmt = _detect_dfm_format(path)
        assert fmt == "binary", f"expected binary, got {fmt}"
    finally:
        os.unlink(path)


def test_detect_empty_file():
    """空文件开始不是 object/inherited，属于 binary"""
    fd, path = tempfile.mkstemp(suffix=".dfm")
    os.close(fd)
    try:
        fmt = _detect_dfm_format(path)
        assert fmt == "binary", f"expected binary for empty file, got {fmt}"
    finally:
        os.unlink(path)


def test_detect_nonexistent_file():
    with pytest.raises(FileNotFoundError):
        _detect_dfm_format(r"C:\nonexistent.dfm")


def test_detect_dfm_with_leading_spaces():
    """文本 DFM 开头可能包含缩进"""
    fd, path = tempfile.mkstemp(suffix=".dfm")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("  object Form1: TForm1\n  end\n")
        fmt = _detect_dfm_format(path)
        assert fmt == "text", f"expected text, got {fmt}"
    finally:
        os.unlink(path)


# ============================================================
# convert_dfm — 条件测试（需要 Delphi 编译器）
# ============================================================

def _has_delphi_compiler() -> bool:
    """检查是否安装了可用的 Delphi 编译器（dcc32.exe 存在且可运行）"""
    dcc = _find_dcc32()
    if not dcc:
        return False
    # 验证编译器可以运行
    try:
        import subprocess
        r = subprocess.run(
            [dcc, "--version"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return r.returncode in (0, 1)
    except Exception:
        return False


@pytest.mark.skipif(not _has_delphi_compiler(), reason="需要 Delphi 编译器")
@pytest.mark.asyncio
async def test_convert_text_to_binary_and_back():
    """文本 DFM → 二进制 → 文本，验证往返一致"""
    tmp_dir = tempfile.mkdtemp()
    text_path = os.path.join(tmp_dir, "source.dfm")
    bin_path = os.path.join(tmp_dir, "out_binary.dfm")
    roundtrip_path = os.path.join(tmp_dir, "roundtrip.dfm")
    try:
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(TEXT_DFM_SIMPLE)

        # 文本 → 二进制
        r1 = await convert_dfm(text_path, bin_path, to_text=False)
        assert r1["success"], f"to-binary failed: {r1['message']}"
        assert r1["target_format"] == "binary"

        # 验证输出是二进制
        fmt = _detect_dfm_format(bin_path)
        assert fmt == "binary", f"expected binary, got {fmt}"

        # 二进制 → 文本
        r2 = await convert_dfm(bin_path, roundtrip_path, to_text=True)
        assert r2["success"], f"to-text failed: {r2['message']}"
        assert r2["target_format"] == "text"

        # 验证内容一致（忽略空白差异）
        with open(text_path, "r") as f:
            original_lines = [l.rstrip() for l in f.readlines()]
        with open(roundtrip_path, "r") as f:
            roundtrip_lines = [l.rstrip() for l in f.readlines()]

        assert len(original_lines) == len(roundtrip_lines), \
            f"line count mismatch: {len(original_lines)} vs {len(roundtrip_lines)}"
        for i, (o, r) in enumerate(zip(original_lines, roundtrip_lines)):
            assert o == r, f"line {i+1} mismatch:\n  original: {o!r}\n  restored: {r!r}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.skipif(not _has_delphi_compiler(), reason="需要 Delphi 编译器")
@pytest.mark.asyncio
async def test_convert_inherited_dfm():
    """inherited 风格的 DFM 也能正确转换"""
    tmp_dir = tempfile.mkdtemp()
    text_path = os.path.join(tmp_dir, "inherited.dfm")
    bin_path = os.path.join(tmp_dir, "inherited_bin.dfm")
    try:
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(TEXT_DFM_INHERITED)

        r = await convert_dfm(text_path, bin_path, to_text=False)
        assert r["success"], f"failed: {r['message']}"

        # 验证转成了二进制
        fmt = _detect_dfm_format(bin_path)
        assert fmt == "binary", f"expected binary, got {fmt}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_convert_already_text():
    """已经是文本格式的 DFM 转换为文本应报错"""
    tmp_dir = tempfile.mkdtemp()
    text_path = os.path.join(tmp_dir, "already_text.dfm")
    out_path = os.path.join(tmp_dir, "out.dfm")
    try:
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(TEXT_DFM_SIMPLE)
        r = await convert_dfm(text_path, out_path, to_text=True)
        assert not r["success"]
        assert "已经是文本格式" in r["message"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_convert_file_not_found():
    r = await convert_dfm(r"C:\nonexistent.dfm", r"C:\out.dfm", to_text=True)
    assert not r["success"]
    assert "不存在" in r["message"]


# ============================================================
# ensure_dfm_text / ensure_dfm_binary
# ============================================================

@pytest.mark.asyncio
async def test_ensure_dfm_text_already_text():
    """已为文本应返回原路径"""
    tmp_dir = tempfile.mkdtemp()
    path = os.path.join(tmp_dir, "test.dfm")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(TEXT_DFM_SIMPLE)
        result = await ensure_dfm_text(path)
        assert result == path, "should return original path for text DFM"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_ensure_dfm_text_binary():
    """二进制 DFM 应转换并返回临时路径"""
    if not _has_delphi_compiler():
        pytest.skip("需要 Delphi 编译器")
    tmp_dir = tempfile.mkdtemp()
    text_path = os.path.join(tmp_dir, "source.dfm")
    bin_path = os.path.join(tmp_dir, "source_bin.dfm")
    try:
        # 先创建文本 DFM
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(TEXT_DFM_SIMPLE)
        # 转换为二进制作为测试输入
        r = await convert_dfm(text_path, bin_path, to_text=False)
        assert r["success"]

        # 对二进制文件调用 ensure_dfm_text
        result = await ensure_dfm_text(bin_path)
        assert result is not None
        assert result != bin_path, "should return different path for binary"
        # 验证内容是文本 DFM
        with open(result, "r") as f:
            content = f.read()
        assert "object Form1" in content
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.skipif(not _has_delphi_compiler(), reason="需要 Delphi 编译器")
@pytest.mark.asyncio
async def test_ensure_dfm_binary():
    tmp_dir = tempfile.mkdtemp()
    text_path = os.path.join(tmp_dir, "test.dfm")
    bin_path = os.path.join(tmp_dir, "test_bin.dfm")
    try:
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(TEXT_DFM_SIMPLE)

        ok = await ensure_dfm_binary(text_path, bin_path)
        assert ok, "binary conversion should succeed"
        fmt = _detect_dfm_format(bin_path)
        assert fmt == "binary", f"expected binary output, got {fmt}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
