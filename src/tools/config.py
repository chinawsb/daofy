"""
配置管理工具

提供编译器配置管理功能
"""

from typing import Optional
from mcp.types import CallToolResult, TextContent
from ..services.config_manager import ConfigManager
from ..utils.validator import Validator
from ..utils.logger import get_logger

logger = get_logger(__name__)

_config_manager: Optional[ConfigManager] = None


def set_config_manager(manager: ConfigManager):
    """设置配置管理器实例"""
    global _config_manager
    _config_manager = manager


async def search_compilers(search_path: Optional[str] = None) -> CallToolResult:
    """
    搜索 Delphi 编译器
    
    - 不带 search_path 参数：自动检测系统中的编译器
    - 带 search_path 参数：在指定路径搜索编译器
    仅返回有效的编译器

    Args:
        search_path: 搜索路径，默认搜索常见安装位置

    Returns:
        CallToolResult with search results
    
    Note:
        建议使用 check_environment 工具来验证编译器有效性并获取详细信息
    """
    logger.info(f"收到搜索编译器请求: {search_path or '自动检测'}")

    if _config_manager is None:
        logger.error("配置管理器未初始化")
        return CallToolResult(
            content=[TextContent(type="text", text="配置管理器未初始化，请先启动服务")],
            isError=True
        )

    try:
        validator = Validator()
        found_compilers = []

        if search_path is None:
            _config_manager._auto_detect_compilers()
            compilers = _config_manager.get_all_compilers()
            default_compiler = _config_manager.get_compiler()

            for c in compilers:
                is_valid, _ = validator.validate_compiler_path(c.path)
                if is_valid:
                    found_compilers.append({
                        "name": c.name,
                        "path": c.path,
                        "version": c.version,
                        "is_default": c.name == (default_compiler.name if default_compiler else None)
                    })
            
            logger.info(f"自动检测完成: {len(found_compilers)} 个有效编译器")
            
            output = f"检测到 {len(found_compilers)} 个有效的 Delphi 编译器:\n\n"
            for c in found_compilers:
                default_mark = " (默认)" if c.get("is_default") else ""
                output += f"- {c['name']}{default_mark}\n"
                output += f"  路径: {c['path']}\n"
                output += f"  版本: {c.get('version', '未知')}\n\n"
            
            return CallToolResult(content=[TextContent(type="text", text=output)])
        else:
            import os
            
            common_paths = [search_path]
            
            for base_path in common_paths:
                if not os.path.exists(base_path):
                    continue
                    
                for version_dir in os.listdir(base_path):
                    version_path = os.path.join(base_path, version_dir)
                    if not os.path.isdir(version_path):
                        continue
                        
                    bin_path = os.path.join(version_path, "bin")
                    if not os.path.exists(bin_path):
                        continue
                    
                    for dcc in ["dcc32.exe", "dcc64.exe"]:
                        dcc_path = os.path.join(bin_path, dcc)
                        if os.path.exists(dcc_path):
                            is_valid, _ = validator.validate_compiler_path(dcc_path)
                            if is_valid:
                                found_compilers.append({
                                    "name": f"Delphi {version_dir}",
                                    "path": dcc_path,
                                    "version": version_dir
                                })
            
            logger.info(f"搜索完成: {len(found_compilers)} 个有效编译器")
            
            output = f"找到 {len(found_compilers)} 个有效的 Delphi 编译器:\n\n"
            for c in found_compilers:
                output += f"- {c['name']}\n"
                output += f"  路径: {c['path']}\n"
                output += f"  版本: {c.get('version', '未知')}\n\n"
            
            return CallToolResult(content=[TextContent(type="text", text=output)])

    except Exception as e:
        error_msg = f"搜索过程发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )
