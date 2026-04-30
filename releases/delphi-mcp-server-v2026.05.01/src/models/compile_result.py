"""
编译结果模型

定义编译结果相关的数据模型
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from enum import Enum


class CompileStatus(Enum):
    """编译状态枚举"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class CompileMessage:
    """编译消息(错误或警告)"""
    file_path: str
    line: int
    column: int
    message: str
    message_type: str  # "error" | "warning" | "fatal"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class CompileResult:
    """编译结果"""
    status: CompileStatus
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    output_file: Optional[str] = None
    warnings: List[CompileMessage] = field(default_factory=list)
    errors: List[CompileMessage] = field(default_factory=list)
    duration: int = 0  # 毫秒
    log: str = ""  # 完整编译日志

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "status": self.status.value,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "output_file": self.output_file,
            "warnings": [w.to_dict() for w in self.warnings],
            "errors": [e.to_dict() for e in self.errors],
            "duration": self.duration,
            "log": self.log
        }
        return result

    def has_errors(self) -> bool:
        """是否有错误"""
        return len(self.errors) > 0 or self.status == CompileStatus.FAILED

    def has_warnings(self) -> bool:
        """是否有警告"""
        return len(self.warnings) > 0

    def get_error_count(self) -> int:
        """获取错误数量"""
        return len(self.errors)

    def get_warning_count(self) -> int:
        """获取警告数量"""
        return len(self.warnings)

    def get_summary(self) -> str:
        """获取编译结果摘要"""
        if self.status == CompileStatus.SUCCESS:
            return f"编译成功,耗时 {self.duration}ms,警告 {self.get_warning_count()} 个"
        elif self.status == CompileStatus.TIMEOUT:
            return f"编译超时,耗时 {self.duration}ms"
        else:
            return f"编译失败,错误 {self.get_error_count()} 个,警告 {self.get_warning_count()} 个,耗时 {self.duration}ms"
