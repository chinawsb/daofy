"""
插件注册表

管理插件注册、按文件扩展名路由、收集工具列表、handler 分发。

Phase 2: 从 server.py 接收 _TOOL_HANDLERS 映射，
将工具名归属到对应插件，提供统一的 list_tools / call_tool 接口。
"""

from typing import Dict, List, Optional, Any, Callable
from pathlib import Path

from .base import CompilerPlugin, PluginInfo, ToolDefinition


class PluginRegistry:
    """插件注册表 — 扩展名路由 + 工具归属 + handler 分发"""

    def __init__(self):
        self._plugins: Dict[str, CompilerPlugin] = {}  # name -> plugin
        self._ext_map: Dict[str, str] = {}  # ext -> plugin_name
        self._tool_handlers: Dict[str, Callable] = {}  # tool_name -> handler
        self._tool_owner: Dict[str, str] = {}  # tool_name -> plugin_name

    def register(self, plugin: CompilerPlugin) -> None:
        """注册插件"""
        info = plugin.info
        self._plugins[info.name] = plugin
        for ext in info.supported_extensions:
            self._ext_map[ext.lower()] = info.name

        # 记录工具归属
        for tool_name in plugin.get_owned_tool_names():
            self._tool_owner[tool_name] = info.name

    def register_handlers(self, handlers: Dict[str, Callable]) -> None:
        """从 server.py 的 _TOOL_HANDLERS 注入 handler 映射。

        Phase 2: server.py 调用此方法将现有 handler 注册到 registry。
        Phase 3: handler 迁移到插件模块后，此方法退化为验证工具归属。
        """
        self._tool_handlers.update(handlers)

    def get_plugin(self, name: str) -> Optional[CompilerPlugin]:
        """按名称获取插件"""
        return self._plugins.get(name)

    def get_plugin_for_file(self, file_path: str) -> Optional[CompilerPlugin]:
        """按文件扩展名获取插件"""
        ext = Path(file_path).suffix.lower()
        name = self._ext_map.get(ext)
        if name:
            return self._plugins.get(name)
        return None

    def get_all_plugins(self) -> List[CompilerPlugin]:
        """获取所有已注册插件"""
        return list(self._plugins.values())

    def get_all_extensions(self) -> Dict[str, str]:
        """获取扩展名 -> 插件名映射"""
        return dict(self._ext_map)

    def get_tool_owner(self, tool_name: str) -> Optional[str]:
        """获取工具归属的插件名"""
        return self._tool_owner.get(tool_name)

    def get_plugin_tools(self, plugin_name: str) -> List[str]:
        """获取指定插件拥有的工具名列表"""
        return [name for name, owner in self._tool_owner.items()
                if owner == plugin_name]

    def get_core_tools(self) -> List[str]:
        """获取核心（非插件）工具名列表"""
        return [name for name in self._tool_handlers
                if name not in self._tool_owner]

    def get_handler(self, tool_name: str) -> Optional[Callable]:
        """按工具名获取 handler"""
        return self._tool_handlers.get(tool_name)

    def dispatch(self, tool_name: str, arguments: dict) -> Any:
        """分发工具调用到对应 handler

        Returns:
            handler 异步调用的结果，未找到返回 None
        """
        handler = self._tool_handlers.get(tool_name)
        if handler:
            return handler(arguments)
        return None

    def collect_tools(self) -> List[ToolDefinition]:
        """收集所有插件注册的 MCP 工具"""
        tools: List[ToolDefinition] = []
        for plugin in self._plugins.values():
            tools.extend(plugin.get_tools())
        return tools
