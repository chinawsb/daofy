"""
编译器配置模型

定义编译器配置相关的数据模型
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


@dataclass
class CompilerConfig:
    """编译器配置"""
    name: str
    path: str
    is_default: bool = False
    version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CompilerConfig':
        """从字典创建实例"""
        return cls(
            name=data.get('name', ''),
            path=data.get('path', ''),
            is_default=data.get('is_default', False),
            version=data.get('version')
        )


@dataclass
class ConfigFile:
    """配置文件结构"""
    compilers: List[CompilerConfig] = field(default_factory=list)
    default_compiler: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "compilers": [c.to_dict() for c in self.compilers],
            "default_compiler": self.default_compiler
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConfigFile':
        """从字典创建实例"""
        compilers = [CompilerConfig.from_dict(c) for c in data.get('compilers', [])]
        return cls(
            compilers=compilers,
            default_compiler=data.get('default_compiler')
        )

    def get_compiler(self, name: str) -> Optional[CompilerConfig]:
        """获取指定名称的编译器配置"""
        for compiler in self.compilers:
            if compiler.name == name:
                return compiler
        return None

    def get_default_compiler(self) -> Optional[CompilerConfig]:
        """获取默认编译器配置"""
        # 优先使用 default_compiler 字段
        if self.default_compiler:
            return self.get_compiler(self.default_compiler)

        # 否则查找 is_default 为 True 的编译器
        for compiler in self.compilers:
            if compiler.is_default:
                return compiler

        # 如果都没有,返回第一个编译器
        if self.compilers:
            return self.compilers[0]

        return None

    def add_compiler(self, compiler: CompilerConfig):
        """添加编译器配置"""
        # 如果设为默认,取消其他默认设置
        if compiler.is_default:
            for c in self.compilers:
                c.is_default = False
            self.default_compiler = compiler.name

        # 检查是否已存在同名编译器
        existing = self.get_compiler(compiler.name)
        if existing:
            # 更新现有配置
            existing.path = compiler.path
            existing.is_default = compiler.is_default
            existing.version = compiler.version
        else:
            # 添加新配置
            self.compilers.append(compiler)

    def remove_compiler(self, name: str) -> bool:
        """删除编译器配置"""
        for i, compiler in enumerate(self.compilers):
            if compiler.name == name:
                self.compilers.pop(i)
                # 如果删除的是默认编译器,清除默认设置
                if self.default_compiler == name:
                    self.default_compiler = None
                return True
        return False

    def set_default_compiler(self, name: str) -> bool:
        """设置默认编译器"""
        compiler = self.get_compiler(name)
        if compiler:
            # 取消其他默认设置
            for c in self.compilers:
                c.is_default = False
            # 设置新的默认编译器
            compiler.is_default = True
            self.default_compiler = name
            return True
        return False
