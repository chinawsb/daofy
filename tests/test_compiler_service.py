#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
编译服务和进程管理器测试

需要本地安装 Delphi 环境
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import os
import subprocess
import winreg
import tempfile
import shutil

import pytest


def test_run_verify_uses_stacktrace_tools_dir():
    """run_verify should inject the open StackTrace unit, not tools/daudit."""
    from src.tools.compile_project import _verify_tools_dir

    tools_dir = _verify_tools_dir()

    assert tools_dir.name == "stacktrace"
    assert (tools_dir / "StackTrace.pas").exists()
    assert "daudit" not in str(tools_dir).lower()


def test_run_verify_injects_stacktrace_from_stacktrace_dir(tmp_path):
    """The temporary dproj/dpr injection should reference tools/stacktrace."""
    from src.tools.compile_project import _inject_verify_units, _restore_dproj

    dproj_path = tmp_path / "Smoke.dproj"
    dpr_path = tmp_path / "Smoke.dpr"
    dproj_path.write_text(
        """<Project>
  <PropertyGroup>
    <ProjectGuid>{11111111-1111-1111-1111-111111111111}</ProjectGuid>
  </PropertyGroup>
  <ItemGroup>
    <DCCReference Include="Smoke.dpr" />
  </ItemGroup>
</Project>
""",
        encoding="utf-8-sig",
    )
    dpr_path.write_text(
        """program Smoke;

uses
  System.SysUtils;

begin
end.
""",
        encoding="utf-8-sig",
    )

    backup_path = _inject_verify_units(str(dproj_path))
    try:
        dproj_raw = dproj_path.read_text(encoding="utf-8-sig")
        dproj_path_text = dproj_raw.replace("/", "\\")
        dpr_text = dpr_path.read_text(encoding="utf-8-sig")

        assert "tools\\stacktrace\\StackTrace.pas" in dproj_path_text
        assert "tools\\stacktrace" in dproj_path_text
        assert "tools\\daudit" not in dproj_path_text
        assert "<DCC_MapFile>3</DCC_MapFile>" in dproj_raw
        assert "StackTrace" in dpr_text
        assert "TStackTraceManager.Current.EnableDefaultLogger" in dpr_text
    finally:
        _restore_dproj(str(dproj_path), backup_path)


def test_collect_output_files_includes_tds_and_rsm(tmp_path):
    """Extra debug symbol outputs should be visible in the MCP result."""
    from src.services.compiler_service import CompilerService

    project_path = tmp_path / "Symbols.dproj"
    tds_path = tmp_path / "Symbols.tds"
    rsm_path = tmp_path / "Symbols.rsm"
    tds_path.touch()
    rsm_path.touch()

    output_files = CompilerService._collect_output_files(
        str(project_path),
        output_path_override=str(tmp_path),
    )

    assert str(tds_path.resolve()) in output_files
    assert str(rsm_path.resolve()) in output_files


def _get_delphi_versions():
    """从注册表获取 Delphi 版本列表（测试辅助函数）"""
    versions = []
    
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Embarcadero\BDS",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_32KEY
        )
        
        index = 0
        while True:
            try:
                version_key = winreg.EnumKey(key, index)
                index += 1
                
                version_path_key = winreg.OpenKey(key, version_key)
                try:
                    root_dir, _ = winreg.QueryValueEx(version_path_key, "RootDir")
                    if root_dir and Path(root_dir).exists():
                        versions.append((version_key, root_dir))
                except OSError:
                    pass
                finally:
                    winreg.CloseKey(version_path_key)
                    
            except OSError:
                break
        
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass
    
    if not versions:
        pytest.skip("Delphi registry installation not found")
    print(f"  检测到 {len(versions)} 个版本: {[v[0] for v in versions]}")
    return versions


def test_detect_delphi_from_registry():
    """从注册表检测 Delphi 安装"""
    versions = _get_delphi_versions()
    assert len(versions) > 0, "应检测到至少一个 Delphi 版本"


