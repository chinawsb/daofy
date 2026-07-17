"""
编译器插件基类

定义所有编译器插件必须实现的接口。

核心能力分层:
  - 必须实现: compile, detect, parse_project
  - 可选覆盖: file_handling, kb_search, project_management
    插件未覆盖的核心能力由 MCP Server 的核心服务提供默认实现。

工具归属:
  - 每个插件通过 owned_tools 声明自己拥有的 MCP 工具名
  - 插件未拥有的工具由核心服务提供
  - handler 引用在 Phase 2 由 server.py 注入到 registry
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
    handler: Optional[Callable] = None  # async def handler(arguments: dict) -> Any


class CompilerPlugin(ABC):
    """编译器插件基类 — 每种语言/编译器实现一个。

    Phase 1: 注册骨架，handler 由 server.py 管理。
    Phase 2: 插件声明工具归属，handler 由 registry 注入。
    Phase 3+: handler 提取到插件模块。
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

    # ── 工具归属声明 ──

    def get_owned_tool_names(self) -> List[str]:
        """返回此插件拥有的 MCP 工具名列表。

        Phase 2: 只声明名称，handler 由 server.py 注入到 registry。
        Phase 3: handler 迁移到插件模块后，返回完整 ToolDefinition。
        """
        return []

    # ── 可选覆盖: 编码规范 ──

    def get_coding_rules(self, section: str = None) -> str:
        """返回语言编码规范（可选覆盖）"""
        return ""

    # ── 工具注册 ──

    def get_tools(self) -> List[ToolDefinition]:
        """返回插件注册的 MCP 工具列表。

        Phase 2: 返回空列表，handler 由 registry 管理。
        Phase 3: 返回完整 ToolDefinition 列表。
        """
        return []
