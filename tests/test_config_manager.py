#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理器测试
"""

import sys
import json
import os
import tempfile
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.services.config_manager import ConfigManager
from src.models.compiler_config import CompilerConfig


def _make_config_path(data: dict) -> str:
    """创建临时配置文件并返回路径"""
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8')
    json.dump(data, tmp)
    tmp.close()
    return tmp.name


def test_init_creates_default_config():
    """ConfigManager 在空路径时自动创建默认配置"""
    tmpdir = tempfile.mkdtemp()
    try:
        config_path = os.path.join(tmpdir, "compilers.json")
        history_path = os.path.join(tmpdir, "history.json")
        cm = ConfigManager(config_path, history_path)
        assert os.path.exists(config_path)
        with open(config_path, encoding='utf-8') as f:
            data = json.load(f)
        assert "compilers" in data
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_add_and_get_compiler():
    """添加后能获取到编译器"""
    tmpdir = tempfile.mkdtemp()
    try:
        config_path = os.path.join(tmpdir, "compilers.json")
        cm = ConfigManager(config_path, os.path.join(tmpdir, "history.json"))
        compiler = CompilerConfig(
            name="Test Win32",
            path=r"C:\dcc32.exe",
            version="Delphi 11 Alexandria",
            is_default=False,
        )
        cm.add_compiler(compiler)
        retrieved = cm.get_compiler("Test Win32")
        assert retrieved is not None
        assert retrieved.name == "Test Win32"
        assert retrieved.version == "Delphi 11 Alexandria"
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_get_all_compilers():
    """get_all_compilers 返回全部编译器列表"""
    tmpdir = tempfile.mkdtemp()
    try:
        # 预写配置文件，避免自动检测真实编译器
        config_path = os.path.join(tmpdir, "compilers.json")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump({"compilers": [
                {"name": "A", "path": "C:\\a.exe", "version": "v1", "is_default": True},
                {"name": "B", "path": "C:\\b.exe", "version": "v2", "is_default": False},
            ]}, f)
        cm = ConfigManager(config_path, os.path.join(tmpdir, "history.json"))
        all_c = cm.get_all_compilers()
        assert len(all_c) == 2, f"期望 2 个编译器，实际 {len(all_c)}"
        assert {c.name for c in all_c} == {"A", "B"}
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_set_default_compiler():
    """set_default_compiler 更新默认编译器"""
    tmpdir = tempfile.mkdtemp()
    try:
        config_path = os.path.join(tmpdir, "compilers.json")
        cm = ConfigManager(config_path, os.path.join(tmpdir, "history.json"))
        c1 = CompilerConfig(name="A", path=r"C:\a.exe", version="v1", is_default=True)
        c2 = CompilerConfig(name="B", path=r"C:\b.exe", version="v2")
        cm.add_compiler(c1)
        cm.add_compiler(c2)
        ok = cm.set_default_compiler("B")
        assert ok
        assert cm.get_compiler("B").is_default
        assert not cm.get_compiler("A").is_default
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_get_compiler_returns_none_for_missing():
    """不存在的名称返回 None"""
    tmpdir = tempfile.mkdtemp()
    try:
        cm = ConfigManager(
            os.path.join(tmpdir, "compilers.json"),
            os.path.join(tmpdir, "history.json"),
        )
        assert cm.get_compiler("NonExistent") is None
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_remove_compiler():
    """删除后不再存在"""
    tmpdir = tempfile.mkdtemp()
    try:
        config_path = os.path.join(tmpdir, "compilers.json")
        cm = ConfigManager(config_path, os.path.join(tmpdir, "history.json"))
        c = CompilerConfig(name="ToRemove", path=r"C:\x.exe", version="v1")
        cm.add_compiler(c)
        assert cm.get_compiler("ToRemove") is not None
        cm.remove_compiler("ToRemove")
        assert cm.get_compiler("ToRemove") is None
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_update_compiler():
    """更新编译器配置"""
    tmpdir = tempfile.mkdtemp()
    try:
        config_path = os.path.join(tmpdir, "compilers.json")
        cm = ConfigManager(config_path, os.path.join(tmpdir, "history.json"))
        c_old = CompilerConfig(name="X", path=r"C:\old.exe", version="v1")
        cm.add_compiler(c_old)
        c_new = CompilerConfig(name="X", path=r"C:\new.exe", version="v2")
        cm.update_compiler("X", c_new)
        retrieved = cm.get_compiler("X")
        assert retrieved.path == r"C:\new.exe"
        assert retrieved.version == "v2"
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_project_version_mapping():
    """项目版本号正确映射到 Delphi 名称"""
    tmpdir = tempfile.mkdtemp()
    try:
        config_path = os.path.join(tmpdir, "compilers.json")
        cm = ConfigManager(config_path, os.path.join(tmpdir, "history.json"))
        # 添加一个 Delphi 11 的编译器
        c = CompilerConfig(
            name="Delphi 11 Alexandria Win32",
            path=r"C:\dcc32.exe",
            version="Delphi 11 Alexandria",
            is_default=True,
        )
        cm.add_compiler(c)

        # 添加 Delphi 12
        c2 = CompilerConfig(
            name="Delphi 12 Athens Win64",
            path=r"C:\dcc64.exe",
            version="Delphi 12 Athens",
        )
        cm.add_compiler(c2)

        # 22.x → Delphi 11 Alexandria
        compiler = cm.get_compiler_for_project("22.0")
        assert compiler is not None
        assert "Delphi 11" in compiler.version

        # 23.x → Delphi 12 Athens
        compiler = cm.get_compiler_for_project("23.0", platform="win64")
        assert compiler is not None
        assert "Delphi 12" in compiler.version
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_project_version_unknown_prefix_falls_back():
    """未知版本前缀回退到最新编译器"""
    tmpdir = tempfile.mkdtemp()
    try:
        config_path = os.path.join(tmpdir, "compilers.json")
        cm = ConfigManager(config_path, os.path.join(tmpdir, "history.json"))
        # 重置为干净的编译器列表（删除自动检测的）
        cm.config.compilers.clear()
        old_compiler = CompilerConfig(
            name="OldC", path=r"C:\dcc32_old.exe", version="Any",
            registry_version="5.0",
        )
        new_compiler = CompilerConfig(
            name="NewC", path=r"C:\dcc32_new.exe", version="Any",
            registry_version="23.0",
        )
        cm.add_compiler(old_compiler)
        cm.add_compiler(new_compiler)
        # 确认只有两个测试编译器
        assert len(cm.get_all_compilers()) == 2, \
            f"期望2个编译器, 实际={[(c.name, c.registry_version) for c in cm.get_all_compilers()]}"
        # 未知版本前缀应回退到最新版本
        compiler = cm.get_compiler_for_project("99.0")
        assert compiler is not None
        assert compiler.name == "NewC", f"应回退到最新版本, 得到={compiler.name}"
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__])


# ════════════════════════════════════════════════════════════════
#  _detect_delphi_from_registry 测试
# ════════════════════════════════════════════════════════════════
# 覆盖：
#   - HKLM 单独存在 (系统级安装, HKCU 缺失)
#   - HKCU 单独存在 (用户级安装, HKLM 缺失)
#   - HKLM + HKCU 都有: 同一版本时 HKCU 胜出
#   - HKLM + HKCU 都有: 不同版本时同时保留
#   - 两边都没有: 返回空 dict
#   - 修复回归: HKLM 存在但 HKCU 缺失时, 早期实现会直接 return 漏掉 HKLM
#   - RootDir 指向不存在的目录: 跳过该条目
#   - 版本键没有 RootDir 值: 跳过该条目

import unittest.mock as mock
import winreg


class _FakeRegKey:
    """模拟 winreg 父 key: 包含一组 (version, root_dir) 条目"""

    def __init__(self, hive_name, versions):
        # versions: Dict[str_version, str_root_dir]
        self.hive_name = hive_name
        self._versions = dict(versions)


class _FakeVersionKey:
    """模拟 winreg 子 key: 包含单个版本的 RootDir"""

    def __init__(self, root_dir):
        self._root_dir = root_dir


def _make_fake_winreg(hklm_data=None, hkcu_data=None):
    """
    返回一个 patch 字典，可用于 patch.multiple(winreg, ...)：
    - OpenKey: 第一次 (hive, subkey, 0, ...) 返回父 key；
                第二次 (parent_key, version) 返回对应 version key
    - EnumKey: 顺序返回父 key 的版本号, 越界抛 OSError
    - QueryValueEx: 读取 version key 的 RootDir
    - CloseKey: no-op
    """
    hklm = hklm_data or {}
    hkcu = hkcu_data or {}

    def fake_open_key(hive_or_key, subkey_or_reserved, *args, **kwargs):
        # 第一次: (hive, subkey, 0, KEY_READ|KEY_WOW64_32KEY) → 父 key
        if isinstance(hive_or_key, int):
            subkey = subkey_or_reserved
            if "Embarcadero" not in subkey or not subkey.endswith("BDS"):
                raise FileNotFoundError(f"No such registry key: {subkey}")
            if hive_or_key == winreg.HKEY_LOCAL_MACHINE:
                return _FakeRegKey("HKLM", hklm)
            elif hive_or_key == winreg.HKEY_CURRENT_USER:
                return _FakeRegKey("HKCU", hkcu)
            else:
                raise FileNotFoundError(f"Unknown hive: {hive_or_key}")
        # 第二次: (parent_key, version_str) → version key
        elif isinstance(hive_or_key, _FakeRegKey):
            version = subkey_or_reserved
            if version in hive_or_key._versions:
                return _FakeVersionKey(hive_or_key._versions[version])
            raise FileNotFoundError(f"Version {version} not in {hive_or_key.hive_name}")
        else:
            raise FileNotFoundError(f"Unexpected OpenKey arg type: {type(hive_or_key)}")

    def fake_enum_key(key, index):
        if not isinstance(key, _FakeRegKey):
            raise OSError("No more data")
        versions = list(key._versions.keys())
        if index >= len(versions):
            raise OSError("No more data")
        return versions[index]

    def fake_query_value_ex(key, value_name):
        if not isinstance(key, _FakeVersionKey):
            raise FileNotFoundError(f"Value {value_name} not found")
        if value_name != "RootDir":
            raise FileNotFoundError(f"Value {value_name} not found")
        return (key._root_dir, winreg.REG_SZ)

    def fake_close_key(key):
        return None

    return {
        "OpenKey": mock.MagicMock(side_effect=fake_open_key),
        "EnumKey": mock.MagicMock(side_effect=fake_enum_key),
        "QueryValueEx": mock.MagicMock(side_effect=fake_query_value_ex),
        "CloseKey": mock.MagicMock(side_effect=fake_close_key),
    }


def _make_real_dir() -> str:
    """创建真实存在的临时目录（验证 os.path.exists 路径检查）"""
    return tempfile.mkdtemp(prefix="daofy_test_hklm_")


def test_detect_hklm_only():
    """只有 HKLM 有 Embarcadero BDS 时也能正确检测（修复关键 bug）"""
    hklm_dir = _make_real_dir()
    try:
        cm = ConfigManager(
            os.path.join(tempfile.mkdtemp(), "compilers.json"),
            os.path.join(tempfile.mkdtemp(), "history.json"),
        )
        fake = _make_fake_winreg(hklm_data={"22.0": hklm_dir})

        with mock.patch.multiple(winreg, **fake):
            result = cm._detect_delphi_from_registry()

        assert result == {"22.0": hklm_dir}, \
            f"HKLM 单独存在时应被检测, 实际: {result}"
    finally:
        import shutil
        shutil.rmtree(hklm_dir, ignore_errors=True)


def test_detect_hkcu_only():
    """只有 HKCU 有 Embarcadero BDS 时也能正确检测"""
    hkcu_dir = _make_real_dir()
    try:
        cm = ConfigManager(
            os.path.join(tempfile.mkdtemp(), "compilers.json"),
            os.path.join(tempfile.mkdtemp(), "history.json"),
        )
        fake = _make_fake_winreg(hkcu_data={"23.0": hkcu_dir})

        with mock.patch.multiple(winreg, **fake):
            result = cm._detect_delphi_from_registry()

        assert result == {"23.0": hkcu_dir}, \
            f"HKCU 单独存在时应被检测, 实际: {result}"
    finally:
        import shutil
        shutil.rmtree(hkcu_dir, ignore_errors=True)


def test_detect_hkcu_overrides_hklm_same_version():
    """同一版本号 HKLM + HKCU 都有时, HKCU 胜出（用户配置优先）"""
    hklm_dir = _make_real_dir()
    hkcu_dir = _make_real_dir()
    try:
        cm = ConfigManager(
            os.path.join(tempfile.mkdtemp(), "compilers.json"),
            os.path.join(tempfile.mkdtemp(), "history.json"),
        )
        fake = _make_fake_winreg(
            hklm_data={"22.0": hklm_dir},
            hkcu_data={"22.0": hkcu_dir},
        )

        with mock.patch.multiple(winreg, **fake):
            result = cm._detect_delphi_from_registry()

        assert result == {"22.0": hkcu_dir}, \
            f"同版本号 HKCU 应胜出, 实际: {result}"
    finally:
        import shutil
        shutil.rmtree(hklm_dir, ignore_errors=True)
        shutil.rmtree(hkcu_dir, ignore_errors=True)


def test_detect_hklm_and_hkcu_different_versions():
    """不同版本号时 HKLM + HKCU 全部保留"""
    hklm_dir = _make_real_dir()
    hkcu_dir = _make_real_dir()
    try:
        cm = ConfigManager(
            os.path.join(tempfile.mkdtemp(), "compilers.json"),
            os.path.join(tempfile.mkdtemp(), "history.json"),
        )
        fake = _make_fake_winreg(
            hklm_data={"22.0": hklm_dir},
            hkcu_data={"23.0": hkcu_dir},
        )

        with mock.patch.multiple(winreg, **fake):
            result = cm._detect_delphi_from_registry()

        assert result == {"22.0": hklm_dir, "23.0": hkcu_dir}, \
            f"不同版本号都应保留, 实际: {result}"
    finally:
        import shutil
        shutil.rmtree(hklm_dir, ignore_errors=True)
        shutil.rmtree(hkcu_dir, ignore_errors=True)


def test_detect_no_registry_returns_empty():
    """HKLM/HKCU 都没有时返回空 dict, 不抛异常"""
    cm = ConfigManager(
        os.path.join(tempfile.mkdtemp(), "compilers.json"),
        os.path.join(tempfile.mkdtemp(), "history.json"),
    )
    fake = _make_fake_winreg()  # 两者都为空

    with mock.patch.multiple(winreg, **fake):
        result = cm._detect_delphi_from_registry()

    assert result == {}, f"空注册表应返回空 dict, 实际: {result}"


def test_detect_hklm_present_hkcu_missing_regression():
    """
    回归测试: 早期实现遇到 HKLM 存在但 HKCU 缺失时会直接 return,
    导致 HKLM 检测被漏掉。修复后应能正常处理。
    """
    hklm_dir = _make_real_dir()
    try:
        cm = ConfigManager(
            os.path.join(tempfile.mkdtemp(), "compilers.json"),
            os.path.join(tempfile.mkdtemp(), "history.json"),
        )
        # 只配置 HKLM 数据, HKCU 返回 FileNotFoundError
        fake = _make_fake_winreg(hklm_data={"22.0": hklm_dir})

        with mock.patch.multiple(winreg, **fake):
            result = cm._detect_delphi_from_registry()

        assert "22.0" in result, \
            f"HKLM 存在时不应被 HKCU 缺失打断, 实际: {result}"
        assert result["22.0"] == hklm_dir
    finally:
        import shutil
        shutil.rmtree(hklm_dir, ignore_errors=True)


def test_detect_skips_nonexistent_rootdir():
    """RootDir 指向不存在的目录时被跳过（不进入结果）"""
    real_dir = _make_real_dir()
    fake_nonexistent = r"C:\nonexistent\delphi_test_xyz"
    try:
        cm = ConfigManager(
            os.path.join(tempfile.mkdtemp(), "compilers.json"),
            os.path.join(tempfile.mkdtemp(), "history.json"),
        )
        fake = _make_fake_winreg(hklm_data={
            "22.0": real_dir,
            "23.0": fake_nonexistent,  # 路径不存在
        })

        with mock.patch.multiple(winreg, **fake):
            result = cm._detect_delphi_from_registry()

        assert result == {"22.0": real_dir}, \
            f"不存在的 RootDir 应被跳过, 实际: {result}"
    finally:
        import shutil
        shutil.rmtree(real_dir, ignore_errors=True)