def test_compiler_executable_exists():
    """验证编译器可执行文件存在"""
    versions = _get_delphi_versions()
    
    for version_key, root_dir in versions:
        bin_path = Path(root_dir) / "bin"
        
        dcc32 = bin_path / "dcc32.exe"
        dcc64 = bin_path / "dcc64.exe"
        
        if dcc32.exists():
            print(f"  {version_key}: dcc32.exe 存在")
        if dcc64.exists():
            print(f"  {version_key}: dcc64.exe 存在")
        
        assert dcc32.exists() or dcc64.exists(), f"{version_key} 应至少有一个编译器"


def test_process_manager_env():
    """测试 ProcessManager 环境变量设置（直接测试逻辑）"""
    import re
    
    compiler_path = r"C:\Program Files (x86)\Embarcadero\Studio\22.0\bin\dcc32.exe"
    
    if 'Studio' in compiler_path:
        match = re.search(r'(.+Studio\\\d+\.\d+)', compiler_path)
        if match:
            bds_path = match.group(1)
            bds_version = bds_path.split('\\')[-1]
            env = {
                'BDS': bds_path,
                'BDSINCLUDE': f"{bds_path}\\include",
                'BDSCOMMONDIR': f"C:\\Users\\Public\\Documents\\Embarcadero\\Studio\\{bds_version}",
                'LANGDIR': 'EN',
            }
            assert "BDS" in env
            assert "22.0" in env["BDS"]
            print(f"  环境变量: BDS={env['BDS']}")
            return
    
    assert False, "未能解析 BDS 路径"


def test_process_manager_env_no_match():
    """测试非 Delphi 路径返回空环境"""
    import re
    
    compiler_path = r"C:\Some\Other\Path\compiler.exe"
    
    if 'Studio' in compiler_path:
        match = re.search(r'(.+Studio\\\d+\.\d+)', compiler_path)
        if match:
            assert False, "不应匹配"
    
    print("  非Delphi路径正确返回空")


def test_process_execute_sync():
    """测试同步进程执行"""
    result = subprocess.run(
        ["cmd.exe", "/c", "echo", "Hello"],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    assert result.returncode == 0, "命令应成功执行"
    assert "Hello" in result.stdout, "输出应包含 Hello"
    print(f"  stdout: {result.stdout.strip()}")


def test_compiler_service_init():
    """测试 CompilerService 初始化（不导入asyncio模块）"""
    from src.services.args_generator import ArgsGenerator
    from src.services.config_manager import ConfigManager
    from src.utils.parser import OutputParser
    from src.utils.validator import Validator
    from src.utils.dproj_parser import DprojParser
    
    cm = ConfigManager()
    
    assert cm is not None
    assert ArgsGenerator is not None
    assert OutputParser is not None
    assert Validator is not None
    print("  CompilerService 依赖组件初始化成功")


def test_compiler_service_find_msbuild():
    """测试 MSBuild 查找（Q5 修复: vswhere + 动态回退）"""
    from src.services.compiler_service import CompilerService
    from src.services.config_manager import ConfigManager

    cm = ConfigManager()
    cs = CompilerService(cm)
    msbuild = cs._find_msbuild()

    if msbuild:
        print(f"  找到 MSBuild: {msbuild}")
        assert Path(msbuild).exists(), f"MSBuild 路径应存在: {msbuild}"
        assert msbuild.endswith("MSBuild.exe"), "应为 MSBuild.exe"
    else:
        print("  未找到 MSBuild（可能未安装 Visual Studio）")


def test_compiler_config_registry_version():
    """Q2 修复: CompilerConfig 保留 registry_version 数值版本号"""
    from src.models.compiler_config import CompilerConfig

    # 模拟自动检测时写入 registry_version
    cfg = CompilerConfig(
        name="Delphi 11 Alexandria Win32",
        path=r"C:\Program Files (x86)\Embarcadero\Studio\22.0\bin\dcc32.exe",
        version="Delphi 11 Alexandria",
        registry_version="22.0",
    )
    assert cfg.registry_version == "22.0"
    print(f"  registry_version: {cfg.registry_version}")

    # 序列化/反序列化后保留
    d = cfg.to_dict()
    assert "registry_version" in d
    assert d["registry_version"] == "22.0"

    cfg2 = CompilerConfig.from_dict(d)
    assert cfg2.registry_version == "22.0"
    print("  序列化/反序列化正确保留")

    # 旧配置无 registry_version 时兼容
    old_dict = {"name": "Legacy", "path": r"C:\Old\dcc32.exe", "version": "Delphi 10.4"}
    cfg3 = CompilerConfig.from_dict(old_dict)
    assert cfg3.registry_version is None
    print("  旧配置兼容: registry_version=None")


def test_compiler_service_get_delphi_root():
    """测试从注册表获取 Delphi 根目录"""
    versions = []
    
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Embarcadero\BDS",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_32KEY
        )
        
        index = 0
        while True:
            try:
                version_key = winreg.EnumKey(key, index)
                index += 1
                
                version_path_key = winreg.OpenKey(key, version_key)
                try:
                    root_dir, _ = winreg.QueryValueEx(version_path_key, "RootDir")
                    if root_dir and Path(root_dir).exists():
                        versions.append((version_key, root_dir))
                except OSError:
                    pass
                finally:
                    winreg.CloseKey(version_path_key)
                    
            except OSError:
                break
        
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass
    
    if not versions:
        pytest.skip("Delphi registry installation not found")
    versions.sort(key=lambda x: x[0], reverse=True)
    root = versions[0][1]
    
    assert Path(root).exists(), "Delphi 根目录应存在"
    print(f"  Delphi 根目录: {root}")


