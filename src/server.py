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
from pathlib import Path
from typing import Any
import io

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=False)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=False)

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
_is_multiprocessing_child = (
    '--multiprocessing-fork' in sys.argv or
    os.environ.get('_IN_PROCESS_POOL_WORKER') == '1' or
    __name__ == '__mp_main__'
)

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
        set_project_kb_service,
        set_thirdparty_kb_service,
        set_help_kb_service,
        search_knowledge,
        build_unified_knowledge_base,
        get_unified_knowledge_stats
    )
    from src.services.knowledge_base.help_knowledge_base import DelphiHelpKnowledgeBase
    from src.tools.read_source_file import set_knowledge_base_services, read_source_file, search_and_read_file
    from src.tools import knowledge_base as kb_tools
    from src.tools import help_knowledge_base as help_kb_tools
    from src.tools import thirdparty_knowledge_base as thirdparty_kb_tools
    from src.tools import async_tasks as async_tools
    from src.tools import pasfmt
    from src.tools.install_package import install_package, list_installed_packages, set_compiler_service as sip
    from src.utils.logger import init_default_logger, get_logger
    from src.__version__ import __version__, __copyright__

    # 初始化日志
    logger = init_default_logger()


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

    # 初始化帮助文档知识库服务
    help_kb_service = DelphiHelpKnowledgeBase()
    set_help_kb_service(help_kb_service)
    logger.info("帮助文档知识库服务初始化完成")

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
    set_project_kb_service(kb_service)
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
                description="【编译/检查】构建Delphi项目或检查单个文件语法。典型场景：1)修改代码后验证编译是否通过 2)生成可执行文件 3)排查编译错误 4)get_args_only=True仅获取编译参数不执行",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目文件路径(.dproj/.dpr)或PAS文件路径 [必需]"},
                        "target_platform": {"type": "string", "enum": ["win32", "win64"], "default": "win32", "description": "目标平台"},
                        "build_configuration": {"type": "string", "default": "Debug", "description": "构建配置(Debug/Release)"},
                        "output_path": {"type": "string", "description": "输出目录"},
                        "timeout": {"type": "integer", "default": 600, "description": "超时秒数"},
                        "debug_info_enabled": {"type": "boolean", "default": True, "description": "是否包含调试信息"},
                        "get_args_only": {"type": "boolean", "default": False, "description": "仅返回编译参数，不执行编译"}
                    },
                    "required": ["project_path"]
                }
            ),
            Tool(
                name="search_knowledge",
                description="【搜索/统计/构建】搜索Delphi代码/API/帮助文档。action=search按名称/语义搜索; action=stats查看知识库统计; action=build构建知识库(异步，用async_task轮询进度)。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["search", "stats", "build"], "default": "search", "description": "操作: search=搜索(快速), stats=查看统计(快速), build=构建知识库(异步，立即返回task_id)"},
                        "kb_type": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty", "help"], "default": "all", "description": "知识库: all=全部, delphi=官方, project=项目, thirdparty=第三方, help=帮助"},
                        "search_type": {"type": "string", "enum": ["all", "class", "record", "interface", "enum", "set", "type", "function", "procedure", "const", "resourcestring", "property", "field", "method", "unit", "semantic", "fuzzy", "filename", "event", "uses"], "default": "semantic", "description": "搜索类型: class=类, record=记录, interface=接口, enum=枚举, set=集合, type=类型别名, function=函数, procedure=过程, const=常量, resourcestring=资源字符串, property=属性, field=字段, method=方法, unit=单元, semantic=语义搜索, fuzzy=模糊匹配"},
                        "query": {"type": "string", "description": "搜索内容，如 'TStringList' 或 'TButton Click事件'"},
                        "project_path": {"type": "string", "description": "项目路径 (action=build 或 kb_type=project时需要)"},
                        "version": {"type": "string", "description": "Delphi版本，如 '23.0'"},
                        "async_mode": {"type": "boolean", "default": True, "description": "是否异步执行"},
                        "force_rebuild": {"type": "boolean", "default": False, "description": "是否强制重建"},
                        "incremental": {"type": "boolean", "default": False, "description": "增量构建(跳过解压CHM,仅help知识库支持)"},
                        "hash_mode": {"type": "string", "default": "mtime_size", "description": "增量hash模式: mtime_size(默认,快速) 或 md5(准确)"},
                        "top_k": {"type": "integer", "default": 10, "description": "返回结果数量 1-10"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="read_source_file",
                description="【读取源码】读取Delphi源文件内容，或按类名/函数名搜索后读取定义。典型场景：1)读取指定文件查看代码 2)搜索TButton类定义并读取 3)搜索Create函数并读取实现",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径 (支持绝对/相对路径)"},
                        "start_line": {"type": "integer", "default": 1, "description": "起始行号"},
                        "max_lines": {"type": "integer", "default": 200, "description": "返回行数"},
                        "search_type": {"type": "string", "enum": ["path", "class", "function"], "default": "path", "description": "读取方式: path=按文件路径, class=搜索类名后读取, function=搜索函数名后读取"},
                        "type_name": {"type": "string", "description": "类名 (search_type=class时需要)"},
                        "function_name": {"type": "string", "description": "函数名 (search_type=function时需要)"},
                        "search_in": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty"], "default": "all", "description": "搜索范围"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="check_environment",
                description="【环境诊断】诊断编译环境、检测Delphi编译器、安装pasfmt格式化工具。action=check诊断当前环境; action=detect检测编译器; action=install安装pasfmt; action=format_install安装pasfmt-rad IDE插件。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["check", "detect", "install", "format_install"], "default": "check", "description": "操作: check=诊断环境, detect=检测编译器, install=安装pasfmt, format_install=安装IDE插件"},
                        "search_path": {"type": "string", "description": "自定义搜索路径 (action=detect)"},
                        "install_dir": {"type": "string", "description": "安装目录 (action=install/format_install)"},
                        "delphi_version": {"type": "string", "description": "Delphi版本 (11/12/13, action=format_install)"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="format_delphi",
                description="【代码格式化】格式化Delphi源码文件或代码字符串。action=file格式化文件; action=code格式化代码字符串; action=check检查格式; action=status检查pasfmt安装状态。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["file", "code", "check", "set_path", "status"], "default": "file", "description": "操作: file=格式化文件, code=格式化代码, check=检查格式, set_path=设置pasfmt路径, status=检查安装状态"},
                        "file_path": {"type": "string", "description": "文件路径 (action=file/check时需要)"},
                        "code": {"type": "string", "description": "代码字符串 (action=code时需要)"},
                        "config_path": {"type": "string", "description": "格式化配置文件路径"},
                        "backup": {"type": "boolean", "default": True, "description": "是否创建备份"},
                        "in_place": {"type": "boolean", "default": True, "description": "是否原地修改"},
                        "path": {"type": "string", "description": "pasfmt路径 (action=set_path时需要)"},
                        "check_rad": {"type": "boolean", "default": False, "description": "检查IDE插件"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="async_task",
                description="【后台任务】管理长时间运行的后台任务(如构建知识库)。action=start启动任务; action=status查进度; action=result取结果; action=list列任务; action=cancel取消任务。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["start", "status", "result", "list", "cancel"], "default": "list", "description": "操作: start=启动后台任务, status=查状态(含进度), result=查结果, list=列表, cancel=取消"},
                        "task_type": {"type": "string", "enum": ["build_knowledge_base", "build_thirdparty_knowledge_base", "init_project_knowledge_base"], "description": "任务类型 (action=start时需要)"},
                        "task_params": {"type": "object", "description": "任务参数: version(Delphi版本), force_rebuild, project_path 等"},
                        "task_id": {"type": "string", "description": "任务ID (action=status/result/cancel时需要)"},
                        "show_progress": {"type": "boolean", "default": True, "description": "是否显示进度"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="install_package",
                description="【组件安装】编译并安装Delphi组件包(.dpk/.dproj)到IDE。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "package_path": {"type": "string", "description": "包文件路径(.dproj/.dpk/.groupproj)"},
                        "target_platform": {"type": "string", "enum": ["win32", "win64"], "default": "win32", "description": "目标平台"},
                        "build_configuration": {"type": "string", "default": "Debug", "description": "构建配置(Debug/Release)"},
                        "timeout": {"type": "integer", "default": 300, "description": "超时秒数"},
                        "install": {"type": "boolean", "default": True, "description": "是否自动安装到IDE"}
                    },
                    "required": ["package_path"]
                }
            ),
            Tool(
                name="list_installed_packages",
                description="【已安装包列表】列出已安装到IDE的Delphi组件包。",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            )
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
                        disabled_warnings=arguments.get('disabled_warnings')
                    )
                elif arguments.get("get_args_only"):
                    # 仅获取参数
                    args = {k: v for k, v in arguments.items() if k != "get_args_only"}
                    result = await get_compiler_args(**args)
                else:
                    # 项目模式：编译
                    result = await compile_project(**arguments)
            
            elif name == "search_knowledge":
                action = arguments.get("action", "search")
                if action == "search":
                    result = await kb_tools.search_knowledge(arguments)
                elif action == "stats":
                    result = await kb_tools.get_unified_knowledge_stats(arguments)
                elif action == "build":
                    # action=build 需要数分钟到数十分钟，自动使用异步任务方式
                    from src.tools.async_tasks import start_async_task
                    async_mode = arguments.get("async_mode", True)
                    if async_mode:
                        # 异步模式：启动后台任务并立即返回 task_id，让 AI 轮询进度
                        kb_type = arguments.get("kb_type", "all")
                        version = arguments.get("version")
                        force_rebuild = arguments.get("force_rebuild", False)
                        
                        # 根据 kb_type 决定任务类型
                        if kb_type in ["all", "delphi"]:
                            task_type = "build_knowledge_base"
                        elif kb_type == "thirdparty":
                            task_type = "build_thirdparty_knowledge_base"
                        elif kb_type == "project":
                            task_type = "init_project_knowledge_base"
                        elif kb_type == "help":
                            # 帮助知识库构建
                            result = await help_kb_tools.build_help_knowledge_base(arguments)
                            return result
                        else:
                            task_type = "build_knowledge_base"
                        
                        incremental = arguments.get("incremental", False)
                        
                        task_result = await start_async_task({
                            "task_type": task_type,
                            "params": {"version": version, "force_rebuild": force_rebuild, "incremental": incremental},
                            "show_progress": arguments.get("show_progress", True)
                        })
                        result = task_result
                    else:
                        # 同步模式（非推荐）
                        result = await kb_tools.build_unified_knowledge_base(arguments)
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
                    )
                elif action == "code":
                    result = await pasfmt.format_code(
                        code=arguments.get("code", ""),
                        config_path=arguments.get("config_path"),
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
                    result = await help_kb_tools.cancel_task(arguments)
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
            
            else:
                raise ValueError(f"未知工具: {name}")

            # 统一返回格式：确保返回 CallToolResult
            if isinstance(result, dict):
                text = str(result.get('message', str(result)))
                is_error = result.get('status') == 'failed' or result.get('success') == False
                return CallToolResult(content=[TextContent(type="text", text=text)], isError=is_error)
            else:
                return result

        except Exception as e:
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


def main():
    """主函数"""
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("服务器已停止")
    except Exception as e:
        logger.error(f"服务器运行失败: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
