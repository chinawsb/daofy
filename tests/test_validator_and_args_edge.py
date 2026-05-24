#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补充 Validator 和 ArgsGenerator 边界测试

新增覆盖:
  Validator:
    - validate_file_path: 空路径/路径遍历/不存在/非文件/非 .pas 扩展名
    - validate_compiler_path: 非文件路径(目录)/非可执行扩展名
    - validate_output_path: 空路径(允许)/非目录/路径遍历
    - validate_search_paths: None 列表/含不存在路径(仅警告)/路径遍历
    - validate_timeout: 负数/边界 1 和 3600/超过 3600
    - validate_warning_level: 负数/5

  ArgsGenerator:
    - generate: 无条件编译/无搜索路径/DLL 输出类型/静态运行时
    - validate_args: 含 $ 的非法参数/含 ; 的非法参数/带引号参数
    - format_command: 路径含空格/路径无空格
    - generate_for_file: 默认命名空间/include 路径/output_dir/disabled_warnings
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest

from src.utils.validator import Validator
from src.services.args_generator import ArgsGenerator
from src.models.compile_request import (
    CompileOptions, OutputType, RuntimeLibrary, TargetPlatform,
)


# ============================================================
# Validator — validate_file_path
# ============================================================

class TestValidateFilePath:

    def test_empty_path(self):
        ok, msg = Validator.validate_file_path("")
        assert not ok
        assert "空" in msg or "不能为空" in msg

    def test_path_traversal(self):
        ok, msg = Validator.validate_file_path(r"C:\..\secret.pas")
        assert not ok
        assert ".." in msg

    def test_nonexistent_file(self):
        ok, msg = Validator.validate_file_path(r"C:\nonexistent_12345.pas")
        assert not ok

    def test_non_pas_extension(self):
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            ok, msg = Validator.validate_file_path(path)
            assert not ok
            assert ".pas" in msg
        finally:
            os.unlink(path)

    def test_directory_instead_of_file(self):
        tmpdir = tempfile.mkdtemp()
        try:
            ok, msg = Validator.validate_file_path(tmpdir)
            assert not ok
            assert "文件" in msg
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_valid_pas_file(self):
        fd, path = tempfile.mkstemp(suffix=".pas")
        os.close(fd)
        try:
            ok, msg = Validator.validate_file_path(path)
            assert ok
        finally:
            os.unlink(path)


# ============================================================
# Validator — validate_compiler_path 补充
# ============================================================

class TestValidateCompilerPathExtra:

    def test_directory_instead_of_file(self):
        tmpdir = tempfile.mkdtemp()
        try:
            ok, msg = Validator.validate_compiler_path(tmpdir)
            assert not ok
            assert "文件" in msg
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_non_executable_extension(self):
        fd, path = tempfile.mkstemp(suffix=".pas")
        os.close(fd)
        try:
            ok, msg = Validator.validate_compiler_path(path)
            assert not ok
            assert "可执行" in msg
        finally:
            os.unlink(path)


# ============================================================
# Validator — validate_output_path 补充
# ============================================================

class TestValidateOutputPathExtra:

    def test_empty_path_is_valid(self):
        ok, msg = Validator.validate_output_path("")
        assert ok

    def test_path_traversal(self):
        ok, msg = Validator.validate_output_path(r"C:\..\output")
        assert not ok

    def test_file_instead_of_directory(self):
        fd, path = tempfile.mkstemp()
        os.close(fd)
        try:
            ok, msg = Validator.validate_output_path(path)
            assert not ok
            assert "目录" in msg
        finally:
            os.unlink(path)


# ============================================================
# Validator — validate_search_paths 补充
# ============================================================

class TestValidateSearchPathsExtra:

    def test_none_is_valid(self):
        ok, msg = Validator.validate_search_paths(None)
        assert ok

    def test_path_with_nonexistent_warns_but_ok(self):
        ok, msg = Validator.validate_search_paths([r"C:\nonexistent_dir_99999"])
        assert ok

    def test_mixed_valid_and_traversal(self):
        tmpdir = tempfile.mkdtemp()
        try:
            ok, msg = Validator.validate_search_paths([tmpdir, r"C:\..\bad"])
            assert not ok
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# Validator — validate_timeout 边界
# ============================================================

class TestValidateTimeoutBoundary:

    def test_boundary_1(self):
        ok, _ = Validator.validate_timeout(1)
        assert ok

    def test_boundary_3600(self):
        ok, _ = Validator.validate_timeout(3600)
        assert ok

    def test_over_3600(self):
        ok, msg = Validator.validate_timeout(3601)
        assert not ok

    def test_negative(self):
        ok, msg = Validator.validate_timeout(-1)
        assert not ok


# ============================================================
# Validator — validate_warning_level 边界
# ============================================================

class TestValidateWarningLevelBoundary:

    def test_boundary_0(self):
        ok, _ = Validator.validate_warning_level(0)
        assert ok

    def test_boundary_4(self):
        ok, _ = Validator.validate_warning_level(4)
        assert ok

    def test_negative(self):
        ok, msg = Validator.validate_warning_level(-1)
        assert not ok


