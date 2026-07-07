"""
Daofy 主程序

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

提供 MCP 协议服务,注册所有工具并启动服务器
"""

import asyncio
import sys
import os
import time
import winreg
import logging as _logging
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Optional

import anyio

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'

# 保护: 子进程(multiprocessing spawn) 的 stdout 已经 pipe,
# TextIOWrapper 可能失败。失败时跳过不影响子进程通信。
if __name__ != '__mp_main__':
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=False)
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=False)
    except Exception:
        import logging as _logging
        _logger = _logging.getLogger(__name__)
        _logger.warning("stdout/stderr 编码设置失败，部分输出可能乱码", exc_info=True)

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.constants import (
    REG_KEY_EMBARCADERO_BDS,
    TIMEOUT_AUTOMATION_GUI,
    TIMEOUT_EXPERIENCE_TOOL,
    TIMEOUT_GENERATE_COPYRIGHT,
)

MCP_SERVER_INSTRUCTIONS = """你正在使用 Daofy for Delphi MCP Server。

关键工具路由规则：
- Delphi 文件(.pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx)必须用 `delphi_file` 读写/搜索/正则匹配+替换，不要用内置 Read/Edit/Write/grep。
- 修改 Delphi 代码前，按需调用 `get_coding_rules(section="writing")` 获取规则；用 `delphi_kb` 查 API/项目符号；用 `delphi_project` 做 compile/audit/layout/runtime 验证。
- 所有 Git 操作必须使用 `code_hosting`，不要在 shell 中直接运行 git。
- 不确定工具用法时，先调用 `tool_help(tool_name=...)` 或 `get_coding_rules(...)`。
"""

MCP_SERVER_DESCRIPTION = (
    "Daofy for Delphi MCP Server，提供 Delphi 项目编译、知识库搜索、"
    "安全文件读写、自动化测试和审计工具。"
)

# ============================================================
# multiprocessing 子进程保护
# Windows spawn模式下,子进程会重新导入 __main__ 模块(即本文件),
# 导致所有服务模块被重新导入(885个模块),启动极慢。
# 检测到是子进程时,跳过所有服务导入,只保留必要的模块。
# ============================================================
_is_multiprocessing_child = __name__ == '__mp_main__'

if _is_multiprocessing_child:
    # 子进程不需要任何MCP服务,直接跳过
    # ProcessPoolExecutor的worker只需要能pickle/unpickle函数即可
    pass
else:

    from mcp.server import Server
    from mcp.server.lowlevel.server import ReadResourceContents
    from mcp.server.session import (
        InitializationState,
        SUPPORTED_PROTOCOL_VERSIONS,
        ServerSession,
    )
    from mcp.server.stdio import stdio_server
    import mcp.types as mcp_types
    from mcp.types import CallToolResult, TextContent, Tool, Resource, ReadResourceResult, TextResourceContents, Prompt, PromptArgument, PromptMessage, GetPromptResult

    from src.services.config_manager import ConfigManager
    from src.services.compiler_service import CompilerService
    from src.services.knowledge_base.zvec_adapter import ZVecKnowledgeBaseAdapter
    from src.services.knowledge_base.thirdparty_knowledge_base import ThirdPartyKnowledgeBase
    from src.services.agent_skill_installer import install_daofy_agent_skills
    from src.tools.project import handle_project as _handle_project
    # project 模块统一管理编译器服务，保留别名供初始化用
    from src.tools.compile_project import set_compiler_service as sp1
    from src.tools.compile_file import set_compiler_service as sp2
    from src.tools.get_args import set_compiler_service as sp3
    from src.tools.config import set_config_manager, search_compilers
    from src.tools.environment import check_environment, set_config_manager as scm, set_thirdparty_kb_service as stks
    from src.tools.knowledge_base import (
        set_delphi_kb_service,
        set_thirdparty_kb_service,
        _resolve_project_path,
    )
    from src.tools.read_source_file import set_knowledge_base_services, read_source_file
    from src.tools import knowledge_base as kb_tools
    from src.tools import thirdparty_knowledge_base as thirdparty_kb_tools
    from src.tools import async_tasks as async_tools
    from src.tools import pasfmt
    from src.tools.install_package import handle_package, set_compiler_service as sip
    from src.tools import document_kb_tools as doc_tools
    from src.tools.code_hosting import code_hosting
    from src.tools import file_tool
    from src.tools import dfm_utils as dfm_utils_mod
    from src.tools import manage_component as manage_component_mod
    from src.tools import create_component_dfm as create_component_dfm_mod
    from src.tools.coding_rules import get_coding_rules as _get_coding_rules
    from src.tools.tool_help import get_tool_help
    from src.tools.experience import experience as _experience
    from src.mcp_resources import (
        available_public_resources,
        build_public_resource_index,
        get_public_resource_text,
    )
    from src.tool_docs import TOOL_NAMES, TOOL_SHORT_DESC
    from src.utils.logger import init_default_logger, log_api_call
    from src.__version__ import __version__, __copyright__
    from src.utils import updater
    from src.services.knowledge_base.async_task_manager import get_task_manager
    from src.services.automation_service import (
    execute_automation as _execute_automation,
    detect_exe_subsystem as _detect_exe_subsystem,
    IMAGE_SUBSYSTEM_WINDOWS_GUI,
    IMAGE_SUBSYSTEM_WINDOWS_CUI,
)
    from src.tools.delphi_rtti import handle_delphi_rtti as _handle_delphi_rtti
    from src.services.copyright_service import generate_copyright as _generate_copyright
    # ocr 使用延迟导入 — 仅当工具调用时才 import（避免未装 onnxruntime 时启动崩溃）

    # 后台版本检查结果缓存（由 startup 异步任务填充）
    _update_check_result: Optional[dict] = None
    _update_check_done: bool = False

    # 文件变更监听器（由 startup 异步任务启动）
    _project_file_watcher: Optional[object] = None

    # 服务器启动时间（用于 /health 资源）
    _server_start_time: float = 0.0
    # 最近一次 KB 构建时间
    _last_kb_build_time: Optional[float] = None

    # 初始化日志
    logger = init_default_logger()


    class DaofyServerSession(ServerSession):
        """ServerSession with MCP 2025-11-25 serverInfo.description metadata."""

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
                                        description=MCP_SERVER_DESCRIPTION,
                                    ),
                                    instructions=self._init_options.instructions,
                                )
                            )
                        )
                    self._initialization_state = InitializationState.Initialized
                case _:
                    await super()._received_request(responder)


    def _get_experimental_task_support(server_obj: Any) -> Optional[Any]:
        """Return MCP task support when the installed SDK exposes it."""
        experimental_handlers = getattr(server_obj, "_experimental_handlers", None)
        if experimental_handlers is None:
            return None
        return getattr(experimental_handlers, "task_support", None)


    async def _run_mcp_server(server, read_stream, write_stream) -> None:
        """Run the MCP server with Daofy initialize metadata."""
        initialization_options = server.create_initialization_options()
        async with AsyncExitStack() as stack:
            lifespan_context = await stack.enter_async_context(server.lifespan(server))
            session = await stack.enter_async_context(
                DaofyServerSession(
                    read_stream,
                    write_stream,
                    initialization_options,
                    stateless=False,
                )
            )

            task_support = _get_experimental_task_support(server)
            if task_support is not None:
                task_support.configure_session(session)
                await stack.enter_async_context(task_support.run())

            async with anyio.create_task_group() as tg:
                try:
                    async for message in session.incoming_messages:
                        logger.debug("Received message: %s", message)
                        tg.start_soon(
                            server._handle_message,
                            message,
                            session,
                            lifespan_context,
                            False,
                        )
                finally:
                    tg.cancel_scope.cancel()


