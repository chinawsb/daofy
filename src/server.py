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
from src.tools.environment import check_environment, set_config_manager as scm
from src.tools.knowledge_base import (
    set_knowledge_base_service,
    set_delphi_kb_service,
    set_project_kb_service,
    set_thirdparty_kb_service,
    set_help_kb_service,
    build_knowledge_base,
    search_class,
    search_function,
    semantic_search,
    get_knowledge_base_stats,
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
                description="【推荐】编译 Delphi 项目工程。当需要验证代码是否正确、构建可执行文件、排查编译错误时，优先使用此工具。支持完整的项目构建流程，包括所有单元编译和链接。避免手动调用dcc32/dcc64编译器，使用此工具可自动处理路径解析和依赖。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目文件路径(.dproj 或 .dpr)"},
                        "target_platform": {"type": "string", "enum": ["win32", "win64"], "default": "win32", "description": "目标平台: win32(32位) 或 win64(64位)"},
                        "output_path": {"type": "string", "description": "输出路径，编译生成的可执行文件存放目录"},
                        "compiler_version": {"type": "string", "description": "编译器版本名称，使用 set_compiler_config 配置的编译器名称"},
                        "timeout": {"type": "integer", "default": 600, "description": "编译超时时间(秒)，默认600秒"},
                        "conditional_defines": {"type": "array", "items": {"type": "string"}, "description": "条件编译定义符号列表，如 ['DEBUG', 'TRACE']"},
                        "unit_search_paths": {"type": "array", "items": {"type": "string"}, "description": "单元文件搜索路径列表"},
                        "resource_search_paths": {"type": "array", "items": {"type": "string"}, "description": "资源文件搜索路径列表"},
                        "optimization_enabled": {"type": "boolean", "default": True, "description": "是否启用编译优化"},
                        "debug_info_enabled": {"type": "boolean", "default": False, "description": "是否生成调试信息"},
                        "warning_level": {"type": "integer", "default": 2, "description": "警告级别(0-4)，数值越大警告越严格"},
                        "disabled_warnings": {"type": "array", "items": {"type": "string"}, "description": "禁用的警告编号列表，如 ['W1000', 'W1001']"},
                        "output_type": {"type": "string", "enum": ["console", "gui", "dll"], "default": "gui", "description": "输出类型: console(控制台程序), gui(GUI程序), dll(动态链接库)"},
                        "runtime_library": {"type": "string", "enum": ["static", "dynamic"], "default": "static", "description": "运行时库链接方式: static(静态链接), dynamic(动态链接)"},
                        "build_configuration": {"type": "string", "description": "构建配置名称，如 'Debug' 或 'Release'"}
                    },
                    "required": ["project_path"]
                }
            ),
            Tool(
                name="compile_file",
                description="【轻量级】对单个.pas文件进行快速语法检查。当只需要验证某个单元文件的语法正确性，而不需要完整编译整个项目时使用。比compile_project更快，适合开发过程中快速检查。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "单元文件路径(.pas)"},
                        "unit_search_paths": {"type": "array", "items": {"type": "string"}, "description": "单元文件搜索路径列表"},
                        "warning_level": {"type": "integer", "default": 2, "description": "警告级别(0-4)，数值越大警告越严格"},
                        "disabled_warnings": {"type": "array", "items": {"type": "string"}, "description": "禁用的警告编号列表，如 ['W1000', 'W1001']"}
                    },
                    "required": ["file_path"]
                }
            ),
            Tool(
                name="get_compiler_args",
                description="【调试用】仅获取编译器命令行参数，不执行实际编译。用于调试编译器配置、手动执行编译、或需要查看msbuild/dcc32具体参数时使用。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目文件路径(.dproj 或 .dpr)"},
                        "target_platform": {"type": "string", "enum": ["win32", "win64"], "default": "win32", "description": "目标平台: win32(32位) 或 win64(64位)"},
                        "output_path": {"type": "string", "description": "输出路径，编译生成的可执行文件存放目录"},
                        "compiler_version": {"type": "string", "description": "编译器版本名称，使用 set_compiler_config 配置的编译器名称"},
                        "conditional_defines": {"type": "array", "items": {"type": "string"}, "description": "条件编译定义符号列表，如 ['DEBUG', 'TRACE']"},
                        "unit_search_paths": {"type": "array", "items": {"type": "string"}, "description": "单元文件搜索路径列表"},
                        "resource_search_paths": {"type": "array", "items": {"type": "string"}, "description": "资源文件搜索路径列表"},
                        "optimization_enabled": {"type": "boolean", "default": True, "description": "是否启用编译优化"},
                        "debug_info_enabled": {"type": "boolean", "default": False, "description": "是否生成调试信息"},
                        "warning_level": {"type": "integer", "default": 2, "description": "警告级别(0-4)，数值越大警告越严格"},
                        "disabled_warnings": {"type": "array", "items": {"type": "string"}, "description": "禁用的警告编号列表，如 ['W1000', 'W1001']"},
                        "output_type": {"type": "string", "enum": ["console", "gui", "dll"], "default": "gui", "description": "输出类型: console(控制台程序), gui(GUI程序), dll(动态链接库)"},
                        "runtime_library": {"type": "string", "enum": ["static", "dynamic"], "default": "static", "description": "运行时库链接方式: static(静态链接), dynamic(动态链接)"},
                        "build_configuration": {"type": "string", "description": "构建配置名称，如 'Debug' 或 'Release'"}
                    },
                    "required": ["project_path"]
                }
            ),
            Tool(
                name="set_compiler_config",
                description="【环境配置】配置 Delphi 编译器路径。在首次编译项目或编译器路径变更时使用。需要提供dcc32.exe/dcc64.exe的完整路径。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "编译器版本名称，用于标识不同的编译器配置"},
                        "path": {"type": "string", "description": "编译器可执行文件路径，如 'C:\\Program Files\\Embarcadero\\RAD Studio\\bin\\dcc32.exe'"},
                        "is_default": {"type": "boolean", "default": False, "description": "是否设为默认编译器"},
                        "version": {"type": "string", "description": "编译器版本号，如 '10.4' 或 '11.0'"}
                    },
                    "required": ["name", "path"]
                }
            ),
            Tool(
                name="search_compilers",
                description="【编译器搜索】搜索 Delphi 编译器。不带参数时自动检测系统中的编译器，带 search_path 参数时在指定路径搜索。仅返回有效的编译器。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "search_path": {"type": "string", "description": "搜索路径，如 'C:\\Program Files (x86)\\Embarcadero\\Studio'（可选）"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="check_environment",
                description="【环境检查】检查 Delphi 编译器环境状态。在编译失败或需要确认编译器是否正确配置时使用。可以查看当前配置的编译器版本和路径。",
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
                description="【推荐】统一搜索知识库。支持同时搜索多个知识库和多种类型。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "kb_type": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty", "help"], "default": "all", "description": "知识库类型: all(全部), delphi, project, thirdparty, help"},
                        "search_type": {"type": "string", "enum": ["all", "class", "function", "semantic", "record", "filename"], "default": "semantic", "description": "搜索类型"},
                        "query": {"type": "string", "description": "搜索关键词"},
                        "project_path": {"type": "string", "description": "项目路径 (仅project类型需要)"},
                        "top_k": {"type": "integer", "default": 10, "description": "返回数量"}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="build_knowledge_base",
                description="【推荐】统一构建知识库。支持同时构建多个知识库。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "kb_type": {"type": "string", "default": "all", "description": "知识库类型: all, delphi, project, thirdparty, help (可组合,如'delphi,project')"},
                        "project_path": {"type": "string", "description": "项目路径 (仅project类型需要)"},
                        "version": {"type": "string", "description": "Delphi版本 (仅delphi/thirdparty需要)"},
                        "async_mode": {"type": "boolean", "default": True, "description": "是否异步"},
                        "force_rebuild": {"type": "boolean", "default": False, "description": "是否强制重建"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="get_knowledge_base_stats",
                description="【推荐】统一获取知识库统计信息。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "kb_type": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty", "help"], "default": "all", "description": "知识库类型"},
                        "project_path": {"type": "string", "description": "项目路径 (仅project需要)"}
                    },
                    "required": []
                }
            ),
            # 项目知识库工具
            Tool(
                name="init_project_knowledge_base",
                description="【首次使用必读】初始化项目知识库。在分析一个新项目之前，必须先调用此工具构建项目的知识库。它会从.dproj读取三方库路径，自动扫描并索引项目源码，之后才能使用项目搜索功能。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目文件路径 (.dproj 或 .dpr)"},
                        "build_thirdparty": {"type": "boolean", "default": True, "description": "是否构建三方库知识库"},
                        "build_project": {"type": "boolean", "default": True, "description": "是否构建项目源码知识库"},
                        "force_rebuild": {"type": "boolean", "default": False, "description": "是否强制重建"}
                    },
                    "required": ["project_path"]
                }
            ),
            Tool(
                name="get_thirdparty_paths",
                description="获取项目的三方库路径 (从 .dproj 文件中提取)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目文件路径 (.dproj 或 .dpr)"}
                    },
                    "required": ["project_path"]
                }
            ),
            # 全局第三方库知识库工具 - 保留 build_thirdparty_knowledge_base（通过统一接口）
            Tool(
                inputSchema={
                    "type": "object",
                    "properties": {
                        "record_name": {"type": "string", "description": "record 类型名称"}
                    },
                    "required": ["record_name"]
                }
            ),
            # 帮助文档知识库工具 - 通过 build_knowledge_base 统一接口
            Tool(
                name="get_help_kb_stats",
                description="获取帮助文档知识库统计信息",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "help_names": {"type": "array", "items": {"type": "string"}, "description": "要扫描的帮助文件列表，如 ['fmx', 'vcl']，默认全部"},
                        "max_files_per_help": {"type": "integer", "description": "每个帮助文件最大处理文档数（用于测试）"},
                        "source_dir": {"type": "string", "description": "外部源目录路径（默认使用 kb_dir/extracted）"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="build_help_kb_index",
                description="构建帮助文档向量索引（分步骤构建第3步）",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "help_names": {"type": "array", "items": {"type": "string"}, "description": "要构建的帮助文件列表，如 ['fmx', 'vcl']，默认全部"},
                        "max_files_per_help": {"type": "integer", "description": "每个帮助文件最大处理文档数（用于测试）"},
                        "source_dir": {"type": "string", "description": "外部源目录路径（默认使用 kb_dir/extracted）"},
                        "async_mode": {"type": "boolean", "default": True, "description": "是否使用异步模式"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="search_help",
                description="【文档查询】搜索 Delphi 官方帮助文档。当需要了解VCL/FMX类的官方用法、查看方法参数说明、查找示例代码时使用。返回帮助文档中的相关内容。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索查询，如 'TStringList', 'Create 创建对象'"},
                        "top_k": {"type": "integer", "default": 10, "description": "返回结果数量"}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="get_help_kb_stats",
                description="获取帮助文档知识库统计信息",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            # 项目依赖分析工具
            Tool(
                name="analyze_project_dependencies",
                description="【项目分析】分析 Delphi 项目的单元依赖关系。当需要了解项目的模块结构、查找循环依赖、确定需要编译的单元顺序、或清理无用单元时使用。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目文件路径(.dpr 或 .dproj)"}
                    },
                    "required": ["project_path"]
                }
            ),
            Tool(
                name="resolve_smart_library_paths",
                description="智能解析项目需要的第三方库路径",
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
                description="【推荐】读取 Delphi 源码文件内容。智能体需要查看任何 .pas 文件的源代码时，必须使用此工具而不是自行读取文件。支持指定行号范围，可精确定位代码段。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径（相对路径或完整路径）"},
                        "start_line": {"type": "integer", "default": 1, "description": "起始行号（从1开始）"},
                        "end_line": {"type": "integer", "description": "结束行号（可选，默认文件末尾）"},
                        "max_lines": {"type": "integer", "default": 500, "description": "最大返回行数（最大1000）"},
                        "search_in": {"type": "string", "enum": ["all", "delphi", "thirdparty"], "default": "all", "description": "搜索范围"}
                    },
                    "required": ["file_path"]
                }
            ),
            Tool(
                name="search_and_read_file",
                description="【一站式】搜索类/record/interface/函数定义，并自动读取其所在文件的完整代码。当需要同时了解类型定义和其周围代码上下文时使用，是search_class + read_source_file的组合。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "type_name": {"type": "string", "description": "类型名称（类、record、interface，可选）"},
                        "record_name": {"type": "string", "description": "record 类型名称（可选）"},
                        "function_name": {"type": "string", "description": "函数名（可选）"},
                        "search_in": {"type": "string", "enum": ["all", "delphi", "thirdparty"], "default": "all", "description": "搜索范围"},
                        "start_line": {"type": "integer", "default": 1, "description": "起始行号"},
                        "max_lines": {"type": "integer", "default": 100, "description": "最大返回行数"}
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
                            "enum": ["build_knowledge_base", "build_thirdparty_knowledge_base", "init_project_knowledge_base"],
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
            elif name == "build_knowledge_base":
                result = await kb_tools.build_unified_knowledge_base(arguments)
            elif name == "get_knowledge_base_stats":
                result = await kb_tools.get_unified_knowledge_stats(arguments)
            elif name == "search_knowledge":
                result = await kb_tools.search_knowledge(arguments)
            # 项目知识库工具
            elif name == "init_project_knowledge_base":
                result = await project_kb_tools.init_project_knowledge_base(arguments)
            elif name == "get_thirdparty_paths":
                result = await project_kb_tools.get_thirdparty_paths(arguments)
            # 帮助文档知识库工具
            elif name == "build_help_knowledge_base":
                result = await help_kb_tools.build_help_knowledge_base(arguments)
            elif name == "search_help":
                result = await help_kb_tools.search_help(arguments)
            elif name == "get_help_kb_stats":
                result = await help_kb_tools.get_help_kb_stats(arguments)
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
