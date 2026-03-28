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

    # 注册工具
    @server.list_tools()
    async def list_tools():
        """列出所有可用工具"""
        from mcp.types import Tool
        return [
            Tool(
                name="compile_project",
                description="【编译首选】构建项目生成.exe/.dll文件。当AI需要：1)验证代码修改后能否编译通过 2)生成可执行文件 3)排查编译错误时使用。此工具自动处理所有依赖路径，优先于手动调用dcc32/dcc64。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目文件路径，如 'C:\\MyProject\\MyProject.dproj' [必需]"},
                        "target_platform": {"type": "string", "enum": ["win32", "win64"], "default": "win32", "description": "目标平台: win32=32位, win64=64位"},
                        "build_configuration": {"type": "string", "default": "Debug", "description": "构建配置: Debug或Release"},
                        "output_path": {"type": "string", "description": "输出目录，不填则使用项目默认"},
                        "timeout": {"type": "integer", "default": 600, "description": "超时秒数，大项目可设为1200"},
                        "debug_info_enabled": {"type": "boolean", "default": True, "description": "是否包含调试信息"}
                    },
                    "required": ["project_path"]
                }
            ),
            Tool(
                name="compile_file",
                description="【快速检查】快速检查单个.pas文件语法错误。比compile_project快10倍，适合：修改完一个单元后立即检查、编写新代码时实时验证、只关心特定文件的错误。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Pas文件路径 [必需]"},
                        "unit_search_paths": {"type": "array", "items": {"type": "string"}, "description": "依赖单元路径，通常不需要填"}
                    },
                    "required": ["file_path"]
                }
            ),
            Tool(
                name="get_compiler_args",
                description="【调试用】仅生成编译命令供调试。当AI需要：1)手动执行编译 2)查看具体参数 3)排查编译配置问题时使用。不实际执行编译。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目路径 [必需]"},
                        "target_platform": {"type": "string", "enum": ["win32", "win64"], "default": "win32"},
                        "build_configuration": {"type": "string", "default": "Debug"}
                    },
                    "required": ["project_path"]
                }
            ),
            Tool(
                name="search_compilers",
                description="【自动检测】自动检测系统中安装的Delphi编译器。首次使用或编译器找不到时调用，返回可用的编译器列表及其路径。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "search_path": {"type": "string", "description": "自定义搜索路径，不填则自动搜索注册表"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="check_environment",
                description="【环境诊断】诊断编译环境问题。当编译失败、找不到编译器、或需要确认环境配置时调用。返回：编译器列表、第三方库路径、当前配置状态。",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="get_coding_rules",
                description="【规范参考】获取 Delphi 源码编码规则。当智能体需要修改或编写 Delphi 代码时，应先调用此工具了解项目的编码规范，包括命名约定、注释要求、代码格式等。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目路径（可选），用于查找用户自定义的编码规则文件"}
                    },
                    "required": []
                }
            ),

            # 统一知识库工具 (推荐)
            Tool(
                name="search_knowledge",
                description="【AI必用】搜索代码、API、文档的首选工具。当AI需要查找类定义、函数用法、API文档、代码示例时，优先使用此工具。适用于：查找VCL/FMX类用法、搜索第三方组件API、理解代码结构、获取代码示例。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "kb_type": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty", "help"], "default": "all", "description": "知识库: all=全部, delphi=官方源码, project=当前项目, thirdparty=第三方库, help=帮助文档"},
                        "search_type": {"type": "string", "enum": ["all", "class", "function", "semantic", "record", "filename"], "default": "semantic", "description": "搜索类型: semantic=语义搜索(推荐), class=类名, function=函数名, record=记录类型, filename=文件名"},
                        "query": {"type": "string", "description": "搜索内容，如 'TStringList' 或 'TButton Click事件用法' 或 'SendEmail函数'"},
                        "project_path": {"type": "string", "description": "项目路径 (kb_type包含project时需要)"},
                        "top_k": {"type": "integer", "default": 10, "description": "返回结果数量，建议5-20"}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="build_knowledge",
                description="【首次使用必调】初始化项目或构建知识库。当AI需要分析新项目、搜索项目代码、或编译前必须先调用此工具。提供project_path自动分析项目依赖并构建项目+第三方库知识库。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "kb_type": {"type": "string", "default": "all", "description": "知识库: all=全部, delphi=官方源码, project=项目源码, thirdparty=第三方库, help=帮助文档。可组合如'delphi,project'"},
                        "project_path": {"type": "string", "description": "项目文件路径(.dproj/.dpr)，必填！用于初始化项目知识库"},
                        "version": {"type": "string", "description": "Delphi版本号，如 '23.0'，不填则自动检测最新版本"},
                        "async_mode": {"type": "boolean", "default": True, "description": "是否异步执行，大项目建议true避免超时"},
                        "force_rebuild": {"type": "boolean", "default": False, "description": "是否强制重建，代码有变更时设为true"}
                    },
                    "required": ["project_path"]
                }
            ),
            Tool(
                name="get_knowledge_stats",
                description="【查询用】查看知识库状态。了解当前有哪些知识库可用、各自包含多少内容（类/函数/文件数量）。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "kb_type": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty", "help"], "default": "all", "description": "知识库类型: all=全部, delphi=官方, project=项目, thirdparty=第三方, help=帮助"},
                        "project_path": {"type": "string", "description": "项目路径 (kb_type包含project时需要)"}
                    },
                    "required": []
                }
            ),
            # 项目依赖分析工具
            Tool(
                name="analyze_project_dependencies",
                description="【项目分析】分析项目结构。当AI需要：1)了解模块划分和依赖关系 2)查找循环引用 3)确定编译顺序 4)清理无用单元时使用。返回单元依赖图和编译顺序。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目路径(.dproj/.dpr) [必需]"}
                    },
                    "required": ["project_path"]
                }
            ),
            Tool(
                name="resolve_smart_library_paths",
                description="【编译准备】获取项目依赖的第三方库路径列表。当compile_project失败提示找不到单元时，或需要手动配置搜索路径时调用。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目文件路径(.dpr 或 .dproj)"},
                        "platform": {"type": "string", "default": "Win32", "description": "目标平台: Win32 或 Win64"}
                    },
                    "required": ["project_path"]
                }
            ),
            # 源码文件读取工具
            Tool(
                name="read_source_file",
                description="【读取源码】直接读取指定文件内容。适用于：已知文件路径、需要查看具体实现、定位特定代码段。通过行号范围精确定位。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径，支持相对路径或绝对路径 [必需]"},
                        "start_line": {"type": "integer", "default": 1, "description": "起始行号(从1开始)"},
                        "max_lines": {"type": "integer", "default": 200, "description": "返回行数，最多1000"},
                        "search_in": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty"], "default": "all", "description": "知识库搜索范围"}
                    },
                    "required": ["file_path"]
                }
            ),
            Tool(
                name="search_and_read_file",
                description="【代码定位首选】先搜索后读取一体化工具。当AI需要：1)查找某个类/函数的定义位置 2)查看具体实现时，用此工具一次完成搜索+读取，比先用search_knowledge再用read_source_file更高效。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "type_name": {"type": "string", "description": "类名，如 'TStringList'"},
                        "function_name": {"type": "string", "description": "函数/过程名"},
                        "search_in": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty"], "default": "all", "description": "搜索范围: all=全部, delphi=官方, project=项目, thirdparty=第三方库"},
                        "max_lines": {"type": "integer", "default": 150, "description": "返回代码行数"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="start_async_task",
                description="【后台任务】启动异步任务以避免长时间操作超时。当需要构建大型知识库或执行耗时较长的操作时，使用此工具启动后台任务，然后通过 get_task_status 查询进度。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_type": {
                            "type": "string",
                            "enum": ["build_knowledge", "build_project_knowledge"],
                            "description": "任务类型"
                        },
                        "params": {
                            "type": "object",
                            "description": "任务参数（根据任务类型不同）"
                        },
                        "show_progress": {
                            "type": "boolean",
                            "default": True,
                            "description": "是否显示进度"
                        }
                    },
                    "required": ["task_type"]
                }
            ),
            Tool(
                name="get_task_status",
                description="获取异步任务状态",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "任务ID"}
                    },
                    "required": ["task_id"]
                }
            ),
            Tool(
                name="get_task_result",
                description="获取异步任务结果",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "任务ID"}
                    },
                    "required": ["task_id"]
                }
            ),
            Tool(
                name="list_tasks",
                description="列出所有异步任务",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="cancel_task",
                description="取消任务",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "任务ID"}
                    },
                    "required": ["task_id"]
                }
            ),
            # pasfmt 代码格式化工具
            Tool(
                name="format_delphi_file",
                description="【代码格式化】格式化 Delphi 源代码文件。智能体修改完代码后，使用此工具自动格式化代码以符合 Delphi 编码规范。推荐在提交代码前使用。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "要格式化的 Delphi 文件路径"},
                        "config_path": {"type": "string", "description": "pasfmt 配置文件路径（可选）"},
                        "backup": {"type": "boolean", "default": True, "description": "是否创建备份文件（在 __history 目录下）"},
                        "in_place": {"type": "boolean", "default": True, "description": "是否原地格式化（修改原文件）"},
                        "check_only": {"type": "boolean", "default": False, "description": "仅检查格式，不实际修改文件"}
                    },
                    "required": ["file_path"]
                }
            ),
            Tool(
                name="format_delphi_code",
                description="格式化 Delphi 代码字符串",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "要格式化的 Delphi 代码"},
                        "config_path": {"type": "string", "description": "pasfmt 配置文件路径（可选）"}
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="set_pasfmt_path",
                description="设置 pasfmt 可执行文件路径",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "pasfmt 可执行文件路径"}
                    },
                    "required": ["path"]
                }
            ),
            Tool(
                name="install_pasfmt",
                description="安装 pasfmt 代码格式化工具。可选择安装命令行工具或 IDE 插件",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "install_dir": {"type": "string", "description": "命令行工具安装目录，默认为 C:\\\\Program Files\\\\pasfmt"},
                        "install_rad": {"type": "boolean", "default": False, "description": "是否安装 IDE 插件 (pasfmt-rad)"},
                        "delphi_version": {"type": "string", "description": "Delphi 版本 (11, 12, 13)，仅 IDE 插件需要"},
                        "install_64bit": {"type": "boolean", "default": False, "description": "是否安装64位版本，仅 IDE 插件需要"},
                        "delphi_install_dir": {"type": "string", "description": "Delphi 安装目录，默认为自动检测"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="check_pasfmt_installation",
                description="检查 pasfmt 安装状态。可检查命令行工具或 IDE 插件",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "check_rad": {"type": "boolean", "default": False, "description": "是否检查 IDE 插件"},
                        "delphi_version": {"type": "string", "description": "Delphi 版本 (11, 12, 13)，检查 IDE 插件时需要"}
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
                result = await compile_project.compile_project(**arguments)  # type: ignore[attr-defined]
            elif name == "compile_file":
                result = await compile_file(**arguments)
            elif name == "get_compiler_args":
                result = await get_compiler_args(**arguments)
            elif name == "set_compiler_config":
                result = await set_compiler_config(**arguments)
            elif name == "search_compilers":
                result = await search_compilers(**arguments)
            elif name == "check_environment":
                result = await check_environment()
            elif name == "get_coding_rules":
                result = await coding_rules.get_coding_rules(**arguments)
            elif name == "build_knowledge":
                result = await kb_tools.build_unified_knowledge_base(arguments)
            elif name == "get_knowledge_stats":
                result = await kb_tools.get_unified_knowledge_stats(arguments)
            elif name == "search_knowledge":
                result = await kb_tools.search_knowledge(arguments)
            # 项目知识库工具
            elif name == "init_project_knowledge_base":
                result = await project_kb_tools.init_project_knowledge_base(arguments)
            # 异步任务工具
            elif name == "start_async_task":
                result = await async_tools.start_async_task(arguments)
            elif name == "get_task_status":
                result = await async_tools.get_task_status(arguments)
            elif name == "get_task_result":
                result = await async_tools.get_task_result(arguments)
            elif name == "list_tasks":
                result = await async_tools.list_tasks(arguments)
            elif name == "cancel_task":
                result = await help_kb_tools.cancel_task(arguments)
            # 项目依赖分析工具
            elif name == "analyze_project_dependencies":
                result = await dep_tools.analyze_project_dependencies(arguments)
            elif name == "resolve_smart_library_paths":
                result = await dep_tools.resolve_smart_library_paths(arguments)
            # 源码文件读取工具
            elif name == "read_source_file":
                result = await read_source_file(arguments)
            elif name == "search_and_read_file":
                result = await search_and_read_file(arguments)
            # pasfmt 代码格式化工具
            elif name == "format_delphi_file":
                result = await pasfmt.format_file(**arguments)
            elif name == "format_delphi_code":
                result = await pasfmt.format_code(**arguments)
            elif name == "set_pasfmt_path":
                path = arguments.get("path")
                if path is not None:
                    pasfmt.set_pasfmt_path(path)
                    result = {"message": f"pasfmt 路径已设置为: {path}"}
                else:
                    result = {"message": "未提供 pasfmt 路径"}
            elif name == "install_pasfmt":
                install_rad = arguments.get("install_rad", False)
                if install_rad:
                    result = await pasfmt.download_and_install_pasfmt_rad(**arguments)
                else:
                    result = await pasfmt.download_and_install_pasfmt(**arguments)
            elif name == "check_pasfmt_installation":
                check_rad = arguments.get("check_rad", False)
                if check_rad:
                    result = await pasfmt.check_pasfmt_rad_installation(**arguments)
                else:
                    result = await pasfmt.check_pasfmt_installation(**arguments)
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
