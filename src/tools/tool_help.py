"""
tool_help MCP 工具 — 按工具名返回完整帮助文档

用于替代将详细文档塞入 tool description 的做法。
AI Agent 不确定某工具用法时，调用此工具按需获取全量帮助。
"""

from typing import Any
from ..config.tool_docs import TOOL_HELP_DOCS

import logging
logger = logging.getLogger(__name__)


def get_tool_help(tool_name: str) -> dict:
    """获取单个工具的完整帮助文档。

    Args:
        tool_name: 工具名，如 compile_project / delphi_file

    Returns:
        dict: {"tool": name, "docs": {...}} 或 {"error": "..."}
    """
    docs = TOOL_HELP_DOCS.get(tool_name)
    if not docs:
        available = ", ".join(sorted(TOOL_HELP_DOCS.keys()))
        return {
            "status": "failed",
            "message": f"未知工具: {tool_name}。可用工具: {available}",
        }

    # 格式化为可读文本
    lines = [f"📘 {tool_name} — {docs.get('description', '')}", ""]

    if docs.get("triggers"):
        triggers = "; ".join(docs["triggers"])
        lines.append(f"触发词: {triggers}")
        lines.append("")

    if docs.get("file_triggers"):
        ft = docs["file_triggers"]
        if isinstance(ft, list):
            for item in ft:
                lines.append(f"⚠️  {item}")
        else:
            lines.append(f"⚠️  {ft}")
        lines.append("")

    constraints = docs.get("constraints", [])
    if constraints:
        for c in constraints:
            lines.append(c)
        lines.append("")

    auto_paths = docs.get("auto_unit_paths", [])
    if auto_paths:
        lines.append("DaofyAutomation 单元选择（根据框架类型选其一）:")
        for p in auto_paths:
            lines.append(f"  • {p}")
        lines.append("")

    if docs.get("features"):
        lines.append("功能特性:")
        for f in docs["features"]:
            lines.append(f"  ✅ {f}")
        lines.append("")

    if docs.get("sync_rules"):
        lines.append("同步规则:")
        for r in docs["sync_rules"]:
            lines.append(f"  {r}")
        lines.append("")

    if docs.get("actions"):
        lines.append("操作说明 (action):")
        acts = docs["actions"]
        if isinstance(acts, dict):
            # 优先按分组展示
            for key, val in acts.items():
                if isinstance(val, dict):
                    lines.append(f"  ▶ {key}:")
                    for sub_k, sub_v in val.items():
                        lines.append(f"    {sub_k} — {sub_v}")
                else:
                    lines.append(f"  {key} — {val}")
        lines.append("")

    if docs.get("action_params"):
        lines.append("各 action 参数说明（先 tool_help 再调用）：")
        lines.append("")
        for act_name, act_info in docs["action_params"].items():
            desc = act_info.get("description", "")
            lines.append(f"  ▶ {act_name}: {desc}")
            req = act_info.get("required", [])
            if req:
                lines.append(f"    必需参数: {', '.join(req)}")
            opt = act_info.get("optional", {})
            if opt:
                lines.append("    可选参数:")
                for pname, pdesc in opt.items():
                    lines.append(f"      {pname}: {pdesc}")
            ex = act_info.get("examples", [])
            if ex:
                lines.append("    示例:")
                for e in ex:
                    lines.append(f"      {e}")
            lines.append("")

    if docs.get("workflow_hints"):
        lines.append("常用工作流:")
        for name, flow in docs["workflow_hints"].items():
            lines.append(f"  {name}: {flow}")
        lines.append("")

    if docs.get("modes"):
        lines.append("运行模式:")
        for mode_name, mode_desc in docs["modes"].items():
            lines.append(f"  {mode_name}: {mode_desc}")
        lines.append("")

    if docs.get("workflow"):
        lines.append(f"协作链: {docs['workflow']}")
        lines.append("")

    if docs.get("fallback"):
        lines.append(f"降级策略: {docs['fallback']}")
        lines.append("")

    if docs.get("section_guide"):
        lines.append("章节说明 (section):")
        for sec_name, sec_desc in docs["section_guide"].items():
            lines.append(f"  {sec_name} — {sec_desc}")
        lines.append("")
    if docs.get("default_section"):
        lines.append(docs["default_section"])
        lines.append("")

    if docs.get("platforms"):
        lines.append("支持平台:")
        for plat_name, plat_desc in docs["platforms"].items():
            lines.append(f"  {plat_name}: {plat_desc}")
        lines.append("")

    if docs.get("china_access"):
        lines.append(f"国内访问: {docs['china_access']}")
        lines.append("")

    if docs.get("details"):
        lines.append(docs["details"])
        lines.append("")

    if docs.get("notes"):
        lines.append(docs["notes"])
        lines.append("")

    if docs.get("push_notification"):
        lines.append(f"推送通知: {docs['push_notification']}")
        lines.append("")

    if docs.get("usage"):
        lines.append(docs["usage"])
        lines.append("")

    if docs.get("examples"):
        lines.append("示例:")
        for ex in docs["examples"]:
            lines.append(f"  {ex}")
        lines.append("")

    text = "\n".join(lines)
    return {"status": "ok", "tool": tool_name, "help": text}
