"""Regression tests for delphi_project compile extra arguments."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.models.compile_request import CompileOptions, ProjectCompileRequest
from src.services.args_generator import ArgsGenerator
from src.services.compiler_service import CompilerService
from src.tools import project


@pytest.mark.asyncio
async def test_compile_action_forwards_extra_args(monkeypatch):
    captured = {}

    async def fake_compile_project(**kwargs):
        captured.update(kwargs)
        return {"status": "success"}

    monkeypatch.setattr(project, "_compile_project", fake_compile_project)

    result = await project._handle_compile({
        "project_path": "Project.dproj",
        "extra_args": ["/p:DCC_DebugInfoInTds=true"],
    })

    assert result == {"status": "success"}
    assert captured["extra_args"] == ["/p:DCC_DebugInfoInTds=true"]


@pytest.mark.asyncio
async def test_compile_file_action_forwards_extra_args(monkeypatch):
    captured = {}

    async def fake_compile_file(**kwargs):
        captured.update(kwargs)
        return {"status": "success"}

    monkeypatch.setattr(project, "_compile_file", fake_compile_file)

    result = await project._handle_compile_file({
        "project_path": "Unit1.pas",
        "extra_args": ["-VT"],
    })

    assert result == {"status": "success"}
    assert captured["extra_args"] == ["-VT"]


@pytest.mark.asyncio
async def test_dry_run_action_forwards_extra_args(monkeypatch):
    captured = {}

    async def fake_get_compiler_args(**kwargs):
        captured.update(kwargs)
        return {"status": "success"}

    monkeypatch.setattr(project, "_get_compiler_args", fake_get_compiler_args)

    result = await project._handle_dry_run({
        "project_path": "Project.dpr",
        "extra_args": ["-VR"],
    })

    assert result == {"status": "success"}
    assert captured["extra_args"] == ["-VR"]


@pytest.mark.asyncio
async def test_msbuild_command_includes_extra_args(tmp_path):
    captured = {}

    class FakeProcessManager:
        async def execute(self, executable, args, timeout):
            batch_path = Path(args[-1])
            captured["batch"] = batch_path.read_bytes().decode("ascii", errors="ignore")
            return 1, "", "compile failed"

    dproj_path = tmp_path / "Symbols.dproj"
    dproj_path.write_text(
        '<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003" />',
        encoding="utf-8",
    )

    service = object.__new__(CompilerService)
    service.msbuild_path = "MSBuild.exe"
    service.validator = SimpleNamespace(validate_project_path=lambda path: (True, ""))
    service.args_generator = ArgsGenerator()
    service.process_manager = FakeProcessManager()
    service.output_parser = SimpleNamespace(
        parse_errors=lambda output: [],
        parse_warnings=lambda output: [],
        extract_error_summary=lambda output: "compile failed",
    )
    service._check_process_running = lambda name: None
    service._get_delphi_root_from_registry = lambda: None
    service._get_rsvars_path = lambda: r"C:\fake\rsvars.bat"
    service._save_history = lambda *args: None

    request = ProjectCompileRequest(
        project_path=str(dproj_path),
        options=CompileOptions(extra_args=[
            "/p:DCC_DebugInfoInTds=true",
            "/p:DCC_RemoteDebug=true",
        ]),
    )

    result = await service.compile_project_with_msbuild(request)

    assert result.error_code == "COMPILATION_FAILED"
    assert "/p:DCC_DebugInfoInTds=true" in captured["batch"]
    assert "/p:DCC_RemoteDebug=true" in captured["batch"]
