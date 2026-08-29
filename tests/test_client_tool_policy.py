"""Regression coverage for DaofyCoding-native MCP capability filtering."""

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from src.client_tool_policy import (
    ensure_tool_visible,
    filter_tools,
    normalize_client_name,
)


@dataclass(frozen=True)
class _Tool:
    name: str


ALL_TOOLS = [
    _Tool("delphi_file"),
    _Tool("structured_content"),
    _Tool("automate_delphi"),
    _Tool("delphi_rtti"),
    _Tool("delphi_project"),
]


def test_regular_clients_keep_the_full_tool_directory() -> None:
    assert filter_tools(ALL_TOOLS, "Claude Desktop") == ALL_TOOLS
    assert filter_tools(ALL_TOOLS, None) == ALL_TOOLS


@pytest.mark.parametrize(
    "client_name",
    [
        "DaofyCoding",
        "daofy-coding",
        "Daofy Coding",
        "daofy_coding",
        "DAOFY-CODING",
        "daofy-agent",
    ],
)
def test_daofycoding_hides_native_tool_duplicates(client_name: str) -> None:
    visible = filter_tools(ALL_TOOLS, client_name)

    assert [tool.name for tool in visible] == ["delphi_file", "delphi_project"]


@pytest.mark.parametrize(
    "client_name,normalized",
    [
        ("DaofyCoding", "daofycoding"),
        (" Daofy Coding ", "daofycoding"),
        ("daofy_coding", "daofycoding"),
        ("DAOFY-CODING", "daofycoding"),
        ("daofy-agent", "daofyagent"),
        (None, ""),
    ],
)
def test_client_name_normalization_is_separator_insensitive(
    client_name: str | None, normalized: str
) -> None:
    assert normalize_client_name(client_name) == normalized


def test_client_name_matching_does_not_use_substrings() -> None:
    assert filter_tools(ALL_TOOLS, "NotDaofyCoding") == ALL_TOOLS


@pytest.mark.parametrize(
    "session",
    [
        {"client_params": {"clientInfo": {"name": "Daofy Coding"}}},
        SimpleNamespace(
            _client_params=SimpleNamespace(
                client_info={"name": "daofy_coding"},
            ),
        ),
    ],
)
def test_server_reads_client_identity_from_attribute_and_dict_sessions(
    monkeypatch: pytest.MonkeyPatch, session: object
) -> None:
    import src.server as server_module

    monkeypatch.setattr(server_module, "get_server_session", lambda _server: session)

    assert server_module._get_mcp_client_name(object()) in {
        "Daofy Coding",
        "daofy_coding",
    }


@pytest.mark.parametrize("tool_name,replacement", [
    ("structured_content", "structured_content"),
    ("automate_delphi", "automation_run"),
    ("delphi_rtti", "automation_run"),
])
def test_daofycoding_cannot_call_a_hidden_tool(tool_name: str, replacement: str) -> None:
    with pytest.raises(ValueError, match=f"native '{replacement}'"):
        ensure_tool_visible(tool_name, "DaofyCoding")


def test_regular_clients_can_call_every_registered_tool() -> None:
    for tool in ALL_TOOLS:
        ensure_tool_visible(tool.name, "other-client")
