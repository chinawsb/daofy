"""
Delphi 知识库 MCP 工具

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

提供知识库查询和管理的 MCP 工具
"""

from typing import Any
from mcp.types import CallToolResult

# 统一的知识库服务实例
_delphi_kb_service = None
_project_kb_service = None
_thirdparty_kb_service = None


def set_delphi_kb_service(service):
    """设置 Delphi 知识库服务实例"""
    global _delphi_kb_service
    _delphi_kb_service = service


def set_project_kb_service(service):
    """设置项目知识库服务实例"""
    global _project_kb_service
    _project_kb_service = service


def set_thirdparty_kb_service(service):
    """设置第三方库知识库服务实例"""
    global _thirdparty_kb_service
    _thirdparty_kb_service = service


async def search_knowledge(arguments: Any) -> CallToolResult:
    """统一搜索知识库"""
    kb_type = arguments.get("kb_type", "all")
    search_type = arguments.get("search_type", "semantic")
    query = arguments.get("query", "")
    top_k = arguments.get("top_k", 10)
    
    if not query:
        return CallToolResult(content=[{"type": "text", "text": "请提供搜索关键词 query"}], isError=True)
    
    results = {}
    kb_types = [kb_type] if kb_type != "all" else ["delphi", "project", "thirdparty"]
    
    
    _SEARCH_TYPE_TO_KIND = {
        'class': ['TC'], 'record': ['TR'], 'interface': ['TI'], 'enum': ['TE'],
        'set': ['TS'], 'type': ['TY', 'AT', 'PT'], 'function': ['FF'], 'procedure': ['FP'],
        'const': ['CC'], 'resourcestring': ['CR'], 'property': ['MP'], 'field': ['MF'],
        'method': ['MM'], 'unit': ['UI'], 'event': ['ME'],
    }

    def _filter_by_search_type(symbols, st):
        if st in _SEARCH_TYPE_TO_KIND:
            allowed_kinds = _SEARCH_TYPE_TO_KIND[st]
            return [s for s in symbols if s.get('kind_code', '') in allowed_kinds]
        return symbols

    for kb in kb_types:
        try:
            if kb == "delphi" and _delphi_kb_service:
                # 名称搜索（精确/通配匹配）
                symbol_results = _delphi_kb_service.search_by_name(query)
                filtered = _filter_by_search_type(symbol_results, search_type)[:top_k]
                if filtered:
                    results[f"{kb}_symbols"] = filtered
                # 语义搜索（补充语义匹配结果）
                if search_type in ("semantic", "all"):
                    try:
                        semantic_classes = _delphi_kb_service.semantic_search_classes(query, top_k=top_k)
                        if semantic_classes:
                            results[f"{kb}_semantic_classes"] = semantic_classes
                    except Exception:
                        pass
                    try:
                        semantic_functions = _delphi_kb_service.semantic_search_functions(query, top_k=top_k)
                        if semantic_functions:
                            results[f"{kb}_semantic_functions"] = semantic_functions
                    except Exception:
                        pass

            elif kb == "project":
                # 项目知识库搜索：使用 ProjectKnowledgeBase 独立查询
                project_path = arguments.get("project_path")
                if not project_path:
                    results["project_error"] = "请提供 project_path 参数"
                else:
                    from ..services.knowledge_base.project_knowledge_base import ProjectKnowledgeBase
                    try:
                        pkb = ProjectKnowledgeBase(project_path)
                        pkb.load_knowledge_bases()
                        if pkb.project_kb:
                            # 名称搜索（search_by_name 返回与 Delphi KB 相同格式）
                            project_results = pkb.project_kb.search_by_name(query)
                            filtered = _filter_by_search_type(project_results, search_type)[:top_k]
                            if filtered:
                                results["project_symbols"] = filtered
                            # 语义搜索（直接使用 tuple 格式兼容已有输出逻辑）
                            if search_type in ("semantic", "all"):
                                try:
                                    sc = pkb.project_kb.semantic_search_classes(query, top_k=top_k)
                                    if sc:
                                        results["project_semantic_classes"] = sc
                                except Exception:
                                    pass
                                try:
                                    sf = pkb.project_kb.semantic_search_functions(query, top_k=top_k)
                                    if sf:
                                        results["project_semantic_functions"] = sf
                                except Exception:
                                    pass
                        else:
                            results["project_error"] = "项目知识库未构建，请先构建"
                    except Exception as e:
                        results["project_error"] = str(e)

            elif kb == "thirdparty" and _thirdparty_kb_service:
                # 确保知识库已加载
                if _thirdparty_kb_service.kb_instance is None:
                    _thirdparty_kb_service.load_knowledge_base()
                if _thirdparty_kb_service.kb_instance:
                    # 名称搜索：直接从底层 kb_instance 获取完整匹配结果
                    symbol_results = _thirdparty_kb_service.kb_instance.search_by_name(query)
                    filtered = _filter_by_search_type(symbol_results, search_type)[:top_k]
                    if filtered:
                        results["thirdparty_symbols"] = filtered
                    # 语义搜索
                    if search_type in ("semantic", "all"):
                        try:
                            semantic_classes = _thirdparty_kb_service.semantic_search_classes(query, top_k=top_k)
                            if semantic_classes:
                                results["thirdparty_semantic_classes"] = semantic_classes
                        except Exception:
                            pass
                        try:
                            semantic_functions = _thirdparty_kb_service.semantic_search_functions(query, top_k=top_k)
                            if semantic_functions:
                                results["thirdparty_semantic_functions"] = semantic_functions
                        except Exception:
                            pass

        except Exception as e:
            results[f"{kb}_error"] = str(e)
    
    output = f"搜索 '{query}' (类型: {search_type}, 知识库: {kb_type}):\n\n"
    has_results = False
    
    _KIND_DESC = {
        'TC': '类', 'TR': '记录', 'TI': '接口', 'TH': 'Helper', 'TE': '枚举', 'TS': '集合',
        'TY': '类型别名', 'AT': '数组', 'PT': '指针', 'FF': '函数', 'FP': '过程',
        'CC': '常量', 'CR': '资源字符串', 'MP': '属性', 'MF': '字段', 'MM': '方法', 'ME': '事件', 'UI': '单元'
    }

    def _format_symbol(r):
        # 类型描述：兼容 SQLiteVector 格式（kind_code）和 SmartCache 格式（type_name）
        kind_code = r.get('kind_code', '')
        type_desc = _KIND_DESC.get(kind_code) or r.get('kind') or r.get('type_name', kind_code) or ''
        # 文件路径：兼容两种 KB 返回格式
        file_info = r.get('file')
        if isinstance(file_info, dict):
            file_path = file_info.get('full_path') or file_info.get('path', 'N/A')
        else:
            file_path = r.get('full_path') or r.get('relative_path', 'N/A')
        return f"  - {r.get('name', 'N/A')} ({type_desc})\n    文件: {file_path}\n    行号: {r.get('line', 'N/A')}\n"

    # 显示符号搜索结果
    if "delphi_symbols" in results and results["delphi_symbols"]:
        output += f"Delphi 符号 ({len(results['delphi_symbols'])}):\n"
        for r in results["delphi_symbols"][:top_k]:
            output += _format_symbol(r)
            if r.get('definition'):
                output += f"    定义: {r.get('definition')}\n"
        output += "\n"
        has_results = True
    
    # 显示所有类型搜索结果
    if "delphi_all" in results and results["delphi_all"]:
        output += f"Delphi 所有符号 ({len(results['delphi_all'])}):\n"
        for r in results["delphi_all"][:top_k]:
            kind_code = r.get('kind_code', '')
            type_desc = _KIND_DESC.get(kind_code, r.get('kind', kind_code))
            output += f"  - {r.get('name', 'N/A')} ({type_desc})\n"
        output += "\n"
        has_results = True
    
    if "delphi_classes" in results and results["delphi_classes"]:
        output += f"Delphi 类 ({len(results['delphi_classes'])}):\n"
        for r in results["delphi_classes"][:top_k]:
            output += f"  - {r.get('name', 'N/A')}\n"
        output += "\n"
        has_results = True
    
    if "delphi_functions" in results and results["delphi_functions"]:
        output += f"Delphi 函数/过程 ({len(results['delphi_functions'])}):\n"
        for r in results["delphi_functions"][:top_k]:
            output += f"  - {r.get('name', 'N/A')}\n"
        output += "\n"
        has_results = True
    
    if "delphi_semantic_classes" in results and results["delphi_semantic_classes"]:
        output += f"Delphi 类(语义搜索) ({len(results['delphi_semantic_classes'])}):\n"
        for name, sim in results["delphi_semantic_classes"][:top_k]:
            output += f"  - {name} (相似度: {sim:.2f})\n"
        output += "\n"
        has_results = True
    
    if "delphi_semantic_functions" in results and results["delphi_semantic_functions"]:
        output += f"Delphi 函数/过程(语义搜索) ({len(results['delphi_semantic_functions'])}):\n"
        for name, sim in results["delphi_semantic_functions"][:top_k]:
            output += f"  - {name} (相似度: {sim:.2f})\n"
        output += "\n"
        has_results = True
    
    # 项目知识库搜索结果
    for kb, label in [("project", "项目"), ("thirdparty", "三方库")]:
        if f"{kb}_symbols" in results and results[f"{kb}_symbols"]:
            output += f"{label} 符号 ({len(results[f'{kb}_symbols'])}):\n"
            for r in results[f"{kb}_symbols"][:top_k]:
                output += _format_symbol(r)
                if r.get('definition'):
                    output += f"    定义: {r.get('definition')}\n"
            output += "\n"
            has_results = True
        if f"{kb}_semantic_classes" in results and results[f"{kb}_semantic_classes"]:
            output += f"{label} 类(语义搜索) ({len(results[f'{kb}_semantic_classes'])}):\n"
            for name, sim in results[f"{kb}_semantic_classes"][:top_k]:
                output += f"  - {name} (相似度: {sim:.2f})\n"
            output += "\n"
            has_results = True
        if f"{kb}_semantic_functions" in results and results[f"{kb}_semantic_functions"]:
            output += f"{label} 函数/过程(语义搜索) ({len(results[f'{kb}_semantic_functions'])}):\n"
            for name, sim in results[f"{kb}_semantic_functions"][:top_k]:
                output += f"  - {name} (相似度: {sim:.2f})\n"
            output += "\n"
            has_results = True
    
    if not has_results:
        output += "未找到相关内容\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])


async def build_unified_knowledge_base(arguments: Any) -> CallToolResult:
    """
    统一构建知识库
    
    参数:
    - kb_type: "delphi"|"project"|"thirdparty"|"help"|"all" 知识库类型，支持组合(如"delphi,project")
    - project_path: 项目路径 (仅project类型需要)
    - version: Delphi版本 (仅delphi/thirdparty需要)
    - async_mode: 是否异步
    - force_rebuild: 是否强制重建
    """
    kb_type = arguments.get("kb_type", "all")
    project_path = arguments.get("project_path")
    version = arguments.get("version")
    async_mode = arguments.get("async_mode", True)
    force_rebuild = arguments.get("force_rebuild", False)
    
    # 解析知识库类型
    if kb_type == "all":
        kb_types = ["delphi", "project", "thirdparty", "help"]
    elif isinstance(kb_type, str):
        kb_types = [k.strip() for k in kb_type.split(",")]
    else:
        kb_types = [kb_type]
    
    results = {}
    
    for kb in kb_types:
        try:
            if kb == "delphi" and _delphi_kb_service:
                success = _delphi_kb_service.build_knowledge_base(version=version, force_rebuild=force_rebuild)
                results["delphi"] = "成功" if success else "失败"
            elif kb == "project" and _project_kb_service and project_path:
                success = _project_kb_service.build_project_knowledge_base(force_rebuild=force_rebuild)
                results["project"] = "成功" if success else "失败"
            elif kb == "thirdparty" and _thirdparty_kb_service:
                success = _thirdparty_kb_service.build_thirdparty_knowledge_base(version=version, force_rebuild=force_rebuild)
                results["thirdparty"] = "成功" if success else "失败"
        except Exception as e:
            results[kb] = f"错误: {str(e)}"
    
    # 格式化输出
    output = f"构建知识库 ({kb_type}):\n\n"
    for kb, status in results.items():
        output += f"- {kb}: {status}\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])


