"""
experience MCP 工具 — 经验记忆管理

通过 action 参数分派操作，语义搜索复用 embedding_service。
"""

from typing import Any, Optional
from ..services.experience_service import get_experience_service

import logging
logger = logging.getLogger(__name__)


def experience(**kwargs) -> dict:
    """经验记忆工具统一入口。

    通过 action 参数分派到具体操作。

    Args:
        action: 操作类型
        **kwargs: 各操作的参数

    Returns:
        dict: 结果
    """
    action = kwargs.pop("action", "")
    svc = get_experience_service()

    try:
        if action == "save":
            return _act_save(svc, **kwargs)
        elif action == "search":
            return _act_search(svc, **kwargs)
        elif action == "get":
            return _act_get(svc, **kwargs)
        elif action == "list":
            return _act_list(svc, **kwargs)
        elif action == "update":
            return _act_update(svc, **kwargs)
        elif action == "delete":
            return _act_delete(svc, **kwargs)
        else:
            return _err(f"未知 action: {action}，可用: save/search/get/list/update/delete")
    except Exception as e:
        logger.exception("experience 执行失败")
        return _err(str(e))


def _ok(msg: str, data: Any = None) -> dict:
    result = {"status": "ok", "message": msg}
    if data is not None:
        result["data"] = data
    return result


def _err(msg: str) -> dict:
    return {"status": "failed", "message": f"❌ {msg}"}


def _fmt_experience(exp: dict) -> str:
    """格式化单条经验为可读文本"""
    tags = exp.get("tags", [])
    tools = exp.get("tools_used", [])
    sim = exp.get("similarity")
    lines = [
        f"ID: {exp['id']}",
        f"问题: {exp['problem']}",
        f"解决: {exp['solution']}",
    ]
    if tags:
        lines.append(f"标签: {', '.join(tags)}")
    if tools:
        lines.append(f"用到的工具: {', '.join(tools)}")
    if sim is not None:
        lines.append(f"匹配度: {sim:.2%}")
    lines.append(f"复用次数: {exp.get('hit_count', 0)}")
    return "\n".join(lines)


# ── Action handlers ──


def _act_save(svc, **kw):
    problem = kw.get("problem", "").strip()
    solution = kw.get("solution", "").strip()
    if not problem or not solution:
        return _err("缺少必需参数: problem(问题描述) 和 solution(解决步骤)")

    tools_used = kw.get("tools_used")
    context = kw.get("context")
    tags = kw.get("tags")

    result = svc.save(
        problem=problem,
        solution=solution,
        tools_used=tools_used,
        context=context,
        tags=tags,
    )
    return _ok(
        f"✅ 经验已保存\n  ID: {result['id']}\n  问题: {problem[:80]}",
        data=result,
    )


def _act_search(svc, **kw):
    query = kw.get("query", "").strip()
    if not query:
        return _err("缺少必需参数: query(搜索关键词)")

    top_k = int(kw.get("top_k", 5))
    tags = kw.get("tags")

    results = svc.search(query=query, top_k=top_k, tags=tags)
    if not results:
        return _ok(f"📭 未找到相关经验 (query: {query})", data=[])

    lines = [f"📋 找到 {len(results)} 条相关经验:"]
    for exp in results:
        sim = exp.get("similarity", 0)
        sim_str = f" [匹配度: {sim:.2%}]" if sim else ""
        lines.append("")
        lines.append(f"▶ {exp['problem']}{sim_str}")
        lines.append(f"  ID: {exp['id']}")
        lines.append(f"  解决: {exp['solution'][:200]}")
        if exp.get("tags"):
            lines.append(f"  标签: {', '.join(exp['tags'])}")

    return _ok("\n".join(lines), data=results)


def _act_get(svc, **kw):
    exp_id = kw.get("id", "").strip()
    if not exp_id:
        return _err("缺少必需参数: id(经验ID)")

    result = svc.get(exp_id)
    if result is None:
        return _err(f"经验不存在: {exp_id}")

    return _ok(f"📘 经验详情:\n{_fmt_experience(result)}", data=result)


def _act_list(svc, **kw):
    tags = kw.get("tags")
    sort_by = kw.get("sort_by", "updated_at")
    limit = int(kw.get("limit", 20))

    results = svc.list(tags=tags, sort_by=sort_by, limit=limit)
    if not results:
        return _ok("📭 暂无经验记录", data=[])

    lines = [f"📋 共 {len(results)} 条经验:"]
    for exp in results:
        tags_str = f" [{', '.join(exp.get('tags', []))}]" if exp.get("tags") else ""
        lines.append(f"  • {exp['problem'][:60]} — 复用{exp.get('hit_count', 1)}次{tags_str}")

    return _ok("\n".join(lines), data=results)


def _act_update(svc, **kw):
    exp_id = kw.get("id", "").strip()
    if not exp_id:
        return _err("缺少必需参数: id(经验ID)")

    solution = kw.get("solution")
    tags = kw.get("tags")
    problem = kw.get("problem")

    if solution is None and tags is None and problem is None:
        return _err("至少需要提供一项更新内容: solution/tags/problem")

    result = svc.update(exp_id=exp_id, solution=solution, tags=tags, problem=problem)
    if result is None:
        return _err(f"经验不存在: {exp_id}")

    return _ok(f"✅ 经验已更新: {exp_id}", data=result)


def _act_delete(svc, **kw):
    exp_id = kw.get("id", "").strip()
    if not exp_id:
        return _err("缺少必需参数: id(经验ID)")

    ok = svc.delete(exp_id)
    if not ok:
        return _err(f"经验不存在: {exp_id}")

    return _ok(f"🗑️ 经验已删除: {exp_id}")
