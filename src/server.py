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
import winreg
from pathlib import Path
from typing import Any, Optional
import io

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'

# 保护: 子进程(multiprocessing spawn) 的 stdout 已经 pipe,
# TextIOWrapper 可能失败。失败时跳过不影响子进程通信。
if __name__ != '__mp_main__':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=False)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=False)
    except Exception:
        import logging as _logging
        _logger = _logging.getLogger(__name__)
        _logger.warning("stdout/stderr 编码设置失败，部分输出可能乱码", exc_info=True)

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

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
    from mcp.server.stdio import stdio_server
    from mcp.types import CallToolResult, TextContent, Tool, Resource, ReadResourceResult, TextResourceContents

    from src.services.config_manager import ConfigManager
    from src.services.compiler_service import CompilerService
    from src.services.knowledge_base import DelphiKnowledgeBaseService
    from src.services.knowledge_base.thirdparty_knowledge_base import ThirdPartyKnowledgeBase
    from src.tools.project import handle_project as _handle_project, set_compiler_service as _set_compile_svc
    # project 模块统一管理编译器服务，保留别名供初始化用
    from src.tools.compile_project import set_compiler_service as sp1
    from src.tools.compile_file import set_compiler_service as sp2
    from src.tools.get_args import set_compiler_service as sp3
    from src.tools.config import set_config_manager, search_compilers
    from src.tools.environment import check_environment, set_config_manager as scm, set_thirdparty_kb_service as stks
    from src.tools.knowledge_base import (
        set_delphi_kb_service,
        set_thirdparty_kb_service,
        search_knowledge,
        build_unified_knowledge_base,
        get_unified_knowledge_stats,
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
    from src.config.tool_docs import TOOL_NAMES, TOOL_SHORT_DESC
    from src.utils.logger import init_default_logger, get_logger, log_api_call
    from src.__version__ import __version__, __copyright__

    # 初始化日志
    logger = init_default_logger()


def _auto_detect_delphi_help_dir() -> Optional[str]:
    """自动检测最新安装的 Delphi 帮助文档目录"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Embarcadero\BDS")
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
                vk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Embarcadero\BDS\{ver}")
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
    for ver in ["37.0", "23.0", "22.0", "21.0", "20.0", "19.0", "18.0", "17.0"]:
        path = rf"C:\Program Files (x86)\Embarcadero\Studio\{ver}\Help\Doc"
        if Path(path).exists():
            logger.info(f"使用默认帮助目录: {path}")
            return path
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
                            "use project(action='compile') to verify")
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

    return None


async def run_server():
    """运行 MCP Server"""
    logger.info(f"启动 Daofy v{__version__}")
    logger.info(f"{__copyright__}")

    # 初始化配置管理器
    config_manager = ConfigManager()
    logger.info("配置管理器初始化完成")

    # 初始化编译服务
    compiler_service = CompilerService(config_manager)
    logger.info("编译服务初始化完成")

    # 初始化知识库服务
    kb_service = DelphiKnowledgeBaseService()
    logger.info("知识库服务初始化完成")

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
    server = Server("daofy-for-delphi")
    logger.info("MCP Server 实例创建完成")

    # ============================================================
    # MCP 工具注册
    # 所有工具必须同时在 list_tools() 和 call_tool() 中注册
    # ============================================================
    @server.list_tools()
    async def list_tools():
        """列出所有可用工具"""
        return [
            # ===== 项目全生命周期管理 ⭐⭐⭐ =====
            Tool(
                name="project",
                description=TOOL_SHORT_DESC["project"],
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["compile", "compile_file", "dry_run", "info", "create",
                                     "set", "add_config", "remove_config", "add_source",
                                     "remove_source", "audit", "ast", "runtime"],
                            "description": "操作类型。先 tool_help('project') 查看各 action 的参数说明。"
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
                        "action": {"type": "string", "enum": ["search", "stats", "build", "scan", "web", "read", "build_embedding"], "default": "search", "description": "操作类型: search=搜索, stats=统计, build=构建, scan=扫描文档, web=添加网页, read=读取, build_embedding=构建向量"},
                        "query": {"type": "string", "description": "搜索关键词（action=search时需要）"},
                        "kb_type": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty", "document"], "default": "all", "description": "知识库类型"},
                        "search_type": {"type": "string", "enum": ["function", "procedure", "class", "record", "interface", "enum", "set", "helper", "type", "const", "resourcestring", "variable", "property", "method", "field", "event", "operator", "string", "dfm", "attribute", "unit", "semantic", "reference", "all"], "description": "搜索类型（action=search 时生效）"},
                        "top_k": {"type": "integer", "default": 200, "description": "最大返回结果数（默认200，最大500）"},
                        "project_path": {"type": "string", "description": "项目路径（搜索project/thirdparty知识库时需要，不传则自动检测目录下的.dproj）"},
                        "version": {"type": "string", "description": "Delphi版本（构建知识库时使用）"},
                        "async_mode": {"type": "boolean", "default": True, "description": "是否异步执行（build操作时生效，默认true）"},
                        "rebuild": {"type": "boolean", "default": False, "description": "是否强制重建（build操作时生效）"},
                        "incremental": {"type": "boolean", "default": False, "description": "是否增量更新（build操作时生效）"},
                        "build_thirdparty": {"type": "boolean", "default": True, "description": "构建项目KB时是否同时构建第三方库KB"},
                        "build_project": {"type": "boolean", "default": True, "description": "是否构建项目KB"},
                        "directory": {"type": "string", "description": "扫描目录（action=scan时使用，或build document时可以不传自动检测Delphi帮助目录）"},
                        "extensions": {"type": "array", "items": {"type": "string"}, "description": "文件扩展名过滤（action=scan/build时使用，如[\".chm\"]）"},
                        "content_type": {"type": "string", "description": "文档类型过滤（action=search kb_type=document时使用）"},
                        "url": {"type": "string", "description": "网页URL（action=web时使用）或文档URL（action=read时使用）"},
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
                        "action": {"type": "string", "enum": ["read", "write", "format", "backup", "uses"], "default": "read", "description": "操作类型: read=读文件, write=写文件(自动备份), format=格式化, backup=备份管理, uses=增删uses子句"},
                        "file_path": {"type": "string", "description": "目标文件路径，支持 .pas/.dfm/.dproj/.dpk/.fmx/.inc"},

                        # ---- [仅 action=read] 参数 ----
                        "search_type": {"type": "string", "enum": ["path", "class", "function", "record"], "description": "[仅 action=read] 读取模式: path=按路径, class=按类名定位, function=按函数名定位, record=按record名定位"},
                        "type_name": {"type": "string", "description": "[仅 action=read, search_type=class] 类名/接口名/枚举名，如 'TForm1'"},
                        "class_name": {"type": "string", "description": "[仅 action=read, search_type=class] 类名（与type_name二选一，兼容旧版）"},
                        "record_name": {"type": "string", "description": "[仅 action=read, search_type=record] Record 类型名"},
                        "function_name": {"type": "string", "description": "[仅 action=read, search_type=function] 函数/过程名，如 'Create'"},
                        "start_line": {"type": "integer", "default": 0, "description": "起始行号（从0开始，左闭右开区间）。action=read 时分段读取；action=write 时配合 end_line 做部分写入"},
                        "limit": {"type": "integer", "default": 2000, "description": "[仅 action=read] 最大返回行数。当文件超长时分段读取"},
                        "show_line_numbers": {"type": "boolean", "default": False, "description": "[仅 action=read] 是否在输出中显示行号前缀（如 '     1: unit Unit1;'），默认 false"},
                        "end_line": {"type": "integer", "description": "结束行号（不包含该行，左闭右开区间），不传则到文件末尾。action=read 时配合 start_line 分段；action=write 时配合 start_line 做部分写入"},
                        "search_in": {"type": "string", "enum": ["all", "delphi", "thirdparty"], "default": "all", "description": "[仅 action=read, search_type=class/function] 搜索范围"},
                        "project_path": {"type": "string", "description": "[仅 action=read, search_type=class/function] 项目文件路径，用于在项目知识库中查找 .pas"},

                        # ---- [仅 action=write] 参数 ----
                        "content": {"type": "string", "description": "【action=write 必需】写入的内容。不传 start_line/end_line 时替换全文，必须包含完整文件内容。配合 start_line/end_line 时仅替换指定行范围。"},
                        "encoding": {"type": "string", "default": "auto", "description": "[仅 action=write] 写入编码: auto=自动检测保持原始编码, 也可指定 utf-8/gbk/utf-16"},
                        "auto_format": {"type": "boolean", "default": False, "description": "[仅 action=write] 写入后自动调用 pasfmt 格式化代码"},
                        "backup": {"type": "boolean", "default": True, "description": "[仅 action=write] 写入前自动备份原文件到 __history 目录（建议保持默认 true）"},

                        # ---- [仅 action=format] 参数 ----
                        "mode": {"type": "string", "enum": ["file", "code", "check"], "default": "file", "description": "[仅 action=format] 格式化模式: file=格式化文件, code=格式化代码段, check=仅检查格式"},
                        "code": {"type": "string", "description": "[仅 action=format, mode=code] 待格式化的代码文本"},
                        "config_path": {"type": "string", "description": "[仅 action=format] pasfmt 配置文件路径（可选，高级用法）"},
                        "uses_style": {"type": "string", "enum": ["compact", "pasfmt_default"], "description": "[仅 action=format] uses子句风格: compact=合并为一行, pasfmt_default=每行一个"},
                        "dry_run": {"type": "boolean", "default": False, "description": "[仅 action=format] true=仅检查格式不修改文件"},

                        # ---- [仅 action=backup] 参数 ----
                        "backup_action": {"type": "string", "enum": ["create", "list", "restore"], "default": "create", "description": "[仅 action=backup] 备份子操作: create=创建备份, list=列出版本, restore=恢复指定版本"},
                        "version": {"type": "integer", "description": "[仅 action=backup, backup_action=restore] 要恢复的版本号，不传则恢复最新版"},

                        # ---- [仅 action=uses] 参数 ----
                        "uses_action": {"type": "string", "enum": ["add", "remove"], "description": "[仅 action=uses] uses子句操作: add=添加单元, remove=删除单元"},
                        "unit_name": {"type": "string", "description": "[仅 action=uses] 单元名，如 Vcl.Dialogs、System.SysUtils"},
                        "uses_section": {"type": "string", "enum": ["interface", "implementation"], "default": "interface", "description": "[仅 action=uses] uses子句所在区域: interface 或 implementation"},
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
                        "action": {"type": "string", "enum": ["create_token", "init_labels", "create_issue", "close_issue", "add_comment", "list_issues", "git_clone", "git_add", "git_commit", "git_push", "git_push_retry", "git_status"], "description": "操作类型: git_* 为 Git 本地操作（必须使用此工具，禁止用 bash 执行 git）；create_token/init_labels/create_issue 等为平台 API 操作"},
                        "base_url": {"type": "string", "description": "平台实例地址，如 https://code.qdac.cc:3000 (API 操作需要)"},
                        "token": {"type": "string", "description": "API 访问令牌 (API 操作需要)"},
                        "repo": {"type": "string", "description": "仓库名，格式 owner/repo (API 操作需要)"},
                        "issue_number": {"type": "integer", "description": "工单编号 (close_issue/add_comment 需要)"},
                        "title": {"type": "string", "description": "工单标题 (create_issue 需要)"},
                        "body": {"type": "string", "description": "正文内容，支持 Markdown (create_issue/add_comment 需要)"},
                        "labels": {"type": "array", "items": {"type": "string"}, "description": "标签名称列表 (create_issue 可选)"},
                        "comment": {"type": "string", "description": "关闭工单时的说明 (close_issue 可选)"},
                        "state": {"type": "string", "enum": ["open", "closed", "all"], "description": "工单过滤状态 (list_issues 可选，默认 open)"},
                        "username": {"type": "string", "description": "用户名 (create_token 需要)"},
                        "password": {"type": "string", "description": "密码 (create_token 需要)"},
                        "token_name": {"type": "string", "description": "Token 名称 (create_token 可选，默认 delphi-mcp)"},
                        # Git 操作参数
                        "dir": {"type": "string", "description": "Git 仓库本地路径 (git_* 操作需要)"},
                        "repo_url": {"type": "string", "description": "远程仓库 URL (git_clone 需要)"},
                        "mirror": {"type": "string", "description": "GitHub 镜像源地址，如 https://hub.fastgit.xyz (git_clone 可选)"},
                        "branch": {"type": "string", "description": "分支名 (git_clone/git_push 可选)"},
                        "message": {"type": "string", "description": "提交信息 (git_commit 需要)"},
                        "files": {"type": "array", "items": {"type": "string"}, "description": "要 add 的文件列表 (git_add 需要)"},
                        "remote": {"type": "string", "description": "远程名称 (git_push/git_push_retry 可选，默认 origin)"},
                        "retry_interval": {"type": "integer", "description": "重试间隔秒数 (git_push_retry 可选，默认 300)"},
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
                            "description": "工具名",
                        },
                    },
                    "required": ["tool_name"],
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
                            "enum": ["save", "search", "get", "list", "update", "merge", "prune", "delete"],
                            "description": "操作类型: save=保存经验(自动去重), search=语义搜索, get=查看详情, list=浏览列表, update=更新, merge=合并多条, prune=列出低价值待清理条目, delete=删除",
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
        action = arguments.get("action", "search")
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
                if not directory:
                    detected = _auto_detect_delphi_help_dir()
                    if detected:
                        directory = detected
                        logger.info(f"自动检测到 Delphi 帮助目录: {directory}")
                    else:
                        logger.warning("未提供 directory 且未检测到 Delphi 帮助目录")
                task_params = {"urls": arguments.get("urls", []), "directory": directory,
                               "extensions": arguments.get("extensions", [".chm"]),
                               "start_url": arguments.get("start_url"), "max_pages": arguments.get("max_pages", 100),
                               "max_depth": arguments.get("max_depth", 3), "domain_filter": arguments.get("domain_filter"),
                               "url_pattern": arguments.get("url_pattern"), "exclude": arguments.get("exclude"),
                               "rebuild": arguments.get("rebuild", False)}
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
        return get_tool_help(tool_name=arguments.get("tool_name", ""))

    async def _handle_experience(arguments: dict) -> dict:
        return _experience(**arguments)

    _TOOL_HANDLERS = {
        "project": _handle_project_tool,
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

            # P3: API 调用日志（排除注入的 _on_complete 回调，防止 json.dumps 序列化函数报错）
            _log_args = {k: v for k, v in arguments.items() if k != '_on_complete'}
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
            log_api_call(logger, name, arguments, {"error": str(e)})
            logger.error(f"工具调用失败: {str(e)}", exc_info=True)
            import json as _json
            return CallToolResult(
                content=[TextContent(type="text", text=_json.dumps(error_result, ensure_ascii=False, indent=2))],
                isError=True
            )

    # 注册 MCP 资源
    _resources_dir = project_root / "config"

    @server.list_resources()
    async def list_resources():
        """列出可用资源"""
        resources = []
        coding_rules_path = _resources_dir / "CODING_RULES.mdc"
        if coding_rules_path.exists():
            resources.append(Resource(
                uri="delphi://coding-rules",
                name="CODING_RULES",
                title="Delphi 编码规范",
                description="Delphi 源码编码规则，包含命名规范、格式化、类型声明顺序、修改/审核代码规则等",
                mimeType="text/markdown"
            ))
        return resources

    @server.read_resource()
    async def read_resource(uri: str):
        """读取资源内容"""
        from pydantic import AnyUrl  # pydantic import 延迟以避免不必要的依赖加载

        if uri == "delphi://coding-rules":
            rules_path = _resources_dir / "CODING_RULES.mdc"
            if rules_path.exists():
                with open(rules_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return ReadResourceResult(
                    contents=[TextResourceContents(
                        uri=AnyUrl(uri),
                        mimeType="text/markdown",
                        text=content
                    )]
                )
            return ReadResourceResult(
                contents=[TextResourceContents(
                    uri=AnyUrl(uri),
                    text="编码规则文件不存在"
                )]
            )
        raise ValueError(f"未知资源: {uri}")

    # 启动服务器
    logger.info("MCP Server 启动完成,准备接收请求...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
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
    logger.info("资源清理完成")


def main():
    """主函数"""
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("服务器已停止")
    except Exception as e:
        logger.error(f"服务器运行失败: {str(e)}", exc_info=True)
        sys.exit(1)
    finally:
        _cleanup_resources()


if __name__ == "__main__":
    main()
