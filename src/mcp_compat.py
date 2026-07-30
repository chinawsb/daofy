"""
MCP SDK v1/v2 compatibility layer.

Detects installed mcp version at import time and provides unified imports,
type factories, and a CompatibleServer wrapper that work with both
MCP Python SDK v1.x and v2.x.

MCP v2 breaking changes handled here:
  - mcp.server.lowlevel.server.ReadResourceContents → removed, defined locally
  - mcp.server.session.InitializationState → removed, stubbed
  - mcp.server.session.SUPPORTED_PROTOCOL_VERSIONS → deprecated, stubbed
  - @server.list_tools() decorators → replaced with on_* constructor params
  - Tool(inputSchema=...) → Tool(input_schema=...)
  - Resource(mimeType=...) → Resource(mime_type=...)
  - ServerSession → thin proxy (init flow differs)
  - McpError → MCPError
  - Experimental Tasks support → removed
  - Server.run(stateless=...) → parameter removed
  - server.request_context.session → removed
"""

from __future__ import annotations

import re
from typing import Any, Optional, Union

# ── Version detection ──────────────────────────────────────────────

try:
    import mcp

    _ver = getattr(mcp, "__version__", "") or ""
    _m = re.match(r"(\d+)", str(_ver))
    MCP2 = bool(_m and int(_m.group(1)) >= 2)
except ImportError:
    MCP2 = False

# ── Type re-exports (mcp.types remains as permanent alias in v2) ──

import mcp.types as mcp_types

from mcp.types import (
    CallToolResult,
    GetPromptResult,
    LATEST_PROTOCOL_VERSION,
    Prompt,
    PromptArgument,
    PromptMessage,
    ReadResourceResult,
    Resource,
    TextContent,
    TextResourceContents,
    Tool,
)

# ── Error class (McpError → MCPError in v2) ───────────────────────

if MCP2:
    from mcp.shared.exceptions import MCPError as _McpErrorOrigin
else:
    from mcp.shared.exceptions import McpError as _McpErrorOrigin

# In v2 it's named MCPError; we re-export as McpError for v1 callers
McpError = _McpErrorOrigin

# ── Transport (unchanged) ──────────────────────────────────────────

from mcp.server.stdio import stdio_server

# ── Server base (from mcp.server import Server is unchanged) ──────

# ── Version-dependent symbols ───────────────────────────────────────

if MCP2:
    from dataclasses import dataclass

    from mcp.server.session import ServerSession as _V2ServerSession

    # ReadResourceContents was in mcp.server.lowlevel.server in v1, removed in v2
    @dataclass
    class ReadResourceContents:
        """Replacement for mcp.server.lowlevel.server.ReadResourceContents (removed in v2)."""
        content: Union[str, bytes]
        mime_type: str

    # InitializationState was in mcp.server.session in v1, removed in v2
    class InitializationState:
        """Stub for v1's InitializationState (removed in v2)."""
        NotInitialized = "not_initialized"
        Initializing = "initializing"
        Initialized = "initialized"

    # SUPPORTED_PROTOCOL_VERSIONS deprecated in v2
    SUPPORTED_PROTOCOL_VERSIONS: list[str] = [
        "2026-07-28",
        "2025-11-25",
        "2025-03-26",
    ]

else:
    from mcp.server.lowlevel.server import ReadResourceContents
    from mcp.server.session import (
        SUPPORTED_PROTOCOL_VERSIONS,
        InitializationState,
        ServerSession,
    )


# ── Field-name factory helpers ─────────────────────────────────────
# In v2, all Pydantic model fields use snake_case for Python attribute access.

def make_tool(name: str, description: str, input_schema: dict) -> Tool:
    """Create Tool with version-appropriate field names."""
    if MCP2:
        return Tool(name=name, description=description, input_schema=input_schema)
    return Tool(name=name, description=description, inputSchema=input_schema)


def make_resource(
    uri: str, name: str, title: str, description: str, mime_type: str
) -> Resource:
    """Create Resource with version-appropriate field names."""
    if MCP2:
        return Resource(
            uri=uri, name=name, title=title,
            description=description, mime_type=mime_type,
        )
    return Resource(
        uri=uri, name=name, title=title,
        description=description, mimeType=mime_type,
    )


def make_text_resource_contents(
    uri: str, mime_type: str, text: str
) -> TextResourceContents:
    """Create TextResourceContents with version-appropriate field names."""
    if MCP2:
        return TextResourceContents(uri=uri, mime_type=mime_type, text=text)
    return TextResourceContents(uri=uri, mimeType=mime_type, text=text)