def _auto_detect_delphi_help_dir() -> Optional[str]:
    """自动检测最新安装的 Delphi 帮助文档目录"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_EMBARCADERO_BDS)
        versions = []
        i = 0
        while True:
            try:
                versions.append(winreg.EnumKey(key, i))
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)

        versions.sort(key=lambda x: float(x) if x.replace('.', '').isdigit() else 0, reverse=True)
        for ver in versions:
            try:
                vk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{REG_KEY_EMBARCADERO_BDS}\\{ver}")
                root_dir = winreg.QueryValueEx(vk, "RootDir")[0]
                winreg.CloseKey(vk)
                help_dir = Path(root_dir) / "Help" / "Doc"
                if help_dir.exists():
                    logger.info(f"自动检测到 Delphi 帮助目录 (版本 {ver}): {help_dir}")
                    return str(help_dir)
            except Exception:
                logger.debug("读取注册表版本键失败", exc_info=True)
                continue
    except Exception:
        logger.debug("打开注册表 BDS 键失败", exc_info=True)

    # 注册表失败，尝试默认路径（版本号与注册表一致：37.0=Delphi13, 23.0=Delphi12, 22.0=Delphi11...）
    # 只有 17.0 (XE) 及以上版本使用此目录结构
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if not program_files_x86:
        return None
    for ver in ["37.0", "23.0", "22.0", "21.0", "20.0", "19.0", "18.0", "17.0"]:
        path = Path(program_files_x86) / "Embarcadero" / "Studio" / ver / "Help" / "Doc"
        if path.exists():
            logger.info(f"使用默认帮助目录: {path}")
            return str(path)
    return None


def _get_smart_hint(name: str, result: Any, arguments: dict) -> Optional[str]:
    """
    智能提示：根据工具名和返回结果，生成下一步建议。

    Args:
        name: 工具名
        result: 工具返回结果（dict 或 CallToolResult）
        arguments: 调用参数

    Returns:
        建议文本，无建议时返回 None
    """
    if name == "delphi_kb":
        action = arguments.get("action", "search")
        if action == "search":
            if isinstance(result, dict):
                results = result.get('results') or result.get('data') or []
                if isinstance(results, list) and len(results) > 0:
                    return ("hint: use "
                            'delphi_file(action="read", file_path="...") to read full source')
        elif action == "stats":
            return ("hint: if KB data is stale, "
                    "use delphi_kb(action='build', kb_type='project') to rebuild")

    elif name == "get_coding_rules":
        # 仅在 section=None（默认模式）时提示
        section = arguments.get("section")
        if section is None or section == "":
            return ("hint: use section param for specific chapters:\n"
                    '   get_coding_rules(section="writing")  - before writing\n'
                    '   get_coding_rules(section="review")   - after compile, before review\n'
                    '   get_coding_rules(section="safety")   - security-sensitive ops')

    elif name == "check_environment":
        action = arguments.get("action", "check")
        if action == "detect" or action == "check":
            if isinstance(result, dict):
                compilers = result.get('compilers') or result.get('data')
                if compilers and len(compilers) > 0:
                    return ("hint: environment ready, "
                            "use delphi_project(action='compile') to verify")
                else:
                    return ("hint: no compiler detected, "
                            "check Delphi installation, "
                            "or use check_environment(action='detect', search_path=...)")

    elif name == "package":
        action = arguments.get("action", "")
        if action == "install":
            if isinstance(result, CallToolResult):
                is_error = result.isError
            elif isinstance(result, dict):
                is_error = (
                    result.get('status') == 'failed'
                    or result.get('success') is False
                    or (result.get('error') is not None and result.get('error') != '')
                )
            else:
                is_error = False
            if not is_error:
                return ("hint: install done, "
                        "use package(action='list') to verify IDE registration")

    # P4: 版本更新提示（检查完成且有新版本时通知 AI）
    if _update_check_done and _update_check_result and _update_check_result.get("update_available"):
        return (
            f"📦 发现新版本 Daofy: v{_update_check_result['current']} → "
            f"v{_update_check_result['latest']}！\n"
            f"请使用 `daofy_update(action=\"check\")` 查看详情，"
            f"或 `daofy_update(action=\"update\")` 通过 git pull 更新。\n"
            f"发布说明: {_update_check_result['release_url']}"
        )

    return None


# ============================================================
# Delphi 文件读写尾注 — 提醒 AI 使用 delphi_file 工具
# ============================================================
# 以下工具返回结果时将追加尾注，防止 AI 绕过 delphi_file 直接读写 .pas/.dfm 等文件
def _redact_env_argument(value: Any) -> Any:
    """Return a log-safe summary for env/environment argument values."""
    if not isinstance(value, dict):
        return "<redacted-env>"
    return {
        "count": len(value),
        "names": sorted(str(key) for key in value),
    }


def _redact_sensitive_arguments(value: Any) -> Any:
    """Recursively redact sensitive values from tool-call arguments."""
    if isinstance(value, dict):
        redacted: dict = {}
        for key, item in value.items():
            if str(key) in {"env", "environment"}:
                redacted[key] = _redact_env_argument(item)
            else:
                redacted[key] = _redact_sensitive_arguments(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_arguments(item) for item in value]
    return value


_DELPHI_FILE_FOOTNOTE_TOOLS: set = {
    "delphi_file",
    "delphi_kb",
    "delphi_project",
    "manage_component",
    "check_environment",
    "get_coding_rules",
    "code_hosting",
}


_DELPHI_FILE_FOOTNOTE_TEXT = (
    "\n\n---\n"
    "⚠️ Delphi 文件必须用 `delphi_file` 读写/搜索/正则匹配+替换，"
    "不要用内置 Read/Edit/Write/grep。"
)

# action → 需要尾注的操作集合
_DELPHI_FILE_FOOTNOTE_ACTIONS: dict[str, set[str]] = {
    "delphi_kb":          {"search", "read", "stats"},
    "delphi_project":     {"info", "ast", "audit", "compile", "compile_file"},
    "check_environment":  {"detect"},
    "code_hosting":       {"git_clone", "git_pull", "git_merge", "git_switch"},
}


def _get_delphi_file_footnote(name: str, arguments: dict) -> Optional[str]:
    """对可能涉及 Delphi 文件操作的工具返回尾注，提醒使用 delphi_file。"""
    if name not in _DELPHI_FILE_FOOTNOTE_TOOLS:
        return None
    # manage_component, get_coding_rules, delphi_file 无 action 限制
    if name in ("manage_component", "get_coding_rules", "delphi_file"):
        return _DELPHI_FILE_FOOTNOTE_TEXT
    action = arguments.get("action", "")
    if name in _DELPHI_FILE_FOOTNOTE_ACTIONS and action in _DELPHI_FILE_FOOTNOTE_ACTIONS[name]:
        return _DELPHI_FILE_FOOTNOTE_TEXT
    return None


def _build_mcp_resource_list(root: Path = project_root) -> list:
    """Build MCP Resource objects exposed by Daofy."""
    resources = [
        Resource(
            uri="delphi://resources",
            name="resources",
            title="Daofy public resource index",
            description="Index of stable Daofy MCP resource URIs for AI agents.",
            mimeType="text/markdown",
        )
    ]
    for spec in available_public_resources(root):
        resources.append(Resource(
            uri=spec.uri,
            name=spec.name,
            title=spec.title,
            description=spec.description,
            mimeType=spec.mime_type,
        ))
    resources.append(Resource(
        uri="delphi://health",
        name="health",
        title="Daofy 服务器状态",
        description="服务器运行状态、版本号、文件监听器状态等健康检查信息",
        mimeType="application/json"
    ))
    return resources


def _compute_uptime_seconds(start_time: float) -> float:
    """Return non-negative uptime for monotonic and legacy epoch start times."""
    if start_time <= 0:
        return 0.0

    monotonic_now = time.monotonic()
    uptime = monotonic_now - start_time
    if uptime < 0:
        uptime = time.time() - start_time
    return max(0.0, uptime)


def _read_mcp_resource(uri: str, root: Path = project_root):
    """Read one MCP Resource exposed by Daofy."""
    from pydantic import AnyUrl  # 延迟导入，避免启动时额外加载

    uri = str(uri)

    if uri == "delphi://resources":
        return ReadResourceResult(
            contents=[TextResourceContents(
                uri=AnyUrl(uri),
                mimeType="text/markdown",
                text=build_public_resource_index(root),
            )]
        )

    if uri.startswith("delphi://automation/") or uri == "delphi://coding-rules":
        try:
            mime_type, content = get_public_resource_text(uri, root)
            return ReadResourceResult(
                contents=[TextResourceContents(
                    uri=AnyUrl(uri),
                    mimeType=mime_type,
                    text=content
                )]
            )
        except FileNotFoundError as e:
            return ReadResourceResult(
                contents=[TextResourceContents(
                    uri=AnyUrl(uri),
                    mimeType="text/plain",
                    text=str(e),
                )]
            )
        except KeyError:
            pass

    if uri == "delphi://health":
        import json as _json
        uptime = _compute_uptime_seconds(_server_start_time)
        watcher_running = (
            _project_file_watcher is not None
        ) if '_project_file_watcher' in globals() else False
        health = {
            "version": __version__,
            "uptime_seconds": round(uptime, 1),
            "uptime": f"{int(uptime // 3600)}h{int((uptime % 3600) // 60)}m{int(uptime % 60)}s",
            "file_watcher_active": watcher_running,
        }
        try:
            from src.services.delphi_edit_guard import snapshot_status
            health["edit_guard"] = snapshot_status()
        except Exception as e:
            health["edit_guard"] = {
                "enabled": False,
                "error": str(e),
            }
        return ReadResourceResult(
            contents=[TextResourceContents(
                uri=AnyUrl(uri),
                mimeType="application/json",
                text=_json.dumps(health, ensure_ascii=False, indent=2)
            )]
        )

    raise ValueError(f"未知资源: {uri}")


def _read_mcp_resource_contents(uri: str, root: Path = project_root) -> list:
    """Read one resource in the shape expected by mcp.server.Server."""
    result = _read_mcp_resource(uri, root)
    return [
        ReadResourceContents(
            content=content.text,
            mime_type=content.mimeType,
        )
        for content in result.contents
    ]


async def run_server():
    """运行 MCP Server"""
    global _server_start_time
    _server_start_time = time.monotonic()
    logger.info(f"启动 Daofy v{__version__}")
    logger.info(f"{__copyright__}")

    # 尽力同步 Daofy Agent Skill。失败不影响 MCP Server 启动。
    try:
        install_daofy_agent_skills()
    except Exception:
        logger.warning("同步 Daofy Agent Skill 失败（不影响正常运行）", exc_info=True)

    # 初始化配置管理器
    config_manager = ConfigManager()
    logger.info("配置管理器初始化完成")

    # 初始化编译服务
    compiler_service = CompilerService(config_manager)
    logger.info("编译服务初始化完成")

    # 初始化知识库服务（ZVec 引擎）
    delphi_source_dirs = []
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_EMBARCADERO_BDS)
        i = 0
        while True:
            try:
                vkey = winreg.EnumKey(key, i)
                vpath = winreg.OpenKey(key, vkey)
                try:
                    root = winreg.QueryValueEx(vpath, "RootDir")[0]
                    src = Path(root) / "source"
                    if src.exists():
                        delphi_source_dirs.append(str(src))
                except OSError:
                    pass
                finally:
                    winreg.CloseKey(vpath)
                i += 1
            except WindowsError:
                break
        winreg.CloseKey(key)
    except Exception as e:
        logger.warning(f"检测 Delphi 版本失败: {e}")

    kb_dir = str(Path(__file__).parent.parent / "data" / "delphi-knowledge-base")
    kb_service = ZVecKnowledgeBaseAdapter(kb_dir, source_dirs=delphi_source_dirs)
    logger.info(f"ZVec 知识库初始化完成 (源码目录: {delphi_source_dirs})")

    # 初始化第三方库知识库服务
    thirdparty_kb_service = ThirdPartyKnowledgeBase()
    thirdparty_kb_tools.set_thirdparty_knowledge_base_service(thirdparty_kb_service)
    logger.info("第三方库知识库服务初始化完成")

    # 设置工具的服务实例
    sp1(compiler_service)
    sp2(compiler_service)
    sp3(compiler_service)
    sip(compiler_service)
    scm(config_manager)
    set_config_manager(config_manager)
    stks(thirdparty_kb_service)
    set_knowledge_base_services(kb_service, thirdparty_kb_service)
    set_delphi_kb_service(kb_service)
    # 项目 KB 服务由 project_path 参数动态创建,不在启动时初始化
    # set_project_kb_service(kb_service)  # kb_service 是 Delphi RTL KB,不适合作为项目 KB
    set_thirdparty_kb_service(thirdparty_kb_service)

    # 设置 DFM 工具编译器路径
    newest = config_manager.get_newest_compiler()
    if newest and newest.path:
        if os.path.isfile(newest.path):
            dfm_utils_mod.set_compiler_path(newest.path)
            create_component_dfm_mod.set_compiler_path(newest.path)
            logger.info(f"DFM 工具编译器路径已设置: {newest.path}")
        else:
            logger.warning("编译器文件不存在: %s，DFM 转换功能将不可用。请重新检测编译器。", newest.path)
    else:
        logger.warning("未找到可用编译器，DFM 转换功能将不可用")

    # 设置事件签名解析器的 KB 服务引用
    from src.tools.dfm_parser import set_kb_services as _set_dfm_kb
    _set_dfm_kb(delphi_kb=kb_service, thirdparty_kb=thirdparty_kb_service)

    logger.info("工具服务实例设置完成")

    # 创建 MCP Server 实例
    server = Server(
        "daofy-for-delphi",
        version=__version__,
        instructions=MCP_SERVER_INSTRUCTIONS,
    )
    logger.info("MCP Server 实例创建完成")

    # ============================================================
    # MCP 工具注册
    # 所有工具必须同时在 list_tools() 和 call_tool() 中注册
    # ============================================================
    @server.list_tools()
    async def list_tools():
        """列出所有可用工具"""
        return [
            # ===== Delphi 项目全生命周期管理 ⭐⭐⭐ =====
            Tool(
                name="delphi_project",
                description=TOOL_SHORT_DESC["delphi_project"],
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["compile", "compile_file", "dry_run", "info", "create",
                                     "set", "add_config", "remove_config", "add_source",
                                     "remove_source", "audit", "ast", "runtime", "layout"],
                            "description": "操作类型。先 tool_help('delphi_project') 查看各 action 的参数说明。"
                        },
                        "project_path": {"type": "string", "description": "项目文件路径(.dproj/.dpr/.dpk/.pas)"},
                        "dry_run": {"type": "boolean", "default": False, "description": "仅预览编译参数不实际执行"},
                    },
                    "additionalProperties": True,
                    "required": ["action"]
                }
            ),

            # ===== 知识库搜索/管理 ⭐⭐⭐ =====
            Tool(
                name="delphi_kb",
                description=TOOL_SHORT_DESC["delphi_kb"],
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["search", "stats", "build", "scan", "web", "read", "build_embedding"], "description": "操作类型（默认 search；若提供 url 则自动设为 web）: search=搜索, stats=统计, build=构建, scan=扫描文档, web=添加网页, read=读取, build_embedding=构建向量"},
                        "query": {"type": "string", "description": "搜索关键词（action=search时需要）"},
                        "kb_type": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty", "document", "example"], "default": "all", "description": "知识库类型: delphi=Delphi RTL/VCL/FMX 官方源码, project=当前项目源码, thirdparty=第三方组件库(如 FastReport/DevExpress), document=文档(Chm/网页), example=示例代码(Demo), all=所有"},
                        "search_type": {"type": "string", "enum": ["function", "procedure", "class", "record", "interface", "enum", "set", "helper", "type", "const", "resourcestring", "variable", "property", "method", "field", "event", "operator", "string", "dfm", "attribute", "unit", "semantic", "reference", "all"], "description": "搜索类型（action=search 时生效）"},
                        "top_k": {"type": "integer", "default": 200, "description": "最大返回结果数（默认200，最大500）"},
                        "project_path": {"type": "string", "description": "项目路径（搜索project/thirdparty知识库时需要，不传则自动检测目录下的.dproj/.dpr/.dpk）"},
                        "version": {"type": "string", "description": "Delphi版本（构建知识库时使用）"},
                        "async_mode": {"type": "boolean", "default": True, "description": "是否异步执行（build操作时生效，默认true）"},
                        "rebuild": {"type": "boolean", "default": False, "description": "是否强制重建（build操作时生效）"},
                        "incremental": {"type": "boolean", "default": False, "description": "是否增量更新（build操作时生效）"},
                        "build_thirdparty": {"type": "boolean", "default": True, "description": "构建项目KB时是否同时构建第三方库KB"},
                        "build_project": {"type": "boolean", "default": True, "description": "是否构建项目KB"},
                        "directory": {"type": "string", "description": "扫描目录（action=scan时使用，或build document时可以不传自动检测Delphi帮助目录）"},
                        "extensions": {"type": "array", "items": {"type": "string"}, "description": "文件扩展名过滤（action=scan/build时使用，如[\".chm\"]）"},
                        "content_type": {"type": "string", "description": "文档类型过滤（action=search kb_type=document时使用）"},
                        "url": {"type": "string", "description": "网页URL（提供 url 且未传 action 时自动触发 web 模式；或 read 时作为文档URL）"},
                        "doc_id": {"type": "string", "description": "文档ID（action=read时使用，与url二选一）"},
                        "file_path": {"type": "string", "description": "文件路径（action=read时使用）"},
                        "offset": {"type": "integer", "default": 0, "description": "读取偏移量（action=read时使用）"},
                        "limit": {"type": "integer", "default": 5000, "description": "读取字节数限制（action=read时使用）"},
                        "max_pages": {"type": "integer", "default": 100, "description": "最大抓取页数（build document KB时使用）"},
                        "max_depth": {"type": "integer", "default": 3, "description": "最大抓取深度（build document KB时使用）"},
                        "domain_filter": {"type": "string", "description": "域名过滤（build document KB时使用）"},
                        "url_pattern": {"type": "string", "description": "URL模式过滤（build document KB时使用）"},
                        "exclude": {"type": "array", "items": {"type": "string"}, "description": "排除目录列表（build document KB时使用）"},
                        "max_workers": {"type": "integer", "description": "最大工作进程数（action=scan时使用）"},
                        "show_progress": {"type": "boolean", "default": True, "description": "是否显示进度"},
                    }
                }
            ),

            # ===== Delphi 文件专用操作 — 读/写/格式化/备份管理 ⭐⭐⭐ =====
            Tool(
                name="delphi_file",
                description=TOOL_SHORT_DESC["delphi_file"],
                inputSchema={
                    "type": "object",
                    "required": ["action"],
                    "properties": {
                        # ---- 全局参数（所有 action 都可用）----
                        "action": {"type": "string", "enum": ["read", "write", "replace", "insert", "delete", "format", "backup", "encode", "uses", "fix_garbled", "grep"], "default": "read", "description": "操作类型: read=读文件, write=兼容写入, replace=替换(需old_content), insert=按锚点插入(需old_content), delete=删除(需old_content), format=格式化, backup=备份管理, encode=编码转换, uses=增删uses, fix_garbled=修复中文乱码, grep=正则搜索/替换(支持单文件/多文件目录递归/文件列表/多pattern OR搜索+多级过滤+dry_run预览)。路由规则：Delphi 文件必须用 delphi_file 读写/搜索/正则匹配+替换，不要用内置 Read/Edit/Write/grep。"},
                        "file_path": {"type": "string", "description": "目标 Delphi 文件路径，支持 .pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx；读取或修改这些文件都应路由到 delphi_file，即使只是读取也不要用内置 Read/Edit/Write/grep。grep 中与 path/files 三选一"},

                        # ---- [read] 参数 ----
                        "search_type": {"type": "string", "enum": ["path", "class", "function", "record"], "description": "[read] 读取模式: path/class/function/record"},
                        "type_name": {"type": "string", "description": "[read/class] 类名/接口名/枚举名"},
                        "class_name": {"type": "string", "description": "[read/class] 类名（与type_name二选一，兼容旧版）"},
                        "record_name": {"type": "string", "description": "[read/record] Record 类型名"},
                        "function_name": {"type": "string", "description": "[read/function] 函数/过程名"},
                        "start_line": {"type": "integer", "default": 1, "description": "[read] 起始行号(1-indexed inclusive)"},
                        "limit": {"type": "integer", "default": 500, "description": "[read] 最大返回行数(默认500，上限1000)"},
                        "show_line_numbers": {"type": "boolean", "default": False, "description": "[read] 显示 1-indexed 行号前缀"},
                        "end_line": {"type": "integer", "description": "[read] 结束行号(1-indexed inclusive)，默认 start_line+limit-1"},
                        "search_in": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty"], "default": "all", "description": "[read/class] 搜索范围 delphi/project/thirdparty/all"},
                        "project_path": {"type": "string", "description": "[read/class] 项目文件路径，用于搜索项目 KB"},

                        # ---- [write/replace/insert/delete] 参数 ----
                        # write 兼容旧语义；replace/insert/delete 提供更明确的安全编辑语义。
                        "edits": {
                            "type": "array",
                            "description": "[write/replace/insert/delete] 编辑列表。replace=替换范围，insert=以start_line为锚点按position插入，delete=删除范围。replace/insert/delete 对现有文件要求每个 edit 提供非空 old_content。",
                            "items": {
                                "type": "object",
                                "required": ["start_line"],
                                "properties": {
                                    "start_line": {"type": "integer", "description": "起始行号（1-indexed inclusive）"},
                                    "end_line": {"type": "integer", "description": "结束行号（1-indexed inclusive）；replace/delete 不传则到文件末尾；insert 不使用"},
                                    "position": {"type": "string", "enum": ["before", "after"], "default": "before", "description": "[insert] 插入位置: before=锚点行前, after=锚点行后"},
                                    "content": {"type": "string", "description": "replace/write 的替换内容；insert 的插入内容；delete 可省略。兼容 write 中空串=删除该区间"},
                                    "old_content": {"type": "string", "description": "将被替换/删除区间或 insert 锚点行的非空旧内容。写入前会忽略字符串外空白后比较；replace/insert/delete 对现有文件必填"},
                                    "description": {"type": "string", "description": "可选的文字描述，仅用于返回消息标记"}
                                }
                            }
                        },
                        "encoding": {"type": "string", "default": "auto", "description": "[read/write/replace/insert/delete/uses] 读/写编码: auto/utf-8/gbk/utf-16，默认 auto。read 时指定可覆盖自动检测结果"},
                        "auto_format": {"type": "boolean", "default": False, "description": "[write/replace/insert/delete] 写入后自动 pasfmt 格式化，返回偏移量已含格式变化"},
                        "backup": {"type": "boolean", "default": True, "description": "[write/replace/insert/delete/uses] 写入前自动备份到 __history（建议保持 true）"},
                        "dry_run": {"type": "boolean", "description": "[write/replace/insert/delete/format/encode/grep] true=只预览/检查不写盘；grep 替换默认 true，其他 action 默认 false"},
                        "force": {"type": "boolean", "default": False, "description": "[write/replace/insert/delete] 跳过重复检测和脏标记检查（默认 false 时检测到重复仅警告不阻断）"},
                        "allow_dirty": {"type": "boolean", "default": False, "description": "[write/replace/insert/delete] 跳过脏标记检查（默认 false）。优先为每个 edit 提供 old_content；仅确认行号准确时才设 true"},

                        # ---- [format] 参数 ----
                        "mode": {"type": "string", "enum": ["file", "code", "check"], "default": "file", "description": "[format] 模式: file/code/check"},
                        "code": {"type": "string", "description": "[format/code] 待格式化的代码文本"},
                        "config_path": {"type": "string", "description": "[format] pasfmt 配置文件路径(高级)"},
                        "uses_style": {"type": "string", "enum": ["compact", "pasfmt_default"], "description": "[format] uses风格: compact=一行, pasfmt_default=每行一个"},

                        # ---- [backup] 参数 ----
                        "backup_action": {"type": "string", "enum": ["create", "list", "restore"], "default": "create", "description": "[backup] 子操作: create/list/restore"},
                        "version": {"type": "integer", "description": "[backup/restore] 版本号，不传则恢复最新"},

                        # ---- [encode] 参数 ----
                        "from_encoding": {"type": "string", "default": "auto", "description": "[encode] 源编码（auto=自动检测，推荐始终用 auto；显式指定错误可能导致解码失败或乱码）"},
                        "to_encoding": {"type": "string", "description": "[encode] 目标编码: utf-8/utf-8-sig/gbk/utf-16/utf-16-le/utf-16-be/ansi"},

                        # ---- [uses] 参数 ----
                        "uses_action": {"type": "string", "enum": ["add", "remove"], "description": "[uses] add=添加, remove=删除"},
                        "unit_name": {"type": "string", "description": "[uses] 单元名，如 Vcl.Dialogs"},
                        "uses_section": {"type": "string", "enum": ["interface", "implementation"], "default": "interface", "description": "[uses] 所在区域: interface/implementation"},

                        # ---- [grep] 参数 ----
                        "pattern": {"type": "string", "description": "[grep] 单正则搜索模式（与 patterns 二选一），支持 /pattern/flags 语法"},
                        "patterns": {"type": "array", "items": {"type": "string"}, "description": "[grep] 多 pattern OR 搜索（与 pattern 二选一），每个元素支持 /pattern/flags 语法"},
                        "path": {"type": "string", "description": "[grep] 搜索目录（与 file_path/files 三选一），递归搜索目录下匹配文件"},
                        "include": {"type": "string", "description": "[grep] 文件包含 glob 模式（默认 **/*，仅 path 模式有效）"},
                        "exclude": {"type": "string", "description": "[grep] 文件排除 glob 模式（仅 path 模式有效）"},
                        "files": {"type": "array", "items": {"type": "string"}, "description": "[grep] 文件路径列表（与 file_path/path 三选一）"},
                        "filter_pattern": {"type": "string", "description": "[grep] 二级过滤模式（可选，同一行/匹配文本必须也匹配此模式）"},
                        "exclude_pattern": {"type": "string", "description": "[grep] 排除模式（可选，同一行/匹配文本必须不匹配此模式）"},
                        "replace": {"type": "string", "description": "[grep] 替换文本（可选，不传=搜索模式，传了=替换模式）"},
                        "context": {"type": "integer", "default": 0, "description": "[grep] 上下文行数（默认 0）"},
                        "count": {"type": "integer", "default": 200, "description": "[grep] 最大返回结果数（默认 200）"},
                    }
                }
            ),

            # ===== 组件管理 ⭐⭐ =====
            Tool(
                name="manage_component",
                description=TOOL_SHORT_DESC["manage_component"],
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["create", "add", "remove", "modify"], "default": "create",
                                   "description": "操作类型: create=生成DFM, add=添加组件, remove=删除组件, modify=修改属性"},
                        "target_dfm": {"type": "string", "description": "目标 DFM 文件路径（add/remove/modify 时必需）"},
                        "target_pas": {"type": "string", "description": "目标 PAS 文件路径（add/remove/modify 时可选，用于自动同步声明）"},
                        "component_name": {"type": "string", "description": "组件名称（remove/modify 时必需，指定操作的目标组件）"},
                        "parent_name": {"type": "string", "description": "父组件名称（add 时可选，默认添加到根组件下）"},
                        "new_component_class": {"type": "string", "description": "新组件类名（add 时必需，如 TButton）"},
                        "new_component_name": {"type": "string", "description": "新组件实例名（add 时可选，默认自动生成如 Button1）"},
                        "properties": {"type": "object", "additionalProperties": {"type": "string"},
                                       "description": "组件属性字典（add/modify 时使用，如 {\"Caption\": \"OK\", \"OnClick\": \"BtnClick\"}）"},
                        "dfm_text": {"type": "string", "description": "待添加的 DFM 文本片段（add 时可选，替代 new_component_class+properties）"},
                        "code": {"type": "string", "description": "[create 必需] Pascal 实现代码，必须包含 function CreateComponent(AOwner: TComponent): TComponent; 定义"},
                        "uses": {"type": "array", "items": {"type": "string"}, "description": "[create] 需引用的单元列表，如 [\"Vcl.Forms\", \"Vcl.StdCtrls\"]"},
                        "type_decl": {"type": "string", "description": "[create] 类型声明段（可选），用于声明 Form 类、事件桩等"},
                        "init_code": {"type": "string", "description": "[create] 初始化代码（可选），在 CreateComponent 前执行。自定义 Form 类需 RegisterClass。"},
                        "compile_timeout": {"type": "integer", "default": 60, "description": "编译超时秒数"},
                        "exec_timeout": {"type": "integer", "default": 15, "description": "执行超时秒数（组件创建代码可能耗时操作）"},
                    },
                    "required": ["action"]
                }
            ),

            # ===== 环境检查 ⭐⭐⭐ =====
            Tool(
                name="check_environment",
                description=TOOL_SHORT_DESC["check_environment"],
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["check", "detect", "install", "format_install"], "default": "check", "description": "操作类型: check=检查, detect=检测编译器, install=安装pasfmt, format_install=安装pasfmt RAD插件"},
                        "search_path": {"type": "string", "description": "额外搜索路径（action=detect时使用）"},
                        "install_dir": {"type": "string", "description": "安装目录（action=install/format_install时使用）"},
                        "delphi_version": {"type": "string", "default": "11", "description": "Delphi版本（action=format_install时使用，如\"11\"、\"12\"）"},
                    }
                }
            ),

            # ===== 异步任务管理 ⭐ =====
            Tool(
                name="async_task",
                description=TOOL_SHORT_DESC["async_task"],
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["start", "status", "result", "list", "cancel"], "description": "操作类型", "default": "list"},
                        "task_id": {"type": "string", "description": "任务ID（action=status/result/cancel时使用）"},
                        "long_poll_seconds": {"type": "integer", "default": 0, "minimum": 0, "maximum": 30, "description": "[status] 长轮询秒数(默认0=立即返回，建议≤30)"},
                        "task_type": {"type": "string", "description": "任务类型（action=start时使用），如: build_knowledge_base, build_thirdparty_knowledge_base, init_project_knowledge_base, build_document_knowledge_base, build_embedding"},
                        "task_params": {"type": "object", "description": "任务参数（action=start时使用，根据task_type不同而不同）"},
                        "show_progress": {"type": "boolean", "default": True, "description": "是否显示进度"},
                    }
                }
            ),

            # ===== 组件包管理 ⭐⭐ =====
            Tool(
                name="package",
                description=TOOL_SHORT_DESC["package"],
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["install", "list"], "default": "install", "description": "操作类型: install=编译安装组件包, list=列出已安装的组件包"},
                        "package_path": {"type": "string", "description": "[install] 包文件路径(.dproj/.dpk/.groupproj)"},
                        "target_platform": {"type": "string", "enum": ["win32", "win64"], "default": "win32", "description": "[install] 目标平台"},
                        "build_configuration": {"type": "string", "default": "Debug", "description": "[install] 构建配置(Debug/Release)"},
                        "timeout": {"type": "integer", "default": 300, "description": "[install] 超时时间(秒)"},
                        "install": {"type": "boolean", "default": True, "description": "[install] 是否自动安装到 IDE"},
                    },
                    "required": ["action"]
                }
            ),

            # ===== 编码规则（AI 必读）⭐⭐⭐ =====
            Tool(
                name="get_coding_rules",
                description=TOOL_SHORT_DESC["get_coding_rules"],
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目路径（可选），用于查找项目自定义的编码规则文件(CODING_RULES.mdc)"},
                        "section": {"type": "string", "description": "章节名称（可选），如 workflow/writing/review/safety/agent_rules/kb_search/format/compile/cleanup/kb_build。不传则返回工作流总览+章节索引"},
                    }
                }
            ),

            # ===== 代码托管平台统一工具 =====
            Tool(
                name="code_hosting",
                description=TOOL_SHORT_DESC["code_hosting"],
                inputSchema={
                    "type": "object",
                    "properties": {
                        "platform": {"type": "string", "enum": ["gitea", "github", "gitlab", "gitee", "gitcode"], "description": "平台类型（API 操作需要，Git 本地操作不需要）"},
                        "action": {"type": "string", "enum": ["create_token", "init_labels", "create_issue", "get_issue", "edit_issue", "set_labels", "close_issue", "add_comment", "list_issues", "create_pull", "get_pull", "list_pulls", "edit_pull", "merge_pull", "close_pull", "reopen_pull", "create_release", "get_release", "list_releases", "edit_release", "delete_release", "git_clone", "git_add", "git_commit", "git_push", "git_push_retry", "git_status", "git_diff", "git_show", "git_log", "git_fetch", "git_pull", "git_branch", "git_switch", "git_merge", "git_restore", "git_unstage", "git_stash", "git_tag"], "description": "操作类型: git_* 为 Git 本地操作（必须使用此工具，禁止用 bash 执行 git）；create_token/init_labels/create_issue 等为平台 API 操作"},
                        "base_url": {"type": "string", "description": "平台实例地址，如 https://code.qdac.cc:3000 (API 操作需要)"},
                        "token": {"type": "string", "description": "API 访问令牌 (API 操作需要)"},
                        "repo": {"type": "string", "description": "仓库名，格式 owner/repo (API 操作需要)"},
                        "issue_number": {"type": "integer", "description": "工单编号 (get_issue/edit_issue/set_labels/close_issue/add_comment 需要)"},
                        "pull_number": {"type": "integer", "description": "PR/MR 编号 (get_pull/edit_pull/merge_pull/close_pull/reopen_pull 需要)"},
                        "release_id": {"type": "integer", "description": "Release ID (GitHub/Gitea/Gitee get/edit/delete release 需要)"},
                        "title": {"type": "string", "description": "工单或 PR/MR 标题 (create_issue/create_pull 需要)"},
                        "body": {"type": "string", "description": "正文内容，支持 Markdown (create_issue/add_comment/create_pull/create_release 等使用)"},
                        "labels": {"type": "array", "items": {"type": "string"}, "description": "标签名称列表 (create_issue/edit_issue/set_labels 可选)"},
                        "comment": {"type": "string", "description": "关闭工单时的说明 (close_issue 可选)"},
                        "state": {"type": "string", "enum": ["open", "closed", "merged", "all"], "description": "工单/PR 过滤或修改状态；merged 仅用于 list_pulls 过滤，合并请用 merge_pull (list_issues/list_pulls/edit_issue/edit_pull 可选，默认 open)"},
                        "page": {"type": "integer", "description": "分页页码 (list_issues/list_pulls/list_releases 可选，默认 1)"},
                        "username": {"type": "string", "description": "用户名 (create_token 需要)"},
                        "password": {"type": "string", "description": "密码 (create_token 需要)"},
                        "token_name": {"type": "string", "description": "Token 名称 (create_token 可选，默认 delphi-mcp)"},
                        "source_branch": {"type": "string", "description": "源分支 (create_pull 需要，edit_pull 可选)"},
                        "target_branch": {"type": "string", "description": "目标分支 (create_pull 需要，edit_pull 可选)"},
                        "tag_name": {"type": "string", "description": "Release 标签名 (create_release 需要；GitLab/GitCode get/edit/delete release 需要)"},
                        "name": {"type": "string", "description": "Release 名称 (create_release/edit_release 可选)"},
                        "target_commitish": {"type": "string", "description": "GitHub/Gitea/Gitee Release 目标提交 (create_release 可选)"},
                        "draft": {"type": "boolean", "description": "GitHub/Gitea/Gitee Release 草稿标记 (create_release/edit_release 可选)"},
                        "prerelease": {"type": "boolean", "description": "GitHub/Gitea/Gitee Release 预发布标记 (create_release/edit_release 可选)"},
                        # Git 操作参数
                        "dir": {"type": "string", "description": "Git 仓库本地路径 (git_* 操作需要)"},
                        "repo_url": {"type": "string", "description": "远程仓库 URL (git_clone 需要)"},
                        "mirror": {"type": "string", "description": "GitHub 镜像源地址，如 https://hub.fastgit.xyz (git_clone 可选)"},
                        "branch": {"type": "string", "description": "分支名 (git_clone/git_push/git_fetch/git_pull/git_branch/git_switch/git_merge 可选)"},
                        "message": {"type": "string", "description": "提交信息 (git_commit 需要)"},
                        "files": {"type": "array", "items": {"type": "string"}, "description": "文件列表 (git_add/git_diff/git_log/git_restore/git_unstage/git_stash 可选/需要)"},
                        "ref": {"type": "string", "description": "提交/分支/范围引用 (git_diff/git_show/git_log/git_fetch/git_pull/git_tag 需要)"},
                        "staged": {"type": "boolean", "description": "查看 staged diff / restore staged 时使用"},
                        "stat": {"type": "boolean", "description": "输出 diff/show 统计信息"},
                        "name_only": {"type": "boolean", "description": "只输出文件名 (git_diff/git_show 可选)"},
                        "limit": {"type": "integer", "description": "输出截断或日志条数 (git_diff/git_show/git_log 可选)"},
                        "start_point": {"type": "string", "description": "新分支/新标签起点 (git_branch/git_switch/git_tag 可选)"},
                        "source": {"type": "string", "description": "git_restore 的 --source 引用 (可选)"},
                        "tag": {"type": "string", "description": "标签名 (git_tag 或 create_release/get_release/edit_release/delete_release 可选/需要)"},
                        "delete": {"type": "boolean", "description": "删除分支/标签 (git_branch/git_tag 可选)"},
                        "create": {"type": "boolean", "description": "创建并切换分支 (git_switch 可选)"},
                        "prune": {"type": "boolean", "description": "git_fetch 使用 --prune"},
                        "remote_branches": {"type": "boolean", "description": "git_branch 列出远程分支 (-a)"},
                        "rebase": {"type": "boolean", "description": "git pull 使用 rebase 模式"},
                        "ff_only": {"type": "boolean", "description": "git pull / git merge 使用 ff-only"},
                        "no_commit": {"type": "boolean", "description": "git merge 使用 no-commit"},
                        "async_mode": {"type": "boolean", "description": "git_fetch/git_pull/git_merge 使用后台任务执行，返回 task_id 后配合 async_task 查询"},
                        "include_untracked": {"type": "boolean", "description": "git stash push 包含未跟踪文件"},
                        "op": {"type": "string", "description": "git stash 操作: push/list/pop/apply/drop/show"},
                        "remote": {"type": "string", "description": "远程名称 (git_push/git_push_retry 可选，默认 origin)"},
                        "retry_interval": {"type": "integer", "description": "重试间隔秒数 (git_push_retry 可选，默认 300)"},
                        "max_retries": {"type": "integer", "description": "最大重试次数 (git_push_retry 可选，默认 12)"},
                        "task_id": {"type": "string", "description": "异步任务ID (配合 async_task 工具查询)"},
                    },
                    "required": ["action"]
                }
            ),

            # ===== 工具帮助（按需获取详细文档）=====
            Tool(
                name="tool_help",
                description=TOOL_SHORT_DESC["tool_help"],
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "enum": TOOL_NAMES,
                            "description": "要查询的工具名",
                        },
                        "action": {
                            "type": "string",
                            "description": "可选，指定 action 名称时只返回该 action 的参数说明，减少无关信息干扰",
                        },
                    },
                    "required": ["tool_name"],
                }
            ),

            # ===== Daofy 自身更新管理 =====
            Tool(
                name="daofy_update",
                description="检查 Daofy 版本更新、执行 git pull 更新。发现新版本时智能提示中会自动通知。"
                    " check/update 后台异步执行（类似 code_hosting），返回 task_id 配合 async_task 查进度。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["check", "check_retry", "update", "update_retry", "version"],
                            "default": "check",
                            "description": "check=快速检查(失败后自动后台重试), check_retry=强制后台重试(返回task_id), update=后台git pull, update_retry=后台自动重试git pull(返回task_id), version=当前版本号",
                        },
                        "retry_interval": {
                            "type": "integer",
                            "description": "重试间隔秒数 (update_retry 可选，默认 60)",
                        },
                        "max_retries": {
                            "type": "integer",
                            "description": "最大重试次数 (update_retry 可选，默认 10)",
                        },
                        "task_id": {
                            "type": "string",
                            "description": "异步任务ID (配合 async_task 工具查询状态/结果)",
                        },
                    },
                    "required": ["action"],
                }
            ),

            # ===== 经验记忆管理 =====
            Tool(
                name="experience",
                description=TOOL_SHORT_DESC["experience"],
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["save", "search", "get", "list", "update", "merge", "prune", "delete", "rebuild_embedding"],
                            "description": "操作类型: save=保存经验(自动去重), search=语义搜索, get=查看详情, list=浏览列表, update=更新, merge=合并多条, prune=列出低价值待清理条目, delete=删除, rebuild_embedding=重建缺失向量(需模型已加载)",
                        },
                        "problem": {"type": "string", "description": "[save] 问题描述"},
                        "solution": {"type": "string", "description": "[save] 解决步骤"},
                        "tools_used": {"type": "array", "items": {"type": "string"}, "description": "[save] 用到的工具列表"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "[save/search/list] 标签过滤"},
                        "context": {"type": "object", "description": "[save] 上下文信息"},
                        "query": {"type": "string", "description": "[search] 搜索关键词"},
                        "top_k": {"type": "integer", "default": 5, "description": "[search] 返回条数"},
                        "id": {"type": "string", "description": "[get/update/delete] 经验ID"},
                        "ids": {"type": "array", "items": {"type": "string"}, "description": "[merge] 待合并的经验ID列表（至少2个）"},
                        "keep": {"type": "string", "description": "[merge] 保留的目标ID（可选，不传则创建新记录）"},
                        "sort_by": {"type": "string", "default": "updated_at", "enum": ["updated_at", "created_at", "hit_count", "score"], "description": "[list] 排序字段"},
                        "limit": {"type": "integer", "default": 20, "description": "[list/prune] 返回条数"},
                        "force": {"type": "boolean", "default": False, "description": "[save] 发现高相似度经验时仍强制新保存（跳过 >0.7 去重提醒层）"},
                    },
                    "required": ["action"],
                }
            ),

            # ===== 软著文档生成 =====
            Tool(
                name="generate_copyright",
                description=TOOL_SHORT_DESC.get("generate_copyright", "生成软著文档"),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["generate", "validate", "update_config", "status", "list", "generate_content", "audit"],
                            "default": "generate",
                            "description": "操作类型: generate=生成文档; validate=检查配置; update_config=更新配置; status=检查环境; list=列出已生成; generate_content=生成草稿; audit=审计草稿",
                        },
                        "config": {
                            "type": "object",
                            "description": "配置更新（仅 action=update_config 时必需）",
                        },
                        "doc_type": {
                            "type": "string",
                            "enum": ["all", "source", "manual", "summary"],
                            "default": "all",
                            "description": "文档类型（仅 action=generate 时生效）",
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "输出目录（可选，默认 docs/copyright）",
                        },
                        "project_path": {
                            "type": "string",
                            "description": "目标项目路径（config 存于 <project_path>/docs/copyright/copyright.json），不传时默认当前工作目录。",
                        },
                    },
                    "required": ["action"],
                }
            ),

            # ===== Delphi 自动化测试（GUI+控制台） =====
            Tool(
                name="automate_delphi",
                description=TOOL_SHORT_DESC.get("automate_delphi", "Delphi 自动化测试(GUI+控制台)"),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["auto", "gui", "console", "prepare"],
                            "default": "auto",
                            "description": "模式: auto=自动检测(PE头), gui=命名管道GUI自动化(需链接DaofyAutomation单元), console=subprocess控制台交互(无需Delphi端改造), prepare=将DaofyAutomation路径注册到Delphi全局搜索路径",
                        },
                        "app_path": {
                            "type": "string",
                            "description": "Delphi exe 文件路径",
                        },
                        # ── GUI 模式参数 ──
                        "script": {
                            "anyOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "object"}},
                                {
                                    "type": "object",
                                    "properties": {
                                        "steps": {"type": "array", "items": {"type": "object"}}
                                    },
                                    "required": ["steps"],
                                }
                            ],
                            "description": "[gui] JSON 脚本（JSON 字符串、文件路径、命令对象数组，或包含 steps 的完整脚本对象）。"
                                           " 推荐格式: {\"test_name\":\"smoke\",\"steps\":[{\"cmd\":\"goto\",\"target\":\"TMainForm\"}, ...]}"
                                           " 简写格式: [{\"cmd\":\"goto\",\"target\":\"TMainForm\",\"capture\":\"main_001\"}, ...]"
                                            " 协议: JSON请求/响应，cmd字段支持: goto/click/rclick/dblclick/hover/move/drag/type/key/wait/waitfor/capture/listwnd/dumpstate/formsum/dlgscan/dlgclick/msgscan/msgclick/msgclose/dlgfile/rcall/rinspect/rget/rset/snapdir/exit/callgraph/callgraph_diff/callgraph_path/callgraph_impact/callgraph_select_tests/callgraph_failure_diag/callgraph_boundary_check/callgraph_refactor_check/callgraph_orphan_candidates/callgraph_explain_exception。async(click/rclick/dblclick/hover/move/drag/msgclick/dlgclick/rcall/key/rset/type)立即返回ACK；sync(goto/capture/waitfor/wait/dumpstate/listwnd/dlgscan/msgscan/msgclose/dlgfile/snapdir/exit/rget/rinspect/callgraph/callgraph_diff/callgraph_path/callgraph_impact/callgraph_select_tests/callgraph_failure_diag/callgraph_boundary_check/callgraph_refactor_check/callgraph_orphan_candidates/callgraph_explain_exception)阻塞等待。callgraph 为可选诊断命令，支持 direction=callees/callers、project_only、exclude_prefixes、include_prefixes、edge_limit，并返回 edge_count/returned_count/truncated，边包含 call_addr/call_file/call_line/category/from_category/to_category；callgraph_path 支持 source/target/max_depth/max_paths/include_prefixes，返回 found 和 paths；callgraph_diff 默认 compare_by=name，可选 addr/full；callgraph_impact 为 Python 侧影响分析命令，支持 functions/targets 或 file+line/locations，批量查询 callers；其他 callgraph_* 为 Python 侧用途层命令；Delphi 端需额外 uses DaofyAutomation.CallGraph 并生成 Detailed .map。",
                        },
                        "snapshots_dir": {
                            "type": "string",
                            "description": "[gui] 截图输出目录（可选，默认 docs/copyright/snapshots）",
                        },
                        "wait_timeout": {
                            "type": "number",
                            "default": 10,
                            "description": "[gui] 等待 Delphi 管道就绪的超时秒数（默认 10s）",
                        },
                        # ── Console 模式参数 ──
                        "input": {
                            "type": "string",
                            "default": "",
                            "description": "[console] 发送到 stdin 的文本",
                        },
                        "expect": {
                            "type": "string",
                            "default": "",
                            "description": "[console] 等待的 stdout 正则模式（expect 式等待，匹配即返回）",
                        },
                        "timeout": {
                            "type": "number",
                            "default": 30,
                            "description": "[console] 超时秒数（默认 30s）",
                        },
                        "args": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "[console] 额外命令行参数",
                        },
                        # ── 公共参数 ──
                        "env": {
                            "type": "object",
                            "additionalProperties": {
                                "anyOf": [
                                    {"type": "string"},
                                    {"type": "number"},
                                    {"type": "boolean"},
                                    {"type": "null"},
                                ]
                            },
                            "description": "[gui/console] Temporary environment variables for the tested child process. Values are not persisted; null unsets a variable. GUI scripts may also declare top-level env/environment.",
                        },
                        "keep_alive": {
                            "type": "boolean",
                            "default": False,
                            "description": "True=执行完后保持进程运行供后续复用，False=执行完退出（默认）",
                        },
                        "stop_on_failure": {
                            "type": "boolean",
                            "default": True,
                            "description": "[gui] True=首个失败后停止执行后续依赖步骤，并在报告中标记 skipped；False=继续执行全部步骤",
                        },
                    },
                    "required": [],
                }
            ),

            # ===== OCR 图像文字识别（可选功能）⭐ =====
            Tool(
                name="ocr",
                description=(
                    "图像分析: recognize(文字识别)/detect(文本框)/diff(截图对比)/"
                    "color(颜色分析)/match(图标匹配)/status。"
                    " 可选功能(pip install daofy-for-delphi[ocr])。"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["recognize", "detect", "status",
                                     "diff", "color", "match"],
                            "default": "recognize",
                            "description": "recognize/detect/status/diff/color/match",
                        },
                        "image_path": {
                            "type": "string",
                            "description": "[recognize/detect/color/match] 图片路径",
                        },
                        "baseline": {
                            "type": "string",
                            "description": "[diff] 基线截图路径",
                        },
                        "current": {
                            "type": "string",
                            "description": "[diff] 当前截图路径",
                        },
                        "threshold": {
                            "type": "number",
                            "description": "[diff]像素差异阈值0-255(默认10) / [match]匹配阈值0-1(默认0.8)",
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "[diff] 差异图输出目录",
                        },
                        "region": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "[color] 分析区域 [x,y,w,h]",
                        },
                        "template_path": {
                            "type": "string",
                            "description": "[match] 模板图标路径",
                        },
                    },
                    "required": [],
                }
            ),

            # ===== Delphi RTTI 桥接 ⭐ =====
            Tool(
                name="delphi_rtti",
                description=(
                    "Delphi RTTI 桥接 — 通过 RTTI 发现和调用 Delphi 应用程序的运行时能力。\n"
                    "三步法：\n"
                    "① discover(app_path, class_name?) → 扫描 RTTI 暴露的方法和参数 Schema\n"
                    "② call(app_path, class_name, method, params) → 调用方法\n"
                    "③ guide → 返回完整使用指南\n"
                    "💡 首次使用先 action='guide' 获取完整说明。"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["guide", "discover", "call"],
                            "description": "操作类型: guide=使用指南, discover=发现能力, call=调用方法",
                        },
                        "app_path": {
                            "type": "string",
                            "description": "Delphi exe 文件路径（discover/call 需要，guide 不需要）",
                        },
                        "class_name": {
                            "type": "string",
                            "description": "目标类名（discover/call），为空则扫描所有类",
                        },
                        "method": {
                            "type": "string",
                            "description": "方法名（call 时需要）",
                        },
                        "params": {
                            "type": "object",
                            "description": "方法参数（call 时需要），如 {\"customerName\": \"张三\"}",
                        },
                        "keep_alive": {
                            "type": "boolean",
                            "default": False,
                            "description": "是否保持进程运行供后续复用",
                        },
                        "force": {
                            "type": "boolean",
                            "default": False,
                            "description": "是否强制刷新发现缓存",
                        },
                    },
                    "required": ["action"],
                }
            ),
        ]

    # ============================================================
    # 参数类型校验 — MCP 客户端可能传错类型（如 string 代替 bool）
    # ============================================================

    def _coerce_bool(val, default: bool = False) -> bool:
        """将任意输入安全转换为 bool。"""
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ('1', 'true', 'yes', 'on')
        if isinstance(val, (int, float)):
            return val != 0
        return default

    def _coerce_int(val, default: int = 0, minv=None, maxv=None) -> int:
        """将任意输入安全转换为 int，支持范围裁剪。"""
        if isinstance(val, int):
            return val
        if isinstance(val, str):
            try:
                v = int(val)
            except (ValueError, TypeError):
                return default
            if minv is not None:
                v = max(v, minv)
            if maxv is not None:
                v = min(v, maxv)
            return v
        if isinstance(val, float):
            v = int(val)
            if minv is not None:
                v = max(v, minv)
            if maxv is not None:
                v = min(v, maxv)
            return v
        return default

    def _coerce_list(val, default=None):
        """将任意输入安全转换为 list。"""
        if isinstance(val, list):
            return val
        if isinstance(val, (str, bytes)):
            return [val]
        if val is None:
            return default or []
        return default or []

    # ============================================================
    # 工具分发 — 将工具名映射到对应的 handler 函数
    async def _handle_project_tool(arguments: dict) -> Any:
        return await _handle_project(**arguments)

    async def _handle_delphi_kb(arguments: dict) -> Any:
        default_action = "web" if arguments.get("url") else "search"
        action = arguments.get("action", default_action)
        kb_type = arguments.get("kb_type", "all")
        if action == "search":
            return await doc_tools.search_documents(arguments) if kb_type == "document" else await kb_tools.search_knowledge(arguments)
        elif action == "stats":
            return await doc_tools.get_document_statistics(arguments) if kb_type == "document" else await kb_tools.get_unified_knowledge_stats(arguments)
        elif action == "build":
            async_mode = _coerce_bool(arguments.get("async_mode"), True)
            if not async_mode:
                return await kb_tools.build_unified_knowledge_base(arguments)
            version = arguments.get("version")
            rebuild = _coerce_bool(arguments.get("rebuild"), False)
            kb_type_map = {"all": "build_knowledge_base", "delphi": "build_knowledge_base",
                           "thirdparty": "build_thirdparty_knowledge_base", "project": "init_project_knowledge_base",
                           "document": "build_document_knowledge_base"}
            task_type = kb_type_map.get(kb_type, "build_knowledge_base")
            incremental = arguments.get("incremental", False)
            if task_type == "build_document_knowledge_base":
                directory = arguments.get("directory")
                start_url = arguments.get("start_url")
                urls = arguments.get("urls", [])
                # 只有当没有指定 start_url 和 urls（纯目录扫描）时才自动检测帮助目录
                if not directory and not start_url and not urls:
                    detected = _auto_detect_delphi_help_dir()
                    if detected:
                        directory = detected
                        logger.info(f"自动检测到 Delphi 帮助目录: {directory}")
                    else:
                        logger.warning("未提供 directory 且未检测到 Delphi 帮助目录")

                # 文档知识库重建确认：force_rebuild 会清除现有所有文档
                if rebuild:
                    try:
                        _scanner = doc_tools._get_scanner()
                        _stats = _scanner.get_statistics()
                        _total = _stats.get('total_documents', 0)
                        if _total > 0:
                            _confirm = _coerce_bool(arguments.get("confirm"), False)
                            if not _confirm:
                                _msg = [f"⚠️ **确认重建文档知识库**\n\n当前知识库包含 **{_total}** 篇文档：\n"]
                                _by_type = _stats.get('by_type', {})
                                if _by_type:
                                    _msg.append("按类型：\n")
                                    for _t, _c in sorted(_by_type.items(), key=lambda x: x[1], reverse=True):
                                        _msg.append(f"  - {_t}: {_c}\n")
                                _by_ext = _stats.get('by_extension', {})
                                if _by_ext:
                                    _msg.append("按扩展名：\n")
                                    for _e, _c in sorted(_by_ext.items(), key=lambda x: x[1], reverse=True):
                                        _msg.append(f"  - {_e}: {_c}\n")
                                _msg.append(
                                    "\n`rebuild=True` 将 **清除以上所有文档** 后重新构建，原有内容不可恢复。\n\n"
                                    "如需保留旧内容，请：\n"
                                    "  1. 在本次构建参数中同时包含旧的文档源（如多个 URL 或目录），或\n"
                                    "  2. 移除 `rebuild=True` 改用增量添加\n\n"
                                    "**确认继续请添加参数 `confirm=True`**"
                                )
                                return CallToolResult(content=[TextContent(type="text", text="".join(_msg))])
                    except Exception as _e:
                        logger.warning(f"检查文档知识库状态失败，跳过确认: {_e}")

                task_params = {"urls": arguments.get("urls", []), "directory": directory,
                               "extensions": arguments.get("extensions", [".chm"]),
                               "start_url": arguments.get("start_url"), "max_pages": arguments.get("max_pages", 100),
                               "max_depth": arguments.get("max_depth", 3), "domain_filter": arguments.get("domain_filter"),
                               "url_pattern": arguments.get("url_pattern"), "exclude": arguments.get("exclude"),
                               "rebuild": rebuild}
            elif task_type == "init_project_knowledge_base":
                resolved_path = _resolve_project_path(arguments.get("project_path"))
                task_params = {"project_path": resolved_path, "version": version,
                               "rebuild": rebuild, "build_thirdparty": arguments.get("build_thirdparty", True),
                               "build_project": arguments.get("build_project", True)}
            else:
                task_params = {"version": version, "rebuild": rebuild, "incremental": incremental}
            return await async_tools.start_async_task({"task_type": task_type, "task_params": task_params,
                                                         "show_progress": arguments.get("show_progress", True),
                                                         "_on_complete": arguments.get("_on_complete")})
        elif action == "build_embedding":
            pp = _resolve_project_path(arguments.get("project_path"))
            if not pp:
                return {"error": "未检测到项目路径"}
            return await async_tools.start_async_task({"task_type": "build_embedding", "task_params": {"project_path": pp},
                                                        "show_progress": True,
                                                        "_on_complete": arguments.get("_on_complete")})
        elif action == "scan":
            return await doc_tools.scan_documents(arguments) if kb_type == "document" else {"error": "action=scan 仅支持 kb_type=document"}
        elif action == "web":
            return await doc_tools.add_web_document(arguments) if kb_type == "document" else {"error": "action=web 仅支持 kb_type=document"}
        elif action == "read":
            if arguments.get("url") or arguments.get("doc_id"):
                return await doc_tools.read_document(arguments)
            elif arguments.get("file_path"):
                return await read_source_file(arguments)
            return {"error": "action=read 需要 url/doc_id 或 file_path 参数"}
        return {"error": f"未知action: {action}"}

    async def _handle_file_tool(arguments: dict) -> Any:
        return await file_tool.handle_file_tool(arguments)

    async def _handle_manage_component(arguments: dict) -> Any:
        # manage_component_mod 是函数（被 __init__.py re-export 了），直接调用
        return await manage_component_mod(
            action=arguments.get("action", "create"),
            target_dfm=arguments.get("target_dfm"),
            target_pas=arguments.get("target_pas"),
            component_name=arguments.get("component_name"),
            parent_name=arguments.get("parent_name"),
            new_component_class=arguments.get("new_component_class"),
            new_component_name=arguments.get("new_component_name"),
            properties=arguments.get("properties"),
            dfm_text=arguments.get("dfm_text"),
            code=arguments.get("code", ""),
            uses=arguments.get("uses"),
            type_decl=arguments.get("type_decl", ""),
            init_code=arguments.get("init_code", ""),
            compile_timeout=arguments.get("compile_timeout", 60),
            exec_timeout=arguments.get("exec_timeout", 15),
        )

    async def _handle_check_environment(arguments: dict) -> Any:
        action = arguments.get("action", "check")
        if action == "detect":
            return await search_compilers(search_path=arguments.get("search_path"))
        elif action == "check":
            return await check_environment()
        elif action == "install":
            return await pasfmt.download_and_install_pasfmt(install_dir=arguments.get("install_dir"))
        elif action == "format_install":
            return await pasfmt.download_and_install_pasfmt_rad(delphi_version=arguments.get("delphi_version", "11"), install_dir=arguments.get("install_dir"))
        return {"error": f"未知action: {action}"}

    async def _handle_async_task(arguments: dict) -> Any:
        action = arguments.get("action", "list")
        handlers = {"start": async_tools.start_async_task, "status": async_tools.get_task_status,
                     "result": async_tools.get_task_result, "list": async_tools.list_tasks,
                     "cancel": async_tools.cancel_task}
        handler = handlers.get(action)
        if handler:
            return await handler(arguments)
        return {"error": f"未知action: {action}"}

    async def _handle_package(arguments: dict) -> Any:
        return await handle_package(**arguments)

    async def _handle_get_coding_rules(arguments: dict) -> Any:
        return await _get_coding_rules(project_path=arguments.get("project_path"), section=arguments.get("section"))

    async def _handle_code_hosting(arguments: dict) -> Any:
        try:
            if "action" not in arguments:
                return {"status": "failed", "message": "missing required parameter: action"}
            # 使用 asyncio.to_thread 避免同步 HTTP 阻塞事件循环
            return await asyncio.to_thread(code_hosting, **arguments)
        except Exception as e:
            logger.error(f"code_hosting 执行失败: {e}", exc_info=True)
            return {"status": "failed", "message": f"code_hosting failed: {e}"}

    async def _handle_tool_help(arguments: dict) -> Any:
        return get_tool_help(
            tool_name=arguments.get("tool_name", ""),
            action=arguments.get("action", ""),
        )

    async def _handle_experience(arguments: dict) -> dict:
        """处理 experience 工具调用，带 asyncio 超时保护（30s）。"""
        import asyncio
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_experience, **arguments),
                timeout=TIMEOUT_EXPERIENCE_TOOL,
            )
            return result
        except asyncio.TimeoutError:
            return {
                "status": "failed",
                "message": "experience 操作超时（30s），可能是 embedding 模型加载/下载耗时过长。"
                    " 建议：先调用 delphi_kb(action=build_embedding) 预加载模型，"
                    " 再使用 experience 的语义搜索功能。",
            }
        except Exception as e:
            return {"status": "failed", "message": f"experience failed: {e}"}

    async def _handle_daofy_update(arguments: dict) -> dict:
        """处理 daofy_update 工具调用（类似 code_hosting 模式：后台异步+定时重试）。"""
        action = arguments.get("action", "check")
        task_manager = get_task_manager()

        # ── version: 同步返回，无需网络 ──
        if action == "version":
            install_type = "git" if updater.is_git_installation() else "pip"
            return {
                "version": updater.get_current_version(),
                "install_type": install_type,
                "python": sys.version,
            }

        # ── check: 先快速尝试（同步），失败后提交后台重试任务 ──
        if action == "check":
            # 1. 优先检查缓存
            cached = updater.get_cached_update_result()
            if cached is not None:
                install_type = "git" if updater.is_git_installation() else "pip"
                cached["install_type"] = install_type
                status_msg = (
                    f"发现新版本 v{cached['latest']}！（当前 v{cached['current']}）"
                    if cached.get("update_available")
                    else f"当前已是最新版本: v{cached['current']}"
                )
                return {**cached, "message": status_msg, "cache_hit": True}

            # 2. 快速同步尝试
            quick = await asyncio.get_running_loop().run_in_executor(
                None, updater.check_for_update
            )
            if quick is not None:
                install_type = "git" if updater.is_git_installation() else "pip"
                quick["install_type"] = install_type
                if quick["update_available"]:
                    if install_type == "git":
                        quick["message"] = (
                            f"发现新版本 v{quick['latest']}！"
                            f" 当前版本 v{quick['current']}。"
                            f" 建议: daofy_update(action='update') 执行 git pull 更新。"
                        )
                    else:
                        quick["message"] = (
                            f"发现新版本 v{quick['latest']}！"
                            f" 当前版本 v{quick['current']}。"
                            f" 请运行: pip install --upgrade daofy-for-delphi"
                        )
                else:
                    quick["message"] = f"当前已是最新版本: v{quick['current']}"
                return quick

            # 3. 快速尝试失败，提交后台自动重试任务（类似 code_hosting git_push_retry）
            logger.info("版本检查快速尝试失败，提交后台自动重试任务...")
            on_complete = arguments.get('_on_complete')
            task_id = task_manager.submit_task(
                name="version_check_retry",
                func=updater.check_for_update_retry,
                on_complete=on_complete,
                dedup_key="version_check_retry",
            )
            return {
                "task_id": task_id,
                "status": "async",
                "message": (
                    "快速检查失败（网络不可达），已提交后台自动重试任务。\n"
                    f"  任务ID: {task_id}\n"
                    f"  重试间隔: {updater.RETRY_INTERVAL}s | 最多 {updater.MAX_RETRIES} 次\n"
                    "  使用 async_task(action=status, task_id=...) 查看进度。"
                ),
            }

        # ── check_retry: 强制提交后台自动重试任务（返回 task_id） ──
        if action == "check_retry":
            on_complete = arguments.get('_on_complete')
            task_id = task_manager.submit_task(
                name="version_check_retry",
                func=updater.check_for_update_retry,
                on_complete=on_complete,
                dedup_key="version_check_retry",
            )
            return {
                "task_id": task_id,
                "status": "async",
                "message": (
                    "后台版本检查任务已提交。\n"
                    f"  任务ID: {task_id}\n"
                    f"  重试间隔: {updater.RETRY_INTERVAL}s | 最多 {updater.MAX_RETRIES} 次\n"
                    "  使用 async_task(action=status, task_id=...) 查看进度。"
                ),
            }

        # ── update / update_retry: 后台 git pull 更新 ──
        if action in ("update", "update_retry"):
            if not updater.is_git_installation():
                return {
                    "success": False,
                    "message": (
                        "当前为 pip 安装模式，不支持 git pull 更新。\n"
                        "请手动运行: pip install --upgrade daofy-for-delphi"
                    ),
                }

            on_complete = arguments.get('_on_complete')
            retry_interval = int(arguments.get("retry_interval", 60))
            max_retries = int(arguments.get("max_retries", 10))

            if action == "update_retry":
                # 自定义 retry 参数
                orig_interval = updater.UPDATE_RETRY_INTERVAL
                orig_max = updater.UPDATE_MAX_RETRIES
                updater.UPDATE_RETRY_INTERVAL = retry_interval
                updater.UPDATE_MAX_RETRIES = max_retries
                try:
                    task_id = task_manager.submit_task(
                        name="git_update_retry",
                        func=updater._do_retry_update,
                        on_complete=on_complete,
                        dedup_key="git_update_retry",
                    )
                finally:
                    updater.UPDATE_RETRY_INTERVAL = orig_interval
                    updater.UPDATE_MAX_RETRIES = orig_max
                eta_min = (retry_interval * max_retries) // 60
                return {
                    "task_id": task_id,
                    "status": "async",
                    "message": (
                        "后台自动重试 git pull 更新任务已提交。\n"
                        f"  任务ID: {task_id}\n"
                        f"  重试间隔: {retry_interval}s | 最多 {max_retries} 次 | 预计最长 ~{eta_min}min\n"
                        "  使用 async_task(action=status, task_id=...) 查看进度。"
                    ),
                }

            # update（单次）
            task_id = task_manager.submit_task(
                name="git_update",
                func=updater.git_pull_update_sync,
                on_complete=on_complete,
            )
            return {
                "task_id": task_id,
                "status": "async",
                "message": (
                    "后台 git pull 更新任务已提交。\n"
                    f"  任务ID: {task_id}\n"
                    "  使用 async_task(action=status, task_id=...) 查看进度。"
                ),
            }

        return {"error": f"未知 action: {action}"}

    async def _handle_generate_copyright(arguments: dict) -> dict:
        """处理 generate_copyright 工具调用。"""
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_generate_copyright, **arguments),
                timeout=TIMEOUT_GENERATE_COPYRIGHT,
            )
            return result
        except asyncio.TimeoutError:
            return {"status": "failed", "message": "generate_copyright 执行超时（300s）"}
        except Exception as e:
            return {"status": "failed", "message": f"generate_copyright failed: {e}"}

    def _auto_paths() -> list[str]:
        """返回需要注册到 Delphi 搜索路径的目录列表。"""
        root = Path(__file__).resolve().parent.parent
        return [
            str(root / "tools" / "auto"),
            str(root / "tools" / "stacktrace"),
        ]

    def _register_path_for_platform(key, reg_path: str, path: str, platform: str, results: list[dict]):
        """将单个路径注册到指定平台的 Delphi 搜索路径。"""
        try:
            search_path, _ = winreg.QueryValueEx(key, "Search Path")
            paths = search_path.split(";")

            if path in paths:
                results.append({
                    "platform": platform, "status": "already_present",
                    "path": path,
                })
            else:
                clean_path = search_path.rstrip(";")
                new_path = clean_path + ";" + path if clean_path else path
                winreg.SetValueEx(key, "Search Path", 0, winreg.REG_SZ, new_path)
                results.append({
                    "platform": platform, "status": "added",
                    "path": path,
                })
        except Exception as e:
            results.append({
                "platform": platform, "status": "error",
                "path": path,
                "message": f"写入搜索路径失败: {e}",
            })

    def _register_daofy_auto(version: str, platforms: list[str] | None = None) -> list[dict]:
        """将 DaofyAutomation + StackTrace 路径写入 Delphi 全局搜索路径（注册表）。"""
        if platforms is None:
            platforms = ["Win32", "Win64"]

        reg_paths = _auto_paths()
        results: list[dict] = []

        for platform in platforms:
            reg_path = f"{REG_KEY_EMBARCADERO_BDS}\\{version}\\Library\\{platform}"
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    reg_path,
                    0,
                    winreg.KEY_READ | winreg.KEY_WRITE,
                )
            except FileNotFoundError:
                for p in reg_paths:
                    results.append({
                        "platform": platform, "status": "skipped",
                        "path": p,
                        "message": f"注册表路径不存在: HKCU\\{reg_path}",
                    })
                continue
            except PermissionError:
                for p in reg_paths:
                    results.append({
                        "platform": platform, "status": "error",
                        "path": p,
                        "message": "权限不足，无法写入注册表",
                    })
                continue
            except Exception as e:
                for p in reg_paths:
                    results.append({
                        "platform": platform, "status": "error",
                        "path": p,
                        "message": f"打开注册表失败: {e}",
                    })
                continue

            try:
                for p in reg_paths:
                    _register_path_for_platform(key, reg_path, p, platform, results)
            finally:
                try:
                    winreg.CloseKey(key)
                except Exception:
                    pass

        return results

    async def _handle_automate_delphi(arguments: dict) -> dict:
        """处理 automate_delphi 工具调用（自动检测或按 action 路由）。"""
        import asyncio
        requested_action = arguments.get("action", "auto")
        action = requested_action

        # ── prepare：注册 DaofyAutomation 到 Delphi 全局搜索路径 ──
        if action == "prepare":
            try:
                from src.utils.delphi_env import get_delphi_version as _get_dv
                version = _get_dv()
            except ImportError:
                version = None

            if not version:
                return {
                    "action": "prepare", "status": "error",
                    "message": "未检测到已安装的 Delphi 编译器",
                }

            results = _register_daofy_auto(version)
            added = sum(1 for r in results if r["status"] == "added")
            already = sum(1 for r in results if r["status"] == "already_present")
            errors = sum(1 for r in results if r["status"] == "error")
            skipped = sum(1 for r in results if r["status"] == "skipped")

            return {
                "action": "prepare",
                "delphi_version": version,
                "daofy_auto_paths": _auto_paths(),
                "results": results,
                "status": "success" if errors == 0 else "partial",
                "message": (
                    f"Delphi {version}: 新增 {added} 个平台, "
                    f"已存在 {already} 个平台"
                    + (f", {skipped} 个跳过" if skipped else "")
                    + (f", {errors} 个失败" if errors else "")
                ),
            }

        app_path = arguments.get("app_path", "")
        keep_alive = _coerce_bool(arguments.get("keep_alive", False))
        stop_on_failure = _coerce_bool(arguments.get("stop_on_failure", True))
        env = arguments.get("env", None)
        subsystem = None

        if not app_path:
            return {"status": "error", "message": "缺少必需参数: app_path"}

        # auto 检测：读 PE 头 Subsystem
        if action == "auto":
            subsystem = _detect_exe_subsystem(app_path)
            if subsystem == IMAGE_SUBSYSTEM_WINDOWS_CUI:
                action = "console"
            elif subsystem == IMAGE_SUBSYSTEM_WINDOWS_GUI:
                action = "gui"
            else:
                # 无法检测时默认 gui（保持兼容）
                action = "gui"

        if action == "gui":
            script = arguments.get("script", "")
            snapshots_dir = arguments.get("snapshots_dir", "")
            wait_timeout = arguments.get("wait_timeout", 10)

            if not script:
                return {"status": "error", "message": "gui 模式缺少必需参数: script"}

            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(_execute_automation,
                                      action="gui",
                                      app_path=app_path,
                                      script=script,
                                      snapshots_dir=snapshots_dir,
                                      wait_for_pipe=wait_timeout,
                                      keep_alive=keep_alive,
                                      stop_on_failure=stop_on_failure,
                                      env=env),
                    timeout=TIMEOUT_AUTOMATION_GUI,
                )
                result.setdefault("requested_action", requested_action)
                result.setdefault("resolved_action", action)
                result.setdefault("detected_subsystem", subsystem)
                return result
            except asyncio.TimeoutError:
                return {
                    "status": "failed",
                    "message": "automate_delphi(gui) 执行超时（300s）",
                }
            except Exception as e:
                return {"status": "failed", "message": f"automate_delphi(gui) failed: {e}"}

        elif action == "console":
            input_text = arguments.get("input", "")
            expect = arguments.get("expect", "")
            timeout = arguments.get("timeout", 30)
            args = arguments.get("args", None)

            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(_execute_automation,
                                      action="console",
                                      app_path=app_path,
                                      input_text=input_text,
                                      expect=expect,
                                      timeout=timeout,
                                      keep_alive=keep_alive,
                                      args=args,
                                      env=env),
                    timeout=max(timeout + 10, 120),
                )
                result.setdefault("requested_action", requested_action)
                result.setdefault("resolved_action", action)
                result.setdefault("detected_subsystem", subsystem)
                return result
            except asyncio.TimeoutError:
                return {
                    "status": "failed",
                    "message": "automate_delphi(console) 执行超时",
                    "action": "console",
                }
            except Exception as e:
                return {"status": "failed", "message": f"automate_delphi(console) failed: {e}"}

        else:
            return {"status": "error", "message": f"未知 action: {action}"}

    async def _handle_delphi_rtti(arguments: dict) -> dict:
        """处理 delphi_rtti 工具调用（RTTI 发现/调用）。"""
        return await _handle_delphi_rtti(arguments)

    async def _handle_ocr(arguments: dict) -> dict:
        """处理 ocr 工具调用（延迟导入，无 OCR 依赖时返回友好错误）。"""
        try:
            from src.tools.ocr import handle_ocr as _ocr_handler
        except ImportError as e:
            return {
                "status": "failed",
                "error": (
                    f"缺少 OCR 依赖: {e}。"
                    "请安装可选依赖: pip install daofy-for-delphi[ocr]"
                ),
            }
        return await asyncio.to_thread(_ocr_handler, arguments)

    _TOOL_HANDLERS = {
            "delphi_project": _handle_project_tool,
        "delphi_kb": _handle_delphi_kb,
        "delphi_file": _handle_file_tool,
        "file_tool": _handle_file_tool,  # 旧名兼容别名
        "manage_component": _handle_manage_component,
        "check_environment": _handle_check_environment,
        "async_task": _handle_async_task,
        "package": _handle_package,
        "get_coding_rules": _handle_get_coding_rules,
        "code_hosting": _handle_code_hosting,
        "tool_help": _handle_tool_help,
        "experience": _handle_experience,
        "daofy_update": _handle_daofy_update,
        "generate_copyright": _handle_generate_copyright,
        "automate_delphi": _handle_automate_delphi,
        "delphi_rtti": _handle_delphi_rtti,
        "ocr": _handle_ocr,
    }

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """调用工具（由 _TOOL_HANDLERS dispatch）"""
        import time as _time
        from datetime import datetime as _datetime
        import asyncio as _asyncio

        _call_start = _time.monotonic()
        _call_start_dt = _datetime.now()

        logger.info(f"调用工具: {name}")
        result = None

        try:
            handler = _TOOL_HANDLERS.get(name)
            if handler:
                # ── MCP 推送通知注入 ──
                # 对于 code_hosting 等支持异步任务的工具，注入 _on_complete 回调
                # 任务完成时自动推送 TaskStatusNotification 到 MCP 客户端，无需轮询
                try:
                    from mcp.types import (
                        TaskStatusNotification, TaskStatusNotificationParams,
                    )
                    _session = server.request_context.session
                    _loop = _asyncio.get_running_loop()

                    def _make_on_complete(session, loop):
                        def _on_complete(task_info):
                            """后台任务完成回调 — 推送 TaskStatusNotification"""
                            # 映射 local TaskStatus → MCP Literal 状态值
                            status_map = {
                                'COMPLETED': 'completed',
                                'FAILED': 'failed',
                                'CANCELLED': 'cancelled',
                            }
                            ts = task_info.status.name  # e.g. 'COMPLETED'
                            mcp_status = status_map.get(ts, 'completed')
                            # 确保 datetime 类型
                            created = task_info.created_at
                            updated = task_info.completed_at or _datetime.now()

                            notif = TaskStatusNotification(
                                params=TaskStatusNotificationParams(
                                    taskId=task_info.task_id,
                                    status=mcp_status,
                                    statusMessage=task_info.message[:500] if task_info.message else None,
                                    createdAt=created,
                                    lastUpdatedAt=updated,
                                    ttl=3600000,  # 1 hour retention
                                )
                            )
                            # 从后台线程调度到 asyncio 事件循环
                            asyncio.run_coroutine_threadsafe(
                                session.send_notification(notif),
                                loop
                            )
                        return _on_complete

                    arguments['_on_complete'] = _make_on_complete(_session, _loop)
                except (LookupError, AttributeError, ImportError) as _ctx_err:
                    logger.debug(f"无法注入 MCP 推送回调: {_ctx_err}")
                    # 非 MCP 环境（如测试）或无 request_context 时静默跳过

                result = await handler(arguments)
            else:
                raise ValueError(f"未知工具: {name}")

            # 计算调用用时
            _call_end = _time.monotonic()
            _call_end_dt = _datetime.now()
            _duration = _call_end - _call_start

            # P2: 智能提示
            hint = _get_smart_hint(name, result, arguments)
            if hint:
                if isinstance(result, CallToolResult):
                    if result.content and hasattr(result.content[0], 'text'):
                        result.content[0].text = result.content[0].text + "\n\n" + hint
                elif isinstance(result, dict):
                    msg = result.get('message', '')
                    if isinstance(msg, str):
                        result['message'] = msg + "\n\n" + hint

            # P2b: Delphi 文件读写尾注
            footnote = _get_delphi_file_footnote(name, arguments)
            if footnote:
                if isinstance(result, CallToolResult):
                    if result.content and hasattr(result.content[0], 'text'):
                        # 避免重复添加（后续 serialize 时还会嵌入一次）
                        result.content[0].text = result.content[0].text + footnote
                elif isinstance(result, dict):
                    msg = result.get('message', '')
                    if isinstance(msg, str):
                        result['message'] = msg + footnote

            # P3: API 调用日志（排除注入的 _on_complete 回调，防止 json.dumps 序列化函数报错）
            _log_args = _redact_sensitive_arguments(
                {k: v for k, v in arguments.items() if k != '_on_complete'}
            )
            log_api_call(logger, name, _log_args, result)

            import json as _json
            _show_timing = config_manager.get_show_timing()
            # 统一提取 data：dict→直接使用，CallToolResult→提取 TextContent 文本
            if isinstance(result, dict):
                data = result
                is_error = (result.get('status') == 'failed'
                            or result.get('success') is False
                            or (result.get('error') is not None and result.get('error') != ''))
            elif isinstance(result, CallToolResult):
                extracted = None
                if result.content and len(result.content) > 0:
                    ct = result.content[0]
                    if hasattr(ct, 'text'):
                        extracted = ct.text
                if extracted is not None:
                    try:
                        parsed = _json.loads(extracted)
                        if isinstance(parsed, dict):
                            data = {k: v for k, v in parsed.items() if v is not None}
                        else:
                            data = extracted
                    except (_json.JSONDecodeError, TypeError):
                        data = extracted
                else:
                    data = str(result)
                is_error = getattr(result, 'isError', False)
            elif isinstance(result, (str, bytes)):
                data = result
                is_error = False
            else:
                data = str(result)
                is_error = False

            response = {'success': not is_error, 'data': data}
            if isinstance(result, CallToolResult):
                response['isError'] = is_error
            if _show_timing and isinstance(data, dict):
                response['timing'] = {
                    'duration': round(_duration * 1000, 1),
                    'startTime': _call_start_dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3],
                    'endTime': _call_end_dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3],
                }
            if isinstance(response, (dict, list)):
                try:
                    text = _json.dumps(response, ensure_ascii=False, indent=2, default=str)
                except (TypeError, ValueError):
                    text = str(response)
            else:
                text = str(response)
            result = CallToolResult(content=[TextContent(type="text", text=text)], isError=is_error)
            return result

        except Exception as e:
            _call_end = _time.monotonic()
            _call_end_dt = _datetime.now()
            _duration = _call_end - _call_start
            error_result = {
                "error": str(e),
                "timing": {
                    'duration': round(_duration * 1000, 1),
                    'startTime': _call_start_dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3],
                    'endTime': _call_end_dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3],
                }
            }
            log_api_call(logger, name, _redact_sensitive_arguments(arguments), {"error": str(e)})
            logger.error(f"工具调用失败: {str(e)}", exc_info=True)
            import json as _json
            return CallToolResult(
                content=[TextContent(type="text", text=_json.dumps(error_result, ensure_ascii=False, indent=2))],
                isError=True
            )

    # 注册 MCP 资源

    @server.list_resources()
    async def list_resources():
        """列出可用资源"""
        return _build_mcp_resource_list(project_root)

    @server.read_resource()
    async def read_resource(uri: str):
        """读取资源内容"""
        return _read_mcp_resource_contents(uri, project_root)

    # ============================================================
    # MCP 提示词注册
    # 自动化测试工作流专用提示词模板
    # ============================================================

    @server.list_prompts()
    async def list_prompts():
        """列出所有可用提示词模板"""
        return [
            Prompt(
                name="automate-expert-primer",
                description="🎭 注入测试专家角色：设定身份、思维框架、三层递进思考模型",
                arguments=[
                    PromptArgument(
                        name="app_name",
                        description="被测 Delphi 应用名称",
                        required=False,
                    ),
                    PromptArgument(
                        name="project_path",
                        description="项目路径（用于后续代码分析）",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="automate-code-analysis",
                description="🔍 代码感知分析：读取目标单元的 DFM/PAS，生成控件映射表、事件分析、测试路径",
                arguments=[
                    PromptArgument(
                        name="form_name",
                        description="目标 Form/Frame 类名（如 TNewCustomerForm）",
                        required=True,
                    ),
                    PromptArgument(
                        name="project_path",
                        description="项目路径（传给 delphi_kb 搜索代码）",
                        required=True,
                    ),
                    PromptArgument(
                        name="app_path",
                        description="Delphi 应用 exe 路径（可选，用于后续自动化）",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="automate-test-plan",
                description="启动自动化测试规划：角色设定 + 代码分析 + 结构化步骤序列",
                arguments=[
                    PromptArgument(
                        name="goal",
                        description="测试目标描述（如「新建客户 - 成功路径」）",
                        required=True,
                    ),
                    PromptArgument(
                        name="app_path",
                        description="Delphi 应用 exe 路径",
                        required=False,
                    ),
                    PromptArgument(
                        name="project_path",
                        description="项目路径（用于代码分析）",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="automate-step-execute",
                description="单步自动化执行协议：前置感知→执行→等待→验证",
                arguments=[
                    PromptArgument(
                        name="phase",
                        description="步骤阶段: perceive / execute / verify",
                        required=True,
                    ),
                    PromptArgument(
                        name="tool",
                        description="工具/命令名 (如 goto+click, capture, waitfor, rcall)",
                        required=True,
                    ),
                    PromptArgument(
                        name="target",
                        description="操作目标 (控件名/坐标/文件路径)",
                        required=True,
                    ),
                    PromptArgument(
                        name="expected",
                        description="预期结果描述",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="automate-failure-recover",
                description="自动化测试失败恢复：诊断→决策→恢复→学习",
                arguments=[
                    PromptArgument(
                        name="signal",
                        description="失败信号: timeout / click_error / unexpected_dialog / rtti_exception / ocr_mismatch",
                        required=True,
                    ),
                    PromptArgument(
                        name="expected",
                        description="预期结果",
                        required=False,
                    ),
                    PromptArgument(
                        name="actual",
                        description="实际结果",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="automate-save-experience",
                description="测试完成后保存经验到知识库：结构化记录成功/失败模式",
                arguments=[],
            ),
            Prompt(
                name="automate-session-end",
                description="结束测试会话：保存经验、导出脚本、角色切回开发模式",
                arguments=[
                    PromptArgument(
                        name="save_experience",
                        description="是否保存测试经验（true/false，默认 true）",
                        required=False,
                    ),
                    PromptArgument(
                        name="export_script",
                        description="是否导出测试脚本到 tests/scripts/（true/false，默认 true）",
                        required=False,
                    ),
                ],
            ),
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
        """获取指定提示词模板内容"""
        args = arguments or {}

        if name == "automate-expert-primer":
            app_name = args.get("app_name", "待测 Delphi 应用")
            project_path = args.get("project_path", "")
            proj_line = f"\n项目路径: `{project_path}`" if project_path else ""
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"## 角色设定：Delphi UI 自动化测试专家\n\n"
                                f"你是一位 **Delphi UI 自动化测试专家**。"
                                f"被测应用: **{app_name}**{proj_line}\n\n"
                                f"### 你的核心方法论\n\n"
                                f"**感知 → 规划 → 执行 → 反馈（循环）**\n\n"
                                f"### 三层递进思考模型\n\n"
                                f"**第一层：理解被测对象（代码感知）**\n"
                                f"在操作任何控件之前，先读源码理解它：\n"
                                f"- 读 `.dfm` → 了解控件布局、类型、名称、事件绑定\n"
                                f"- 读 `.pas` → 了解事件处理程序、验证逻辑、数据流\n"
                                f"- 用 `delphi_kb` 查 API → 理解框架行为\n"
                                f"- 输出：控件映射表 + 事件处理程序分析 + 代码分支路径表\n\n"
                                f"**第二层：生成测试策略（规划）**\n"
                                f"根据源码理解，确定：\n"
                                f"- 覆盖哪些路径 — 每个事件处理程序 + 每个代码分支\n"
                                f"- 用什么工具 — RTTI(`rcall`) > 控件级(`goto+click`) > 坐标级(`move+click`)\n"
                                f"- 预期结果 — 从代码逻辑推导的断言（如 `ModalResult := mrOk` → 窗口应关闭）\n"
                                f"- 边界条件 — 从验证代码中提取（`if edtName.Text=''` → 测试空值）\n\n"
                                f"**第三层：执行-验证循环（执行）**\n"
                                f"严格按感知→执行→验证每步循环：\n"
                                f"- 先感知（`capture`/`dumpstate`/`msgscan`），不假设 UI 状态\n"
                                f"- 一步一验证，失败即停\n"
                                f"- 弹窗优先处理 — 操作后立即 `msgscan`\n"
                                f"- 失败时诊断→决策→恢复→学习\n\n"
                                f"---\n"
                                f"开始前，请先读取 MCP Resource `delphi://automation/workflow`，"
                                f"再执行 `get_coding_rules(section=\"automation\")` "
                                f"加载完整的方法论和提示词模板。"
                            ),
                        ),
                    ),
                ]
            )

        if name == "automate-code-analysis":
            form_name = args.get("form_name", "")
            project_path = args.get("project_path", "")
            app_path = args.get("app_path", "")
            app_hint = f"\n应用路径: `{app_path}`" if app_path else ""
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"## 代码感知分析\n\n"
                                f"目标类: **{form_name}**\n"
                                f"项目路径: `{project_path}`{app_hint}\n\n"
                                f"请按以下流程分析源码并输出测试路径：\n\n"
                                f"### 步骤 1：定位目标代码\n"
                                f"```\n"
                                f"delphi_kb(query=\"{form_name}\", search_type=\"class\", "
                                f"kb_type=\"project\", project_path=\"{project_path}\")\n"
                                f"delphi_file(action=\"read\", search_type=\"class\", "
                                f"type_name=\"{form_name}\", search_in=\"project\", "
                                f"project_path=\"{project_path}\")\n"
                                f"```\n\n"
                                f"### 步骤 2：分析 DFM 控件结构\n"
                                f"读取 `.dfm` 文件，列出：\n"
                                f"- 所有控件的名称、类型、事件绑定\n"
                                f"- 关键初始状态（Visible, Enabled, ReadOnly, MaxLength 等）\n"
                                f"- 输出：控件映射表\n\n"
                                f"### 步骤 3：分析 PAS 事件处理程序\n"
                                f"对每个绑定事件的处理程序，分析：\n"
                                f"- 代码路径：`if`/`case`/`try` 分支\n"
                                f"- 验证逻辑：检查空值、范围、格式的代码\n"
                                f"- 业务操作：数据创建、DB 写入、窗口关闭等\n"
                                f"- 输出：事件处理程序分析表\n\n"
                                f"### 步骤 4：推导测试路径\n"
                                f"按代码到测试路径的映射规则，输出：\n\n"
                                f"| # | 路径 | 操作 | 代码派生的断言 |\n"
                                f"|---|------|------|--------------|\n"
                                f"| 1 | 成功路径 | ... | ... |\n"
                                f"| 2 | 空值路径 | ... | ... |\n"
                                f"| 3 | 边界值 | ... | ... |\n"
                                f"| 4 | 异常路径 | ... | ... |\n"
                                f"| ... | ... | ... | ... |\n\n"
                                f"### 步骤 5（可选）：整合到测试规划\n"
                                f"使用 `prompts/get automate-test-plan` 将分析结果嵌入完整测试规划。\n\n"
                                f"完整脚本生成流程见 MCP Resource "
                                f"`delphi://automation/script-generation-workflow`，"
                                f"方法论见 `get_coding_rules(section=\"automation\")` §H"
                            ),
                        ),
                    ),
                ]
            )

        if name == "automate-test-plan":
            goal = args.get("goal", "未指定测试目标")
            app_path = args.get("app_path", "")
            project_path = args.get("project_path", "")
            app_line = f"\n应用路径: `{app_path}`" if app_path else ""
            proj_line = f"\n项目路径: `{project_path}`" if project_path else ""
            code_analysis_step = (
                f"\n\n### 阶段 0（前置）：代码感知分析\n"
                f"在感知 UI 之前，先读源码理解被测功能：\n"
                f"- 使用 `automate-code-analysis` prompt 分析目标单元的 DFM + PAS\n"
                f"- 获取控件映射表 + 事件处理程序分析 + 代码派生的断言\n"
                f"- 这些分析结果将直接指导后续的规划步骤"
            ) if project_path else ""

            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"## 自动化测试规划\n\n"
                                f"**目标**: {goal}{app_line}{proj_line}\n\n"
                                f"角色身份：你是 **Delphi UI 自动化测试专家**。"
                                f"按三层递进模型工作：代码感知 → 策略规划 → 执行验证。\n"
                                f"完整角色定义见 `get_coding_rules(section=\"automation\")` §F0\n"
                                f"代码感知方法论见 §H\n{code_analysis_step}"
                                f"\n\n### 阶段 1：加载方法论\n"
                                f"读取 `delphi://automation/script-generation-workflow`，并执行 "
                                f"`get_coding_rules(section=\"automation\")` 获取完整的"
                                f"感知·规划·执行·反馈架构、提示词模板(F)和经验优化闭环(G)\n\n"
                                f"### 阶段 2：检索经验\n"
                                f"```\n"
                                f"experience(action=\"search\", query=\"{goal}\", top_k=3)\n"
                                f"```\n\n"
                                f"### 阶段 3：感知当前状态\n"
                                f"通过 `capture` / `dumpstate` / `listwnd` / `msgscan` "
                                f"了解 UI 当前状态\n\n"
                                f"### 阶段 4：规划步骤序列\n"
                                f"输出结构化的步骤表，断言从代码逻辑推导：\n\n"
                                f"| # | 阶段 | 工具 | 目标 | 预期结果 | 超时 | 失败处理 |\n"
                                f"|---|------|------|------|---------|------|---------|\n"
                                f"| 0 | code | delphi_kb/delphi_file | 读源码分析 | 控件映射表 | — | — |\n"
                                f"| 1 | perceive | capture/dumpstate | 初始状态 | 主窗口已打开 | 5s | 上报 |\n"
                                f"| 2 | execute | goto+click | 操作目标 | 代码派生断言 | 10s | capture→分析 |\n"
                                f"| 3 | verify | waitfor+rget | 验证结果 | 与代码逻辑一致 | 5s | 降级RTTI |\n"
                                f"| ... | ... | ... | ... | ... | ... | ... |\n\n"
                                f"### 阶段 5：确认后执行\n"
                                f"每步严格按 `感知→执行→验证` 循环，失败即停不继续后续\n\n"
                                f"详细模板见 MCP Resource `delphi://automation/script-schema` "
                                f"和 `get_coding_rules(section=\"automation\")` §F1"
                            ),
                        ),
                    ),
                ]
            )

        if name == "automate-step-execute":
            phase = args.get("phase", "")
            tool = args.get("tool", "")
            target = args.get("target", "")
            expected = args.get("expected", "未指定")
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"## 单步自动化执行\n\n"
                                f"**阶段**: {phase}\n"
                                f"**工具**: {tool}\n"
                                f"**目标**: {target}\n"
                                f"**预期**: {expected}\n\n"
                                f"### 执行协议\n\n"
                                f"1. **前置感知** — `msgscan` 检查弹窗；必要时 `capture`/`dumpstate` 确认当前状态\n"
                                f"2. **执行** — 调用 `{tool}` 操作 `{target}`\n"
                                f"   - 同步命令 → 检查返回码\n"
                                f"   - 异步命令 → 记录操作已发起\n"
                                f"3. **等待** — 异步命令用 `wait(500~2000)` 或 `waitfor(控件, 10000)`\n"
                                f"4. **验证** — `msgscan` 确认无弹窗；`capture`/`rget`/`ocr` 确认结果\n"
                                f"   - 一致 → 标记完成\n"
                                f"   - 不一致 → 切换到失败恢复流程\n\n"
                                f"详细协议见 MCP Resource `delphi://automation/script-schema` "
                                f"和 `get_coding_rules(section=\"automation\")` §F2"
                            ),
                        ),
                    ),
                ]
            )

        if name == "automate-failure-recover":
            signal = args.get("signal", "未指定")
            expected = args.get("expected", "未记录")
            actual = args.get("actual", "未记录")
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"## 自动化测试失败恢复\n\n"
                                f"**失败信号**: {signal}\n"
                                f"**预期**: {expected}\n"
                                f"**实际**: {actual}\n\n"
                                f"### 诊断\n"
                                f"1. `capture` 截图留存\n"
                                f"2. `dumpstate` 获取当前控件树\n"
                                f"3. `msgscan` 检测弹窗\n"
                                f"4. 分析差异原因：控件状态/弹窗/时序/路径变更\n\n"
                                f"### 恢复策略\n\n"
                                f"| 条件 | 恢复动作 |\n"
                                f"|------|---------|\n"
                                f"| 弹窗干扰 | msgclick(OK/Cancel) → 重试原操作 |\n"
                                f"| 控件不可见 | dumpstate 查替代路径 → 修正 goto |\n"
                                f"| 超时无错误 | 增加 waitfor 时间 → 重试 |\n"
                                f"| RTTI 可用 | degrade 到 rcall/rset 绕过 GUI |\n"
                                f"| 确定性失败 | 上报并保存经验 |\n\n"
                                f"### 学习记录\n"
                                f"恢复后保存经验：\n"
                                f"`experience(action=\"save\", problem=\"{signal} in {expected}\", "
                                f"solution=\"...恢复方法...\", tags=[\"automation\", \"failure_recovery\"])`\n\n"
                                f"完整恢复模板见 MCP Resource `delphi://automation/repair-loop` "
                                f"和 `get_coding_rules(section=\"automation\")` §F3"
                            ),
                        ),
                    ),
                ]
            )

        if name == "automate-save-experience":
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"## 保存自动化测试经验\n\n"
                                f"测试执行完成，请按以下模板保存经验：\n\n"
                                f"### 执行概况\n"
                                f"- **总步骤数**: \n"
                                f"- **成功**: \n"
                                f"- **失败+恢复**: \n"
                                f"- **不可恢复失败**: \n"
                                f"- **总耗时**: \n\n"
                                f"### 成功模式\n"
                                f"- 稳定的工具组合: \n"
                                f"- RTTI 使用情况: \n"
                                f"- 关键时序调整: \n\n"
                                f"### 失败模式\n"
                                f"- 失败描述 → 原因 → 恢复方式 → 是否可自动化\n\n"
                                f"### 保存\n"
                                f"```\n"
                                f"experience(action=\"save\",\n"
                                f"    problem=\"<场景关键词>\",\n"
                                f"    solution=\"<核心做法>\",\n"
                                f"    tools_used=[\"<工具列表>\"],\n"
                                f"    tags=[\"automation\", \"<app_name>\"])\n"
                                f"```\n\n"
                                f"完整模板见 `get_coding_rules(section=\"automation\")` §F4"
                            ),
                        ),
                    ),
                ]
            )

        if name == "automate-session-end":
            save_exp = args.get("save_experience", "true")
            export_script = args.get("export_script", "true")
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"## 结束自动化测试会话\n\n"
                                f"测试执行完成，请按以下步骤收尾：\n\n"
                                f"### 1. 保存本次测试经验\n"
                                f"（save_experience={save_exp}）\n"
                                f"```\n"
                                f"experience(action=\"save\",\n"
                                f"    problem=\"<场景关键词>\",\n"
                                f"    solution=\"<核心做法>\",\n"
                                f"    tools_used=[\"<工具列表>\"],\n"
                                f"    tags=[\"automation\", \"<app_name>\"])\n"
                                f"```\n\n"
                                f"### 2. 导出可复用脚本\n"
                                f"（export_script={export_script}）\n"
                                f"将本次执行的脚本保存到 `tests/scripts/`：\n"
                                f"```\n"
                                f"delphi_file(action=\"write\",\n"
                                f"    file_path=\"tests/scripts/<test_name>.json\",\n"
                                f"    content=<script_json>)\n"
                                f"```\n"
                                f"详细格式见 MCP Resource `delphi://automation/script-schema` "
                                f"和 `get_coding_rules(section=\"automation\")` §I2\n\n"
                                f"### 3. 角色切换\n"
                                f"自动化测试会话已结束。\n"
                                f"角色从 **Delphi UI 自动化测试专家** 切回 **Delphi 开发专家**。\n"
                                f"思维框架切换为编码模式：\n"
                                f"```\n"
                                f"get_coding_rules(section=\"coding\")\n"
                                f"```\n"
                                f"开始编码工作前，建议先执行 `get_coding_rules(section=\"workflow\")` "
                                f"获取完整开发工作流。"
                            ),
                        ),
                    ),
                ]
            )

        raise ValueError(f"未知提示词: {name}")

    # ============================================================
    # 后台版本检查 — 启动时异步检测 GitHub 有无新版本（带自动重试）
    # ============================================================

    async def _background_version_check():
        """后台检查 Daofy 版本更新，使用 AsyncTaskManager 提交自动重试任务。

        类似 code_hosting git_push_retry 模式：
        - 网络不可达时自动重试（5分钟间隔，最多12次≈1小时）
        - 重试期间不阻塞 MCP 服务
        - 成功时通过 on_complete 回调更新全局变量
        """
        global _update_check_result, _update_check_done
        try:
            logger.info("正在后台检查 Daofy 版本更新（异步自动重试）...")

            # 先快速尝试一次（不等待重试）
            loop = asyncio.get_running_loop()
            quick_result = await loop.run_in_executor(
                None, updater.check_for_update
            )
            if quick_result is not None:
                _update_check_result = quick_result
                if quick_result.get("update_available"):
                    logger.warning(
                        "发现新版本！当前: %s, 最新: %s → %s",
                        quick_result["current"], quick_result["latest"],
                        quick_result["release_url"],
                    )
                else:
                    logger.info("当前已是最新版本: %s", quick_result["current"])
                _update_check_done = True
                return

            # 快速尝试失败，提交后台自动重试任务
            logger.info("版本检查快速尝试失败，提交后台自动重试任务...")

            def _on_update_complete(task_info):
                """后台重试任务完成回调 — 更新全局缓存。"""
                global _update_check_result, _update_check_done
                result = task_info.result
                if isinstance(result, dict) and 'error' not in result:
                    _update_check_result = result
                    if result.get("update_available"):
                        logger.warning(
                            "后台重试发现新版本！当前: %s, 最新: %s",
                            result["current"], result["latest"],
                        )
                    else:
                        logger.info(
                            "后台重试确认已是最新版本: %s", result["current"]
                        )
                elif isinstance(result, dict) and result.get('error'):
                    logger.warning(
                        "后台版本检查重试全部失败: %s", result['error']
                    )
                _update_check_done = True

            from src.services.knowledge_base.async_task_manager import get_task_manager
            task_id = get_task_manager().submit_task(
                name="version_check_retry",
                func=updater.check_for_update_retry,
                on_complete=_on_update_complete,
            )
            logger.info(
                "后台版本检查重试任务已提交: task_id=%s | "
                "间隔=%ds | 最多%d次 | 最长约%dmin",
                task_id,
                updater.RETRY_INTERVAL,
                updater.MAX_RETRIES,
                updater.ETA_MINUTES,
            )

        except ImportError as e:
            logger.warning(
                "无法提交异步重试任务（AsyncTaskManager 不可用）: %s", e
            )
            _update_check_done = True
        except Exception as e:
            logger.debug("版本检查失败（不影响正常运行）: %s", e)
            _update_check_done = True

    # 启动后台版本检查（不阻塞启动）
    asyncio.create_task(_background_version_check())

    # ============================================================
    # 自动构建项目知识库 — 启动时检测项目目录并后台构建
    # ============================================================

    async def _auto_build_project_kb():
        """自动检测项目目录并后台构建项目知识库（不阻塞启动）"""
        try:
            logger.info("正在自动检测项目目录...")
            loop = asyncio.get_running_loop()

            # 在 executor 中执行 CWD 扫描（可能涉及文件系统 I/O）
            project_path = await loop.run_in_executor(
                None, _resolve_project_path, None
            )

            if not project_path:
                logger.info(
                    "未检测到项目文件（.dproj/.dpr/.dpk），跳过自动构建项目知识库"
                )
                return

            logger.info(
                "检测到项目: %s，正在后台自动构建项目知识库...",
                project_path,
            )

            # 使用现有异步任务机制提交后台构建
            # rebuild=False → 增量更新（只索引变更文件）
            # 首次运行时 KB 不存在，build_project_knowledge_base 会自动全量构建
            # Step 1 的热切换机制保证：已有 KB 重建时不阻塞搜索
            task_params = {
                "project_path": project_path,
                "rebuild": False,
                "build_thirdparty": True,
                "build_project": True,
            }
            result = await async_tools.start_async_task({
                "task_type": "init_project_knowledge_base",
                "task_params": task_params,
                "show_progress": False,
            })

            # start_async_task 返回 CallToolResult，isError=False 表示任务已成功提交到后台
            if result.isError:
                logger.warning(
                    "自动构建项目知识库提交失败: %s", project_path
                )
            else:
                logger.info(
                    "自动构建项目知识库任务已提交到后台: %s", project_path
                )

            # ── Step 3: 启动文件变更监听（如果 watchdog 可用） ──
            await _start_project_file_watcher(project_path)

        except Exception as e:
            logger.debug(
                "自动构建项目知识库失败（不影响正常运行）: %s", e
            )

    async def _start_project_file_watcher(project_path: str) -> None:
        """启动项目文件变更监听器，自动触发增量 KB 更新。

        在 executor 中启动，不阻塞事件循环。watchdog 不可用时静默降级。
        """
        global _project_file_watcher
        try:
            from src.services.knowledge_base.file_watcher import (
                ProjectFileWatcher,
            )

            project_dir = str(Path(project_path).parent)
            loop = asyncio.get_running_loop()

            def _start_watcher() -> Optional[object]:
                w = ProjectFileWatcher(project_path, project_dir)
                w.start()
                return w

            watcher = await loop.run_in_executor(None, _start_watcher)
            if watcher:
                _project_file_watcher = watcher
                logger.info(
                    "文件变更监听已启动 (watchdog 可用): %s", project_dir
                )
            else:
                logger.info(
                    "文件变更监听未启动 (watchdog 不可用): %s", project_dir
                )

        except Exception as e:
            logger.debug(
                "启动文件变更监听失败（不影响正常运行）: %s", e
            )

    # 启动后台项目知识库自动构建（不阻塞启动）
    asyncio.create_task(_auto_build_project_kb())

    # 启动服务器
    logger.info("MCP Server 启动完成,准备接收请求...")
    async with stdio_server() as (read_stream, write_stream):
        await _run_mcp_server(
            server,
            read_stream,
            write_stream,
        )


def _cleanup_resources():
    """清理资源：关闭后台任务、DB连接、临时文件等"""
    logger.info("清理资源中...")
    try:
        from src.tools.knowledge_base import _cleanup_pkb_cache  # 延迟导入避免循环import
        _cleanup_pkb_cache()
    except Exception:
        logger.warning("清理 pkb_cache 时发生异常", exc_info=True)
    try:
        from src.tools.dfm_utils import _cleanup_dfm_temp_dirs
        _cleanup_dfm_temp_dirs()
    except Exception:
        logger.warning("清理 DFM 临时文件时发生异常", exc_info=True)
    try:
        from src.services.experience_service import cleanup as _cleanup_exp
        _cleanup_exp()
    except Exception:
        logger.warning("清理经验库时发生异常", exc_info=True)
    try:
        from src.tools.knowledge_base import (
            get_knowledge_base_service, get_thirdparty_knowledge_base_service,
        )
        _kb = get_knowledge_base_service()
        if _kb is not None and hasattr(_kb, 'close'):
            _kb.close()
        _tpb = get_thirdparty_knowledge_base_service()
        if _tpb is not None and hasattr(_tpb, 'close'):
            _tpb.close()
    except Exception:
        logger.warning("清理知识库服务时发生异常", exc_info=True)
    global _project_file_watcher
    if _project_file_watcher is not None:
        try:
            _project_file_watcher.stop()
        except Exception:
            logger.warning("停止文件监听时发生异常", exc_info=True)
        _project_file_watcher = None
    logger.info("资源清理完成")


def _build_arg_parser() -> "argparse.ArgumentParser":
    """构建 CLI 参数解析器 (不依赖任何服务, --help/--version 立即退出)"""
    import argparse
    parser = argparse.ArgumentParser(
        prog="daofy",
        description="Daofy for Delphi — MCP Server (Delphi 编译 + 知识库)",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="显示版本信息并退出",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="自定义 compilers.json 路径 (默认: config/compilers.json)",
    )
    return parser


def main():
    """主函数"""
    # ── 早退: --help/--version 不触发任何服务初始化 ──
    # 避免在没装 Delphi / 默认路径失效的环境下 --help 报错
    parser = _build_arg_parser()
    args = parser.parse_args()
    if args.version:
        print(f"Daofy v{__version__}")
        print(f"Python {sys.version.split()[0]}")
        print(f"{__copyright__}")
        return

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("服务器已停止")
    except Exception as e:
        logger.error(f"服务器运行失败: {str(e)}", exc_info=True)
        _logging.shutdown()
        sys.exit(1)
    finally:
        _cleanup_resources()


if __name__ == "__main__":
    main()
