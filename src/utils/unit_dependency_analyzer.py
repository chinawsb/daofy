"""
单元依赖分析器

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

分析 Delphi 项目的单元依赖关系，智能匹配需要的库路径
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import json

from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class UnitInfo:
    """单元信息"""
    name: str  # 单元名称（如 'Classes' 或 'System.Classes'）
    full_name: str  # 完整名称
    file_path: Optional[str] = None  # 文件路径
    is_namespace: bool = False  # 是否是命名空间单元（如 System.Classes）
    
    def __hash__(self):
        return hash(self.name.lower())
    
    def __eq__(self, other):
        if isinstance(other, UnitInfo):
            return self.name.lower() == other.name.lower()
        return False


@dataclass
class ProjectDependencies:
    """项目依赖信息"""
    project_path: str
    units: Set[UnitInfo] = field(default_factory=set)  # 项目直接引用的单元
    missing_units: Set[str] = field(default_factory=set)  # 找不到的单元
    resolved_paths: Dict[str, str] = field(default_factory=dict)  # 单元名 -> 文件路径
    
    def get_unit_names(self) -> Set[str]:
        """获取所有单元名称（小写）"""
        return {u.name.lower() for u in self.units}


class UnitDependencyAnalyzer:
    """单元依赖分析器"""
    
    def __init__(self):
        self.file_extensions = {'.pas', '.dpr', '.dpk'}
        # 缓存：路径 -> {单元名 -> 文件路径}
        self._path_cache: Dict[str, Dict[str, str]] = {}
        
    def analyze_project(self, project_path: str, 
                       search_paths: Optional[List[str]] = None) -> ProjectDependencies:
        """
        分析项目依赖
        
        Args:
            project_path: 项目文件路径(.dpr 或 .dproj)
            search_paths: 额外的搜索路径
            
        Returns:
            项目依赖信息
        """
        project_path_obj = Path(project_path)
        deps = ProjectDependencies(project_path=str(project_path_obj))
        
        # 获取项目目录
        project_dir = project_path_obj.parent
        
        # 1. 收集项目中的所有源码文件
        source_files = self._collect_source_files(project_dir, project_path_obj)
        logger.info(f"找到 {len(source_files)} 个源码文件")
        
        # 2. 提取所有引用的单元
        all_units: Set[UnitInfo] = set()
        for source_file in source_files:
            units = self._extract_uses_from_file(source_file)
            all_units.update(units)
        
        deps.units = all_units
        logger.info(f"项目引用了 {len(all_units)} 个单元")
        
        # 3. 解析单元位置
        self._resolve_unit_locations(deps, search_paths or [])
        
        return deps
    
    def _collect_source_files(self, project_dir: Path, project_file: Path) -> List[Path]:
        """收集项目中的源码文件"""
        source_files = []
        
        # 首先添加项目文件本身
        if project_file.suffix.lower() in self.file_extensions:
            source_files.append(project_file)
        
        # 递归查找项目目录下的所有源码文件
        for ext in self.file_extensions:
            for file_path in project_dir.rglob(f"*{ext}"):
                # 排除一些常见目录
                if self._should_include_file(file_path, project_dir):
                    source_files.append(file_path)
        
        return source_files
    
    def _should_include_file(self, file_path: Path, project_dir: Path) -> bool:
        """判断是否应该包含该文件"""
        # 转换为相对路径
        try:
            rel_path = file_path.relative_to(project_dir)
            rel_str = str(rel_path).lower()
            
            # 排除的目录
            exclude = {
                '__recovery', '__history', 'backup', '.git', '.svn',
                'win32', 'win64', 'debug', 'release',  # 输出目录
            }
            
            parts = rel_str.split(os.sep)
            for part in parts[:-1]:  # 不包括文件名
                if part in exclude:
                    return False
            
            return True
        except ValueError:
            return True
    
    def _extract_uses_from_file(self, file_path: Path) -> Set[UnitInfo]:
        """从文件中提取 uses 子句中的单元"""
        units = set()
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 跳过太大的文件（可能是二进制或异常文件）
            if len(content) > 10 * 1024 * 1024:  # 10MB
                logger.warning(f"跳过过大文件: {file_path} ({len(content)} bytes)")
                return units
            
            # 匹配 uses 子句（支持多行）
            # 匹配 uses 后面跟着的单元列表，直到分号
            uses_pattern = r'\buses\s+([^;]+);'
            matches = re.findall(uses_pattern, content, re.IGNORECASE | re.DOTALL)
            
            for match in matches:
                # 清理注释
                match = re.sub(r'\{[^}]*\}', '', match)  # 删除 {注释}
                match = re.sub(r'\(\*[^\*]*\*\)', '', match)  # 删除 (*注释*)
                match = re.sub(r'//.*$', '', match, flags=re.MULTILINE)  # 删除 //注释
                
                # 分割单元名
                unit_names = [u.strip() for u in match.split(',') if u.strip()]
                
                for unit_name in unit_names:
                    # 验证单元名称是否有效
                    if not self._is_valid_unit_name(unit_name):
                        continue
                    
                    # 处理命名空间（如 System.Classes）
                    is_namespace = '.' in unit_name
                    simple_name = unit_name.split('.')[-1] if is_namespace else unit_name
                    
                    unit_info = UnitInfo(
                        name=simple_name,
                        full_name=unit_name,
                        is_namespace=is_namespace
                    )
                    units.add(unit_info)
            
        except Exception as e:
            logger.warning(f"提取 uses 失败 {file_path}: {e}")
        
        return units
    
    def _is_valid_unit_name(self, name: str) -> bool:
        """
        验证是否为有效的 Pascal 单元名称
        
        有效单元名规则:
        - 必须以字母或下划线开头
        - 只能包含字母、数字、下划线
        - 不能包含空格、特殊字符
        - 不能是常见英文单词（非 Delphi 关键字）
        """
        if not name:
            return False
        
        # 去除引号和in关键字（处理 "in 'filename'" 这种）
        name = name.strip().strip("'\"")
        if name.lower().startswith('in '):
            return False
        
        # 检查是否包含无效字符
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$', name):
            return False
        
        # 检查长度限制
        if len(name) > 64:
            return False
        
        # 检查是否为垃圾文本（包含常见英文单词组合）
        name_lower = name.lower()
        garbage_patterns = [
            'the', 'first', 'second', 'third', 'pointer', 'block', 'free',
            'reserved', 'list', 'memory', 'stack', 'heap', 'address',
            'null', 'void', 'integer', 'string', 'char', 'byte', 'word',
            'error', 'warning', 'debug', 'info', 'exception', 'failed'
        ]
        
        # 如果名称太短且是常见单词，跳过
        if len(name_lower) <= 3 and name_lower in (
            'the', 'for', 'var', 'end', 'not', 'and', 'or', 'but', 'out', 'log',
            'sys', 'obj', 'ini', 'cfg', 'app', 'msg', 'err', 'dbg'
        ):
            return False
        
        # 如果名称中有多个连续的小写单词（垃圾文本特征）
        parts = name_lower.split('.')
        for part in parts:
            if len(part) > 20:
                return False
        
        return True
    
    def _resolve_unit_locations(self, deps: ProjectDependencies, 
                                additional_paths: List[str]):
        """解析单元位置"""
        unit_names = deps.get_unit_names()
        
        # 1. 首先检查项目目录本身
        project_dir = Path(deps.project_path).parent
        self._scan_path_for_units(project_dir, unit_names, deps, "项目目录")
        
        # 2. 检查额外的搜索路径
        for path in additional_paths:
            if Path(path).exists():
                self._scan_path_for_units(Path(path), unit_names, deps, f"搜索路径: {path}")
        
        # 3. 记录未找到的单元
        found_units = {u.lower() for u in deps.resolved_paths.keys()}
        deps.missing_units = {u for u in unit_names if u.lower() not in found_units}
        
        if deps.missing_units:
            logger.warning(f"未找到 {len(deps.missing_units)} 个单元: {list(deps.missing_units)[:10]}")
    
    def _scan_path_for_units(self, path: Path, target_units: Set[str], 
                             deps: ProjectDependencies, source: str):
        """扫描路径查找单元"""
        path_str = str(path)
        
        # 使用缓存
        if path_str in self._path_cache:
            cached_units = self._path_cache[path_str]
            for unit_name in target_units:
                if unit_name.lower() in cached_units and unit_name.lower() not in deps.resolved_paths:
                    deps.resolved_paths[unit_name] = cached_units[unit_name.lower()]
            return
        
        # 扫描目录
        unit_map: Dict[str, str] = {}
        
        try:
            for file_path in path.rglob("*.pas"):
                unit_name = file_path.stem.lower()
                if unit_name not in unit_map:
                    unit_map[unit_name] = str(file_path)
                
                # 检查是否是目标单元
                if unit_name in target_units and unit_name not in deps.resolved_paths:
                    deps.resolved_paths[unit_name] = str(file_path)
                    logger.debug(f"在 {source} 找到单元 {unit_name}: {file_path}")
        except Exception as e:
            logger.warning(f"扫描路径失败 {path}: {e}")
        
        # 缓存结果
        self._path_cache[path_str] = unit_map


class SmartLibraryPathResolver:
    """智能库路径解析器
    
    处理优先级（从高到低）：
    1. 项目目录下的单元（最优先）
    2. 全局库路径中后引入的单元（覆盖前面的）
    3. 用户显式传入的路径（直接跳过智能分析）
    """
    
    def __init__(self, thirdparty_kb_service=None):
        self.analyzer = UnitDependencyAnalyzer()
        self.thirdparty_kb_service = thirdparty_kb_service
        
    def resolve_library_paths(self, project_path: str, 
                             platform: str = "Win32",
                             user_search_paths: Optional[List[str]] = None) -> Tuple[List[str], Dict]:
        """
        智能解析项目需要的库路径
        
        Args:
            project_path: 项目文件路径
            platform: 目标平台
            user_search_paths: 用户显式传入的搜索路径（如果提供，直接返回）
            
        Returns:
            (需要的库路径列表, 详细信息字典)
        """
        # 如果用户显式传入了路径，直接使用，不再分析
        if user_search_paths:
            logger.info(f"用户使用显式传入的 {len(user_search_paths)} 个路径，跳过智能分析")
            return user_search_paths, {
                "mode": "user_provided",
                "total_paths": len(user_search_paths),
                "paths": user_search_paths
            }
        
        logger.info(f"开始智能解析项目库路径: {project_path}")
        
        # 1. 分析项目依赖
        deps = self.analyzer.analyze_project(project_path)
        
        info = {
            "total_units": len(deps.units),
            "missing_units_before": len(deps.missing_units),
            "missing_unit_names": list(deps.missing_units),
        }
        
        # 2. 获取所有第三方库路径
        if self.thirdparty_kb_service:
            all_thirdparty_paths = self.thirdparty_kb_service.get_library_paths()
        else:
            # 如果没有服务，使用全局函数
            from ..services.knowledge_base.thirdparty_knowledge_base import ThirdPartyKnowledgeBase
            kb = ThirdPartyKnowledgeBase()
            all_thirdparty_paths = kb.get_library_paths()
        
        logger.info(f"全局第三方库路径数量: {len(all_thirdparty_paths)}")
        
        # 3. 扫描所有路径，建立单元 -> 路径的映射
        # 优先级：项目目录 > 后引入的全局路径（后面的覆盖前面的）
        project_dir = Path(project_path).parent
        unit_to_path: Dict[str, Tuple[str, int]] = {}  # 单元名 -> (路径, 优先级)
        
        # 首先扫描项目目录（优先级最高 = 0）
        if deps.missing_units:
            project_units = self._scan_path_for_units_with_priority(
                str(project_dir), deps.missing_units, priority=0
            )
            for unit, path in project_units.items():
                unit_to_path[unit] = (path, 0)
            logger.info(f"项目目录提供了 {len(project_units)} 个单元")
        
        # 然后扫描全局库路径（优先级递增，后面的覆盖前面的）
        remaining_units = deps.missing_units - set(unit_to_path.keys())
        
        for idx, lib_path in enumerate(all_thirdparty_paths):
            if not remaining_units:
                break
            
            # 优先级从1开始递增，后面的优先级更高
            priority = idx + 1
            found_units = self._scan_path_for_units_with_priority(
                lib_path, remaining_units, priority=priority
            )
            
            for unit, path in found_units.items():
                # 如果单元已存在，只有新优先级 >= 旧优先级时才覆盖
                if unit not in unit_to_path or priority >= unit_to_path[unit][1]:
                    unit_to_path[unit] = (path, priority)
                    remaining_units.discard(unit)
        
        # 4. 收集需要的路径（去重并保持引入顺序）
        # 按优先级分组路径
        priority_to_paths: Dict[int, Set[str]] = defaultdict(set)
        for unit, (path, priority) in unit_to_path.items():
            priority_to_paths[priority].add(path)
        
        # 按优先级排序（0最先，然后1,2,3...）
        needed_paths = []
        seen_paths = set()
        for priority in sorted(priority_to_paths.keys()):
            for path in priority_to_paths[priority]:
                if path not in seen_paths:
                    needed_paths.append(path)
                    seen_paths.add(path)
        
        resolved_units = set(unit_to_path.keys())
        
        info.update({
            "mode": "smart_resolve",
            "needed_paths_count": len(needed_paths),
            "total_paths_count": len(all_thirdparty_paths),
            "resolved_units": len(resolved_units),
            "still_missing": len(remaining_units),
            "still_missing_units": sorted(remaining_units),
            "selected_paths": needed_paths,
            "unit_to_path": {u: p[0] for u, p in unit_to_path.items()},
        })
        
        logger.info(f"智能解析完成: 从 {len(all_thirdparty_paths)} 个路径中"
                   f"选择了 {len(needed_paths)} 个路径，"
                   f"解决了 {len(resolved_units)} 个单元依赖，"
                   f"仍有 {len(remaining_units)} 个未找到")
        
        return needed_paths, info
    
    def _scan_path_for_units_with_priority(self, path: str, 
                                           target_units: Set[str],
                                           priority: int) -> Dict[str, str]:
        """
        扫描路径查找目标单元，返回单元名 -> 路径的映射
        
        Args:
            path: 要扫描的路径
            target_units: 目标单元集合
            priority: 优先级（用于日志）
            
        Returns:
            找到的单元映射 {单元名: 路径}
        """
        found = {}
        path_obj = Path(path)
        
        if not path_obj.exists():
            return found
        
        try:
            for file_path in path_obj.rglob("*.pas"):
                unit_name = file_path.stem.lower()
                if unit_name in target_units:
                    found[unit_name] = str(path)
                    logger.debug(f"[优先级{priority}] 找到单元 {unit_name}: {path}")
        except Exception as e:
            logger.warning(f"扫描路径失败 {path}: {e}")
        
        return found
    
    def generate_response_file(self, project_path: str, 
                               unit_paths: List[str]) -> str:
        """
        生成响应文件（解决命令行过长问题）
        
        Args:
            project_path: 项目路径
            unit_paths: 单元搜索路径列表
            
        Returns:
            响应文件路径
        """
        project_dir = Path(project_path).parent
        response_file = project_dir / "__compile_response__.txt"
        
        with open(response_file, 'w', encoding='utf-8') as f:
            f.write(f"-U{';'.join(unit_paths)}\n")
        
        logger.info(f"生成响应文件: {response_file}")
        return str(response_file)


def analyze_project_units(project_path: str) -> Dict:
    """
    分析项目单元的便捷函数
    
    Args:
        project_path: 项目文件路径
        
    Returns:
        分析结果字典
    """
    analyzer = UnitDependencyAnalyzer()
    deps = analyzer.analyze_project(project_path)
    
    return {
        "project": project_path,
        "total_units": len(deps.units),
        "units": sorted([u.name for u in deps.units]),
        "missing_units": sorted(deps.missing_units),
        "resolved_units": deps.resolved_paths,
    }


def smart_resolve_library_paths(project_path: str, 
                                platform: str = "Win32",
                                user_search_paths: Optional[List[str]] = None) -> Tuple[List[str], Dict]:
    """
    智能解析库路径的便捷函数
    
    Args:
        project_path: 项目文件路径
        platform: 目标平台
        user_search_paths: 用户显式传入的搜索路径（如果提供，直接返回）
        
    Returns:
        (需要的库路径列表, 详细信息)
    """
    resolver = SmartLibraryPathResolver()
    return resolver.resolve_library_paths(project_path, platform, user_search_paths)
