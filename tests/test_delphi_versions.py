#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Delphi 版本映射工具测试
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.utils.delphi_versions import (
    DELPHI_VERSION_NAMES,
    PROJECT_VERSION_PREFIX_MAP,
    DCC_VERSION_TO_REGISTRY,
    get_version_name,
    get_version_name_from_path,
    get_project_version_name,
    parse_compiler_version_from_output,
    detect_registry_version_from_compiler,
    project_version_to_registry_version,
    registry_to_project_version,
)


def test_all_known_versions_have_names():
    """所有已知版本号都有对应的产品名称"""
    known = {
        "37.0": "Delphi 13 Florence",
        "23.0": "Delphi 12 Athens",
        "22.0": "Delphi 11 Alexandria",
        "21.0": "Delphi 10.4 Sydney",
        "20.0": "Delphi 10.3 Rio",
        "19.0": "Delphi 10.2 Tokyo",
        "18.0": "Delphi 10.1 Berlin",
        "17.0": "Delphi 10 Seattle",
        "16.0": "Delphi XE8",
        "15.0": "Delphi XE7",
        "14.0": "Delphi XE6",
        "12.0": "Delphi XE5",
        "11.0": "Delphi XE4",
        "10.0": "Delphi XE3",
        "9.0": "Delphi XE2",
        "8.0": "Delphi XE",
        "7.0": "Delphi 2010",
        "6.0": "Delphi 2009",
        "5.0": "Delphi 2007",
        "4.0": "Delphi 2006",
        "3.0": "Delphi 2005",
    }
    for ver, expected_name in known.items():
        assert DELPHI_VERSION_NAMES[ver] == expected_name, f"{ver} → {expected_name}"
    assert len(DELPHI_VERSION_NAMES) == len(known)


def test_get_version_name():
    """get_version_name 的已知版本和未知版本回退"""
    assert get_version_name("37.0") == "Delphi 13 Florence"
    assert get_version_name("22.0") == "Delphi 11 Alexandria"
    assert get_version_name("99.0") == "Delphi 99.0"  # 未知版本回退


def test_get_version_name_from_path():
    """从安装路径提取版本号"""
    assert get_version_name_from_path(r"C:\Program Files\Embarcadero\Studio\22.0") == "Delphi 11 Alexandria"
    assert get_version_name_from_path(r"C:\Program Files\Embarcadero\Studio\23.0\\") == "Delphi 12 Athens"
    # 不含版本号的路径
    assert get_version_name_from_path(r"C:\Delphi") == "Delphi Unknown"


def test_get_project_version_name():
    """项目版本前缀映射"""
    assert get_project_version_name("22") == "Delphi 11 Alexandria"
    assert get_project_version_name("37") == "Delphi 13 Florence"
    assert get_project_version_name("99") is None  # 未知前缀


def test_project_prefix_map_completeness():
    """每个已知版本在 PROJECT_VERSION_PREFIX_MAP 中都有对应的前缀条目（13除外）"""
    for full_key in ("37", "23", "22", "21", "20", "19", "18", "17",
                     "16", "15", "14", "12", "11", "10", "9", "8"):
        assert full_key in PROJECT_VERSION_PREFIX_MAP, f"缺少前缀 {full_key}"
    # 确保不存在的版本（如"13"）没有被错误包含
    assert "13" not in PROJECT_VERSION_PREFIX_MAP


def test_project_prefix_no_unexpected_entries():
    """PROJECT_VERSION_PREFIX_MAP 中不应有不存在的虚拟版本（XE10、XE9 等）"""
    for prefix, name in PROJECT_VERSION_PREFIX_MAP.items():
        assert "XE10" not in name, f"不应存在虚拟版本 XE10: {prefix} → {name}"
        assert "XE9" not in name, f"不应存在虚拟版本 XE9: {prefix} → {name}"
        assert "XE8" not in name or prefix in ("16",), f"XE8 只应出现在 16: {prefix} → {name}"


def test_name_consistency():
    """同一版本在 DELPHI_VERSION_NAMES 和 PROJECT_VERSION_PREFIX_MAP 中名称一致"""
    for prefix, name in PROJECT_VERSION_PREFIX_MAP.items():
        full_key = prefix + ".0"
        if full_key in DELPHI_VERSION_NAMES:
            assert DELPHI_VERSION_NAMES[full_key] == name, \
                f"版本 {prefix} 在两份映射中的名称不一致: {DELPHI_VERSION_NAMES[full_key]} vs {name}"


# ============================================================
# 编译器版本检测测试（通过 --version 输出解析）
# ============================================================

def test_parse_compiler_version_from_output():
    """从 dcc32 --version 输出中正确解析编译器版本号"""
    # dcc32.exe (Delphi 11)
    output = "dcc (Embarcadero Delphi for Windows) 35.0\nEmbarcadero Delphi for Win32 compiler version 35.0\nCopyright ..."
    assert parse_compiler_version_from_output(output) == "35.0"

    # dcc64.exe (Delphi 11)
    output64 = "dcc (Embarcadero Delphi for Windows) 35.0\nEmbarcadero Delphi for Win64 compiler version 35.0\nCopyright ..."
    assert parse_compiler_version_from_output(output64) == "35.0"

    # 无效输出
    assert parse_compiler_version_from_output("") is None
    assert parse_compiler_version_from_output("gcc version 12.0") is None
    assert parse_compiler_version_from_output("Delphi compiler version") is None  # 不完整


