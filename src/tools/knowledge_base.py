"""
Delphi 知识库 MCP 工具

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

提供知识库查询和管理的 MCP 工具
"""

import logging
from pathlib import Path
from typing import Any, List, Optional
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
    """尝试在指引中追加统计信息"""
    if kb_type in ("all", "delphi") and _delphi_kb_service:
        try:
            s = _delphi_kb_service.get_statistics()
            bi = _format_build_info(s)
            guide += (
                f"  Delphi KB:  {s.get('files', 0)} 文件, "
                f"{s.get('classes', 0)} 类, "
                f"{s.get('functions', 0)} 函数{bi}\n"
            )
        except Exception as e:
            logger.debug("获取 Delphi KB 统计失败: %s", e)
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
        except Exception as e:
            logger.debug("获取 Project KB 统计失败: %s", e)
    if kb_type in ("all", "thirdparty") and _thirdparty_kb_service:
        try:
            s = _thirdparty_kb_service.get_statistics()
            bi = _format_build_info(s)
            guide += (
                f"  Thirdparty: {s.get('files', 0)} 文件, "
                f"{s.get('classes', 0)} 类, "
                f"{s.get('functions', 0)} 函数{bi}\n"
            )
        except Exception as e:
            logger.debug("获取 Thirdparty KB 统计失败: %s", e)
    return guide


def _resolve_project_path(project_path: Optional[str] = None) -> Optional[str]:
    """
    解析项目路径：如果未提供则自动检测当前目录下的项目文件。

    支持的项目文件类型（按优先级）：
    - .dproj (MSBuild 项目文件，信息最丰富)
    - .dpr   (传统 Delphi 项目文件)
    - .dpk   (包文件)

    检测顺序：
    1. 如果传入了 project_path（非空），直接使用（不检查存在性，让下游报错）
    2. 扫描 CWD 查找 *.dproj / *.dpr / *.dpk（优先选择 .dproj）
    3. 扫描 CWD 的父目录查找同类文件
    4. 如果找到恰好一个，返回该路径
    5. 如果找到多个，按优先级选（.dproj > .dpr > .dpk），同名匹配优先
    6. 如果找到 0 个或多个，返回 None（由调用方处理错误信息）

    Args:
        project_path: 用户传入的项目路径（可选）

    Returns:
        解析后的项目路径，或 None
    """
    # 用户显式传入了路径 → 直接使用，无论是否存在
    if project_path:
        return str(Path(project_path))

    # 按优先级排序的搜索模式
    project_patterns = ["*.dproj", "*.dpr", "*.dpk"]

    # 自动检测：从 CWD 开始，向上查找项目文件
    cwd = Path.cwd()
    for search_dir in [cwd] + list(cwd.parents)[:5]:
        found_all: dict[str, list[Path]] = {}
        for pattern in project_patterns:
            found_all[pattern] = list(search_dir.glob(pattern))

        total_found = sum(len(v) for v in found_all.values())

        if total_found == 0:
            continue

        if total_found == 1:
            # 唯一找到，直接返回
            for files in found_all.values():
                if files:
                    return str(files[0].resolve())

        # 多个文件 → 按优先级选
        project_name = search_dir.name
        for pattern in project_patterns:
            for f in found_all[pattern]:
                if f.stem == project_name or f.stem.lower() == project_name.lower():
                    return str(f.resolve())

        # 同名匹配失败 → 按优先级返回第一个
        for pattern in project_patterns:
            if found_all[pattern]:
                return str(found_all[pattern][0].resolve())

        # 理论上不会到达这里

    return None


def set_delphi_kb_service(service):
    """设置 Delphi 知识库服务实例"""
    global _delphi_kb_service
    _delphi_kb_service = service


def set_thirdparty_kb_service(service):
    """设置第三方库知识库服务实例"""
    global _thirdparty_kb_service
    _thirdparty_kb_service = service


def _get_or_create_pkb(project_path: str, fresh: bool = False):
    """获取或创建项目知识库实例（带缓存）

    Args:
        project_path: 项目路径
        fresh: 是否创建全新实例（用于构建操作，避免 close() 影响缓存）

    Returns:
        ProjectKnowledgeBase 实例
    """
    from ..services.knowledge_base.project_knowledge_base import ProjectKnowledgeBase

    if fresh:
        return ProjectKnowledgeBase(project_path)

    if project_path not in _pkb_cache:
        _pkb_cache[project_path] = ProjectKnowledgeBase(project_path)
    return _pkb_cache[project_path]


