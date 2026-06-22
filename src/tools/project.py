"""
project 统一工具 — 合并 compile_project + dproj_tool + run_audit

通过 action 路由到各子功能，复用现有实现。
"""

import logging
from typing import Any

from ..utils.logger import get_logger

logger = get_logger(__name__)

# ── 导入现有工具函数 ──
# compile_project 相关
from .compile_project import compile_project as _compile_project, set_compiler_service as _set_compile_svc
from .compile_file import compile_file as _compile_file
from .get_args import get_compiler_args as _get_compiler_args

# dproj_tool
from .dproj_tool import dproj_tool as _dproj_tool

# audit
from .audit import run_audit as _run_audit

# 编译服务（全局实例由 server.py 设置，但需要在这里 re-export 给 server.py）
_compiler_service_set = False


def set_compiler_service(svc):
    """设置编译器服务（由 server.py 初始化时调用）"""
    global _compiler_service_set
    _set_compile_svc(svc)
    _compiler_service_set = True


# ── action 路由 ──

_ACTIONS = {
    # compile_project 系列
    "compile": "compile",
    "dry_run": "dry_run",
    "compile_file": "compile_file",
    # dproj_tool 系列
    "info": "dproj",
    "create": "dproj",
    "set": "dproj",
    "add_config": "dproj",
    "remove_config": "dproj",
    "add_source": "dproj",
    "remove_source": "dproj",
    # run_audit 系列
    "audit": "audit",
    "ast": "audit",
    "runtime": "audit",
}

_DISABLED_WARNINGS = {"W1000"}  # 默认禁用的警告


async def handle_project(**kwargs) -> Any:
    """统一的 project 工具入口，按 action 路由到子功能。

    前一步可调用 tool_help(tool_name="delphi_project") 查看各 action 的详细参数。
    """
    action = kwargs.get("action", "")

    try:
        # ── compile 系列 ──
        if action in ("compile",):
            return await _handle_compile(kwargs)

        elif action == "dry_run":
            return await _handle_dry_run(kwargs)

        elif action == "compile_file":
            return await _handle_compile_file(kwargs)

        # ── dproj_tool 系列 ──
        elif action in ("info", "create", "set", "add_config", "remove_config",
                         "add_source", "remove_source"):
            return await _handle_dproj(action, kwargs)

        # ── run_audit 系列 ──
        elif action in ("audit", "ast", "runtime"):
            return await _handle_audit(kwargs)

        else:
            return {"status": "failed", "message": f"未知 action: {action}。"
                    f"运行 tool_help(tool_name='delphi_project') 查看所有可用 action 及其参数。"}
    except Exception as e:
        logger.exception("project 执行失败")
        return {"status": "failed", "message": str(e)}


# ── 子处理器 ──


async def _handle_compile(kwargs: dict) -> Any:
    """处理 compile action"""
    project_path = kwargs.get("project_path", "")
    if not project_path:
        return {"status": "failed", "message": "缺少必需参数: project_path"}

    if project_path.lower().endswith('.pas'):
        return await _compile_file(
            file_path=project_path,
            unit_search_paths=kwargs.get('unit_search_paths'),
            conditional_defines=kwargs.get('conditional_defines'),
            compiler_version=kwargs.get('compiler_version'),
        )

    return await _compile_project(
        project_path=project_path,
        target_platform=kwargs.get("target_platform", "win32"),
        build_configuration=kwargs.get("build_configuration", "Debug"),
        output_path=kwargs.get("output_path"),
        compiler_version=kwargs.get("compiler_version"),
        conditional_defines=kwargs.get("conditional_defines"),
        unit_search_paths=kwargs.get("unit_search_paths"),
        resource_search_paths=kwargs.get("resource_search_paths"),
        optimize=kwargs.get("optimize"),
        debug=kwargs.get("debug"),
        warning_level=kwargs.get("warning_level", 2),
        disabled_warnings=kwargs.get("disabled_warnings", _DISABLED_WARNINGS),
        output_type=kwargs.get("output_type", "gui"),
        runtime_library=kwargs.get("runtime_library", "static"),
        timeout=kwargs.get("timeout", 600),
        auto_install=kwargs.get("auto_install", True),
        run_verify=kwargs.get("run_verify", False),
    )


async def _handle_dry_run(kwargs: dict) -> Any:
    """处理 dry_run action"""
    accepted_keys = {
        "project_path", "target_platform", "output_path", "compiler_version",
        "conditional_defines", "unit_search_paths", "resource_search_paths",
        "optimize", "debug", "warning_level",
        "disabled_warnings", "output_type", "runtime_library", "build_configuration",
    }
    filtered = {k: v for k, v in kwargs.items() if k in accepted_keys}
    return await _get_compiler_args(**filtered)


async def _handle_compile_file(kwargs: dict) -> Any:
    """处理 compile_file action"""
    return await _compile_file(
        file_path=kwargs.get("file_path", kwargs.get("project_path", "")),
        unit_search_paths=kwargs.get('unit_search_paths'),
        conditional_defines=kwargs.get('conditional_defines'),
        compiler_version=kwargs.get('compiler_version'),
    )


async def _handle_dproj(action: str, kwargs: dict) -> Any:
    """处理 dproj_tool 系列 action"""
    return await _dproj_tool(
        action=action,
        project_path=kwargs.get("project_path", ""),
        main_source=kwargs.get("main_source"),
        project_guid=kwargs.get("project_guid"),
        project_version=kwargs.get("project_version"),
        framework_type=kwargs.get("framework_type", "VCL"),
        unit_search_paths=kwargs.get("unit_search_paths"),
        namespace=kwargs.get("namespace"),
        configs=kwargs.get("configs"),
        sources=kwargs.get("sources"),
        form_units=kwargs.get("form_units"),
        property_name=kwargs.get("property_name"),
        value=kwargs.get("value"),
        config=kwargs.get("config"),
        platform=kwargs.get("platform"),
        config_name=kwargs.get("config_name"),
        base_config=kwargs.get("base_config"),
        defines=kwargs.get("defines"),
        optimize=kwargs.get("optimize"),
        debug_info=kwargs.get("debug_info"),
        source_file=kwargs.get("source_file"),
        main_source_flag=kwargs.get("main_source_flag", False),
    )


async def _handle_audit(kwargs: dict) -> Any:
    """处理 run_audit 系列 action"""
    return await _run_audit(kwargs)
