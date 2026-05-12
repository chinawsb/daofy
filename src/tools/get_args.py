"""
获取命令行参数工具

提供命令行参数生成功能
"""

from typing import Optional, List, Dict, Any
from mcp.types import CallToolResult, TextContent
from ..models.compile_request import ProjectCompileRequest, CompileOptions, TargetPlatform, OutputType, RuntimeLibrary
from ..services.compiler_service import CompilerService
from ..utils.logger import get_logger

logger = get_logger(__name__)

# 全局编译服务实例
_compiler_service: Optional[CompilerService] = None


def set_compiler_service(service: CompilerService):
    """设置编译服务实例"""
    global _compiler_service
    _compiler_service = service


async def get_compiler_args(
    project_path: str,
    target_platform: Optional[str] = None,
    output_path: Optional[str] = None,
    compiler_version: Optional[str] = None,
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
    获取编译器命令行参数(不执行编译)

    Args:
        project_path: 项目文件路径(.dproj 或 .dpr)
        target_platform: 目标平台(win32/win64/osx64/osxarm64/iosdevice64/android/linux64等)
        output_path: 输出路径
        compiler_version: 编译器版本名称
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
        命令行参数
    """
    logger.info(f"收到获取命令行参数请求: {project_path}")

    if _compiler_service is None:
        logger.error("编译服务未初始化")
        return CallToolResult(
            content=[TextContent(type="text", text="编译服务未初始化，请先启动服务")],
            isError=True
        )

    try:
        # 如果未指定目标平台（或为默认值"win32"），尝试从 .dproj 读取
        if not target_platform or target_platform == "win32":
            from ..utils.dproj_parser import resolve_target_platform_from_dproj
            target_platform = resolve_target_platform_from_dproj(project_path)
            logger.info(f"从 .dproj 读取到目标平台: {target_platform}")
        else:
            target_platform = target_platform.lower()
        
        # 构建编译选项
        options = CompileOptions(
            target_platform=TargetPlatform(target_platform),
            output_path=output_path,
            compiler_version=compiler_version,
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

        # 生成参数
        result = _compiler_service.get_args(request)

        # 返回结果
        return CallToolResult(
            content=[TextContent(type="text", text=str(result.to_dict()))],
            isError=False
        )

    except Exception as e:
        error_msg = f"生成参数过程发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )
