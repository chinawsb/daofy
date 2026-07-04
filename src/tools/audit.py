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
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.types import CallToolResult, TextContent

from ..constants import TIMEOUT_AUDIT

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
            full_cmd, capture_output=True, text=True, timeout=TIMEOUT_AUDIT,
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


def _run_skeleton(base_dir: str, file_path: Optional[str] = None,
                   detail: str = "compact") -> Optional[List[Dict]]:
    """运行 daudit --mode skeleton 提取代码骨架摘要

    CLI: daudit --mode skeleton --skeleton-detail compact --format json <file(s)>

    skeleton 模式专为 AI Agent 设计，输出预格式化的文本摘要：
      单元名、uses、类/记录/接口、函数/过程、常量/变量
    --skeleton-detail compact: 无调用链信息，最省 token

    Args:
        base_dir: 审计基准目录（用于查找 .pas 文件）
        file_path: 单文件路径（优先于 base_dir）
        detail: skeleton 详细度: compact（推荐）/ normal / full

    Returns:
        list of {"file": path, "data": text}，或 None
    """
    daudit = _find_daudit()
    if not daudit:
        return None

    pas_files: List[str] = []
    if file_path:
        pas_files.append(file_path)
    elif base_dir:
        src = Path(base_dir)
        if src.is_file():
            pas_files.append(str(src.resolve()))
        elif src.is_dir():
            pas_files.extend(str(p.resolve()) for p in src.rglob("*.pas"))

    if not pas_files:
        return None

    cmd = [daudit, "--mode", "skeleton", "--skeleton-detail", detail,
           "--format", "json"]
    cmd.extend(pas_files)

    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            tmp_path = tmp.name

        with open(tmp_path, 'wb') as f:
            result = subprocess.run(
                cmd, stdout=f, stderr=subprocess.PIPE,
                timeout=TIMEOUT_AUDIT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )

        if result.returncode == 0 and os.path.getsize(tmp_path) > 0:
            with open(tmp_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                files_data = payload.get("data", payload)
                if isinstance(files_data, dict):
                    files_list = files_data.get("files", [])
                elif isinstance(files_data, list):
                    files_list = files_data
                else:
                    files_list = []
                logger.info("Skeleton 解析完成: %d 个文件", len(files_list))
                return files_list

        stderr = result.stderr.strip()[:200] if result.stderr else ""
        logger.warning("Skeleton 解析异常 (exit=%d): %s", result.returncode, stderr)

    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
        logger.error("Skeleton 解析调用失败: %s", e)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

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



def _build_guide() -> str:
    """daudit.exe 不存在时的引导提示"""
    return (
        "# 代码分析工具未就绪\n\n"
        "AST 分析引擎 (daudit.exe) 尚未安装。安装后可提供 Delphi 源码结构化解析能力。\n\n"
        "## 当前可用的替代方式\n\n"
        "1. **delphi_file(action=\"read\", ...)** — 读源码自行分析结构\n"
        "2. **delphi_kb(query=..., search_type=\"reference\")** — 查 API 用法\n"
        "3. **get_coding_rules(section=\"review\")** — 获取审核清单\n\n"
        "## 两种模式（AI 常用程度排序）\n\n"
        "1. **ast**（⭐ 推荐，AI Agent 摘要）: `daudit --mode skeleton --compact` — 代码骨架提取。\n"
            "   输出预格式化文本（单元名、uses、类/函数/常量），无需 AI 二次解析，最省 token。\n"
        "2. **audit**: `daudit --mode audit` — 运行 50+ 条静态分析规则审计代码质量。\n"
        "   适用于审查特定违规模式\n\n"
        "## 预计目录结构\n\n"
        "```\ntools/daudit/\n└── daudit.exe    ← AST 分析引擎\n```\n\n"
        "放置 daudit.exe 后，重新调用本工具即可使用。"
    )


# ═══════════════════════════════════════════════════════════
# Runtime 注册检查（模式 "runtime"）
# ═══════════════════════════════════════════════════════════

_RULES_PATH = Path(__file__).parent.parent / "rules" / "runtime_registry.json"


def _load_runtime_rules() -> List[Dict]:
    """加载运行时注册检查规则"""
    if not _RULES_PATH.exists():
        return []
    try:
        with open(_RULES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("rules", [])
    except Exception as e:
        logger.warning("加载运行时规则失败: %s", e)
        return []


def _find_pas_dfm_files(base_dir: str) -> tuple:
    """扫描目录下的 .pas 和 .dfm 文件"""
    src = Path(base_dir)
    pas_files = list(src.rglob("*.pas"))
    dfm_files = list(src.rglob("*.dfm"))
    return pas_files, dfm_files


def _extract_classes_from_dfm(filepath: Path) -> set:
    """从 DFM 文件提取组件类名 (object Xxx: TYyy)"""
    classes = set()
    try:
        text = filepath.read_text(encoding="utf-8-sig")
        for m in re.finditer(r'object\s+\w+\s*:\s*(T\w+)', text):
            classes.add(m.group(1))
    except Exception as e:
        logger.debug("提取 DFM 类名失败 %s: %s", filepath, e)
    return classes


def _extract_uses_set(filepath: Path) -> set:
    """从 PAS 文件提取所有 uses 中的单元名"""
    units = set()
    try:
        text = filepath.read_text(encoding="utf-8-sig")
        # 移除字符串和注释
        text = re.sub(r"'(?:[^']*)'", '', text)
        text = re.sub(r'\{[^}]*\}', '', text)
        text = re.sub(r'//[^\n]*', '', text)
        # 匹配 uses ... ; 段
        for m in re.finditer(
            r'\buses\b\s*(.*?)\s*;',
            text, re.DOTALL
        ):
            section = m.group(1)
            for part in section.split(','):
                part = part.strip()
                if part and not part[0].isupper():
                    continue
                units.add(part)
    except Exception as e:
        logger.debug("提取 uses 列表失败 %s: %s", filepath, e)
    return units


def _check_runtime_rules(base_dir: str) -> List[Dict]:
    """执行运行时注册规则检查"""
    rules = _load_runtime_rules()
    if not rules:
        return [{
            "id": "N/A",
            "severity": "warning",
            "message": "未找到运行时规则文件或规则为空",
        }]

    pas_files, dfm_files = _find_pas_dfm_files(base_dir)
    if not pas_files and not dfm_files:
        return [{
            "id": "N/A",
            "severity": "info",
            "message": f"在 {base_dir} 中未找到 .pas 或 .dfm 文件",
        }]

    # 收集项目中全部类名（从 DFM 最可靠）
    project_classes: set = set()
    all_uses: set = set()

    for f in dfm_files:
        project_classes |= _extract_classes_from_dfm(f)
    for f in pas_files:
        all_uses |= _extract_uses_set(f)

    findings: List[Dict] = []
    for rule in rules:
        triggers = rule.get("triggers", [])
        dependencies = rule.get("dependencies", [])
        require_unit = rule.get("require_unit", "")

        # 检查是否有触发器类
        has_trigger = any(t in project_classes for t in triggers)
        if not has_trigger:
            continue

        # 如果定义了依赖类，检查是否有命中
        if dependencies:
            has_dep = any(d in project_classes for d in dependencies)
            if not has_dep:
                continue

        # 检查 require_unit 是否在 uses 中
        unit_found = False
        for u in all_uses:
            if u == require_unit or u.endswith('.' + require_unit):
                unit_found = True
                break

        if not unit_found:
            findings.append({
                "id": rule["id"],
                "severity": rule.get("severity", "warning"),
                "trigger_classes": [t for t in triggers if t in project_classes],
                "dependencies": [d for d in dependencies if d in project_classes],
                "require_unit": require_unit,
                "message": rule.get("message", ""),
            })

    return findings


def _format_runtime_report(findings: List[Dict]) -> str:
    """格式化运行时注册检查报告"""
    if not findings:
        return "## ✅ 运行时注册检查通过\n\n未发现缺失的运行时注册单元。\n"

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]

    lines = ["## 🔍 运行时注册检查结果\n"]
    lines.append(f"| 级别 | 规则 | 数量 |")
    lines.append(f"|------|------|------|")
    lines.append(f"| 🔴 错误 | {len(errors)} 项 |" if errors else "| 🔴 错误 | 0 |")
    lines.append(f"| 🟡 警告 | {len(warnings)} 项 |" if warnings else "| 🟡 警告 | 0 |")
    lines.append("")

    if not errors and not warnings:
        lines.append("检查通过，未发现问题。\n")
        return "\n".join(lines)

    for f in findings:
        icon = "🔴" if f["severity"] == "error" else "🟡"
        lines.append(f"### {icon} [{f['id']}] {f['severity'].upper()}")
        lines.append("")
        msg = f["message"]
        if f.get("trigger_classes"):
            msg = msg.replace("{triggers}", ", ".join(f["trigger_classes"]))
        if f.get("dependencies"):
            msg = msg.replace("{dependencies}", ", ".join(f["dependencies"]))
        lines.append(f"**{msg}**")
        lines.append("")
        lines.append(f"- 触发类: `{'`, `'.join(f.get('trigger_classes', []))}`")
        if f.get("dependencies"):
            lines.append(f"- 依赖类: `{'`, `'.join(f['dependencies'])}`")
        lines.append(f"- 建议添加: `{f.get('require_unit', '')}` 到 uses 子句")
        lines.append("")

    return "\n".join(lines)


async def run_audit(arguments: Dict[str, Any]) -> CallToolResult:
    """执行 Delphi 代码审计 / AST 语法解析 / Runtime 注册检查

    参数:
        base_dir:   审计基准目录 — 审计/AST解析/runtime检查时查找项目及源码的根路径
        file_path:    单文件路径（ast 模式可选，优先于 base_dir）
        mode:         运行模式，默认 "audit"。可选 "ast"（AST 语法解析）、"runtime"（运行时注册检查）
        severity:     最低严重级别，默认 "suggestion"（仅 audit 模式）
        output_format: 输出格式，默认 "report"。可选 "json"

    返回:
        结构化 CallToolResult
    """
    base_dir = arguments.get("base_dir", "").strip()
    file_path = arguments.get("file_path", "").strip() or None
    mode = arguments.get("mode", "audit")
    severity = arguments.get("severity", "suggestion")
    output_format = arguments.get("output_format", "report")

    # 校验参数
    if not base_dir and not file_path:
        return CallToolResult(
            content=[TextContent(
                type="text",
                text="# 参数错误\n\n请提供 `base_dir`（审计基准目录）或 `file_path`（文件）参数。\n\n"
                     '示例: `run_audit(base_dir="C:\\\\Project\\\\src")`\n'
                     '      `run_audit(mode="ast", file_path="Unit1.pas")`'
            )],
            isError=True,
        )

    if base_dir:
        src_path = Path(base_dir)
        if not src_path.exists():
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"# 路径不存在\n\n`{base_dir}` 不存在，请检查路径。"
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

    # ── Runtime 注册检查模式（不需要 daudit）──
    if mode == "runtime":
        if not base_dir:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text="# 参数错误\n\nruntime 模式需要 `base_dir` 参数。\n\n"
                         '示例: `run_audit(mode="runtime", base_dir="C:\\\\Project\\\\src")`'
                )],
                isError=True,
            )
        findings = _check_runtime_rules(base_dir)
        text = _format_runtime_report(findings)
        return CallToolResult(content=[TextContent(type="text", text=text)])

    # 检查 daudit 是否可用
    if not _find_daudit():
        guide = _build_guide()
        guide += (
            f"\n---\n**请求参数**: mode=`{mode}`, base_dir=`{base_dir}`, "
            f"file_path=`{file_path or ''}`\n\n"
            f"daudit.exe 就绪后，直接重新调用即可。"
        )
        return CallToolResult(content=[TextContent(type="text", text=guide)])

    # ── AST 语法解析模式（实际调用 daudit --mode skeleton）──
    if mode == "ast":
        detail = "compact"  # compact / normal / full
        files_list = _run_skeleton(base_dir, file_path, detail=detail)
        if not files_list:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text="# AST 解析执行失败\n\n"
                         "daudit.exe 已找到但解析出错。请检查:\n"
                         "1. daudit.exe 是否可执行\n"
                         "2. 目录/文件是否包含 .pas 文件\n"
                         "3. 是否有足够内存/磁盘空间\n\n"
                         f"**目录**: {base_dir}\n"
                         f"**文件**: {file_path or '（全部）'}"
                )],
                isError=True,
            )

        if output_format == "json":
            text = json.dumps(files_list, indent=2, ensure_ascii=False)
        else:
            # skeleton 模式返回的 data 已是预格式化文本，直接拼接输出
            parts = []
            for fi in files_list:
                fname = fi.get("file", "?")
                fdata = fi.get("data", "")
                header = f"## {fname}\n"
                parts.append(header + fdata)
            text = "# 代码结构摘要（Skeleton）\n\n" + "\n---\n\n".join(parts)

            # 提示 AI Agent: normal/full 额外提供什么信息
            text += (
                "\n\n---\n"
                "> 💡 当前 skeleton-detail=compact（最省 token）。若需要更多上下文，"
                "可指定 `skeleton_detail=\"normal\"` 或 `skeleton_detail=\"full\"` 再调 run_audit：\n"
                "> - **normal** — 同 compact，无额外信息（compact/normal 输出量相同）\n"
                "> - **full** — 在每个函数/过程后追加 `// calls=[被调函数列表] | reads=[读取的全局变量列表]`，\n"
                ">   用于分析调用链和变量依赖，token 约增加一倍\n"
            )

        return CallToolResult(content=[TextContent(type="text", text=text)])

    # ── 代码审计模式（默认）──
    # audit 模式需要 base_dir
    if not base_dir:
        return CallToolResult(
            content=[TextContent(
                type="text",
                text="# 参数错误\n\n审计模式需要 `base_dir` 参数。\n\n"
                     '示例: `run_audit(base_dir="C:\\\\Project\\\\src")`'
            )],
            isError=True,
        )

    data = _run_audit([base_dir], recursive=True)
    if not data:
        return CallToolResult(
            content=[TextContent(
                type="text",
                text="# 审计执行失败\n\n"
                     "daudit.exe 已找到但执行出错。请检查:\n"
                     "1. daudit.exe 是否可执行\n"
                     "2. 源码目录是否包含 .pas 文件\n"
                     "3. 是否有足够内存/磁盘空间\n\n"
                     f"**目录**: {base_dir}"
            )],
            isError=True,
        )

    # 格式化输出
    if output_format == "json":
        text = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        text = _format_report(data, severity)

    return CallToolResult(content=[TextContent(type="text", text=text)])
