"""
日志工具模块

提供统一的日志配置和获取方法
"""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str = "delphi_mcp",
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    配置并返回日志记录器

    Args:
        name: 日志记录器名称
        level: 日志级别
        log_file: 日志文件路径,如果为 None 则不输出到文件
        format_string: 日志格式字符串

    Returns:
        配置好的日志记录器
    """
    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 默认日志格式
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    formatter = logging.Formatter(format_string)

    # 添加控制台处理器 - 使用stderr避免干扰MCP协议
    # 设置UTF-8编码以正确显示中文
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # 设置流编码为UTF-8
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

    logger.addHandler(console_handler)

    # 添加文件处理器
    if log_file:
        # 确保日志目录存在
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "delphi_mcp") -> logging.Logger:
    """
    获取日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        日志记录器实例
    """
    return logging.getLogger(name)


# 默认日志记录器
_default_logger: Optional[logging.Logger] = None


def init_default_logger(log_file: str = "logs/delphi_mcp.log") -> logging.Logger:
    """
    初始化默认日志记录器

    Args:
        log_file: 日志文件路径

    Returns:
        默认日志记录器
    """
    global _default_logger
    _default_logger = setup_logger(log_file=log_file)
    return _default_logger


def get_default_logger() -> logging.Logger:
    """
    获取默认日志记录器

    Returns:
        默认日志记录器实例
    """
    global _default_logger
    if _default_logger is None:
        _default_logger = init_default_logger()
    return _default_logger
