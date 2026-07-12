#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试编译模型 — CompileResult, CompileMessage, CompileRequest, ConfigFile

覆盖:
  - CompileMessage: to_dict 序列化
  - CompileResult: to_dict, has_errors, has_warnings, get_summary
  - CompileOptions: __post_init__ 验证（非法 warning_level, timeout）
  - ProjectCompileRequest: __post_init__ 验证（空路径、错误扩展名）
  - FileCompileRequest: __post_init__ 验证
  - ConfigFile: get_default_compiler 优先级、add_compiler 同名更新、remove_compiler 删默认
  - CompilerConfig: to_dict/from_dict 往返
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest

from src.models.compile_result import CompileMessage, CompileResult, CompileStatus
from src.models.compile_request import (
    CompileOptions, ProjectCompileRequest, FileCompileRequest,
    OutputType, RuntimeLibrary, TargetPlatform,
)
from src.models.compiler_config import CompilerConfig, ConfigFile


# ============================================================
# CompileMessage
# ============================================================

class TestCompileMessage:

    def test_to_dict(self):
        m = CompileMessage(file_path="A.pas", line=10, column=5,
                           message="Undeclared", message_type="error")
        d = m.to_dict()
        assert d["file_path"] == "A.pas"
        assert d["line"] == 10
        assert d["message_type"] == "error"


# ============================================================
# CompileResult
# ============================================================

class TestCompileResult:

    def test_to_dict_success(self):
        r = CompileResult(status=CompileStatus.SUCCESS, duration=100)
        d = r.to_dict()
        assert d["status"] == "success"
        assert d["duration"] == 100

    def test_has_errors_true_from_status(self):
        r = CompileResult(status=CompileStatus.FAILED)
        assert r.has_errors()

    def test_has_errors_true_from_error_list(self):
        e = CompileMessage("A.pas", 1, 1, "msg", "error")
        r = CompileResult(status=CompileStatus.FAILED, errors=[e])
        assert r.has_errors()
        assert r.get_error_count() == 1

    def test_has_errors_false(self):
        r = CompileResult(status=CompileStatus.SUCCESS)
        assert not r.has_errors()
        assert r.get_error_count() == 0

    def test_has_warnings(self):
        w = CompileMessage("A.pas", 1, 1, "msg", "warning")
        r = CompileResult(status=CompileStatus.SUCCESS, warnings=[w])
        assert r.has_warnings()
        assert r.get_warning_count() == 1

    def test_no_warnings(self):
        r = CompileResult(status=CompileStatus.SUCCESS)
        assert not r.has_warnings()

    def test_summary_success(self):
        r = CompileResult(status=CompileStatus.SUCCESS, duration=200)
        assert "编译成功" in r.get_summary()
        assert "200ms" in r.get_summary()

    def test_summary_timeout(self):
        r = CompileResult(status=CompileStatus.TIMEOUT, duration=600000)
        assert "编译超时" in r.get_summary()

    def test_summary_failed(self):
        e = CompileMessage("A.pas", 1, 1, "msg", "error")
        r = CompileResult(status=CompileStatus.FAILED, errors=[e])
        assert "编译失败" in r.get_summary()
        assert "1" in r.get_summary()

    def test_to_dict_includes_errors_and_warnings(self):
        e = CompileMessage("A.pas", 1, 1, "e", "error")
        w = CompileMessage("B.pas", 2, 2, "w", "warning")
        r = CompileResult(status=CompileStatus.FAILED, errors=[e], warnings=[w])
        d = r.to_dict()
        assert len(d["errors"]) == 1
        assert len(d["warnings"]) == 1


# ============================================================
# CompileOptions — __post_init__ 验证
# ============================================================

