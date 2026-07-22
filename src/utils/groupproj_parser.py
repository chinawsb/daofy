"""
.groupproj 文件解析器

提供 Delphi 项目组文件(.groupproj)的统一解析逻辑，
被 compile_project 和 install_package 共用。

支持的 XML 节点：
  - <Projects Include="...">           (XE/XE2 旧格式，含 <Dependencies>)
  - <ProjectReference Include="...">   (新版格式)
  - <BuildOrder>                       (编译顺序)
  - <Platforms>                        (支持的平台列表)
  - <Config>/<Platform>                (默认配置)
  - <PropertyGroup>/<ProjectGuid>      (项目 GUID)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)

MSBUILD_NS = "http://schemas.microsoft.com/developer/msbuild/2003"


@dataclass
class GroupProjectInfo:
    """解析后的 .groupproj 结构化信息"""

    # 子项目路径列表（已按 BuildOrder 排序、已去重）
    child_projects: List[Path] = field(default_factory=list)

    # 每个子项目的依赖列表（key = 文件名，value = 依赖文件名列表）
    dependencies: dict[str, List[str]] = field(default_factory=dict)

    # BuildOrder 中定义的编译顺序（文件名列表，可能为空）
    build_order: List[str] = field(default_factory=list)

    # 支持的平台列表（来自 <Platforms> 节点）
    supported_platforms: List[str] = field(default_factory=list)

    # 默认配置（来自 <Config> 节点）
    default_config: Optional[str] = None

    # 默认平台（来自 <Platform> 节点）
    default_platform: Optional[str] = None

    # 项目 GUID
    project_guid: Optional[str] = None


def _tag(ns: str, local: str) -> str:
    """构建带命名空间的标签名"""
    return f"{{{ns}}}{local}"


def _find_all_with_fallback(
    root: ET.Element, ns: str, tag: str
) -> List[ET.Element]:
    """递归搜索带命名空间和不带命名空间的元素（使用 .// 前缀确保搜索嵌套子元素）"""
    results = []
    results.extend(root.findall(f".//{_tag(ns, tag)}"))
    results.extend(root.findall(f".//{tag}"))
    return results


def parse_groupproj(
    group_path: str | Path,
) -> GroupProjectInfo:
    """
    解析 .groupproj 文件，返回结构化信息。

    支持的 XML 节点：
      - <Projects Include="..."> + <Dependencies>  (旧格式)
      - <ProjectReference Include="...">             (新格式)
      - <BuildOrder>                                 (编译顺序)
      - <Platforms>                                  (支持的平台)
      - <Config>/<Platform>                          (默认配置)
      - <PropertyGroup>/<ProjectGuid>                (项目 GUID)

    Args:
        group_path: .groupproj 文件路径

    Returns:
        GroupProjectInfo 结构化信息

    Raises:
        FileNotFoundError: 文件不存在
        ET.ParseError: XML 解析失败
    """
    group_path = Path(group_path)
    group_dir = group_path.parent

    tree = ET.parse(str(group_path))  # noqa: S318 - .groupproj 是本地受信文件，XXE 风险可控
    root = tree.getroot()
    info = GroupProjectInfo()

    # ── 1. PropertyGroup / ProjectGuid ──
    for pg in _find_all_with_fallback(root, MSBUILD_NS, "PropertyGroup"):
        guid_elem = pg.find(_tag(MSBUILD_NS, "ProjectGuid"))
        if guid_elem is None:
            guid_elem = pg.find("ProjectGuid")
        if guid_elem is not None and guid_elem.text:
            info.project_guid = guid_elem.text.strip()
            break

    # ── 2. Config / Platform 默认值 ──
    for pg in _find_all_with_fallback(root, MSBUILD_NS, "PropertyGroup"):
        config_elem = pg.find(_tag(MSBUILD_NS, "Config"))
        if config_elem is None:
            config_elem = pg.find("Config")
        if config_elem is not None and config_elem.text:
            info.default_config = config_elem.text.strip()

        platform_elem = pg.find(_tag(MSBUILD_NS, "Platform"))
        if platform_elem is None:
            platform_elem = pg.find("Platform")
        if platform_elem is not None and platform_elem.text:
            info.default_platform = platform_elem.text.strip()

    # ── 3. ItemGroup → Projects / ProjectReference（收集子项目引用） ──
    seen: set[str] = set()
    deps_map: dict[str, List[str]] = {}

    # 3a. <Projects Include="..."> 旧格式（XE/XE2）
    for proj_elem in _find_all_with_fallback(root, MSBUILD_NS, "Projects"):
        include = proj_elem.get("Include", "")
        if not include:
            continue
        child_path = (group_dir / include).resolve()
        child_key = str(child_path)
        if child_path.exists():
            if child_key not in seen:
                seen.add(child_key)
                info.child_projects.append(child_path)
            # 解析 <Dependencies>
            deps_elem = proj_elem.find(_tag(MSBUILD_NS, "Dependencies"))
            if deps_elem is None:
                deps_elem = proj_elem.find("Dependencies")
            if deps_elem is not None and deps_elem.text:
                deps_map[child_path.name] = [
                    d.strip() for d in deps_elem.text.split(";") if d.strip()
                ]
        else:
            logger.warning("项目组引用的文件不存在，已跳过: %s", child_path)

    # 3b. <ProjectReference Include="..."> 新格式
    for proj_elem in _find_all_with_fallback(root, MSBUILD_NS, "ProjectReference"):
        include = proj_elem.get("Include", "")
        if not include:
            continue
        child_path = (group_dir / include).resolve()
        child_key = str(child_path)
        if child_path.exists():
            if child_key not in seen:
                seen.add(child_key)
                info.child_projects.append(child_path)
        else:
            logger.warning("项目组引用的文件不存在，已跳过: %s", child_path)

    info.dependencies = deps_map

    # ── 4. BuildOrder ──
    for bo in _find_all_with_fallback(root, MSBUILD_NS, "BuildOrder"):
        for ref in bo:
            text = (ref.text or "").strip()
            if text:
                info.build_order.append(text)

    # ── 5. ProjectExtensions → Platforms ──
    for pe in _find_all_with_fallback(root, MSBUILD_NS, "ProjectExtensions"):
        for bp in _find_all_with_fallback(pe, MSBUILD_NS, "BorlandProject"):
            for platforms in _find_all_with_fallback(bp, MSBUILD_NS, "Platforms"):
                for plat in _find_all_with_fallback(platforms, MSBUILD_NS, "Platform"):
                    value = plat.get("value", "")
                    if value:
                        info.supported_platforms.append(value)

    # ── 6. 按 BuildOrder 排序子项目 ──
    _sort_by_build_order(info)

    return info


