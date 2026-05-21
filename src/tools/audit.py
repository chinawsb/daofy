"""
代码审计 / AST 语法解析 MCP 工具

对接 daudit.exe，支持两种模式:
  --mode audit — 执行 Delphi 源码静态分析，输出违规报告
  --mode ast   — AST 语法解析，输出实体结构信息

daudit.exe 不存在时降级为引导提示，不影响其他功能。

输出格式:
  {"mode":"audit|ast","status":"ok|error","data":{...},"summary":{...}}

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.types import CallToolResult, TextContent

logger = logging.getLogger(__name__)

# daudit.exe 路径缓存
_DAUDIT_PATH: Optional[str] = None


def _find_daudit() -> Optional[str]:
    """查找 daudit.exe 路径"""
    global _DAUDIT_PATH
    if _DAUDIT_PATH:
        return _DAUDIT_PATH

    candidates = [
        Path(__file__).parent.parent.parent / "tools" / "daudit" / "daudit.exe",
        Path.cwd() / "tools" / "daudit" / "daudit.exe",
    ]
    for p in candidates:
        if p.exists():
            _DAUDIT_PATH = str(p.resolve())
            return _DAUDIT_PATH
    return None


def _run_daudit(cmd: List[str]) -> Optional[Dict]:
    """运行 daudit.exe 并解析统一信封 JSON

    daudit 新版输出纯 JSON，格式统一为:
    {"mode":"...","status":"ok|error","data":{...},"summary":{...}}

    Args:
        cmd: daudit 命令行参数列表

    Returns:
        解析后的完整 payload dict，或 None
    """
    daudit = _find_daudit()
    if not daudit:
        return None

    full_cmd = [daudit, "--format", "json"] + cmd

    try:
        result = subprocess.run(
            full_cmd, capture_output=True, text=True, timeout=300,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode in (0, 1) and result.stdout.strip():
            return json.loads(result.stdout)
        logger.warning("daudit 异常 (exit=%d): %s", result.returncode, result.stderr[:200])
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
        logger.error("daudit 调用失败: %s", e)

    return None


def _run_audit(paths: List[str], recursive: bool = False) -> Optional[Dict]:
    """运行 daudit --mode audit

    CLI: daudit --mode audit --format json [--recursive] <path(s)>

    Returns:
        data 段 dict ({findings, totalFindings})，或 None
    """
    cmd = ["--mode", "audit"]
    if recursive:
        cmd.append("--recursive")
    cmd.extend(paths)

    payload = _run_daudit(cmd)
    if payload and payload.get("status") == "ok":
        return payload.get("data")
    return None


def _run_ast(source_dir: str, file_path: Optional[str] = None,
             compact: bool = False) -> Optional[Dict]:
    """运行 daudit --mode ast 进行 AST 语法解析

    CLI: daudit --mode ast --format json [--compact] <file(s)>
    注意 --mode ast 不支持 --recursive，需显式传文件列表。

    Args:
        source_dir: 源码目录（用于查找 .pas 文件）
        file_path: 单文件路径（优先于 source_dir）
        compact: 是否使用 --compact 压缩输出

    Returns:
        data 段 dict ({files: [...]})，或 None
    """
    # 收集待解析文件
    pas_files: List[str] = []
    if file_path:
        pas_files.append(file_path)
    elif source_dir:
        src = Path(source_dir)
        if src.is_file():
            pas_files.append(str(src.resolve()))
        elif src.is_dir():
            pas_files.extend(str(p.resolve()) for p in src.rglob("*.pas"))

    if not pas_files:
        return None

    cmd = ["--mode", "ast"]
    if compact:
        cmd.append("--compact")
    cmd.extend(pas_files)

    payload = _run_daudit(cmd)
    if payload and payload.get("status") == "ok":
        return payload.get("data")
    return None


def _extract_json(text: str) -> Optional[str]:
    """从 daudit 混合输出中提取第一个完整 JSON 对象（处理头部横幅+尾部摘要）"""
    start = text.find('{')
    if start < 0:
        return None
    # 逐字符找到匹配的闭合 }
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _call_daudit(paths: List[str], recursive: bool = False) -> Optional[Dict]:
    """调用 daudit.exe --mode audit 执行代码审计

    实际 CLI: daudit --mode audit --format json [--recursive] <path(s)>

    Args:
        paths: 文件或目录路径列表
        recursive: 是否递归扫描目录

    Returns:
        JSON 结果 dict ({findings, totalFindings})，或 None
    """
    daudit = _find_daudit()
    if not daudit:
        return None

    cmd = [daudit, "--mode", "audit", "--format", "agent"]
    if recursive:
        cmd.append("--recursive")
    cmd.extend(paths)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode in (0, 1) and result.stdout.strip():
            json_str = _extract_json(result.stdout)
            if json_str:
                return json.loads(json_str)
        logger.warning("daudit 审计异常 (exit=%d): %s", result.returncode, result.stderr[:200])
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
        logger.error("daudit 审计调用失败: %s", e)

    return None


def _call_ast(source_dir: str, file_path: Optional[str] = None) -> Optional[Dict]:
    """调用 daudit.exe --mode ast 进行 AST 语法解析

    实际 CLI: daudit --mode ast --format json <file(s)>
    注意 --mode ast 不支持 --recursive，需显式传文件列表。

    Args:
        source_dir: 源码目录（用于查找 .pas 文件）
        file_path: 单文件路径（优先于 source_dir）

    Returns:
        AST 解析结果 dict ({files: [...]})，或 None
    """
    daudit = _find_daudit()
    if not daudit:
        return None

    # 收集待解析文件
    pas_files: List[str] = []
    if file_path:
        pas_files.append(file_path)
    elif source_dir:
        src = Path(source_dir)
        if src.is_file():
            pas_files.append(str(src.resolve()))
        elif src.is_dir():
            # 手动收集 .pas 文件（ast 模式不支持 --recursive）
            pas_files.extend(str(p.resolve()) for p in src.rglob("*.pas"))

    if not pas_files:
        return None

    cmd = [daudit, "--mode", "ast", "--format", "json"] + pas_files

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode == 0 and result.stdout.strip():
            stdout = result.stdout.strip()
            # --format agent 对 AST 模式输出纯 JSON，尝试直接解析
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                json_str = _extract_json(stdout)
                if json_str:
                    return json.loads(json_str)
        logger.warning("AST 解析异常 (exit=%d): %s", result.returncode, result.stderr[:200])
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
        logger.error("AST 解析调用失败: %s", e)

    return None


# ── 严重级别排序（映射 daudit 实际 severity → 显示级别）──
_DAUDIT_SEVERITY_MAP = {
    "error": "critical",
    "warning": "warning",
    "hint": "suggestion",
}
_SEVERITY_ORDER = {"critical": 0, "warning": 1, "suggestion": 2}
_SEVERITY_LABEL = {"critical": "🔴 严重", "warning": "🟡 一般", "suggestion": "🔵 建议"}


def _format_report(data: Dict, min_severity: str = "suggestion") -> str:
    """将审计 data 段格式化为 Markdown 报告

    data 格式:
    {
        "findings": [
            {"rule_id":"...", "file":"...", "line":N, "column":N,
             "severity":"hint|warning|error",
             "category":"...", "message":"...",
             "code_snippet":"..."}
        ],
        "totalFindings": N
    }
    """
    findings: List[Dict] = data.get("findings", [])
    total = data.get("totalFindings", len(findings))

    min_level = _SEVERITY_ORDER.get(min_severity, 2)

    lines: List[str] = []
    lines.append("# 代码审计报告")
    lines.append("")
    lines.append(f"**违规总数**: {total}")
    lines.append("")

    # 按严重级别分组
    groups: Dict[str, List[Dict]] = {"critical": [], "warning": [], "suggestion": []}
    for f in findings:
        raw_sev = f.get("severity", "hint")
        mapped_sev = _DAUDIT_SEVERITY_MAP.get(raw_sev, "suggestion")
        lv = _SEVERITY_ORDER.get(mapped_sev, 2)
        if lv <= min_level:
            groups[mapped_sev].append(f)

    # 分类统计
    cat_count: Dict[str, int] = {}
    for f in findings:
        cat = f.get("category", "Other")
        cat_count[cat] = cat_count.get(cat, 0) + 1
    if cat_count:
        lines.append("### 按类别分布")
        for cat in sorted(cat_count):
            lines.append(f"- **{cat}**: {cat_count[cat]}")
        lines.append("")

    for display_sev in ["critical", "warning", "suggestion"]:
        items = groups[display_sev]
        if not items:
            continue
        lines.append(f"## {_SEVERITY_LABEL[display_sev]} ({len(items)} 条)")
        lines.append("")

        for f in items:
            rule_id = f.get("rule_id", "")
            file_path = f.get("file", "?")
            line_num = f.get("line", "?")
            column = f.get("column", "")
            category = f.get("category", "")
            message = f.get("message", "")
            snippet = f.get("code_snippet", "")

            loc = f"`{file_path}:{line_num}"
            if column:
                loc += f":{column}"
            loc += "`"

            header = f"- **[{rule_id}]** {category} — {loc}" if rule_id else f"- **{category}** — {loc}"
            lines.append(header)
            lines.append(f"  {message}")
            if snippet:
                lines.append("  ```pascal")
                lines.append(f"  {snippet}")
                lines.append("  ```")
            lines.append("")

    return "\n".join(lines)


def _format_ast_report(data: Dict) -> str:
    """将 AST data 段格式化为 Markdown 报告

    data 格式:
    {"files": [{"file": "...", "unit_name": "...",
                "uses": {"interface":[...], "implementation":[...]},
                "entities": [
                    {"kind":"TC", "name":"TMyClass", ...},
                    {"kind":"FP", "name":"Run", "signature":"procedure Run()", ...},
                    ...
                ],
                "errors":[...]}]}
    """
    files_data: List[Dict] = data.get("files", [])
    if not files_data:
        return "# AST 语法解析报告\n\n*无解析结果*"

    lines: List[str] = []
    lines.append("# AST 语法解析报告")
    lines.append("")

    for file_idx, file_info in enumerate(files_data):
        file_name = file_info.get("file", "?")
        status = file_info.get("status", "ok")
        unit_name = file_info.get("unit_name", "")
        parse_time = file_info.get("parse_time_ms", 0)
        errors = file_info.get("errors", [])
        uses = file_info.get("uses", {})
        entities: List[Dict] = file_info.get("entities", [])

        if file_idx > 0:
            lines.append("---")
            lines.append("")

        lines.append(f"## 文件: `{file_name}`")
        lines.append("")

        if status != "ok":
            err_msg = file_info.get("error_msg", "未知错误")
            lines.append(f"**解析失败**: {err_msg}")
            lines.append("")
            continue

        # 文件元信息
        meta_parts = [f"**单元**: {unit_name}"] if unit_name else []
        if parse_time:
            meta_parts.append(f"**解析耗时**: {parse_time}ms")
        if meta_parts:
            lines.append(" | ".join(meta_parts))
            lines.append("")

        # Uses 引用
        if uses.get("interface") or uses.get("implementation"):
            lines.append("### Uses 引用")
            if uses.get("interface"):
                lines.append(f"- **interface**: {', '.join(uses['interface'])}")
            if uses.get("implementation"):
                lines.append(f"- **implementation**: {', '.join(uses['implementation'])}")
            lines.append("")

        if not entities:
            lines.append("*无实体*")
            lines.append("")
            continue

        # ── 实体概览：按 kind 分组统计 ──
        kind_count: Dict[str, int] = {}
        kind_labels = {
            "TC": "Class", "TR": "Record", "TI": "Interface", "TH": "Helper",
            "TE": "Enum", "TS": "Set", "TY": "Type Alias",
            "FF": "Function", "FP": "Procedure", "OP": "Operator",
            "CC": "Const", "CR": "ResourceString", "GV": "Global Variable",
            "MF": "Field", "MP": "Property",
        }
        for ent in entities:
            kind = ent.get("kind", "?")
            kind_count[kind] = kind_count.get(kind, 0) + 1

        lines.append(f"### 实体概览（共 {len(entities)} 个）")
        for kind in sorted(kind_count):
            label = kind_labels.get(kind, kind)
            lines.append(f"- **{label}** ({kind}): {kind_count[kind]}")
        lines.append("")

        # ── 类/接口/记录（TC / TI / TR）──
        type_entities = [e for e in entities if e.get("kind") in ("TC", "TI", "TR")]
        if type_entities:
            lines.append("### 类型定义")
            for ent in type_entities:
                kind = ent.get("kind", "")
                kind_label = kind_labels.get(kind, kind)
                name = ent.get("name", "(anonymous)")
                sig = ent.get("signature", "")

                # 类/接口/记录有 name 时用 name，否则从成员方法名推断或 fallback
                if name:
                    display = f"`{name}`"
                elif sig and sig.strip() not in ('= class', ''):
                    display = f"`{sig}`"
                else:
                    display = f"`{kind_label}`"
                lines.append(f"- **{kind_label}**: {display}")
                if ent.get("inherits_from"):
                    lines.append(f"  - 继承: {ent['inherits_from']}")
                if ent.get("inheritance_chain"):
                    chain = " → ".join(ent["inheritance_chain"])
                    lines.append(f"  - 继承链: {chain}")
                members = ent.get("members", [])
                if members:
                    for m in members[:15]:
                        mk = m.get("kind", "")
                        mn = m.get("name", "")
                        ml = m.get("line", "")
                        loc = f" (行 {ml})" if ml else ""
                        lines.append(f"  - `{mk}` {mn}{loc}")
                    if len(members) > 15:
                        lines.append(f"  - ... 还有 {len(members) - 15} 个成员")
            lines.append("")

        # ── 函数/过程（FF / FP / OP）──
        func_entities = [e for e in entities if e.get("kind") in ("FF", "FP", "OP")]
        if func_entities:
            lines.append("### 函数/过程")
            for ent in func_entities:
                kind = ent.get("kind", "")
                kind_label = kind_labels.get(kind, kind)
                sig = ent.get("signature", ent.get("name", "?"))
                scope = ent.get("parent_scope", "")
                line_no = ent.get("start_line", "")
                loc = f" (行 {line_no})" if line_no else ""
                scope_str = f" ← {scope}" if scope else ""
                lines.append(f"- `{sig}`{scope_str}{loc}")
            lines.append("")

        # ── 常量/枚举/变量（CC / CR / TE / TS / GV / TY）──
        other_entities = [
            e for e in entities
            if e.get("kind") in ("CC", "CR", "TE", "TS", "GV", "TY")
        ]
        if other_entities:
            lines.append("### 常量/枚举/变量")
            for ent in other_entities:
                kind = ent.get("kind", "")
                kind_label = kind_labels.get(kind, kind)
                name = ent.get("name", "?")
                extra = ""
                if ent.get("value") is not None:
                    extra = f" = {ent['value']}"
                elif ent.get("definition"):
                    extra = f" = {ent['definition']}"
                lines.append(f"- **{kind_label}**: `{name}`{extra}")
            lines.append("")

        # 解析错误/警告
        if errors:
            lines.append("### 解析警告/错误")
            for err in errors:
                line_no = err.get("line", "?")
                msg = err.get("message", "")
                sev = err.get("severity", "warning")
                lines.append(f"- [{sev}] 第 {line_no} 行: {msg}")
            lines.append("")

    return "\n".join(lines)


def _build_guide() -> str:
    """daudit.exe 不存在时的引导提示"""
    return (
        "# 代码审计工具未就绪\n\n"
        "AST 审计引擎 (daudit.exe) 尚未安装。安装后可自动运行 50+ 条静态分析规则。\n\n"
        "## 当前可用的替代审计方式\n\n"
        "1. **get_coding_rules(section=\"review\")** — 获取审核清单，AI 按清单逐项检查\n"
        "2. **delphi_kb(query=..., search_type=\"reference\")** — 查 API 用法\n"
        "3. **file_tool(action=\"read\", ...)** — 读源码做人工审查\n\n"
        "## 两种模式\n\n"
        "- **audit**（默认）: `daudit --mode audit` — 静态分析，输出违规报告\n"
        "- **ast**: `daudit --mode ast` — AST 语法解析，输出实体结构\n\n"
        "## 预计目录结构\n\n"
        "```\ntools/daudit/\n└── daudit.exe    ← AST 审计引擎\n```\n\n"
        "放置 daudit.exe 后，重新调用本工具即可使用。"
    )


async def run_audit(arguments: Dict[str, Any]) -> CallToolResult:
    """执行 Delphi 代码审计 / AST 语法解析

    参数:
        source_dir: 源码目录路径（审计/ast 模式必需之一）
        file_path:  单文件路径（ast 模式可选，优先于 source_dir）
        mode:       运行模式，默认 "audit"。可选 "ast"（AST 语法解析）
        severity:   最低严重级别，默认 "suggestion"（仅 audit 模式）
        output_format: 输出格式，默认 "report"。可选 "json"

    返回:
        结构化 CallToolResult
    """
    source_dir = arguments.get("source_dir", "").strip()
    file_path = arguments.get("file_path", "").strip() or None
    mode = arguments.get("mode", "audit")
    severity = arguments.get("severity", "suggestion")
    output_format = arguments.get("output_format", "report")

    # 校验参数
    if not source_dir and not file_path:
        return CallToolResult(
            content=[TextContent(
                type="text",
                text="# 参数错误\n\n请提供 `source_dir`（目录）或 `file_path`（文件）参数。\n\n"
                     '示例: `run_audit(source_dir="C:\\\\Project\\\\src")`\n'
                     '      `run_audit(mode="ast", file_path="Unit1.pas")`'
            )],
            isError=True,
        )

    if source_dir:
        src_path = Path(source_dir)
        if not src_path.exists():
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"# 路径不存在\n\n`{source_dir}` 不存在，请检查路径。"
                )],
                isError=True,
            )

    if file_path:
        fp_path = Path(file_path)
        if not fp_path.exists():
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"# 文件不存在\n\n`{file_path}` 不存在，请检查路径。"
                )],
                isError=True,
            )

    # 检查 daudit 是否可用
    if not _find_daudit():
        guide = _build_guide()
        guide += (
            f"\n---\n**请求参数**: mode=`{mode}`, source_dir=`{source_dir}`, "
            f"file_path=`{file_path or ''}`\n\n"
            f"daudit.exe 就绪后，直接重新调用即可。"
        )
        return CallToolResult(content=[TextContent(type="text", text=guide)])

    # ── AST 语法解析模式 ──
    if mode == "ast":
        data = _run_ast(source_dir, file_path)
        if not data:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text="# AST 解析执行失败\n\n"
                         "daudit.exe 已找到但解析出错。请检查:\n"
                         "1. daudit.exe 是否可执行\n"
                         "2. 目录/文件是否包含 .pas 文件\n"
                         "3. 是否有足够内存/磁盘空间\n\n"
                         f"**目录**: {source_dir}\n"
                         f"**文件**: {file_path or '（全部）'}"
                )],
                isError=True,
            )

        if output_format == "json":
            text = json.dumps(data, indent=2, ensure_ascii=False)
        else:
            text = _format_ast_report(data)

        return CallToolResult(content=[TextContent(type="text", text=text)])

    # ── 代码审计模式（默认）──
    # audit 模式需要 source_dir
    if not source_dir:
        return CallToolResult(
            content=[TextContent(
                type="text",
                text="# 参数错误\n\n审计模式需要 `source_dir` 参数。\n\n"
                     '示例: `run_audit(source_dir="C:\\\\Project\\\\src")`'
            )],
            isError=True,
        )

    data = _run_audit([source_dir], recursive=True)
    if not data:
        return CallToolResult(
            content=[TextContent(
                type="text",
                text="# 审计执行失败\n\n"
                     "daudit.exe 已找到但执行出错。请检查:\n"
                     "1. daudit.exe 是否可执行\n"
                     "2. 源码目录是否包含 .pas 文件\n"
                     "3. 是否有足够内存/磁盘空间\n\n"
                     f"**目录**: {source_dir}"
            )],
            isError=True,
        )

    # 格式化输出
    if output_format == "json":
        text = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        text = _format_report(data, severity)

    return CallToolResult(content=[TextContent(type="text", text=text)])
