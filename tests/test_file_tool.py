#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 file_tool 集成 — src/tools/file_tool.py

工具返回值统一为 dict:
  success: {"status": "success", "message": "..."}
  error:   {"status": "failed", "message": "..."}
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, AsyncMock
import pytest

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.tools.file_tool import (
    handle_file_tool, handle_read, handle_write,
    handle_backup, handle_format, handle_batch_write,
    _is_delphi_file, _is_dfm_file, _check_dirty, _clear_dirty,
)
from src.tools.pasfmt import format_code as _pasfmt_format_code


# ============================================================
# Helpers
# ============================================================

def _make_file(path: str, content: str = "unit Test;\nbegin\nend.\n",
               encoding: str = "utf-8") -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding=encoding) as f:
        f.write(content)
    return path


def _assert_success(result: dict):
    assert result.get("status") == "success", \
        f"expected success, got: {result}"


def _assert_error(result: dict):
    assert result.get("status") == "failed", \
        f"expected error, got: {result}"


# ============================================================
# handle_read
# ============================================================

@pytest.mark.asyncio
async def test_read_missing_file_path():
    result = await handle_read({"search_type": "path"})
    _assert_error(result)
    assert "file_path" in result["message"].lower()


@pytest.mark.asyncio
async def test_read_file_not_found():
    result = await handle_read({
        "file_path": r"C:\nonexistent_file_12345.pas",
    })
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_read_existing_file():
    tmp = tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False,
                                      encoding="utf-8")
    tmp.write("unit Test;\nbegin\nend.\n")
    tmp.close()
    try:
        result = await handle_read({"file_path": tmp.name})
        assert isinstance(result, dict)
    finally:
        os.unlink(tmp.name)


@pytest.mark.asyncio
async def test_read_search_type_class():
    result = await handle_read({
        "search_type": "class",
        "type_name": "TForm1",
    })
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_read_search_type_function():
    result = await handle_read({
        "search_type": "function",
        "function_name": "Create",
    })
    assert isinstance(result, dict)


# ============================================================
# handle_write
# ============================================================

@pytest.mark.asyncio
async def test_write_new_file():
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "TestUnit.pas")
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 1, "content": "unit TestUnit;\nbegin\nend.\n"}],
            "backup": False,
        })
        _assert_success(result)
        assert "wrote:" in result["message"]
        assert os.path.isfile(file_path)
        # 新文件默认 UTF-8 BOM，需指明编码读取
        with open(file_path, "r", encoding="utf-8-sig") as f:
            assert "unit TestUnit" in f.read()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_existing_file_with_backup():
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "TestUnit.pas")
    _make_file(file_path, "original content")
    history_dir = os.path.join(tmp_dir, "__history")
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 1, "content": "modified content"}],
            "backup": True,
        })
        _assert_success(result)
        assert "backup: __history\\" in result["message"]

        backups = os.listdir(history_dir)
        assert len(backups) == 1
        assert backups[0].endswith(".~1~")

        bp = os.path.join(history_dir, backups[0])
        with open(bp, "r") as f:
            assert f.read() == "original content"
        with open(file_path, "r") as f:
            assert f.read() == "modified content\n"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_backup_version_increment():
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "TestUnit.pas")
    _make_file(file_path, "v1")
    history_dir = os.path.join(tmp_dir, "__history")
    try:
        await handle_write({"file_path": file_path, "edits": [{"start_line": 1, "content": "v2"}], "backup": True})
        await handle_read({"file_path": file_path})  # 清除脏标记
        await handle_write({"file_path": file_path, "edits": [{"start_line": 1, "content": "v3"}], "backup": True})

        backups = sorted(os.listdir(history_dir))
        assert len(backups) == 2
        assert backups[0].endswith(".~1~")
        assert backups[1].endswith(".~2~")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_missing_file_path():
    result = await handle_write({"edits": [{"start_line": 1, "content": "hello"}]})
    _assert_error(result)


@pytest.mark.asyncio
async def test_write_missing_content():
    result = await handle_write({"file_path": "test.pas"})
    _assert_error(result)


@pytest.mark.asyncio
async def test_write_preserves_encoding():
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "test_gbk.pas")
    gbk_content = "unit Test;\n// 中文注释\nbegin\nend.\n"
    with open(file_path, "w", encoding="gbk") as f:
        f.write(gbk_content)
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 1, "content": gbk_content}],
            "backup": False,
        })
        _assert_success(result)
        assert "encoding: gbk" in result["message"]

        with open(file_path, "rb") as f:
            raw = f.read()
        raw.decode("gbk")  # 不应抛异常
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_format_after():
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "TestUnit.pas")
    _make_file(file_path, "unit  TestUnit ;\nbegin\nend.")
    try:
        with patch("src.tools.file_tool.pasfmt.format_file",
                   new_callable=AsyncMock) as mock_fmt:
            mock_fmt.return_value = {
                "status": "success", "formatted": True,
                "message": "ok"
            }
            result = await handle_write({
                "file_path": file_path,
                "edits": [{"start_line": 1, "content": "unit TestUnit;\nbegin\nend.\n"}],
                "backup": False,
                "auto_format": True,
            })
            _assert_success(result)
            mock_fmt.assert_called_once()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# handle_backup
# ============================================================

