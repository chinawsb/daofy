"""
配置管理工具

提供编译器配置管理功能
"""

from typing import Optional, Dict, Any
from mcp.types import CallToolResult, TextContent
from ..models.compiler_config import CompilerConfig
from ..services.config_manager import ConfigManager
from ..utils.validator import Validator
from ..utils.logger import get_logger

logger = get_logger(__name__)

# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


def set_config_manager(manager: ConfigManager):
    """设置配置管理器实例"""
    global _config_manager
    _config_manager = manager


async def set_compiler_config(
    name: str,
    path: str,
    is_default: bool = False,
    version: Optional[str] = None
) -> Dict[str, Any]:
    """
    配置 Delphi 编译器

    Args:
        name: 编译器版本名称
        path: 编译器可执行文件路径
        is_default: 是否设为默认编译器
        version: 编译器版本号

    Returns:
        配置结果字典
    """
    logger.info(f"收到配置编译器请求: {name}")

    if _config_manager is None:
        logger.error("配置管理器未初始化")
        return {
            "success": False,
            "message": "配置管理器未初始化",
            "compiler_name": name
        }

    try:
        # 验证编译器路径
        validator = Validator()
        is_valid, error_msg = validator.validate_compiler_path(path)
        if not is_valid:
            logger.error(f"编译器路径验证失败: {error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "compiler_name": name
            }

        # 创建编译器配置
        compiler = CompilerConfig(
            name=name,
            path=path,
            is_default=is_default,
            version=version
        )

        # 添加配置
        _config_manager.add_compiler(compiler)

        logger.info(f"编译器配置成功: {name}")
        return {
            "success": True,
            "message": f"编译器配置成功: {name}",
            "compiler_name": name
        }

    except Exception as e:
        error_msg = f"配置过程发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "message": error_msg,
            "compiler_name": name
        }


async def get_compiler_list() -> Dict[str, Any]:
    """
    获取所有编译器配置列表

    Returns:
        编译器配置列表字典
    """
    logger.info("收到获取编译器列表请求")

    if _config_manager is None:
        logger.error("配置管理器未初始化")
        return {
            "success": False,
            "message": "配置管理器未初始化",
            "compilers": []
        }

    try:
        compilers = _config_manager.get_all_compilers()
        default_compiler = _config_manager.get_compiler()

        return {
            "success": True,
            "message": f"共 {len(compilers)} 个编译器配置",
            "compilers": [c.to_dict() for c in compilers],
            "default_compiler": default_compiler.name if default_compiler else None
        }

    except Exception as e:
        error_msg = f"获取编译器列表过程发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "message": error_msg,
            "compilers": []
        }


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
            # 自动检测模式：检测系统中已配置的编译器
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
            
            # Format output
            output = f"检测到 {len(found_compilers)} 个有效的 Delphi 编译器:\n\n"
            for c in found_compilers:
                default_mark = " (默认)" if c.get("is_default") else ""
                output += f"- {c['name']}{default_mark}\n"
                output += f"  路径: {c['path']}\n"
                output += f"  版本: {c.get('version', '未知')}\n\n"
            
            return CallToolResult(content=[TextContent(type="text", text=output)])
        else:
            # 搜索模式：在指定路径搜索
            import os
            from pathlib import Path
            
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


# 兼容旧接口
async def detect_compilers() -> CallToolResult:
    """自动检测系统中可用的 Delphi 编译器（兼容旧接口）"""
    return await search_compilers()


async def search_delphi_compilers(search_path: Optional[str] = None) -> CallToolResult:
    """在指定路径搜索 Delphi 编译器（兼容旧接口）"""
    return await search_compilers(search_path)


async def remove_compiler_config(name: str) -> Dict[str, Any]:
    """
    删除编译器配置

    Args:
        name: 编译器名称

    Returns:
        删除结果字典
    """
    logger.info(f"收到删除编译器配置请求: {name}")

    if _config_manager is None:
        logger.error("配置管理器未初始化")
        return {
            "success": False,
            "message": "配置管理器未初始化",
            "compiler_name": name
        }

    try:
        result = _config_manager.remove_compiler(name)

        if result:
            logger.info(f"编译器配置删除成功: {name}")
            return {
                "success": True,
                "message": f"编译器配置删除成功: {name}",
                "compiler_name": name
            }
        else:
            logger.warning(f"编译器配置不存在: {name}")
            return {
                "success": False,
                "message": f"编译器配置不存在: {name}",
                "compiler_name": name
            }

    except Exception as e:
        error_msg = f"删除过程发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "message": error_msg,
            "compiler_name": name
        }
