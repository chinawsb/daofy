#!/usr/bin/env python3
"""Tests for exception_filter feature."""
import json

import pytest

from src.services import automation_service as service

@pytest.fixture()
def fake_pipe():
    """返回一个可编程的 mock pipe 函数。"""
    sent: list[str] = []
    responses: dict[tuple, str] = {}

    def _pipe(cmd_str: str, timeout_ms=None) -> str:
        sent.append(cmd_str)
        parsed = json.loads(cmd_str)
        cmd = parsed.get("cmd", "")
        key = (cmd, parsed.get("target", ""))
        if key in responses:
            return responses[key]
        return '{"status":"ok","data":"{}"}'

    _pipe.sent = sent  # type: ignore[attr-defined]
    _pipe.responses = responses  # type: ignore[attr-defined]
    return _pipe


def _dialog_state(title: str = "Error Dialog") -> dict:
    return {
        "forms": [{"caption": title, "class_name": "TfrmError", "is_dialog": True}],
        "focus": {"active_window": "test.exe"},
    }


def _pipe_for_state(state: dict | None):
    if state is None:
        return lambda cmd: None
    encoded = json.dumps({"status": "ok", "data": json.dumps(state)})
    return lambda cmd: encoded


# ── _parse_exception_filter ────────────────────────────────────────


class TestParseExceptionFilter:
    def test_none_returns_default(self):
        config = service._parse_exception_filter(None)
        assert config == service.DEFAULT_EXCEPTION_FILTER

    def test_custom_config(self):
        config = service._parse_exception_filter({
            "enabled": True,
            "poll_interval_ms": 1000,
            "max_exceptions": 5,
            "on_exception": {"dialog": "close", "focus_lost": "refocus"},
        })
        assert config["enabled"] is True
        assert config["poll_interval_ms"] == 1000
        assert config["max_exceptions"] == 5
        assert config["on_exception"]["dialog"] == "close"
        assert config["on_exception"]["focus_lost"] == "refocus"

    def test_invalid_entries_filtered(self):
        config = service._parse_exception_filter({
            "on_exception": {"invalid_type": "close", "dialog": "invalid_action"},
        })
        assert "invalid_type" not in config["on_exception"]
        assert "dialog" not in config["on_exception"]


# ── ExceptionFilter 检测 ───────────────────────────────────────────


class TestExceptionFilterDetect:
    def test_detect_dialog(self):
        ef = service.ExceptionFilter(
            {"enabled": True}, "test.exe", _pipe_for_state(_dialog_state("Error Dialog"))
        )
        exc = ef._detect_exception()
        assert exc is not None
        assert exc[0] == "dialog"
        assert "Error Dialog" in exc[1]["title"]

    def test_detect_focus_lost(self):
        state = {"forms": [], "focus": {"active_window": "OtherApp.exe"}}
        ef = service.ExceptionFilter(
            {"enabled": True}, "test.exe", _pipe_for_state(state)
        )
        exc = ef._detect_exception()
        assert exc is not None
        assert exc[0] == "focus_lost"

    def test_ignore_pattern(self):
        state = _dialog_state("About Daofy")
        ef = service.ExceptionFilter(
            {"enabled": True, "ignore_patterns": [{"title_pattern": "About|关于"}]},
            "test.exe", _pipe_for_state(state),
        )
        exc = ef._detect_exception()
        assert exc is None

    def test_empty_pipe_returns_none(self):
        ef = service.ExceptionFilter({"enabled": True}, "test.exe", lambda c: None)
        exc = ef._detect_exception()
        assert exc is None

    def test_no_forms_no_focus_returns_none(self):
        state = {"forms": [], "focus": {"active_window": "test.exe"}}
        ef = service.ExceptionFilter(
            {"enabled": True}, "test.exe", _pipe_for_state(state)
        )
        exc = ef._detect_exception()
        assert exc is None


# ── ExceptionFilter 处理动作 ────────────────────────────────────────


class TestExceptionFilterHandle:
    def test_close_sends_escape(self, fake_pipe):
        ef = service.ExceptionFilter({"enabled": True}, "test.exe", fake_pipe)
        ef.exception_count = 0
        action = ef._handle_exception("dialog", {"title": "Error"})
        assert action == "close"
        req = json.loads(fake_pipe.sent[-1])
        assert req["cmd"] == "key"
        assert req["key"] == "{ESCAPE}"

    def test_refocus_sends_goto(self, fake_pipe):
        ef = service.ExceptionFilter({"enabled": True}, "my_app.exe", fake_pipe)
        ef.exception_count = 0
        action = ef._handle_exception("focus_lost", {"active_window": "Other.exe"})
        assert action == "refocus"
        req = json.loads(fake_pipe.sent[-1])
        assert req["cmd"] == "goto"
        assert req["target"] == "my_app.exe"

    def test_log_does_not_send(self, fake_pipe):
        ef = service.ExceptionFilter(
            {"enabled": True, "on_exception": {"dialog": "log"}},
            "test.exe", fake_pipe,
        )
        ef.exception_count = 0
        before = len(fake_pipe.sent)
        action = ef._handle_exception("dialog", {"title": "Info"})
        assert action == "log"
        assert len(fake_pipe.sent) == before

    def test_ignore_does_not_send(self, fake_pipe):
        ef = service.ExceptionFilter(
            {"enabled": True, "on_exception": {"dialog": "ignore"}},
            "test.exe", fake_pipe,
        )
        ef.exception_count = 0
        before = len(fake_pipe.sent)
        action = ef._handle_exception("dialog", {"title": "Info"})
        assert action == "ignore"
        assert len(fake_pipe.sent) == before


# ── check_and_handle 流程 ──────────────────────────────────────────


class TestCheckAndHandle:
    def test_disabled_returns_no_abort(self):
        ef = service.ExceptionFilter({"enabled": False}, "test.exe", lambda c: None)
        should_abort, action = ef.check_and_handle()
        assert should_abort is False
        assert action == ""

    def test_max_exceptions_aborts(self):
        state = _dialog_state()
        ef = service.ExceptionFilter(
            {"enabled": True, "max_exceptions": 2}, "test.exe", _pipe_for_state(state),
        )
        ef.exception_count = 2
        should_abort, action = ef.check_and_handle()
        assert should_abort is True
        assert action == "max_exceptions_reached"

    def test_exception_increments_count(self):
        state = _dialog_state()
        ef = service.ExceptionFilter(
            {"enabled": True, "on_exception": {"dialog": "close"}},
            "test.exe", _pipe_for_state(state),
        )
        assert ef.exception_count == 0
        ef.check_and_handle()
        assert ef.exception_count == 1
        ef.check_and_handle()
        assert ef.exception_count == 2


# ── get_stats ──────────────────────────────────────────────────────


class TestGetStats:
    def test_stats_shape(self):
        ef = service.ExceptionFilter({"enabled": True, "max_exceptions": 5}, "test.exe", lambda c: None)
        stats = ef.get_stats()
        assert stats["enabled"] is True
        assert stats["exception_count"] == 0
        assert stats["max_exceptions"] == 5
        assert isinstance(stats["exceptions_handled"], list)
