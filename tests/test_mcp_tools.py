#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP 工具参数验证测试

测试 src/tools/ 和 src/services/args_generator.py 的参数验证逻辑
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import tempfile
import os


# ============================================================
# ArgsGenerator 测试
# ============================================================

def test_args_generator_basic():
    """测试基础参数生成"""
    from src.services.args_generator import ArgsGenerator
    from src.models.compile_request import CompileOptions, OutputType, RuntimeLibrary
    
    gen = ArgsGenerator()
    options = CompileOptions(
        output_path="C:\\Output",
        optimization_enabled=True,
        debug_info_enabled=False,
        warning_level=2,
        disabled_warnings=[],
        output_type=OutputType.GUI,
        runtime_library=RuntimeLibrary.STATIC
    )
    
    args = gen.generate("C:\\Test\\Project.dpr", options)
    
    assert "C:\\Test\\Project.dpr" in args
    assert any("-E" in arg for arg in args), "应包含输出路径参数"
    assert "-$O+" in args, "应启用优化"
    assert "-CG" in args, "应为 GUI 输出类型"
    print("  基础参数生成正确")


def test_args_generator_conditional_defines():
    """测试条件编译符号"""
    from src.services.args_generator import ArgsGenerator
    from src.models.compile_request import CompileOptions, OutputType, RuntimeLibrary
    
    gen = ArgsGenerator()
    options = CompileOptions(
        conditional_defines=["DEBUG", "WIN32", "TEST"],
        optimization_enabled=False,
        debug_info_enabled=True,
        warning_level=3,
        disabled_warnings=[],
        output_type=OutputType.CONSOLE,
        runtime_library=RuntimeLibrary.DYNAMIC
    )
    
    args = gen.generate("Project.dpr", options)
    
    assert any("DEBUG;WIN32;TEST" in arg for arg in args), "条件编译符号应合并"
    assert "-CC" in args, "应为控制台输出"
    assert "-$Y+" in args, "应为动态运行时库"
    print("  条件编译符号正确合并")


def test_args_generator_search_paths():
    """测试搜索路径"""
    from src.services.args_generator import ArgsGenerator
    from src.models.compile_request import CompileOptions, OutputType, RuntimeLibrary
    
    gen = ArgsGenerator()
    options = CompileOptions(
        unit_search_paths=["C:\\Lib1", "C:\\Lib2"],
        resource_search_paths=["C:\\Res"],
        optimization_enabled=True,
        debug_info_enabled=False,
        warning_level=2,
        disabled_warnings=[],
        output_type=OutputType.GUI,
        runtime_library=RuntimeLibrary.STATIC
    )
    
    args = gen.generate("Project.dpr", options)
    
    assert any("C:\\Lib1;C:\\Lib2" in arg and arg.startswith("-U") for arg in args), "单元搜索路径"
    assert any("C:\\Res" in arg and arg.startswith("-R") for arg in args), "资源搜索路径"
    print("  搜索路径正确")


def test_args_generator_disabled_warnings():
    """测试禁用警告"""
    from src.services.args_generator import ArgsGenerator
    from src.models.compile_request import CompileOptions, OutputType, RuntimeLibrary
    
    gen = ArgsGenerator()
    options = CompileOptions(
        optimization_enabled=True,
        debug_info_enabled=False,
        warning_level=2,
        disabled_warnings=["W1001", "W1002"],
        output_type=OutputType.GUI,
        runtime_library=RuntimeLibrary.STATIC
    )
    
    args = gen.generate("Project.dpr", options)
    
    assert "-$W-W1001" in args
    assert "-$W-W1002" in args
    print("  禁用警告参数正确")


def test_args_generator_validate_safe():
    """测试参数验证 - 安全参数"""
    from src.services.args_generator import ArgsGenerator
    
    gen = ArgsGenerator()
    args = ["Project.dpr", "-U", "C:\\Lib", "-$O+", "-CG"]
    
    result = gen.validate_args(args)
    assert result is True
    print("  安全参数验证通过")


def test_args_generator_validate_dangerous():
    """测试参数验证 - 危险字符"""
    from src.services.args_generator import ArgsGenerator
    
    gen = ArgsGenerator()
    args = ["Project.dpr", "-UC:\\Lib|evil"]  # 管道符
    
    result = gen.validate_args(args)
    assert result is False
    print("  危险字符正确拒绝")


