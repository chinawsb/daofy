#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""batch_write edge case tests."""

import sys, os, tempfile, shutil
from pathlib import Path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
import pytest
from src.tools.file_tool import handle_batch_write
from src.utils.file_backup import detect_encoding


def _mf(path, txt):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(txt)


def _ok(r):
    assert r.get("status") == "success", f"expected success, got: {r}"


def _mf_encoded(path, txt, encoding):
    """按指定编码写入文件（用于模拟非 UTF-8 文件）"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(txt.encode(encoding))


# --- Bug 1: content includes original text -> duplicate ---


@pytest.mark.asyncio
async def test_insert_keeps_original_no_dup():
    """[4,5) replace F1, content has F1+new line -> no dup"""
    d = tempfile.mkdtemp(prefix="b1_")
    try:
        f = os.path.join(d, "U.pas")
        _mf(f, "unit U;\ninterface\ntype\n  T=class\n    F1: Integer;\n    F2: String;\n  end;\nimplementation\nend.\n")
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 4, "end_line": 5, "content": "    F1: Integer;\n    F1b: Boolean;", "description": "add"},
        ], "backup": False})
        _ok(r)
        with open(f) as fh:
            c = fh.read()
        assert c.count("F1: Integer") == 1, f"F1 dup:\n{c}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_insert_adjacent_no_dup():
    """adjacent [5,6)+[6,7), content has original -> no dup"""
    d = tempfile.mkdtemp(prefix="b1a_")
    try:
        f = os.path.join(d, "U.pas")
        _mf(f, "unit U;\ninterface\ntype\n  T=class\n    F1: Integer;\n    F2: String;\n    procedure Bar;\n  end;\nimplementation\nend.\n")
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 5, "end_line": 6, "content": "    F2: String;\n    F2b: Boolean;", "description": "add after F2"},
            {"start_line": 6, "end_line": 7, "content": "    procedure Bar;", "description": "keep Bar"},
        ], "backup": False})
        _ok(r)
        with open(f) as fh:
            c = fh.read()
        assert c.count("F2: String") == 1, f"F2 dup:\n{c}"
        assert c.count("procedure Bar") == 1, f"Bar dup:\n{c}"
        assert "F2b: Boolean" in c
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_insert_end_line_none_no_dup():
    """end_line=None, content has original -> no dup, ends with end."""
    d = tempfile.mkdtemp(prefix="b1b_")
    try:
        f = os.path.join(d, "U.pas")
        _mf(f, "unit U;\ninterface\ntype\n  T=class\n    F1: Integer;\n    F2: String;\n  end;\nend.\n")
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 4, "content": "    F1: Integer;\n    F1b: Boolean;\n  end;\nend.", "description": "F1 to EOF"},
        ], "backup": False})
        _ok(r)
        with open(f) as fh:
            c = fh.read()
        assert c.count("F1: Integer") == 1, f"F1 dup:\n{c}"
        assert c.rstrip().endswith("end."), f"no end.:\n{c}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- Bug 2: end. handling ---


@pytest.mark.asyncio
async def test_enddot_after_edit():
    """edit near end, nothing after end."""
    d = tempfile.mkdtemp(prefix="b2_")
    try:
        f = os.path.join(d, "U.pas")
        _mf(f, "unit U;\ninterface\nimplementation\n\nprocedure Foo;\nbegin\nend;\n\nend.\n")
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 4, "end_line": 7, "content": "procedure Foo;\nbegin\n  // work\nend;", "description": "edit Foo"},
        ], "backup": False})
        _ok(r)
        with open(f) as fh:
            c = fh.read()
        rest = c[c.rfind("end.") + 4:].strip()
        assert rest == "", f"after end.:\n{c}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_enddot_adjacent_edits():
    """multiple edits, end. not duplicated"""
    d = tempfile.mkdtemp(prefix="b2a_")
    try:
        f = os.path.join(d, "U.pas")
        _mf(f, "unit U;\ninterface\nimplementation\n\nprocedure A;\nbegin\nend;\n\nprocedure B;\nbegin\nend;\n\nend.\n")
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 4, "end_line": 7, "content": "procedure A;\nbegin\n  // A\nend;", "description": "edit A"},
            {"start_line": 8, "end_line": 11, "content": "procedure B;\nbegin\n  // B\nend;", "description": "edit B"},
        ], "backup": False})
        _ok(r)
        with open(f) as fh:
            c = fh.read()
        rest = c[c.rfind("end.") + 4:].strip()
        assert rest == "", f"after end.:\n{c}"
        assert c.count("end.") == 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_enddot_replace_tail():
    """replace tail including end., content ends with end. -> clean"""
    d = tempfile.mkdtemp(prefix="b2c_")
    try:
        f = os.path.join(d, "U.pas")
        _mf(f, "unit U;\ninterface\nimplementation\n\nprocedure Foo;\nbegin\nend;\n\nend.\n")
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 7, "end_line": 9, "content": "procedure Foo;\nbegin\n  Work;\nend;\n\nend.", "description": "replace tail"},
        ], "backup": False})
        _ok(r)
        with open(f) as fh:
            c = fh.read()
        rest = c[c.rfind("end.") + 4:].strip()
        assert rest == "", f"after end.:\n{c}"
        assert c.count("end.") == 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_enddot_no_trailing_newline():
    """original file no trailing \n -> clean after end."""
    d = tempfile.mkdtemp(prefix="b2d_")
    try:
        f = os.path.join(d, "U.pas")
        _mf(f, "unit U;\ninterface\nimplementation\n\nprocedure Foo;\nbegin\nend;\n\nend.")
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 4, "end_line": 7, "content": "procedure Foo;\nbegin\n  Work;\nend;", "description": "edit Foo"},
        ], "backup": False})
        _ok(r)
        with open(f) as fh:
            c = fh.read()
        rest = c[c.rfind("end.") + 4:].strip()
        assert rest == "", f"after end.:\n{c}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_enddot_delete_empty_before():
    """delete empty line before end. -> end. remains"""
    d = tempfile.mkdtemp(prefix="b2e_")
    try:
        f = os.path.join(d, "U.pas")
        _mf(f, "unit U;\n\ninterface\n\nimplementation\n\nprocedure Foo;\nbegin\nend;\n\nend.\n")
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 9, "end_line": 10, "content": "", "description": "del empty before end."},
        ], "backup": False})
        _ok(r)
        with open(f) as fh:
            c = fh.read()
        rest = c[c.rfind("end.") + 4:].strip()
        assert rest == "", f"after end.:\n{c}"
        assert c.count("end.") == 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_enddot_delete_enddot_line():
    """replace tail including end. -> no orphan code"""
    d = tempfile.mkdtemp(prefix="b2f_")
    try:
        f = os.path.join(d, "U.pas")
        _mf(f, "unit U;\ninterface\nimplementation\n\nprocedure Foo;\nbegin\nend;\n\nend.\n")
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 7, "end_line": 9, "content": "  Work;\nend;\n\nend.", "description": "replace tail incl end."},
        ], "backup": False})
        _ok(r)
        with open(f) as fh:
            c = fh.read()
        rest = c[c.rfind("end.") + 4:].strip()
        assert rest == "", f"after end.:\n{c}"
        assert c.count("end.") == 1
    finally:
        shutil.rmtree(d, ignore_errors=True)

@pytest.mark.asyncio
async def test_sanity_warn_on_dup_first_line():
    """content 首行与被替换行相同 → ⚠️ 警告出现（但写入仍然成功）"""
    d = tempfile.mkdtemp(prefix="warn_")
    try:
        f = os.path.join(d, "U.pas")
        _mf(f, "unit U;\ninterface\ntype\n  T=class\n    F1: Integer;\n  end;\nend.\n")
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 4, "end_line": 5, "content": "    F1: Integer;\n    F1b: Boolean;", "description": "保留F1加字段"},
        ], "backup": False})
        assert r.get("status") == "success", f"应成功但返回了:\n{r}"
        msg = r.get("message", "")
        assert "⚠️" in msg, f"期望警告但未出现:\n{msg}"
        assert "content 首行" in msg, f"错误信息缺少原因:\n{msg}"
        # 文件应有 F1 且无重复
        with open(f) as fh:
            c = fh.read()
        assert c.count("F1: Integer") == 1, f'F1 dup:\n{c}'
        assert "F1b: Boolean" in c, f'缺少 F1b:\n{c}'
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_force_bypasses_dup_first_line():
    """force=true 时跳过 content 首行重复检查"""
    d = tempfile.mkdtemp(prefix="force_")
    try:
        f = os.path.join(d, "U.pas")
        _mf(f, "unit U;\ninterface\ntype\n  T=class\n    F1: Integer;\n  end;\nend.\n")
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 4, "end_line": 5, "content": "    F1: Integer;\n    F1b: Boolean;", "description": "保留F1加字段"},
        ], "backup": False, "force": True})
        assert r.get("status") == "success", f"force=true 应允许写入:\n{r}"
        # 文件应正常写入，无重复
        with open(f) as fh:
            c = fh.read()
        assert c.count("F1: Integer") == 1, f'F1 dup:\n{c}'
        assert "F1b: Boolean" in c, f'缺少 F1b:\n{c}'
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_post_merge_dup_detection():
    """编辑后产生连续重复行 → 阻止写入"""
    d = tempfile.mkdtemp(prefix="dup_merge_")
    try:
        f = os.path.join(d, "U.pas")
        _mf(f, "unit U;\ninterface\ntype\n  T=class\n    F1: Integer;\n    F2: String;\n  end;\nend.\n")
        with open(f) as fh:
            original = fh.read()
        # 两个 edit 相邻且第一个的 content 末尾与第二个的 content 开头相同 → 产生边界重复
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 4, "end_line": 5, "content": "    F1: Integer;\n    Extra: Boolean;", "description": "edit F1"},
            {"start_line": 5, "end_line": 6, "content": "    Extra: Boolean;\n    F2: String;", "description": "edit F2"},
        ], "backup": False})
        assert r.get("status") == "failed", f"应检测到重复行:\n{r}"
        msg = r.get("message", "")
        assert "连续重复" in msg, f"错误信息不匹配:\n{msg}"
        # 文件不应被修改
        with open(f) as fh:
            c = fh.read()
        assert c == original, f"文件被意外修改:\n原内容:\n{original}\n当前:\n{c}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_force_bypasses_post_merge_dup():
    """force=true 时跳过最终结果重复检查"""
    d = tempfile.mkdtemp(prefix="dup_force_")
    try:
        f = os.path.join(d, "U.pas")
        _mf(f, "unit U;\ninterface\ntype\n  T=class\n    F1: Integer;\n    F2: String;\n  end;\nend.\n")
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 4, "end_line": 5, "content": "    F1: Integer;\n    Extra: Boolean;", "description": "edit F1"},
            {"start_line": 5, "end_line": 6, "content": "    Extra: Boolean;\n    F2: String;", "description": "edit F2"},
        ], "backup": False, "force": True})
        assert r.get("status") == "success", f"force=true 应跳过重复检测:\n{r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- Bug 3 (严重): encoding 不一致时静默改写 ---
# AI Agent 报告: "将 Unicode16LE 的内容，写入了 UTF-8 编码的文件中"
# 根因: 用户/AI 误指定 encoding, 旧逻辑直接用错码编码, 文件被改写
# 修复: 显式指定 encoding 时内部自动转码 (read=detected, write=user_specified)


@pytest.mark.asyncio
async def test_auto_mode_preserves_utf8():
    """encoding='auto' (默认) 时 UTF-8 文件保持 UTF-8 编码, 无转码提示"""
    d = tempfile.mkdtemp(prefix="enc_auto_")
    try:
        f = os.path.join(d, "U.pas")
        _mf(f, "unit U;\ninterface\nimplementation\nend.\n")
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 2, "end_line": 3, "content": "implementation\n\nprocedure Foo;\nbegin\nend;", "description": "edit"},
        ], "backup": False, "encoding": "auto"})
        _ok(r)
        msg = r.get("message", "")
        assert "encoding: utf-8" in msg, f"应显示 utf-8 编码:\n{msg}"
        assert "transcoded" not in msg, f"auto 模式不应有转码提示:\n{msg}"
        # 文件仍为 UTF-8
        assert detect_encoding(f) == "utf-8"
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_utf8_to_utf16le_transcode():
    """[转码] UTF-8 文件 + encoding='utf-16-le' → 内部转码, 文件变为 UTF-16LE"""
    d = tempfile.mkdtemp(prefix="enc_trans_")
    try:
        f = os.path.join(d, "U.pas")
        _mf(f, "unit U;\ninterface\nimplementation\nend.\n")
        assert detect_encoding(f) == "utf-8"

        # 显式指定 utf-16-le, 触发转码
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 2, "end_line": 3, "content": "implementation\n\nprocedure Foo;\nbegin\nend;", "description": "transcode"},
        ], "backup": False, "encoding": "utf-16-le"})
        _ok(r)
        msg = r.get("message", "")
        # 应该有转码提示 (新格式: "ℹ transcoded: utf-8 → utf-16-le")
        assert "transcoded" in msg, f"应有转码提示:\n{msg}"
        assert "utf-8" in msg and "utf-16-le" in msg, f"应包含两种编码:\n{msg}"
        # 验证文件被成功转码为 UTF-16-LE
        assert detect_encoding(f) == "utf-16-le", f"文件应被转码为 utf-16-le, 实际: {detect_encoding(f)}"
        # 验证内容可正确以 UTF-16-LE 解读
        with open(f, 'r', encoding='utf-16-le') as fh:
            content = fh.read()
        assert "procedure Foo" in content
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_utf16le_to_utf8_transcode():
    """[转码] UTF-16-LE 文件 + encoding='utf-8' → 内部转码, 文件变为 UTF-8"""
    d = tempfile.mkdtemp(prefix="enc_back_")
    try:
        f = os.path.join(d, "U.pas")
        # 创建 UTF-16-LE 无 BOM 文件
        text = "unit U;\ninterface\nimplementation\nend.\n"
        _mf_encoded(f, text, "utf-16-le")
        assert detect_encoding(f) == "utf-16-le"

        # 显式指定 utf-8, 触发转码
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 2, "end_line": 3, "content": "implementation\n\nprocedure Foo;\nbegin\nend;", "description": "transcode back"},
        ], "backup": False, "encoding": "utf-8"})
        _ok(r)
        # 验证文件被成功转码为 UTF-8
        assert detect_encoding(f) == "utf-8", f"文件应被转码为 utf-8, 实际: {detect_encoding(f)}"
        # 验证内容可正确以 UTF-8 解读
        with open(f, 'r', encoding='utf-8') as fh:
            content = fh.read()
        assert "procedure Foo" in content
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_utf16le_explicit_preserved():
    """UTF-16-LE 文件 + encoding='utf-16-le' (匹配) → 保持 UTF-16-LE, 无转码提示"""
    d = tempfile.mkdtemp(prefix="enc_keep_")
    try:
        f = os.path.join(d, "U.pas")
        text = "unit U;\ninterface\nimplementation\nend.\n"
        _mf_encoded(f, text, "utf-16-le")
        assert detect_encoding(f) == "utf-16-le"

        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 2, "end_line": 3, "content": "implementation\n\nprocedure Foo;\nbegin\nend;", "description": "edit"},
        ], "backup": False, "encoding": "utf-16-le"})
        _ok(r)
        msg = r.get("message", "")
        # 不应有转码提示（编码匹配）
        assert "转码" not in msg, f"编码匹配时不应有转码提示:\n{msg}"
        # 文件仍为 UTF-16-LE
        assert detect_encoding(f) == "utf-16-le"
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_utf8_sig_treated_as_utf8():
    """utf-8-sig 与 utf-8 视为兼容（同 utf-8 家族）, 不应触发转码提示"""
    d = tempfile.mkdtemp(prefix="enc_sig_")
    try:
        f = os.path.join(d, "U.pas")
        # 写入带 BOM 的 UTF-8 文件
        with open(f, 'wb') as fh:
            fh.write(b'\xef\xbb\xbf' + b'unit U;\ninterface\nimplementation\nend.\n')
        assert detect_encoding(f) == "utf-8-sig"

        # 显式指定 utf-8 (sig 视为 utf-8 的兼容变体) — 仅修改一个非重复行
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 1, "end_line": 2, "content": "interface\n\nuses SysUtils;", "description": "edit"},
        ], "backup": False, "encoding": "utf-8"})
        _ok(r)
        msg = r.get("message", "")
        # utf-8-sig 与 utf-8 视为兼容, 不应有转码提示
        assert "转码" not in msg, f"utf-8-sig ↔ utf-8 不应触发转码:\n{msg}"
        # 文件仍可正确读出
        with open(f, 'r', encoding='utf-8-sig') as fh:
            content = fh.read()
        assert "uses SysUtils" in content
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.asyncio
async def test_ai_bug_scenario_no_longer_corrupts():
    """
    [回归] AI Agent bug 场景: 文件是 UTF-8, AI 错误指定 encoding='utf-16-le'.
    修复前: 文件被改写为 UTF-16LE, 内容被错误编码 (AI 报告的 bug).
    修复后: 内部转码, 文件按用户指定的编码写出, 但内容仍正确可读.
    """
    d = tempfile.mkdtemp(prefix="ai_bug_")
    try:
        f = os.path.join(d, "U.pas")
        # 原文件是 UTF-8
        original = "unit U;\ninterface\nimplementation\nend.\n"
        _mf(f, original)
        assert detect_encoding(f) == "utf-8"

        # AI 错误指定 utf-16-le (但提供了正确的 Python str 内容)
        correct_content = "implementation\n\nprocedure Foo;\nbegin\n  Work;\nend;"
        r = await handle_batch_write({"file_path": f, "edits": [
            {"start_line": 2, "end_line": 3, "content": correct_content, "description": "AI edit"},
        ], "backup": False, "encoding": "utf-16-le"})
        _ok(r)

        # 修复后行为: 文件被转码为 utf-16-le, 但内容仍正确
        assert detect_encoding(f) == "utf-16-le"
        with open(f, 'r', encoding='utf-16-le') as fh:
            content = fh.read()
        # 验证内容没有变成 'u\x00n\x00i\x00t\x00' 式的乱码
        assert "procedure Foo" in content
        assert "Work" in content
        # 不应有内嵌的 \x00 (那是 UTF-16-LE 编码原始 ASCII 的特征, 表明内容被错编码)
        assert "\x00" not in content, f"内容含 \\x00, 表明被错编码:\n{content!r}"
    finally:
        shutil.rmtree(d, ignore_errors=True)

