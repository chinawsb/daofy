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

# 设置环境变量以确保正确的编码
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'

# 重新配置标准错误输出流编码
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from mcp.server import Server
from mcp.server.stdio import stdio_server

from src.services.config_manager import ConfigManager
from src.services.compiler_service import CompilerService
from src.services.knowledge_base import DelphiKnowledgeBaseService
from src.services.knowledge_base.thirdparty_knowledge_base import ThirdPartyKnowledgeBase
from src.tools import compile_project, compile_file, get_args, config, environment
from src.tools import knowledge_base as kb_tools
from src.tools import project_knowledge_base as project_kb_tools
from src.tools import help_knowledge_base as help_kb_tools
from src.tools import thirdparty_knowledge_base as thirdparty_kb_tools
from src.tools import analyze_dependencies as dep_tools
from src.tools import read_source_file as source_tools
from src.tools import coding_rules
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
    compile_project.set_compiler_service(compiler_service)
    compile_file.set_compiler_service(compiler_service)
    get_args.set_compiler_service(compiler_service)
    config.set_config_manager(config_manager)
    environment.set_config_manager(config_manager)
    kb_tools.set_knowledge_base_service(kb_service)
    source_tools.set_knowledge_base_services(kb_service, thirdparty_kb_service)
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
                description="编译 Delphi 工程",
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
                description="编译单个 Delphi 单元文件(仅语法检查)",
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
                description="获取编译器命令行参数(不执行编译)",
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
                description="配置 Delphi 编译器",
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
                name="check_environment",
                description="检查编译器环境状态",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="get_coding_rules",
                description="获取 Delphi 源码编码规则",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目路径（可选），用于查找用户自定义的编码规则文件"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="build_knowledge_base",
                description="构建 Delphi 源码知识库 (支持语义搜索)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "version": {"type": "string", "description": "Delphi 版本 (可选),默认使用最新版本"},
                        "force_rebuild": {"type": "boolean", "default": False, "description": "是否强制重建知识库"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="search_class",
                description="搜索 Delphi 类定义",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "class_name": {"type": "string", "description": "类名,如 'TButton'"}
                    },
                    "required": ["class_name"]
                }
            ),
            Tool(
                name="search_function",
                description="搜索 Delphi 函数/过程定义",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "function_name": {"type": "string", "description": "函数名,如 'Create'"}
                    },
                    "required": ["function_name"]
                }
            ),
            Tool(
                name="semantic_search",
                description="语义搜索 Delphi 代码 (支持自然语言查询)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索查询,如 'create button' 或 'network http request'"},
                        "top_k": {"type": "integer", "default": 10, "description": "返回结果数量"}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="get_knowledge_base_stats",
                description="获取知识库统计信息",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="list_delphi_versions",
                description="列出已安装的 Delphi 版本",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            # 项目知识库工具
            Tool(
                name="init_project_knowledge_base",
                description="初始化项目知识库 (从 .dproj 读取三方库路径并构建知识库)",
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
                name="search_project_class",
                description="在项目中搜索类定义 (支持搜索项目源码和三方库)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目文件路径 (.dproj 或 .dpr)"},
                        "class_name": {"type": "string", "description": "类名"},
                        "search_in": {"type": "string", "enum": ["project", "thirdparty", "all"], "default": "all", "description": "搜索范围: project(项目源码), thirdparty(三方库), all(全部)"}
                    },
                    "required": ["project_path", "class_name"]
                }
            ),
            Tool(
                name="search_project_function",
                description="在项目中搜索函数定义 (支持搜索项目源码和三方库)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目文件路径 (.dproj 或 .dpr)"},
                        "function_name": {"type": "string", "description": "函数名"},
                        "search_in": {"type": "string", "enum": ["project", "thirdparty", "all"], "default": "all", "description": "搜索范围: project(项目源码), thirdparty(三方库), all(全部)"}
                    },
                    "required": ["project_path", "function_name"]
                }
            ),
            Tool(
                name="semantic_search_project",
                description="在项目中进行语义搜索 (支持自然语言查询,自动检测源码变动并更新)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目文件路径 (.dproj 或 .dpr)"},
                        "query": {"type": "string", "description": "搜索查询,如 'create button' 或 'network http request'"},
                        "top_k": {"type": "integer", "default": 10, "description": "返回结果数量"},
                        "search_in": {"type": "string", "enum": ["project", "thirdparty", "all"], "default": "all", "description": "搜索范围: project(项目源码), thirdparty(三方库), all(全部)"}
                    },
                    "required": ["project_path", "query"]
                }
            ),
            Tool(
                name="get_project_kb_stats",
                description="获取项目知识库统计信息",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目文件路径 (.dproj 或 .dpr)"}
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
            # 全局第三方库知识库工具
            Tool(
                name="build_thirdparty_knowledge_base",
                description="构建第三方库知识库 (全局)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "version": {"type": "string", "description": "Delphi 版本 (可选)"},
                        "force_rebuild": {"type": "boolean", "default": False, "description": "是否强制重建"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="search_thirdparty_class",
                description="在第三方库中搜索类 (全局)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "class_name": {"type": "string", "description": "类名"}
                    },
                    "required": ["class_name"]
                }
            ),
            Tool(
                name="search_thirdparty_function",
                description="在第三方库中搜索函数 (全局)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "function_name": {"type": "string", "description": "函数名"}
                    },
                    "required": ["function_name"]
                }
            ),
            Tool(
                name="semantic_search_thirdparty",
                description="在第三方库中进行语义搜索 (全局)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索查询"},
                        "top_k": {"type": "integer", "default": 10, "description": "返回结果数量"}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="get_thirdparty_kb_stats",
                description="获取第三方库知识库统计信息 (全局)",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="get_thirdparty_paths_global",
                description="获取第三方库路径列表 (全局)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "version": {"type": "string", "description": "Delphi 版本 (可选)"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="search_thirdparty_record",
                description="在第三方库中搜索 record 类型 (全局)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "record_name": {"type": "string", "description": "record 类型名称"}
                    },
                    "required": ["record_name"]
                }
            ),
            Tool(
                name="search_by_filename",
                description="按文件名搜索文件 (支持通配符)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "文件名或通配符模式 (如: SuperCore*.pas)"},
                        "search_in": {"type": "string", "enum": ["all", "delphi", "thirdparty"], "default": "all", "description": "搜索范围"}
                    },
                    "required": ["filename"]
                }
            ),
            # 帮助文档知识库工具
            Tool(
                name="build_help_knowledge_base",
                description="构建 Delphi 帮助文档知识库 (完整构建：解压+扫描+索引，支持异步模式)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "force_rebuild": {"type": "boolean", "default": False, "description": "是否强制重建"},
                        "async_mode": {"type": "boolean", "default": True, "description": "是否使用异步模式（推荐，避免超时）"},
                        "help_names": {"type": "array", "items": {"type": "string"}, "description": "要构建的帮助文件列表，如 ['fmx', 'vcl']，默认全部"},
                        "max_files_per_help": {"type": "integer", "description": "每个帮助文件最大处理文档数（用于测试）"},
                        "incremental": {"type": "boolean", "default": False, "description": "是否使用增量构建（跳过解压）"},
                        "source_dir": {"type": "string", "description": "外部源目录路径（用于增量构建时指定外部extracted目录）"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="extract_help_chm",
                description="解压 Delphi 帮助文档 CHM 文件（分步骤构建第1步）",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "help_names": {"type": "array", "items": {"type": "string"}, "description": "要解压的帮助文件列表，如 ['fmx', 'vcl']，默认全部"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="scan_help_html",
                description="扫描已解压的 HTML 文件（分步骤构建第2步）",
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
                name="get_task_status",
                description="获取后台任务状态（用于查询帮助知识库构建进度）",
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
                description="列出所有后台任务",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="search_help",
                description="搜索 Delphi 帮助文档（支持语义搜索类、函数和文档）",
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
                description="分析 Delphi 项目的单元依赖关系",
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
                description="读取 Delphi 源码文件内容（先在知识库中定位文件，再从磁盘读取）",
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
                description="搜索类型（类/record/interface）或函数并读取所在文件内容",
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
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """调用工具"""
        logger.info(f"调用工具: {name}")

        try:
            if name == "compile_project":
                result = await compile_project.compile_project(**arguments)
            elif name == "compile_file":
                result = await compile_file.compile_file(**arguments)
            elif name == "get_compiler_args":
                result = await get_args.get_compiler_args(**arguments)
            elif name == "set_compiler_config":
                result = await config.set_compiler_config(**arguments)
            elif name == "check_environment":
                result = await environment.check_environment()
            elif name == "get_coding_rules":
                result = await coding_rules.get_coding_rules(**arguments)
            elif name == "build_knowledge_base":
                result = await kb_tools.build_knowledge_base(arguments)
            elif name == "search_class":
                result = await kb_tools.search_class(arguments)
            elif name == "search_function":
                result = await kb_tools.search_function(arguments)
            elif name == "semantic_search":
                result = await kb_tools.semantic_search(arguments)
            elif name == "get_knowledge_base_stats":
                result = await kb_tools.get_knowledge_base_stats(arguments)
            elif name == "list_delphi_versions":
                result = await kb_tools.list_delphi_versions(arguments)
            # 项目知识库工具
            elif name == "init_project_knowledge_base":
                result = await project_kb_tools.init_project_knowledge_base(arguments)
            elif name == "search_project_class":
                result = await project_kb_tools.search_project_class(arguments)
            elif name == "search_project_function":
                result = await project_kb_tools.search_project_function(arguments)
            elif name == "semantic_search_project":
                result = await project_kb_tools.semantic_search_project(arguments)
            elif name == "get_project_kb_stats":
                result = await project_kb_tools.get_project_kb_stats(arguments)
            elif name == "get_thirdparty_paths":
                result = await project_kb_tools.get_thirdparty_paths(arguments)
            # 全局第三方库知识库工具
            elif name == "build_thirdparty_knowledge_base":
                result = await thirdparty_kb_tools.build_thirdparty_knowledge_base(arguments)
            elif name == "search_thirdparty_class":
                result = await thirdparty_kb_tools.search_thirdparty_class(arguments)
            elif name == "search_thirdparty_function":
                result = await thirdparty_kb_tools.search_thirdparty_function(arguments)
            elif name == "semantic_search_thirdparty":
                result = await thirdparty_kb_tools.semantic_search_thirdparty(arguments)
            elif name == "get_thirdparty_kb_stats":
                result = await thirdparty_kb_tools.get_thirdparty_kb_stats(arguments)
            elif name == "get_thirdparty_paths_global":
                result = await thirdparty_kb_tools.get_thirdparty_paths(arguments)
            elif name == "search_thirdparty_record":
                result = await thirdparty_kb_tools.search_record(arguments)
            elif name == "search_by_filename":
                result = await thirdparty_kb_tools.search_by_filename(arguments)
            # 帮助文档知识库工具
            elif name == "build_help_knowledge_base":
                result = await help_kb_tools.build_help_knowledge_base(arguments)
            elif name == "extract_help_chm":
                result = await help_kb_tools.extract_help_chm(arguments)
            elif name == "scan_help_html":
                result = await help_kb_tools.scan_help_html(arguments)
            elif name == "build_help_kb_index":
                result = await help_kb_tools.build_help_kb_index(arguments)
            elif name == "get_task_status":
                result = await help_kb_tools.get_task_status(arguments)
            elif name == "list_tasks":
                result = await help_kb_tools.list_tasks(arguments)
            elif name == "search_help":
                result = await help_kb_tools.search_help(arguments)
            elif name == "get_help_kb_stats":
                result = await help_kb_tools.get_help_kb_stats(arguments)
            # 项目依赖分析工具
            elif name == "analyze_project_dependencies":
                result = await dep_tools.analyze_project_dependencies(arguments)
            elif name == "resolve_smart_library_paths":
                result = await dep_tools.resolve_smart_library_paths(arguments)
            # 源码文件读取工具
            elif name == "read_source_file":
                result = await source_tools.read_source_file(arguments)
            elif name == "search_and_read_file":
                result = await source_tools.search_and_read_file(arguments)
            else:
                raise ValueError(f"未知工具: {name}")

            return {"content": [{"type": "text", "text": str(result)}]}

        except Exception as e:
            logger.error(f"工具调用失败: {str(e)}", exc_info=True)
            return {"content": [{"type": "text", "text": f"错误: {str(e)}"}], "isError": True}

    # 启动服务器
    logger.info("MCP Server 启动中...")
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
