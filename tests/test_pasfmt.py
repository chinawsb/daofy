"""
Tests for src/tools/pasfmt.py — Delphi 代码格式化工具

Covers:
  - _compact_uses_clause: 多行 uses → 单行压缩
  - set_pasfmt_path / get_pasfmt_path: 路径状态管理
  - set_uses_style / get_uses_style: 风格状态管理
  - format_file: 错误路径（pasfmt 未安装、文件不存在）
  - format_code: 错误路径（pasfmt 未安装）
  - check_pasfmt_installation / check_pasfmt_rad_installation
"""

import os
import sys
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.tools.pasfmt import (
    _compact_uses_clause,
    set_pasfmt_path, get_pasfmt_path,
    set_uses_style, get_uses_style,
    format_file, format_code,
    check_pasfmt_installation, check_pasfmt_rad_installation,
    DELPHI_VERSIONS,
)


# ============================================================
# 辅助：在测试后恢复全局状态
# ============================================================

def _reset_global_state():
    """恢复 pasfmt 全局变量到初始状态（仅为隔离测试）"""
    import src.tools.pasfmt as _pm
    _pm._PASFMT_PATH = None
    _pm._USES_STYLE = "compact"


# ============================================================
# _compact_uses_clause — 纯函数，核心压缩逻辑
# ============================================================

class TestCompactUsesClause:

    def test_simple_multi_line(self):
        """多行 uses 压缩为单行"""
        code = """unit Test;

interface

uses
  System.SysUtils,
  System.Classes;

implementation

end.
"""
        result = _compact_uses_clause(code)
        assert "uses System.SysUtils, System.Classes;" in result
        # 确认不再有多行形式
        assert "System.SysUtils,\n" not in result

    def test_single_unit(self):
        """单个单元 uses"""
        code = """unit Test;
interface
uses
  System.Classes;
implementation
end."""
        result = _compact_uses_clause(code)
        assert "uses System.Classes;" in result

    def test_three_units(self):
        """三个单元"""
        code = """unit Test;
interface
uses
  System.SysUtils,
  System.Classes,
  Winapi.Windows;
implementation
end."""
        result = _compact_uses_clause(code)
        assert "uses System.SysUtils, System.Classes, Winapi.Windows;" in result

    def test_no_uses_clause(self):
        """没有 uses 子句的代码应原样返回"""
        code = "unit Test;\nbegin\nend.\n"
        result = _compact_uses_clause(code)
        assert result == code

    def test_uses_already_single_line(self):
        """已经是单行的 uses 不应改动"""
        code = "unit Test;\nuses System.SysUtils, System.Classes;\nbegin\nend.\n"
        result = _compact_uses_clause(code)
        assert result == code
        assert "uses System.SysUtils, System.Classes;" in result

    def test_uses_with_trailing_comment(self):
        """uses 块后面有注释"""
        code = """unit Test;
interface
uses
  System.SysUtils,
  System.Classes;  // 标准库
implementation
end."""
        result = _compact_uses_clause(code)
        assert "uses System.SysUtils, System.Classes;" in result

    def test_implementation_uses(self):
        """implementation 下的 uses 也应压缩"""
        code = """unit Test;
interface
implementation
uses
  System.SysUtils,
  System.Classes;
end."""
        result = _compact_uses_clause(code)
        assert "uses System.SysUtils, System.Classes;" in result

    def test_empty_interface_uses_with_implementation_uses(self):
        """interface 无 uses，implementation 有 uses"""
        code = """unit Test;
interface
implementation
uses
  Winapi.Windows;
end."""
        result = _compact_uses_clause(code)
        assert "uses Winapi.Windows;" in result

    def test_mixed_single_and_multi_line(self):
        """多个 uses 子句混合"""
        code = """unit Test;
interface
uses
  System.SysUtils;
implementation
uses
  Winapi.Windows,
  System.Classes;
end."""
        result = _compact_uses_clause(code)
        assert "uses System.SysUtils;" in result
        assert "uses Winapi.Windows, System.Classes;" in result

    def test_uses_in_comment_should_not_match(self):
        """字符串或注释中的 uses 不应触发"""
        code = """unit Test;
interface
const
  s = 'uses';
implementation
end."""
        result = _compact_uses_clause(code)
        assert result == code

    def test_indented_uses(self):
        """带缩进的 uses"""
        code = """unit Test;
interface
  uses
    System.SysUtils,
    System.Classes;
implementation
end."""
        result = _compact_uses_clause(code)
        assert "uses System.SysUtils, System.Classes;" in result

    def test_compact_does_not_create_empty_uses(self):
        """无需压缩时不应引入 uses"""
        code = "unit Test;\nbegin\nend.\n"
        result = _compact_uses_clause(code)
        assert "uses" not in result

    def test_unit_with_no_implementation_section(self):
        """只有 interface 的单元"""
        code = """unit Test;
interface
uses
  System.SysUtils;
end."""
        result = _compact_uses_clause(code)
        assert "uses System.SysUtils;" in result