def _clear_pkb_cache(project_path: str) -> None:
    """关闭并移除指定项目的 PKB 缓存实例（构建完成后刷新缓存用）

    Args:
        project_path: 项目 dproj 路径
    """
    if project_path in _pkb_cache:
        try:
            _pkb_cache[project_path].close()
        except Exception as e:
            logger.debug("关闭 PKB 缓存失败: %s", str(e))
        del _pkb_cache[project_path]
        logger.info(f"已清除项目 PKB 缓存: {project_path}")


def _cleanup_pkb_cache():
    """关闭并清理所有缓存的 ProjectKnowledgeBase 实例"""
    for path, pkb in list(_pkb_cache.items()):
        try:
            pkb.close()
        except Exception as e:
            logger.debug("关闭 PKB 缓存失败: %s", str(e))
    _pkb_cache.clear()


def _search_document_kb(query: str, top_k: int = 20) -> Optional[List[dict]]:
    """搜索文档知识库（全文搜索），返回文档结果列表。

    文档 KB 使用全文搜索（FTS），对多关键词查询效果远好于符号名称匹配。
    如果文档知识库不存在或搜索失败，返回 None。
    """
    try:
        from ..services.knowledge_base.scan_generic_documents import (
            GenericDocumentScanner,
        )
        server_root = Path(__file__).parent.parent.parent
        kb_dir = str(server_root / "data" / "document-knowledge-base")
        kb_path = Path(kb_dir)
        if not kb_path.exists():
            return None
        scanner = GenericDocumentScanner(kb_dir)
        results = scanner.search(query, top_k=top_k)
        return results if results else None
    except Exception as e:
        logger.debug("文档知识库搜索失败: %s", str(e))
        return None


# AI Agent 经常将多关键字拼为一个长查询，以下集合过滤无意义的噪声词。
# 设计为两层：
#   _MKW_HARD_STOP — 极通用词，无论如何都应过滤
#   _MKW_DELPHI_KEYWORDS — Delphi 关键字，第一步过滤，但如果所有词都被过滤掉则保留
_MKW_HARD_STOP: frozenset = frozenset({
    'a', 'an', 'the', 'in', 'of', 'for', 'to', 'with', 'on', 'at', 'by', 'is', 'it',
    'delphi', 'pascal', 'syntax', 'declaration', 'declare', 'definition', 'define',
    'example', 'examples', 'usage', 'use', 'using', 'keyword', 'keywords',
    'statement', 'statements', 'reference', 'attribute', 'attributes',
    'directive', 'directives', 'section', 'clause', 'demo', 'sample', 'howto',
})

_MKW_DELPHI_KEYWORDS: frozenset = frozenset({
    'class', 'type', 'types', 'private', 'public', 'protected', 'published', 'strict',
    'nested', 'field', 'fields', 'var', 'vars', 'const', 'consts', 'procedure',
    'function', 'constructor', 'destructor', 'property', 'read', 'write', 'default',
    'override', 'virtual', 'dynamic', 'abstract', 'static', 'inline', 'deprecated',
})


def _split_multikeywords(query: str) -> List[str]:
    """将 AI 拼凑的多关键字长查询拆分为独立搜索词。

    AI Agent 经常把多个关键字拼到一个 query 里，例如：
      "Delphi class field declaration syntax private type nested ..."
    此函数识别这种情况，提取有意义的搜索词逐一搜索后聚合结果。

    设计：第一层过滤硬停用词（_MKW_HARD_STOP），第二层过滤 Delphi 关键字（_MKW_DELPHI_KEYWORDS）。
    如果所有词都是关键字（无硬停用词以外的词），则退而使用关键字本身作为搜索词。

    Returns:
        有效搜索词列表。若无需拆分则返回 [原始query]。
    """
    tokens = query.split()
    if len(tokens) <= 3:
        return [query]

    # 第一层：过滤硬停用词（a, the, delphi, syntax, etc.）
    hard_filtered = [
        t for t in tokens
        if t.lower() not in _MKW_HARD_STOP
        and len(t) > 1
    ]
    if hard_filtered:
        # 第二层：进一步过滤 Delphi 关键字
        meaningful = [
            t for t in hard_filtered
            if t.lower() not in _MKW_DELPHI_KEYWORDS
        ]
        if not meaningful:
            # 剩余全是 Delphi 关键字（如 class, type, field），仍然比原始 query 更有用
            meaningful = hard_filtered
    else:
        # 全是硬停用词，退化为原始查询
        return [query]

    # 去重（保留顺序）、截最长 8 个关键词
    seen: set = set()
    deduped: List[str] = []
    for w in meaningful:
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            deduped.append(w)
        if len(deduped) >= 8:
            break
    return deduped


