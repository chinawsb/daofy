"""
工具函数包

包含编码检测、路径处理等通用工具函数
"""

import ctypes
import locale
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_console_encoding(oem: bool = False) -> str:
    """获取当前控制台的实际编码。

    在 Windows 上，控制台代码页（GetConsoleOutputCP）可能与系统 ANSI 编码
    （locale.getpreferredencoding）不同。例如 Python 启用 UTF-8 模式时，
    控制台代码页为 65001 (UTF-8)，但 ANSI 编码仍为 cp936 (GBK)。

    解码子进程输出时使用控制台代码页（oem=False），确保中文正确显示。
    写入 batch 文件时使用 OEM 代码页（oem=True），因为 cmd.exe 只认 OEM 编码。

    Args:
        oem: True 时返回 OEM 代码页（用于 batch 文件），False 时返回控制台代码页

    Returns:
        编码名称字符串，如 'cp65001'、'cp936'、'utf-8' 等
    """
    try:
        if oem:
            cp = ctypes.windll.kernel32.GetOEMCP()
        else:
            cp = ctypes.windll.kernel32.GetConsoleOutputCP()
        if cp > 0:
            return f'cp{cp}'
    except Exception as e:
        logger.debug("获取编码失败（回退到 ANSI 编码）: %s", e)
    return locale.getpreferredencoding()
