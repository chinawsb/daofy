"""
编码规则工具

提供 Delphi 源码编码规则查询功能，支持按章节分段获取，
减少 token 消耗并提升 AI Agent 的规则遵守率。
"""

import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from mcp.types import CallToolResult, TextContent
from ..utils.logger import get_logger

logger = get_logger(__name__)

# 章节名称映射：短键 → Markdown 标题（## 或 ###）
SECTION_KEYS: Dict[str, str] = {
    "workflow": "工作流总览",
    "env": "① 环境检查",
    "kb_search": "② KB 搜索（编码前必做）",
    "writing": "③ 写 Delphi 代码",
    "format": "④ 格式化",
    "compile": "⑤ 编译",
    "review_guide": "⑥ 代码审核",
    "cleanup": "⑦ 清理 & 验证",
    "review_detail": "审核",
    "kb_build": "知识库重建",
    "agent_rules": "Agent 操作硬规则",
    "human_collab": "⑧ 人机协同 — 异常诊断与人工介入",
    "experience": "⑨ 经验保存 — 将知识沉淀到经验知识库",
    "maintenance": "⑩ 规则维护",
    "automation": "⚙ 自动化测试架构 — 感知·规划·执行·反馈循环",
    # ③ 写 Delphi 代码 内的子章节
    "delphi_file_write_rule": "delphi_file 写入规则",
    "delphi_file_dirty_flag": "连续编辑与脏标记保护（v2026.06.12+）",
    "delphi_file_output_format": "delphi_file 紧凑输出格式（v2026.06.12+）",
    "delphi_file_usage_tips": "write 使用建议",
    # 审核子章节（### 级别）
    "consistency": "一致性",
    "completeness": "完整性",
    "resource_leak": "资源泄露",
    "delphi_specific": "Delphi 特有",
    "common_errors": "常见错误模式",
    "code_quality": "代码质量",
    "data_conversion": "数据转换",
    "safety": "安全",
    "performance": "性能",
}

# 元章节：组合多个相关标题一起返回
META_SECTIONS: Dict[str, List[str]] = {
    "review": ["review_guide", "review_detail"],
    "coding": ["writing", "format", "compile"],
}

# 反向映射：标题 → 短键（用于错误提示）
TITLE_TO_KEY = {v: k for k, v in SECTION_KEYS.items()}


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

    # 直接标题匹配
    if section_name in ranges:
        start, end = ranges[section_name]
        return _strip_trailing_separator('\n'.join(lines[:3] + [''] + lines[start:end]))

    # 通过 SECTION_KEYS 映射查找
    target_title = SECTION_KEYS.get(section_name)
    if target_title and target_title in ranges:
        start, end = ranges[target_title]
        return _strip_trailing_separator('\n'.join(lines[:3] + [''] + lines[start:end]))

    return None


def _extract_meta_section(content: str, meta_name: str, ranges: Dict[str, Tuple[int, int]]) -> Optional[str]:
    """提取元章节（多个标题的组合）。"""
    keys = META_SECTIONS.get(meta_name)
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
                   if t not in ('一致性', '完整性', '资源泄露', 'Delphi 特有',
                                '常见错误模式', '代码质量', '数据转换', '安全', '性能')):
            # 顶级章节
            pass
    # Simpler: just list by section key category
    lines_out.append("  基础流程: workflow, env, kb_search, writing, format, compile, review_guide, cleanup")
    lines_out.append("  审核细化: review(合集), consistency, completeness, resource_leak, delphi_specific,")
    lines_out.append("           common_errors, code_quality, data_conversion, safety, performance")
    lines_out.append("  writing 子章节: delphi_file_write_rule, delphi_file_dirty_flag, delphi_file_output_format,")
    lines_out.append("                 delphi_file_usage_tips")
    lines_out.append("  其他:     review_detail, kb_build, agent_rules, human_collab, experience, maintenance, automation")
    lines_out.append("  组合:     review(审核指南+审核表), coding(写代码+格式化+compile)")
    lines_out.append("")
    lines_out.append("不传 section 则返回全部内容（向后兼容）。")

    return '\n'.join(lines_out)


