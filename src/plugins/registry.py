"""
插件注册表

动态发现 + 注册 + 按文件扩展名路由 + handler 分发。

核心机制:
  1. discover(plugins_dir) 扫描 src/plugins/*/plugin.py，
     importlib 动态加载 CompilerPlugin 子类并实例化。
  2. register_handlers(handlers, descriptions, schemas, owner) 注册 handler + schema，
     由各插件 handler 模块自行调用。
  3. collect_tools() 返回所有工具定义（ToolDefinition），供 list_tools() 使用。
  4. get_handler() 按工具名路由到 handler，供 call_tool() 使用。
"""

import importlib
import logging
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path

from .base import CompilerPlugin, PluginInfo, ToolDefinition

logger = logging.getLogger(__name__)


class PluginRegistry:
    """插件注册表 — 动态发现 + handler 分发 + schema 收集"""

    def __init__(self):
        self._plugins: Dict[str, CompilerPlugin] = {}  # name -> plugin
        self._ext_map: Dict[str, str] = {}  # ext -> plugin_name
        self._tool_handlers: Dict[str, Callable] = {}  # tool_name -> handler
        self._tool_descriptions: Dict[str, str] = {}  # tool_name -> description
        self._tool_schemas: Dict[str, Dict[str, Any]] = {}  # tool_name -> inputSchema
        self._tool_owner: Dict[str, str] = {}  # tool_name -> plugin_name
        self._aliases: set = set()  # 别名工具名（不暴露给 MCP 客户端）

    # ── 插件动态发现 ──

    def discover(self, plugins_dir: str | Path) -> None:
        """扫描 plugins_dir/*/plugin.py，动态加载 CompilerPlugin 子类。

        目录结构约定:
          src/plugins/<name>/
            __init__.py
            plugin.py    # 必须包含 CompilerPlugin 子类
            handlers.py  # 可选，handler 函数

        跳过:
          - __pycache__、以 _ 或 . 开头的目录
          - base.py、registry.py 等非 plugin 目录
          - core/ 目录（核心工具单独注册）
        """
        plugins_path = Path(plugins_dir)
        if not plugins_path.is_dir():
            logger.warning(f"插件目录不存在: {plugins_path}")
            return

        for pkg_dir in sorted(plugins_path.iterdir()):
            if not pkg_dir.is_dir():
                continue
            name = pkg_dir.name
            # 跳过特殊目录
            if name.startswith(("_", ".")) or name == "core":
                continue
            plugin_file = pkg_dir / "plugin.py"
            if not plugin_file.exists():
                continue

            try:
                module = importlib.import_module(f"src.plugins.{name}.plugin")
            except Exception as e:
                logger.error(f"导入插件模块失败: src.plugins.{name}.plugin — {e}", exc_info=True)
                continue

            # 查找 CompilerPlugin 子类
            found = False
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type)
                        and issubclass(attr, CompilerPlugin)
                        and attr is not CompilerPlugin):
                    try:
                        plugin_instance = attr()
                        self.register(plugin_instance)
                        found = True
                        logger.info(f"动态加载插件: {plugin_instance.info.display_name} "
                                    f"(tools: {plugin_instance.get_owned_tool_names()})")
                    except Exception as e:
                        logger.error(f"实例化插件 {attr_name} 失败: {e}", exc_info=True)

            if not found:
                logger.warning(f"插件目录 {name}/ 中未找到 CompilerPlugin 子类")

    # ── 插件注册 ──

    def register(self, plugin: CompilerPlugin) -> None:
        """注册插件 + 收集其 ToolDefinition（含 handler + schema）

        如果 plugin.is_available() 返回 False，跳过该插件的工具注册，
        仅保留插件元信息（名称、扩展名映射），避免暴露不可用的工具。
        """
        info = plugin.info
        self._plugins[info.name] = plugin
        for ext in info.supported_extensions:
            self._ext_map[ext.lower()] = info.name

        if not plugin.is_available():
            logger.info(f"插件 {info.display_name} 未检测到开发工具，跳过工具注册")
            return

        # 收集插件声明的工具归属
        for tool_name in plugin.get_owned_tool_names():
            self._tool_owner[tool_name] = info.name

        # 从 get_tools() 收集 handler + schema + description
        for tool_def in plugin.get_tools():
            if tool_def.handler:
                self._tool_handlers[tool_def.name] = tool_def.handler
            if tool_def.description:
                self._tool_descriptions[tool_def.name] = tool_def.description
            if tool_def.input_schema:
                self._tool_schemas[tool_def.name] = tool_def.input_schema

    # ── Handler 模块注册（各插件 handler 模块自行调用）──

    def register_handlers(
        self,
        handlers: Dict[str, Callable],
        descriptions: Dict[str, str] | None = None,
        schemas: Dict[str, Dict[str, Any]] | None = None,
        owner: str | None = None,
        aliases: set | None = None,
    ) -> None:
        """注册 handler 模块导出的工具 — handler + description + schema 一次注册。

        由各插件的 handlers.py 模块在导入时调用：
            _plugin_registry.register_handlers(
                CORE_HANDLERS, CORE_TOOL_DESCRIPTIONS, CORE_TOOL_SCHEMAS)
        """
        for name, handler in handlers.items():
            self._tool_handlers[name] = handler
            if owner:
                self._tool_owner[name] = owner
        if descriptions:
            self._tool_descriptions.update(descriptions)
        if schemas:
            self._tool_schemas.update(schemas)
        if aliases:
            self._aliases.update(aliases)

    def get_handler(self, tool_name: str) -> Optional[Callable]:
        """按工具名获取 handler"""
        return self._tool_handlers.get(tool_name)

    # ── 工具定义收集（供 list_tools 使用）──

    def collect_tools(self) -> List[ToolDefinition]:
        """收集所有工具定义（插件 + 核心），供 server.py list_tools() 使用。

        返回的 ToolDefinition 包含 name, description, inputSchema, handler。
        别名工具（如 file_tool）不包含在内。
        """
        tools: List[ToolDefinition] = []
        for name in self._tool_handlers:
            if name in self._aliases:
                continue
            tools.append(ToolDefinition(
                name=name,
                description=self._tool_descriptions.get(name, f"工具: {name}"),
                input_schema=self._tool_schemas.get(name, {"type": "object", "properties": {}}),
                handler=self._tool_handlers[name],
            ))
        return tools

    # ── 查询方法 ──

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

    def dispatch(self, tool_name: str, arguments: dict) -> Any:
        """分发工具调用到对应 handler"""
        handler = self._tool_handlers.get(tool_name)
        if handler:
            return handler(arguments)
        return None