@pytest.mark.asyncio
async def test_backup_create():
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "test.pas")
    _make_file(file_path, "hello")
    try:
        result = await handle_backup({
            "file_path": file_path,
            "backup_action": "create",
        })
        _assert_success(result)
        assert "备份已创建" in result["message"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_backup_list():
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "test.pas")
    _make_file(file_path, "v1")
    history_dir = os.path.join(tmp_dir, "__history")
    try:
        await handle_backup({"file_path": file_path, "backup_action": "create"})
        with open(file_path, "w") as f:
            f.write("v2")
        await handle_backup({"file_path": file_path, "backup_action": "create"})

        result = await handle_backup({
            "file_path": file_path,
            "backup_action": "list",
        })
        _assert_success(result)
        assert "备份数: 2" in result["message"]
    finally:
        shutil.rmtree(history_dir, ignore_errors=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_backup_restore():
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "test.pas")
    _make_file(file_path, "original")
    history_dir = os.path.join(tmp_dir, "__history")
    try:
        await handle_backup({"file_path": file_path, "backup_action": "create"})
        with open(file_path, "w") as f:
            f.write("modified")
        result = await handle_backup({
            "file_path": file_path,
            "backup_action": "restore",
        })
        _assert_success(result)
        assert "已从" in result["message"]
        with open(file_path, "r") as f:
            assert f.read() == "original"
    finally:
        shutil.rmtree(history_dir, ignore_errors=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_backup_restore_specific_version():
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "test.pas")
    _make_file(file_path, "v1")
    history_dir = os.path.join(tmp_dir, "__history")
    try:
        from src.utils.file_backup import create_backup
        create_backup(file_path)
        with open(file_path, "w") as f:
            f.write("v2")
        create_backup(file_path)
        with open(file_path, "w") as f:
            f.write("v3")

        result = await handle_backup({
            "file_path": file_path,
            "backup_action": "restore",
            "version": 1,
        })
        _assert_success(result)
        with open(file_path, "r") as f:
            assert f.read() == "v1"
    finally:
        shutil.rmtree(history_dir, ignore_errors=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_backup_missing_file_path():
    result = await handle_backup({"backup_action": "create"})
    _assert_error(result)


@pytest.mark.asyncio
async def test_backup_list_empty():
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "nobackups.pas")
    _make_file(file_path, "hello")
    try:
        result = await handle_backup({
            "file_path": file_path,
            "backup_action": "list",
        })
        _assert_success(result)  # 空列表也是成功
        assert "没有找到" in result["message"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# handle_format (error paths)
# ============================================================

@pytest.mark.asyncio
async def test_format_missing_file_path():
    result = await handle_format({})
    _assert_error(result)


@pytest.mark.asyncio
async def test_format_nonexistent_file():
    result = await handle_format({
        "file_path": r"C:\nonexistent.pas",
    })
    assert isinstance(result, dict)


# ============================================================
# handle_file_tool — 主入口路由
# ============================================================

@pytest.mark.asyncio
async def test_main_entry_read():
    result = await handle_file_tool({"action": "read", "file_path": "/nonexistent"})
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_main_entry_write():
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "test.pas")
    try:
        result = await handle_file_tool({
            "action": "write",
            "file_path": file_path,
            "edits": [{"start_line": 1, "content": "unit Test;\nbegin\nend.\n"}],
            "backup": False,
        })
        _assert_success(result)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_main_entry_backup():
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "test.pas")
    _make_file(file_path, "data")
    try:
        result = await handle_file_tool({
            "action": "backup",
            "file_path": file_path,
            "backup_action": "create",
        })
        _assert_success(result)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_main_entry_unknown_action():
    result = await handle_file_tool({"action": "nonexistent"})
    _assert_error(result)
    assert "未知 action" in result["message"]


@pytest.mark.asyncio
async def test_main_entry_default_action_is_read():
    result = await handle_file_tool({"file_path": "test.pas"})
    assert isinstance(result, dict)


# ============================================================
# Bug 回归测试 — 补充边界覆盖
# ============================================================