# ============================================================
# 状态管理
# ============================================================

class TestStateManagement:

    def setup_method(self):
        _reset_global_state()

    def teardown_method(self):
        _reset_global_state()

    def test_set_and_get_pasfmt_path(self):
        # Mock env var and default paths to isolate test
        with patch.dict(os.environ, {}, clear=True):
            with patch("os.path.exists", return_value=False):
                from src.tools.pasfmt import get_pasfmt_path as gpp
                assert gpp() is None
                set_pasfmt_path(r"C:\tools\pasfmt.exe")
                assert gpp() == r"C:\tools\pasfmt.exe"

    def test_set_and_get_uses_style(self):
        assert get_uses_style() == "compact"
        set_uses_style("pasfmt_default")
        assert get_uses_style() == "pasfmt_default"

    def test_set_uses_style_invalid(self):
        """无效风格应回退到 compact"""
        set_uses_style("invalid_style")
        assert get_uses_style() == "compact"

    def test_set_pasfmt_path_overwrites(self):
        """重复设置应覆盖"""
        set_pasfmt_path(r"C:\tools\pasfmt.exe")
        set_pasfmt_path(r"D:\other\pasfmt.exe")
        assert get_pasfmt_path() == r"D:\other\pasfmt.exe"


# ============================================================
# format_file — 错误路径（pasfmt 未安装，文件不存在）
# ============================================================

class TestFormatFileErrors:

    def setup_method(self):
        _reset_global_state()

    def teardown_method(self):
        _reset_global_state()

    @pytest.mark.asyncio
    async def test_format_file_not_found(self):
        """文件不存在应返回 FILE_NOT_FOUND 错误"""
        result = await format_file(r"C:\nonexistent\file.pas")
        assert result["status"] == "failed"
        assert result["error_code"] == "FILE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_format_file_pasfmt_not_found(self):
        """pasfmt 未安装应返回 PASFMT_NOT_FOUND 错误"""
        # 确保没有 pasfmt 路径
        with patch("src.tools.pasfmt.get_pasfmt_path", return_value=None):
            with tempfile.NamedTemporaryFile(suffix=".pas", mode="w", delete=False,
                                             encoding="utf-8") as f:
                f.write("unit Test;\nbegin\nend.\n")
                tmp_path = f.name
            try:
                result = await format_file(tmp_path)
                assert result["status"] == "failed"
                assert result["error_code"] == "PASFMT_NOT_FOUND"
            finally:
                os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_format_file_in_place_success_mocked(self):
        """模拟 pasfmt 成功执行"""
        tmp_dir = tempfile.mkdtemp()
        file_path = os.path.join(tmp_dir, "TestUnit.pas")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("unit Test;\nbegin\nend.\n")
        try:
            with patch("src.tools.pasfmt.get_pasfmt_path",
                       return_value=r"C:\fake\pasfmt.exe"):
                with patch("subprocess.run") as mock_run:
                    mock_result = MagicMock()
                    mock_result.returncode = 0
                    mock_result.stdout = ""
                    mock_result.stderr = ""
                    mock_run.return_value = mock_result

                    result = await format_file(file_path)
                    assert result["status"] == "success"
                    assert result["formatted"] is True
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_format_file_check_only(self):
        """check_only=True 时 pasfmt returncode != 0 是正常行为"""
        tmp_dir = tempfile.mkdtemp()
        file_path = os.path.join(tmp_dir, "TestUnit.pas")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("unit Test;\nbegin\nend.\n")
        try:
            with patch("src.tools.pasfmt.get_pasfmt_path",
                       return_value=r"C:\fake\pasfmt.exe"):
                with patch("subprocess.run") as mock_run:
                    mock_result = MagicMock()
                    mock_result.returncode = 1  # 格式问题
                    mock_result.stdout = ""
                    mock_result.stderr = "ERROR CHECK: 'test.pas' has incorrect formatting"
                    mock_run.return_value = mock_result

                    result = await format_file(file_path, dry_run=True)
                    assert result["status"] == "success"
                    assert result["dry_run"] is True
                    assert result["formatted"] is False
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_format_file_execution_failure(self):
        """pasfmt 执行失败（returncode != 0 且非 check_only）"""
        tmp_dir = tempfile.mkdtemp()
        file_path = os.path.join(tmp_dir, "TestUnit.pas")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("unit Test;\nbegin\nend.\n")
        try:
            with patch("src.tools.pasfmt.get_pasfmt_path",
                       return_value=r"C:\fake\pasfmt.exe"):
                with patch("subprocess.run") as mock_run:
                    mock_result = MagicMock()
                    mock_result.returncode = 2
                    mock_result.stdout = ""
                    mock_result.stderr = "error: bad option"
                    mock_run.return_value = mock_result

                    result = await format_file(file_path)
                    assert result["status"] == "failed"
                    assert result["error_code"] == "PASFMT_EXECUTION_FAILED"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_format_file_timeout(self):
        """pasfmt 超时应返回 TIMEOUT 错误"""
        tmp_dir = tempfile.mkdtemp()
        file_path = os.path.join(tmp_dir, "TestUnit.pas")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("unit Test;\nbegin\nend.\n")
        try:
            with patch("src.tools.pasfmt.get_pasfmt_path",
                       return_value=r"C:\fake\pasfmt.exe"):
                with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(
                        cmd="pasfmt", timeout=30)):
                    result = await format_file(file_path)
                    assert result["status"] == "failed"
                    assert result["error_code"] == "TIMEOUT"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# format_code — 错误路径
