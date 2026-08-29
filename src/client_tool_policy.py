"""Client-aware MCP tool visibility policy.

DaofyCoding owns several capabilities that were originally prototyped in the
Daofy MCP server.  When DaofyCoding is the MCP client, exposing both copies
creates ambiguous tool choices and can route work through the optional server
instead of the host-owned implementation.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar


DAOFYCODING_CLIENT_NAMES = frozenset({
    "daofycoding",
    "daofyagent",  # Compatibility with DaofyCoding builds before 2026-08-28.
})

DAOFYCODING_NATIVE_TOOL_REPLACEMENTS = {
    "structured_content": "structured_content",
    "automate_delphi": "automation_run",
    "delphi_rtti": "automation_run",
}

_ToolDefinitionT = TypeVar("_ToolDefinitionT")


def normalize_client_name(client_name: str | None) -> str:
    """Return the stable comparison form for an MCP client name."""
    # MCP client names are display strings, so tolerate harmless separators and
    # casing differences without using substring matching (which could hide
    # tools from an unrelated client such as ``NotDaofyCoding``).
    return "".join(
        character
        for character in str(client_name or "").casefold()
        if character.isalnum()
    )


def is_daofycoding_client(client_name: str | None) -> bool:
    """Return whether the standard MCP clientInfo identifies DaofyCoding."""
    return normalize_client_name(client_name) in DAOFYCODING_CLIENT_NAMES


def hidden_tool_names(client_name: str | None) -> frozenset[str]:
    """Return tools superseded by native capabilities in the current client."""
    if not is_daofycoding_client(client_name):
        return frozenset()
    return frozenset(DAOFYCODING_NATIVE_TOOL_REPLACEMENTS)


def filter_tools(
    tools: Iterable[_ToolDefinitionT],
    client_name: str | None,
) -> list[_ToolDefinitionT]:
    """Filter tool definitions while preserving registry order."""
    hidden = hidden_tool_names(client_name)
    return [tool for tool in tools if getattr(tool, "name", "") not in hidden]


def ensure_tool_visible(tool_name: str, client_name: str | None) -> None:
    """Reject direct calls to tools hidden from the current client."""
    if tool_name not in hidden_tool_names(client_name):
        return
    replacement = DAOFYCODING_NATIVE_TOOL_REPLACEMENTS[tool_name]
    raise ValueError(
        f"Tool '{tool_name}' is hidden for DaofyCoding clients; "
        f"use the native '{replacement}' tool instead."
    )
