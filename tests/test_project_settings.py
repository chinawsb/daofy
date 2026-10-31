#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目级 Delphi/MSBuild 配置测试。

覆盖多版本机器上“不同工程使用不同 Delphi/MSBuild”的核心行为：
- 就近查找 ``.daofy/project.json`` / ``daofy.project.json``
- 项目配置无效时直接失败（不回退到其它版本）
- ``delphi_version`` 支持产品名（XE4）与版本号（11.0）
- ``msbuild_by_delphi_version`` 支持 ``.dproj ProjectVersion`` 键
- 显式 MSBuild 配置无效时不回退到直接编译
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.models.compile_request import CompileOptions, ProjectCompileRequest, TargetPlatform
from src.models.compile_result import CompileResult, CompileStatus
from src.services.compiler_service import CompilerService
from src.services.config_manager import ConfigManager
from src.services.project_settings import (
    ProjectSettings,
    find_project_config,
    load_project_settings,
)
from src.utils.delphi_versions import normalize_version_key


def _write_compilers(tmp_path: Path, **overrides) -> ConfigManager:
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
    config_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ConfigManager(str(config_path), str(tmp_path / "history.json"))


def _write_project_config(directory: Path, payload: dict, name: str = ".daofy/project.json") -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_normalize_version_key_accepts_product_names():
    assert normalize_version_key("11") == "11.0"
    assert normalize_version_key("XE4") == "11.0"
    assert normalize_version_key("Delphi XE4") == "11.0"
    assert normalize_version_key("Delphi 12 Athens") == "23.0"
    assert normalize_version_key("XE4 Win32") == "11.0"
    # .dproj ProjectVersion 与注册表版本不同的版本
    assert normalize_version_key("14.6") == "14.0"
    assert normalize_version_key("18.2") == "18.0"
    assert normalize_version_key("not-a-version") is None


def test_find_project_config_prefers_nearest_file(tmp_path):
    root = tmp_path / "Workspace"
    child = root / "App" / "Source"
    child.mkdir(parents=True)
    _write_project_config(root, {"delphi_version": "11.0"})
    nearest = _write_project_config(
        root / "App",
        {"delphi_version": "16.0"},
        name="daofy.project.json",
    )

    assert find_project_config(child) == nearest


def test_find_project_config_accepts_directory_with_dot(tmp_path):
    project_dir = tmp_path / "MyApp.v2"
    project_dir.mkdir()
    config = _write_project_config(project_dir, {"delphi_version": "11.0"})

    assert find_project_config(project_dir) == config
    assert find_project_config(project_dir / "Main.dproj") == config


def test_load_project_settings_normalizes_product_name(tmp_path):
    project_dir = tmp_path / "App"
    project_dir.mkdir()
    _write_project_config(project_dir, {"delphi_version": "XE4"})

    settings = load_project_settings(project_dir)

    assert settings is not None
    assert settings.delphi_version == "11.0"


def test_load_project_settings_invalid_json_sets_error(tmp_path):
    project_dir = tmp_path / "App"
    project_dir.mkdir()
    config_path = project_dir / "daofy.project.json"
    config_path.write_text("{ not valid json", encoding="utf-8")

    settings = load_project_settings(project_dir)

    assert settings is not None
    assert settings.error
    assert "JSON" in settings.error


def test_load_project_settings_invalid_version_sets_error(tmp_path):
    project_dir = tmp_path / "App"
    project_dir.mkdir()
    _write_project_config(project_dir, {"delphi_version": "not-a-version"})

    settings = load_project_settings(project_dir)

    assert settings is not None
    assert settings.error
    assert settings.delphi_version is None


def test_resolve_project_compiler_rejects_invalid_project_config(tmp_path):
    service = object.__new__(CompilerService)
    service.config_manager = SimpleNamespace()
    settings = ProjectSettings(
        source=str(tmp_path / ".daofy" / "project.json"),
        error="bad delphi_version",
    )

    compiler, path, error = service._resolve_project_compiler(
        str(tmp_path / "Project.dproj"),
        None,
        TargetPlatform.WIN32,
        settings,
    )

    assert compiler is None
    assert path is None
    assert error == "bad delphi_version"


def test_load_project_settings_resolves_relative_msbuild_path(tmp_path):
    project_dir = tmp_path / "App"
    project_dir.mkdir()
    config_path = _write_project_config(
        project_dir,
        {"msbuild_path": "tools/MSBuild.exe"},
    )

    settings = load_project_settings(project_dir)

    assert settings is not None
    assert settings.msbuild_path == str(config_path.parent / "tools" / "MSBuild.exe")