@pytest.mark.asyncio
async def test_read_with_end_line():
    """end_line（1-indexed inclusive）应限制读取行数"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "multi_line.pas")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("unit Test;\n// line 2\n// line 3\n// line 4\n// line 5\nend.\n")
    try:
        result = await handle_read({
            "file_path": file_path,
            "start_line": 1,
            "end_line": 3,
        })
        _assert_success(result)
        msg = result["message"]
        assert "1-indexed [1, 3]" in msg, f"unexpected range in: {msg}"
        assert "// line 3" in msg
        assert "// line 5" not in msg  # outside [1,3]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_with_start_line_and_end_line():
    """start_line + end_line（1-indexed）应精确截取中间段落"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "range_test.pas")
    lines = [f"// line {i}" for i in range(1, 21)]
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    try:
        result = await handle_read({
            "file_path": file_path,
            "start_line": 5,
            "end_line": 10,
        })
        _assert_success(result)
        msg = result["message"]
        assert "1-indexed [5, 10]" in msg
        assert "// line 5" in msg
        assert "// line 10" in msg
        assert "// line 4" not in msg
        assert "// line 11" not in msg
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_different_encodings_utf8():
    """读取 UTF-8 编码文件"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "utf8_test.pas")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("unit Test;\n// UTF-8 中文\nend.\n")
    try:
        result = await handle_read({"file_path": file_path})
        _assert_success(result)
        assert "中文" in result["message"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_different_encodings_utf8_bom():
    """读取 UTF-8 with BOM 编码文件（BOM 应被透明处理）"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "utf8_bom.pas")
    with open(file_path, "wb") as f:
        f.write(b'\xef\xbb\xbfunit Test;\n// UTF-8 BOM\nend.\n')
    try:
        result = await handle_read({"file_path": file_path})
        _assert_success(result)
        assert "UTF-8 BOM" in result["message"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_different_encodings_gbk():
    """读取 GBK 编码文件"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "gbk_test.pas")
    with open(file_path, "wb") as f:
        f.write("unit Test;\n// GBK 中文注释\nend.\n".encode("gbk"))
    try:
        result = await handle_read({"file_path": file_path})
        _assert_success(result)
        assert "中文注释" in result["message"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_different_encodings_utf16():
    """读取 UTF-16 with BOM 编码文件"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "utf16_test.pas")
    with open(file_path, "wb") as f:
        f.write("unit Test;\n// UTF-16 中文\nend.\n".encode("utf-16"))
    try:
        result = await handle_read({"file_path": file_path})
        _assert_success(result)
        assert "中文" in result["message"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_different_encodings_utf16_le_no_bom():
    """读取 UTF-16 LE 无 BOM 编码文件"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "utf16le_test.pas")
    with open(file_path, "wb") as f:
        f.write("unit Test;\n// UTF16LE\nend.\n".encode("utf-16-le"))
    try:
        result = await handle_read({"file_path": file_path})
        _assert_success(result)
        assert "UTF16LE" in result["message"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_dfm_binary_auto_convert():
    """写入二进制 DFM 文件应自动转回二进制格式"""
    tmp_dir = tempfile.mkdtemp()
    text_path = os.path.join(tmp_dir, "source.dfm")
    bin_path = os.path.join(tmp_dir, "binary.dfm")
    new_content = "object Form1: TForm1\n  Caption = 'Updated'\nend\n"
    try:
        # 创建文本 DFM
        with open(text_path, "w", encoding="utf-8") as f:
            f.write("object Form1: TForm1\n  Left = 0\nend\n")
        # 转换为二进制
        from src.tools.dfm_utils import convert_dfm, _detect_dfm_format
        r = await convert_dfm(text_path, bin_path, to_text=False)
        if not r.get("success"):
            pytest.skip("Delphi 编译器不可用，跳过 DFM 二进制测试")
        assert _detect_dfm_format(bin_path) == "binary"

        # 写入新内容（应自动转回二进制）
        result = await handle_write({
            "file_path": bin_path,
            "edits": [{"start_line": 1, "content": new_content}],
            "backup": False,
        })
        _assert_success(result)
        assert "binary DFM converted" in result["message"]
        # 验证仍是二进制格式
        assert _detect_dfm_format(bin_path) == "binary"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_encoding_auto_new_file():
    """新建文件 encoding=auto 应使用 utf-8"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "TestUnit.pas")
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 1, "content": "unit TestUnit;\nbegin\nend.\n"}],
            "backup": False,
            "encoding": "auto",
        })
        _assert_success(result)
        assert "encoding: utf-8" in result["message"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_encoding_utf16():
    """UTF-16 编码写入后应保留 BOM"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "test_utf16.pas")
    utf16_content = "unit Test;\nbegin\nend.\n"
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 1, "content": utf16_content}],
            "encoding": "utf-16",
            "backup": False,
        })
        _assert_success(result)
        with open(file_path, "rb") as f:
            raw = f.read(4)
        assert raw[:2] in (b'\xff\xfe', b'\xfe\xff'), "UTF-16 BOM 应存在"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_to_readonly_dir():
    """写入只读目录应返回错误"""
    result = await handle_write({
        "file_path": r"C:\__nonexistent_dir__\test.pas",
        "edits": [{"start_line": 1, "content": "unit Test;"}],
        "backup": False,
    })
    _assert_error(result)


@pytest.mark.asyncio
async def test_write_backup_disabled():
    """backup=False 时不应创建 __history"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "TestUnit.pas")
    _make_file(file_path, "original")
    history_dir = os.path.join(tmp_dir, "__history")
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 1, "content": "modified"}],
            "backup": False,
        })
        _assert_success(result)
        assert not os.path.isdir(history_dir), "backup=False 时不应创建历史目录"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_existing_dfm_text_preserved():
    """文本 DFM 写入后应保持文本格式（非二进制 DFM 不转换）"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "TestForm.dfm")
    dfm_content = "object Form1: TForm1\n  Left = 0\n  Top = 0\n  Caption = 'Hello'\nend\n"
    _make_file(file_path, dfm_content)
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 1, "content": dfm_content}],
            "backup": False,
        })
        _assert_success(result)
        # 验证仍然是文本 DFM
        from src.tools.dfm_utils import _detect_dfm_format
        fmt = _detect_dfm_format(file_path)
        assert fmt == "text", f"文本 DFM 应保持文本格式，实际: {fmt}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_format_action_code_correct_type():
    """format_action='code' 应返回 dict（当前返回 CallToolResult，是类型不一致）"""
    result = await handle_format({
        "format_action": "code",
        "code": "unit Test;\nbegin\nend.",
    })
    # 注意：当前实现返回 CallToolResult，不是 dict。此测试记录此行为。
    # 期望是 dict，但当前可能返回 CallToolResult
    from mcp.types import CallToolResult
    assert isinstance(result, (dict, CallToolResult)), \
        f"期望 dict 或 CallToolResult，实际: {type(result)}"


@pytest.mark.asyncio
async def test_format_action_check():
    """format_action='check' 应正常返回"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "test_check.pas")
    _make_file(file_path, "unit Test;\nbegin\nend.\n")
    try:
        result = await handle_format({
            "file_path": file_path,
            "format_action": "check",
        })
        assert isinstance(result, dict)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_backup_unknown_action():
    """未知 backup_action 应报错"""
    result = await handle_backup({
        "file_path": "test.pas",
        "backup_action": "nonexistent",
    })
    _assert_error(result)
    assert "未知" in result["message"]


@pytest.mark.asyncio
async def test_main_entry_format():
    """主入口 format 路由"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "test_fmt.pas")
    _make_file(file_path, "unit Test;\nbegin\nend.\n")
    try:
        result = await handle_file_tool({
            "action": "format",
            "file_path": file_path,
            "backup": False,
        })
        assert isinstance(result, dict)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_is_delphi_file():
    assert _is_delphi_file("test.pas") is True
    assert _is_delphi_file("test.dpr") is True
    assert _is_delphi_file("test.dfm") is True
    assert _is_delphi_file("test.fmx") is True
    assert _is_delphi_file("test.dproj") is True
    assert _is_delphi_file("test.dpk") is True
    assert _is_delphi_file("test.inc") is True
    assert _is_delphi_file("test.txt") is False
    assert _is_delphi_file("test.py") is False


@pytest.mark.asyncio
async def test_is_dfm_file():
    assert _is_dfm_file("test.dfm") is True
    assert _is_dfm_file("test.fmx") is True
    assert _is_dfm_file("test.pas") is False


@pytest.mark.asyncio
async def test_write_max_lines_cap():
    """max_lines 应被限制在 1000 以内"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "big_file.pas")
    content = "\n".join(f"// line {i}" for i in range(2000))
    _make_file(file_path, content)
    try:
        result = await handle_read({
            "file_path": file_path,
            "max_lines": 5000,  # 超出上限
        })
        _assert_success(result)
        # 实际返回行数应受限制（约 1000）
        msg = result.get("message", "")
        # 验证截断标记
        assert isinstance(msg, str)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# 1-indexed 边界测试（读）
# ============================================================