def _normalize_query(query: str) -> str:
    """规范化搜索关键词，处理 AI Agent 常见的查询模式。

    当前处理：
    - Delphi 编译指令 {$WARN} → WARN（去掉 {$ 和 } 前缀后缀）
      知识库中编译指令存储为名称本身（如 'WARN'），而非 {$WARN} 格式。
    """
    q = query.strip()
    # {$WARN} / {$WARN ON} / {$IFDEF DEBUG} 等编译指令
    if q.startswith('{$') and q.endswith('}'):
        inner = q[2:-1].strip()
        if inner:
            return inner
    # 仅 $ 前缀：$WARN → WARN
    if q.startswith('$') and len(q) > 1:
        return q[1:]
    return q


async def search_knowledge(arguments: Any) -> CallToolResult:
    """统一搜索知识库（thin orchestrator: 路由 + 调度）"""
    kb_type = arguments.get("kb_type", "all")
    search_type = arguments.get("search_type", "all")
    query = _normalize_query(arguments.get("query", ""))
    top_k = min(arguments.get("top_k", 200), 500)

    # 空 query: 返回知识库状态 + 使用指引
    if not query:
        return CallToolResult(content=[{"type": "text", "text": _empty_query_guide(kb_type, search_type)}])

    # 路由: 根据 kb_type 决定要搜索的 KB 列表
    results: dict = {}
    kb_types = [kb_type] if kb_type != "all" else ["delphi", "project", "thirdparty"]
    project_path = _resolve_project_path(arguments.get("project_path"))

    # 主搜索循环: 每个 KB 独立处理 reference / symbols+semantic
    for kb in kb_types:
        try:
            if search_type == "reference":
                _search_references(kb, query, project_path, results)
            else:
                _search_symbols(kb, query, search_type, top_k, project_path, results)
        except Exception as e:
            results[f"{kb}_error"] = str(e)

    # 文档知识库 (仅 kb_type="all")
    _maybe_search_document(kb_type, query, top_k, results)

    # 多关键词 fallback: 原始 query 未命中时自动拆分后逐一搜索并去重聚合
    keywords: list = [query]
    if not _has_meaningful_results(results):
        _kw_split = _split_multikeywords(query)
        if len(_kw_split) > 1:
            keywords = _kw_split
            _multi_keyword_search(keywords, kb_types, search_type, project_path, top_k, results)

    # 格式化输出
    output = _format_search_output(query, kb_type, search_type, results, top_k, keywords)
    return CallToolResult(content=[{"type": "text", "text": output}])


# ──────────────────────────────────────────────────────────────────
# 常量 + 纯函数（重构自原嵌套函数 / 内联常量）
# ──────────────────────────────────────────────────────────────────

_SEARCH_TYPE_TO_KIND: dict = {
    'class': ['TC'], 'record': ['TR'], 'interface': ['TI'], 'enum': ['TE'],
    'set': ['TS'], 'helper': ['TH'],
    'type': ['TY', 'AT', 'PT'], 'function': ['FF', 'FP'], 'procedure': ['FP'], 'operator': ['OP'],
    'const': ['CC'], 'resourcestring': ['CR'], 'variable': ['GV'],
    'property': ['MP'], 'field': ['MF'], 'method': ['MM'], 'event': ['ME'],
    'unit': ['UI'], 'string': ['KS'], 'dfm': ['DF'], 'attribute': ['AB'],
}

