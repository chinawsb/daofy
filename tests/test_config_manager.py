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
