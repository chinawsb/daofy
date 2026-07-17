"""
Lazarus/FPC 编译器插件

Phase 1: 委托到现有 compiler_service.compile_with_lazbuild / lpi_parser，
         不重复任何业务逻辑。
Phase 2: 工具归属声明 (get_owned_tool_names)。
Phase 5: handler 提取到 handlers.py，get_tools() 返回完整 ToolDefinition。
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import CompilerPlugin, PluginInfo, ToolDefinition
from ...utils.logger import get_logger

logger = get_logger(__name__)


class LazarusPlugin(CompilerPlugin):
    """Lazarus/Free Pascal 编译器插件"""

    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="lazarus",
            display_name="Lazarus/Free Pascal",
            version="1.0.0",
            description="Lazarus IDE / Free Pascal 编译器支持 (lazbuild)",
            supported_extensions=[".lpi", ".lpr", ".lpk"],
        )

    # ── detect ──

    async def detect(self) -> List[Dict[str, Any]]:
        """检测已安装的 Lazarus/FPC 编译器"""
        from ...services.config_manager import ConfigManager
        cm = ConfigManager()
        compilers = cm._detect_lazarus()
        return [
            {
                "name": c.name,
                "path": c.path,
                "version": c.version,
                "compiler_type": c.compiler_type,
            }
            for c in compilers
        ]

    # ── compile ──

    async def compile(self, project_path: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """编译 Lazarus 项目 (委托 compiler_service.compile_with_lazbuild)"""
        from ...services.compiler_service import CompilerService
        from ...services.config_manager import ConfigManager
        from ...models.compile_request import ProjectCompileRequest, CompileOptions, TargetPlatform

        platform_map = {
            "win32": TargetPlatform.WIN32,
            "win64": TargetPlatform.WIN64,
        }
        target = platform_map.get(options.get("target_platform", "win32"), TargetPlatform.WIN32)

        build_config = options.get("build_configuration")
        timeout = options.get("timeout", 600)

        compile_opts = CompileOptions(
            target_platform=target,
            build_configuration=build_config,
            timeout=timeout,
        )
        request = ProjectCompileRequest(
            project_path=project_path,
            options=compile_opts,
        )

        cm = ConfigManager()
        cs = CompilerService(cm)
        result = await cs.compile_with_lazbuild(request)
        return result.to_dict()

    # ── parse_project ──

    def parse_project(self, project_path: str) -> Optional[Dict[str, Any]]:
        """解析 Lazarus 项目文件 (.lpi)"""
        if not project_path.endswith(('.lpi', '.lpr', '.lpk')):
            return None

        from ...utils.lpi_parser import LpiParser

        p = Path(project_path)
        if p.suffix.lower() == '.lpr':
            lpi_path = p.with_suffix('.lpi')
            if not lpi_path.exists():
                return None
            project_path = str(lpi_path)

        parser = LpiParser(project_path)
        if not parser.parse():
            return None

        info = parser.get_project_info()
        return {
            "name": info.get("name", ""),
            "platform": "lazarus",
            "file_path": project_path,
            "info": info,
        }

    # ── 工具归属声明 (Phase 2) + handler 提取 (Phase 5) ──

    def get_owned_tool_names(self) -> List[str]:
        """Lazarus 插件拥有的 MCP 工具名列表"""
        return [
            "lazarus_compile",
            "lazarus_project",
        ]

    def get_tools(self) -> List[ToolDefinition]:
        """返回 Lazarus 插件注册的 MCP 工具 (Phase 5: 完整 ToolDefinition)"""
        from .handlers import LAZARUS_HANDLERS
        return [
            ToolDefinition(
                name=name,
                description=self._TOOL_DESCRIPTIONS.get(name, f"Lazarus 工具: {name}"),
                input_schema=self._TOOL_SCHEMAS.get(name, {"type": "object", "properties": {}}),
                handler=handler,
            )
            for name, handler in LAZARUS_HANDLERS.items()
        ]

    # 工具描述和 schema 元数据
    _TOOL_DESCRIPTIONS = {
        "lazarus_compile": "Lazarus/Free Pascal 项目编译 (lazbuild)",
        "lazarus_project": "Lazarus 项目信息查询 — 解析 .lpi 文件",
    }

    _TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {}