_KIND_DESC: dict = {
    'TC': '类', 'TR': '记录', 'TI': '接口', 'TH': 'Helper', 'TE': '枚举', 'TS': '集合',
    'TY': '类型别名', 'AT': '数组', 'PT': '指针', 'FF': '函数', 'FP': '过程', 'OP': '运算符重载',
    'CC': '常量', 'CR': '资源字符串', 'GV': '全局变量',
    'MP': '属性', 'MF': '字段', 'MM': '方法', 'ME': '事件',
    'UI': '单元', 'KS': '字符串', 'DF': 'DFM属性', 'AB': '自定义属性',
}


def _filter_by_search_type(symbols: list, st: str) -> list:
    """按 search_type 过滤符号列表 (依据 kind_code)"""
    if st in _SEARCH_TYPE_TO_KIND:
        allowed_kinds = _SEARCH_TYPE_TO_KIND[st]
        return [s for s in symbols if s.get('kind_code', '') in allowed_kinds]
    return symbols


def _trunc_hint(items: list, results: dict, total_key, top_k: int) -> str:
    """如果结果被 top_k 截断，返回提示信息"""
    total = len(items)
    if total_key and total_key in results:
        total = results[total_key]
    if total > top_k:
        return f"  (提示: 共 {total} 条结果，top_k={top_k}，{total - top_k} 条未显示，可增大 top_k 获取全部)\n"
    return ''


def _format_symbol(r: dict) -> str:
    """格式化单个符号的输出 (含 AST 增强字段)"""
    kind_code = r.get('kind_code', '')
    type_desc = _KIND_DESC.get(kind_code) or r.get('kind') or r.get('type_name', kind_code) or ''
    # 文件路径：兼容两种 KB 返回格式
    file_info = r.get('file')
    if isinstance(file_info, dict):
        file_path = file_info.get('full_path') or file_info.get('path', 'N/A')
    else:
        file_path = r.get('full_path') or r.get('relative_path', 'N/A')

    name = r.get('name', 'N/A')
    line = r.get('line', 'N/A')

    # AST 增强字段
    extra = []
    sig = r.get('signature', '') or r.get('kind', '')
    if sig and sig not in ('', name):
        extra.append(f"签名: {sig}")
    inherits = r.get('inherits_from') or r.get('base_class', '')
    if inherits:
        extra.append(f"继承: {inherits}")
    visibility = r.get('visibility', '')
    if visibility and visibility != 'published':
        extra.append(f"可见性: {visibility}")
    modifiers = r.get('modifiers')
    if modifiers and isinstance(modifiers, str) and modifiers != '[]':
        extra.append(f"修饰: {modifiers}")
    source = r.get('source', '')
    if source == 'ast':
        extra.append("(AST)")

    result = f"  - {name} ({type_desc})\n    文件: {file_path}\n    行号: {line}\n"
    if extra:
        result += f"    {' | '.join(extra)}\n"
    return result


def _format_document_results(doc_list: list, limit: int) -> str:
    """格式化文档知识库搜索结果"""
    if not doc_list:
        return ''
    out = f"文档知识库 ({len(doc_list)}):\n"
    for i, doc in enumerate(doc_list[:limit], 1):
        doc_id = doc.get('id', '?')
        title = doc.get('title', 'N/A')
        out += f"  {i}. [ID:{doc_id}] {title}\n"
        ct = doc.get('content_type', '')
        if ct:
            out += f"     类型: {ct}\n"
        url = doc.get('url')
        path = doc.get('path', '')
        if url:
            out += f"     URL: {url}\n"
        elif path:
            out += f"     路径: {path}\n"
        sz = doc.get('size', 0)
        if sz:
            out += f"     大小: {sz} 字节\n"
        content = doc.get('content', '')
        if content:
            preview = content[:150].replace('\n', ' ')
            out += f"     预览: {preview}...\n"
    hint = _trunc_hint(doc_list, {}, None, limit)
    if hint:
        out += hint
    out += "\n"
    return out


# ──────────────────────────────────────────────────────────────────
# 搜索子路径（重构自原 search_knowledge 内联代码）
# ──────────────────────────────────────────────────────────────────

def _empty_query_guide(kb_type: str, search_type: str) -> str:
    """空 query 时返回知识库状态 + 使用指引"""
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
    try:
        guide = _append_stats_guide(guide, kb_type)
    except Exception as e:
        logger.debug("获取统计信息失败: %s", str(e))
    return guide