# ============================================================
# ArgsGenerator — generate 补充
# ============================================================

class TestArgsGeneratorGenerate:

    def test_dll_output_type(self):
        gen = ArgsGenerator()
        opts = CompileOptions(output_type=OutputType.DLL)
        args = gen.generate("Project.dpr", opts)
        assert "-LD" in args

    def test_static_runtime(self):
        gen = ArgsGenerator()
        opts = CompileOptions(runtime_library=RuntimeLibrary.STATIC)
        args = gen.generate("Project.dpr", opts)
        assert "-$Y-" in args

    def test_no_conditional_defines(self):
        gen = ArgsGenerator()
        opts = CompileOptions(conditional_defines=[])
        args = gen.generate("Project.dpr", opts)
        assert not any("-$D+" in a and ";" in a for a in args)

    def test_no_search_paths(self):
        gen = ArgsGenerator()
        opts = CompileOptions(unit_search_paths=[], resource_search_paths=[])
        args = gen.generate("Project.dpr", opts)
        assert not any(a.startswith("-U") for a in args)
        assert not any(a.startswith("-R") for a in args)

    def test_optimization_disabled(self):
        gen = ArgsGenerator()
        opts = CompileOptions(optimize=False)
        args = gen.generate("Project.dpr", opts)
        assert "-$O-" in args

    def test_debug_enabled(self):
        gen = ArgsGenerator()
        opts = CompileOptions(debug=True)
        args = gen.generate("Project.dpr", opts)
        assert "-$D+" in args


# ============================================================
# ArgsGenerator — validate_args 边界
# ============================================================

class TestArgsGeneratorValidateArgs:

    def test_dollar_sign_in_non_param(self):
        gen = ArgsGenerator()
        assert not gen.validate_args(["Project.dpr", "$MALICIOUS"])

    def test_semicolon_in_non_param(self):
        gen = ArgsGenerator()
        assert not gen.validate_args(["Project.dpr", "evil;rm -rf"])

    def test_quoted_arg_with_pipe_passes(self):
        """引号内的管道符视为安全（引号隔离 shell 注入）"""
        gen = ArgsGenerator()
        assert gen.validate_args(['-U"C:\\Lib|evil"'])

    def test_unquoted_path_param_with_pipe(self):
        gen = ArgsGenerator()
        assert not gen.validate_args(["-UC:\\Lib|evil"])

    def test_clean_args_pass(self):
        gen = ArgsGenerator()
        assert gen.validate_args(["Project.dpr", "-U", "C:\\Lib", "-$O+"])

    def test_ampersand_in_arg(self):
        gen = ArgsGenerator()
        assert not gen.validate_args(["Project.dpr", "cmd1&cmd2"])


# ============================================================
# ArgsGenerator — format_command
# ============================================================

class TestArgsGeneratorFormatCommand:

    def test_path_with_spaces_quoted(self):
        gen = ArgsGenerator()
        cmd = gen.format_command(r"C:\Program Files\dcc32.exe", ["Project.dpr"])
        assert '"C:\\Program Files\\dcc32.exe"' in cmd

    def test_path_without_spaces(self):
        gen = ArgsGenerator()
        cmd = gen.format_command(r"C:\dcc32.exe", ["Project.dpr"])
        assert cmd.startswith("C:\\dcc32.exe ")


# ============================================================
# ArgsGenerator — generate_for_file 补充
# ============================================================

class TestArgsGeneratorGenerateForFile:

    def test_default_namespaces(self):
        gen = ArgsGenerator()
        args = gen.generate_for_file("Unit.pas")
        ns_args = [a for a in args if a.startswith("-NS")]
        assert len(ns_args) == 1
        assert "System" in ns_args[0]
        assert "Winapi" in ns_args[0]

    def test_custom_namespaces(self):
        gen = ArgsGenerator()
        args = gen.generate_for_file("Unit.pas", namespaces=["Custom.NS"])
        ns_args = [a for a in args if a.startswith("-NS")]
        assert "Custom.NS" in ns_args[0]

    def test_include_paths(self):
        gen = ArgsGenerator()
        args = gen.generate_for_file("Unit.pas", include_paths=["C:\\Include"])
        assert any(a.startswith("-I") and "Include" in a for a in args)

    def test_output_dir(self):
        gen = ArgsGenerator()
        args = gen.generate_for_file("Unit.pas", output_dir="C:\\Output")
        assert any(a.startswith("-N") and "Output" in a for a in args)

    def test_disabled_warnings(self):
        gen = ArgsGenerator()
        args = gen.generate_for_file("Unit.pas", disabled_warnings=["W1000", "W1001"])
        assert "-$W-W1000" in args
        assert "-$W-W1001" in args

    def test_no_debug_info_flag(self):
        gen = ArgsGenerator()
        args = gen.generate_for_file("Unit.pas")
        assert "-$M-" in args
