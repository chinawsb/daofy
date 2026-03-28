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
    
    通过知识库查找未解析的第三方库单元路径。
    
    Args:
        arguments: 包含以下参数:
            - project_path: 项目文件路径 (.dpr 或 .dproj) (必需)
            - resolve_via_kb: 是否通过知识库查找未解析单元 (默认 True)
            
    Returns:
        分析结果，包含项目引用的所有单元列表
    """
    project_path = arguments.get("project_path")
    resolve_via_kb = arguments.get("resolve_via_kb", True)
    
    if not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "请提供项目文件路径"}],
            isError=True
        )
    
    try:
        logger.info(f"分析项目依赖: {project_path}")
        result = analyze_project_units(project_path)
        
        # 通过知识库和Delphi源码路径查找未解析的单元
        resolved_via_kb = {}
        if resolve_via_kb and result.get('missing_units'):
            logger.info(f"通过知识库查找 {len(result['missing_units'])} 个未解析单元...")
            
            # 尝试加载并搜索知识库
            try:
                from ..services.knowledge_base.thirdparty_knowledge_base import ThirdPartyKnowledgeBase
                from ..services.knowledge_base.service import DelphiKnowledgeBaseService
                
                # 初始化第三方库知识库
                thirdparty_kb = ThirdPartyKnowledgeBase()
                thirdparty_kb.load_knowledge_base()
                
                # 初始化Delphi知识库
                delphi_kb = DelphiKnowledgeBaseService()
                delphi_kb.load_knowledge_base()
                
                kb_thirdparty = thirdparty_kb.kb_instance
                kb_delphi = delphi_kb.kb_instance
                
                logger.info(f"知识库已加载 - 第三方库: {kb_thirdparty is not None}, Delphi: {kb_delphi is not None}")
                
                # 方法1: 通过Delphi源码目录查找VCL/RTL单元（优先，更可靠）
                delphi_source_paths = [
                    r"C:\Program Files (x86)\Embarcadero\Studio\23.0\source\rtl\common",
                    r"C:\Program Files (x86)\Embarcadero\Studio\23.0\source\rtl\win",
                    r"C:\Program Files (x86)\Embarcadero\Studio\23.0\source\vcl",
                    r"C:\Program Files (x86)\Embarcadero\Studio\23.0\source\fmx",
                ]
                
                import os
                missing_units_set = set(result['missing_units'])
                
                for base_path in delphi_source_paths:
                    if not os.path.exists(base_path):
                        continue
                    for root, dirs, files in os.walk(base_path):
                        for f in files:
                            if not f.endswith('.pas'):
                                continue
                            
                            # 提取单元名（去掉路径空间前缀）
                            # Vcl.Controls.pas -> Controls
                            # System.Classes.pas -> Classes  
                            # FMX.Controls.pas -> Controls
                            parts = f[:-4].split('.')  # 去掉 .pas
                            unit_name = parts[-1].lower() if parts else ''
                            
                            if unit_name and unit_name in missing_units_set:
                                full_path = os.path.join(root, f)
                                resolved_via_kb[unit_name] = {"source": "delphi", "path": full_path}
                
                logger.info(f"通过Delphi源码目录解析了 {len(resolved_via_kb)} 个单元")
                
                logger.info(f"通过Delphi源码目录解析了 {len(resolved_via_kb)} 个单元")
                
                # 输出调试：检查 controls 是否在 missing_units 中
                if 'controls' in [u.lower() for u in result.get('missing_units', [])]:
                    logger.info("controls 在缺失列表中")
                
                # 方法2: 通过知识库搜索类定义获取文件路径（补充）
                for unit in result['missing_units']:
                    # 搜索第三方库
                    if kb_thirdparty and unit not in resolved_via_kb:
                        kb_results = kb_thirdparty.search_by_class_name(unit)[:3]
                        if kb_results:
                            for r in kb_results:
                                path = r.get('file', {}).get('full_path', '') or r.get('full_path', '')
                                if path and path.lower().endswith('.pas'):
                                    resolved_via_kb[unit] = {"source": "thirdparty", "path": path}
                                    break
                    
                    # 搜索Delphi官方库
                    if kb_delphi and unit not in resolved_via_kb:
                        kb_results = kb_delphi.search_by_class_name(unit)[:3]
                        if kb_results:
                            for r in kb_results:
                                path = r.get('file', {}).get('full_path', '') or r.get('full_path', '')
                                if path and path.lower().endswith('.pas'):
                                    resolved_via_kb[unit] = {"source": "delphi", "path": path}
                                    break
                
                logger.info(f"通过知识库和Delphi源码解析了 {len(resolved_via_kb)} 个单元")
                
            except Exception as kb_err:
                import traceback
                logger.warning(f"知识库查询失败: {kb_err}\n{traceback.format_exc()}")
        
        # 合并已解析的单元
        all_resolved = dict(result.get('resolved_units', {}))
        for unit, info in resolved_via_kb.items():
            all_resolved[unit] = info['path']
        
        # 更新结果
        result['resolved_via_kb'] = resolved_via_kb
        result['all_resolved'] = all_resolved
        
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
            missing_count = len(result['missing_units']) - len(resolved_via_kb)
            output += f"⚠️ 未找到的单元 ({missing_count} 个):\n"
            for unit in result['missing_units'][:20]:
                if unit not in resolved_via_kb:
                    output += f"  - {unit}\n"
            if missing_count > 20:
                output += f"  ... 还有 {missing_count - 20} 个\n"
            output += "\n"
        
        # 显示通过知识库找到的单元
        if resolved_via_kb:
            output += f"✓ 通过知识库解析 ({len(resolved_via_kb)} 个):\n"
            for unit, info in list(resolved_via_kb.items())[:15]:
                output += f"  - {unit}: {info['path']}\n"
            if len(resolved_via_kb) > 15:
                output += f"  ... 还有 {len(resolved_via_kb) - 15} 个\n"
            output += "\n"
        
        if result.get('resolved_units'):
            output += f"✓ 本地已解析 ({len(result['resolved_units'])} 个):\n"
            for unit, path in list(result['resolved_units'].items())[:10]:
                output += f"  - {unit}: {path}\n"
            if len(result['resolved_units']) > 10:
                output += f"  ... 还有 {len(result['resolved_units']) - 10} 个\n"
        
        # 汇总
        total_resolved = len(all_resolved)
        output += f"\n📊 解析汇总: {total_resolved}/{result['total_units']} ({total_resolved*100//result['total_units']}%)"
        
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