def test_resolve_msbuild_path_prefers_project_over_map(tmp_path):
    project_msbuild = tmp_path / "project-msbuild.exe"
    project_msbuild.write_text("stub", encoding="utf-8")
    mapped_msbuild = tmp_path / "mapped-msbuild.exe"
    mapped_msbuild.write_text("stub", encoding="utf-8")

    service = object.__new__(CompilerService)
    service.msbuild_path = None
    service._msbuild_auto_cache = {}
    service.config_manager = SimpleNamespace(
        get_msbuild_for_version=lambda version: str(mapped_msbuild),
    )
    settings = ProjectSettings(
        msbuild_path=str(project_msbuild),
        source=str(tmp_path / ".daofy" / "project.json"),
    )

    path, _source, explicit_error = service._resolve_msbuild_path("11.0", settings)

    assert path == str(project_msbuild)
    assert explicit_error is False


def test_resolve_msbuild_path_invalid_project_path_fails_without_fallback(
    tmp_path,
):
    service = object.__new__(CompilerService)
    service.msbuild_path = None
    service._msbuild_auto_cache = {}
    service.config_manager = SimpleNamespace()
    settings = ProjectSettings(
        msbuild_path=str(tmp_path / "missing.exe"),
        source=str(tmp_path / ".daofy" / "project.json"),
    )

    path, source, explicit_error = service._resolve_msbuild_path("11.0", settings)

    assert path is None
    assert explicit_error is True
    assert "项目配置" in source


def test_resolve_msbuild_path_redetects_for_project_version(tmp_path):
    init_msbuild = tmp_path / "init-msbuild.exe"
    init_msbuild.write_text("stub", encoding="utf-8")
    version_msbuild = tmp_path / "version-msbuild.exe"
    version_msbuild.write_text("stub", encoding="utf-8")
    calls = []

    service = object.__new__(CompilerService)
    service.msbuild_path = str(init_msbuild)
    service._msbuild_auto_cache = {}
    service.config_manager = SimpleNamespace(
        get_msbuild_for_version=lambda version: None,
    )

    def fake_auto(version=None):
        calls.append(version)
        return str(version_msbuild)

    service._auto_find_msbuild = fake_auto

    path, _source, _explicit_error = service._resolve_msbuild_path("11.0")

    assert path == str(version_msbuild)
    assert calls == ["11.0"]


def test_resolve_msbuild_registry_version_uses_project_delphi_version(tmp_path):
    manager = _write_compilers(tmp_path)
    service = object.__new__(CompilerService)
    service.config_manager = manager
    request = ProjectCompileRequest(
        project_path=str(tmp_path / "Project.dproj"),
        options=CompileOptions(),
    )
    parser = SimpleNamespace(get_project_version=lambda: "14.6")
    settings = ProjectSettings(
        delphi_version="11.0",
        source=str(tmp_path / ".daofy" / "project.json"),
    )

    version = service._resolve_msbuild_registry_version(
        request,
        parser,
        True,
        settings,
    )

    assert version == "11.0"


def test_resolve_msbuild_registry_version_accepts_version_as_compiler(tmp_path):
    manager = _write_compilers(tmp_path)
    service = object.__new__(CompilerService)
    service.config_manager = manager
    request = ProjectCompileRequest(
        project_path=str(tmp_path / "Project.dproj"),
        options=CompileOptions(),
    )
    parser = SimpleNamespace(get_project_version=lambda: "16.0")
    settings = ProjectSettings(
        compiler_version="11.0",
        source=str(tmp_path / ".daofy" / "project.json"),
    )

    version = service._resolve_msbuild_registry_version(
        request,
        parser,
        True,
        settings,
    )

    assert version == "11.0"


def test_resolve_msbuild_registry_version_invalid_compiler_without_fallback(tmp_path):
    """项目 compiler_version 无效且无 delphi_version 时返回 None（调用方应失败）。"""
    manager = _write_compilers(tmp_path)
    service = object.__new__(CompilerService)
    service.config_manager = manager
    request = ProjectCompileRequest(
        project_path=str(tmp_path / "Project.dproj"),
        options=CompileOptions(),
    )
    parser = SimpleNamespace(get_project_version=lambda: "16.0")
    settings = ProjectSettings(
        compiler_version="MissingCompiler",
        source=str(tmp_path / ".daofy" / "project.json"),
    )

    version = service._resolve_msbuild_registry_version(
        request,
        parser,
        True,
        settings,
    )

    assert version is None


