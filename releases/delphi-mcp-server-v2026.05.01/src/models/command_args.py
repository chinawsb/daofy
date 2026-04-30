"""
命令行参数模型

定义命令行参数相关的数据模型
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any


@dataclass
class CommandArgs:
    """命令行参数"""
    compiler_executable: str
    project_file: str
    arguments: List[str]
    full_command: str
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    def has_warnings(self) -> bool:
        """是否有警告"""
        return len(self.warnings) > 0

    def get_argument_string(self) -> str:
        """获取参数字符串(不包含编译器路径)"""
        return " ".join(self.arguments)