def make_read_resource_result(contents: list) -> ReadResourceResult:
    """Create ReadResourceResult (API unchanged between v1/v2)."""
    return ReadResourceResult(contents=contents)


# ── CompatibleServer — wraps the decorator→on_* migration ─────────

class CompatibleServer:
    """MCP Server wrapper that works with both v1 (decorators) and v2 (on_*).

    Usage:
        server = CompatibleServer("name", version="1.0")

        @server.list_tools()
        async def list_tools():
            return [...]

        @server.call_tool()
        async def call_tool(name: str, arguments: dict):
            ...

        # The underlying Server is created lazily on first real attribute access.
        opts = server.create_initialization_options()
    """

    def __init__(self, name: str, **kwargs: Any) -> None:
        self._name = name
        self._kwargs = kwargs
        self._handlers: dict[str, Any] = {}
        self._server: Any = None

    def _reg(self, method: str, func: Any) -> Any:
        self._handlers[method] = func
        return func

    def list_tools(self):
        """Decorator: @server.list_tools()"""
        def deco(f):
            return self._reg("list_tools", f)
        return deco

    def call_tool(self):
        """Decorator: @server.call_tool()"""
        def deco(f):
            return self._reg("call_tool", f)
        return deco

    def list_resources(self):
        """Decorator: @server.list_resources()"""
        def deco(f):
            return self._reg("list_resources", f)
        return deco

    def read_resource(self):
        """Decorator: @server.read_resource()"""
        def deco(f):
            return self._reg("read_resource", f)
        return deco

    def list_prompts(self):
        """Decorator: @server.list_prompts()"""
        def deco(f):
            return self._reg("list_prompts", f)
        return deco

    def get_prompt(self):
        """Decorator: @server.get_prompt()"""
        def deco(f):
            return self._reg("get_prompt", f)
        return deco

    def _ensure_server(self) -> None:
        if self._server is not None:
            return
        if MCP2:
            from mcp.server import Server as _V2Server

            handler_map = {
                "list_tools": "on_list_tools",
                "call_tool": "on_call_tool",
                "list_resources": "on_list_resources",
                "read_resource": "on_read_resource",
                "list_prompts": "on_list_prompts",
                "get_prompt": "on_get_prompt",
            }
            kwargs: dict[str, Any] = {}
            for k, v in handler_map.items():
                if k in self._handlers:
                    kwargs[v] = self._handlers[k]
            kwargs.update(self._kwargs)
            self._server = _V2Server(self._name, **kwargs)
        else:
            from mcp.server import Server as _V1Server

            self._server = _V1Server(self._name, **self._kwargs)
            for method in (
                "list_tools",
                "call_tool",
                "list_resources",
                "read_resource",
                "list_prompts",
                "get_prompt",
            ):
                if method in self._handlers:
                    getattr(self._server, method)()(self._handlers[method])

    def __getattr__(self, name: str) -> Any:
        # Instance attributes (_handlers, _server, _name, _kwargs) are
        # found in instance.__dict__ before this is ever called, so
        # underscore-prefixed attributes that reach here must be
        # forwarded to the underlying Server (e.g. _handle_message).
        self._ensure_server()
        return getattr(self._server, name)


# ── Run MCP server (version-adaptive) ──────────────────────────────

async def run_mcp_server(
    server: CompatibleServer,
    read_stream: Any,
    write_stream: Any,
    *,
    fetch_workspace_roots=None,
    install_client_rules=None,
) -> None:
    """Run MCP server with both v1 and v2 session handling.

    Parameters
    ----------
    server : CompatibleServer
        The server instance (with handlers already registered via decorators).
    read_stream, write_stream :
        stdio transport streams from stdio_server().
    fetch_workspace_roots :
        Optional async callable(session) for v1-style roots fetching.
    install_client_rules :
        Optional async callable(session) for client rules installation.
    """
    if MCP2:
        # v2: Server.run() handles session creation internally
        import anyio
        from contextlib import AsyncExitStack

        initialization_options = server.create_initialization_options()
        async with AsyncExitStack() as stack:
            lifespan_context = await stack.enter_async_context(
                server.lifespan(server)
            )
            await server.run(
                read_stream,
                write_stream,
                initialization_options,
            )
    else:
        # v1: manual session creation with DaofyServerSession
        from contextlib import AsyncExitStack

        import anyio

        initialization_options = server.create_initialization_options()
        async with AsyncExitStack() as stack:
            lifespan_context = await stack.enter_async_context(
                server.lifespan(server)
            )
            session = await stack.enter_async_context(
                _V1DaofyServerSession(
                    read_stream,
                    write_stream,
                    initialization_options,
                )
            )

            # Experimental Tasks support (v1 only)
            _task_support = _get_experimental_task_support_v1(server)
            if _task_support is not None:
                _task_support.configure_session(session)
                await stack.enter_async_context(_task_support.run())

            async with anyio.create_task_group() as tg:
                if fetch_workspace_roots:
                    tg.start_soon(fetch_workspace_roots, session)
                if install_client_rules:
                    tg.start_soon(install_client_rules, session)
                try:
                    async for message in session.incoming_messages:
                        tg.start_soon(
                            server._handle_message,
                            message,
                            session,
                            lifespan_context,
                            False,
                        )
                finally:
                    tg.cancel_scope.cancel()


