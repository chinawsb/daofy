"""
编码规则工具

提供 Delphi 源码编码规则查询功能，支持按章节分段获取，
减少 token 消耗并提升 AI Agent 的规则遵守率。
"""

import re
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from mcp.types import CallToolResult, TextContent

from src.mcp_resources import PUBLIC_RESOURCE_SPECS, resolve_resource_path

from ..utils.logger import get_logger

logger = get_logger(__name__)

# 章节名称映射：短键 → Markdown 标题（## 或 ###）
SECTION_KEYS: Dict[str, str] = {
    "planning": "P0 前置计划与审查",
    "workflow": "工作流总览",
    "directory": "📁 目录约束",
    "env": "① 环境检查",
    "kb_search": "② KB 搜索（编码前必做）",
    "writing": "③ 写 Delphi 代码",
    "format": "④ 格式化",
    "compile": "⑤ 编译",
    "review_guide": "⑦ 代码审核",
    "cleanup": "⑥ 清理 & 验证",
    "review_detail": "审核",
    "kb_build": "知识库重建",
    "agent_rules": "Agent 操作硬规则",
    "human_collab": "人机协同 — 异常诊断与人工介入",
    "experience": "⑪ 经验保存 — 将知识沉淀到经验库",
    "maintenance": "⑫ 规则维护",
    "automation": "⚙ 自动化测试架构 — 感知·规划·执行·反馈循环",
    "ui-testing": "⑧ 自动化 UI 交互测试",
    "ui_layout": "UI 布局规范与审计",
    "console-testing": "⑨ 控制台程序交互验证",
    # ③ 写 Delphi 代码 内的子章节
    "delphi_file_write_rule": "delphi_file 写入规则",
    "delphi_file_dirty_flag": "脏标记保护（v2026.06.12+）",
    "delphi_file_output_format": "紧凑输出格式（v2026.06.12+）",
    "delphi_file_usage_tips": "推荐做法",
    # 审核子章节（### 级别）
    "consistency": "一致性",
    "completeness": "完整性",
    "resource_leak": "资源泄露",
    "delphi_specific": "Delphi 特有陷阱",
    "common_errors": "常见错误模式",
    "code_quality": "代码质量",
    "data_conversion": "数据转换",
    "safety": "安全",
    "performance": "性能",
}

SECTION_ALIASES: Dict[str, str] = {
    "kb-search": "kb_search",
    "kb-rebuild": "kb_build",
    "agent-rules": "agent_rules",
    "dir": "directory",
    "dirs": "directory",
    "目录": "directory",
    "human-collab": "human_collab",
    "review-guide": "review_guide",
    "review-detail": "review_detail",
    "resource-leak": "resource_leak",
    "delphi-specific": "delphi_specific",
    "common-errors": "common_errors",
    "code-quality": "code_quality",
    "data-conversion": "data_conversion",
    "delphi-file-rules": "delphi_file_write_rule",
    "delphi-file-write-rule": "delphi_file_write_rule",
    "delphi-file-dirty-flag": "delphi_file_dirty_flag",
    "delphi-file-output-format": "delphi_file_output_format",
    "delphi-file-usage-tips": "delphi_file_usage_tips",
    "delphi_file_rules": "delphi_file_write_rule",
    "ui_testing": "ui-testing",
    "ui-layout": "ui_layout",
    "layout": "ui_layout",
    "console_testing": "console-testing",
}


def _normalize_section_name(section_name: str) -> str:
    """Return the canonical section key accepted by SECTION_KEYS/META_SECTIONS."""
    return SECTION_ALIASES.get(section_name, section_name)


# 元章节：组合多个相关标题一起返回
META_SECTIONS: Dict[str, List[str]] = {
    "review": ["review_guide", "review_detail"],
    "coding": ["writing", "format", "compile"],
}

# 反向映射：标题 → 短键（用于错误提示）
TITLE_TO_KEY = {v: k for k, v in SECTION_KEYS.items()}


CODING_RULES_DIR = Path(__file__).parent.parent / "resources" / "coding-rules"


def _default_rules_candidates() -> List[Path]:
    """Return built-in coding rule files in preferred lookup order.

    Returns either:
    - the coding-rules/ directory (merged by _read_first_existing_text), or
    - the MCP resource path as fallback.
    """
    # Return the new directory structure — _read_first_existing_text's directory-mode
    # merge will pick up and join all .md files within it.
    if CODING_RULES_DIR.is_dir():
        return [CODING_RULES_DIR]
    # Fallback: try the MCP resource path directly
    try:
        coding_rules = next(
            spec for spec in PUBLIC_RESOURCE_SPECS
            if spec.uri == "delphi://coding-rules"
        )
        path = resolve_resource_path(coding_rules)
        return [path] if path is not None else []
    except StopIteration:
        return []


