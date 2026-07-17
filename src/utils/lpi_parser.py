"""
LPI 文件解析器

解析 Lazarus/Free Pascal 项目文件(.lpi)以提取编译配置
"""

import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from pathlib import Path
from ..utils.logger import get_logger

logger = get_logger(__name__)


class LpiParser:
    """Lazarus 项目文件解析器"""

    def __init__(self, lpi_path: str):
        """
        初始化解析器

        Args:
            lpi_path: .lpi 文件路径
        """
        self.lpi_path = lpi_path
        self.tree = None
        self.root = None

    def parse(self) -> bool:
        """
        解析 .lpi 文件

        Returns:
            是否解析成功
        """
        try:
            self.tree = ET.parse(self.lpi_path)
            self.root = self.tree.getroot()
            logger.info(f"成功解析 .lpi 文件: {self.lpi_path}")
            return True
        except Exception as e:
            logger.error(f"解析 .lpi 文件失败: {str(e)}")
            return False

    def get_unit_search_paths(self, config: str = None) -> List[str]:
        """
        获取单元搜索路径

        Args:
            config: 配置名称 (Default/Debug/Release)

        Returns:
            单元搜索路径列表
        """
        if self.root is None:
            logger.error("未解析 .lpi 文件")
            return []

        paths = set()

        # 查找 PublishInfo 下的 CompilerOptions
        compiler_options = self.root.find(".//CompilerOptions")
        if compiler_options is None:
            return []

        # 查找 SearchPaths
        search_paths = compiler_options.find("SearchPaths")
        if search_paths is None:
            return []

        # 读取 OtherUnitFiles
        other_unit_files = search_paths.find("OtherUnitFiles")
        if other_unit_files is not None and other_unit_files.text:
            for path in other_unit_files.text.split(";"):
                path = path.strip()
                if path and not path.startswith("$("):
                    if not Path(path).is_absolute():
                        project_dir = Path(self.lpi_path).parent
                        path = str((project_dir / path).resolve())
                    paths.add(path)

        # 读取 UnitPath
        unit_path = search_paths.find("UnitPath")
        if unit_path is not None and unit_path.text:
            for path in unit_path.text.split(";"):
                path = path.strip()
                if path and not path.startswith("$("):
                    if not Path(path).is_absolute():
                        project_dir = Path(self.lpi_path).parent
                        path = str((project_dir / path).resolve())
                    paths.add(path)

        logger.info(f"找到 {len(paths)} 个单元搜索路径")
        return list(paths)

    def get_main_source(self) -> Optional[str]:
        """
        获取主源文件名 (.lpr)

        Returns:
            主源文件名
        """
        if self.root is None:
            return None

        # 查找 PublishInfo 下的 MainUnit
        main_unit = self.root.find(".//MainUnit")
        if main_unit is not None:
            filename = main_unit.get("Filename")
            if filename:
                return filename

        return None

    def get_project_info(self) -> Dict:
        """
        获取项目信息

        Returns:
            项目信息字典
        """
        if self.root is None:
            return {}

        info = {
            "project_name": None,
            "main_source": None,
            "unit_count": 0,
        }

        # 查找 ProjectInfo
        project_info = self.root.find(".//ProjectInfo")
        if project_info is not None:
            title = project_info.find("Title")
            if title is not None and title.text:
                info["project_name"] = title.text.strip()

        # 获取主源文件
        info["main_source"] = self.get_main_source()

        # 统计单元数量
        units = self.root.findall(".//Unit")
        info["unit_count"] = len(units)

        return info

    def get_units(self) -> List[Dict[str, str]]:
        """
        获取项目中的所有单元

        Returns:
            单元列表，每个单元包含 Filename 和 IsPartOfProject
        """
        if self.root is None:
            return []

        units = []
        for unit_elem in self.root.findall(".//Unit"):
            filename = unit_elem.get("Filename")
            is_part = unit_elem.get("IsPartOfProject", "True")
            if filename:
                units.append({
                    "filename": filename,
                    "is_part_of_project": is_part.lower() == "true",
                })

        return units

    def get_compiler_options(self) -> Dict:
        """
        获取编译器选项

        Returns:
            编译器选项字典
        """
        if self.root is None:
            return {}

        options = {
            "target_cpu": None,
            "target_os": None,
            "generate_debugging_info": False,
            "optimization_level": 0,
        }

        compiler_options = self.root.find(".//CompilerOptions")
        if compiler_options is None:
            return options

        # Target
        target = compiler_options.find("Target")
        if target is not None:
            cpu = target.find("CPU")
            if cpu is not None and cpu.text:
                options["target_cpu"] = cpu.text.strip()
            os_elem = target.find("OS")
            if os_elem is not None and os_elem.text:
                options["target_os"] = os_elem.text.strip()

        # Debugging
        debugging = compiler_options.find("Debugging")
        if debugging is not None:
            gen_debug = debugging.find("GenerateDebugInfo")
            if gen_debug is not None:
                options["generate_debugging_info"] = gen_debug.get("Value", "").lower() == "true"

        # Optimization
        optimization = compiler_options.find("Optimization")
        if optimization is not None:
            level = optimization.find("Level")
            if level is not None and level.text:
                try:
                    options["optimization_level"] = int(level.text.strip())
                except ValueError:
                    pass

        return options
