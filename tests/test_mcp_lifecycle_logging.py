import logging
from typing import Any
from unittest import mock

import anyio
import pytest

from src.mcp_compat import _StdinEofLoggingReceiveStream


class _EofStream:
    async def receive(self) -> Any:
        raise anyio.EndOfStream

    async def __aenter__(self) -> "_EofStream":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


@pytest.mark.anyio
async def test_stdin_eof_is_logged_once(caplog):
    caplog.set_level(logging.INFO, logger="src.mcp_compat")
    stream = _StdinEofLoggingReceiveStream(_EofStream())

    with pytest.raises(StopAsyncIteration):
        await stream.__anext__()
    with pytest.raises(StopAsyncIteration):
        await stream.__anext__()

    assert "event=stdin_eof" in caplog.text
    assert caplog.text.count("event=stdin_eof") == 1


def _patch_cleanup_steps(monkeypatch: Any, *, failing_step: str | None = None) -> list[str]:
    import src.services.experience_service as experience_service
    import src.tools.dfm_utils as dfm_utils
    import src.tools.knowledge_base as knowledge_base
    import src.tools.project_knowledge_base as project_knowledge_base

    modules_and_names = (
        (knowledge_base, "_cleanup_pkb_cache", "pkb_cache"),
        (dfm_utils, "_cleanup_dfm_temp_dirs", "dfm_temp_dirs"),
        (experience_service, "cleanup", "experience_service"),
        (project_knowledge_base, "_cleanup_project_kb_cache", "project_kb_cache"),
    )
    calls = []
    for module, name, step_name in modules_and_names:
        def cleanup_step(step_name=step_name):
            calls.append(step_name)
            if step_name == failing_step:
                raise RuntimeError(f"{step_name} failed")

        monkeypatch.setattr(module, name, cleanup_step)
    return calls


def test_cleanup_logs_successful_steps(monkeypatch: Any) -> None:
    import src.server as server_module

    calls = _patch_cleanup_steps(monkeypatch)
    monkeypatch.setattr(server_module, "_project_file_watcher", None)
    with mock.patch.object(server_module.logger, "info") as info:
        server_module._cleanup_resources("server_run_returned")

    assert calls == ["pkb_cache", "dfm_temp_dirs", "experience_service", "project_kb_cache"]
    messages = [call.args[0] for call in info.call_args_list]
    assert messages[0] == "mcp_cleanup event=started reason=%s"
    assert any(
        call.args[:2] == ("mcp_cleanup event=finished reason=%s failures=%d elapsed_ms=%d", "server_run_returned")
        and call.args[2] == 0
        for call in info.call_args_list
    )
    assert any(
        call.args[:2] == ("mcp_cleanup event=step_skipped step=project_file_watcher reason=not_started",)
        for call in info.call_args_list
    )


def test_cleanup_logs_failure_and_continues(monkeypatch: Any) -> None:
    import src.server as server_module

    calls = _patch_cleanup_steps(monkeypatch, failing_step="dfm_temp_dirs")
    monkeypatch.setattr(server_module, "_project_file_watcher", None)
    with mock.patch.object(server_module.logger, "info") as info, mock.patch.object(
        server_module.logger, "warning"
    ) as warning:
        server_module._cleanup_resources("exception")

    assert calls == ["pkb_cache", "dfm_temp_dirs", "experience_service", "project_kb_cache"]
    assert any(call.args[:2] == ("mcp_cleanup event=step_failed step=%s", "dfm_temp_dirs") for call in warning.call_args_list)
    assert any(
        call.args[:2] == ("mcp_cleanup event=finished reason=%s failures=%d elapsed_ms=%d", "exception")
        and call.args[2] == 1
        for call in info.call_args_list
    )
