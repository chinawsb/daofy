"""
编译结果模型

定义编译结果相关的数据模型
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from enum import Enum
from pathlib import Path


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
    output_files: List[str] = field(default_factory=list)  # 所有输出产物路径（exe/dll/bpl/bpi/dcp等）
    warnings: List[CompileMessage] = field(default_factory=list)
    errors: List[CompileMessage] = field(default_factory=list)
    duration: int = 0  # 毫秒
    log: str = ""  # 完整编译日志

    def to_dict(self, strip_log: bool = True) -> Dict[str, Any]:
        """转换为字典

        Args:
            strip_log: 是否去除编译器版权横幅（Embarcadero / Copyright 行）
        """
        log = self._strip_compiler_header(self.log) if strip_log else self.log
        result: Dict[str, Any] = {
            "status": self.status.value,
            "duration": self.duration,
        }
        # 输出产物列表（首项即主目标文件 exe/dll/bpl）
        if self.output_files:
            result["output_files"] = self.output_files
        if self.status != CompileStatus.SUCCESS:
            if self.error_code:
                result["error_code"] = self.error_code
            if self.error_message:
                result["error_message"] = self.error_message
        if self.errors:
            result["errors"] = [e.to_dict() for e in self.errors]
        if self.warnings:
            result["warnings"] = [w.to_dict() for w in self.warnings]
        if log:
            result["log"] = log
        return result

    @staticmethod
    def _strip_compiler_header(log: str) -> str:
        """移除编译器输出中每次重复的版权/版本横幅行
        
        MSBuild 输出：
          Microsoft(R) 生成引擎版本 4.8.9221.0
          [Microsoft .NET Framework 版本 4.0.30319.42000]
          版权所有 (C) Microsoft Corporation。保留所有权利。
        dcc32 输出：
          Embarcadero Delphi for Win32 compiler version 37.0
          Copyright (c) 1983,2026 Embarcadero Technologies, Inc.
        保留有用行：
          256 lines, 0.14 seconds, 1000288 bytes code, 44080 bytes data.
        """
        if not log:
            return log
        lines = log.splitlines(keepends=True)
        keep = []
        for l in lines:
            s = l.strip()
            if not s:
                continue
            # MSBuild 版本横幅
            if s.startswith('Microsoft(') or s.startswith('[Microsoft .NET Framework'):
                continue
            # MSBuild 中文版权
            if s.startswith('版权所有'):
                continue
            # Delphi 编译器版本 + 版权
            if s.startswith('Embarcadero Delphi') or s.startswith('Copyright (c)'):
                continue
            keep.append(l)
        return ''.join(keep)

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
