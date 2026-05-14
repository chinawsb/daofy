"""
Delphi 知识库 MCP 工具

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

提供知识库查询和管理的 MCP 工具
"""

import logging
from pathlib import Path
from typing import Any, Optional
from mcp.types import CallToolResult

logger = logging.getLogger(__name__)

# 统一的知识库服务实例
_delphi_kb_service = None
_thirdparty_kb_service = None

# 项目知识库缓存 {project_path: ProjectKnowledgeBase instance}
_pkb_cache = {}


def _format_build_info(s: dict) -> str:
    """格式化末次构建信息"""
    parts = []
    bt = s.get('last_build_time')
    if bt:
        # ISO 时间取到分钟
        parts.append(bt[:16].replace('T', ' '))
    dur = s.get('last_build_duration')
    if dur is not None:
        if dur < 60:
            parts.append(f'{dur}秒')
        else:
            parts.append(f'{dur//60}分{dur%60}秒')
    return f' (末次构建: {", ".join(parts)})' if parts else ''


def _append_stats_guide(guide: str, kb_type: str) -> str:
    """向 guide 字符串追加知识库统计信息，返回修改后的字符串"""
    if kb_type in ("all", "delphi") and _delphi_kb_service:
        try:
            s = _delphi_kb_service.get_statistics()
            bi = _format_build_info(s)
            guide += (
                f"  Delphi KB:  {s.get('files', 0)} 文件, "
                f"{s.get('classes', 0)} 类, "
                f"{s.get('functions', 0)} 函数{bi}\n"
            )
        except Exception:
            pass
    if kb_type in ("all", "project"):
        try:
            pp = _resolve_project_path(None)
            if pp:
                pkb = _get_or_create_pkb(pp)
                pkb.load_knowledge_bases()
                s = pkb.get_statistics()
                pj = s.get("project") or {}
                bi = _format_build_info(pj)
                guide += (
                    f"  Project KB: {pj.get('files', 0)} 文件, "
                    f"{pj.get('classes', 0)} 类, "
                    f"{pj.get('functions', 0)} 函数{bi}\n"
                )
        except Exception:
            pass
    if kb_type in ("all", "thirdparty") and _thirdparty_kb_service:
        try:
            s = _thirdparty_kb_service.get_statistics()
            bi = _format_build_info(s)
            guide += (
                f"  Thirdparty: {s.get('files', 0)} 文件, "
                f"{s.get('classes', 0)} 类, "
                f"{s.get('functions', 0)} 函数{bi}\n"
            )
        except Exception:
            pass
    return guide


def _resolve_project_path(project_path: Optional[str] = None) -> Optional[str]:
    """
    解析项目路径：如果未提供则自动检测当前目录下的 .dproj 文件。

    检测顺序：
    1. 如果传入了 project_path（非空），直接使用（不检查存在性，让下游报错）
    2. 扫描 CWD 查找 *.dproj
    3. 扫描 CWD 的父目录查找 *.dproj
    4. 如果找到恰好一个，返回该路径
    5. 如果找到 0 个或多个，返回 None（由调用方处理错误信息）

    Args:
        project_path: 用户传入的项目路径（可选）

    Returns:
        解析后的项目路径，或 None
    """
    # 用户显式传入了路径 → 直接使用，无论是否存在
    if project_path:
        return str(Path(project_path))

    # 自动检测：从 CWD 开始，向上查找 .dproj
    cwd = Path.cwd()
    for search_dir in [cwd] + list(cwd.parents)[:5]:
        dproj_files = list(search_dir.glob("*.dproj"))
        if len(dproj_files) == 1:
            return str(dproj_files[0].resolve())
        elif len(dproj_files) > 1:
            # 找到多个 .dproj，试试看有没有和目录名同名的
            project_name = search_dir.name
            for f in dproj_files:
                if f.stem == project_name or f.stem.lower() == project_name.lower():
                    return str(f.resolve())
            # 仍然不明确，继续向上搜索

    return None


def set_delphi_kb_service(service):
    """设置 Delphi 知识库服务实例"""
    global _delphi_kb_service
    _delphi_kb_service = service


