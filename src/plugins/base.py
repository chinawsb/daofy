"""
编译器插件基类

定义所有编译器插件必须实现的接口。

核心能力分层:
  - 必须实现: compile, detect, parse_project
  - 可选覆盖: file_handling, kb_search, project_management
    插件未覆盖的核心能力由 MCP Server 的核心服务提供默认实现。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Callable


@dataclass
class PluginInfo:
    """插件元信息"""
    name: str
    display_name: str
    version: str = "1.0.0"
    description: str = ""
    supported_extensions: List[str] = field(default_factory=list)


@dataclass
class ToolDefinition:
    """MCP 工具声明（由插件注册到核心）"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable  # async def handler(arguments: dict) -> Any


class CompilerPlugin(ABC):
    """编译器插件基类 — 每种语言/编译器实现一个。

    Phase 1: 委托到现有代码，零重写。
    Phase 2+: 各语言独立优化实现。
    """

    # ── 必须实现 ──

    @property
    @abstractmethod
    def info(self) -> PluginInfo:
        """插件元信息"""
        ...

    @abstractmethod
    async def detect(self) -> List[Dict[str, Any]]:
        """检测本机已安装的该编译器实例"""
        ...

    @abstractmethod
    async def compile(self, project_path: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """执行编译"""
        ...

    @abstractmethod
    def parse_project(self, project_path: str) -> Optional[Dict[str, Any]]:
        """解析项目文件，提取源文件列表、依赖、配置等"""
        ...

    # ── 可选覆盖: 文件处理 ──
    # 默认: 插件不提供，核心服务不注册对应工具

    def file_read(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """读取源码文件（可选覆盖）"""
        raise NotImplementedError

    def file_write(self, file_path: str, edits: List[Dict], **kwargs) -> Dict[str, Any]:
        """写入源码文件（可选覆盖）"""
        raise NotImplementedError

    def file_format(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """格式化源码文件（可选覆盖）"""
        raise NotImplementedError

    # ── 可选覆盖: 知识库 ──

    def kb_search(self, query: str, **kwargs) -> Dict[str, Any]:
        """搜索知识库（可选覆盖）"""
        raise NotImplementedError

    def kb_build(self, **kwargs) -> Dict[str, Any]:
        """构建知识库（可选覆盖）"""
        raise NotImplementedError

    # ── 可选覆盖: 项目管理 ──

    def project_audit(self, base_dir: str, **kwargs) -> Dict[str, Any]:
        """审计项目代码（可选覆盖）"""
        raise NotImplementedError

    def project_info(self, project_path: str, **kwargs) -> Dict[str, Any]:
        """获取项目信息（可选覆盖）"""
        raise NotImplementedError

    # ── 可选覆盖: 编码规范 ──

    def get_coding_rules(self, section: str = None) -> str:
        """返回语言编码规范（可选覆盖）"""
        return ""

    # ── 工具注册 ──

    def get_tools(self) -> List[ToolDefinition]:
        """返回插件注册的 MCP 工具列表。

        默认: 只注册 compile 工具。
        Delphi 插件会额外注册 delphi_file, delphi_kb 等。
        """
        return [
            ToolDefinition(
                name=f"{self.info.name}_compile",
                description=f"{self.info.display_name} 项目编译",
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_path": {"type": "string"},
                    },
                    "required": ["project_path"],
                },
                handler=self.compile,
            ),
        ]
