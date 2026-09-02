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

import logging
import re
from typing import Any, Optional, Union

try:  # jsonschema is a hard dependency of the mcp SDK (both v1/v2)
    import jsonschema
except Exception:  # pragma: no cover - degrade to no validation
    jsonschema = None

import anyio
from pydantic import AnyUrl, BaseModel

logger = logging.getLogger(__name__)

# ── Version detection ──────────────────────────────────────────────
# Feature-detect the SDK generation first. v2 renamed McpError→MCPError
# and removed mcp.server.lowlevel.server.ReadResourceContents, while
# __version__ is unreliable (missing or still 1.x-style on some 2.x
# builds), so the version number is only a fallback.

def _detect_mcp2() -> bool:
    """Return True when the installed mcp SDK uses the v2 API surface.

    Detection order:
      1. mcp.shared.exceptions.MCPError present  → v2
      2. mcp.shared.exceptions.McpError present  → v1
      3. mcp.__version__ major >= 2              → v2 (fallback)
      Otherwise                                  → v1
    """
    try:
        import mcp.shared.exceptions as _exc

        if hasattr(_exc, "MCPError"):
            return True
        if hasattr(_exc, "McpError"):
            return False
    except (ImportError, AttributeError):
        logger.debug(
            "mcp shared.exceptions feature detection failed", exc_info=True
        )
    try:
        import mcp

        _ver = getattr(mcp, "__version__", "") or ""
        _m = re.match(r"(\d+)", str(_ver))
        return bool(_m and int(_m.group(1)) >= 2)
    except ImportError:
        return False


MCP2 = _detect_mcp2()

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
# Feature-detect rather than rely on version number, because some mcp
# releases expose 1.x __version__ while already using MCPError naming.

try:
    from mcp.shared.exceptions import MCPError as _McpErrorOrigin
except ImportError:
    from mcp.shared.exceptions import McpError as _McpErrorOrigin

# Re-export as McpError for callers that use the v1 name.
McpError = _McpErrorOrigin

# ── Transport (unchanged) ──────────────────────────────────────────

from mcp.server.stdio import stdio_server


class _StdinEofLoggingReceiveStream:
    """Log once when the MCP stdio input stream reaches EOF."""

    def __init__(self, stream: Any) -> None:
        self._stream = stream
        self._eof_logged = False

    def _log_eof(self) -> None:
        if self._eof_logged:
            return
        self._eof_logged = True
        logger.info("mcp_lifecycle event=stdin_eof transport=stdio")

    async def receive(self) -> Any:
        try:
            return await self._stream.receive()
        except anyio.EndOfStream:
            self._log_eof()
            raise

    def __aiter__(self) -> "_StdinEofLoggingReceiveStream":
        return self

    async def __anext__(self) -> Any:
        try:
            return await self.receive()
        except anyio.EndOfStream as exc:
            raise StopAsyncIteration from exc

    async def __aenter__(self) -> "_StdinEofLoggingReceiveStream":
        await self._stream.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        return await self._stream.__aexit__(exc_type, exc, tb)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)

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
    """Create TextResourceContents with version-appropriate field names.

    `uri` may be passed as a pydantic ``AnyUrl`` (some call sites do); v2's
    ``TextResourceContents.uri`` is a strict ``str`` field, so coerce the
    ``AnyUrl`` to its string form first to avoid a ValidationError.
    """
    if isinstance(uri, AnyUrl):
        uri = str(uri)
    if MCP2:
        return TextResourceContents(uri=uri, mime_type=mime_type, text=text)
    return TextResourceContents(uri=uri, mimeType=mime_type, text=text)


def make_read_resource_result(contents: list) -> ReadResourceResult:
    """Create ReadResourceResult (API unchanged between v1/v2)."""
    return ReadResourceResult(contents=contents)


def call_tool_result_is_error(result: Any) -> bool:
    """Read the error flag off a ``CallToolResult`` across SDK generations.

    v1 uses camelCase ``isError``, v2 uses snake_case ``is_error``. Duck-type
    so both work; non-``CallToolResult`` inputs (dict/str/etc.) return False.
    """
    if isinstance(result, CallToolResult):
        return bool(
            getattr(result, "isError", None)
            or getattr(result, "is_error", None)
        )
    return False


def _make_error_result(error_message: str) -> CallToolResult:
    """Build an error ``CallToolResult`` across SDK generations.

    v1 uses ``isError``, v2 uses ``is_error``; pick the field
    the installed model accepts.
    """
    text = TextContent(type="text", text=error_message)
    if hasattr(CallToolResult, "is_error"):
        return CallToolResult(content=[text], is_error=True)
    return CallToolResult(content=[text], isError=True)


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
        # v1's lowlevel server populates this cache from the list_tools
        # handler and then validates call_tool arguments against
        # tool.inputSchema (validate_input=True). v2's runner has no such
        # validation, so we mirror it: capture name → inputSchema here and
        # validate in _raw_adapt_v2("call_tool").
        self._tool_schemas: dict[str, dict[str, Any]] = {}

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

    def _raw_adapt_v2(self, method: str, func: Any) -> Any:
        """Wrap a v1-style handler into the v2 ``(ctx, params)`` signature.

        v2's ServerRunner invokes every request handler as
        ``handler(ctx, typed_params)``.  Our handlers are written against the
        v1 decorator API (``list_tools()`` / ``call_tool(name, arguments)``
        / ...), so each one is adapted here:

        =================  ============================  ====================
        v1 handler         v2 params type                adaptation
        =================  ============================  ====================
        list_tools()       PaginatedRequestParams        drop ctx/params
        list_resources()   PaginatedRequestParams        drop ctx/params
        list_prompts()     PaginatedRequestParams        drop ctx/params
        call_tool(n, a)    CallToolRequestParams         params.name/arguments
        read_resource(u)   ReadResourceRequestParams     params.uri
        get_prompt(n, a)   GetPromptRequestParams        params.name/arguments
        =================  ============================  ====================

        Returns the original function unchanged (for v1 / tests).
        """
        if method in ("list_tools", "list_resources", "list_prompts"):
            # v1 handlers returned a bare list of BaseModel instances (Tool /
            # Resource / Prompt). v2's runner validates the result against the
            # per-version protocol result model (ListToolsResult /
            # ListResourcesResult / ListPromptsResult), which requires the
            # items under the plural key AND plain-dict items — a BaseModel
            # instance built from v1's mcp.types fails the v2 per-version
            # model check (different class). The 2026-07-28 surface also
            # requires resultType/ttlMs/cacheScope; supply neutral "no cache"
            # defaults, older surfaces ignore them via extra="ignore".
            _key = {
                "list_tools": "tools",
                "list_resources": "resources",
                "list_prompts": "prompts",
            }[method]

            async def _no_params(ctx: Any, params: Any, _key: str = _key) -> Any:
                items = await func()
                dumped = []
                for it in items:
                    if isinstance(it, BaseModel):
                        dumped.append(
                            it.model_dump(
                                by_alias=True, mode="json", exclude_none=True
                            )
                        )
                    else:
                        dumped.append(it)
                # Capture tool inputSchemas so _call_tool can apply the same
                # jsonschema validation v1 performs server-side (v2 skips it).
                if _key == "tools":
                    for it in dumped:
                        if isinstance(it, dict):
                            schema = it.get("input_schema") or it.get("inputSchema")
                            if isinstance(schema, dict):
                                self._tool_schemas[it.get("name", "")] = schema
                return {
                    _key: dumped,
                    "resultType": "complete",
                    "ttlMs": 0,
                    "cacheScope": "private",
                }

            return _no_params
        if method == "call_tool":
            async def _call_tool(ctx: Any, params: Any) -> Any:
                # v2 may deliver arguments=None for a no-arg invocation; the
                # v1 handlers expect a dict.
                arguments = params.arguments or {}
                # Mirror v1's server-side input validation (validate_input=True
                # in mcp v1 lowlevel server.call_tool). v2's runner performs no
                # such check, so empty/malformed required params would reach the
                # handler and execute side effects. Reject them exactly like v1.
                if jsonschema is not None:
                    schema = self._tool_schemas.get(params.name)
                    if schema is not None:
                        try:
                            jsonschema.validate(instance=arguments, schema=schema)
                        except jsonschema.ValidationError as e:
                            return _make_error_result(
                                f"Input validation error: {e.message}"
                            )
                return await func(params.name, arguments)

            return _call_tool
        if method == "read_resource":
            async def _read_resource(ctx: Any, params: Any) -> Any:
                # v1 read_resource handlers return a bare list of
                # ReadResourceContents (content/mime_type); v2's runner validates
                # the result against the per-version ReadResourceResult model,
                # which requires dict contents {uri, mimeType, text} plus the
                # 2026-era resultType/ttlMs/cacheScope. Mirror the list_* fix.
                items = await func(params.uri)
                dumped = []
                for it in items:
                    content = getattr(it, "content", None)
                    mime_type = getattr(it, "mime_type", None) or getattr(
                        it, "mimeType", None
                    )
                    dumped.append(
                        {
                            "uri": str(params.uri),
                            "mimeType": mime_type,
                            "text": content,
                        }
                    )
                return {
                    "contents": dumped,
                    "resultType": "complete",
                    "ttlMs": 0,
                    "cacheScope": "private",
                }

            return _read_resource
        if method == "get_prompt":
            async def _get_prompt(ctx: Any, params: Any) -> Any:
                return await func(params.name, params.arguments)

            return _get_prompt
        return func

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
                    kwargs[v] = self._raw_adapt_v2(k, self._handlers[k])
            kwargs.update(self._kwargs)
            # v2's Server only advertises name/version in serverInfo unless
            # title/description are passed explicitly. Under v1 the same
            # `title`/`description` were hardcoded in `_V1DaofyServerSession`;
            # mirror them here so the two SDK generations agree on the wire.
            kwargs.setdefault(
                "title",
                "Daofy for Delphi"
                if self._name == "daofy-for-delphi"
                else self._name,
            )
            kwargs.setdefault(
                "description",
                "Daofy for Delphi MCP Server，提供 Delphi 项目编译、知识库搜索、安全文件读写、自动化测试和审计工具。",
            )
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
    logged_read_stream = _StdinEofLoggingReceiveStream(read_stream)
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
                logged_read_stream,
                write_stream,
                initialization_options,
            )
        logger.info("mcp_lifecycle event=server_run_returned sdk_mode=v2")
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
                    logged_read_stream,
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
        logger.info("mcp_lifecycle event=server_run_returned sdk_mode=v1_compat")


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


# ── Session accessor helper ────────────────────────────────────────

def get_server_session(server_obj: Any) -> Optional[Any]:
    """Get the current request's server session, None if unavailable.

    Recent MCP SDK releases continue to expose ``request_context``.  Keep the
    lookup duck-typed so both SDK generations and test doubles are supported.
    """
    try:
        context = getattr(server_obj, "request_context", None)
        return getattr(context, "session", None)
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