# ── v1-only helpers ────────────────────────────────────────────────

def _get_experimental_task_support_v1(server_obj: Any) -> Optional[Any]:
    """Return MCP task support (v1 only)."""
    experimental_handlers = getattr(server_obj, "_experimental_handlers", None)
    if experimental_handlers is None:
        return None
    return getattr(experimental_handlers, "task_support", None)


# DaofyServerSession — v1 only (v2 ServerSession is a thin proxy)
if not MCP2:
    from mcp.server.session import ServerSession as _BaseSession

    class _V1DaofyServerSession(_BaseSession):
        """v1 ServerSession with MCP 2025-11-25 serverInfo.description metadata."""

        async def _received_request(self, responder):
            match responder.request.root:
                case mcp_types.InitializeRequest(params=params):
                    requested_version = params.protocolVersion
                    self._initialization_state = InitializationState.Initializing
                    self._client_params = params
                    with responder:
                        await responder.respond(
                            mcp_types.ServerResult(
                                mcp_types.InitializeResult(
                                    protocolVersion=requested_version
                                    if requested_version in SUPPORTED_PROTOCOL_VERSIONS
                                    else mcp_types.LATEST_PROTOCOL_VERSION,
                                    capabilities=self._init_options.capabilities,
                                    serverInfo=mcp_types.Implementation(
                                        name=self._init_options.server_name,
                                        title="Daofy for Delphi",
                                        version=self._init_options.server_version,
                                        websiteUrl=self._init_options.website_url,
                                        icons=self._init_options.icons,
                                        description="Daofy for Delphi MCP Server，提供 Delphi 项目编译、知识库搜索、安全文件读写、自动化测试和审计工具。",
                                    ),
                                    instructions=self._init_options.instructions,
                                )
                            )
                        )
                    self._initialization_state = InitializationState.Initialized
                case _:
                    await super()._received_request(responder)
else:
    # v2 thin proxy — not used in this mode
    _V1DaofyServerSession = None  # type: ignore


# ── Session accessor helper (for request_context.session removal) ──

def get_server_session(server_obj: Any) -> Optional[Any]:
    """Get the current server session, None if unavailable.

    In v1: server.request_context.session
    In v2: request_context property removed; returns None (callers must handle).
    """
    if MCP2:
        return None
    try:
        return getattr(server_obj, "request_context", None).session
    except Exception:
        return None


# ── Notification helper (v2-safe) ──────────────────────────────────

async def send_task_notification(
    session: Any, task_info: Any, datetime_now=None
) -> None:
    """Send TaskStatusNotification to MCP client.

    Works with both v1 and v2 sessions. Silently no-ops if session is None.
    """
    if session is None:
        return
    try:
        from mcp.types import (
            TaskStatusNotification,
            TaskStatusNotificationParams,
        )

        import datetime as _dt

        status_map = {
            "COMPLETED": "completed",
            "FAILED": "failed",
            "CANCELLED": "cancelled",
        }
        ts = task_info.status.name
        mcp_status = status_map.get(ts, "completed")
        created = task_info.created_at
        updated = task_info.completed_at or (datetime_now or _dt.datetime.now())

        notif = TaskStatusNotification(
            params=TaskStatusNotificationParams(
                taskId=task_info.task_id,
                status=mcp_status,
                statusMessage=(
                    task_info.message[:500] if task_info.message else None
                ),
                createdAt=created,
                lastUpdatedAt=updated,
                ttl=3600000,
            )
        )
        await session.send_notification(notif)
    except Exception:
        pass  # notification best-effort