def _has_meaningful_results(results: dict) -> bool:
    """检查 results 中是否有有效数据（排除 _error / _warning / async_task_id 标记）"""
    return any(
        v for k, v in results.items()
        if not k.endswith('_error') and not k.endswith('_warning') and k != 'project_async_task_id'
    )


def _search_references(kb: str, query: str, project_path: Optional[str], results: dict) -> None:
    """单个 KB 的引用查询 (search_type=='reference')

    - delphi: 委托给 _delphi_kb_service.search_by_name
    - project: 解析 dproj 命名空间前缀，调用 project_kb.search_usages
    - thirdparty: 委托给 _thirdparty_kb_service.kb_instance.search_usages
    """
    if kb == "delphi" and _delphi_kb_service:
        refs = _delphi_kb_service.search_by_name(query)
        if refs:
            results["delphi_symbols"] = refs
        return

    if kb == "project":
        if not project_path:
            results["project_error"] = "未检测到项目路径"
            return
        try:
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
        return

    if kb == "thirdparty" and _thirdparty_kb_service:
        if _thirdparty_kb_service.kb_instance is None:
            _thirdparty_kb_service.load_knowledge_base()
        if _thirdparty_kb_service.kb_instance:
            refs = _thirdparty_kb_service.kb_instance.search_usages(query)
            if refs:
                results["thirdparty_references"] = refs


def _search_symbols(
    kb: str,
    query: str,
    search_type: str,
    top_k: int,
    project_path: Optional[str],
    results: dict,
) -> None:
    """单个 KB 的符号 + 语义查询 (search_type in {class, function, all, semantic, ...})"""
    if kb == "delphi" and _delphi_kb_service:
        # 名称搜索（精确/通配匹配）
        symbol_results = _delphi_kb_service.search_by_name(query)
        filtered_by_type = _filter_by_search_type(symbol_results, search_type)
        total_before_cut = len(filtered_by_type)
        filtered = filtered_by_type[:top_k]
        if filtered:
            results["delphi_symbols"] = filtered
            results["delphi_symbols_total"] = total_before_cut
        # 语义搜索（补充语义匹配结果）
        if search_type in ("semantic", "all"):
            try:
                semantic_classes = _delphi_kb_service.semantic_search_classes(query, top_k=top_k)
                if semantic_classes:
                    results["delphi_semantic_classes"] = semantic_classes
            except Exception as e:
                logger.debug("忽略非致命异常: %s", str(e))
            try:
                semantic_functions = _delphi_kb_service.semantic_search_functions(query, top_k=top_k)
                if semantic_functions:
                    results["delphi_semantic_functions"] = semantic_functions
            except Exception as e:
                logger.debug("忽略非致命异常: %s", str(e))
        return

    if kb == "project":
        if not project_path:
            results["project_error"] = "请提供 project_path 参数（当前目录未自动检测到 .dproj 文件）"
            return
        try:
            pkb = _get_or_create_pkb(project_path)
            pkb.load_knowledge_bases()
            # 搜索前检查源码是否有变更，有则自动启动异步重建（防重入）
            if not pkb.check_and_update_project_kb():
                _start_async_project_rebuild(project_path, results)
            if pkb.project_kb is None:
                results["project_error"] = (
                    f"项目知识库未构建。请先执行：\n"
                    f"  delphi_kb(action='build', kb_type='project', project_path='{project_path}')\n"
                    f"构建完成后再搜索。"
                )
                return

            # 名称搜索（search_by_name 返回与 Delphi KB 相同格式）
            project_results = pkb.project_kb.search_by_name(query)
            filtered_by_type = _filter_by_search_type(project_results, search_type)
            total_before_cut = len(filtered_by_type)
            filtered = filtered_by_type[:top_k]
            if filtered:
                results["project_symbols"] = filtered
                results["project_symbols_total"] = total_before_cut
            # 语义搜索
            if search_type in ("semantic", "all"):
                _try_semantic_search(pkb.project_kb, "project", query, top_k, results)
        except Exception as e:
            results["project_error"] = str(e)
        return

    if kb == "thirdparty" and _thirdparty_kb_service:
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
                _try_semantic_search(_thirdparty_kb_service.kb_instance, "thirdparty", query, top_k, results)


