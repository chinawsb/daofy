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
from src.tools.config import set_compiler_config, set_config_manager, search_compilers
from src.tools.environment import check_environment, set_config_manager as scm, set_thirdparty_kb_service as stks
from src.tools.knowledge_base import (
    set_knowledge_base_service,
    set_delphi_kb_service,
    set_project_kb_service,
    set_thirdparty_kb_service,
    set_help_kb_service,
    build_knowledge,
    search_class,
    search_function,
    semantic_search,
    get_knowledge_stats,
    list_delphi_versions,
    search_knowledge,
    build_unified_knowledge_base,
    get_unified_knowledge_stats
)
from src.tools.read_source_file import set_knowledge_base_services, read_source_file, search_and_read_file
from src.tools import knowledge_base as kb_tools
from src.tools import project_knowledge_base as project_kb_tools
from src.tools import help_knowledge_base as help_kb_tools
from src.tools import thirdparty_knowledge_base as thirdparty_kb_tools
from src.tools import analyze_dependencies as dep_tools
from src.tools import coding_rules
from src.tools import async_tasks as async_tools
from src.tools import pasfmt
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

    # 设置工具的服务实例
    sp1(compiler_service)
    sp2(compiler_service)
    sp3(compiler_service)
    scm(config_manager)
    stks(thirdparty_kb_service)
    set_knowledge_base_service(kb_service)
    set_knowledge_base_services(kb_service, thirdparty_kb_service)
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
                description="【编译/检查】构建项目或检查单个文件语法。用于：1)验证代码修改后能否编译通过 2)生成可执行文件 3)排查编译错误 4)快速检查文件语法。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目文件路径(.dproj/.dpr)或PAS文件路径 [必需]"},
                        "target_platform": {"type": "string", "enum": ["win32", "win64"], "default": "win32", "description": "目标平台"},
                        "build_configuration": {"type": "string", "default": "Debug", "description": "构建配置"},
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
                description="【搜索首选】搜索代码/API/文档的统一入口。支持：类/函数/属性搜索、语义搜索、查看统计。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["search", "stats", "build"], "default": "search", "description": "操作: search=搜索, stats=查看统计, build=构建知识库"},
                        "kb_type": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty", "help"], "default": "all", "description": "知识库: all=全部, delphi=官方, project=项目, thirdparty=第三方, help=帮助"},
                        "search_type": {"type": "string", "enum": ["all", "class", "function", "semantic", "fuzzy", "record", "filename", "property", "method", "field", "event", "uses", "const"], "default": "semantic", "description": "搜索类型: fuzzy=模糊匹配(反转字符串), 支持中英文关键词"},
                        "query": {"type": "string", "description": "搜索内容，如 'TStringList' 或 'TButton Click事件'"},
                        "project_path": {"type": "string", "description": "项目路径 (action=build 或 kb_type包含project时需要)"},
                        "version": {"type": "string", "description": "Delphi版本，如 '23.0'"},
                        "async_mode": {"type": "boolean", "default": True, "description": "是否异步执行"},
                        "force_rebuild": {"type": "boolean", "default": False, "description": "是否强制重建"},
                        "top_k": {"type": "integer", "default": 10, "description": "返回结果数量"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="read_source_file",
                description="【读取源码】读取指定文件内容，或搜索后读取。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径 (支持绝对/相对路径)"},
                        "start_line": {"type": "integer", "default": 1, "description": "起始行号"},
                        "max_lines": {"type": "integer", "default": 200, "description": "返回行数"},
                        "search_type": {"type": "string", "enum": ["path", "class", "function"], "default": "path", "description": "读取方式: path=文件路径, class=搜索类名, function=搜索函数名"},
                        "type_name": {"type": "string", "description": "类名 (search_type=class时需要)"},
                        "function_name": {"type": "string", "description": "函数名 (search_type=function时需要)"},
                        "search_in": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty"], "default": "all", "description": "搜索范围"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="check_environment",
                description="【环境诊断】诊断编译环境、检测Delphi编译器、安装配置工具。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["check", "detect", "install", "format_install"], "default": "check", "description": "操作: check=诊断环境, detect=检测编译器, install=安装pasfmt, format_install=安装IDE插件"},
                        "search_path": {"type": "string", "description": "自定义搜索路径"},
                        "install_dir": {"type": "string", "description": "安装目录"},
                        "delphi_version": {"type": "string", "description": "Delphi版本 (11,12,13)"},
                        "delphi_install_dir": {"type": "string", "description": "Delphi安装目录"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="format_delphi",
                description="【代码格式化】格式化Delphi源码文件或代码字符串。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["file", "code", "check", "set_path", "status"], "default": "file", "description": "操作: file=格式化文件, code=格式化代码, check=检查格式, set_path=设置路径, status=检查安装状态"},
                        "file_path": {"type": "string", "description": "文件路径 (action=file/check时需要)"},
                        "code": {"type": "string", "description": "代码字符串 (action=code时需要)"},
                        "config_path": {"type": "string", "description": "配置文件路径"},
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
                description="【后台任务】管理异步任务，如构建大型知识库。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["start", "status", "result", "list", "cancel"], "default": "list", "description": "操作: start=启动, status=查状态, result=查结果, list=列表, cancel=取消"},
                        "task_type": {"type": "string", "enum": ["build_knowledge", "build_project_knowledge"], "description": "任务类型 (action=start时需要)"},
                        "task_params": {"type": "object", "description": "任务参数"},
                        "task_id": {"type": "string", "description": "任务ID"},
                        "show_progress": {"type": "boolean", "default": True, "description": "是否显示进度"}
                    },
                    "required": []
                }
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """调用工具"""
        logger.info(f"调用工具: {name}")

        try:
            if name == "compile_project":
                # 合并 compile_file, get_compiler_args
                proj_path = arguments.get("project_path", "")
                if proj_path.lower().endswith(('.pas', '.dpr')):
                    # 文件模式：检查语法
                    result = await compile_file(**arguments)
                elif arguments.get("get_args_only"):
                    # 仅获取参数
                    result = await get_compiler_args(**arguments)
                else:
                    # 项目模式：编译
                    result = await compile_project.compile_project(**arguments)
            
            elif name == "search_knowledge":
                # 统一搜索接口：search/stats/build
                action = arguments.get("action", "search")
                if action == "search":
                    result = await kb_tools.search_knowledge(arguments)
                elif action == "stats":
                    result = await kb_tools.get_unified_knowledge_stats(arguments)
                elif action == "build":
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
                # 合并 search_compilers
                action = arguments.get("action", "check")
                if action == "detect":
                    result = await search_compilers(**arguments)
                elif action == "check":
                    result = await check_environment()
                else:
                    result = {"error": f"未知action: {action}"}
            
            elif name == "format_delphi":
                # 合并 format_delphi_file, format_delphi_code, set_pasfmt_path, install_pasfmt, check_pasfmt_installation
                action = arguments.get("action", "file")
                if action == "file":
                    result = await pasfmt.format_file(**arguments)
                elif action == "code":
                    result = await pasfmt.format_code(**arguments)
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
                        result = await pasfmt.check_pasfmt_rad_installation(**arguments)
                    else:
                        result = await pasfmt.check_pasfmt_installation(**arguments)
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
