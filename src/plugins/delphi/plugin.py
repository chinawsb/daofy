"""
Delphi 编译器插件

Phase 1: 委托到现有 compiler_service / dproj_parser 等模块，零重写。
Phase 2: 工具归属声明 (get_owned_tool_names)。
Phase 3: handler 提取到 handlers.py，get_tools() 返回完整 ToolDefinition。
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import CompilerPlugin, PluginInfo, ToolDefinition


class DelphiPlugin(CompilerPlugin):
    """Delphi 编译器插件

    工具注册: 声明 Delphi 专属工具名 → 路由到 server.py 已有处理器。
    编译: 委托 compiler_service (MSBuild / DCC)。
    解析: 委托 dproj_parser。
    """

    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="delphi",
            display_name="Delphi",
            version="1.0.0",
            description="Embarcadero Delphi 编译器支持 (MSBuild/DCC)",
            supported_extensions=[".dproj", ".dpr", ".dpk"],
        )

    # ── detect ──

    async def detect(self) -> List[Dict[str, Any]]:
        """检测已安装的 Delphi 编译器"""
        from ...services.config_manager import ConfigManager
        cm = ConfigManager()
        return cm._detect_delphi_from_registry()

    # ── compile ──

    async def compile(self, project_path: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """编译 Delphi 项目 (委托 compiler_service)"""
        from ...services.compiler_service import CompilerService
        from ...services.config_manager import ConfigManager

        cm = ConfigManager()
        cs = CompilerService(cm)

        result = await cs.compile_project(
            project_path=project_path,
            target_platform=options.get("target_platform", "win32"),
            build_configuration=options.get("build_configuration", "Debug"),
            extra_args=options.get("extra_args"),
            output_path=options.get("output_path"),
            compiler_version=options.get("compiler_version"),
            conditional_defines=options.get("conditional_defines"),
            unit_search_paths=options.get("unit_search_paths"),
            resource_search_paths=options.get("resource_search_paths"),
            optimize=options.get("optimize"),
            debug=options.get("debug"),
            warning_level=options.get("warning_level", 2),
            disabled_warnings=options.get("disabled_warnings", set()),
            output_type=options.get("output_type", "gui"),
        )
        return result.to_dict()

    # ── parse_project ──

    def parse_project(self, project_path: str) -> Optional[Dict[str, Any]]:
        """解析 Delphi 项目文件 (.dproj)"""
        if not project_path.endswith(('.dproj', '.dpr', '.dpk')):
            return None

        from ...utils.dproj_parser import DprojParser
        parser = DprojParser(project_path)
        if not parser.parse():
            return None

        info = parser.get_project_info()
        return {
            "name": info.get("name", ""),
            "platform": "delphi",
            "file_path": project_path,
            "info": info,
        }

    # ── 编码规范 ──
    # Phase 1: get_coding_rules 仍在 server.py 闭包中实现，
    # 此处保留接口定义供 Phase 2 迁移。

    def get_coding_rules(self, section: str = None) -> str:
        """获取 Delphi 编码规范

        Phase 2 TODO: 迁移 get_coding_rules 实现到此处。
        """
        return ""  # Phase 2: 实现完整逻辑

    # ── 工具归属声明 (Phase 2) + handler 提取 (Phase 3) ──

    def get_owned_tool_names(self) -> List[str]:
        """Delphi 插件拥有的 MCP 工具名列表"""
        return [
            "delphi_project",
            "delphi_file",
            "delphi_kb",
            "manage_component",
            "get_coding_rules",
            "package",
            "check_environment",
            "delphi_rtti",
            "automate_delphi",
        ]

    def get_tools(self) -> List[ToolDefinition]:
        """返回 Delphi 插件注册的 MCP 工具 (Phase 3: 完整 ToolDefinition)"""
        from .handlers import DELPHI_HANDLERS
        return [
            ToolDefinition(
                name=name,
                description=self._TOOL_DESCRIPTIONS.get(name, f"Delphi 工具: {name}"),
                input_schema=self._TOOL_SCHEMAS.get(name, {"type": "object", "properties": {}}),
                handler=handler,
            )
            for name, handler in DELPHI_HANDLERS.items()
            if name != "file_tool"  # file_tool 是 delphi_file 的兼容别名，不单独注册
        ]

    # 工具描述和 schema 元数据
    _TOOL_DESCRIPTIONS = {
        "delphi_project": "Delphi 项目全生命周期管理：编译/配置/审计/部署",
        "delphi_file": "Delphi 文件必用读写/搜索/替换/备份工具",
        "delphi_kb": "知识库搜索/管理",
        "manage_component": "DFM组件增/删/改/生成",
        "get_coding_rules": "编码规则获取工具 — 支持 Delphi 和 Lazarus/FPC 编码规范，支持按语言/章节分段获取",
        "package": "组件包编译安装/列出",
        "check_environment": "环境检查/编译器检测/安装",
        "delphi_rtti": "RTTI 发现/调用",
        "automate_delphi": "Delphi 自动化测试",
    }

    _TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {}  # schema 由 server.py list_tools 提供
