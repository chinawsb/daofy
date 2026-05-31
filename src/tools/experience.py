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
        elif action == "merge":
            return _act_merge(svc, **kwargs)
        elif action == "prune":
            return _act_prune(svc, **kwargs)
        elif action == "delete":
            return _act_delete(svc, **kwargs)
        else:
            return _err(f"未知 action: {action}，可用: save/search/get/list/update/merge/prune/delete")
    except Exception as e:
        logger.exception("experience 执行失败")
        return _err(str(e))


def _ok(msg: str, data: Any = None) -> dict:
    result = {"status": "ok", "message": msg}
    if data is not None:
        result["data"] = data
    return result


def _err(msg: str) -> dict:
    return {"status": "failed", "message": msg}


def _fmt_experience(exp: dict) -> str:
    """格式化单条经验为可读文本"""
    tags = exp.get("tags", [])
    tools = exp.get("tools_used", [])
    sim = exp.get("similarity")
    lines = [
        f"ID: {exp['id']}",
        f"problem: {exp['problem']}",
        f"solution: {exp['solution']}",
    ]
    if tags:
        lines.append(f"tags: {', '.join(tags)}")
    if tools:
        lines.append(f"tools: {', '.join(tools)}")
    if sim is not None:
        lines.append(f"match: {sim:.2%}")
    lines.append(f"used: {exp.get('hit_count', 0)}x")
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
        f"saved\n  ID: {result['id']}\n  problem: {problem[:80]}",
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
        return _ok(f"no results (query: {query})", data=[])

    lines = [f"{len(results)} results:"]
    for exp in results:
        sim = exp.get("similarity", 0)
        sim_str = f" [match:{sim:.2%}]" if sim else ""
        lines.append("")
        lines.append(f"{exp['problem']}{sim_str}")
        lines.append(f"  ID: {exp['id']}")
        lines.append(f"  solution: {exp['solution'][:200]}")
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

    return _ok(f"detail:\n{_fmt_experience(result)}", data=result)


def _act_list(svc, **kw):
    tags = kw.get("tags")
    sort_by = kw.get("sort_by", "updated_at")
    limit = int(kw.get("limit", 20))

    results = svc.list(tags=tags, sort_by=sort_by, limit=limit)
    if not results:
        return _ok("no records", data=[])

    lines = [f"{len(results)} records:"]
    for exp in results:
        tags_str = f" [{', '.join(exp.get('tags', []))}]" if exp.get("tags") else ""
        lines.append(f"  - {exp['problem'][:60]} - used {exp.get('hit_count', 1)}x{tags_str}")

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

    return _ok(f"updated: {exp_id}", data=result)


def _act_merge(svc, **kw):
    ids = kw.get("ids")
    if not ids or not isinstance(ids, list) or len(ids) < 2:
        return _err("缺少必需参数: ids(至少2个经验ID列表，如 ids=['a','b'])")
    ids = [i.strip() for i in ids if i.strip()]
    keep = kw.get("keep")
    result = svc.merge(ids, keep=keep)
    if result is None:
        return _err("合并失败，请检查 IDs 是否有效")
    return _ok(f"merged {len(ids)} records into {result['id']}", data=result)


def _act_prune(svc, **kw):
    limit = int(kw.get("limit", 20))
    results = svc.prune_list(limit=limit)
    if not results:
        return _ok("no stale records found", data=[])
    lines = [f"{len(results)} low-value records (ascending value):"]
    for r in results:
        tags_str = f" [{', '.join(r.get('tags', []))}]" if r.get("tags") else ""
        lines.append(
            f"  value={r['value']:.3f}  hits={r['hit_count']}  "
            f"{r['problem'][:60]}{tags_str}"
        )
    return _ok("\n".join(lines), data=results)


def _act_delete(svc, **kw):
    exp_id = kw.get("id", "").strip()
    if not exp_id:
        return _err("缺少必需参数: id(经验ID)")

    ok = svc.delete(exp_id)
    if not ok:
        return _err(f"经验不存在: {exp_id}")

    return _ok(f"deleted: {exp_id}")
