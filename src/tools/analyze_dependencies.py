"""
项目依赖分析 MCP 工具

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

提供项目单元依赖分析和智能库路径解析功能
"""

from typing import Any
from mcp.types import CallToolResult

from ..utils.unit_dependency_analyzer import (
    analyze_project_units,
    smart_resolve_library_paths
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


async def analyze_project_dependencies(arguments: Any) -> CallToolResult:
    """
    分析项目单元依赖
    
    Args:
        arguments: 包含以下参数:
            - project_path: 项目文件路径 (.dpr 或 .dproj) (必需)
            
    Returns:
        分析结果，包含项目引用的所有单元列表
    """
    project_path = arguments.get("project_path")
    if not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供项目文件路径"}],
            isError=True
        )
    
    try:
        logger.info(f"分析项目依赖: {project_path}")
        result = analyze_project_units(project_path)
        
        # 格式化输出
        output = f"项目依赖分析结果\n"
        output += f"================\n\n"
        output += f"项目: {result['project']}\n"
        output += f"单元总数: {result['total_units']}\n\n"
        
        if result['units']:
            output += f"引用的单元 ({len(result['units'])} 个):\n"
            for i, unit in enumerate(result['units'], 1):
                output += f"  {i}. {unit}\n"
            output += "\n"
        
        if result['missing_units']:
            output += f"⚠️ 未找到的单元 ({len(result['missing_units'])} 个):\n"
            for unit in result['missing_units'][:20]:  # 最多显示20个
                output += f"  - {unit}\n"
            if len(result['missing_units']) > 20:
                output += f"  ... 还有 {len(result['missing_units']) - 20} 个\n"
            output += "\n"
        
        if result['resolved_units']:
            output += f"✓ 已解析的单元 ({len(result['resolved_units'])} 个):\n"
            for unit, path in list(result['resolved_units'].items())[:10]:
                output += f"  - {unit}: {path}\n"
            if len(result['resolved_units']) > 10:
                output += f"  ... 还有 {len(result['resolved_units']) - 10} 个\n"
        
        return CallToolResult(content=[{"type": "text", "text": output}])
        
    except Exception as e:
        logger.error(f"分析项目依赖失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"分析项目依赖失败: {str(e)}"}],
            isError=True
        )


async def resolve_smart_library_paths(arguments: Any) -> CallToolResult:
    """
    智能解析项目需要的库路径
    
    分析项目实际使用的单元，从全局第三方库路径中智能筛选出需要的路径，
    避免命令行过长问题。
    
    Args:
        arguments: 包含以下参数:
            - project_path: 项目文件路径 (.dpr 或 .dproj) (必需)
            - platform: 目标平台 (可选, 默认 Win32)
            
    Returns:
        智能解析后的库路径列表
    """
    project_path = arguments.get("project_path")
    if not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供项目文件路径"}],
            isError=True
        )
    
    platform = arguments.get("platform", "Win32")
    
    try:
        logger.info(f"智能解析库路径: {project_path}, 平台: {platform}")
        paths, info = smart_resolve_library_paths(project_path, platform)
        
        # 格式化输出
        output = f"智能库路径解析结果\n"
        output += f"==================\n\n"
        output += f"项目: {project_path}\n"
        output += f"平台: {platform}\n\n"
        
        output += f"📊 统计信息:\n"
        output += f"  - 项目引用单元数: {info['total_units']}\n"
        output += f"  - 全局第三方库路径数: {info['total_paths_count']}\n"
        output += f"  - 智能筛选后路径数: {info['needed_paths_count']}\n"
        output += f"  - 解决的单元依赖: {info['resolved_units']}\n"
        output += f"  - 仍未找到的单元: {info['still_missing']}\n\n"
        
        if paths:
            output += f"✓ 推荐使用的库路径 ({len(paths)} 个):\n"
            for i, path in enumerate(paths, 1):
                output += f"  {i}. {path}\n"
            output += "\n"
            output += f"💡 提示: 这些路径可以直接用于 compile_project 的 unit_search_paths 参数\n"
        else:
            output += "⚠️ 未找到需要的第三方库路径\n"
        
        if info.get('still_missing_units'):
            output += f"\n⚠️ 以下单元仍未找到，可能需要手动添加路径:\n"
            for unit in info['still_missing_units'][:10]:
                output += f"  - {unit}\n"
            if len(info['still_missing_units']) > 10:
                output += f"  ... 还有 {len(info['still_missing_units']) - 10} 个\n"
        
        return CallToolResult(content=[{"type": "text", "text": output}])
        
    except Exception as e:
        logger.error(f"智能解析库路径失败: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"智能解析库路径失败: {str(e)}"}],
            isError=True
        )
