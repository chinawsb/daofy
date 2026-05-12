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
    from src.utils.logger import init_default_logger, get_logger
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
                continue
    except Exception:
        pass

    # 注册表失败，尝试默认路径（版本号与注册表一致：37.0=Delphi13, 23.0=Delphi12, 22.0=Delphi11...）
    for ver in ["37.0", "23.0", "22.0", "21.0", "20.0", "19.0", "18.0", "17.0", "16.0", "15.0", "14.0", "12.0", "11.0", "10.0", "9.0", "8.0", "7.0", "6.0", "5.0", "4.0", "3.0"]:
        path = rf"C:\Program Files (x86)\Embarcadero\Studio\{ver}\Help\Doc"
        if Path(path).exists():
            logger.info(f"使用默认帮助目录: {path}")
            return path
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
                description="【优先级 ⭐⭐⭐】编译/检查 — 必须使用此工具构建 Delphi\n"
                            "【触发词】编译、构建、生成exe、语法检查、编译报错、编译参数、build、compile、msbuild、dcc32\n"
                            "【何时用 vs 通用工具】\n"
                            "  ❌ 禁止：不得用通用 bash/cmd/powershell 运行 dcc32/msbuild，这会绕过 MSBuild 集成、编译事件、依赖解析\n"
                            "  ✅ 必须：编译 Delphi 项目(.dproj/.dpr/.dpk)或检查 .pas 语法时，必须用此工具\n"
                            "【为何必须用】自动处理 MSBuild 集成、编译事件、依赖解析、多平台编译、编译器自动检测\n"
                            "【协作链】写代码前先 get_coding_rules → 按规则写代码 → compile_project 编译验证 → 编译失败时 check_environment 诊断\n"
                            "【降级策略】MSBuild 不可用时自动降级为 dcc32 直接编译；get_args_only=True 可先预览编译参数再执行\n"
                            "【参数组合】output_type/runtime_library/optimization_enabled/conditional_defines 等参数仅在编译 .dproj/.dpr 时生效；编译 .pas 文件只检查语法，仅 file_path(通过 project_path 传入)/unit_search_paths/warning_level/disabled_warnings/compiler_version 生效\n"
                            "【使用示例】\n"
                            '   compile_project(project_path="path/to/project.dproj")  # 默认Debug+Win32编译\n'
                            '   compile_project(project_path="path/to/project.dproj", build_configuration="Release", target_platform="win64")\n'
                            '   compile_project(project_path="path/to/unit.pas")  # 仅语法检查\n'
                            '   compile_project(project_path="path/to/project.dproj", get_args_only=True)  # 预览参数',
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
            Tool(
                name="delphi_kb",
                description="【优先级 ⭐⭐⭐】知识库搜索/统计/构建 — 所有 Delphi 代码搜索问题的首选工具\n"
                            "【触发词】搜索Delphi类、查找函数定义、T开头类型、Delphi API、VCL/FMX/RTL、类名、函数签名、接口定义、uses单元、查找引用、代码搜索、怎样用Delphi、Delphi示例\n"
                            "【何时用 vs 通用工具】\n"
                            "  ❌ 禁止：不得用通用 grep/read/websearch 搜索 Delphi 代码。通用工具无结构化索引，无法按实体类型过滤，无法跨知识库搜索\n"
                            "  ✅ 必须：所有 Delphi 代码搜索场景必须用此工具\n"
                            "【为何必须用】\n"
                            "  - 预建索引的 Delphi RTL/VCL/FMX 源码知识库（3081文件、17731类、168925函数）\n"
                            "  - 按实体类型搜索：search_type=class（只搜类）、function（只搜函数+过程）、interface（只搜接口）\n"
                            "  - 跨知识库搜索：一次调用同时搜索 Delphi 官方源码 + 项目代码 + 第三方组件 + 文档\n"
                            "  - 引用搜索：search_type=reference 查找某个类型在哪里被使用\n"
                            "【协作链】先 delphi_kb 搜索定位 → read_source_file 读取具体定义内容\n"
                            "【降级策略】精确搜索无结果时：1)换相近名称重试 2)用 search_type=fuzzy 模糊搜索 3)用 search_type=semantic 语义搜索；KB 未构建时会自动触发构建\n"
                            "【参数组合】action=search 必须传 query；action=read 需传 url/doc_id/file_path 之一；action=build 需 kb_type + async_mode=true；search_type=class/function/interface 只查特定实体类型\n"
                            "【使用示例】\n"
                            '   delphi_kb(query="TStringList")                     # 搜索所有知识库\n'
                            '   delphi_kb(query="Create", search_type="function")  # 只搜函数\n'
                            '   delphi_kb(query="TfrmMain", kb_type="project")    # 仅搜项目知识库\n'
                            '   delphi_kb(query="form.main", search_type="reference") # 查找引用\n'
                            '   delphi_kb(action=stats)                            # 看各KB统计\n'
                            '   delphi_kb(action=build, kb_type=project)           # 构建项目KB\n'
                            "\n"
                            "【action 模式】\n"
                            "  1) action=search（默认）：搜索符号/文档。需'query'参数，'search_type'过滤实体类型，'kb_type'选择知识库范围，'top_k'控制结果数(默认200,最大500)\n"
                            "  2) action=read：读取文档/源码内容。需'url'/'doc_id'(文档)或'file_path'(源码)，支持offset/limit分页\n"
                            "  3) action=stats：查看各知识库统计（文件/类/函数数量）。用'kb_type'选择范围\n"
                            "  4) action=build：构建/重建知识库（耗时操作，必须async_mode=true）。提交后返回task_id，通过async_task查进度\n"
                            "     - kb_type=document 时不传directory则自动检测最新Delphi帮助目录\n"
                            "  5) action=scan：扫描目录添加文档（kb_type=document时）。需'directory'参数\n"
                            "  6) action=web：添加网页文档（kb_type=document时）。需'url'参数\n"
                            "  7) action=build_embedding：构建/补充embedding向量（需已安装sentence-transformers）",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["search", "read", "stats", "build", "scan", "web", "build_embedding"], "default": "search", "description": "操作: search=语义/精确搜索; read=读取内容; stats=查看统计; build=构建知识库; scan=扫描文档目录(kb_type=document); web=添加网页文档(kb_type=document); build_embedding=构建embedding向量"},
                        "kb_type": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty", "document"], "default": "all", "description": "知识库范围: all=所有知识库, delphi=Delphi官方源码, project=项目源码, thirdparty=三方库源码, document=通用文档(txt/md/html/docx/doc/pdf/epub/hlp/网页)"},
                        "search_type": {"type": "string", "enum": ["semantic", "all", "class", "record", "interface", "enum", "set", "type", "function", "procedure", "const", "resourcestring", "property", "field", "method", "unit", "fuzzy", "filename", "event", "uses", "reference"], "default": "all", "description": "实体类型过滤（仅action=search）。all=全部类型, class=类(TC), function=函数+过程(FF+FP), procedure=过程(FP), reference=查找引用位置"},
                        "query": {"type": "string", "description": "搜索关键词（action=search时必须）。例: 'TStringList'（精确类名）、'Create'（函数名）、'TfrmMain'（项目自有类）、'SysUtils'（单元名）"},
                        "doc_id": {"type": "integer", "description": "文档ID（action=read时，与url/file_path三选一）"},
                        "url": {"type": "string", "description": "文档URL（action=read/web时）；网页URL（action=web时需要）"},
                        "file_path": {"type": "string", "description": "源码文件路径（action=read时，与url/doc_id三选一）"},
                        "offset": {"type": "integer", "default": 0, "description": "内容起始偏移（action=read时，默认0）"},
                        "limit": {"type": "integer", "default": 5000, "description": "内容最大长度（action=read时，默认5000，最大20000）"},
                        "project_path": {"type": "string", "description": "项目.dproj/.dpr/.dpk路径（可选，不传时自动从当前目录检测）"},
                        "version": {"type": "string", "description": "Delphi版本号如 '23.0'（仅action=build且kb_type=delphi/thirdparty时需要）"},
                        "async_mode": {"type": "boolean", "default": True, "description": "是否异步构建（仅action=build，默认true）。true=提交后立即返回task_id(通过async_task查进度); false=阻塞等待(不推荐，可能超时)"},
                        "force_rebuild": {"type": "boolean", "default": False, "description": "是否强制重建（仅action=build）。false=尽可能增量更新"},
                        "incremental": {"type": "boolean", "default": False, "description": "增量构建，跳过CHM提取"},
                        "hash_mode": {"type": "string", "default": "mtime_size", "description": "变更检测模式（仅action=build）: mtime_size=快速(默认), md5=准确"},
                        "top_k": {"type": "integer", "default": 200, "description": "最大返回结果数 1-500（仅action=search）"},
                        "directory": {"type": "string", "description": "要扫描的目录路径（action=scan且kb_type=document时需要；action=build且kb_type=document时可选，不传则自动检测Delphi帮助目录）"},
                        "extensions": {"type": "array", "items": {"type": "string"}, "description": "文件扩展名列表（可选，如['.md', '.txt', '.html']；kb_type=document且不传时默认['.chm']）"},
                        "urls": {"type": "array", "items": {"type": "string"}, "description": "网页URL列表（action=build且kb_type=document时使用）"},
                        "start_url": {"type": "string", "description": "起始URL（action=build且kb_type=document时自动爬取）"},
                        "max_pages": {"type": "integer", "default": 100, "description": "最大爬取页面数（自动爬取时）"},
                        "max_depth": {"type": "integer", "default": 3, "description": "最大爬取深度（自动爬取时）"},
                        "domain_filter": {"type": "string", "description": "域名过滤（自动爬取时，只爬取该域名）"},
                        "url_pattern": {"type": "string", "description": "URL正则模式过滤（自动爬取时）"},
                        "content_type": {"type": "string", "description": "文档类型过滤（可选，如'markdown', 'html', 'docx'）"},
                        "max_workers": {"type": "integer", "description": "最大工作进程数（可选）"},
                        "exclude_dirs": {"type": "array", "items": {"type": "string"}, "description": "排除的子目录名列表（仅action=build且kb_type=document时有效，默认排除多语言帮助子目录如['ja','fr','de']）"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="read_source_file",
                description="【优先级 ⭐⭐】读取 Delphi 源码 — 按路径或按类名/函数名定位读取\n"
                            "【触发词】读取源码、查看定义、打开文件、看代码、类实现、函数体\n"
                            "【何时用 vs 通用 read】\n"
                            "  ❌ 禁止：不得用通用 read 搜索 Delphi 类/函数定义。通用 read 只能按已知路径读取，无法自动定位\n"
                            "  ✅ 必须：需要读取 Delphi 源文件内容时用此工具\n"
                            "【为何必须用】1)支持 search_type=class 按类名自动定位并读取 2)支持 search_type=function 按函数名读取 3)支持 search_type=reference 按引用位置读取 4)自动在 Delphi 官方/项目/三方库知识库中查找文件路径\n"
                            "【协作链】delphi_kb(action=search) 搜索定位 → read_source_file 读取内容\n"
                            "【降级策略】按 file_path 未找到文件时，自动在知识库中多策略路径匹配（尝试相对路径、大小写不敏感、文件名匹配等）\n"
                            "【参数组合】search_type=class 必须传 type_name；search_type=function 必须传 function_name；search_type=reference 必须传 file_path + 可选的 type_name/function_name\n"
                            "【使用示例】\n"
                            '   read_source_file(file_path="C:\\Project\\Unit1.pas")  # 按路径读取\n'
                            '   read_source_file(search_type="class", type_name="TButton")  # 搜类名并读取\n'
                            '   read_source_file(search_type="function", function_name="Create")  # 搜函数并读取',
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径 (支持绝对/相对路径)"},
                        "start_line": {"type": "integer", "default": 1, "description": "起始行号"},
                        "max_lines": {"type": "integer", "default": 200, "description": "返回行数"},
                        "search_type": {"type": "string", "enum": ["path", "class", "function", "reference"], "default": "path", "description": "读取方式: path=按文件路径, class=搜索类名后读取, function=搜索函数名后读取, reference=查找引用后读取"},
                        "type_name": {"type": "string", "description": "类名 (search_type=class时需要)"},
                        "function_name": {"type": "string", "description": "函数名 (search_type=function时需要)"},
                        "search_in": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty"], "default": "all", "description": "搜索范围"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="check_environment",
                description="【优先级 ⭐⭐】环境诊断 — 首次使用或编译器报\u201c未找到\u201d时先调用此工具\n"
                            "【触发词】检查环境、编译器找不到、诊断、安装Delphi、检测版本、环境配置、pasfmt安装\n"
                            "【何时用 vs 通用工具】\n"
                            "  \u274c 禁止：不得用 bash/generate_terminal 检查环境变量或搜索编译器路径，这不可靠且无法检测注册表\n"
                            "  \u2705 必须：诊断 Delphi 编译环境时用此工具\n"
                            "【为何必须用】自动从注册表检测已安装的 Delphi 版本和编译器路径，检测 MSBuild，诊断常见环境问题\n"
                            "【协作链】编译器未找到 → check_environment(action=detect) 重新检测 → compile_project 重试编译\n"
                            "【降级策略】注册表检测失败时：1)自动在 Program Files 常见路径搜索 dcc32.exe 2)运行 dcc32 --version 从输出解析版本号 3)以上均失败则使用硬编码默认值\n"
                            "【使用示例】\n"
                            '   check_environment(action="check")  # 诊断当前环境\n'
                            '   check_environment(action="detect")  # 重新检测编译器\n'
                            '   check_environment(action="install")  # 安装pasfmt格式化工具\n'
                            "【action】check=诊断当前环境; detect=重新检测编译器; install=安装pasfmt; format_install=安装pasfmt-rad IDE插件",
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
                description="【优先级 ⭐⭐】代码格式化 — 格式化 Delphi 源码或检查格式规范\n"
                            "【触发词】格式化代码、整理格式、代码风格、pasfmt、自动排版\n"
                            "【何时用 vs 通用工具】\n"
                            "  ❌ 禁止：不得手动调整缩进排版（手动排版容易引入不一致，且无法保证项目风格统一）\n"
                            "  ✅ 必须：需要统一 Delphi 源码格式风格时必须用此工具\n"
                            "【协作链】修改 Delphi 代码后 → format_delphi 格式化 → compile_project 编译验证\n"
                            "【使用示例】\n"
                            '   format_delphi(action="file", file_path="src/Unit1.pas")  # 格式化文件\n'
                            '   format_delphi(action="code", code="unit Test;\\ninterface\\n...")  # 格式化代码字符串\n'
                            '   format_delphi(action="check", file_path="src/Unit1.pas")  # 仅检查不修改\n'
                            "【action】file=格式化文件; code=格式化代码字符串; check=仅检查不修改; status=检查pasfmt安装状态",
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
                description="【优先级 ⭐⭐】后台任务管理 — 用于查看 delphi_kb(action=build) 提交的异步构建进度\n"
                            "【触发词】任务进度、构建状态、后台任务、task_id、异步任务、查看进度、构建结果、异步查询\n"
                            "【何时用】\n"
                            "  【强制触发】调用 delphi_kb(action=build) 后，必须用此工具轮询进度\n"
                            "  ✅ 必须：delphi_kb(action=build, async_mode=true) 提交后立即返回 task_id，AI Agent 必须调用此工具轮询直至完成\n"
                            "【使用示例】\n"
                            '   async_task(action="status", task_id="task_xxx")  # 查进度（推荐 long_poll_seconds=120）\n'
                            '   async_task(action="result", task_id="task_xxx")  # 取结果\n'
                            '   async_task(action="list")  # 列出所有后台任务\n'
                            "【action】status=查进度(推荐 long_poll_seconds=120 减少轮询); result=取结果; list=列出所有任务; cancel=取消任务",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["start", "status", "result", "list", "cancel"], "default": "list", "description": "操作: start=启动后台任务, status=查状态(含进度，支持long_poll_seconds长轮询), result=查结果, list=列表, cancel=取消"},
                        "task_type": {"type": "string", "enum": ["build_knowledge_base", "build_thirdparty_knowledge_base", "init_project_knowledge_base", "build_document_knowledge_base", "build_embedding"], "description": "任务类型 (action=start时需要)"},
                        "task_params": {"type": "object", "description": "任务参数: version(Delphi版本), force_rebuild, project_path, exclude_dirs(文档KB时可选，排除多语言子目录如['ja','fr','de']), extensions 等"},
                        "task_id": {"type": "string", "description": "任务ID (action=status/result/cancel时需要)"},
                        "show_progress": {"type": "boolean", "default": True, "description": "是否显示进度"},
                        "long_poll_seconds": {"type": "integer", "default": 0, "description": "长轮询秒数（action=status时有效，等待进度变化再返回，默认0即立即返回，推荐120秒减少AI轮询次数）"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="install_package",
                description="【优先级 ⭐⭐】组件安装 — 编译并安装 Delphi 组件包(.dpk/.dproj/.groupproj)到 IDE\n"
                            "【触发词】安装组件、安装包、安装控件、注册组件、dpk、bpl、设计期包\n"
                            "【何时用 vs 通用工具】\n"
                            "  ❌ 禁止：不得用 compile_project 编译 .dpk 包，这不会注册到 IDE\n"
                            "  ✅ 必须：需要编译并将 Delphi 组件包安装到 IDE 时使用\n"
                            "【为何必须用】自动识别设计期包/运行期包，设计期包编译成功后自动注册到 IDE\n"
                            "【协作链】先 compile_project 纯编译验证代码无错 → install_package 安装到 IDE → list_installed_packages 验证注册成功\n"
                            "【降级策略】设计期包安装到 IDE 失败时，在返回结果中给出 BPL 文件路径提示手动安装\n"
                            "【使用示例】\n"
                            '   install_package(package_path="path/to/package.dpk")  # 编译并安装到IDE',
                inputSchema={
                    "type": "object",
                    "properties": {
                        "package_path": {"type": "string", "description": "包文件路径(.dproj/.dpk/.groupproj)"},
                        "target_platform": {"type": "string", "enum": ["win32", "win64", "osx64", "osxarm64", "iosdevice64", "iosdevice", "iossimulator", "android", "android64", "linux64"], "default": "win32", "description": "目标平台"},
                        "build_configuration": {"type": "string", "default": "Debug", "description": "构建配置(Debug/Release)"},
                        "timeout": {"type": "integer", "default": 300, "description": "超时秒数"},
                        "install": {"type": "boolean", "default": True, "description": "是否自动安装到IDE"}
                    },
                    "required": ["package_path"]
                }
            ),
            Tool(
                name="list_installed_packages",
                description="【优先级 ⭐】已安装包列表 — 列出已注册到 IDE 的 Delphi 组件包\n"
                            "【触发词】已安装的包、注册的组件、IDE包列表、bpl列表\n"
                            "【何时用】查看当前 IDE 中已注册安装的所有 Delphi 组件包\n"
                            "【协作链】install_package 安装包后 → list_installed_packages 验证注册成功",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="get_coding_rules",
                description="【优先级 ⭐⭐⭐】编码规则 — 写 Delphi 代码前必须先调用此工具获取规范\n"
                            "【触发词】编码规范、命名规则、代码风格、代码规范、编码规则、写代码前\n"
                            "【何时用 vs 通用猜测】\n"
                            "  ❌ 禁止：不得凭通用 Delphi 知识猜测项目的编码风格，每个项目可能有自定义规则\n"
                            "  ✅ 必须：AI Agent 在编写或修改任何 Delphi 代码前，必须调用此工具获取项目级编码规则（命名、格式化、类型声明顺序、修改约束、审核要点）\n"
                            "【为何必须用】自动合并默认规则 + 项目自定义 CODING_RULES.mdc 规则\n"
                            "【协作链】get_coding_rules 获取规则 → 按规则写代码 → compile_project 编译验证 → format_delphi 格式化\n"
                            "【使用示例】\n"
                            '   get_coding_rules()  # 获取默认编码规则\n'
                            '   get_coding_rules(project_path="path/to/project.dproj")  # 获取项目自定义规则',
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string", "description": "项目路径(可选)，用于查找用户自定义的CODING_RULES.mdc覆盖默认规则"}
                    },
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
                                "exclude_dirs": arguments.get("exclude_dirs")
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
                result = await get_coding_rules(arguments)
            
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
