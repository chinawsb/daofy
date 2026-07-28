"""
experience MCP 工具 — 经验记忆管理

通过 action 参数分派操作，语义搜索复用 embedding_service。

新增 suggest action: 分析最近工具调用历史，自动检测经验保存机会，
预填 problem/solution/tags/context 草稿，供 AI 审核后 save。
"""

import json
from typing import Any, Optional
from ..services.experience_service import get_experience_service
from ..services.experience_tracker import get_tracker

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
        elif action == "rebuild_embedding":
            return _act_rebuild_embedding(svc, **kwargs)
        elif action == "suggest":
            return _act_suggest(**kwargs)
        else:
            return _err(f"未知 action: {action}，可用: save/search/get/list/update/merge/prune/delete/rebuild_embedding/suggest")
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

    # 保存前搜索相似经验，提醒 AI 泛化
    # 注意：svc.save() 内部也会做 >0.85 去重合并，这里的 >0.7 检查是额外提醒层
    # 如果用户不 force，则返回警告并终止保存（让 AI 选择 merge/update）
    # 如果用户 force=true，则跳过提醒，让 svc.save() 的 >0.85 逻辑处理最终去重
    _force = kw.get("force", False)
    if not _force:
        try:
            similar = svc.search(query=problem, top_k=3)
            high_match = [s for s in similar if s.get("similarity", 0) > 0.7]
            if high_match:
                lines = ["⚠️ 发现高相似度经验，建议用 merge/update 合并而非另存："]
                for s in high_match:
                    lines.append(f"  [{s['similarity']:.0%}] {s['id']} {s['problem'][:60]}")
                lines.append("如需确认后合并，取消本次 save，改用:")
                best_id = high_match[0]['id']
                lines.append(f'  experience(action=merge, ids=["...", "{best_id}"]')
                lines.append(f'  或 experience(action=update, id="{best_id}", ...)')
                lines.append("如仍需新保存，设置 force=true 跳过此检查")
                return _ok("\n".join(lines), data={"similar": [s["id"] for s in high_match]})
        except Exception as e:
            logger.debug("经验去重搜索失败（不影响保存流程）: %s", e)


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


def _act_rebuild_embedding(svc, **kw):
    result = svc.rebuild_embeddings()
    if "error" in result:
        return _err(result["error"])
    lines = [f"经验 embedding 重建完成:"]
    lines.append(f"  总记录: {result['total']}")
    lines.append(f"  已有向量: {result['skipped']}")
    lines.append(f"  本次重建: {result['rebuilt']}")
    lines.append(f"  失败: {result['failed']}")
    return _ok("\n".join(lines), data=result)


def _act_suggest(**kw) -> dict:
    """分析最近工具调用历史，自动检测经验保存机会，预填草稿。

    返回预填的 problem/solution/tags/context，供 AI 审核后
    调用 experience(action="save", ...) 正式保存。
    """
    tracker = get_tracker()
    draft = tracker.suggest()
    if draft is None:
        return _ok(
            "未检测到值得保存的经验。\n"
            "  suggest 需要 2+ 次工具调用，且检测到以下模式之一：\n"
            "  - fix_cycle:  编译失败 → 修改代码 → 编译成功\n"
            "  - learn_apply: 查知识库 → 修改代码 → 编译成功\n"
            "  - clean_fix:  修改代码 → 编译成功（无前置失败）"
        )

    # 格式化输出
    lines = [
        "📋 检测到经验保存机会，审核后可用以下命令保存：",
        "",
        f"experience(action=\"save\",",
        f'  problem="""{draft["problem"]}""",',
        f'  solution="""{draft["solution"]}""",',
        f'  tags={json.dumps(draft["tags"], ensure_ascii=False)},',
        f'  context={json.dumps(draft["context"], ensure_ascii=False)},',
        f'  force=true',
        f")",
    ]
    note = (
        "\n💡 建议：审核后泛化 problem 描述（去掉 auto 标记、"
        "抽象通用场景），可用 force=true 跳过 >0.7 去重提醒层。"
    )

    return _ok(
        "\n".join(lines) + note,
        data=draft,
    )
