"""
DPROJ 文件解析器

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

解析 Delphi 项目文件(.dproj)以提取编译配置
"""

import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from pathlib import Path
from ..utils.logger import get_logger

logger = get_logger(__name__)


class DprojParser:
    """Delphi 项目文件解析器"""

    # MSBuild 命名空间
    MSBUILD_NS = "http://schemas.microsoft.com/developer/msbuild/2003"

    def __init__(self, dproj_path: str):
        """
        初始化解析器

        Args:
            dproj_path: .dproj 文件路径
        """
        self.dproj_path = dproj_path
        self.tree = None
        self.root = None

    def parse(self) -> bool:
        """
        解析 .dproj 文件

        Returns:
            是否解析成功
        """
        try:
            self.tree = ET.parse(self.dproj_path)
            self.root = self.tree.getroot()
            logger.info(f"成功解析 .dproj 文件: {self.dproj_path}")
            return True
        except Exception as e:
            logger.error(f"解析 .dproj 文件失败: {str(e)}")
            return False

    def _find_element(self, parent: ET.Element, tag: str) -> Optional[ET.Element]:
        """
        查找元素(带命名空间)

        Args:
            parent: 父元素
            tag: 标签名

        Returns:
            找到的元素,如果未找到则返回 None
        """
        full_tag = f"{{{self.MSBUILD_NS}}}{tag}"
        return parent.find(full_tag)

    def _find_all_elements(self, parent: ET.Element, tag: str) -> List[ET.Element]:
        """
        查找所有元素(带命名空间)

        Args:
            parent: 父元素
            tag: 标签名

        Returns:
            找到的元素列表
        """
        full_tag = f"{{{self.MSBUILD_NS}}}{tag}"
        return parent.findall(full_tag)

    def get_unit_search_paths(self, config: str = None, platform: str = None) -> List[str]:
        """
        获取单元搜索路径

        Args:
            config: 配置名称(Debug/Release等),如果为 None 则获取所有配置
            platform: 平台名称(Win32/Win64),如果为 None 则获取所有平台

        Returns:
            单元搜索路径列表
        """
        if not self.root:
            logger.error("未解析 .dproj 文件")
            return []

        paths = set()

        # 遍历所有 PropertyGroup
        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            # 检查配置和平台条件
            condition = prop_group.get("Condition", "")

            # 如果指定了配置或平台,检查条件是否匹配
            if config or platform:
                # 检查平台条件
                if platform:
                    # 支持多种平台条件格式
                    platform_patterns = [
                        f"'$(Platform)'=='{platform}'",
                        f"'$(Base_{platform})'!=''",
                        f"'$(Cfg_1_{platform})'!=''",
                        f"'$(Cfg_2_{platform})'!=''",
                        f"'$(Cfg_3_{platform})'!=''"
                    ]
                    if not any(pattern in condition for pattern in platform_patterns):
                        continue

                # 检查配置条件
                if config:
                    config_patterns = [
                        f"'$(Config)'=='{config}'",
                        f"'$(Cfg_1)'!=''" if config == "Debug" else "",
                        f"'$(Cfg_2)'!=''" if config == "Release" else "",
                        f"'$(Cfg_3)'!=''" if config == "Dev" else ""
                    ]
                    config_patterns = [p for p in config_patterns if p]  # 移除空字符串
                    if not any(pattern in condition for pattern in config_patterns):
                        continue

            # 查找 DCC_UnitSearchPath 元素
            unit_search_path_elem = self._find_element(prop_group, "DCC_UnitSearchPath")
            if unit_search_path_elem is not None and unit_search_path_elem.text:
                # 分割路径(使用分号分隔)
                path_str = unit_search_path_elem.text.strip()
                for path in path_str.split(';'):
                    path = path.strip()
                    if path and not path.startswith('$('):  # 忽略 MSBuild 变量
                        # 转换相对路径为绝对路径
                        if not Path(path).is_absolute():
                            project_dir = Path(self.dproj_path).parent
                            path = str((project_dir / path).resolve())
                        paths.add(path)

        logger.info(f"找到 {len(paths)} 个单元搜索路径")
        return list(paths)

    def get_namespace(self, config: str = None, platform: str = None) -> List[str]:
        """
        获取命名空间

        Args:
            config: 配置名称
            platform: 平台名称

        Returns:
            命名空间列表
        """
        if not self.root:
            return []

        namespaces = set()

        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            condition = prop_group.get("Condition", "")

            if config or platform:
                if config and f"'$(Config)'=='{config}'" not in condition:
                    continue
                if platform and f"'$(Platform)'=='{platform}'" not in condition:
                    continue

            namespace_elem = self._find_element(prop_group, "DCC_Namespace")
            if namespace_elem is not None and namespace_elem.text:
                ns_str = namespace_elem.text.strip()
                for ns in ns_str.split(';'):
                    ns = ns.strip()
                    if ns and not ns.startswith('$('):
                        namespaces.add(ns)

        return list(namespaces)

    def get_build_events(self, config: str = None, platform: str = None) -> dict:
        """
        获取编译事件

        Args:
            config: 配置名称
            platform: 平台名称

        Returns:
            编译事件字典,包含 PreBuildEvent, PreLinkEvent 和 PostBuildEvent
        """
        if not self.root:
            return {}

        events = {
            'pre_build': None,
            'pre_link': None,
            'post_build': None,
            'pre_build_ignore_exit_code': False,
            'pre_link_ignore_exit_code': False,
            'post_build_ignore_exit_code': False,
            'post_build_execute_when': None
        }

        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            condition = prop_group.get("Condition", "")

            if config or platform:
                if config and f"'$(Config)'=='{config}'" not in condition:
                    continue
                if platform and f"'$(Platform)'=='{platform}'" not in condition:
                    continue

            # PreBuildEvent
            pre_build_elem = self._find_element(prop_group, "PreBuildEvent")
            if pre_build_elem is not None and pre_build_elem.text:
                events['pre_build'] = pre_build_elem.text.strip()

            # PreLinkEvent
            pre_link_elem = self._find_element(prop_group, "PreLinkEvent")
            if pre_link_elem is not None and pre_link_elem.text:
                events['pre_link'] = pre_link_elem.text.strip()

            # PostBuildEvent
            post_build_elem = self._find_element(prop_group, "PostBuildEvent")
            if post_build_elem is not None and post_build_elem.text:
                events['post_build'] = post_build_elem.text.strip()

            # PreBuildEventIgnoreExitCode
            pre_ignore_elem = self._find_element(prop_group, "PreBuildEventIgnoreExitCode")
            if pre_ignore_elem is not None and pre_ignore_elem.text:
                events['pre_build_ignore_exit_code'] = pre_ignore_elem.text.strip().lower() == 'true'

            # PreLinkEventIgnoreExitCode
            pre_link_ignore_elem = self._find_element(prop_group, "PreLinkEventIgnoreExitCode")
            if pre_link_ignore_elem is not None and pre_link_ignore_elem.text:
                events['pre_link_ignore_exit_code'] = pre_link_ignore_elem.text.strip().lower() == 'true'

            # PostBuildEventIgnoreExitCode
            post_ignore_elem = self._find_element(prop_group, "PostBuildEventIgnoreExitCode")
            if post_ignore_elem is not None and post_ignore_elem.text:
                events['post_build_ignore_exit_code'] = post_ignore_elem.text.strip().lower() == 'true'

            # PostBuildEventExecuteWhen
            post_when_elem = self._find_element(prop_group, "PostBuildEventExecuteWhen")
            if post_when_elem is not None and post_when_elem.text:
                events['post_build_execute_when'] = post_when_elem.text.strip()

        return events

    def get_output_path(self, config: str = None, platform: str = None) -> Optional[str]:
        """
        获取输出路径

        Args:
            config: 配置名称
            platform: 平台名称

        Returns:
            输出路径
        """
        if not self.root:
            return None

        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            condition = prop_group.get("Condition", "")

            if config or platform:
                if config and f"'$(Config)'=='{config}'" not in condition:
                    continue
                if platform and f"'$(Platform)'=='{platform}'" not in condition:
                    continue

            output_elem = self._find_element(prop_group, "DCC_ExeOutput")
            if output_elem is not None and output_elem.text:
                output_path = output_elem.text.strip()
                # 替换变量
                if '$(Platform)' in output_path and platform:
                    output_path = output_path.replace('$(Platform)', platform)
                if '$(Config)' in output_path and config:
                    output_path = output_path.replace('$(Config)', config)

                # 转换为绝对路径
                if not Path(output_path).is_absolute():
                    project_dir = Path(self.dproj_path).parent
                    output_path = str((project_dir / output_path).resolve())

                return output_path

        return None

    def get_conditional_defines(self, config: str = None, platform: str = None) -> List[str]:
        """
        获取条件编译符号

        Args:
            config: 配置名称
            platform: 平台名称

        Returns:
            条件编译符号列表
        """
        if not self.root:
            return []

        defines = set()

        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            condition = prop_group.get("Condition", "")

            if config or platform:
                if config and f"'$(Config)'=='{config}'" not in condition:
                    continue
                if platform and f"'$(Platform)'=='{platform}'" not in condition:
                    continue

            defines_elem = self._find_element(prop_group, "DCC_Define")
            if defines_elem is not None and defines_elem.text:
                define_str = defines_elem.text.strip()
                for define in define_str.split(';'):
                    define = define.strip()
                    if define and not define.startswith('$('):
                        defines.add(define)

        return list(defines)

    def get_main_source(self) -> Optional[str]:
        """
        获取主源文件名

        Returns:
            主源文件名(.dpr 文件名)
        """
        if not self.root:
            return None

        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            main_source_elem = self._find_element(prop_group, "MainSource")
            if main_source_elem is not None and main_source_elem.text:
                return main_source_elem.text.strip()

        return None

    def get_project_info(self) -> Dict:
        """
        获取项目信息

        Returns:
            项目信息字典
        """
        if not self.root:
            return {}

        info = {
            "project_guid": None,
            "project_version": None,
            "framework_type": None,
            "app_type": None,
            "main_source": None,
            "targeted_platforms": None
        }

        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            # 只读取第一个 PropertyGroup(通常包含基本信息)
            if prop_group.get("Condition"):
                continue

            for key in info.keys():
                elem = self._find_element(prop_group, key.title().replace("_", ""))
                if elem is not None and elem.text:
                    info[key] = elem.text.strip()

            # 特殊处理 MainSource
            if info["main_source"] is None:
                main_source_elem = self._find_element(prop_group, "MainSource")
                if main_source_elem is not None and main_source_elem.text:
                    info["main_source"] = main_source_elem.text.strip()

        return info

    def get_project_version(self) -> Optional[str]:
        """
        获取项目版本号

        Returns:
            项目版本号(如 "19.2"),如果未找到则返回 None
        """
        info = self.get_project_info()
        return info.get("project_version")

    def is_file_in_project(self, file_name: str) -> bool:
        """
        检查文件是否属于项目

        Args:
            file_name: 文件名(不含路径)

        Returns:
            文件是否属于项目
        """
        if not self.root:
            return False

        # 检查 ItemGroup 中的 DCCReference
        for item_group in self._find_all_elements(self.root, "ItemGroup"):
            for dcc_ref in self._find_all_elements(item_group, "DCCReference"):
                include = dcc_ref.get("Include", "")
                if include:
                    # 提取文件名
                    ref_file_name = Path(include).name
                    if ref_file_name.lower() == file_name.lower():
                        return True

        # 检查主源文件
        main_source = self.get_main_source()
        if main_source and Path(main_source).name.lower() == file_name.lower():
            return True

        return False
