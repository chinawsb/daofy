"""
环境检查工具

提供编译器环境检查功能
"""

from typing import Dict, Any, List, Optional
from ..services.config_manager import ConfigManager
from ..utils.validator import Validator
from ..utils.logger import get_logger

logger = get_logger(__name__)

# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None

# 全局第三方库服务实例
_thirdparty_kb_service = None


def set_config_manager(manager: ConfigManager):
    """设置配置管理器实例"""
    global _config_manager
    _config_manager = manager


def set_thirdparty_kb_service(service):
    """设置第三方库知识库服务实例"""
    global _thirdparty_kb_service
    _thirdparty_kb_service = service


async def check_environment() -> Dict[str, Any]:
    """
    检查编译器环境状态

    Returns:
        环境状态字典
    """
    logger.info("收到环境检查请求")

    if _config_manager is None:
        logger.error("配置管理器未初始化")
        return {
            "status": "unavailable",
            "message": "配置管理器未初始化",
            "compilers": [],
            "default_compiler": None
        }

    try:
        compilers = _config_manager.get_all_compilers()
        default_compiler = _config_manager.get_compiler()

        # 检查每个编译器是否可用
        validator = Validator()
        compiler_infos = []

        for compiler in compilers:
            is_valid, _ = validator.validate_compiler_path(compiler.path)
            compiler_infos.append({
                "name": compiler.name,
                "path": compiler.path,
                "version": compiler.version,
                "is_available": is_valid,
                "is_default": compiler.is_default
            })

        # 判断整体状态
        available_count = sum(1 for info in compiler_infos if info["is_available"])
        status = "available" if available_count > 0 else "unavailable"

        logger.info(f"环境检查完成: {available_count}/{len(compilers)} 个编译器可用")

        # 获取第三方库路径
        thirdparty_paths = []
        try:
            if _thirdparty_kb_service:
                thirdparty_paths = _thirdparty_kb_service.get_library_paths()
        except Exception as e:
            logger.warning(f"获取第三方库路径失败: {e}")

        return {
            "status": status,
            "message": f"共 {len(compilers)} 个编译器配置,{available_count} 个可用",
            "compilers": compiler_infos,
            "default_compiler": default_compiler.name if default_compiler else None,
            "thirdparty_paths": thirdparty_paths
        }

    except Exception as e:
        error_msg = f"环境检查过程发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "status": "unavailable",
            "message": error_msg,
            "compilers": [],
            "default_compiler": None
        }


async def get_compile_history(limit: int = 10) -> Dict[str, Any]:
    """
    获取编译历史记录

    Args:
        limit: 最大记录数

    Returns:
        编译历史字典
    """
    logger.info(f"收到获取编译历史请求,限制: {limit}")

    if _config_manager is None:
        logger.error("配置管理器未初始化")
        return {
            "success": False,
            "message": "配置管理器未初始化",
            "entries": []
        }

    try:
        entries = _config_manager.get_history(limit)

        return {
            "success": True,
            "message": f"共 {len(entries)} 条历史记录",
            "entries": [e.to_dict() for e in entries]
        }

    except Exception as e:
        error_msg = f"获取编译历史过程发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "message": error_msg,
            "entries": []
        }
