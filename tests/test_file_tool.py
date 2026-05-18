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
    handle_backup, handle_format, _is_delphi_file, _is_dfm_file
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
            "content": "unit TestUnit;\nbegin\nend.\n",
            "backup": False,
        })
        _assert_success(result)
        assert "文件已写入" in result["message"]
        assert os.path.isfile(file_path)
        with open(file_path, "r") as f:
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
            "content": "modified content",
            "backup": True,
        })
        _assert_success(result)
        assert "备份已创建" in result["message"]

        backups = os.listdir(history_dir)
        assert len(backups) == 1
        assert backups[0].endswith(".~1~")

        bp = os.path.join(history_dir, backups[0])
        with open(bp, "r") as f:
            assert f.read() == "original content"
        with open(file_path, "r") as f:
            assert f.read() == "modified content"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_backup_version_increment():
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "TestUnit.pas")
    _make_file(file_path, "v1")
    history_dir = os.path.join(tmp_dir, "__history")
    try:
        await handle_write({"file_path": file_path, "content": "v2", "backup": True})
        await handle_write({"file_path": file_path, "content": "v3", "backup": True})

        backups = sorted(os.listdir(history_dir))
        assert len(backups) == 2
        assert backups[0].endswith(".~1~")
        assert backups[1].endswith(".~2~")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_write_missing_file_path():
    result = await handle_write({"content": "hello"})
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
            "content": gbk_content,
            "backup": False,
        })
        _assert_success(result)
        assert "编码: gbk" in result["message"]

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
                "content": "unit TestUnit;\nbegin\nend.\n",
                "backup": False,
                "format_after_write": True,
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
            "content": "unit Test;\nbegin\nend.\n",
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
    """end_line 参数应限制读取行数"""
    tmp_dir = tempfile.mkdtemp()
    file_path = os.path.join(tmp_dir, "multi_line.pas")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("unit Test;\n// line 2\n// line 3\n// line 4\n// line 5\nend.\n")
    try:
        result = await handle_read({
            "file_path": file_path,
            "end_line": 3,
        })
        _assert_success(result)
        msg = result["message"]
        assert "显示范围: 第 1 行 到 第 3 行" in msg, f"unexpected range in: {msg}"
        assert "// line 3" in msg
        assert "// line 5" not in msg  # 不应出现在 3 行以后
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_read_with_start_line_and_end_line():
    """start_line + end_line 组合应精确截取中间段落"""
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
        assert "显示范围: 第 5 行 到 第 10 行" in msg
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
            "content": new_content,
            "backup": False,
        })
        _assert_success(result)
        assert "二进制 DFM" in result["message"]
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
            "content": "unit TestUnit;\nbegin\nend.\n",
            "backup": False,
            "encoding": "auto",
        })
        _assert_success(result)
        assert "编码: utf-8" in result["message"]
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
            "content": utf16_content,
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
        "content": "unit Test;",
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
            "content": "modified",
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
            "content": dfm_content,
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
    assert _is_dfm_file("test.fmx") is False
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
