"""Regression tests for version-scoped Delphi EnvOptions handling."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.models.compile_request import (
    CompileOptions,
    ProjectCompileRequest,
    TargetPlatform,
)
from src.services.args_generator import ArgsGenerator
from src.services.compiler_service import CompilerService
from src.utils.delphi_env import (
    EnvOptionsLibraryStatus,
    build_env_options_overlay,
    inspect_env_options_library_paths,
)

_MSBUILD_NAMESPACE = "http://schemas.microsoft.com/developer/msbuild/2003"


def _write_env_options(
    appdata_dir: Path,
    version: str,
    platform_paths: dict[str, list[str]],
) -> Path:
    path = appdata_dir / "Embarcadero" / "BDS" / version / "EnvOptions.proj"
    path.parent.mkdir(parents=True)
    groups = "\n".join(
        """  <PropertyGroup Condition="'$(Platform)'=='{platform}'">
    <DelphiLibraryPath>{paths}</DelphiLibraryPath>
  </PropertyGroup>""".format(platform=platform, paths=";".join(paths))
        for platform, paths in platform_paths.items()
    )
    path.write_text(
        """<Project xmlns="{namespace}">
{groups}
</Project>
""".format(namespace=_MSBUILD_NAMESPACE, groups=groups),
        encoding="utf-8",
    )
    return path


def test_inspect_env_options_is_version_and_platform_scoped(tmp_path: Path) -> None:
    """Only the selected Delphi version and effective platform are compared."""
    win32_paths = [r"C:\Delphi22\Win32", r"C:\Shared"]
    win64_paths = [r"C:\Delphi22\Win64", r"C:\Shared64"]
    _write_env_options(
        tmp_path,
        "22.0",
        {"Win32": win32_paths, "Win64": win64_paths},
    )
    _write_env_options(
        tmp_path,
        "23.0",
        {"Win64": [r"C:\Delphi23\Win64"]},
    )

    status = inspect_env_options_library_paths(
        "22.0",
        "Win64",
        appdata_dir=tmp_path,
        registry_paths=win64_paths,
    )

    assert status.state == "current"
    assert status.env_options_path is not None
    assert "22.0" in str(status.env_options_path)
    assert tuple(win64_paths) == status.env_options_paths


@pytest.mark.parametrize(
    ("create_file", "env_paths", "expected_state"),
    [
        (False, [], "missing"),
        (True, [r"C:\OldLibrary"], "stale"),
    ],
)
def test_inspect_env_options_classifies_missing_and_stale(
    tmp_path: Path,
    create_file: bool,
    env_paths: list[str],
    expected_state: str,
) -> None:
    """A missing file and a content mismatch have distinct states."""
    if create_file:
        _write_env_options(tmp_path, "22.0", {"Win32": env_paths})

    status = inspect_env_options_library_paths(
        "22.0",
        "Win32",
        appdata_dir=tmp_path,
        registry_paths=[r"C:\CurrentLibrary"],
    )

    assert status.state == expected_state


def test_build_env_options_overlay_preserves_original_settings(tmp_path: Path) -> None:
    """The overlay imports EnvOptions and overrides only DelphiLibraryPath."""
    original = _write_env_options(
        tmp_path,
        "22.0",
        {"Win64": [r"C:\Old&Library"]},
    )

    content = build_env_options_overlay(
        original,
        [r"C:\Current&Library", r"C:\Another Library"],
        "Win64",
    )
    root = ET.fromstring(content)
    imported = root.find(f"{{{_MSBUILD_NAMESPACE}}}Import")
    library_path = root.find(
        ".//{{{}}}DelphiLibraryPath".format(_MSBUILD_NAMESPACE)
    )

    assert imported is not None
    assert imported.attrib["Project"] == str(original)
    assert library_path is not None
    assert library_path.text == r"C:\Current&Library;C:\Another Library"
    assert "DCC_UnitSearchPath" not in content


def test_explicit_compiler_version_wins_over_project_version() -> None:
    """Multi-version builds use the explicitly selected compiler version."""
    service = object.__new__(CompilerService)
    service.config_manager = SimpleNamespace(
        get_compiler=lambda name: SimpleNamespace(registry_version="22.0")
    )
    request = ProjectCompileRequest(
        project_path="Project.dproj",
        options=CompileOptions(compiler_version="Delphi 11 Win32"),
    )
    parser = SimpleNamespace(get_project_version=lambda: "23.0")

    version = service._resolve_msbuild_registry_version(request, parser, True)

    assert version == "22.0"


@pytest.mark.parametrize(
    "argument",
    [
        "/p:Platform=Win64",
        "-p:Platform=Win64",
        "/property:Platform=Win64",
        "-property:Platform=Win64",
    ],
)
def test_parse_msbuild_property_supports_all_prefixes(argument: str) -> None:
    """Platform resolution recognizes every documented MSBuild property prefix."""
    assert CompilerService._parse_msbuild_property(argument) == (
        "platform",
        "Win64",
    )


def test_explicit_legacy_compiler_version_comes_from_its_path() -> None:
    """Legacy compiler configs do not borrow the newer project version."""
    service = object.__new__(CompilerService)
    service.config_manager = SimpleNamespace(
        get_compiler=lambda name: SimpleNamespace(
            registry_version=None,
            path=r"C:\Program Files (x86)\Embarcadero\Studio\22.0\bin\dcc32.exe",
        )
    )
    request = ProjectCompileRequest(
        project_path="Project.dproj",
        options=CompileOptions(compiler_version="Legacy Delphi 11"),
    )
    parser = SimpleNamespace(get_project_version=lambda: "23.0")

    version = service._resolve_msbuild_registry_version(request, parser, True)

    assert version == "22.0"


def test_unresolved_explicit_compiler_does_not_use_project_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unidentifiable explicit compiler never falls back across versions."""
    service = object.__new__(CompilerService)
    service.config_manager = SimpleNamespace(
        get_compiler=lambda name: SimpleNamespace(
            registry_version=None,
            path=r"C:\Custom\dcc32.exe",
        )
    )
    request = ProjectCompileRequest(
        project_path="Project.dproj",
        options=CompileOptions(compiler_version="Custom Delphi"),
    )
    parser = SimpleNamespace(get_project_version=lambda: "23.0")
    monkeypatch.setattr(
        "src.services.compiler_service.detect_registry_version_from_compiler",
        lambda path: None,
    )

    version = service._resolve_msbuild_registry_version(request, parser, True)

    assert version is None


