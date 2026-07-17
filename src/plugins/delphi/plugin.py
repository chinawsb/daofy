"""
Delphi 编译器插件

Phase 1: 委托到现有 compiler_service / dproj_parser 等模块，零重写。
工具处理器引用 server.py 中已有的函数引用，不重复包装。
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

    # ── 工具归属声明 ──
    # Phase 2: 插件声明拥有哪些工具名，handler 由 server.py 注入到 registry。

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
