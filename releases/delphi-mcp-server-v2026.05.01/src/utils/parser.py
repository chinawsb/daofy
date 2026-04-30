"""
输出解析器

解析 Delphi 编译器输出,提取错误和警告信息
"""

import re
from typing import List
from ..models.compile_result import CompileMessage
from ..utils.logger import get_logger

logger = get_logger(__name__)


class OutputParser:
    """Delphi 编译器输出解析器"""

    # 错误/警告正则表达式模式
    # 格式: Error: File.pas(10,5): Error message
    # 格式: Warning: File.pas(20,10): Warning message
    # 格式: Fatal: File.pas(1,1): Fatal error
    MESSAGE_PATTERN = re.compile(
        r'(?P<type>Error|Warning|Fatal):\s+'
        r'(?P<file>[^(]+)\((?P<line>\d+),(?P<column>\d+)\):\s+'
        r'(?P<message>.+)'
    )

    # 致命错误模式(无行号)
    FATAL_PATTERN = re.compile(
        r'Fatal:\s+(?P<message>.+)'
    )

    def parse(self, output: str) -> List[CompileMessage]:
        """
        解析编译器输出

        Args:
            output: 编译器输出字符串

        Returns:
            编译消息列表
        """
        messages = []

        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue

            # 尝试匹配标准错误/警告格式
            match = self.MESSAGE_PATTERN.match(line)
            if match:
                message_type = match.group('type').lower()
                if message_type == 'fatal':
                    message_type = 'error'

                messages.append(CompileMessage(
                    file_path=match.group('file').strip(),
                    line=int(match.group('line')),
                    column=int(match.group('column')),
                    message=match.group('message').strip(),
                    message_type=message_type
                ))
                continue

            # 尝试匹配致命错误格式(无行号)
            match = self.FATAL_PATTERN.match(line)
            if match:
                messages.append(CompileMessage(
                    file_path="",
                    line=0,
                    column=0,
                    message=match.group('message').strip(),
                    message_type='error'
                ))

        logger.debug(f"解析到 {len(messages)} 条消息")
        return messages

    def parse_errors(self, output: str) -> List[CompileMessage]:
        """
        仅解析错误消息

        Args:
            output: 编译器输出字符串

        Returns:
            错误消息列表
        """
        messages = self.parse(output)
        errors = [m for m in messages if m.message_type == 'error']
        logger.debug(f"解析到 {len(errors)} 条错误")
        return errors

    def parse_warnings(self, output: str) -> List[CompileMessage]:
        """
        仅解析警告消息

        Args:
            output: 编译器输出字符串

        Returns:
            警告消息列表
        """
        messages = self.parse(output)
        warnings = [m for m in messages if m.message_type == 'warning']
        logger.debug(f"解析到 {len(warnings)} 条警告")
        return warnings

    def has_errors(self, output: str) -> bool:
        """
        检查输出中是否有错误

        Args:
            output: 编译器输出字符串

        Returns:
            是否有错误
        """
        # 检查是否包含 Error 或 Fatal
        return bool(re.search(r'\b(Error|Fatal)\b:', output))

    def has_warnings(self, output: str) -> bool:
        """
        检查输出中是否有警告

        Args:
            output: 编译器输出字符串

        Returns:
            是否有警告
        """
        return bool(re.search(r'\bWarning\b:', output))

    def extract_error_summary(self, output: str) -> str:
        """
        提取错误摘要

        Args:
            output: 编译器输出字符串

        Returns:
            错误摘要字符串
        """
        errors = self.parse_errors(output)
        if not errors:
            return "无错误"

        summary_lines = []
        for error in errors[:5]:  # 最多显示前 5 个错误
            if error.file_path:
                summary_lines.append(f"{error.file_path}({error.line},{error.column}): {error.message}")
            else:
                summary_lines.append(error.message)

        if len(errors) > 5:
            summary_lines.append(f"... 还有 {len(errors) - 5} 个错误")

        return '\n'.join(summary_lines)