class TestCompileOptionsValidation:

    def test_valid_defaults(self):
        opts = CompileOptions()
        assert opts.warning_level == 2
        assert opts.timeout == 600

    def test_invalid_warning_level_raises(self):
        with pytest.raises(ValueError, match="警告级别"):
            CompileOptions(warning_level=5)

    def test_invalid_warning_level_negative(self):
        with pytest.raises(ValueError, match="警告级别"):
            CompileOptions(warning_level=-1)

    def test_invalid_timeout_zero(self):
        with pytest.raises(ValueError, match="超时时间"):
            CompileOptions(timeout=0)

    def test_invalid_timeout_negative(self):
        with pytest.raises(ValueError, match="超时时间"):
            CompileOptions(timeout=-10)

    def test_all_output_types(self):
        for ot in OutputType:
            opts = CompileOptions(output_type=ot)
            assert opts.output_type == ot

    def test_all_runtime_libraries(self):
        for rl in RuntimeLibrary:
            opts = CompileOptions(runtime_library=rl)
            assert opts.runtime_library == rl

    def test_all_target_platforms(self):
        for tp in TargetPlatform:
            opts = CompileOptions(target_platform=tp)
            assert opts.target_platform == tp

    def test_extra_args_are_preserved(self):
        opts = CompileOptions(extra_args=["-VT", "-VR"])
        assert opts.extra_args == ["-VT", "-VR"]

    @pytest.mark.parametrize("extra_args", ["-VT", [""], ["   "], [1]])
    def test_invalid_extra_args_raise(self, extra_args):
        with pytest.raises(ValueError, match="额外编译参数"):
            CompileOptions(extra_args=extra_args)


# ============================================================
# ProjectCompileRequest — __post_init__ 验证
# ============================================================

class TestProjectCompileRequestValidation:

    def test_valid_dproj(self):
        req = ProjectCompileRequest(project_path="C:\\Test\\Project.dproj")
        assert req.project_path.endswith(".dproj")

    def test_valid_dpr(self):
        req = ProjectCompileRequest(project_path="C:\\Test\\Project.dpr")
        assert req.project_path.endswith(".dpr")

    def test_valid_dpk(self):
        req = ProjectCompileRequest(project_path="C:\\Test\\Package.dpk")
        assert req.project_path.endswith(".dpk")

    def test_empty_path_raises(self):
        with pytest.raises(ValueError, match="项目路径不能为空"):
            ProjectCompileRequest(project_path="")

    def test_wrong_extension_raises(self):
        with pytest.raises(ValueError, match="项目文件必须是"):
            ProjectCompileRequest(project_path="C:\\Test\\Project.pas")

    def test_options_default(self):
        req = ProjectCompileRequest(project_path="Project.dproj")
        assert isinstance(req.options, CompileOptions)


# ============================================================
# FileCompileRequest — __post_init__ 验证
# ============================================================

class TestFileCompileRequestValidation:

    def test_valid_pas(self):
        req = FileCompileRequest(file_path="C:\\Test\\Unit.pas")
        assert req.file_path.endswith(".pas")

    def test_empty_path_raises(self):
        with pytest.raises(ValueError, match="文件路径不能为空"):
            FileCompileRequest(file_path="")

    def test_wrong_extension_raises(self):
        with pytest.raises(ValueError, match="文件必须是 .pas"):
            FileCompileRequest(file_path="C:\\Test\\Unit.dpr")

    def test_invalid_warning_level(self):
        with pytest.raises(ValueError, match="警告级别"):
            FileCompileRequest(file_path="Unit.pas", warning_level=10)

    def test_compiler_version_default_none(self):
        req = FileCompileRequest(file_path="Unit.pas")
        assert req.compiler_version is None


# ============================================================
# ConfigFile — 模型逻辑
# ============================================================