def set_thirdparty_kb_service(service):
    """设置第三方库知识库服务实例"""
    global _thirdparty_kb_service
    _thirdparty_kb_service = service


def _get_or_create_pkb(project_path: str):
    """获取或创建项目知识库实例（带缓存）"""
    global _pkb_cache
    if project_path not in _pkb_cache:
        from ..services.knowledge_base.project_knowledge_base import ProjectKnowledgeBase
        _pkb_cache[project_path] = ProjectKnowledgeBase(project_path)
    return _pkb_cache[project_path]


async def search_knowledge(arguments: Any) -> CallToolResult:
    """统一搜索知识库"""
    kb_type = arguments.get("kb_type", "all")
    search_type = arguments.get("search_type", "all")
    query = arguments.get("query", "")
    top_k = min(arguments.get("top_k", 200), 500)
    
    if not query:
        # 空 query: 返回知识库状态 + 使用指引，而非简单报错
        kb_type = arguments.get("kb_type", "all")
        guide = (
            "Delphi 知识库搜索\n"
            "═══════════════════════════════════════\n"
            "使用示例:\n"
            '  delphi_kb(query="TStringList")            — 搜索类\n'
            '  delphi_kb(query="Create", search_type="function") — 搜索函数\n'
            '  delphi_kb(query="TForm", kb_type="delphi")  — 指定知识库\n'
            '  delphi_kb(query="TfrmMain", kb_type="project") — 搜索项目代码\n'
            '  delphi_kb(search_type="reference", query="TfrmMain") — 查找引用\n'
            '\n'
            f"知识库范围: {kb_type}\n"
            f"search_type: {search_type}\n"
            f"先调用 delphi_kb(action=stats, kb_type={kb_type}) 查看各 KB 文件数\n"
        )
        # 尝试获取统计信息补充到提示中
        try:
            guide = _append_stats_guide(guide, kb_type)
        except Exception:
            pass
        return CallToolResult(content=[{"type": "text", "text": guide}])
    
    results = {}
    kb_types = [kb_type] if kb_type != "all" else ["delphi", "project", "thirdparty"]
    
    
    # vocabularies.type 使用 Delphi 双字母编码（与 Delphi KB 一致）
    _SEARCH_TYPE_TO_KIND = {
        'class': ['TC'], 'record': ['TR'], 'interface': ['TI'], 'enum': ['TE'],
        'set': ['TS'], 'type': ['TY', 'AT', 'PT'], 'function': ['FF', 'FP'], 'procedure': ['FP'],
        'const': ['CC'], 'resourcestring': ['CR'], 'property': ['MP'], 'field': ['MF'],
        'method': ['MM'], 'unit': ['UI'], 'event': ['ME'], 'string': ['KS'],
    }

    def _filter_by_search_type(symbols, st):
        if st in _SEARCH_TYPE_TO_KIND:
            allowed_kinds = _SEARCH_TYPE_TO_KIND[st]
            return [s for s in symbols if s.get('kind_code', '') in allowed_kinds]
        return symbols

    for kb in kb_types:
        try:
            # 引用查询：使用 search_usages 搜索哪些文件引用了该符号
            if search_type == "reference":
                if kb == "delphi" and _delphi_kb_service:
                    refs = _delphi_kb_service.search_by_name(query)
                    if refs:
                        results[f"{kb}_symbols"] = refs
                elif kb == "project":
                    project_path = _resolve_project_path(arguments.get("project_path"))
                    if project_path:
                        try:
                            # 从 .dproj 读取命名空间前缀，用于解析省略前缀的单元引用
                            # 未配置时使用 Delphi 2010+ 默认前缀
                            from ..utils.dproj_parser import DprojParser
                            try:
                                parser = DprojParser(project_path)
                                ns_prefixes = parser.get_namespace()
                            except Exception:
                                ns_prefixes = None

                            if not ns_prefixes:
                                # Delphi 2010+ 默认命名空间前缀
                                ns_prefixes = [
                                    'Winapi', 'System.Win', 'Data.Win', 'Datasnap.Win',
                                    'Web.Win', 'Soap.Win', 'Xml.Win', 'System', 'Xml',
                                    'Data', 'Datasnap', 'Web', 'Soap', 'Vcl',
                                    'Vcl.Imaging', 'Vcl.Touch', 'Vcl.Samples', 'Vcl.Shell',
                                ]

                            pkb = _get_or_create_pkb(project_path)
                            pkb.load_knowledge_bases()
                            # 搜索前检查源码是否有变更（不阻塞重建，仅报告状态）
                            if not pkb.check_and_update_project_kb():
                                results["project_warning"] = (
                                    "项目源码已变更，知识库数据可能不是最新。\n"
                                    "请执行 delphi_kb(action='build', kb_type='project', "
                                    f"project_path='{project_path}') 重建。"
                                )
                            if pkb.project_kb is None:
                                results["project_error"] = (
                                    f"项目知识库未构建。请先执行：\n"
                                    f"  delphi_kb(action='build', kb_type='project', project_path='{project_path}')\n"
                                    f"构建完成后再搜索。"
                                )
                            else:
                                refs = pkb.project_kb.search_usages(query, namespace_prefixes=ns_prefixes)
                                if refs:
                                    results["project_references"] = refs
                        except Exception as e:
                            results["project_error"] = str(e)
                    else:
                        results["project_error"] = "未检测到项目路径"
                elif kb == "thirdparty" and _thirdparty_kb_service:
                    if _thirdparty_kb_service.kb_instance is None:
                        _thirdparty_kb_service.load_knowledge_base()
                    if _thirdparty_kb_service.kb_instance:
                        refs = _thirdparty_kb_service.kb_instance.search_usages(query)
                        if refs:
                            results["thirdparty_references"] = refs
                continue  # 引用查询已处理，跳过下面的符号搜索

            if kb == "delphi" and _delphi_kb_service:
                # 名称搜索（精确/通配匹配）
                symbol_results = _delphi_kb_service.search_by_name(query)
                filtered_by_type = _filter_by_search_type(symbol_results, search_type)
                total_before_cut = len(filtered_by_type)
                filtered = filtered_by_type[:top_k]
                if filtered:
                    results[f"{kb}_symbols"] = filtered
                    results[f"{kb}_symbols_total"] = total_before_cut
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
                project_path = _resolve_project_path(arguments.get("project_path"))
                if not project_path:
                    results["project_error"] = "请提供 project_path 参数（当前目录未自动检测到 .dproj 文件）"
                else:
                    try:
                        pkb = _get_or_create_pkb(project_path)
                        pkb.load_knowledge_bases()
                        # 搜索前检查源码是否有变更，有则自动启动异步重建（防重入）
                        if not pkb.check_and_update_project_kb():
                            try:
                                from ..services.knowledge_base.async_task_manager import get_task_manager
                                from ..services.knowledge_base.project_knowledge_base import (
                                    ProjectKnowledgeBase as _PKB,
                                )

                                _tm = get_task_manager()
                                _rebuild_path = project_path
                                _dedup_key = f"project_rebuild:{_rebuild_path}"

                                def _rebuild_project_task(**kwargs):
                                    _pp = kwargs.get("project_path")
                                    _pc = kwargs.get("_progress_callback")
                                    _p = _PKB(_pp, progress_callback=_pc)
                                    # force_rebuild=False：增量构建，只扫描 hash 变化的文件
                                    _p.build_project_knowledge_base(force_rebuild=False)
                                    _p.close()
                                    return True

                                _task_id = _tm.submit_task(
                                    f"重建项目知识库 ({Path(_rebuild_path).stem})",
                                    _rebuild_project_task,
                                    dedup_key=_dedup_key,
                                    project_path=_rebuild_path,
                                )
                                results["project_async_task_id"] = _task_id
                                logger.info(f"检测到项目源码变更，启动异步重建 task_id={_task_id}")
                            except Exception as e:
                                logger.warning(f"启动异步重建失败: {e}")
                                results["project_warning"] = (
                                    "项目源码已变更，知识库数据可能不是最新。\n"
                                    "请执行 delphi_kb(action='build', kb_type='project', "
                                    f"project_path='{project_path}') 手动重建。"
                                )
                        # 如果知识库未构建，返回提示而非自动构建
                        if pkb.project_kb is None:
                            results["project_error"] = (
                                f"项目知识库未构建。请先执行：\n"
                                f"  delphi_kb(action='build', kb_type='project', project_path='{project_path}')\n"
                                f"构建完成后再搜索。"
                            )
                            continue
                        
                        # 名称搜索（search_by_name 返回与 Delphi KB 相同格式）
                        project_results = pkb.project_kb.search_by_name(query)
                        filtered_by_type = _filter_by_search_type(project_results, search_type)
                        total_before_cut = len(filtered_by_type)
                        filtered = filtered_by_type[:top_k]
                        if filtered:
                            results["project_symbols"] = filtered
                            results["project_symbols_total"] = total_before_cut
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
                    except Exception as e:
                        results["project_error"] = str(e)

            elif kb == "thirdparty" and _thirdparty_kb_service:
                # 确保知识库已加载
                if _thirdparty_kb_service.kb_instance is None:
                    _thirdparty_kb_service.load_knowledge_base()
                if _thirdparty_kb_service.kb_instance:
                    # 名称搜索：直接从底层 kb_instance 获取完整匹配结果
                    symbol_results = _thirdparty_kb_service.kb_instance.search_by_name(query)
                    filtered_by_type = _filter_by_search_type(symbol_results, search_type)
                    total_before_cut = len(filtered_by_type)
                    filtered = filtered_by_type[:top_k]
                    if filtered:
                        results["thirdparty_symbols"] = filtered
                        results["thirdparty_symbols_total"] = total_before_cut
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

    def _trunc_hint(items, total_key=None):
        """如果结果被 top_k 截断，返回提示信息"""
        total = len(items)
        if total_key and total_key in results:
            total = results[total_key]
        if total > top_k:
            return f"  (提示: 共 {total} 条结果，top_k={top_k}，{total - top_k} 条未显示，可增大 top_k 获取全部)\n"
        return ''

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
        output += _trunc_hint(results['delphi_symbols'], 'delphi_symbols_total')
        output += "\n"
        has_results = True
    
    # 显示所有类型搜索结果
    if "delphi_all" in results and results["delphi_all"]:
        output += f"Delphi 所有符号 ({len(results['delphi_all'])}):\n"
        for r in results["delphi_all"][:top_k]:
            kind_code = r.get('kind_code', '')
            type_desc = _KIND_DESC.get(kind_code, r.get('kind', kind_code))
            output += f"  - {r.get('name', 'N/A')} ({type_desc})\n"
        output += _trunc_hint(results['delphi_all'])
        output += "\n"
        has_results = True
    
    if "delphi_classes" in results and results["delphi_classes"]:
        output += f"Delphi 类 ({len(results['delphi_classes'])}):\n"
        for r in results["delphi_classes"][:top_k]:
            output += f"  - {r.get('name', 'N/A')}\n"
        output += _trunc_hint(results['delphi_classes'])
        output += "\n"
        has_results = True
    
    if "delphi_functions" in results and results["delphi_functions"]:
        output += f"Delphi 函数/过程 ({len(results['delphi_functions'])}):\n"
        for r in results["delphi_functions"][:top_k]:
            output += f"  - {r.get('name', 'N/A')}\n"
        output += _trunc_hint(results['delphi_functions'])
        output += "\n"
        has_results = True
    
    if "delphi_semantic_classes" in results and results["delphi_semantic_classes"]:
        output += f"Delphi 类(语义搜索) ({len(results['delphi_semantic_classes'])}):\n"
        for name, sim in results["delphi_semantic_classes"][:top_k]:
            output += f"  - {name} (相似度: {sim:.2f})\n"
        output += _trunc_hint(results['delphi_semantic_classes'])
        output += "\n"
        has_results = True
    
    if "delphi_semantic_functions" in results and results["delphi_semantic_functions"]:
        output += f"Delphi 函数/过程(语义搜索) ({len(results['delphi_semantic_functions'])}):\n"
        for name, sim in results["delphi_semantic_functions"][:top_k]:
            output += f"  - {name} (相似度: {sim:.2f})\n"
        output += _trunc_hint(results['delphi_semantic_functions'])
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
            output += _trunc_hint(results[f'{kb}_symbols'], f'{kb}_symbols_total')
            output += "\n"
            has_results = True
        if f"{kb}_semantic_classes" in results and results[f"{kb}_semantic_classes"]:
            output += f"{label} 类(语义搜索) ({len(results[f'{kb}_semantic_classes'])}):\n"
            for name, sim in results[f"{kb}_semantic_classes"][:top_k]:
                output += f"  - {name} (相似度: {sim:.2f})\n"
            output += _trunc_hint(results[f'{kb}_semantic_classes'])
            output += "\n"
            has_results = True
        if f"{kb}_semantic_functions" in results and results[f"{kb}_semantic_functions"]:
            output += f"{label} 函数/过程(语义搜索) ({len(results[f'{kb}_semantic_functions'])}):\n"
            for name, sim in results[f"{kb}_semantic_functions"][:top_k]:
                output += f"  - {name} (相似度: {sim:.2f})\n"
            output += _trunc_hint(results[f'{kb}_semantic_functions'])
            output += "\n"
            has_results = True

    # 引用查询结果
    for ref_key, label in [("project_references", "项目引用"), ("thirdparty_references", "三方库引用")]:
        if ref_key in results and results[ref_key]:
            refs = results[ref_key]
            output += f"{label} ({len(refs)} 个文件引用):\n"
            for r in refs[:top_k]:
                fi = r.get("file", {})
                imported = r.get("imported_by", [])
                output += f"  - {fi.get('full_path', '?')}\n"
                if imported:
                    output += f"    引用单元: {', '.join(imported[:5])}\n"
            output += _trunc_hint(refs)
            output += "\n"
            has_results = True

    # 显示异步重建任务信息
    if "project_async_task_id" in results:
        output += (
            f"【后台重建】检测到项目源码变更，已自动启动异步重建。\n"
            f"  可通过 async_task(action='status', task_id='{results['project_async_task_id']}') 查询进度。\n"
            f"  重建完成后重新搜索可获取最新数据。\n\n"
        )
        has_results = True

    # 显示提示信息（如果有）
    for warn_key in ["project_warning"]:
        if warn_key in results and results[warn_key]:
            output += f"【提示】{results[warn_key]}\n\n"
            has_results = True

    # 显示错误信息（如果有）
    for err_key in ["project_error", "thirdparty_error", "delphi_error"]:
        if err_key in results and results[err_key]:
            label = {"project_error": "项目", "thirdparty_error": "三方库", "delphi_error": "Delphi"}.get(err_key, err_key)
            output += f"【{label}】错误: {results[err_key]}\n\n"
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
    project_path = _resolve_project_path(arguments.get("project_path"))
    version = arguments.get("version")
    async_mode = arguments.get("async_mode", True)
    force_rebuild = arguments.get("force_rebuild", False)
    
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
                # build 前关闭已有连接（SQLiteVectorKnowledgeBase 以 WAL 模式打开，会阻止其他连接）
                _delphi_kb_service.close()
                success = _delphi_kb_service.build_knowledge_base(version=version, force_rebuild=force_rebuild)
                results["delphi"] = "成功" if success else "失败"
            elif kb == "project" and project_path:
                pkb = _get_or_create_pkb(project_path)
                success = pkb.build_project_knowledge_base(force_rebuild=force_rebuild)
                pkb.close()
                results["project"] = "成功" if success else "失败"
            elif kb == "thirdparty" and _thirdparty_kb_service:
                _thirdparty_kb_service.close()
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
            elif kb == "project":
                project_path = _resolve_project_path(arguments.get("project_path"))
                if not project_path:
                    results["project"] = {"error": "请提供 project_path 参数（当前目录未自动检测到 .dproj 文件）"}
                else:
                    try:
                        pkb = _get_or_create_pkb(project_path)
                        ok = pkb.load_knowledge_bases()
                        if not ok or not pkb.project_kb:
                            results["project"] = {"error": "项目知识库加载失败，请先构建或检查 .delphi-kb/knowledge.sqlite 是否存在"}
                        else:
                            full_stats = pkb.get_statistics()
                            results["project"] = full_stats.get("project") or {"error": "项目统计信息为空"}
                    except Exception as e:
                        results["project"] = {"error": str(e)}
            elif kb == "thirdparty" and _thirdparty_kb_service:
                stats = _thirdparty_kb_service.get_statistics()
                results["thirdparty"] = stats
        except Exception as e:
            results[kb] = {"error": str(e)}
    
    # 格式化输出
    # 若 kb_type=all 或包含 document，补充文档知识库统计
    if kb_type in ("all", "document"):
        try:
            from src.services.knowledge_base.schema import use_connection
            server_root = Path(__file__).parent.parent.parent
            db_path = server_root / "data" / "document-knowledge-base" / "documents.sqlite"
            if db_path.exists():
                with use_connection(str(db_path), use_wal=False) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM documents")
                    total = cursor.fetchone()[0]
                    cursor.execute("SELECT extension, COUNT(*) FROM documents GROUP BY extension ORDER BY COUNT(*) DESC")
                    by_ext = dict(cursor.fetchall())
                    cursor.execute("SELECT content_type, COUNT(*) FROM documents GROUP BY content_type ORDER BY COUNT(*) DESC")
                    by_type = dict(cursor.fetchall())
                # 实际数据库文件大小
                db_stat = db_path.stat()
                db_size_mb = round(db_stat.st_size / (1024 * 1024), 2)
                from datetime import datetime
                last_build = datetime.fromtimestamp(db_stat.st_mtime).isoformat()
                results["document"] = {
                    "total_documents": total,
                    "by_type": by_type,
                    "by_extension": by_ext,
                    "database_size_mb": db_size_mb,
                    "last_build_time": last_build,
                }
            else:
                results["document"] = {"error": f"文档知识库不存在: {db_path}"}
        except Exception as e:
            results["document"] = {"error": str(e)}
    
    output = f"知识库统计 ({kb_type}):\n\n"
    
    for kb, stats in results.items():
        output += f"【{kb.upper()}】\n"
        if isinstance(stats, dict) and "error" in stats:
            output += f"  错误: {stats['error']}\n"
        else:
            if isinstance(stats, dict) and 'by_type' in stats and 'total_documents' in stats:
                # Document KB stats has different key structure (by_type + total_documents)
                output += f"  总文档数: {stats.get('total_documents', 0)}\n"
                db_size = stats.get('database_size_mb')
                if db_size is not None:
                    output += f"  数据库: {db_size:.2f} MB\n"
                bt = stats.get('last_build_time')
                if bt:
                    output += f"  末次构建: {bt[:16].replace('T', ' ')}\n"
                by_type = stats.get('by_type', {})
                if by_type:
                    output += f"  按类型统计:\n"
                    for ct, cnt in by_type.items():
                        output += f"    {ct}: {cnt}\n"
                by_ext = stats.get('by_extension', {})
                if by_ext:
                    output += f"  按扩展名统计:\n"
                    for ext, cnt in sorted(by_ext.items(), key=lambda x: x[1], reverse=True):
                        output += f"    {ext}: {cnt}\n"
                continue
            output += f"  文件: {stats.get('total_documents', stats.get('files', 0))}\n"
            output += f"  类: {stats.get('total_classes', stats.get('classes', 0))}\n"
            output += f"  函数: {stats.get('total_functions', stats.get('functions', 0))}\n"
            output += f"  数据库: {stats.get('database_size_mb', 0):.2f} MB\n"
            bt = stats.get('last_build_time')
            dur = stats.get('last_build_duration')
            if bt:
                output += f"  末次构建: {bt[:16].replace('T', ' ')}"
                if dur is not None:
                    output += f" (用时 {dur//60}分{dur%60}秒)" if dur >= 60 else f" (用时 {dur}秒)"
                output += "\n"
            # 文件类型/扩展名分布
            by_ext = stats.get('by_extension', {})
            if by_ext:
                output += f"  文件类型分布:\n"
                for ext, cnt in sorted(by_ext.items(), key=lambda x: x[1], reverse=True):
                    output += f"    {ext}: {cnt}\n"
        output += "\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])