@pytest.mark.asyncio
async def test_msbuild_stale_env_options_uses_short_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale global path uses an overlay without replacing project search paths."""
    captured: dict[str, Any] = {}
    original_env_options = _write_env_options(
        tmp_path,
        "22.0",
        {"Win64": [r"C:\OldLibrary"]},
    )
    registry_paths = tuple(
        r"C:\ThirdParty\Library{:04d}\Source".format(index)
        for index in range(400)
    )

    def fake_inspect(version: str, platform: str) -> EnvOptionsLibraryStatus:
        captured["inspect"] = (version, platform)
        return EnvOptionsLibraryStatus(
            "stale",
            original_env_options,
            registry_paths,
            (r"C:\OldLibrary",),
        )

    class FakeProcessManager:
        async def execute(
            self,
            executable: str,
            args: list[str],
            timeout: int,
        ) -> tuple[int, str, str]:
            batch_path = Path(args[-1])
            batch = batch_path.read_text(encoding="ascii", errors="ignore")
            match = re.search(
                r'(?:"/p:EnvOptions=([^"]+)"|/p:EnvOptions=(\S+))',
                batch,
            )
            assert match is not None
            overlay_path = Path(match.group(1) or match.group(2))
            captured["batch_path"] = batch_path
            captured["batch"] = batch
            captured["overlay_path"] = overlay_path
            captured["overlay"] = overlay_path.read_text(encoding="utf-8")
            return 1, "", "compile failed"

    dproj_path = tmp_path / "MultiVersion.dproj"
    dproj_path.write_text(
        """<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup><ProjectVersion>23.0</ProjectVersion></PropertyGroup>
</Project>
""",
        encoding="utf-8",
    )

    service = object.__new__(CompilerService)
    service.msbuild_path = "MSBuild.exe"
    service.config_manager = SimpleNamespace(
        get_compiler=lambda name: SimpleNamespace(registry_version="22.0")
    )
    service.validator = SimpleNamespace(validate_project_path=lambda path: (True, ""))
    service.args_generator = ArgsGenerator()
    service.process_manager = FakeProcessManager()
    service.output_parser = SimpleNamespace(
        parse_errors=lambda output: [],
        parse_warnings=lambda output: [],
        extract_error_summary=lambda output: "compile failed",
    )
    service._check_process_running = lambda name: None
    service._get_delphi_root_from_registry = lambda version=None: r"C:\Delphi22"
    service._get_rsvars_path = lambda version=None: (
        captured.setdefault("rsvars_version", version) or r"C:\Delphi22\bin\rsvars.bat"
    )
    service._save_history = lambda *args: None
    monkeypatch.setattr(
        "src.services.compiler_service.inspect_env_options_library_paths",
        fake_inspect,
    )

    request = ProjectCompileRequest(
        project_path=str(dproj_path),
        options=CompileOptions(
            target_platform=TargetPlatform.WIN32,
            compiler_version="Delphi 11 Win32",
            extra_args=["/p:Platform=Win64"],
        ),
    )

    result = await service.compile_project_with_msbuild(request)

    assert result.error_code == "COMPILATION_FAILED"
    assert captured["inspect"] == ("22.0", "Win64")
    assert captured["rsvars_version"] == "22.0"
    assert len(captured["batch"]) < 8191
    assert registry_paths[-1] not in captured["batch"]
    assert registry_paths[-1] in captured["overlay"]
    assert "DelphiLibraryPath" in captured["overlay"]
    assert "DCC_UnitSearchPath" not in captured["batch"]
    assert request.options.unit_search_paths == []
    assert not captured["batch_path"].exists()
    assert not captured["overlay_path"].exists()