class TestConfigFile:

    def test_get_default_compiler_by_field(self):
        cf = ConfigFile(
            compilers=[
                CompilerConfig(name="A", path="a.exe", is_default=False),
                CompilerConfig(name="B", path="b.exe", is_default=True),
            ],
            default_compiler="B",
        )
        default = cf.get_default_compiler()
        assert default is not None
        assert default.name == "B"

    def test_get_default_compiler_by_is_default_flag(self):
        cf = ConfigFile(
            compilers=[
                CompilerConfig(name="A", path="a.exe"),
                CompilerConfig(name="B", path="b.exe", is_default=True),
            ],
        )
        default = cf.get_default_compiler()
        assert default is not None
        assert default.name == "B"

    def test_get_default_compiler_fallback_first(self):
        cf = ConfigFile(
            compilers=[
                CompilerConfig(name="A", path="a.exe"),
                CompilerConfig(name="B", path="b.exe"),
            ],
        )
        default = cf.get_default_compiler()
        assert default is not None
        assert default.name == "A"

    def test_get_default_compiler_empty(self):
        cf = ConfigFile()
        assert cf.get_default_compiler() is None

    def test_add_compiler_new(self):
        cf = ConfigFile()
        cf.add_compiler(CompilerConfig(name="X", path="x.exe"))
        assert cf.get_compiler("X") is not None

    def test_add_compiler_same_name_updates(self):
        cf = ConfigFile()
        cf.add_compiler(CompilerConfig(name="X", path="old.exe", version="v1"))
        cf.add_compiler(CompilerConfig(name="X", path="new.exe", version="v2"))
        c = cf.get_compiler("X")
        assert c.path == "new.exe"
        assert c.version == "v2"
        assert len(cf.compilers) == 1

    def test_add_compiler_default_clears_others(self):
        cf = ConfigFile(compilers=[
            CompilerConfig(name="A", path="a.exe", is_default=True),
        ])
        cf.add_compiler(CompilerConfig(name="B", path="b.exe", is_default=True))
        assert not cf.get_compiler("A").is_default
        assert cf.get_compiler("B").is_default
        assert cf.default_compiler == "B"

    def test_remove_compiler_normal(self):
        cf = ConfigFile(compilers=[
            CompilerConfig(name="A", path="a.exe"),
            CompilerConfig(name="B", path="b.exe"),
        ])
        assert cf.remove_compiler("A")
        assert cf.get_compiler("A") is None
        assert len(cf.compilers) == 1

    def test_remove_compiler_nonexistent(self):
        cf = ConfigFile()
        assert not cf.remove_compiler("Ghost")

    def test_remove_default_compiler_clears_field(self):
        cf = ConfigFile(
            compilers=[CompilerConfig(name="A", path="a.exe", is_default=True)],
            default_compiler="A",
        )
        cf.remove_compiler("A")
        assert cf.default_compiler is None

    def test_set_default_compiler(self):
        cf = ConfigFile(compilers=[
            CompilerConfig(name="A", path="a.exe", is_default=True),
            CompilerConfig(name="B", path="b.exe"),
        ])
        assert cf.set_default_compiler("B")
        assert cf.get_compiler("B").is_default
        assert not cf.get_compiler("A").is_default
        assert cf.default_compiler == "B"

    def test_set_default_compiler_nonexistent(self):
        cf = ConfigFile()
        assert not cf.set_default_compiler("Ghost")

    def test_to_dict_from_dict_roundtrip(self):
        cf = ConfigFile(
            compilers=[
                CompilerConfig(name="A", path="a.exe", version="v1",
                               registry_version="22.0", is_default=True),
            ],
            default_compiler="A",
        )
        d = cf.to_dict()
        cf2 = ConfigFile.from_dict(d)
        assert len(cf2.compilers) == 1
        assert cf2.compilers[0].name == "A"
        assert cf2.compilers[0].registry_version == "22.0"
        assert cf2.default_compiler == "A"


# ============================================================
# CompilerConfig — 序列化往返
# ============================================================

class TestCompilerConfig:

    def test_to_dict_from_dict(self):
        c = CompilerConfig(name="Test", path="c.exe", version="v1",
                           registry_version="23.0", is_default=True)
        d = c.to_dict()
        c2 = CompilerConfig.from_dict(d)
        assert c2.name == "Test"
        assert c2.registry_version == "23.0"

    def test_from_dict_missing_optional_fields(self):
        d = {"name": "X", "path": "x.exe"}
        c = CompilerConfig.from_dict(d)
        assert c.version is None
        assert c.registry_version is None
        assert c.is_default is False