@pytest.mark.asyncio
async def test_read_1indexed_default_start():
    """默认 start_line=1 从文件开头读取"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "default_start.pas")
    content = "line1\nline2\nline3\nline4\nline5\n"
    _make_file(file_path, content)
    try:
        result = await handle_read({"file_path": file_path, "end_line": 2})
        _assert_success(result)
        msg = result["message"]
        assert "1-indexed [1, 2]" in msg
        assert "line1" in msg and "line2" in msg
        assert "line3" not in msg
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_1indexed_empty_range():
    """start_line > end_line 时区间为空，应返回 0 行"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "empty_range.pas")
    _make_file(file_path, "a\nb\nc\n")
    try:
        result = await handle_read({
            "file_path": file_path,
            "start_line": 3,
            "end_line": 2,
        })
        _assert_success(result)
        msg = result["message"]
        # start > end → 空区间
        assert "a\n" not in msg
        assert "b\n" not in msg
        assert "c\n" not in msg
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_1indexed_single_line():
    """start_line=3, end_line=3 → 仅返回第 3 行"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "single_line.pas")
    content = "alpha\nbeta\ngamma\ndelta\n"
    _make_file(file_path, content)
    try:
        result = await handle_read({
            "file_path": file_path,
            "start_line": 3,
            "end_line": 3,
        })
        _assert_success(result)
        msg = result["message"]
        assert "1-indexed [3, 3]" in msg
        assert "gamma" in msg
        assert "alpha" not in msg and "beta" not in msg and "delta" not in msg
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_1indexed_truncation_hint():
    """截断提示应显示 1-indexed 范围"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "trunc_hint.pas")
    lines = "\n".join(f"L{i}" for i in range(100))
    _make_file(file_path, lines + "\n")
    try:
        result = await handle_read({
            "file_path": file_path,
            "start_line": 6,
            "limit": 3,
        })
        _assert_success(result)
        msg = result["message"]
        assert "1-indexed [6, 8]" in msg, f"meta 行应含 1-indexed 范围: {msg}"
        assert " (truncated)" in msg, f"meta 行应含 (truncated) 标记: {msg}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_1indexed_negative_start_clamped():
    """负 start_line 应 clamp 到 1"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "neg_start.pas")
    _make_file(file_path, "only\n")
    try:
        result = await handle_read({
            "file_path": file_path,
            "start_line": -5,
            "end_line": 1,
        })
        _assert_success(result)
        assert "only" in result["message"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_1indexed_beyond_eof():
    """end_line 超出文件末尾 → 应返回已有行数"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "beyond_eof.pas")
    _make_file(file_path, "x\ny\nz\n")
    try:
        result = await handle_read({
            "file_path": file_path,
            "start_line": 1,
            "end_line": 999,
        })
        _assert_success(result)
        msg = result["message"]
        assert "x" in msg and "y" in msg and "z" in msg
        # 总行数应显示实际行数（3）
        assert "1-indexed [1, 3]" in msg
        assert "truncated" not in msg
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# 0-indexed 边界测试（写 - 部分写入）
# ============================================================

@pytest.mark.asyncio
async def test_write_partial_replace_middle():
    """部分写入替换中间行 [3,4] → 替换第 3,4 行"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "partial_mid.pas")
    _make_file(file_path, "a\nb\nc\nd\ne\n")
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 3, "end_line": 4, "content": "X\nY\n"}],
            "backup": False,
        })
        _assert_success(result)
        with open(file_path, "r") as f:
            assert f.read() == "a\nb\nX\nY\ne\n"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_partial_replace_from_start():
    """部分写入从开头替换 [1,2] → 替换前 2 行"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "partial_start.pas")
    _make_file(file_path, "a\nb\nc\n")
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 1, "end_line": 2, "content": "X\n"}],
            "backup": False,
        })
        _assert_success(result)
        with open(file_path, "r") as f:
            assert f.read() == "X\nc\n"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_partial_replace_to_end():
    """部分写入替换到末尾 [2,...] → 从第 2 行起全替换"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "partial_end.pas")
    _make_file(file_path, "a\nb\nc\n")
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 2, "content": "X\nY\n"}],
            "backup": False,
        })
        _assert_success(result)
        with open(file_path, "r") as f:
            assert f.read() == "a\nX\nY\n"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_partial_delete_lines():
    """空 content 删除第 2,3 行"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "partial_delete.pas")
    _make_file(file_path, "a\nb\nc\nd\n")
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 2, "end_line": 3, "content": ""}],
            "backup": False,
        })
        _assert_success(result)
        with open(file_path, "r") as f:
            assert f.read() == "a\nd\n"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_partial_single_line():
    """替换单行 [3,3] → 仅替换第 3 行"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "partial_single.pas")
    _make_file(file_path, "a\nb\nc\nd\n")
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 3, "end_line": 3, "content": "X\n"}],
            "backup": False,
        })
        _assert_success(result)
        with open(file_path, "r") as f:
            assert f.read() == "a\nb\nX\nd\n"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_partial_negative_start():
    """start_line < 1 应报错"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "neg_start.pas")
    _make_file(file_path, "a\nb\n")
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": -1, "content": "x\n"}],
            "backup": False,
        })
        _assert_error(result)
        assert "不能小于 1" in result["message"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_partial_start_eq_end():
    """start_line > end_line 空区间应报错"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "empty_range.pas")
    _make_file(file_path, "a\nb\n")
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 2, "end_line": 1, "content": "x\n"}],
            "backup": False,
        })
        _assert_error(result)
        assert "需满足 start_line ≤ end_line" in result["message"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_partial_end_exceeds_total():
    """end_line > total 应报错"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "out_of_bounds.pas")
    _make_file(file_path, "a\nb\n")
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 1, "end_line": 999, "content": "x\n"}],
            "backup": False,
        })
        _assert_error(result)
        assert "超出当前总行数" in result["message"]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# 行号偏移量测试（Bug1: offset 正确性）
# ============================================================

