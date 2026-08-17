"""
project 统一工具 — 合并 compile_project + dproj_tool + run_audit + deploy

通过 action 路由到各子功能，复用现有实现。
"""

import json
import logging
import re
from typing import Any, List, Optional

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

# deploy
from .deploy import deploy_project as _deploy_project

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
    "layout": "audit",
    # deploy 系列
    "devices": "deploy",
    "deploy": "deploy",
}

_DISABLED_WARNINGS = {"W1000"}  # 默认禁用的警告

# ── MSBuild 属性提取（从 extra_args 同步 /p:Platform 和 /p:Config）──

_MS_BUILD_PROPERTY_RE = re.compile(r'^/p:(\w+)=(.+)$', re.IGNORECASE)


def _extract_msbuild_property(extra_args: Optional[List[str]], prop_name: str) -> Optional[str]:
    """从 extra_args 中提取最后一个 /p:{prop_name}=... 的值（MSBuild last-wins 语义）。

    Args:
        extra_args: 附加编译参数列表
        prop_name: MSBuild 属性名（如 "Platform"、"Config"）

    Returns:
        属性值字符串，未找到时返回 None
    """
    if not extra_args:
        return None
    result = None
    for arg in extra_args:
        m = _MS_BUILD_PROPERTY_RE.match(arg)
        if m and m.group(1).lower() == prop_name.lower():
            result = m.group(2)
    return result


def _warn_extra_args_conflict(
    extra_args: Optional[List[str]],
    prop_name: str,
    explicit_value: str,
) -> Optional[str]:
    """检测 extra_args 中的 /p:{prop_name} 是否与显式传入的值冲突。

    冲突时以 extra_args 值为准（MSBuild last-wins），并记录警告。

    Returns:
        冲突时返回 extra_args 中的值；无冲突返回 None
    """
    extra_value = _extract_msbuild_property(extra_args, prop_name)
    if extra_value is None:
        return None
    if extra_value.lower() != explicit_value.lower():
        logger.warning(
            "extra_args 中 /p:%s=%s 与显式参数 %s=%s 冲突，以 extra_args 值为准",
            prop_name, extra_value, prop_name, explicit_value,
        )
        return extra_value
    return None


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
        elif action in ("audit", "ast", "runtime", "layout"):
            return await _handle_audit(kwargs)

        # ── deploy 系列 ──
        elif action in ("devices", "deploy"):
            return await _handle_deploy(action, kwargs)

        else:
            return {"status": "failed", "message": f"未知 action: {action}。"
                    f"运行 tool_help(tool_name='delphi_project') 查看所有可用 action 及其参数。"}
    except Exception as e:
        logger.exception("project 执行失败")
        return {"status": "failed", "message": str(e)}


# ── 子处理器 ──


async def _handle_compile(kwargs: dict) -> Any:
    """处理 compile action，完成后记录到经验追踪器。"""
    project_path = kwargs.get("project_path", "")
    if not project_path:
        return {"status": "failed", "message": "缺少必需参数: project_path"}

    if project_path.lower().endswith('.pas'):
        result = await _compile_file(
            file_path=project_path,
            unit_search_paths=kwargs.get('unit_search_paths'),
            conditional_defines=kwargs.get('conditional_defines'),
            compiler_version=kwargs.get('compiler_version'),
            extra_args=kwargs.get('extra_args'),
        )
        _record_compile_to_tracker(project_path, result, "compile_file")
        return result

    # ── 从 extra_args 同步平台/配置（修复 /p:Platform 和 /p:Config 被忽略的问题）──
    # 优先级：显式参数 > extra_args /p: > .dproj 解析 > "win32"/"Debug" 兜底
    extra_args = kwargs.get("extra_args")
    target_platform = kwargs.get("target_platform")
    build_configuration = kwargs.get("build_configuration")

    # 用户未传 target_platform 时，从 extra_args 提取 /p:Platform
    if not target_platform:
        extra_platform = _extract_msbuild_property(extra_args, "Platform")
        if extra_platform:
            target_platform = extra_platform.lower()
            logger.info("从 extra_args 提取目标平台: %s", target_platform)

    # 用户未传 build_configuration 时，从 extra_args 提取 /p:Config
    if not build_configuration:
        extra_config = _extract_msbuild_property(extra_args, "Config")
        if extra_config:
            build_configuration = extra_config
            logger.info("从 extra_args 提取构建配置: %s", build_configuration)

    # ── 冲突检测：显式参数与 extra_args 中的同名属性不一致时，以 extra_args 为准 ──
    if target_platform and extra_args:
        conflict = _warn_extra_args_conflict(extra_args, "Platform", target_platform)
        if conflict:
            target_platform = conflict.lower()

    if build_configuration and extra_args:
        conflict = _warn_extra_args_conflict(extra_args, "Config", build_configuration)
        if conflict:
            build_configuration = conflict

    result = await _compile_project(
        project_path=project_path,
        target_platform=target_platform,  # None 时由 compile_project 从 .dproj 解析
        build_configuration=build_configuration or "Debug",
        extra_args=extra_args,
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
    _record_compile_to_tracker(project_path, result, "compile")
    return result


def _record_compile_to_tracker(project_path: str, result: Any, action: str) -> None:
    """将编译结果记录到经验追踪器。"""
    try:
        from ..services.experience_tracker import get_tracker

        # 判断是否成功
        success = True
        result_text = ""
        if hasattr(result, 'isError'):
            success = not result.isError
            if result.content and len(result.content) > 0:
                ct = result.content[0]
                if hasattr(ct, 'text'):
                    result_text = ct.text
        elif isinstance(result, dict):
            success = result.get('status') != 'failed'
            result_text = result.get('message', result.get('error', ''))

        tracker = get_tracker()
        tracker.record(
            name="delphi_project",
            arguments={"action": action, "project_path": project_path},
            success=success,
            result_text=result_text,
        )
    except Exception as e:
        logger.debug("记录编译结果到追踪器失败（不影响编译）: %s", e)


async def _handle_dry_run(kwargs: dict) -> Any:
    """处理 dry_run action"""
    accepted_keys = {
        "project_path", "target_platform", "output_path", "compiler_version",
        "conditional_defines", "unit_search_paths", "resource_search_paths",
        "optimize", "debug", "warning_level",
        "disabled_warnings", "output_type", "runtime_library", "build_configuration",
        "extra_args",
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
        extra_args=kwargs.get('extra_args'),
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
        app_type=kwargs.get("app_type"),
        unit_search_paths=kwargs.get("unit_search_paths"),
        namespace=kwargs.get("namespace"),
        configs=kwargs.get("configs"),
        sources=kwargs.get("sources"),
        platforms=kwargs.get("platforms"),
        target_platform=kwargs.get("target_platform"),
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


async def _handle_deploy(action: str, kwargs: dict) -> Any:
    """处理 deploy 系列 action"""
    # 移除 kwargs 中的 action 以避免重复
    deploy_kwargs = {k: v for k, v in kwargs.items() if k != "action"}
    return await _deploy_project(action=action, **deploy_kwargs)