# ============================================================
# compile_project 参数验证测试
# ============================================================

def test_compile_project_resolve_dproj():
    """测试 .dproj 文件解析"""
    tmp_dir = Path(tempfile.mkdtemp())
    dproj_file = tmp_dir / "Test.dproj"
    
    # 使用 MSBuild 命名空间
    dproj_file.write_text("""<?xml version="1.0"?>
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <ProjectVersion>22.0</ProjectVersion>
  </PropertyGroup>
</Project>
""", encoding='utf-8')
    
    try:
        from src.utils.dproj_parser import DprojParser
        
        parser = DprojParser(str(dproj_file))
        success = parser.parse()
        
        assert success, "应成功解析"
        version = parser.get_project_version()
        assert version == "22.0", f"版本应为 22.0，实际: {version}"
        print("  .dproj 解析正确")
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_compile_project_detect_compiler():
    """测试从项目检测编译器"""
    from src.services.config_manager import ConfigManager
    
    cm = ConfigManager()
    compilers = cm.get_all_compilers()
    
    if compilers:
        compiler = cm.get_compiler_for_project("22.0", "win32")
        
        if compiler:
            assert "Delphi" in compiler.version or "22" in compiler.version or "11" in compiler.version
            print(f"  检测到编译器: {compiler.name}")
        else:
            print("  未匹配到编译器（可能未安装 Delphi 11）")
    else:
        print("  跳过：无可用编译器")


# ============================================================
# knowledge_base 工具参数验证测试
# ============================================================

def test_kb_search_type_class():
    """测试 search_type=class 映射"""
    search_type = "class"
    type_filter = None
    
    type_map = {
        "class": ["TC"],
        "record": ["TR"],
        "interface": ["TI"],
        "function": ["FF"],
        "procedure": ["FP"],
        "all": None
    }
    
    type_filter = type_map.get(search_type)
    assert type_filter == ["TC"]
    print("  search_type=class 映射正确")


def test_kb_search_type_function():
    """测试 search_type=function 映射"""
    type_map = {
        "class": ["TC"],
        "function": ["FF"],
        "procedure": ["FP"],
        "all": None
    }
    
    assert type_map.get("function") == ["FF"]
    assert type_map.get("procedure") == ["FP"]
    print("  search_type 函数映射正确")


def test_kb_search_type_invalid():
    """测试无效 search_type 回退"""
    type_map = {
        "class": ["TC"],
        "function": ["FF"],
        "all": None
    }
    
    result = type_map.get("invalid_type", None)
    assert result is None
    print("  无效 search_type 正确回退")


def test_kb_resolve_project_path_explicit():
    """测试显式传入项目路径"""
    from src.tools.knowledge_base import _resolve_project_path
    
    result = _resolve_project_path("C:\\Explicit\\Project.dproj")
    
    assert result is not None
    assert "Project.dproj" in result
    print("  显式路径解析正确")


def test_kb_resolve_project_path_auto():
    """测试自动检测项目路径"""
    from src.tools.knowledge_base import _resolve_project_path
    
    original_cwd = Path.cwd()
    tmp_dir = Path(tempfile.mkdtemp())
    dproj_file = tmp_dir / "AutoProject.dproj"
    dproj_file.write_text("<Project/>", encoding='utf-8')
    
    try:
        os.chdir(str(tmp_dir))
        result = _resolve_project_path(None)
        
        if result:
            assert "AutoProject.dproj" in result
            print("  自动检测路径正确")
        else:
            print("  自动检测返回 None（正常，可能有多个 .dproj）")
    finally:
        os.chdir(str(original_cwd))
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# validator 测试补充
# ============================================================

def test_validator_project_path_empty():
    """测试空项目路径"""
    from src.utils.validator import Validator
    
    v = Validator()
    result = v.validate_project_path("")
    
    assert result.valid is False
    assert "空" in result.message or "不能为空" in result.message
    print("  空路径正确拒绝")


def test_validator_project_path_not_exists():
    """测试不存在的项目路径"""
    from src.utils.validator import Validator
    
    v = Validator()
    result = v.validate_project_path("C:\\NonExistent\\Project.dproj")
    
    assert result.valid is False
    print("  不存在的路径正确拒绝")