def _sort_by_build_order(info: GroupProjectInfo) -> None:
    """
    按 BuildOrder 排序子项目。

    排序逻辑：
      1. BuildOrder 中的项目按声明顺序排列
      2. 不在 BuildOrder 中的项目追加到末尾
      3. 如果 BuildOrder 引用了不存在的子项目，忽略该条目
    """
    if not info.build_order or not info.child_projects:
        return

    # 构建 name → index 映射（BuildOrder 中的顺序）
    order_map: dict[str, int] = {}
    for i, name in enumerate(info.build_order):
        order_map[name.lower()] = i

    # 按 BuildOrder 排序，不在 BuildOrder 中的项目排在最后
    info.child_projects.sort(
        key=lambda p: order_map.get(p.name.lower(), len(info.build_order))
    )


def build_dependency_graph(info: GroupProjectInfo) -> dict[str, List[str]]:
    """
    从 <Dependencies> 构建依赖图。

    返回 {子项目文件名: [依赖文件名列表]}。
    如果没有 <Dependencies> 声明，返回空字典。

    Args:
        info: parse_groupproj 返回的结构化信息

    Returns:
        依赖图字典
    """
    return info.dependencies


def topological_sort(
    info: GroupProjectInfo,
) -> List[Path]:
    """
    拓扑排序子项目（基于 <Dependencies> + <BuildOrder>）。

    排序优先级：
      1. 如果有 BuildOrder，直接使用 BuildOrder 顺序
      2. 否则基于 <Dependencies> 做拓扑排序
      3. 都没有则保持原始顺序

    Args:
        info: parse_groupproj 返回的结构化信息

    Returns:
        排序后的子项目路径列表
    """
    # 如果有 BuildOrder，直接使用（已排序）
    if info.build_order:
        return list(info.child_projects)

    # 如果有 Dependencies，做拓扑排序
    if info.dependencies:
        return _topo_sort_with_deps(info)

    # 保持原始顺序
    return list(info.child_projects)


def _topo_sort_with_deps(info: GroupProjectInfo) -> List[Path]:
    """基于 Dependencies 做拓扑排序"""
    # 构建 name → Path 映射
    name_to_path: dict[str, Path] = {}
    for p in info.child_projects:
        name_to_path[p.name.lower()] = p

    # 构建邻接表（依赖 → 被依赖）
    graph: dict[str, List[str]] = {}
    for name, deps in info.dependencies.items():
        key = name.lower()
        graph.setdefault(key, [])
        for dep in deps:
            dep_key = dep.lower()
            graph.setdefault(dep_key, [])
            graph[dep_key].append(key)

    # Kahn's algorithm 拓扑排序
    in_degree: dict[str, int] = {n: 0 for n in graph}
    for node, neighbors in graph.items():
        for neighbor in neighbors:
            in_degree[neighbor] = in_degree.get(neighbor, 0) + 1

    queue = deque(n for n, d in in_degree.items() if d == 0)
    sorted_names: List[str] = []

    while queue:
        node = queue.popleft()
        sorted_names.append(node)
        for neighbor in graph.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # 转换为 Path，未在图中的项目追加到末尾
    result: List[Path] = []
    for name in sorted_names:
        if name in name_to_path:
            result.append(name_to_path[name])

    # 追加不在依赖图中的项目
    sorted_set = set(sorted_names)
    for p in info.child_projects:
        if p.name.lower() not in sorted_set:
            result.append(p)

    return result


def get_platform_for_project(
    info: GroupProjectInfo, fallback: str = "win32"
) -> str:
    """
    从 .groupproj 获取默认平台。

    优先级：
      1. <Platform> 节点
      2. <Platforms> 中的第一个平台
      3. fallback

    Args:
        info: parse_groupproj 返回的结构化信息
        fallback: 默认平台

    Returns:
        平台名称（小写）
    """
    if info.default_platform:
        return info.default_platform.lower()
    if info.supported_platforms:
        return info.supported_platforms[0].lower()
    return fallback.lower()


def get_config_for_project(
    info: GroupProjectInfo, fallback: str = "Debug"
) -> str:
    """
    从 .groupproj 获取默认配置。

    优先级：
      1. <Config> 节点
      2. fallback

    Args:
        info: parse_groupproj 返回的结构化信息
        fallback: 默认配置

    Returns:
        配置名称
    """
    if info.default_config:
        return info.default_config
    return fallback