def _try_semantic_search(kb_service, kb: str, query: str, top_k: int, results: dict) -> None:
    """对 project / thirdparty 知识库执行语义搜索 (classes + functions)，失败时静默"""
    try:
        sc = kb_service.semantic_search_classes(query, top_k=top_k)
        if sc:
            results[f"{kb}_semantic_classes"] = sc
    except Exception as e:
        logger.debug("忽略非致命异常: %s", str(e))
    try:
        sf = kb_service.semantic_search_functions(query, top_k=top_k)
        if sf:
            results[f"{kb}_semantic_functions"] = sf
    except Exception as e:
        logger.debug("忽略非致命异常: %s", str(e))


def _start_async_project_rebuild(project_path: str, results: dict) -> None:
    """项目源码变更时，启动异步重建任务（防重入通过 dedup_key）"""
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
            _p.build_project_knowledge_base(rebuild=False)
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


def _maybe_search_document(kb_type: str, query: str, top_k: int, results: dict) -> None:
    """文档知识库搜索 (仅 kb_type='all' 时)"""
    if kb_type != "all":
        return
    _is_multiword = bool(_split_multikeywords(query) and len(_split_multikeywords(query)) > 1)
    try:
        doc_results = _search_document_kb(query, top_k)
        if doc_results:
            results["document"] = doc_results
            results["document_is_multiword"] = _is_multiword
    except Exception as e:
        logger.debug("文档知识库搜索失败: %s", str(e))


