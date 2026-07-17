"""Lazarus/FPC 插件工具 handlers — 独立于插件实例的纯函数。

遵循 Delphi 插件 handlers.py 模式:
  1. 每个 handler 接受 (arguments: dict) → 返回 Any (dict / CallToolResult)
  2. 导出 LAZARUS_HANDLERS / LAZARUS_TOOL_DESCRIPTIONS / LAZARUS_TOOL_SCHEMAS
  3. handler 内部延迟导入 CompilerService / LpiParser，避免模块级依赖
"""

from typing import Any

from src.utils.logger import init_default_logger

logger = init_default_logger()


# ============================================================
# 工具 handler 函数
# ============================================================

async def _handle_lazarus_compile(arguments: dict) -> dict:
    """编译 Lazarus/Free Pascal 项目 (.lpi / .lpr)

    Arguments:
        project_path (str): .lpi 或 .lpr 文件路径 (必需)
        target_platform (str, optional): win32 / win64，默认 win32
        build_configuration (str, optional): Default / Release / Debug
        timeout (int, optional): 超时秒数，默认 600
    """
    from src.services.compiler_service import CompilerService
    from src.services.config_manager import ConfigManager
    from src.models.compile_request import ProjectCompileRequest, CompileOptions, TargetPlatform

    project_path = arguments.get("project_path", "")
    if not project_path:
        return {"status": "failed", "error": "缺少必需参数: project_path"}

    platform_map = {
        "win32": TargetPlatform.WIN32,
        "win64": TargetPlatform.WIN64,
    }
    target = platform_map.get(
        arguments.get("target_platform", "win32").lower(),
        TargetPlatform.WIN32,
    )
    build_config = arguments.get("build_configuration")
    timeout = int(arguments.get("timeout", 600))

    compile_opts = CompileOptions(
        target_platform=target,
        build_configuration=build_config,
        timeout=timeout,
    )
    request = ProjectCompileRequest(
        project_path=project_path,
        options=compile_opts,
    )

    cm = ConfigManager()
    cs = CompilerService(cm)
    try:
        result = await cs.compile_with_lazbuild(request)
        return result.to_dict()
    except Exception as e:
        logger.error(f"lazarus_compile 失败: {e}", exc_info=True)
        return {
            "status": "failed",
            "error": f"编译失败: {e}",
            "project_path": project_path,
        }


async def _handle_lazarus_project(arguments: dict) -> dict:
    """获取 Lazarus 项目信息

    解析 .lpi 文件，返回项目名称、主源文件、单元列表、编译器选项。

    Arguments:
        project_path (str): .lpi 或 .lpr 文件路径 (必需)
        action (str, optional): info / units / options，默认 info
    """
    from src.utils.lpi_parser import LpiParser

    project_path = arguments.get("project_path", "")
    if not project_path:
        return {"status": "failed", "error": "缺少必需参数: project_path"}

    # .lpr → 查找同名 .lpi
    from pathlib import Path
    p = Path(project_path)
    lpi_path = project_path
    if p.suffix.lower() == ".lpr":
        candidate = p.with_suffix(".lpi")
        if candidate.exists():
            lpi_path = str(candidate)
        else:
            return {
                "status": "failed",
                "error": f"未找到与 {project_path} 对应的 .lpi 文件",
            }

    parser = LpiParser(lpi_path)
    if not parser.parse():
        return {
            "status": "failed",
            "error": f"解析 .lpi 文件失败: {lpi_path}",
        }

    action = arguments.get("action", "info")

    if action == "units":
        return {
            "status": "success",
            "project_path": lpi_path,
            "units": parser.get_units(),
        }

    if action == "options":
        return {
            "status": "success",
            "project_path": lpi_path,
            "compiler_options": parser.get_compiler_options(),
        }

    # 默认 info
    info = parser.get_project_info()
    return {
        "status": "success",
        "project_path": lpi_path,
        "name": info.get("project_name", ""),
        "main_source": info.get("main_source", ""),
        "unit_count": info.get("unit_count", 0),
        "search_paths": parser.get_unit_search_paths(),
        "compiler_options": parser.get_compiler_options(),
    }


# ============================================================
# 导出：工具名 → handler 映射
# ============================================================

LAZARUS_HANDLERS: dict[str, Any] = {
    "lazarus_compile": _handle_lazarus_compile,
    "lazarus_project": _handle_lazarus_project,
}

LAZARUS_TOOL_DESCRIPTIONS: dict[str, str] = {
    "lazarus_compile": "Lazarus/Free Pascal 项目编译 (lazbuild)",
    "lazarus_project": "Lazarus 项目信息查询 — 解析 .lpi 文件，获取项目名称/主源文件/单元列表/编译器选项",
}

LAZARUS_TOOL_SCHEMAS: dict[str, dict] = {
    "lazarus_compile": {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": ".lpi 或 .lpr 文件路径",
            },
            "target_platform": {
                "type": "string",
                "enum": ["win32", "win64"],
                "default": "win32",
            },
            "build_configuration": {
                "type": "string",
                "description": "Default / Release / Debug",
            },
            "timeout": {
                "type": "integer",
                "default": 600,
            },
        },
        "required": ["project_path"],
    },
    "lazarus_project": {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": ".lpi 或 .lpr 文件路径",
            },
            "action": {
                "type": "string",
                "enum": ["info", "units", "options"],
                "default": "info",
                "description": "info=项目概要, units=单元列表, options=编译器选项",
            },
        },
        "required": ["project_path"],
    },
}
