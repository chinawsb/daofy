"""
Delphi MCP Server 主程序

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
        pass

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
    from mcp.types import CallToolResult, TextContent

    from src.services.config_manager import ConfigManager
    from src.services.compiler_service import CompilerService
    from src.services.knowledge_base import DelphiKnowledgeBaseService
    from src.services.knowledge_base.thirdparty_knowledge_base import ThirdPartyKnowledgeBase
    from src.tools.compile_project import set_compiler_service as sp1, compile_project
    from src.tools.compile_file import set_compiler_service as sp2, compile_file
    from src.tools.get_args import set_compiler_service as sp3, get_compiler_args
    from src.tools.config import set_config_manager, search_compilers
    from src.tools.environment import check_environment, set_config_manager as scm, set_thirdparty_kb_service as stks
    from src.tools.knowledge_base import (
        set_delphi_kb_service,
        set_thirdparty_kb_service,
        search_knowledge,
        build_unified_knowledge_base,
        get_unified_knowledge_stats
    )
    from src.tools.read_source_file import set_knowledge_base_services, read_source_file, search_and_read_file
    from src.tools import knowledge_base as kb_tools
    from src.tools import thirdparty_knowledge_base as thirdparty_kb_tools
    from src.tools import async_tasks as async_tools
    from src.tools import pasfmt
    from src.tools.install_package import install_package, list_installed_packages, set_compiler_service as sip
    from src.tools import document_kb_tools as doc_tools
    from src.tools.code_hosting import code_hosting
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
    for ver in ["37.0", "23.0", "22.0", "21.0", "20.0", "19.0", "18.0", "17.0", "16.0", "15.0", "14.0", "12.0", "11.0", "10.0", "9.0", "8.0", "7.0", "6.0", "5.0", "4.0", "3.0"]:
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
    if name == "compile_project":
        proj_path = arguments.get("project_path", "")
        is_pas = proj_path.lower().endswith('.pas')
        if isinstance(result, CallToolResult):
            is_error = result.isError
        elif isinstance(result, dict):
            is_error = (
                result.get('status') == 'failed'
                or result.get('success') is False
                or 'error' in result
            )
        else:
            is_error = False

        if is_error:
            if is_pas:
                return ("✨ 提示：编译失败。试试：\n"
                        "  check_environment(action='detect') — 重新检测编译器\n"
                        "  compile_project(..., get_args_only=True) — 预览编译参数")
            return ("✨ 提示：编译失败。试试：\n"
                    "  check_environment(action='detect') — 重新检测编译器\n"
                    "  check_environment(action='check') — 检查编译环境\n"
                    "  compile_project(..., get_args_only=True) — 预览编译参数")
        elif not is_pas and not arguments.get("get_args_only"):
            return ("✨ 提示：建议用 format_delphi(action='file', file_path=...) "
                    "统一格式化代码风格")

    elif name == "delphi_kb":
        action = arguments.get("action", "search")
        if action == "search":
            if isinstance(result, dict):
                results = result.get('results') or result.get('data') or []
                if isinstance(results, list) and len(results) > 0:
                    return ("✨ 提示：找到目标后，可用 "
                            "read_source_file 读取完整源码定义")
        elif action == "stats":
            return ("✨ 提示：如果知识库数据过期，"
                    "可用 delphi_kb(action='build', kb_type='project') 重建")

    elif name == "get_coding_rules":
        # 仅在 section=None（默认模式）时提示
        section = arguments.get("section")
        if section is None or section == "":
            return ("✨ 提示：使用 section 参数按需获取对应章节：\n"
                    '   get_coding_rules(section="writing")  — 写代码前看编码规则\n'
                    '   get_coding_rules(section="review")   — 编译后看审核表\n'
                    '   get_coding_rules(section="safety")   — 安全敏感操作')

    elif name == "check_environment":
        action = arguments.get("action", "check")
        if action == "detect" or action == "check":
            if isinstance(result, dict):
                compilers = result.get('compilers') or result.get('data')
                if compilers and len(compilers) > 0:
                    return ("✨ 提示：环境已就绪，"
                            "可用 compile_project 开始编译验证")
                else:
                    return ("✨ 提示：未检测到编译器，"
                            "请检查 Delphi 是否已安装，"
                            "或用 check_environment(action='detect', search_path=...) 指定自定义路径")

    elif name == "install_package":
        if isinstance(result, CallToolResult):
            is_error = result.isError
        elif isinstance(result, dict):
            is_error = (
                result.get('status') == 'failed'
                or result.get('success') is False
                or 'error' in result
            )
        else:
            is_error = False
        if not is_error:
            return ("✨ 提示：安装完成，"
                    "可用 list_installed_packages 验证组件已注册到 IDE")

    return None


async def run_server():
    """运行 MCP Server"""
    logger.info(f"启动 Delphi MCP Server v{__version__}")
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
    logger.info("工具服务实例设置完成")

    # 创建 MCP Server 实例
    server = Server("delphi-mcp-server")
    logger.info("MCP Server 实例创建完成")

    # 注册工具 (精简版)
    @server.list_tools()
    async def list_tools():
        """列出所有可用工具"""
        from mcp.types import Tool
        return [
            Tool(
                name="compile_project",
                description="【优先级 ⭐⭐⭐】编译/检查 — 构建 Delphi\n"
                            "【触发词】编译、构建、生成exe、语法检查、编译报错、build、compile、msbuild、dcc32\n"
                            "❌ 不得用 bash/cmd 运行 dcc32/msbuild（绕过 MSBuild/事件/依赖）\n"
                            "✅ 编译 .dproj/.dpr/.dpk 或检查 .pas 语法必须用此\n"
                            "【协作链】get_coding_rules→写代码→compile→失败→check_environment\n"
                            "【降级】MSBuild 不可用→dcc32；get_args_only 预览参数\n"
                            "【示例】\n"
                            '   compile_project(build_configuration="Release")  # "编译Release版本"\n'
                            '   compile_project(target_platform="win64")        # "生成64位exe"\n'
                            '   compile_project(project_path="unit.pas")        # "检查语法"\n'
                            '   compile_project(get_args_only=True)             # "只看参数不执行"',
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目文件路径(.dproj/.dpr/.dpk)或PAS文件路径 [必需]"},
                        "target_platform": {"type": "string", "enum": ["win32", "win64", "osx64", "osxarm64", "iosdevice64", "iosdevice", "iossimulator", "android", "android64", "linux64"], "default": "win32", "description": "目标平台"},
                        "build_configuration": {"type": "string", "default": "Debug", "description": "构建配置(Debug/Release)"},
                        "output_path": {"type": "string", "description": "输出目录"},
                        "compiler_version": {"type": "string", "description": "编译器版本名称（可选，不传时自动检测）"},
                        "conditional_defines": {"type": "array", "items": {"type": "string"}, "description": "条件编译符号列表"},
                        "unit_search_paths": {"type": "array", "items": {"type": "string"}, "description": "单元搜索路径列表"},
                        "resource_search_paths": {"type": "array", "items": {"type": "string"}, "description": "资源搜索路径列表"},
                        "optimization_enabled": {"type": "boolean", "default": True, "description": "是否启用优化"},
                        "debug_info_enabled": {"type": "boolean", "default": True, "description": "是否包含调试信息"},
                        "warning_level": {"type": "integer", "default": 2, "description": "警告级别(0-4)"},
                        "disabled_warnings": {"type": "array", "items": {"type": "string"}, "description": "禁用的警告列表"},
                        "output_type": {"type": "string", "default": "gui", "enum": ["console", "gui", "dll"], "description": "输出类型"},
                        "runtime_library": {"type": "string", "default": "static", "enum": ["static", "dynamic"], "description": "运行时库链接方式"},
                        "timeout": {"type": "integer", "default": 600, "description": "超时秒数"},
                        "install_if_design_package": {"type": "boolean", "default": True, "description": "设计期包是否自动安装"},
                        "get_args_only": {"type": "boolean", "default": False, "description": "仅返回编译参数，不执行编译"}
                    },
                    "required": ["project_path"]
                }
            ),
            # ===== 代码托管平台统一工具 =====
            Tool(
                name="code_hosting",
                description="【代码托管平台】统一操作 Gitea / GitHub / GitLab + Git 本地操作\n"
                            "通过 platform 切换后端(gitea/github/gitlab)，action 选择操作。\n"
                            "\n"
                            "▶ 平台 API 操作:\n"
                            '  code_hosting(platform="gitea", action="create_issue", ...)\n'
                            '  code_hosting(platform="github", action="create_issue", ...)\n'
                            "\n"
                            "▶ Git 本地操作（无需 platform）:\n"
                            '  code_hosting(action="git_clone", repo_url="...", mirror="镜像源")\n'
                            '  code_hosting(action="git_commit", work_dir=".", commit_message="...")\n'
                            "\n"
                            "▶ GitHub 国内访问:\n"
                            "  拉取: git_clone 支持 mirror 参数指定镜像源\n"
                            "  推送: 依赖用户自身的 SSH/HTTPS 代理配置，工具不做假设\n"
                            "\n"
                            "▶ action 列表:\n"
                            "  create_token | init_labels | create_issue | close_issue\n"
                            "  add_comment | list_issues\n"
                            "  --- 同步操作 ---\n"
                            "  git_status | git_add | git_commit\n"
                            "  --- 异步操作（后台执行，返回 task_id） ---\n"
                            "  git_clone | git_push | git_push_retry\n"
                            "  --- 查询异步任务状态 ---\n"
                            '  async_task(action="status", task_id="...")',
                inputSchema={
                    "type": "object",
                    "properties": {
                        "platform": {"type": "string", "enum": ["gitea", "github", "gitlab"], "description": "平台类型（API 操作需要，Git 本地操作不需要）"},
                        "action": {"type": "string", "description": "操作类型: create_token, init_labels, create_issue, close_issue, add_comment, list_issues, git_clone, git_add, git_commit, git_push, git_status, sync_to_github"},
                        "base_url": {"type": "string", "description": "平台实例地址，如 https://code.qdac.cc:3000 (API 操作需要)"},
                        "token": {"type": "string", "description": "API 访问令牌 (API 操作需要)"},
                        "repo": {"type": "string", "description": "仓库名，格式 owner/repo (API 操作需要)"},
                        "issue_number": {"type": "integer", "description": "工单编号 (close_issue/add_comment 需要)"},
                        "title": {"type": "string", "description": "工单标题 (create_issue 需要)"},
                        "body": {"type": "string", "description": "正文内容，支持 Markdown (create_issue/add_comment 需要)"},
                        "label_names": {"type": "array", "items": {"type": "string"}, "description": "标签名称列表 (create_issue 可选)"},
                        "comment_body": {"type": "string", "description": "关闭工单时的说明 (close_issue 可选)"},
                        "state": {"type": "string", "enum": ["open", "closed", "all"], "description": "工单过滤状态 (list_issues 可选，默认 open)"},
                        "username": {"type": "string", "description": "用户名 (create_token 需要)"},
                        "password": {"type": "string", "description": "密码 (create_token 需要)"},
                        "token_name": {"type": "string", "description": "Token 名称 (create_token 可选，默认 delphi-mcp)"},
                        # Git 操作参数
                        "work_dir": {"type": "string", "description": "Git 仓库本地路径 (git_* 操作需要)"},
                        "repo_url": {"type": "string", "description": "远程仓库 URL (git_clone 需要)"},
                        "mirror": {"type": "string", "description": "GitHub 镜像源地址，如 https://hub.fastgit.xyz (git_clone 可选)"},
                        "branch": {"type": "string", "description": "分支名 (git_clone/git_push 可选)"},
                        "commit_message": {"type": "string", "description": "提交信息 (git_commit 需要)"},
                        "files": {"type": "array", "items": {"type": "string"}, "description": "要 add 的文件列表 (git_add 需要)"},
                        "remote_name": {"type": "string", "description": "远程名称 (git_push/git_push_retry 可选，默认 origin)"},
                        "retry_interval": {"type": "integer", "description": "重试间隔秒数 (git_push_retry 可选，默认 300)"},
                        "task_id": {"type": "string", "description": "异步任务ID (git_task_status 需要)"},
                    },
                    "required": ["action"]
                }
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """调用工具"""
        logger.info(f"调用工具: {name}")
        result = None
        
        try:
            if name == "compile_project":
                # 合并 compile_file, get_compiler_args
                proj_path = arguments.get("project_path", "")
                if proj_path.lower().endswith('.pas'):
                    # 文件模式：检查语法
                    result = await compile_file(
                        file_path=proj_path,
                        unit_search_paths=arguments.get('unit_search_paths'),
                        warning_level=arguments.get('warning_level', 2),
                        disabled_warnings=arguments.get('disabled_warnings'),
                        compiler_version=arguments.get('compiler_version'),
                    )
                elif arguments.get("get_args_only"):
                    # 仅获取参数 — 过滤出 get_compiler_args 接受的参数
                    _ACCEPTED_GET_ARGS_KEYS = {
                        "project_path", "target_platform", "output_path", "compiler_version",
                        "conditional_defines", "unit_search_paths", "resource_search_paths",
                        "optimization_enabled", "debug_info_enabled", "warning_level",
                        "disabled_warnings", "output_type", "runtime_library", "build_configuration",
                    }
                    filtered = {k: v for k, v in arguments.items() if k in _ACCEPTED_GET_ARGS_KEYS}
                    result = await get_compiler_args(**filtered)
                else:
                    # 项目模式：编译
                    result = await compile_project(**arguments)
            
            elif name == "delphi_kb":
                action = arguments.get("action", "search")
                kb_type = arguments.get("kb_type", "all")
                
                if action == "search":
                    if kb_type == "document":
                        result = await doc_tools.search_documents(arguments)
                    else:
                        result = await kb_tools.search_knowledge(arguments)
                elif action == "stats":
                    if kb_type == "document":
                        result = await doc_tools.get_document_statistics(arguments)
                    else:
                        result = await kb_tools.get_unified_knowledge_stats(arguments)
                elif action == "build":
                    # action=build 需要数分钟到数十分钟，自动使用异步任务方式
                    from src.tools.async_tasks import start_async_task
                    async_mode = arguments.get("async_mode", True)
                    if async_mode:
                        # 异步模式：启动后台任务并立即返回 task_id，让 AI 轮询进度
                        version = arguments.get("version")
                        force_rebuild = arguments.get("force_rebuild", False)
                        
                        # 根据 kb_type 决定任务类型
                        if kb_type in ["all", "delphi"]:
                            task_type = "build_knowledge_base"
                        elif kb_type == "thirdparty":
                            task_type = "build_thirdparty_knowledge_base"
                        elif kb_type == "project":
                            task_type = "init_project_knowledge_base"
                        elif kb_type == "document":
                            # 文档知识库构建
                            task_type = "build_document_knowledge_base"
                        else:
                            task_type = "build_knowledge_base"
                        
                        incremental = arguments.get("incremental", False)
                        
                        # 根据任务类型准备参数
                        if task_type == "build_document_knowledge_base":
                            directory = arguments.get("directory")
                            if not directory:
                                detected = _auto_detect_delphi_help_dir()
                                if detected:
                                    directory = detected
                                    logger.info(f"自动检测到 Delphi 帮助目录: {directory}")
                                else:
                                    logger.warning("未提供 directory 且未检测到 Delphi 帮助目录")
                            task_params = {
                                "urls": arguments.get("urls", []),
                                "directory": directory,
                                "extensions": arguments.get("extensions", [".chm"]),
                                "start_url": arguments.get("start_url"),
                                "max_pages": arguments.get("max_pages", 100),
                                "max_depth": arguments.get("max_depth", 3),
                                "domain_filter": arguments.get("domain_filter"),
                                "url_pattern": arguments.get("url_pattern"),
                                "exclude_dirs": arguments.get("exclude_dirs"),
                                "force_rebuild": arguments.get("force_rebuild", False)
                            }
                        elif task_type == "init_project_knowledge_base":
                            from src.tools.knowledge_base import _resolve_project_path
                            resolved_path = _resolve_project_path(arguments.get("project_path"))
                            task_params = {
                                "project_path": resolved_path,
                                "version": version,
                                "force_rebuild": force_rebuild,
                                "build_thirdparty": arguments.get("build_thirdparty", True),
                                "build_project": arguments.get("build_project", True),
                            }
                        else:
                            task_params = {
                                "version": version,
                                "force_rebuild": force_rebuild,
                                "incremental": incremental
                            }
                        
                        task_result = await start_async_task({
                            "task_type": task_type,
                            "task_params": task_params,
                            "show_progress": arguments.get("show_progress", True)
                        })
                        result = task_result
                    else:
                        # 同步模式（非推荐）
                        result = await kb_tools.build_unified_knowledge_base(arguments)
                elif action == "build_embedding":
                    # 构建 embedding 向量（异步，避免模型加载超时）
                    from src.tools.knowledge_base import _resolve_project_path
                    pp = _resolve_project_path(arguments.get("project_path"))
                    if not pp:
                        result = {"error": "未检测到项目路径"}
                    else:
                        from src.tools.async_tasks import start_async_task
                        task_result = await start_async_task({
                            "task_type": "build_embedding",
                            "task_params": {"project_path": pp},
                            "show_progress": True
                        })
                        result = task_result
                elif action == "scan":
                    if kb_type == "document":
                        result = await doc_tools.scan_documents(arguments)
                    else:
                        result = {"error": f"action=scan 仅支持 kb_type=document"}
                elif action == "web":
                    if kb_type == "document":
                        result = await doc_tools.add_web_document(arguments)
                    else:
                        result = {"error": f"action=web 仅支持 kb_type=document"}
                elif action == "read":
                    url = arguments.get("url")
                    doc_id = arguments.get("doc_id")
                    file_path = arguments.get("file_path")
                    
                    if url or doc_id:
                        result = await doc_tools.read_document(arguments)
                    elif file_path:
                        result = await read_source_file(arguments)
                    else:
                        result = {"error": "action=read 需要 url/doc_id 或 file_path 参数"}
                else:
                    result = {"error": f"未知action: {action}"}
            
            elif name == "read_source_file":
                # 合并 search_and_read_file
                search_type = arguments.get("search_type", "path")
                if search_type == "path":
                    result = await read_source_file(arguments)
                else:
                    # 搜索模式
                    result = await search_and_read_file(arguments)
            
            elif name == "check_environment":
                # 合并 search_compilers, install_pasfmt, install_pasfmt_rad
                action = arguments.get("action", "check")
                if action == "detect":
                    result = await search_compilers(search_path=arguments.get("search_path"))
                elif action == "check":
                    result = await check_environment()
                elif action == "install":
                    result = await pasfmt.download_and_install_pasfmt(install_dir=arguments.get("install_dir"))
                elif action == "format_install":
                    result = await pasfmt.download_and_install_pasfmt_rad(
                        delphi_version=arguments.get("delphi_version", "11"),
                        install_dir=arguments.get("install_dir"),
                    )
                else:
                    result = {"error": f"未知action: {action}"}
            
            elif name == "format_delphi":
                # 合并 format_delphi_file, format_delphi_code, set_pasfmt_path, install_pasfmt, check_pasfmt_installation
                action = arguments.get("action", "file")
                if action == "file":
                    result = await pasfmt.format_file(
                        file_path=arguments.get("file_path", ""),
                        config_path=arguments.get("config_path"),
                        backup=arguments.get("backup", True),
                        in_place=arguments.get("in_place", True),
                        uses_style=arguments.get("uses_style"),
                    )
                elif action == "code":
                    result = await pasfmt.format_code(
                        code=arguments.get("code", ""),
                        config_path=arguments.get("config_path"),
                        uses_style=arguments.get("uses_style"),
                    )
                elif action == "check":
                    result = await pasfmt.format_file(file_path=arguments.get("file_path"), check_only=True)
                elif action == "set_path":
                    path = arguments.get("path")
                    if path:
                        pasfmt.set_pasfmt_path(path)
                        result = {"message": f"pasfmt 路径已设置为: {path}"}
                    else:
                        result = {"message": "未提供 pasfmt 路径"}
                elif action == "status":
                    check_rad = arguments.get("check_rad", False)
                    if check_rad:
                        result = await pasfmt.check_pasfmt_rad_installation(
                            delphi_version=arguments.get("delphi_version", "11")
                        )
                    else:
                        result = await pasfmt.check_pasfmt_installation()
                else:
                    result = {"error": f"未知action: {action}"}
            
            elif name == "async_task":
                # 合并 start_async_task, get_task_status, get_task_result, list_tasks, cancel_task
                action = arguments.get("action", "list")
                if action == "start":
                    result = await async_tools.start_async_task(arguments)
                elif action == "status":
                    result = await async_tools.get_task_status(arguments)
                elif action == "result":
                    result = await async_tools.get_task_result(arguments)
                elif action == "list":
                    result = await async_tools.list_tasks(arguments)
                elif action == "cancel":
                    result = await async_tools.cancel_task(arguments)
                else:
                    result = {"error": f"未知action: {action}"}
            
            elif name == "install_package":
                result = await install_package(
                    package_path=arguments.get("package_path", ""),
                    target_platform=arguments.get("target_platform", "win32"),
                    build_configuration=arguments.get("build_configuration", "Debug"),
                    timeout=arguments.get("timeout", 300),
                    install=arguments.get("install", True)
                )
            
            elif name == "list_installed_packages":
                result = await list_installed_packages()
            
            elif name == "get_coding_rules":
                from src.tools.coding_rules import get_coding_rules
                result = await get_coding_rules(
                    project_path=arguments.get("project_path"),
                    section=arguments.get("section")
                )

            elif name == "code_hosting":
                result = code_hosting(**arguments)

            else:
                raise ValueError(f"未知工具: {name}")

            # ============================================================
            # P2: 智能提示 — 在工具返回结果中注入下一步建议
            # ============================================================
            hint = _get_smart_hint(name, result, arguments)
            if hint:
                if isinstance(result, CallToolResult):
                    if result.content and hasattr(result.content[0], 'text'):
                        original_text = result.content[0].text
                        result.content[0].text = original_text + "\n\n" + hint
                elif isinstance(result, dict):
                    msg = result.get('message', '')
                    if isinstance(msg, str):
                        result['message'] = msg + "\n\n" + hint

            # ============================================================
            # P3: API 调用日志 (受 log_api_calls 开关控制)
            # ============================================================
            log_api_call(logger, name, arguments, result)

            # 统一返回格式：确保返回 CallToolResult
            if isinstance(result, dict):
                text = str(result.get('message', str(result)))
                is_error = (
                    result.get('status') == 'failed'
                    or result.get('success') is False
                    or 'error' in result
                )
                return CallToolResult(content=[TextContent(type="text", text=text)], isError=is_error)
            else:
                return result

        except Exception as e:
            # 异常也记录到 API 日志
            log_api_call(logger, name, arguments, {"error": str(e)})
            logger.error(f"工具调用失败: {str(e)}", exc_info=True)
            return CallToolResult(
                content=[TextContent(type="text", text=f"错误: {str(e)}")],
                isError=True
            )

    # 注册 MCP 资源
    _resources_dir = project_root / "config"

    @server.list_resources()
    async def list_resources():
        """列出可用资源"""
        from mcp.types import Resource
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
        from mcp.types import ReadResourceResult, TextResourceContents
        from pydantic import AnyUrl

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
    """清理资源：关闭后台任务、DB连接等"""
    logger.info("清理资源中...")
    try:
        from src.tools.knowledge_base import _cleanup_pkb_cache
        _cleanup_pkb_cache()
    except Exception:
        logger.warning("清理资源时发生异常", exc_info=True)
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