def test_resolve_msbuild_registry_version_falls_back_to_delphi_version(tmp_path):
    manager = _write_compilers(tmp_path)
    service = object.__new__(CompilerService)
    service.config_manager = manager
    request = ProjectCompileRequest(
        project_path=str(tmp_path / "Project.dproj"),
        options=CompileOptions(),
    )
    parser = SimpleNamespace(get_project_version=lambda: "16.0")
    settings = ProjectSettings(
        compiler_version="MissingCompiler",
        delphi_version="11.0",
        source=str(tmp_path / ".daofy" / "project.json"),
    )

    version = service._resolve_msbuild_registry_version(
        request,
        parser,
        True,
        settings,
    )

    assert version == "11.0"


def test_resolve_project_compiler_falls_back_to_delphi_version(tmp_path):
    """项目 compiler_version 写错时，delphi_version 仍应生效（不回退到默认版本）。"""
    xe4 = SimpleNamespace(
        name="Delphi XE4 Win32",
        path=r"C:\Delphi\11.0\bin\dcc32.exe",
        registry_version="11.0",
    )
    service = object.__new__(CompilerService)
    service.config_manager = SimpleNamespace(
        get_compiler=lambda name: None,
        get_compiler_by_registry_version=lambda version, platform=None: xe4,
    )
    service._find_compiler_from_registry = lambda platform, version=None: None
    settings = ProjectSettings(
        compiler_version="MissingCompiler",
        delphi_version="11.0",
        source=str(tmp_path / ".daofy" / "project.json"),
    )

    compiler, path, error = service._resolve_project_compiler(
        str(tmp_path / "Project.dproj"),
        None,
        TargetPlatform.WIN32,
        settings,
    )

    assert error is None
    assert path is None
    assert compiler is xe4


def test_compiler_version_name_fallback_does_not_confuse_xe_and_xe8(tmp_path):
    manager = _write_compilers(
        tmp_path,
        compilers=[
            {
                "name": "XE8 dcc32",
                "path": r"C:\Delphi\16.0\bin\dcc32.exe",
                "version": "Delphi XE8",
            }
        ],
        default_compiler="XE8 dcc32",
    )

    # "Delphi XE"(8.0) 不能误命中 "Delphi XE8"(16.0)
    assert manager.get_compiler_by_registry_version("8.0") is None
    assert manager.get_compiler_by_registry_version("16.0") is not None


def test_effective_delphi_root_accepts_explicit_version(tmp_path):
    manager = _write_compilers(tmp_path)
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


def _make_dispatcher_service(tmp_path: Path, msbuild_result: CompileResult):
    dproj_path = tmp_path / "Project.dproj"
    dproj_path.write_text("<Project />", encoding="utf-8")
    service = object.__new__(CompilerService)
    service.msbuild_path = None
    service.config_manager = SimpleNamespace()
    calls = {"msbuild": 0, "direct": 0}

    async def fake_msbuild(request):
        calls["msbuild"] += 1
        return msbuild_result

    async def fake_direct(request):
        calls["direct"] += 1
        return CompileResult(status=CompileStatus.SUCCESS)

    service.compile_project_with_msbuild = fake_msbuild
    service.compile_dpr_direct = fake_direct
    request = ProjectCompileRequest(
        project_path=str(tmp_path / "Project.dpr"),
        options=CompileOptions(),
    )
    return service, request, calls


@pytest.mark.asyncio
async def test_dpr_falls_back_to_direct_when_msbuild_missing(tmp_path):
    service, request, calls = _make_dispatcher_service(
        tmp_path,
        CompileResult(
            status=CompileStatus.FAILED,
            error_code="MSBUILD_NOT_FOUND",
            error_message="not found",
        ),
    )

    result = await service.compile_project(request)

    assert result.status == CompileStatus.SUCCESS
    assert calls == {"msbuild": 1, "direct": 1}


@pytest.mark.asyncio
async def test_dpr_does_not_fall_back_when_msbuild_config_invalid(tmp_path):
    service, request, calls = _make_dispatcher_service(
        tmp_path,
        CompileResult(
            status=CompileStatus.FAILED,
            error_code="MSBUILD_CONFIG_INVALID",
            error_message="bad path",
        ),
    )

    result = await service.compile_project(request)

    assert result.error_code == "MSBUILD_CONFIG_INVALID"
    assert calls == {"msbuild": 1, "direct": 0}