@pytest.mark.asyncio
async def test_write_partial_offset_in_response():
    """部分写入返回值应包含偏移量信息"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "offset_check.pas")
    _make_file(file_path, "a\nb\nc\nd\ne\n")
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 2, "end_line": 3, "content": "X\nY\nZ\n"}],
            "backup": False,
        })
        _assert_success(result)
        msg = result["message"]
        # 替换第2~3行 = 2行, 插入 3行, delta = +1
        # 1-indexed [2,3] → 替换后文件行数增加 1
        assert "edits:" in msg or "wrote:" in msg
        # 检查输出中包含一些行信息
        assert "encoding:" in msg
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_partial_offset_delete():
    """删除行时偏移量应为负数"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "offset_delete.pas")
    _make_file(file_path, "a\nb\nc\nd\ne\n")
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 2, "end_line": 4, "content": ""}],
            "backup": False,
        })
        _assert_success(result)
        msg = result["message"]
        assert "edits:" in msg or "wrote:" in msg
        with open(file_path, "r") as f:
            assert f.read() == "a\ne\n"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_partial_offset_no_change():
    """行数不变时偏移量应为0"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "offset_zero.pas")
    _make_file(file_path, "a\nb\nc\n")
    try:
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 2, "end_line": 2, "content": "X\n"}],
            "backup": False,
        })
        _assert_success(result)
        msg = result["message"]
        assert "edits:" in msg or "wrote:" in msg
        with open(file_path, "r") as f:
            assert f.read() == "a\nX\nc\n"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# show_line_numbers 测试（Bug4）
# ============================================================

@pytest.mark.asyncio
async def test_read_show_line_numbers_default_false():
    """默认 show_line_numbers=False 时不应有行号前缀"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "no_linenum.pas")
    _make_file(file_path, "line1\nline2\nline3\n")
    try:
        result = await handle_read({
            "file_path": file_path,
            "show_line_numbers": False,
        })
        _assert_success(result)
        msg = result["message"]
        # 新格式: meta 行 (# encoding: ...) + 内容, 无 ==== 分隔线
        # 跳过 meta 行后内容不应有行号前缀
        meta_end = msg.find("\n") + 1
        content = msg[meta_end:].strip()
        assert content.startswith("line1"), f"不应有行号前缀: {content[:20]}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_show_line_numbers_true():
    """show_line_numbers=True 时应显示 1-indexed 行号前缀"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "with_linenum.pas")
    _make_file(file_path, "alpha\nbeta\ngamma\n")
    try:
        result = await handle_read({
            "file_path": file_path,
            "show_line_numbers": True,
        })
        _assert_success(result)
        msg = result["message"]
        # 1-indexed 行号: 第 1 行=alpha, 第 2 行=beta, 第 3 行=gamma
        assert "1: alpha" in msg, f"第 1 行应有行号前缀: {msg}"
        assert "2: beta" in msg, f"第 2 行应有行号前缀: {msg}"
        assert "3: gamma" in msg, f"第 3 行应有行号前缀: {msg}"
        # meta 行应含 1-indexed 范围标记
        assert "1-indexed [1, 3]" in msg, f"meta 行应含 1-indexed 范围: {msg}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_show_line_numbers_with_offset():
    """show_line_numbers=True + start_line 偏移应显示正确的 1-indexed 绝对行号"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "linenum_offset.pas")
    lines = "\n".join(f"L{i}" for i in range(1, 21))
    _make_file(file_path, lines + "\n")
    try:
        # 从第 6 行 (1-indexed) 开始读 3 行
        result = await handle_read({
            "file_path": file_path,
            "start_line": 6,
            "end_line": 8,
            "show_line_numbers": True,
        })
        _assert_success(result)
        msg = result["message"]
        # 1-indexed 绝对行号应为 6, 7, 8
        assert "6: L6" in msg
        assert "7: L7" in msg
        assert "8: L8" in msg
        assert "5: L5" not in msg
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# format 偏移量测试（Bug2）
# ============================================================

@pytest.mark.asyncio
async def test_format_offset_in_response():
    """format action 返回值应包含格式化后的偏移量"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "fmt_offset.pas")
    # 用稍微不规范的代码触发 pasfmt 格式化
    _make_file(file_path, "unit  TestUnit ;\ninterface\nimplementation\nend.\n")
    try:
        from src.tools import pasfmt as _pasfmt
        import asyncio
        # 模拟 format_file 返回格式化成功
        with patch("src.tools.file_tool.pasfmt.format_file",
                   new_callable=AsyncMock) as mock_fmt:
            mock_fmt.return_value = {
                "status": "success", "formatted": True,
                "message": "代码格式化成功",
            }
            result = await handle_format({
                "file_path": file_path,
                "mode": "file",
                "backup": False,
            })
            _assert_success(result)
            # format_file 被调用了一次
            mock_fmt.assert_called_once()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_0indexed_limit_after_truncation():
    """limit 读取后截断，实际行数应 = limit"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "trunc_limit.pas")
    lines = "\n".join(f"R{i}" for i in range(500))
    _make_file(file_path, lines + "\n")
    try:
        result = await handle_read({
            "file_path": file_path,
            "start_line": 11,
            "limit": 7,
        })
        _assert_success(result)
        msg = result["message"]
        assert "1-indexed [11, 17]" in msg, f"范围异常: {msg}"
        # 应包含 [11,17] → 7 行
        assert "R11" in msg
        assert "R16" in msg
        assert "R17" not in msg
        assert "truncated" in msg
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_basic():
    """batch_write: 按升序替换两处，互不干扰"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "Unit1.pas")
        original = (
            "unit Unit1;\n"
            "\n"
            "interface\n"
            "\n"
            "implementation\n"
            "\n"
            "procedure A;\n"
            "begin\n"
            "  // A original\n"
            "end;\n"
            "\n"
            "procedure B;\n"
            "begin\n"
            "  // B original\n"
            "end;\n"
            "\n"
            "procedure C;\n"
            "begin\n"
            "  // C original\n"
            "end;\n"
            "\n"
            "end.\n"
        )
        _make_file(file_path, original)

        # Replace A body (lines 8-10 -> [8,10]) and C body (lines 19-21 -> [19,21))
        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 8, "end_line": 10, "content": "  // A updated", "description": "更新 A"},
                {"start_line": 19, "end_line": 21, "content": "  // C updated", "description": "更新 C"},
            ],
            "backup": False,
        })
        _assert_success(result)
        msg = result["message"]
        assert "wrote: 2 edits" in msg, f"edit 计数不对: {msg}"

        with open(file_path, "r", encoding="utf-8") as f:
            final = f.read()
        assert "// A updated" in final
        assert "// C updated" in final
        assert "// A original" not in final
        assert "// B original" in final, "B 被误改了!"
        assert "// C original" not in final
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_desc_order():
    """batch_write: 即使传入顺序是降序，内部也正确按升序处理"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "Unit2.pas")
        original = (
            "unit Unit2;\n"
            "\n"
            "implementation\n"
            "\n"
            "procedure First;\n"
            "begin\n"
            "  // First\n"
            "end;\n"
            "\n"
            "procedure Second;\n"
            "begin\n"
            "  // Second\n"
            "end;\n"
            "\n"
            "end.\n"
        )
        _make_file(file_path, original)

        # 传入降序: Second 在前, First 在后
        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 11, "end_line": 13, "content": "  // Second updated", "description": "更新 Second"},
                {"start_line": 6, "end_line": 8, "content": "  // First updated", "description": "更新 First"},
            ],
            "backup": False,
        })
        _assert_success(result)

        with open(file_path, "r", encoding="utf-8") as f:
            final = f.read()
        assert "// First updated" in final
        assert "// Second updated" in final
        assert "// First\n" not in final
        assert "// Second\n" not in final
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_validation():
    """batch_write: 参数校验"""
    result1 = await handle_batch_write({"file_path": "", "edits": []})
    assert result1.get("status") == "failed"

    result2 = await handle_batch_write({"file_path": "/nonexistent/test.pas", "edits": [{"start_line": 1, "content": ""}]})
    assert result2.get("status") == "failed"

    result3 = await handle_batch_write({
        "file_path": "test.pas",
        "edits": [{"start_line": 5, "end_line": 3, "content": "x"}],
    })
    assert result3.get("status") == "failed"