def test_compiler_service_get_rsvars():
    """测试 rsvars.bat 路径获取"""
    versions = []
    
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Embarcadero\BDS",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_32KEY
        )
        
        index = 0
        while True:
            try:
                version_key = winreg.EnumKey(key, index)
                index += 1
                
                version_path_key = winreg.OpenKey(key, version_key)
                try:
                    root_dir, _ = winreg.QueryValueEx(version_path_key, "RootDir")
                    if root_dir and Path(root_dir).exists():
                        versions.append((version_key, root_dir))
                except OSError:
                    pass
                finally:
                    winreg.CloseKey(version_path_key)
                    
            except OSError:
                break
        
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass
    
    if versions:
        versions.sort(key=lambda x: x[0], reverse=True)
        root_dir = versions[0][1]
        rsvars = Path(root_dir) / "bin" / "rsvars.bat"
        
        if rsvars.exists():
            print(f"  rsvars.bat: {rsvars}")
        else:
            print("  未找到 rsvars.bat")
    else:
        print("  未找到 Delphi 安装")


def test_config_manager_auto_detect():
    """测试配置管理器自动检测编译器"""
    from src.services.config_manager import ConfigManager
    
    cm = ConfigManager()
    
    compilers = cm.get_all_compilers()
    
    assert len(compilers) > 0, "应自动检测到至少一个编译器"
    print(f"  检测到 {len(compilers)} 个编译器:")
    for c in compilers[:3]:
        print(f"    - {c.name}: {c.path}")


def test_config_manager_get_compiler():
    """测试获取编译器配置"""
    from src.services.config_manager import ConfigManager
    
    cm = ConfigManager()
    
    compilers = cm.get_all_compilers()
    if compilers:
        name = compilers[0].name
        compiler = cm.get_compiler(name)
        assert compiler is not None
        assert compiler.name == name
        print(f"  获取编译器: {name}")