# ============================================================

class TestFormatCodeErrors:

    def setup_method(self):
        _reset_global_state()

    def teardown_method(self):
        _reset_global_state()

    @pytest.mark.asyncio
    async def test_format_code_pasfmt_not_found(self):
        """pasfmt 未安装应报错"""
        with patch("src.tools.pasfmt.get_pasfmt_path", return_value=None):
            result = await format_code("unit Test;\nbegin\nend.\n")
            assert result.isError
            assert "pasfmt" in result.content[0].text

    @pytest.mark.asyncio
    async def test_format_code_success_mocked(self):
        """模拟 pasfmt 成功执行 code 格式化"""
        with patch("src.tools.pasfmt.get_pasfmt_path",
                   return_value=r"C:\fake\pasfmt.exe"):
            with patch("subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = "unit Test;\nbegin\nend.\n"
                mock_result.stderr = ""
                mock_run.return_value = mock_result

                result = await format_code("unit Test;\nbegin\nend.\n")
                assert not result.isError
                assert "unit Test" in result.content[0].text

    @pytest.mark.asyncio
    async def test_format_code_failure(self):
        """pasfmt 格式化失败"""
        with patch("src.tools.pasfmt.get_pasfmt_path",
                   return_value=r"C:\fake\pasfmt.exe"):
            with patch("subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.returncode = 1
                mock_result.stdout = ""
                mock_result.stderr = "parse error"
                mock_run.return_value = mock_result

                result = await format_code("bad code")
                assert result.isError


# ============================================================
# check_pasfmt_installation
# ============================================================

class TestCheckPasfmtInstallation:

    def setup_method(self):
        _reset_global_state()

    def teardown_method(self):
        _reset_global_state()

    @pytest.mark.asyncio
    async def test_check_installed(self):
        """pasfmt 已安装应返回安装路径"""
        with patch("src.tools.pasfmt.get_pasfmt_path",
                   return_value=r"C:\tools\pasfmt.exe"):
            with patch("os.path.exists", return_value=True):
                result = await check_pasfmt_installation()
                assert not result.isError
                assert "已安装" in result.content[0].text

    @pytest.mark.asyncio
    async def test_check_not_installed_default_paths(self):
        """pasfmt 未在缓存中但默认路径存在"""
        with patch("src.tools.pasfmt.get_pasfmt_path", return_value=None):
            with patch("os.path.exists") as mock_exists:
                # tools/pasfmt/cli/pasfmt.exe 存在
                def exists_side(p):
                    return "pasfmt" in str(p) and ("exe" in str(p).lower() or "cli" in str(p))
                mock_exists.side_effect = exists_side

                result = await check_pasfmt_installation()
                assert not result.isError
                assert "pasfmt" in result.content[0].text

    @pytest.mark.asyncio
    async def test_check_not_installed(self):
        """pasfmt 完全未安装应返回 isError"""
        with patch("src.tools.pasfmt.get_pasfmt_path", return_value=None):
            with patch("os.path.exists", return_value=False):
                result = await check_pasfmt_installation()
                assert result.isError
                assert "未找到" in result.content[0].text


# ============================================================
# check_pasfmt_rad_installation
# ============================================================

class TestCheckPasfmtRad:

    @pytest.mark.asyncio
    async def test_unsupported_version(self):
        """不支持的 Delphi 版本应报错"""
        result = await check_pasfmt_rad_installation(delphi_version="99")
        assert result["status"] == "failed"
        assert result["error_code"] == "UNSUPPORTED_DELPHI_VERSION"

    @pytest.mark.asyncio
    async def test_not_installed(self):
        """未安装时应返回 installed=False"""
        with patch("os.path.exists", return_value=False):
            # 避免注册表检查
            with patch("sys.platform", "linux"):
                result = await check_pasfmt_rad_installation(delphi_version="12")
                assert result["status"] == "success"
                assert result["installed"] is False


# ============================================================
# DELPHI_VERSIONS 完整性
# ============================================================

class TestDelphiVersions:

    def test_all_versions_have_name(self):
        for ver, info in DELPHI_VERSIONS.items():
            assert info["name"], f"Version {ver} missing name"

    def test_all_versions_have_bpl_32(self):
        for ver, info in DELPHI_VERSIONS.items():
            assert info["bpl_32"], f"Version {ver} missing bpl_32"

    def test_supported_versions(self):
        """已知支持的版本"""
        assert "11" in DELPHI_VERSIONS
        assert "12" in DELPHI_VERSIONS
        assert "13" in DELPHI_VERSIONS