async def get_coding_rules(
    project_path: Optional[str] = None,
    section: Optional[str] = None
) -> CallToolResult:
    """
    获取 Delphi 源码编码规则，支持按章节分段获取。

    默认读取 config/CODING_RULES.mdc 文件，
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
        # 获取默认编码规则文件路径
        current_dir = Path(__file__).parent.parent.parent
        default_rules_path = current_dir / "config" / "CODING_RULES.mdc"

        # 读取默认编码规则
        default_rules = ""
        if default_rules_path.exists():
            try:
                with open(default_rules_path, 'r', encoding='utf-8') as f:
                    default_rules = f.read()
                logger.info(f"成功读取默认编码规则文件: {default_rules_path}")
            except Exception as e:
                logger.error(f"读取默认编码规则文件失败: {str(e)}")
                default_rules = ""
        else:
            logger.warning(f"默认编码规则文件不存在: {default_rules_path}")

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

        # section 参数处理
        if section == "list":
            output = _list_available_sections(merged)
            return CallToolResult(content=[{"type": "text", "text": output}])

        if section:
            # 先查元章节
            lines = merged.split('\n')
            ranges = _find_heading_ranges(lines)
            meta_content = _extract_meta_section(merged, section, ranges)
            if meta_content:
                logger.info(f"返回元章节: {section}")
                return CallToolResult(content=[{"type": "text", "text": meta_content}])

            # 再查单章节
            section_content = _extract_section(merged, section)
            if section_content:
                logger.info(f"返回章节: {section}")
                source = "默认规则 + 用户规则（用户覆盖默认）" if default_rules and user_rules else \
                         "用户规则" if user_rules else "默认规则"
                output = f"编码规则 (来源: {source}, 章节: {section}):\n\n"
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
            "| `section=\"workflow\"` | 工作流总览 | 任务开始，了解整体流程 |",
            "| `section=\"env\"` | ① 环境检查 | 首次运行/环境异常时 |",
            "| `section=\"kb_search\"` | ② KB 搜索 | 编码前查 API 定义 |",
             "| `section=\"writing\"` | ③ 写 Delphi 代码（命名/格式/泛型/异步/代码组织/版本兼容/自动备份/写入规则） | 编码阶段 |",
            "| `section=\"format\"` | ④ 格式化 | 格式化代码 |",
            "| `section=\"compile\"` | ⑤ 编译 | 编译验证 |",
            "| `section=\"review\"` | ⑥ 代码审核（含完整审核表） | 编译通过后审查代码 |",
            "| `section=\"cleanup\"` | ⑦ 清理 | 最终清理 |",
            "| `section=\"safety\"` | 安全规则 | 涉及安全敏感操作时 |",
            "| `section=\"performance\"` | 性能规则 | 性能敏感路径 |",
             "| `section=\"agent_rules\"` | Agent 操作硬规则 | 执行脚本或操作文件时 |",
             "| `section=\"human_collab\"` | ⑧ 人机协同 — 异常诊断与人工介入 | 异常诊断或需要人工介入时 |",
             "| `section=\"experience\"` | ⑨ 经验保存 — 知识沉淀到经验库 | 问题解决后保存经验时 |",
            "| `section=\"kb_build\"` | 知识库重建 | 需要重建 KB 时 |",
             "| `section=\"automation\"` | ⚙ 自动化测试架构（含提示词模板F + 经验优化闭环G） | 执行自动化 UI 测试前，规划测试计划/恢复策略 |",
             "| `section=\"coding\"` | 组合：writing + format + compile | 完整编码流程 |",
             "| `section=\"delphi_file_write_rule\"` | delphi_file 写入规则（1-indexed/edits 参数） | 编辑 Delphi 文件需了解行号规则时 |",
             "",
             "也可获取细分章节：consistency, completeness, resource_leak, delphi_specific, common_errors,",
             "code_quality, data_conversion, safety, performance, delphi_file_write_rule,",
             "delphi_file_dirty_flag, delphi_file_output_format, delphi_file_usage_tips, human_collab, experience, maintenance",
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
