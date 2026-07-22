"""
单文件编译工具

提供 Delphi 单文件编译功能
"""

import json
import os
from typing import Optional, List, Dict, Any
from mcp.types import CallToolResult
from pathlib import Path
from ..models.compile_request import FileCompileRequest
from ..services.compiler_service import CompilerService
from ..utils.logger import get_logger
from ..utils.dproj_parser import DprojParser
from ..utils.delphi_env import get_delphi_library_paths, expand_delphi_path_macros
from ..services.delphi_edit_guard import external_edit_block_message

logger = get_logger(__name__)

# 全局编译服务实例
_compiler_service: Optional[CompilerService] = None


def set_compiler_service(service: CompilerService):
    """设置编译服务实例"""
    global _compiler_service
    _compiler_service = service


def _find_dproj_in_directory(file_dir: Path) -> Optional[str]:
    """
    在指定目录下查找 .dproj 文件

    Args:
        file_dir: 文件所在目录

    Returns:
        .dproj 文件路径，如果未找到则返回 None
    """
    dproj_files = list(file_dir.glob("*.dproj"))
    if dproj_files:
        return str(dproj_files[0])
    return None


def _get_search_paths_from_dproj(dproj_path: str, platform: str = "Win32") -> List[str]:
    """
    从 .dproj 文件获取搜索路径

    Args:
        dproj_path: .dproj 文件路径
        platform: 目标平台

    Returns:
        搜索路径列表
    """
    try:
        parser = DprojParser(dproj_path)
        if not parser.parse():
            return []

        paths = []

        unit_paths = parser.get_unit_search_paths(platform=platform)
        paths.extend(unit_paths)

        browsing_paths = parser.get_browsing_paths(platform=platform)
        paths.extend(browsing_paths)

        return list(set(paths))
    except Exception as e:
        logger.warning(f"解析 .dproj 文件失败: {e}")
        return []


def _get_delphi_default_library_paths(
    platform: str = "Win32",
    compiler_version: Optional[str] = None,
    project_version: Optional[str] = None,
) -> List[str]:
    """
    获取 Delphi 默认的库搜索路径

    Args:
        platform: 目标平台
        compiler_version: 编译器版本名称（可选）
        project_version: .dproj ProjectVersion（可选，用于 compiler_version 未指定时的 fallback）

    Returns:
        库搜索路径列表
    """
    try:
        # 获取编译器对应的 Delphi 版本号
        registry_version = None
        if compiler_version:
            from ..services.config_manager import get_config_manager
            cfg_mgr = get_config_manager()
            if cfg_mgr:
                compiler_cfg = cfg_mgr.get_compiler(compiler_version)
                if compiler_cfg:
                    registry_version = compiler_cfg.registry_version
        # Fallback: compiler_version 未指定时，从 .dproj ProjectVersion 推断
        if not registry_version and project_version:
            from ..utils.delphi_versions import project_version_to_registry_version
            registry_version = project_version_to_registry_version(project_version)
            if registry_version:
                logger.debug(
                    "从 .dproj ProjectVersion=%s 推断 registry_version=%s",
                    project_version, registry_version,
                )
        delphi_lib_paths = get_delphi_library_paths(version=registry_version, platform=platform)
        expanded_paths = []
        for p in delphi_lib_paths:
            expanded = expand_delphi_path_macros(p, version=registry_version, platform=platform)
            if expanded:
                expanded_paths.append(expanded)
        return expanded_paths
    except Exception as e:
        logger.warning(f"获取 Delphi 默认库路径失败: {e}")
        return []


async def compile_file(
    file_path: str,
    unit_search_paths: Optional[List[str]] = None,
    conditional_defines: Optional[List[str]] = None,
    warning_level: int = 2,
    disabled_warnings: Optional[List[str]] = None,
    compiler_version: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
) -> CallToolResult:
    """
    编译单个 Delphi 单元文件(仅语法检查)

    Args:
        file_path: 单元文件路径(.pas)
        unit_search_paths: 单元搜索路径列表(可选，为空时自动从.dproj或Delphi默认路径获取)
        conditional_defines: 条件编译符号列表(可选)
        warning_level: 警告级别(0-4)
        disabled_warnings: 禁用的警告列表
        compiler_version: 编译器版本名称（可选，不传时使用最新安装的版本）
        extra_args: 附加编译器参数列表

    Returns:
        编译结果
    """
    logger.info(f"收到单文件编译请求: {file_path}")

    if _compiler_service is None:
        logger.error("编译服务未初始化")
        return CallToolResult(
            content=[{"type": "text", "text": "编译服务未初始化"}],
            isError=True
        )

    try:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return CallToolResult(
                content=[{"type": "text", "text": f"文件不存在: {file_path}"}],
                isError=True
            )

        block_message = external_edit_block_message(file_path_obj)
        if block_message:
            return CallToolResult(
                content=[{"type": "text", "text": block_message}],
                isError=True,
            )

        file_dir = file_path_obj.parent

        search_paths = unit_search_paths or []

        dproj_path = _find_dproj_in_directory(file_dir)
        if dproj_path:
            logger.info(f"找到 .dproj 文件: {dproj_path}")
            project_paths = _get_search_paths_from_dproj(dproj_path)
            search_paths.extend(project_paths)
            logger.info(f"从 .dproj 获取搜索路径: {len(project_paths)} 个")
        else:
            logger.info("未找到 .dproj 文件，使用 Delphi 默认库路径")
            default_paths = _get_delphi_default_library_paths(compiler_version=compiler_version)
            search_paths.extend(default_paths)
            logger.info(f"从 Delphi 默认配置获取搜索路径: {len(default_paths)} 个")

        request = FileCompileRequest(
            file_path=file_path,
            unit_search_paths=search_paths,
            conditional_defines=conditional_defines or [],
            warning_level=warning_level,
            disabled_warnings=disabled_warnings or [],
            compiler_version=compiler_version,
            extra_args=extra_args or [],
        )

        result = await _compiler_service.compile_file(request)

        return CallToolResult(
            content=[{"type": "text", "text": json.dumps(result.to_dict(), ensure_ascii=False, default=str)}],
            isError=result.status.value != "success"
        )

    except Exception as e:
        error_msg = f"编译过程发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )
