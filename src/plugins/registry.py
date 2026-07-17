"""
插件注册表

管理插件注册、按文件扩展名路由、收集工具列表。
"""

from typing import Dict, List, Optional, Any
from pathlib import Path

from .base import CompilerPlugin, PluginInfo, ToolDefinition


class PluginRegistry:
    """插件注册表 — 按文件扩展名路由到对应插件"""

    def __init__(self):
        self._plugins: Dict[str, CompilerPlugin] = {}  # name -> plugin
        self._ext_map: Dict[str, str] = {}  # ext -> plugin_name

    def register(self, plugin: CompilerPlugin) -> None:
        """注册插件"""
        info = plugin.info
        self._plugins[info.name] = plugin
        for ext in info.supported_extensions:
            self._ext_map[ext.lower()] = info.name

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

    def collect_tools(self) -> List[ToolDefinition]:
        """收集所有插件注册的 MCP 工具"""
        tools: List[ToolDefinition] = []
        for plugin in self._plugins.values():
            tools.extend(plugin.get_tools())
        return tools

    def get_tool_handler(self, tool_name: str) -> Optional[Any]:
        """按工具名查找对应的处理器"""
        for plugin in self._plugins.values():
            for tool_def in plugin.get_tools():
                if tool_def.name == tool_name:
                    return tool_def.handler
        return None
