from pathlib import Path

import pytest

from src.services.delphi_edit_guard import (
    consume_authorized_write,
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
