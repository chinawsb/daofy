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


def _ensure_deps() -> None:
    """启动前检查核心依赖，缺失时自动 pip install（仅主进程，失败不阻塞）。

    使用 importlib.util.find_spec 探测，不触发实际导入，避免副作用。
    """
    import subprocess
    import importlib.util

    # (模块探测名, pip install 规格)
    CORE: list[tuple[str, str]] = [
        ("zvec",      "zvec>=0.5.0"),
        ("chardet",   "chardet>=7.0"),
        ("mcp",       "mcp>=0.9.0"),
        ("pydantic",  "pydantic>=2.0.0"),
        ("bs4",       "beautifulsoup4>=4.12.0"),
        ("html2text", "html2text>=2024.2.25"),
        ("lxml",      "lxml>=4.9.0"),
        ("docx",      "python-docx>=0.8.11"),
        ("requests",  "requests>=2.31.0"),
    ]

    missing = [spec for mod, spec in CORE if importlib.util.find_spec(mod) is None]
    if not missing:
        return

    try:
        _logging.getLogger("daofy").info(
            "缺失依赖，正在自动安装: %s ...", ", ".join(missing)
        )
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", *missing],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
        _logging.getLogger("daofy").info("依赖安装完成")
    except Exception as exc:
        _logging.getLogger("daofy").warning(
            "自动安装依赖失败（%s），请手动执行:  pip install -r requirements.txt", exc
        )


# multiprocessing spawn 子进程重执行本文件时跳过安装
if __name__ != "__mp_main__":
    _ensure_deps()

from src.constants import (
    REG_KEY_EMBARCADERO_BDS,
    TIMEOUT_AUTOMATION_GUI,
    TIMEOUT_EXPERIENCE_TOOL,
    TIMEOUT_GENERATE_COPYRIGHT,
)

def _filter_surrogates(text: str) -> str:
    """过滤字符串中的无效 UTF-8 代理对字符（surrogate characters）。

    代理对字符（U+D800 到 U+DFFF）在 UTF-8 编码中是无效的，
    会导致 Pydantic JSON 序列化失败。此函数将它们替换为 Unicode 替换字符。

    注意：此函数不会影响正常的 Unicode 字符（如中文、日文、韩文、emoji 等），
    因为这些字符的 Unicode 范围（U+0000-U+D7FF, U+E000-U+10FFFF）
    与代理对字符的范围（U+D800-U+DFFF）完全不重叠。

    代理对字符出现的常见原因：
    1. UTF-16 编码的字符串被错误地当作 UTF-8 处理
    2. 某些老旧的 Delphi 组件使用了不标准的编码
    3. 文件读取时编码检测错误

    Args:
        text: 输入字符串

    Returns:
        过滤后的字符串，所有代理对字符已被替换
    """
    import re
    # 检查是否包含代理对字符
    surrogate_pattern = re.compile(r'[\ud800-\udfff]')
    if surrogate_pattern.search(text):
        # 记录警告，帮助调试编码问题
        count = len(surrogate_pattern.findall(text))
        logger.warning(
            "检测到 %d 个无效的 UTF-8 代理对字符，已替换为替换字符。"
            "这可能表示源文件编码不正确。",
            count
        )
        return surrogate_pattern.sub('\ufffd', text)
    return text