def _multi_keyword_search(
    keywords: list,
    kb_types: list,
    search_type: str,
    project_path: Optional[str],
    top_k: int,
    results: dict,
) -> None:
    """多关键词拆分后逐个搜索并按 (name, line, path) 或 (path, imported_by) 去重聚合"""
    seen_dedup: set = set()
    for kw in keywords:
        for kb in kb_types:
            try:
                if search_type == "reference":
                    _multi_kw_ref_one_kb(kb, kw, project_path, seen_dedup, results)
                else:
                    _multi_kw_sym_one_kb(kb, kw, search_type, project_path, seen_dedup, results)
            except Exception:
                continue
        # 对每个拆分关键词也搜索文档知识库（全文搜索比符号匹配更相关）
        try:
            kw_doc_results = _search_document_kb(kw, top_k // len(keywords) + 1)
            if kw_doc_results:
                seen_urls: set = set()
                for d in kw_doc_results:
                    du = d.get('url') or d.get('path', '')
                    if du and du not in seen_urls:
                        seen_urls.add(du)
                        results.setdefault("document", []).append(d)
        except Exception:
            continue


def _multi_kw_ref_one_kb(
    kb: str, kw: str, project_path: Optional[str], seen_dedup: set, results: dict
) -> None:
    """多关键词搜索: 单个 KB 的引用分支"""
    if kb == "delphi" and _delphi_kb_service:
        refs = _delphi_kb_service.search_by_name(kw)
        for r in refs:
            dk = (r.get('name', ''), r.get('line', 0),
                  r.get('file', {}).get('full_path', ''))
            if dk not in seen_dedup:
                seen_dedup.add(dk)
                results.setdefault("delphi_symbols", []).append(r)
    elif kb == "project" and project_path:
        try:
            pkb = _get_or_create_pkb(project_path)
            pkb.load_knowledge_bases()
            if pkb.project_kb:
                refs = pkb.project_kb.search_usages(kw)
                for r in refs:
                    dk = (r.get('file', {}).get('full_path', ''),
                          str(r.get('imported_by', [])))
                    if dk not in seen_dedup:
                        seen_dedup.add(dk)
                        results.setdefault("project_references", []).append(r)
        except Exception as e:
            logger.debug("搜索项目引用失败: %s", e)
    elif kb == "thirdparty" and _thirdparty_kb_service:
        if _thirdparty_kb_service.kb_instance is None:
            _thirdparty_kb_service.load_knowledge_base()
        if _thirdparty_kb_service.kb_instance:
            refs = _thirdparty_kb_service.kb_instance.search_usages(kw)
            for r in refs:
                dk = (r.get('file', {}).get('full_path', ''),
                      str(r.get('imported_by', [])))
                if dk not in seen_dedup:
                    seen_dedup.add(dk)
                    results.setdefault("thirdparty_references", []).append(r)


def _multi_kw_sym_one_kb(
    kb: str, kw: str, search_type: str, project_path: Optional[str], seen_dedup: set, results: dict
) -> None:
    """多关键词搜索: 单个 KB 的符号分支"""
    if kb == "delphi" and _delphi_kb_service:
        refs = _delphi_kb_service.search_by_name(kw)
        filtered = _filter_by_search_type(refs, search_type)
        for r in filtered:
            dk = (r.get('name', ''), r.get('line', 0),
                  r.get('file', {}).get('full_path', ''))
            if dk not in seen_dedup:
                seen_dedup.add(dk)
                results.setdefault("delphi_symbols", []).append(r)
    elif kb == "project" and project_path:
        try:
            pkb = _get_or_create_pkb(project_path)
            pkb.load_knowledge_bases()
            if pkb.project_kb:
                refs = pkb.project_kb.search_by_name(kw)
                filtered = _filter_by_search_type(refs, search_type)
                for r in filtered:
                    dk = (r.get('name', ''), r.get('line', 0),
                          r.get('file', {}).get('full_path', ''))
                    if dk not in seen_dedup:
                        seen_dedup.add(dk)
                        results.setdefault("project_symbols", []).append(r)
        except Exception as e:
            logger.debug("搜索三方库失败: %s", e)
    elif kb == "thirdparty" and _thirdparty_kb_service:
        if _thirdparty_kb_service.kb_instance is None:
            _thirdparty_kb_service.load_knowledge_base()
        if _thirdparty_kb_service.kb_instance:
            refs = _thirdparty_kb_service.kb_instance.search_by_name(kw)
            filtered = _filter_by_search_type(refs, search_type)
            for r in filtered:
                dk = (r.get('name', ''), r.get('line', 0),
                      r.get('file', {}).get('full_path', ''))
                if dk not in seen_dedup:
                    seen_dedup.add(dk)
                    results.setdefault("thirdparty_symbols", []).append(r)


# ──────────────────────────────────────────────────────────────────
# 输出格式化
# ──────────────────────────────────────────────────────────────────

def _format_search_output(
    query: str,
    kb_type: str,
    search_type: str,
    results: dict,
    top_k: int,
    keywords: list,
) -> str:
    """格式化搜索结果为人类可读的多段输出"""
    has_multikeyword_results = _has_meaningful_results(results)
    output = (
        f"搜索 '{query}'"
        f" ({'自动拆分关键词' if keywords and len(keywords) > 1 else '类型: ' + search_type}"
        f", 知识库: {kb_type}):\n\n"
    )
    if keywords and len(keywords) > 1 and has_multikeyword_results:
        output += "> 原始查询未命中，已自动拆分为以下关键词逐一搜索后聚合:\n"
        output += f"> {', '.join(keywords)}\n\n"
    _is_document_first = results.get("document_is_multiword", False) or (keywords and len(keywords) > 1)
    has_results = False
    # 多词查询: 文档 KB 优先展示（全文搜索更相关）
    if "document" in results and _is_document_first:
        doc_fmt = _format_document_results(results["document"], top_k)
        if doc_fmt:
            output += doc_fmt
            has_results = True

    # Delphi 符号（6 个子段）
    for key, label, style in [
        ("delphi_symbols", "Delphi 符号", "detailed"),
        ("delphi_all", "Delphi 所有符号", "all"),
        ("delphi_classes", "Delphi 类", "simple"),
        ("delphi_functions", "Delphi 函数/过程", "simple"),
        ("delphi_semantic_classes", "Delphi 类(语义搜索)", "semantic"),
        ("delphi_semantic_functions", "Delphi 函数/过程(语义搜索)", "semantic"),
    ]:
        if key in results and results[key]:
            output += _format_one_section(key, label, results[key], results, top_k, style)
            has_results = True

    # project + thirdparty 符号 + 语义
    for kb, label in [("project", "项目"), ("thirdparty", "三方库")]:
        for suffix, sublabel, style in [
            ("symbols", "符号", "detailed"),
            ("semantic_classes", "类(语义搜索)", "semantic"),
            ("semantic_functions", "函数/过程(语义搜索)", "semantic"),
        ]:
            key = f"{kb}_{suffix}"
            if key in results and results[key]:
                output += _format_one_section(key, f"{label} {sublabel}", results[key], results, top_k, style)
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
            output += _trunc_hint(refs, results, None, top_k)
            output += "\n"
            has_results = True

    # 异步重建任务信息
    if "project_async_task_id" in results:
        output += (
            f"【后台重建】检测到项目源码变更，已自动启动异步重建。\n"
            f"  可通过 async_task(action='status', task_id='{results['project_async_task_id']}') 查询进度。\n"
            f"  重建完成后重新搜索可获取最新数据。\n\n"
        )
        has_results = True

    # 提示信息
    if "project_warning" in results and results["project_warning"]:
        output += f"【提示】{results['project_warning']}\n\n"
        has_results = True

    # 单词查询: 文档 KB 靠后展示
    if "document" in results and not _is_document_first:
        doc_fmt = _format_document_results(results["document"], top_k)
        if doc_fmt:
            output += doc_fmt
            has_results = True

    # 错误信息
    for err_key, label in [("project_error", "项目"), ("thirdparty_error", "三方库"), ("delphi_error", "Delphi")]:
        if err_key in results and results[err_key]:
            output += f"【{label}】错误: {results[err_key]}\n\n"
            has_results = True

    if not has_results:
        output += "未找到相关内容\n"
    return output


def _format_one_section(
    key: str, label: str, items: list, results: dict, top_k: int, style: str
) -> str:
    """格式化单个结果段

    style:
    - 'detailed': 使用 _format_symbol(r) + definition (delphi/project/thirdparty symbols)
    - 'all': 使用 kind_code → _KIND_DESC + name (delphi_all)
    - 'simple': 使用 just name (delphi_classes, delphi_functions)
    - 'semantic': 使用 (name, sim) tuple format (semantic_*)
    """
    out = f"{label} ({len(items)}):\n"
    if style == "semantic":
        for name, sim in items[:top_k]:
            out += f"  - {name} (相似度: {sim:.2f})\n"
    elif style == "detailed":
        for r in items[:top_k]:
            out += _format_symbol(r)
            if r.get('definition'):
                out += f"    定义: {r.get('definition')}\n"
    elif style == "all":
        for r in items[:top_k]:
            kind_code = r.get('kind_code', '')
            type_desc = _KIND_DESC.get(kind_code, r.get('kind', kind_code))
            out += f"  - {r.get('name', 'N/A')} ({type_desc})\n"
    elif style == "simple":
        for r in items[:top_k]:
            out += f"  - {r.get('name', 'N/A')}\n"
    total_key = f"{key}_total" if f"{key}_total" in results else None
    out += _trunc_hint(items, results, total_key, top_k)
    out += "\n"
    return out


async def build_unified_knowledge_base(arguments: Any) -> CallToolResult:
    """
    统一构建知识库
    
    参数:
    - kb_type: "delphi"|"project"|"thirdparty"|"help"|"all" 知识库类型，支持组合(如"delphi,project")
    - project_path: 项目路径 (仅project类型需要)
    - version: Delphi版本 (仅delphi/thirdparty需要)
    - async_mode: 是否异步
    - rebuild: 是否强制重建
    """
    kb_type = arguments.get("kb_type", "all")
    project_path = _resolve_project_path(arguments.get("project_path"))
    version = arguments.get("version")
    async_mode = arguments.get("async_mode", True)
    rebuild = arguments.get("rebuild", False)
    
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
                success = _delphi_kb_service.build_knowledge_base(version=version, rebuild=rebuild)
                results["delphi"] = "成功" if success else "失败"
            elif kb == "project" and project_path:
                pkb = _get_or_create_pkb(project_path, fresh=True)
                try:
                    success = pkb.build_project_knowledge_base(rebuild=rebuild)
                    results["project"] = "成功" if success else "失败"
                finally:
                    pkb.close()
            elif kb == "thirdparty" and _thirdparty_kb_service:
                _thirdparty_kb_service.close()
                success = _thirdparty_kb_service.build_thirdparty_knowledge_base(version=version, rebuild=rebuild)
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