def _read_first_existing_text(paths: List[Path], label: str) -> Tuple[str, Optional[Path]]:
    """Read the first existing UTF-8 text file from a candidate list.

    If the first path is the CODING_RULES_DIR (a directory), merge all .md files
    within it. Otherwise read the file directly.
    """
    for path in paths:
        if not path.exists():
            continue
        # Directory mode: merge all .md files from coding-rules/
        if path == CODING_RULES_DIR:
            parts: list[str] = []
            merged_paths = sorted(path.rglob("*.md"))
            for f in merged_paths:
                try:
                    parts.append(f.read_text(encoding="utf-8"))
                except Exception as e:
                    logger.error(f"读取 {label} 子文件失败: {f}: {str(e)}")
                    continue
            if parts:
                merged = "\n\n".join(parts)
                return merged, path
            return "", None
        # Single file mode
        try:
            return path.read_text(encoding='utf-8'), path
        except Exception as e:
            logger.error(f"读取{label}失败: {path}: {str(e)}")
            continue
    return "", None


def _find_heading_ranges(lines: List[str]) -> Dict[str, Tuple[int, int]]:
    """解析 markdown 行列表，返回 {标题文本: (起始行号, 结束行号)} 的映射。

    结束行号指向下一同级/更高级标题的前一行，若无后续标题则指向末尾。
    """
    # 收集所有标题行
    heading_pattern = re.compile(r'^(#{2,4})\s+(.+)$')
    headings: List[Tuple[int, str, int]] = []  # (level, title, line_index)

    for i, line in enumerate(lines):
        m = heading_pattern.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            headings.append((level, title, i))

    # 为每个标题计算内容范围
    ranges: Dict[str, Tuple[int, int]] = {}
    for idx, (level, title, start) in enumerate(headings):
        end = len(lines)
        # 找下一个同级或更高级标题（数字越小级别越高）
        for j in range(idx + 1, len(headings)):
            if headings[j][0] <= level:
                end = headings[j][2]
                break
        ranges[title] = (start, end)

    return ranges


def _strip_trailing_separator(text: str) -> str:
    """去掉尾部多余的 --- 分隔线。"""
    return re.sub(r'\n---+\s*$', '', text)


def _extract_section(content: str, section_name: str) -> Optional[str]:
    """从 markdown 内容中提取指定章节。

    返回章节内容（含标题行），不含尾部分隔线。
    若章节不存在返回 None。
    """
    lines = content.split('\n')
    ranges = _find_heading_ranges(lines)
    canonical_section = _normalize_section_name(section_name)

    # 直接标题匹配
    if section_name in ranges:
        start, end = ranges[section_name]
        return _strip_trailing_separator('\n'.join(lines[:3] + [''] + lines[start:end]))

    # 通过 SECTION_KEYS 映射查找
    target_title = SECTION_KEYS.get(canonical_section)
    if target_title and target_title in ranges:
        start, end = ranges[target_title]
        return _strip_trailing_separator('\n'.join(lines[:3] + [''] + lines[start:end]))

    return None


def _extract_meta_section(content: str, meta_name: str, ranges: Dict[str, Tuple[int, int]]) -> Optional[str]:
    """提取元章节（多个标题的组合）。"""
    keys = META_SECTIONS.get(_normalize_section_name(meta_name))
    if not keys:
        return None

    lines = content.split('\n')
    parts: List[str] = []

    for key in keys:
        title = SECTION_KEYS.get(key)
        if title and title in ranges:
            start, end = ranges[title]
            parts.append('\n'.join(lines[start:end]))

    if not parts:
        return None

    # 用分隔线拼接各部分，前面加 title block
    header = '\n'.join(lines[:3])
    body = '\n\n---\n\n'.join(parts)
    return _strip_trailing_separator(header + '\n\n' + body)


