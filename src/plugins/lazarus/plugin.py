"""
Lazarus/FPC 编译器插件

Phase 1: 委托到现有 compiler_service.compile_with_lazbuild / lpi_parser，
不重复任何业务逻辑。
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

        # 映射 target_platform 字符串到枚举
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

        # .lpr → 查找同名 .lpi
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

    # ── 工具注册 ──

    def get_tools(self) -> List[ToolDefinition]:
        """返回 Lazarus 插件注册的 MCP 工具

        Phase 1: 只注册编译和检测工具。
        Lazarus 不需要 delphi_file / delphi_kb / manage_component 等 Delphi 专属工具。
        """
        return [
            ToolDefinition(
                name="lazarus_compile",
                description="Lazarus/Free Pascal 项目编译 (lazbuild)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_path": {
                            "type": "string",
                            "description": ".lpi 或 .lpr 文件路径",
                        },
                        "target_platform": {
                            "type": "string",
                            "enum": ["win32", "win64"],
                            "default": "win32",
                        },
                        "build_configuration": {
                            "type": "string",
                            "description": "Default/Release/Debug",
                        },
                        "timeout": {
                            "type": "integer",
                            "default": 600,
                        },
                    },
                    "required": ["project_path"],
                },
                handler=self.compile,
            ),
        ]