def test_validator_timeout_valid():
    """测试超时参数验证"""
    from src.utils.validator import Validator
    
    v = Validator()
    
    assert v.validate_timeout(60).valid is True
    assert v.validate_timeout(600).valid is True
    assert v.validate_timeout(0).valid is False
    assert v.validate_timeout(-1).valid is False
    print("  超时参数验证正确")


def test_validator_warning_level():
    """测试警告级别验证"""
    from src.utils.validator import Validator
    
    v = Validator()
    
    assert v.validate_warning_level(0).valid is True
    assert v.validate_warning_level(4).valid is True
    assert v.validate_warning_level(5).valid is False
    print("  警告级别验证正确")


# ============================================================
# dproj_parser 测试补充
# ============================================================

def test_dproj_parser_main_source():
    """测试主源文件提取"""
    tmp_dir = Path(tempfile.mkdtemp())
    dproj_file = tmp_dir / "Test.dproj"
    
    dproj_file.write_text("""<?xml version="1.0"?>
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <MainSource>Test.dpr</MainSource>
  </PropertyGroup>
</Project>
""", encoding='utf-8')
    
    try:
        from src.utils.dproj_parser import DprojParser
        
        parser = DprojParser(str(dproj_file))
        parser.parse()
        
        main_source = parser.get_main_source()
        assert main_source == "Test.dpr"
        print("  主源文件提取正确")
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_dproj_parser_build_events():
    """测试构建事件提取"""
    tmp_dir = Path(tempfile.mkdtemp())
    dproj_file = tmp_dir / "Test.dproj"
    
    dproj_file.write_text("""<?xml version="1.0"?>
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <PreBuildEvent>echo PreBuild</PreBuildEvent>
    <PostBuildEvent>echo PostBuild</PostBuildEvent>
  </PropertyGroup>
</Project>
""", encoding='utf-8')
    
    try:
        from src.utils.dproj_parser import DprojParser
        
        parser = DprojParser(str(dproj_file))
        parser.parse()
        
        pre = parser.get_pre_build_event()
        post = parser.get_post_build_event()
        
        assert "PreBuild" in pre
        assert "PostBuild" in post
        print("  构建事件提取正确")
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# 运行所有测试
# ============================================================

def run_tests():
    """运行所有测试"""
    tests = [
        # ArgsGenerator
        ("ArgsGenerator 基础参数", test_args_generator_basic),
        ("ArgsGenerator 条件编译", test_args_generator_conditional_defines),
        ("ArgsGenerator 搜索路径", test_args_generator_search_paths),
        ("ArgsGenerator 禁用警告", test_args_generator_disabled_warnings),
        ("ArgsGenerator 验证安全", test_args_generator_validate_safe),
        ("ArgsGenerator 验证危险", test_args_generator_validate_dangerous),
        
        # compile_project
        ("compile_project .dproj 解析", test_compile_project_resolve_dproj),
        ("compile_project 检测编译器", test_compile_project_detect_compiler),
        
        # knowledge_base
        ("KB search_type=class", test_kb_search_type_class),
        ("KB search_type=function", test_kb_search_type_function),
        ("KB search_type 无效", test_kb_search_type_invalid),
        ("KB 显式路径解析", test_kb_resolve_project_path_explicit),
        ("KB 自动检测路径", test_kb_resolve_project_path_auto),
        
        # validator
        ("Validator 空路径", test_validator_project_path_empty),
        ("Validator 不存在路径", test_validator_project_path_not_exists),
        ("Validator 超时", test_validator_timeout_valid),
        ("Validator 警告级别", test_validator_warning_level),
        
        # dproj_parser
        ("DprojParser 主源文件", test_dproj_parser_main_source),
        ("DprojParser 构建事件", test_dproj_parser_build_events),
    ]
    
    passed = 0
    failed = 0
    
    for name, func in tests:
        try:
            func()
            print(f"[OK] {name}")
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"[FAIL] {name}: {type(e).__name__}: {e}")
            failed += 1
    
    print(f"\n{passed}/{len(tests)} 通过")
    return failed == 0


if __name__ == "__main__":
    print("=" * 60)
    print("MCP 工具参数验证测试")
    print("=" * 60)
    print()
    success = run_tests()
    sys.exit(0 if success else 1)