async def get_unified_knowledge_stats(arguments: Any) -> CallToolResult:
    """
    统一获取知识库统计信息
    
    参数:
    - kb_type: "delphi"|"project"|"thirdparty"|"all"
    - project_path: 项目路径 (仅project需要)
    """
    kb_type = arguments.get("kb_type", "all")
    project_path = arguments.get("project_path")
    
    # 解析知识库类型
    if kb_type == "all":
        kb_types = ["delphi", "project", "thirdparty"]
    elif isinstance(kb_type, str):
        kb_types = [k.strip() for k in kb_type.split(",")]
    else:
        kb_types = [kb_type]
    
    results = {}
    
    for kb in kb_types:
        try:
            if kb == "delphi" and _delphi_kb_service:
                stats = _delphi_kb_service.get_statistics()
                # 映射 keys to expected format
                stats["total_documents"] = stats.get("files", 0)
                stats["total_classes"] = stats.get("classes", 0)
                stats["total_functions"] = stats.get("functions", 0) + stats.get("procedures", 0)
                results["delphi"] = stats
            elif kb == "project" and _project_kb_service:
                stats = _project_kb_service.get_statistics()
                results["project"] = stats
            elif kb == "thirdparty" and _thirdparty_kb_service:
                stats = _thirdparty_kb_service.get_statistics()
                results["thirdparty"] = stats
        except Exception as e:
            results[kb] = {"error": str(e)}
    
    # 格式化输出
    output = f"知识库统计 ({kb_type}):\n\n"
    
    for kb, stats in results.items():
        output += f"【{kb.upper()}】\n"
        if "error" in stats:
            output += f"  错误: {stats['error']}\n"
        else:
            output += f"  文件: {stats.get('total_documents', stats.get('files', 0))}\n"
            output += f"  类: {stats.get('total_classes', stats.get('classes', 0))}\n"
            output += f"  函数: {stats.get('total_functions', stats.get('functions', 0))}\n"
            output += f"  数据库: {stats.get('database_size_mb', 0)} MB\n"
        output += "\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])