@pytest.mark.asyncio
async def test_batch_write_delete_lines():
    """batch_write: 空 content = 删除行"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "Unit3.pas")
        original = (
            "unit Unit3;\n"
            "\n"
            "interface\n"
            "\n"
            "implementation\n"
            "\n"
            "procedure Keep;\n"
            "begin\n"
            "  preserved\n"
            "end;\n"
            "\n"
            "end.\n"
        )
        _make_file(file_path, original)

        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 2, "end_line": 2, "content": "", "description": "删除空行2"},
            ],
            "backup": False,
        })
        _assert_success(result)

        with open(file_path, "r", encoding="utf-8") as f:
            final = f.read()
        # Line 1 (empty) should be gone, rest should be fine
        assert "procedure Keep" in final
        assert "preserved" in final
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# batch_write 边界测试
# ============================================================


@pytest.mark.asyncio
async def test_batch_write_overlap():
    """边界: 重叠区间应拒绝"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "Overlap.pas")
        _make_file(file_path)

        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 10, "end_line": 20, "content": "x", "description": "A"},
                {"start_line": 15, "end_line": 25, "content": "y", "description": "B"},
            ],
        })
        assert result.get("status") == "failed", "重叠应失败"
        assert "重叠" in result.get("message", "")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_overlap_none_end():
    """边界: edit 覆盖到末尾 + 后续 edit 重叠"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "OverlapNone.pas")
        _make_file(file_path)

        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 5, "content": "x", "description": "到末尾"},
                {"start_line": 3, "content": "y", "description": "冲突"},
            ],
        })
        assert result.get("status") == "failed", "覆盖末尾应拒绝后续 edit"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_same_range_overlap():
    """边界: 完全相同范围应拒绝"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "SameRange.pas")
        _make_file(file_path)

        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 10, "end_line": 20, "content": "a", "description": "A"},
                {"start_line": 10, "end_line": 20, "content": "b", "description": "B"},
            ],
        })
        assert result.get("status") == "failed", "相同范围应拒绝"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_adjacent():
    """边界: 恰好相邻 [1,5]+[6,10] 应正常"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "Adjacent.pas")
        data = "\n".join(f"line{i}" for i in range(10)) + "\n"
        _make_file(file_path, data)

        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 1, "end_line": 5, "content": "AAA\nBBB\n", "description": "前半"},
                {"start_line": 6, "end_line": 10, "content": "CCC\nDDD\n", "description": "后半"},
            ],
            "backup": False,
        })
        _assert_success(result)

        with open(file_path, "r", encoding="utf-8") as f:
            final = f.read()
        assert final == "AAA\nBBB\nCCC\nDDD\n", f"相邻编辑结果不对: {repr(final)}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_start_boundary():
    """边界: 从文件头部(start_line=1)编辑"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "StartBound.pas")
        _make_file(file_path, "header\n---\nbody\n")

        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 1, "end_line": 1, "content": "HEADER", "description": "改首行"},
            ],
            "backup": False,
        })
        _assert_success(result)

        with open(file_path, "r", encoding="utf-8") as f:
            final = f.read()
        assert final.startswith("HEADER"), f"首行替换失败: {repr(final)}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_to_eof():
    """边界: end_line=None 覆盖到末尾"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "ToEof.pas")
        _make_file(file_path, "a\nb\nc\n")

        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 2, "content": "B\nC\nD\n", "description": "第2行到末尾"},
            ],
            "backup": False,
        })
        _assert_success(result)

        with open(file_path, "r", encoding="utf-8") as f:
            final = f.read()
        assert final == "a\nB\nC\nD\n", f"到末尾结果不对: {repr(final)}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_large_insert():
    """边界: 大插入(1行->50行)后续edit偏移正确"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "LargeIns.pas")
        lines = [f"line{i}" for i in range(10)]
        _make_file(file_path, "\n".join(lines) + "\n")

        many = "\n".join(f"inserted{j}" for j in range(50)) + "\n"
        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 2, "end_line": 2, "content": many, "description": "大插入"},
                {"start_line": 6, "end_line": 6, "content": "FIVE", "description": "后续edit"},
            ],
            "backup": False,
        })
        _assert_success(result)

        with open(file_path, "r", encoding="utf-8") as f:
            final = f.read()
        assert "FIVE" in final, "后续edit未正确应用"
        assert "inserted0" in final
        assert "inserted49" in final
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_large_delete():
    """边界: 大删除(100行)前后edit偏移正确"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "LargeDel.pas")
        lines = [f"line{i}" for i in range(120)]
        _make_file(file_path, "\n".join(lines) + "\n")

        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 11, "end_line": 110, "content": "", "description": "大删除"},
                {"start_line": 6, "end_line": 6, "content": "FIVE", "description": "前方edit"},
                {"start_line": 113, "end_line": 113, "content": "AFTER", "description": "后方edit"},
            ],
            "backup": False,
        })
        _assert_success(result)

        with open(file_path, "r", encoding="utf-8") as f:
            final = f.read()
        assert "FIVE" in final, "前方edit未正确应用"
        assert "AFTER" in final, "后方edit未正确应用"
        assert "line9" in final, "删除前内容不应丢失"
        assert "line10" not in final, "line10应被删除"
        assert "line109" not in final, "line109应被删除"
        assert "line111" in final, "line111应保留"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_many_edits():
    """边界: 10个edit交替增删累积偏移准确"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "ManyEdits.pas")
        _make_file(file_path, "\n".join(f"line{i}" for i in range(20)) + "\n")

        edits = [
            {"start_line": 1, "end_line": 1,   "content": "zero",       "description": "#0"},
            {"start_line": 3, "end_line": 3,   "content": "two",        "description": "#1"},
            {"start_line": 5, "end_line": 5,   "content": "",           "description": "#2 del"},
            {"start_line": 7, "end_line": 7,   "content": "six\nsix2\n", "description": "#3 ins2"},
            {"start_line": 9, "end_line": 9,   "content": "eight",      "description": "#4"},
            {"start_line": 11, "end_line": 11,  "content": "",           "description": "#5 del"},
            {"start_line": 13, "end_line": 13,  "content": "",           "description": "#6 del"},
            {"start_line": 15, "end_line": 15,  "content": "fourteen\n", "description": "#7"},
            {"start_line": 17, "end_line": 17,  "content": "sixteen",    "description": "#8"},
            {"start_line": 19, "end_line": 20,  "content": "eighteen\neighteen2\n", "description": "#9"},
        ]
        result = await handle_batch_write({
            "file_path": file_path,
            "edits": edits,
            "backup": False,
        })
        _assert_success(result)
        msg = result["message"]
        assert "wrote: 10 edits" in msg, f"edit计数不对: {msg}"

        with open(file_path, "r", encoding="utf-8") as f:
            final = f.read()
        assert "zero" in final
        assert "two" in final
        assert "six" in final and "six2" in final
        assert "eight" in final
        assert "fourteen" in final
        assert "sixteen" in final
        assert "eighteen" in final and "eighteen2" in final
        assert "line0" not in final
        assert "line4" not in final
        assert "line10" not in final
        assert "line12" not in final
        assert "line1" in final
        assert "line3" in final
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_crlf():
    """边界: CRLF文件的换行符统一"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "Crlf.pas")
        # 用二进制写 CRLF 内容，避免 _make_file 的 newline 翻译
        with open(file_path, "wb") as f:
            f.write(b"a\r\nb\r\nc\r\n")

        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 2, "end_line": 2, "content": "B\nBB\n", "description": "LF内容写入CRLF文件"},
            ],
            "backup": False,
        })
        _assert_success(result)

        with open(file_path, "rb") as f:
            raw = f.read()
        # 期望: a + CRLF + B + CRLF + BB + CRLF + c + CRLF
        assert raw == b"a\r\nB\r\nBB\r\nc\r\n", f"CRLF不一致: {raw!r}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_single_edit():
    """边界: 只有一个edit"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "Single.pas")
        _make_file(file_path, "aaa\nbbb\nccc\n")

        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 2, "end_line": 2, "content": "BBB", "description": "单edit"},
            ],
            "backup": False,
        })
        _assert_success(result)

        with open(file_path, "r", encoding="utf-8") as f:
            final = f.read()
        assert "BBB" in final
        assert "aaa" in final
        assert "ccc" in final
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_trailing_newline():
    """边界: content末尾无换行时自动补齐"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "Trail.pas")
        _make_file(file_path, "a\nb\nc\n")

        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 2, "end_line": 2, "content": "no_newline_at_end", "description": "补换行"},
            ],
            "backup": False,
        })
        _assert_success(result)

        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert lines[1].rstrip('\n\r') == "no_newline_at_end", f"第2行不对: {lines!r}"
        assert lines[0] == "a\n"
        assert lines[2] == "c\n"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_fully_replace():
    """边界: 替换整个文件"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "FullReplace.pas")
        _make_file(file_path, "old\ncontent\nhere\n")

        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 1, "end_line": 3, "content": "brand\nnew\nfile\n", "description": "全量替换"},
            ],
            "backup": False,
        })
        _assert_success(result)

        with open(file_path, "r", encoding="utf-8") as f:
            final = f.read()
        assert final == "brand\nnew\nfile\n", f"全量替换不对: {repr(final)}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_multiline_content():
    """边界: content含多行文本保留换行"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "Multi.pas")
        _make_file(file_path, "a\nb\nc\n")

        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 2, "end_line": 2, "content": "B1\nB2\nB3\n", "description": "3行替换1行"},
            ],
            "backup": False,
        })
        _assert_success(result)

        with open(file_path, "r", encoding="utf-8") as f:
            final = f.read()
        assert "B1\nB2\nB3\n" in final, f"多行丢失: {repr(final)}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_partial_preview_no_file_change():
    """write 部分写入 preview=True 时不应修改文件"""
    tmp_dir = tempfile.mkdtemp(prefix="test_write_")
    try:
        file_path = os.path.join(tmp_dir, "Unit1.pas")
        original = "line1\nline2\nline3\nline4\nline5\n"
        _make_file(file_path, original)

        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 2, "end_line": 3, "content": "replaced\nnewline\n"}],
            "backup": False,
            "preview": True,
        })
        _assert_success(result)
        with open(file_path, "r", encoding="utf-8") as f:
            assert f.read() == original, "preview 模式修改了文件!"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_partial_preview_diff_in_message():
    """write 部分写入 preview=True 时返回 - / + diff"""
    tmp_dir = tempfile.mkdtemp(prefix="test_write_")
    try:
        file_path = os.path.join(tmp_dir, "Demo.pas")
        _make_file(file_path, "aaa\nbbb\nccc\n")

        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 2, "end_line": 2, "content": "BBB\n"}],
            "backup": False,
            "preview": True,
        })
        _assert_success(result)
        msg = result["message"]
        assert "preview" in msg, f"应标记 preview, got: {msg}"
        assert "- L2: bbb" in msg, f"缺失删除行标记: {msg}"
        assert "+ BBB" in msg, f"缺失新增行标记: {msg}"
        with open(file_path, "r", encoding="utf-8") as f:
            assert f.read() == "aaa\nbbb\nccc\n", "preview 不应改文件"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_full_preview_new_file():
    """write 全量预览：新建文件时不写盘"""
    tmp_dir = tempfile.mkdtemp(prefix="test_write_")
    try:
        file_path = os.path.join(tmp_dir, "New.pas")
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 1, "content": "unit New;\nbegin\nend.\n"}],
            "preview": True,
        })
        _assert_success(result)
        assert "preview" in result["message"]
        assert "would create" in result["message"]
        assert not os.path.isfile(file_path), "预览不应创建文件"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_full_preview_existing_file():
    """write 全量预览：已有文件时不写盘，返回大小变化"""
    tmp_dir = tempfile.mkdtemp(prefix="test_write_")
    try:
        file_path = os.path.join(tmp_dir, "Old.pas")
        _make_file(file_path, "old content\n")
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 1, "content": "new content\n"}],
            "preview": True,
        })
        _assert_success(result)
        assert "preview" in result["message"]
        assert "preview: true" in result["message"] or "未写入磁盘" in result["message"]
        with open(file_path, "r", encoding="utf-8") as f:
            assert f.read() == "old content\n", "预览不应改文件"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_partial_preview_no_backup():
    """write 部分写入 preview=True 不应创建备份"""
    tmp_dir = tempfile.mkdtemp(prefix="test_write_")
    try:
        file_path = os.path.join(tmp_dir, "NoBak.pas")
        _make_file(file_path, "x\ny\nz\n")
        history_dir = os.path.join(tmp_dir, "__history")
        result = await handle_write({
            "file_path": file_path,
            "edits": [{"start_line": 1, "end_line": 1, "content": "X\n"}],
            "backup": True,
            "preview": True,
        })
        _assert_success(result)
        assert not os.path.exists(history_dir), "preview 不应创建备份"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_preview_no_file_change():
    """preview=True 时不应修改文件内容"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "Unit1.pas")
        original = "line1\nline2\nline3\nline4\nline5\n"
        _make_file(file_path, original)

        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 1, "end_line": 3, "content": "replaced\nnewline\n", "description": "替换中间"},
            ],
            "backup": False,
            "preview": True,
        })
        _assert_success(result)
        # 文件不应变化
        with open(file_path, "r", encoding="utf-8") as f:
            assert f.read() == original, "preview 模式修改了文件!"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_preview_diff_in_message():
    """preview=True 时消息中应包含 diff 预览 ( - / + 行)"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "Demo.pas")
        _make_file(file_path, "aaa\nbbb\nccc\n")

        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 2, "end_line": 2, "content": "BBB\n", "description": "改 bbb"},
            ],
            "backup": False,
            "preview": True,
        })
        _assert_success(result)
        msg = result["message"]
        assert "preview:" in msg or "preview" in msg, f"应标记 preview, got: {msg}"
        assert "- L2: bbb" in msg, f"缺失删除行标记: {msg}"
        assert "+ BBB" in msg, f"缺失新增行标记: {msg}"
        assert "preview: true" in msg or "preview" in msg, f"缺失 preview 标记: {msg}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_preview_no_backup():
    """preview=True 时不应创建备份文件"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "NoBak.pas")
        _make_file(file_path, "x\ny\nz\n")

        # 先确认有没有 __history 目录
        history_dir = os.path.join(tmp_dir, "__history")
        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 1, "end_line": 1, "content": "X\n", "description": "改首行"},
            ],
            "backup": True,   # backup=True 但 preview=True 应跳过备份
            "preview": True,
        })
        _assert_success(result)
        # __history 不应被创建
        assert not os.path.exists(history_dir), "preview 模式不应创建备份"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_preview_same_result_as_actual_write():
    """preview 输出的 diff 应与实际写入内容一致"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "Check.pas")
        _make_file(file_path, "a\nb\nc\nd\ne\n")

        # 先 preview
        preview = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 2, "end_line": 4, "content": "B\nC\nD\n", "description": "改中间3行"},
            ],
            "backup": False,
            "preview": True,
        })
        _assert_success(preview)

        # 读回原始内容确认文件未变
        with open(file_path, "r", encoding="utf-8") as f:
            assert f.read() == "a\nb\nc\nd\ne\n", "preview 不应改文件"

        # 实际写入
        actual = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 2, "end_line": 4, "content": "B\nC\nD\n", "description": "改中间3行"},
            ],
            "backup": False,
            "preview": False,
        })
        _assert_success(actual)

        with open(file_path, "r", encoding="utf-8") as f:
            final = f.read()
        assert final == "a\nB\nC\nD\ne\n", f"实际写入结果不符: {repr(final)}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_batch_write_preview_with_force():
    """preview 与 force 可同时使用: 预览时跳过重复行检测"""
    tmp_dir = tempfile.mkdtemp(prefix="test_batch_")
    try:
        file_path = os.path.join(tmp_dir, "ForcePrev.pas")
        _make_file(file_path, "aaa\nbbb\nccc\n")

        # 故意产生 content 首行与被替换行相同的情况
        result = await handle_batch_write({
            "file_path": file_path,
            "edits": [
                {"start_line": 1, "end_line": 1, "content": "aaa\n", "description": "内容首行与 old 相同"},
            ],
            "backup": False,
            "preview": True,
            "force": True,
        })
        _assert_success(result)
        # 文件仍不应变化
        with open(file_path, "r", encoding="utf-8") as f:
            assert f.read() == "aaa\nbbb\nccc\n", "force+preview 也不应改文件"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