def _list_available_sections(content: str) -> str:
    """生成可用章节列表。"""
    lines = content.split('\n')
    ranges = _find_heading_ranges(lines)

    available = []
    for title in sorted(ranges.keys()):
        # 只暴露 ## 级别的顶级章节和 ### 级别的审核子章节
        if title in TITLE_TO_KEY:
            key = TITLE_TO_KEY[title]
            available.append(f"  `{key}` → {title}")

    lines_out = ["可用章节（传给 section 参数）:", ""]
    lines_out.append("【顶级章节】")
    for item in available:
        if not any(item.startswith(f"  `{t}`") for t in TITLE_TO_KEY.values()
                   if t not in ('一致性', '完整性', '资源泄露', 'Delphi 特有陷阱',
                                '常见错误模式', '代码质量', '数据转换', '安全', '性能')):
            # 顶级章节
            pass
    # Simpler: just list by section key category
    lines_out.append("  基础流程: planning, workflow, env, kb_search, writing, format, compile, cleanup, review_guide")
    lines_out.append("  审核细化: review(合集), consistency, completeness, resource_leak, delphi_specific,")
    lines_out.append("           common_errors, code_quality, data_conversion, safety, performance")
    lines_out.append("  writing 子章节: delphi_file_write_rule, delphi_file_dirty_flag, delphi_file_output_format,")
    lines_out.append("                 delphi_file_usage_tips")
    lines_out.append("  其他:     review_detail, kb_build, agent_rules, human_collab, experience, maintenance, automation, ui-testing, ui_layout, console-testing")
    lines_out.append("  组合:     review(审核指南+审核表), coding(写代码+格式化+compile)")
    lines_out.append("  兼容别名: kb-search/kb-rebuild/agent-rules/human-collab/delphi-file-rules")
    lines_out.append("")
    lines_out.append("不传 section 则返回工作流总览 + 章节索引。")

    return '\n'.join(lines_out)


