"""
单文件编译工具

提供 Delphi 单文件编译功能
"""

from typing import Optional, List, Dict, Any
from mcp.types import CallToolResult
from ..models.compile_request import FileCompileRequest
from ..services.compiler_service import CompilerService
from ..utils.logger import get_logger

logger = get_logger(__name__)

# 全局编译服务实例
_compiler_service: Optional[CompilerService] = None


def set_compiler_service(service: CompilerService):
    """设置编译服务实例"""
    global _compiler_service
    _compiler_service = service


async def compile_file(
    file_path: str,
    unit_search_paths: Optional[List[str]] = None,
    warning_level: int = 2,
    disabled_warnings: Optional[List[str]] = None
) -> CallToolResult:
    """
    编译单个 Delphi 单元文件(仅语法检查)

    Args:
        file_path: 单元文件路径(.pas)
        unit_search_paths: 单元搜索路径列表
        warning_level: 警告级别(0-4)
        disabled_warnings: 禁用的警告列表

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
        # 构建编译请求
        request = FileCompileRequest(
            file_path=file_path,
            unit_search_paths=unit_search_paths or [],
            warning_level=warning_level,
            disabled_warnings=disabled_warnings or []
        )

        # 执行编译
        result = await _compiler_service.compile_file(request)

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
