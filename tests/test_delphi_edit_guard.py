from pathlib import Path

import pytest

from src.services.delphi_edit_guard import (
    consume_authorized_write,
    external_edit_block_message,
    record_authorized_write,
    record_external_edit,
    reset_guard_state,
    snapshot_status,
)


@pytest.fixture(autouse=True)
def _enable_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAOFY_EDIT_GUARD", "warn")
    reset_guard_state()


def test_authorized_daofy_write_is_consumed_without_external_event(tmp_path: Path) -> None:
    reset_guard_state()
    unit_path = tmp_path / "Unit1.pas"
    unit_path.write_text("unit Unit1;\n", encoding="utf-8")

    record_authorized_write(
        unit_path,
        tool="delphi_file",
        operation="write",
    )

    assert consume_authorized_write(unit_path) is not None
    assert snapshot_status()["recent_unauthorized_count"] == 0


def test_external_delphi_edit_is_recorded(tmp_path: Path) -> None:
    reset_guard_state()
    unit_path = tmp_path / "Unit1.pas"
    unit_path.write_text("unit Unit1;\n", encoding="utf-8")

    event = record_external_edit(unit_path, event_type="modified")
    status = snapshot_status()

    assert event is not None
    assert status["enabled"] is True
    assert status["recent_unauthorized_count"] == 1
    assert status["recent_unauthorized_edits"][0]["path"].endswith("Unit1.pas")


def test_non_delphi_paths_are_ignored(tmp_path: Path) -> None:
    reset_guard_state()
    py_path = tmp_path / "tool.py"
    py_path.write_text("print('ok')\n", encoding="utf-8")

    assert record_external_edit(py_path, event_type="modified") is None
    assert snapshot_status()["recent_unauthorized_count"] == 0


def test_strict_mode_blocks_external_edit_in_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAOFY_EDIT_GUARD", "strict")
    reset_guard_state()
    unit_path = tmp_path / "Unit1.pas"
    unit_path.write_text("unit Unit1;\n", encoding="utf-8")

    record_external_edit(unit_path, event_type="modified")

    message = external_edit_block_message(tmp_path)
    assert message is not None
    assert "Delphi 编辑保护已阻止本次操作" in message
    assert "检测到的文件" in message
    assert str(unit_path) in message


def test_warn_mode_does_not_block_external_edit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAOFY_EDIT_GUARD", "warn")
    reset_guard_state()
    unit_path = tmp_path / "Unit1.pas"
    unit_path.write_text("unit Unit1;\n", encoding="utf-8")

    record_external_edit(unit_path, event_type="modified")

    assert external_edit_block_message(tmp_path) is None
    assert snapshot_status()["recent_unauthorized_count"] == 1


def test_strict_mode_scope_filter_ignores_other_projects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAOFY_EDIT_GUARD", "strict")
    reset_guard_state()
    project_a = tmp_path / "A"
    project_b = tmp_path / "B"
    project_a.mkdir()
    project_b.mkdir()
    changed = project_a / "Unit1.pas"
    changed.write_text("unit Unit1;\n", encoding="utf-8")

    record_external_edit(changed, event_type="modified")

    assert external_edit_block_message(project_b) is None
    assert external_edit_block_message(project_a) is not None


@pytest.mark.asyncio
async def test_compile_project_strict_mode_blocks_external_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.tools.compile_project as compile_project_mod

    monkeypatch.setenv("DAOFY_EDIT_GUARD", "strict")
    reset_guard_state()
    dproj_path = tmp_path / "App.dproj"
    unit_path = tmp_path / "Unit1.pas"
    dproj_path.write_text("<Project />", encoding="utf-8")
    unit_path.write_text("unit Unit1;\n", encoding="utf-8")
    record_external_edit(unit_path, event_type="modified")
    monkeypatch.setattr(compile_project_mod, "_compiler_service", object())

    result = await compile_project_mod.compile_project(str(dproj_path))

    assert result.isError
    assert "Delphi 编辑保护已阻止本次操作" in result.content[0].text
    assert str(unit_path) in result.content[0].text


@pytest.mark.asyncio
async def test_compile_file_strict_mode_blocks_external_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.tools.compile_file as compile_file_mod

    monkeypatch.setenv("DAOFY_EDIT_GUARD", "strict")
    reset_guard_state()
    unit_path = tmp_path / "Unit1.pas"
    unit_path.write_text("unit Unit1;\n", encoding="utf-8")
    record_external_edit(unit_path, event_type="modified")
    monkeypatch.setattr(compile_file_mod, "_compiler_service", object())

    result = await compile_file_mod.compile_file(str(unit_path))

    assert result.isError
    assert "Delphi 编辑保护已阻止本次操作" in result.content[0].text
    assert str(unit_path) in result.content[0].text