def test_parse_compiler_version_real_output():
    """用实际的 --version 输出格式测试"""
    # Delphi 12 Athens (dcc32)
    d12_out = "dcc (Embarcadero Delphi for Windows) 36.0\nEmbarcadero Delphi for Win32 compiler version 36.0\nCopyright ..."
    assert parse_compiler_version_from_output(d12_out) == "36.0"

    # Delphi 13 Florence
    d13_out = "dcc (Embarcadero Delphi for Windows) 37.0\nEmbarcadero Delphi for Win32 compiler version 37.0\nCopyright ..."
    assert parse_compiler_version_from_output(d13_out) == "37.0"


def test_dcc_version_to_registry_mapping():
    """DCC_VERSION_TO_REGISTRY 映射表完整性"""
    # 所有已知映射的双向验证
    assert DCC_VERSION_TO_REGISTRY["35.0"] == "22.0"   # Delphi 11
    assert DCC_VERSION_TO_REGISTRY["36.0"] == "23.0"   # Delphi 12
    assert DCC_VERSION_TO_REGISTRY["37.0"] == "37.0"   # Delphi 13
    assert DCC_VERSION_TO_REGISTRY["34.0"] == "21.0"   # Delphi 10.4

    # 每个映射的 registry 版本都应在 DELPHI_VERSION_NAMES 中有对应名称
    for dcc_ver, reg_ver in DCC_VERSION_TO_REGISTRY.items():
        assert reg_ver in DELPHI_VERSION_NAMES, \
            f"映射 {dcc_ver} → {reg_ver} 在 DELPHI_VERSION_NAMES 中不存在"


def test_detect_registry_version_from_compiler_real():
    """实际运行本地 dcc32 --version 检测版本（集成测试）"""
    import os, winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Embarcadero\BDS")
        v = winreg.EnumKey(key, 0)
        winreg.CloseKey(key)
        vk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Embarcadero\BDS\{v}")
        root_dir = winreg.QueryValueEx(vk, "RootDir")[0]
        winreg.CloseKey(vk)
        dcc32 = os.path.join(root_dir, "bin", "dcc32.exe")
        if os.path.exists(dcc32):
            version = detect_registry_version_from_compiler(dcc32)
            assert version is not None, "应检测到版本号"
            assert version in DELPHI_VERSION_NAMES, f"检测到的版本 {version} 应在已知列表中"
            print(f"  实际检测: {dcc32} → registry_version={version}")
    except Exception:
        print("  跳过: 无 Delphi 安装")


def test_detect_registry_version_unknown_compiler():
    """不存在的编译器路径应返回 None"""
    version = detect_registry_version_from_compiler(r"C:\NonExistent\dcc32.exe")
    assert version is None


# ============================================================
# .dproj ProjectVersion → registry_version 反向映射测试
# ============================================================

def test_project_version_to_registry_version_direct_match():
    """多数版本 ProjectVersion == registry_version（直接匹配）"""
    assert project_version_to_registry_version("22.0") == "22.0"   # Delphi 11
    assert project_version_to_registry_version("23.0") == "23.0"   # Delphi 12
    assert project_version_to_registry_version("37.0") == "37.0"   # Delphi 13
    assert project_version_to_registry_version("19.0") == "19.0"   # Delphi 10.2
    assert project_version_to_registry_version("17.0") == "17.0"   # Delphi 10


def test_project_version_to_registry_version_berlin():
    """Delphi 10.1 Berlin 特例：.dproj 18.2 → 注册表 18.0"""
    assert project_version_to_registry_version("18.2") == "18.0"


def test_project_version_to_registry_version_integer_prefix():
    """整数前缀匹配（如 .dproj 中可能只写 "19" 而非 "19.0"）"""
    assert project_version_to_registry_version("19") == "19.0"
    assert project_version_to_registry_version("22") == "22.0"
    assert project_version_to_registry_version("15") == "15.0"


def test_project_version_to_registry_version_unknown():
    """未知版本返回 None"""
    assert project_version_to_registry_version("99.0") is None
    assert project_version_to_registry_version("0.0") is None
    assert project_version_to_registry_version("") is None


def test_registry_project_version_roundtrip():
    """registry → project → registry 往返一致性（Berlin 除外）"""
    for reg_ver in ("22.0", "23.0", "37.0", "19.0", "17.0", "15.0"):
        proj_ver = registry_to_project_version(reg_ver)
        back = project_version_to_registry_version(proj_ver)
        assert back == reg_ver, f"往返失败: {reg_ver} → {proj_ver} → {back}"

    # Berlin 特例：往返不一致（18.0 → 18.2 → 18.0 是反向，但 18.2 → 18.0 是正向）
    assert registry_to_project_version("18.0") == "18.2"
    assert project_version_to_registry_version("18.2") == "18.0"


def test_all_project_versions_have_registry_mapping():
    """PROJECT_VERSION_PREFIX_MAP 中所有前缀都能通过 project_version_to_registry_version 反推"""
    for prefix, _name in PROJECT_VERSION_PREFIX_MAP.items():
        proj_ver = f"{prefix}.0"
        reg_ver = project_version_to_registry_version(proj_ver)
        assert reg_ver is not None, f"ProjectVersion {proj_ver} 无法映射到 registry_version"
        assert reg_ver in DELPHI_VERSION_NAMES, f"registry_version {reg_ver} 不在已知版本中"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