async def get_coding_rules(
    project_path: Optional[str] = None,
    section: Optional[str] = None
) -> CallToolResult:
    """
    获取 Delphi 源码编码规则，支持按章节分段获取。

    默认读取 src/resources/coding-rules/ 目录（合并所有 .md 文件）。
    如果用户项目目录下存在 CODING_RULES.mdc，则合并用户规则（用户规则覆盖默认规则）

    Args:
        project_path: 项目路径（可选），用于查找用户自定义的编码规则文件
        section: 章节名称（可选），如 "workflow"、"writing"、"review" 等。
                 不传或传 None 时返回工作流总览 + 章节索引，引导按需获取。
                 传 "list" 返回可用章节列表。

    Returns:
        编码规则内容
    """
    logger.info(f"获取编码规则请求 — project_path={project_path}, section={section}")

    try:
        # 读取默认编码规则
        default_rules, default_rules_path = _read_first_existing_text(
            _default_rules_candidates(),
            "默认编码规则文件",
        )
        if default_rules_path and default_rules:
            logger.info(f"成功读取默认编码规则文件: {default_rules_path}")
        elif default_rules_path:
            logger.warning(f"默认编码规则文件为空或读取失败: {default_rules_path}")
        else:
            logger.warning("默认编码规则目录不存在: src/resources/coding-rules/")

        # 如果提供了项目路径，尝试读取用户自定义的编码规则
        user_rules = ""
        if project_path:
            project_dir = Path(project_path)
            user_rules_path = project_dir / "CODING_RULES.mdc"

            if user_rules_path.exists():
                try:
                    with open(user_rules_path, 'r', encoding='utf-8') as f:
                        user_rules = f.read()
                    logger.info(f"成功读取用户自定义编码规则文件: {user_rules_path}")
                except Exception as e:
                    logger.error(f"读取用户自定义编码规则文件失败: {str(e)}")
                    user_rules = ""
            else:
                logger.info(f"用户项目目录下未找到自定义编码规则文件: {user_rules_path}")

        # 合并规则：默认规则做底，用户规则覆盖
        merged = ""
        if default_rules:
            merged += "# ═══════════════════════════════════\n"
            merged += "# 默认编码规则\n"
            merged += "# ═══════════════════════════════════\n"
            merged += default_rules
            if user_rules:
                merged += "\n\n"
                merged += "# ═══════════════════════════════════\n"
                merged += "# 用户自定义规则（覆盖上方同名规则）\n"
                merged += "# ═══════════════════════════════════\n"
                merged += user_rules
        elif user_rules:
            merged = user_rules

        if not merged:
            logger.warning("未找到任何编码规则文件")
            return CallToolResult(
                content=[{"type": "text", "text": "未找到任何编码规则文件"}],
                isError=True
            )

        # 特殊章节：section="automation" → 从 resources/automation/ 读取
        if section and _normalize_section_name(section) == "automation":
            automation_index = Path(__file__).parent.parent / "resources" / "automation" / "index.md"
            if automation_index.exists():
                try:
                    text = automation_index.read_text(encoding="utf-8")
                    logger.info("返回自动化测试章节（来自 resources/automation/index.md）")
                    return CallToolResult(content=[{"type": "text", "text": text}])
                except Exception as e:
                    logger.error(f"读取自动化索引失败: {str(e)}")
                    # fall through to default handling

        # section 参数处理
        if section == "list":
            output = _list_available_sections(merged)
            return CallToolResult(content=[{"type": "text", "text": output}])

        if section:
            canonical_section = _normalize_section_name(section)
            # 先查元章节
            lines = merged.split('\n')
            ranges = _find_heading_ranges(lines)
            meta_content = _extract_meta_section(merged, canonical_section, ranges)
            if meta_content:
                logger.info(f"返回元章节: {canonical_section}")
                return CallToolResult(content=[{"type": "text", "text": meta_content}])

            # 再查单章节
            section_content = _extract_section(merged, canonical_section)
            if section_content:
                logger.info(f"返回章节: {canonical_section}")
                source = "默认规则 + 用户规则（用户覆盖默认）" if default_rules and user_rules else \
                         "用户规则" if user_rules else "默认规则"
                output = f"编码规则 (来源: {source}, 章节: {canonical_section}):\n\n"
                output += section_content
                return CallToolResult(content=[{"type": "text", "text": output}])

            # 未找到章节
            logger.warning(f"未知章节: {section}")
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"未知章节: '{section}'。\n\n{_list_available_sections(merged)}"
                )],
                isError=True
            )

        # section=None：返回工作流总览 + 章节索引，引导按需获取
        logger.info("返回工作流 + 章节索引（默认模式）")

        # 提取工作流总览章节
        workflow_content = _extract_section(merged, "工作流总览")
        workflow_part = workflow_content if workflow_content else ""

        # 生成章节索引
        index_lines = [
            "",
            "## 章节索引",
            "",
            "按需获取各章节详情（节省 token，提升遵守率）：",
            "",
            "| 参数 | 内容 | 使用时机 |",
            "|------|------|----------|",
             "| `section=\"planning\"` | P0 前置计划与审查 | 新功能/大规模修改编码前必做 |",
             "| `section=\"workflow\"` | 工作流总览 | 任务开始，了解整体流程 |",
            "| `section=\"env\"` | ① 环境检查 | 首次运行/环境异常时 |",
            "| `section=\"kb_search\"` | ② KB 搜索 | 编码前查 API 定义 |",
             "| `section=\"writing\"` | ③ 写 Delphi 代码（命名/格式/泛型/异步/代码组织/版本兼容/自动备份/写入规则） | 编码阶段 |",
            "| `section=\"format\"` | ④ 格式化 | 格式化代码 |",
            "| `section=\"compile\"` | ⑤ 编译 | 编译验证 |",
             "| `section=\"review\"` | ⑦ 代码审核（含完整审核表） | 清理后审查最终代码质量 |",
             "| `section=\"cleanup\"` | ⑥ 清理 | 编译通过后先清理冗余 |",
            "| `section=\"safety\"` | 安全规则 | 涉及安全敏感操作时 |",
            "| `section=\"performance\"` | 性能规则 | 性能敏感路径 |",
             "| `section=\"agent_rules\"` | Agent 操作硬规则 | 执行脚本或操作文件时 |",
             "| `section=\"human_collab\"` | 人机协同 — 异常诊断与人工介入 | 异常诊断或需要人工介入时（任意步骤可触发） |",
             "| `section=\"experience\"` | ⑪ 经验沉淀 — 知识沉淀到经验库 | 问题解决后保存经验时 |",
            "| `section=\"kb_build\"` | 知识库重建 | 需要重建 KB 时 |",
             "| `section=\"automation\"` | ⚙ 自动化测试架构（含提示词模板F + 经验优化闭环G） | 执行自动化 UI 测试前，规划测试计划/恢复策略 |",
             "| `section=\"ui-testing\"` | ⑧ 自动化 UI 交互测试 | GUI 程序编译通过后，UI 交互验证 |",
             "| `section=\"ui_layout\"` | UI 布局规范与审计 | AI 生成或修改 Delphi 窗体后检查布局质量 |",
             "| `section=\"console-testing\"` | ⑨ 控制台程序交互验证 | Console 程序编译后，stdin/stdout 验证 |",
             "| `section=\"coding\"` | 组合：writing + format + compile | 完整编码流程 |",
             "| `section=\"delphi_file_write_rule\"` | delphi_file 写入规则（1-indexed/edits 参数） | 编辑 Delphi 文件需了解行号规则时 |",
             "",
             "也可获取细分章节：planning, consistency, completeness, resource_leak, delphi_specific, common_errors,",
             "code_quality, data_conversion, safety, performance, delphi_file_write_rule,",
             "delphi_file_dirty_flag, delphi_file_output_format, delphi_file_usage_tips, human_collab, experience, maintenance,",
             "ui-testing, ui_layout, console-testing",
            "",
            "使用示例：",
            "```python",
            'get_coding_rules(section="writing")    # 只看编码规则',
            'get_coding_rules(section="review")     # 只看审核表',
            'get_coding_rules(section="safety")     # 只看安全规则',
            'get_coding_rules(section="list")       # 列出所有章节',
            "```",
        ]
        index_text = "\n".join(index_lines)

        output = workflow_part + "\n" + index_text
        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        error_msg = f"获取编码规则过程发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )
