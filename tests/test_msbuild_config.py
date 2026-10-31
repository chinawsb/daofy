#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本→MSBuild 映射与项目级工具链解析测试。

全局 ``msbuild_path`` / ``default_registry_version`` 与环境变量覆盖已移除：
- MSBuild 只来自项目配置、``msbuild_by_delphi_version`` 或自动探测
- Delphi 版本只来自项目配置或 ``.dproj ProjectVersion``
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.models.compiler_config import ConfigFile, CompilerConfig
from src.services.compiler_service import CompilerService
from src.services.config_manager import ConfigManager
from src.services.project_settings import ProjectSettings
from src.utils.delphi_versions import resolve_registry_version


def _write_config(tmp_path: Path, **overrides) -> Path:
    """在临时目录写入 compilers.json。"""
    data = {
        "compilers": [
            {
                "name": "Delphi XE4 Win32",
                "path": r"C:\Embarcadero\RAD Studio\11.0\bin\dcc32.exe",
                "is_default": False,
                "version": "Delphi XE4",
                "registry_version": "11.0",
            },
            {
                "name": "Delphi XE4 Win64",
                "path": r"C:\Embarcadero\RAD Studio\11.0\bin\dcc64.exe",
                "is_default": False,
                "version": "Delphi XE4",
                "registry_version": "11.0",
            },
            {
                "name": "Delphi XE8 Win32",
                "path": r"C:\Embarcadero\Studio\16.0\bin\dcc32.exe",
                "is_default": True,
                "version": "Delphi XE8",
                "registry_version": "16.0",
            },
        ],
        "default_compiler": "Delphi XE8 Win32",
    }
    data.update(overrides)
    config_path = tmp_path / "compilers.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return config_path


def _make_manager(tmp_path: Path, **overrides) -> ConfigManager:
    config_path = _write_config(tmp_path, **overrides)
    return ConfigManager(str(config_path), str(tmp_path / "history.json"))


def test_config_roundtrip_keeps_only_version_map():
    config = ConfigFile(
        compilers=[CompilerConfig(name="A", path="a.exe")],
        msbuild_by_delphi_version={"11.0": r"C:\Framework\v3.5\MSBuild.exe"},
    )

    payload = config.to_dict()
    restored = ConfigFile.from_dict(payload)

    assert "msbuild_path" not in payload
    assert "default_registry_version" not in payload
    assert restored.msbuild_by_delphi_version == config.msbuild_by_delphi_version


def test_removed_global_keys_are_ignored_on_load(tmp_path):
    config_path = _write_config(
        tmp_path,
        msbuild_path=r"C:\Old\MSBuild.exe",
        default_registry_version="11.0",
    )

    manager = ConfigManager(str(config_path), str(tmp_path / "history.json"))

    assert "msbuild_path" not in manager.config.to_dict()
    assert "default_registry_version" not in manager.config.to_dict()
    # 没有项目配置时使用默认编译器，而不是旧全局 pin
    assert manager.get_effective_compiler(platform="win32").name == "Delphi XE8 Win32"


def test_msbuild_map_accepts_product_name_and_project_version(tmp_path):
    manager = _make_manager(
        tmp_path,
        msbuild_by_delphi_version={
            "XE4": r"C:\Framework\v3.5\MSBuild.exe",
            "14.6": r"C:\Framework\v4.0\MSBuild.exe",
        },
    )

    assert manager.get_msbuild_for_version("11.0") == r"C:\Framework\v3.5\MSBuild.exe"
    assert manager.get_msbuild_for_version("14.0") == r"C:\Framework\v4.0\MSBuild.exe"


def test_msbuild_map_relative_path_is_resolved_against_config_dir(tmp_path):
    manager = _make_manager(
        tmp_path,
        msbuild_by_delphi_version={"11.0": r"tools\MSBuild.exe"},
    )

    assert manager.get_msbuild_for_version("11.0") == str(
        tmp_path / "tools" / "MSBuild.exe"
    )


def test_effective_compiler_has_no_global_pin(tmp_path):
    manager = _make_manager(tmp_path)

    assert manager.get_effective_compiler(platform="win32").name == "Delphi XE8 Win32"
    assert manager.get_compiler_for_project("14.6", "win32") is not None


def test_version_matches_compiler_without_registry_version(tmp_path):
    """手工配置的编译器没有 registry_version 时，按产品名回退匹配。"""
    manager = _make_manager(
        tmp_path,
        compilers=[
            {
                "name": "XE4 dcc32",
                "path": r"C:\Delphi\11.0\bin\dcc32.exe",
                "is_default": True,
                "version": "Delphi XE4",
            }
        ],
        default_compiler="XE4 dcc32",
    )

    compiler = manager.get_compiler_by_registry_version("11.0", "win32")

    assert compiler is not None
    assert compiler.name == "XE4 dcc32"


def test_rsvars_uses_explicit_version(tmp_path):
    manager = _make_manager(tmp_path)
    service = CompilerService(manager)

    fake_root = tmp_path / "RAD Studio" / "11.0"
    (fake_root / "bin").mkdir(parents=True)
    (fake_root / "bin" / "rsvars.bat").write_text("@echo off", encoding="utf-8")
    captured = {}

    def fake_root_lookup(version=None):
        captured["version"] = version
        return str(fake_root)

    service._get_delphi_root_from_registry = fake_root_lookup

    rsvars = service._get_rsvars_path("11.0")

    assert captured["version"] == "11.0"
    assert rsvars == str(fake_root / "bin" / "rsvars.bat")


def test_effective_delphi_root_uses_explicit_version(tmp_path):
    manager = _make_manager(tmp_path)
    service = object.__new__(CompilerService)
    service.config_manager = manager
    captured = {}

    def fake_root_lookup(version=None):
        captured["version"] = version
        return str(tmp_path / "RAD Studio" / "11.0")

    service._get_delphi_root_from_registry = fake_root_lookup

    assert service._get_effective_delphi_root("11.0") == str(
        tmp_path / "RAD Studio" / "11.0"
    )
    assert captured["version"] == "11.0"


def test_resolve_registry_version_uses_project_override(tmp_path):
    manager = _make_manager(tmp_path)

    assert resolve_registry_version(
        None,
        "14.6",
        manager,
        override_version="11.0",
    ) == "11.0"


def _make_msbuild_service(tmp_path: Path, **config_overrides):
    msbuild = tmp_path / "project-MSBuild.exe"
    msbuild.write_text("stub", encoding="utf-8")
    service = object.__new__(CompilerService)
    service.msbuild_path = None
    service._msbuild_auto_cache = {}
    service.config_manager = SimpleNamespace(**config_overrides)
    return service, msbuild


def test_resolve_msbuild_path_prefers_project_path(tmp_path):
    mapped = tmp_path / "mapped-MSBuild.exe"
    mapped.write_text("stub", encoding="utf-8")
    service, project_msbuild = _make_msbuild_service(
        tmp_path,
        get_msbuild_for_version=lambda version: str(mapped),
    )
    settings = ProjectSettings(
        msbuild_path=str(project_msbuild),
        source=str(tmp_path / ".daofy" / "project.json"),
    )

    path, _source, explicit_error = service._resolve_msbuild_path("11.0", settings)

    assert path == str(project_msbuild)
    assert explicit_error is False


def test_resolve_msbuild_path_map_used_when_project_has_no_path(tmp_path):
    mapped = tmp_path / "mapped-MSBuild.exe"
    mapped.write_text("stub", encoding="utf-8")
    service, _project_msbuild = _make_msbuild_service(
        tmp_path,
        get_msbuild_for_version=lambda version: str(mapped),
    )

    path, _source, explicit_error = service._resolve_msbuild_path("11.0")

    assert path == str(mapped)
    assert explicit_error is False


def test_resolve_msbuild_path_invalid_map_path_fails_without_fallback(tmp_path):
    service, _project_msbuild = _make_msbuild_service(
        tmp_path,
        get_msbuild_for_version=lambda version: str(tmp_path / "missing.exe"),
    )

    path, source, explicit_error = service._resolve_msbuild_path("11.0")

    assert path is None
    assert explicit_error is True
    assert "msbuild_by_delphi_version" in source