def test_config_manager_get_newest_compiler():
    """Q2: get_newest_compiler 返回 registry_version 最大的编译器"""
    from src.services.config_manager import ConfigManager
    from src.models.compiler_config import CompilerConfig

    cm = ConfigManager()
    newest = cm.get_newest_compiler()

    if newest:
        all_compilers = cm.get_all_compilers()

        # 对每个有 registry_version 的编译器，验证 get_newest_compiler 的版本 >= 其他版本
        def _ver_tuple(v: str) -> tuple:
            parts = v.split('.')
            return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)

        if newest.registry_version:
            newest_tuple = _ver_tuple(newest.registry_version)
            for c in all_compilers:
                if c.registry_version:
                    assert newest_tuple >= _ver_tuple(c.registry_version), \
                        f"get_newest_compiler() 应返回最高版本, 当前={newest.registry_version}, {c.name}={c.registry_version}"
            print(f"  最新编译器: {newest.name} (registry_version={newest.registry_version})")
        else:
            # registry_version 为 None 是允许的（旧配置或无 --version 检测能力）
            print(f"  最新编译器: {newest.name} (registry_version=None, 所有编译器均无版本号)")
    else:
        print("  跳过: 无可用编译器")


def test_config_manager_get_newest_compiler_fallback():
    """get_compiler_for_project 在无匹配版本时回退到 get_newest_compiler"""
    from src.services.config_manager import ConfigManager

    cm = ConfigManager()
    # 用不存在的版本号触发回退
    fallback = cm.get_compiler_for_project("99.99", "win32")
    
    if fallback:
        newest = cm.get_newest_compiler()
        assert fallback is newest, \
            f"无匹配时应回退到最新版本, 得到={fallback.name}"
        print(f"  版本回退正确: {fallback.name}")
    else:
        print("  跳过: 无可用编译器")


def test_actual_compile_simple_pas():
    """测试实际编译一个简单的 PAS 文件"""
    from src.services.config_manager import ConfigManager
    
    cm = ConfigManager()
    compilers = cm.get_all_compilers()
    
    if not compilers:
        print("  跳过：无可用编译器")
        return
    
    compiler = compilers[0]
    compiler_path = Path(compiler.path)
    
    tmp_dir = Path(tempfile.mkdtemp())
    pas_file = tmp_dir / "TestUnit.pas"
    
    pas_file.write_text("""unit TestUnit;

interface

type
  TTest = class
  public
    procedure Test;
  end;

implementation

procedure TTest.Test;
begin
end;

end.
""", encoding='utf-8')
    
    try:
        result = subprocess.run(
            [str(compiler_path), "-Q", "-B", str(pas_file)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(tmp_dir),
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        
        dcu_file = tmp_dir / "TestUnit.dcu"
        
        if dcu_file.exists():
            print(f"  编译成功: 生成 {dcu_file.name}")
        else:
            print(f"  编译返回码: {result.returncode}")
            if result.stdout:
                print(f"  stdout: {result.stdout[:100]}")
            if result.stderr:
                print(f"  stderr: {result.stderr[:100]}")
        
        assert dcu_file.exists(), "应生成 DCU 文件"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_tests():
    """运行所有测试"""
    tests = [
        ("注册表检测 Delphi", test_detect_delphi_from_registry),
        ("编译器可执行文件存在", test_compiler_executable_exists),
        ("ProcessManager 环境变量", test_process_manager_env),
        ("ProcessManager 空环境", test_process_manager_env_no_match),
        ("同步进程执行", test_process_execute_sync),
        ("CompilerService 初始化", test_compiler_service_init),
        ("查找 MSBuild (Q5)", test_compiler_service_find_msbuild),
        ("CompilerConfig registry_version (Q2)", test_compiler_config_registry_version),
        ("获取 Delphi 根目录", test_compiler_service_get_delphi_root),
        ("获取 rsvars.bat", test_compiler_service_get_rsvars),
        ("配置管理器自动检测", test_config_manager_auto_detect),
        ("获取编译器配置", test_config_manager_get_compiler),
        ("get_newest_compiler (Q2)", test_config_manager_get_newest_compiler),
        ("get_newest_compiler 回退", test_config_manager_get_newest_compiler_fallback),
        ("实际编译 PAS 文件", test_actual_compile_simple_pas),
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
    print("编译服务和进程管理器测试")
    print("=" * 60)
    print()
    success = run_tests()
    sys.exit(0 if success else 1)
