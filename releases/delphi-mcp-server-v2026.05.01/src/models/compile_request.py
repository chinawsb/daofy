"""
编译请求模型

定义编译请求相关的数据模型
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class TargetPlatform(Enum):
    """目标平台枚举"""
    WIN32 = "win32"
    WIN64 = "win64"


class OutputType(Enum):
    """输出类型枚举"""
    CONSOLE = "console"
    GUI = "gui"
    DLL = "dll"


class RuntimeLibrary(Enum):
    """运行时库链接方式枚举"""
    STATIC = "static"
    DYNAMIC = "dynamic"


@dataclass
class CompileOptions:
    """编译选项"""
    target_platform: TargetPlatform = TargetPlatform.WIN32
    output_path: Optional[str] = None
    compiler_version: Optional[str] = None
    timeout: int = 600
    conditional_defines: List[str] = field(default_factory=list)
    unit_search_paths: List[str] = field(default_factory=list)
    resource_search_paths: List[str] = field(default_factory=list)
    optimization_enabled: bool = True
    debug_info_enabled: bool = False
    warning_level: int = 2
    disabled_warnings: List[str] = field(default_factory=list)
    output_type: OutputType = OutputType.GUI
    runtime_library: RuntimeLibrary = RuntimeLibrary.STATIC
    build_configuration: Optional[str] = None

    def __post_init__(self):
        """验证字段"""
        # 验证警告级别
        if not 0 <= self.warning_level <= 4:
            raise ValueError(f"警告级别必须在 0-4 之间,当前值: {self.warning_level}")

        # 验证超时时间
        if self.timeout <= 0:
            raise ValueError(f"超时时间必须为正数,当前值: {self.timeout}")


@dataclass
class ProjectCompileRequest:
    """工程编译请求"""
    project_path: str
    options: CompileOptions = field(default_factory=CompileOptions)

    def __post_init__(self):
        """验证项目路径"""
        if not self.project_path:
            raise ValueError("项目路径不能为空")

        # 验证文件扩展名
        if not (self.project_path.endswith('.dproj') or self.project_path.endswith('.dpr')):
            raise ValueError(f"项目文件必须是 .dproj 或 .dpr 格式,当前路径: {self.project_path}")


@dataclass
class FileCompileRequest:
    """单文件编译请求"""
    file_path: str
    unit_search_paths: List[str] = field(default_factory=list)
    warning_level: int = 2
    disabled_warnings: List[str] = field(default_factory=list)

    def __post_init__(self):
        """验证文件路径"""
        if not self.file_path:
            raise ValueError("文件路径不能为空")

        # 验证文件扩展名
        if not self.file_path.endswith('.pas'):
            raise ValueError(f"文件必须是 .pas 格式,当前路径: {self.file_path}")

        # 验证警告级别
        if not 0 <= self.warning_level <= 4:
            raise ValueError(f"警告级别必须在 0-4 之间,当前值: {self.warning_level}")
