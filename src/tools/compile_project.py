"""
工程编译工具

提供 Delphi 工程整体编译功能
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
from mcp.types import CallToolResult
from ..models.compile_request import ProjectCompileRequest, CompileOptions, TargetPlatform, OutputType, RuntimeLibrary
from ..models.compile_result import CompileResult
from ..services.compiler_service import CompilerService
from ..utils.dproj_parser import DprojParser
from ..utils.logger import get_logger

logger = get_logger(__name__)

# 全局编译服务实例
_compiler_service: Optional[CompilerService] = None


def set_compiler_service(service: CompilerService):
    """设置编译服务实例"""
    global _compiler_service
    _compiler_service = service


def _detect_compiler_from_project(project_path: str, target_platform: str) -> Optional[str]:
    """
    从项目中自动检测最适配的编译器

    Args:
        project_path: 项目文件路径
        target_platform: 目标平台

    Returns:
        编译器名称,如果检测失败则返回 None
    """
    project_path_obj = Path(project_path)
    if not project_path_obj.exists():
        logger.warning(f"项目文件不存在: {project_path}")
        return None

    dproj_path = project_path
    if project_path_obj.suffix.lower() == '.dpr':
        dproj_path = str(project_path_obj.with_suffix('.dproj'))

    if not Path(dproj_path).exists():
        logger.warning(f"未找到 .dproj 文件: {dproj_path}")
        return None

    parser = DprojParser(dproj_path)
    if not parser.parse():
        logger.error(f"解析 .dproj 文件失败: {dproj_path}")
        return None

    project_version = parser.get_project_version()
    if not project_version:
        logger.warning(f"未获取到项目版本号: {dproj_path}")
        return None

    logger.info(f"项目版本号: {project_version}")

    if _compiler_service and _compiler_service.config_manager:
        compiler = _compiler_service.config_manager.get_compiler_for_project(project_version, target_platform)
        if compiler:
            logger.info(f"自动匹配编译器: {compiler.name}")
            return compiler.name

    return None


async def compile_project(
    project_path: str,
    target_platform: str = "win32",
    output_path: Optional[str] = None,
    compiler_version: Optional[str] = None,
    timeout: int = 600,
    conditional_defines: Optional[List[str]] = None,
    unit_search_paths: Optional[List[str]] = None,
    resource_search_paths: Optional[List[str]] = None,
    optimization_enabled: bool = True,
    debug_info_enabled: bool = False,
    warning_level: int = 2,
    disabled_warnings: Optional[List[str]] = None,
    output_type: str = "gui",
    runtime_library: str = "static",
    build_configuration: Optional[str] = None
) -> CallToolResult:
    """
    编译 Delphi 工程

    Args:
        project_path: 项目文件路径(.dproj 或 .dpr)
        target_platform: 目标平台(win32/win64)
        output_path: 输出路径
        compiler_version: 编译器版本名称
        timeout: 超时时间(秒)
        conditional_defines: 条件编译符号列表
        unit_search_paths: 单元搜索路径列表
        resource_search_paths: 资源搜索路径列表
        optimization_enabled: 是否启用优化
        debug_info_enabled: 是否生成调试信息
        warning_level: 警告级别(0-4)
        disabled_warnings: 禁用的警告列表
        output_type: 输出类型(console/gui/dll)
        runtime_library: 运行时库链接方式(static/dynamic)
        build_configuration: 编译配置名称

    Returns:
        编译结果字典
    """
    logger.info(f"收到工程编译请求: {project_path}")

    if _compiler_service is None:
        logger.error("编译服务未初始化")
        return CallToolResult(
            content=[{"type": "text", "text": "编译服务未初始化"}],
            isError=True
        )

    try:
        # 自动检测编译器版本(如果未指定)
        if not compiler_version:
            detected = _detect_compiler_from_project(project_path, target_platform)
            if detected:
                compiler_version = detected
                logger.info(f"自动检测到编译器: {compiler_version}")
            else:
                logger.info("未自动检测到编译器,将使用默认编译器")

        # 构建编译选项
        options = CompileOptions(
            target_platform=TargetPlatform(target_platform),
            output_path=output_path,
            compiler_version=compiler_version,
            timeout=timeout,
            conditional_defines=conditional_defines or [],
            unit_search_paths=unit_search_paths or [],
            resource_search_paths=resource_search_paths or [],
            optimization_enabled=optimization_enabled,
            debug_info_enabled=debug_info_enabled,
            warning_level=warning_level,
            disabled_warnings=disabled_warnings or [],
            output_type=OutputType(output_type),
            runtime_library=RuntimeLibrary(runtime_library),
            build_configuration=build_configuration
        )

        # 构建编译请求
        request = ProjectCompileRequest(
            project_path=project_path,
            options=options
        )

        # 执行编译
        result = await _compiler_service.compile_project(request)

        # 返回结果
        return CallToolResult(
            content=[{"type": "text", "text": str(result.to_dict())}],
            isError=result.status.value != "success"
        )

    except Exception as e:
        error_msg = f"编译过程发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )
