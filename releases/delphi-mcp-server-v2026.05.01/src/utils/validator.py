"""
验证工具

提供通用的验证功能
"""

import os
from pathlib import Path
from typing import Tuple
from ..utils.logger import get_logger

logger = get_logger(__name__)


class Validator:
    """验证工具类"""

    @staticmethod
    def validate_project_path(path: str) -> Tuple[bool, str]:
        """
        验证项目路径

        Args:
            path: 项目文件路径

        Returns:
            (是否有效, 错误消息)
        """
        if not path:
            return False, "项目路径不能为空"

        # 检查路径是否包含 ".."
        if ".." in path:
            return False, "项目路径不能包含 '..'"

        # 检查文件是否存在
        if not os.path.exists(path):
            return False, f"项目文件不存在: {path}"

        # 检查是否为文件
        if not os.path.isfile(path):
            return False, f"项目路径不是文件: {path}"

        # 检查文件扩展名
        if not (path.endswith('.dproj') or path.endswith('.dpr')):
            return False, f"项目文件必须是 .dproj 或 .dpr 格式"

        logger.debug(f"项目路径验证通过: {path}")
        return True, ""

    @staticmethod
    def validate_file_path(path: str) -> Tuple[bool, str]:
        """
        验证文件路径

        Args:
            path: 文件路径

        Returns:
            (是否有效, 错误消息)
        """
        if not path:
            return False, "文件路径不能为空"

        # 检查路径是否包含 ".."
        if ".." in path:
            return False, "文件路径不能包含 '..'"

        # 检查文件是否存在
        if not os.path.exists(path):
            return False, f"文件不存在: {path}"

        # 检查是否为文件
        if not os.path.isfile(path):
            return False, f"路径不是文件: {path}"

        # 检查文件扩展名
        if not path.endswith('.pas'):
            return False, f"文件必须是 .pas 格式"

        logger.debug(f"文件路径验证通过: {path}")
        return True, ""

    @staticmethod
    def validate_compiler_path(path: str) -> Tuple[bool, str]:
        """
        验证编译器路径

        Args:
            path: 编译器可执行文件路径

        Returns:
            (是否有效, 错误消息)
        """
        if not path:
            return False, "编译器路径不能为空"

        # 检查路径是否包含 ".."
        if ".." in path:
            return False, "编译器路径不能包含 '..'"

        # 检查文件是否存在
        if not os.path.exists(path):
            return False, f"编译器文件不存在: {path}"

        # 检查是否为文件
        if not os.path.isfile(path):
            return False, f"编译器路径不是文件: {path}"

        # 检查是否为可执行文件
        if not (path.endswith('.exe') or path.endswith('.bat') or path.endswith('.cmd')):
            return False, f"编译器必须是可执行文件(.exe, .bat, .cmd)"

        logger.debug(f"编译器路径验证通过: {path}")
        return True, ""

    @staticmethod
    def validate_output_path(path: str) -> Tuple[bool, str]:
        """
        验证输出路径

        Args:
            path: 输出目录路径

        Returns:
            (是否有效, 错误消息)
        """
        if not path:
            return True, ""  # 输出路径可选,为空时使用默认路径

        # 检查路径是否包含 ".."
        if ".." in path:
            return False, "输出路径不能包含 '..'"

        # 检查目录是否存在
        if not os.path.exists(path):
            return False, f"输出目录不存在: {path}"

        # 检查是否为目录
        if not os.path.isdir(path):
            return False, f"输出路径不是目录: {path}"

        # 检查是否有写入权限
        if not os.access(path, os.W_OK):
            return False, f"输出目录无写入权限: {path}"

        logger.debug(f"输出路径验证通过: {path}")
        return True, ""

    @staticmethod
    def validate_search_paths(paths: list) -> Tuple[bool, str]:
        """
        验证搜索路径列表

        Args:
            paths: 搜索路径列表

        Returns:
            (是否有效, 错误消息)
        """
        if not paths:
            return True, ""  # 搜索路径可选

        for path in paths:
            # 检查路径是否包含 ".."
            if ".." in path:
                return False, f"搜索路径不能包含 '..': {path}"

            # 检查目录是否存在
            if not os.path.exists(path):
                logger.warning(f"搜索路径不存在: {path}")
                # 不阻止编译,只记录警告

        logger.debug(f"搜索路径验证通过")
        return True, ""

    @staticmethod
    def validate_timeout(timeout: int) -> Tuple[bool, str]:
        """
        验证超时时间

        Args:
            timeout: 超时时间(秒)

        Returns:
            (是否有效, 错误消息)
        """
        if timeout <= 0:
            return False, f"超时时间必须为正数: {timeout}"

        if timeout > 3600:  # 最大 1 小时
            return False, f"超时时间不能超过 3600 秒: {timeout}"

        logger.debug(f"超时时间验证通过: {timeout}")
        return True, ""

    @staticmethod
    def validate_warning_level(level: int) -> Tuple[bool, str]:
        """
        验证警告级别

        Args:
            level: 警告级别(0-4)

        Returns:
            (是否有效, 错误消息)
        """
        if not 0 <= level <= 4:
            return False, f"警告级别必须在 0-4 之间: {level}"

        logger.debug(f"警告级别验证通过: {level}")
        return True, ""