MCP_SERVER_INSTRUCTIONS = (
    "Daofy:Delphi 文件必用 delphi_file 处理，编码前 get_coding_rules，参数用 tool_help(tool_name, action_name)获取"
)

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
    from src.tool_docs import TOOL_NAMES
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

    # ============================================================
    # 插件系统 (Phase 2: 工具归属 + handler 分发)
    # ============================================================
    from src.plugins.registry import PluginRegistry
    from src.plugins.delphi import DelphiPlugin
    from src.plugins.lazarus import LazarusPlugin

    _plugin_registry = PluginRegistry()
    _plugin_registry.register(DelphiPlugin())
    _plugin_registry.register(LazarusPlugin())

    logger.info(f"已注册插件: {[p.info.name for p in _plugin_registry.get_all_plugins()]}")
    logger.info(f"插件扩展名映射: {_plugin_registry.get_all_extensions()}")

    # 插件工具归属:
    #   delphi 插件拥有: delphi_project, delphi_file, delphi_kb, manage_component,
    #                     get_coding_rules, package, check_environment, delphi_rtti, automate_delphi
    #   lazarus 插件拥有: lazarus_compile
    #   核心拥有: async_task, code_hosting, tool_help, experience, daofy_update,
    #            generate_copyright, ocr
    # handler 仍由 _TOOL_HANDLERS 管理（闭包中的局部函数不可导入），
    # Phase 3 将 handler 提取到插件模块。


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


    async def _fetch_workspace_roots(session) -> None:
        """异步获取 AI Agent 工作区根目录并缓存到 file_tool。

        在 session 初始化完成后调用 session.list_roots() 获取工作区根，
        将第一个有效的 file:// URI 转换为本地路径后缓存。
        若客户端不支持 roots 或超时，静默跳过。
        """
        try:
            # 等待初始化完成（InitializedNotification 到达后才可发起 roots/list）
            await anyio.sleep(1.0)
            result = await session.list_roots()
            if not result or not result.roots:
                logger.info("客户端未提供工作区根目录（roots 为空）")
                return

            for root in result.roots:
                uri = root.uri
                if uri.scheme == "file":
                    local_path = uri.path.rstrip("/\\")
                    if local_path and os.path.isdir(local_path):
                        from src.tools.file_tool import set_workspace_root
                        set_workspace_root(local_path)
                        return
                    logger.info("工作区根 URI 不是有效目录: %s", uri)
                else:
                    logger.debug("跳过非 file:// 工作区根: %s", uri)

            logger.info("未找到有效的 file:// 工作区根目录")
        except anyio.EndOfStream:
            logger.debug("session 已关闭，跳过根目录获取")
        except Exception:
            logger.debug("获取工作区根目录失败（客户端可能不支持 roots）- 静默跳过", exc_info=True)


    async def _install_client_rules(session) -> None:
        """将 Daofy 客户端规则安装到所连 MCP 客户端的规则目录。

        客户端身份只有 initialize 之后才可得，故放在后台任务里执行，
        不阻塞握手。失败不影响 Server 运行。
        """
        try:
            from src.services.client_rules_installer import install_client_rules

            client_params = getattr(session, "_client_params", None)
            outcome = install_client_rules(client_params)
            if outcome.get("message"):
                logger.info("[client-rules] %s", outcome["message"])
        except Exception:
            logger.info("安装 Daofy 客户端规则失败（不影响正常运行）", exc_info=True)


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
                # 后台获取工作区根目录
                tg.start_soon(_fetch_workspace_roots, session)
                # 后台将 Daofy 规则安装到所连 MCP 客户端的规则目录
                tg.start_soon(_install_client_rules, session)

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
    "delphi_project":     {"info", "ast", "audit", "compile", "compile_file", "devices", "deploy"},
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
                description="编译/配置/审计/部署",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["compile", "compile_file", "dry_run", "info", "create",
                                     "set", "add_config", "remove_config", "add_source",
                                     "remove_source", "audit", "ast", "runtime", "layout",
                                     "devices", "deploy"],
                        },
                    },
                    "required": ["action"]
                }
            ),

            Tool(
                name="delphi_kb",
                description="知识库搜索/管理",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["search", "stats", "build", "scan", "web", "read", "build_embedding"]},
                    }
                }
            ),

            Tool(
                name="delphi_file",
                description="Delphi 文件必用读写/搜索/替换/备份工具",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["read", "write", "replace", "insert", "delete", "format", "backup", "encode", "uses", "fix_garbled", "grep"],
                            "default": "read",
                        },
                    },
                    "required": ["action"]
                }
            ),

            Tool(
                name="manage_component",
                description="DFM组件增/删/改/生成",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["create", "add", "remove", "modify"], "default": "create"},
                    },
                    "required": ["action"]
                }
            ),

            Tool(
                name="check_environment",
                description="环境检查/编译器检测/安装",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["check", "detect", "install", "format_install"], "default": "check"},
                    }
                }
            ),

            Tool(
                name="async_task",
                description="异步任务管理",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["start", "status", "result", "list", "cancel"], "default": "list"},
                    }
                }
            ),

            Tool(
                name="package",
                description="组件包编译安装/列出",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["install", "list"], "default": "install"},
                    },
                    "required": ["action"]
                }
            ),

            Tool(
                name="get_coding_rules",
                description="编码必用编码规则获取工具",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "section": {"type": "string"},
                        "examples": {"type": "string", "description": "示例名称，如 naming/format/debug-log。按名称加载 coding-rules/examples/ 下的示例文件"},
                    }
                }
            ),

            Tool(
                name="code_hosting",
                description="Git操作+代码托管平台API",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["create_token", "init_labels", "create_issue", "get_issue", "edit_issue", "set_labels", "close_issue", "add_comment", "list_issues", "create_pull", "get_pull", "list_pulls", "edit_pull", "merge_pull", "close_pull", "reopen_pull", "create_release", "get_release", "list_releases", "edit_release", "delete_release", "git_clone", "git_add", "git_commit", "git_push", "git_push_retry", "git_status", "git_diff", "git_show", "git_log", "git_fetch", "git_pull", "git_branch", "git_switch", "git_merge", "git_restore", "git_unstage", "git_stash", "git_tag"]},
                    },
                    "required": ["action"]
                }
            ),

            Tool(
                name="tool_help",
                description="获取工具的完整帮助文档",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "enum": TOOL_NAMES,
                        },
                    },
                    "required": ["tool_name"],
                }
            ),

            Tool(
                name="daofy_update",
                description="版本更新检查/git pull",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["check", "check_retry", "update", "update_retry", "version"],
                            "default": "check",
                        },
                    },
                    "required": ["action"],
                }
            ),

            Tool(
                name="experience",
                description="经验记忆管理",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["save", "search", "get", "list", "update", "merge", "prune", "delete", "rebuild_embedding"],
                        },
                    },
                    "required": ["action"],
                }
            ),

            Tool(
                name="generate_copyright",
                description="生成软著文档",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["generate", "validate", "update_config", "status", "list", "generate_content", "audit"],
                            "default": "generate",
                        },
                    },
                    "required": ["action"],
                }
            ),

            Tool(
                name="automate_delphi",
                description="Delphi 自动化测试",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["auto", "gui", "console", "prepare"],
                            "default": "auto",
                        },
                    },
                    "required": [],
                }
            ),

            Tool(
                name="ocr",
                description="图像分析",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["recognize", "detect", "status",
                                     "diff", "color", "match"],
                            "default": "recognize",
                        },
                    },
                    "required": [],
                }
            ),

            Tool(
                name="delphi_rtti",
                description="RTTI 发现/调用",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["guide", "discover", "call"],
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
        return await _get_coding_rules(project_path=arguments.get("project_path"), section=arguments.get("section"), examples=arguments.get("examples"))

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

    # Phase 2: 将 _TOOL_HANDLERS 注入插件注册表
    _plugin_registry.register_handlers(_TOOL_HANDLERS)

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
            # 过滤无效的 UTF-8 代理对字符，防止 Pydantic JSON 序列化失败
            text = _filter_surrogates(text)
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
    # 注意：knowledge_base 模块没有公开的 getter 函数来获取服务实例，
    # 全局变量 _delphi_kb_service 和 _thirdparty_kb_service 在进程退出时会自动清理。
    # 这里不再尝试导入不存在的 get_knowledge_base_service / get_thirdparty_knowledge_base_service。
    try:
        from src.tools.project_knowledge_base import _cleanup_project_kb_cache
        _cleanup_project_kb_cache()
    except Exception:
        logger.warning("清理项目知识库缓存时发生异常", exc_info=True)
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
