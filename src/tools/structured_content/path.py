"""
JSONPath 查询引擎 — 在 StructuredNode 树上执行简化的 JSONPath 表达式。

支持的语法子集:
  $               根节点
  .key            按键名访问子节点
  ["key"]         方括号键名
  [N]             数组索引
  [*]             通配（所有子节点或数组元素）
  ..key           递归下降查找
  [?(expr)]       过滤表达式（简化: @.key op val）

不支持（后续按需）:
  切片 [start:end:step]
  多键 ["a","b"]
  脚本表达式
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .schema import StructuredNode


# ── Tokenise ─────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(
    r"""
    \$                                           # root
    |\.\.(?P<descendant>[a-zA-Z_][\w]*)         # ..key (recursive descent)
    |\.(?P<dotkey>[a-zA-Z_][\w]*)               # .key (direct child)
    |\[\s*(?P<bracket>\*|[0-9]+)\s*\]            # [*] or [N]
    |\[\s*\?\s*\((?P<filter>[^)]*)\)\s*\]        # [?(expr)]
    |\["(?P<qkey>[^"]+)"\]                       # ["key"]
    """,
    re.VERBOSE,
)


def _tokenise(expression: str) -> list[tuple[str, str]]:
    """解析 JSONPath 表达式为 tokens 列表: (type, value)。"""
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(expression):
        # 跳过空白
        if expression[pos] in " \t\r\n":
            pos += 1
            continue

        m = _TOKEN_RE.match(expression, pos)
        if m is None:
            raise ValueError(f"无法解析 JSONPath 位置 {pos}: {expression[pos:]!r}")

        if m.group() == "$":
            tokens.append(("root", "$"))
        elif m.lastgroup == "descendant":
            tokens.append(("descendant", m.group("descendant")))
        elif m.lastgroup == "dotkey":
            tokens.append(("key", m.group("dotkey")))
        elif m.lastgroup == "qkey":
            tokens.append(("key", m.group("qkey")))
        elif m.lastgroup == "bracket":
            val = m.group("bracket")
            if val == "*":
                tokens.append(("wildcard", "*"))
            else:
                tokens.append(("index", int(val)))
        elif m.lastgroup == "filter":
            tokens.append(("filter", m.group("filter")))

        pos = m.end()
    return tokens


# ── Evaluator ────────────────────────────────────────────────────────


def _apply_filter(node: StructuredNode, expr: str) -> bool:
    """简化过滤表达式求值: @.key op val。"""
    # expr 形如 "@.name == 'Button1'" 或 "@.Left > 100"
    m = re.match(
        r"""@\.(?P<key>[a-zA-Z_][\w]*)
        \s*(?P<op>==|!=|>=|<=|>|<|=~)\s*
        ['"]?(?P<val>[^'"]+)['"]?
        """,
        expr.strip(),
    )
    if not m:
        return True  # 无法解析的过滤默认通过
    key, op, val_str = m.group("key"), m.group("op"), m.group("val")
    actual = node.child_by_key(key)
    if actual is None:
        return False
    actual_val = actual.value if actual.value is not None else (
        actual.to_json_compatible() if actual.kind in ("object", "array") else ""
    )
    # 类型转换
    try:
        if actual_val is not None and val_str.isdigit():
            actual_val = int(actual_val)
            val_str = int(val_str)
    except (ValueError, TypeError):
        pass

    if op == "==":
        return actual_val == val_str
    if op == "!=":
        return actual_val != val_str
    if op == ">":
        return isinstance(actual_val, (int, float)) and actual_val > val_str
    if op == "<":
        return isinstance(actual_val, (int, float)) and actual_val < val_str
    if op == ">=":
        return isinstance(actual_val, (int, float)) and actual_val >= val_str
    if op == "<=":
        return isinstance(actual_val, (int, float)) and actual_val <= val_str
    return True


def _query_single(node: StructuredNode, token: tuple[str, str]) -> list[StructuredNode]:
    """在单个节点上应用一个 token，返回匹配的子节点列表。"""
    typ, val = token

    if typ == "root":
        return [node]

    if typ == "key":
        if val == node.key:  # 用于递归后匹配 key
            return [node]
        c = node.child_by_key(val)
        return [c] if c else []

    if typ == "index":
        if node.kind == "array" and isinstance(val, int) and val < len(node.children):
            return [node.children[val]]
        return []

    if typ == "wildcard":
        return list(node.children)

    if typ == "descendant":
        return node.find_all(val)

    if typ == "filter":
        return [c for c in node.children if _apply_filter(c, val)]

    return []


def query(node: StructuredNode, expression: str) -> list[StructuredNode]:
    """在 StructuredNode 树上执行 JSONPath 查询。

    Args:
        node: 根节点。
        expression: JSONPath 表达式，如 ``$.components[0].name``。

    Returns:
        匹配的节点列表。
    """
    tokens = _tokenise(expression)
    if not tokens:
        return []

    candidates = [node]
    for token in tokens:
        next_candidates: list[StructuredNode] = []
        for c in candidates:
            next_candidates.extend(_query_single(c, token))
        candidates = next_candidates
        if not candidates:
            break
    return candidates


def query_first(node: StructuredNode, expression: str) -> Optional[StructuredNode]:
    """查询第一个匹配的节点。"""
    results = query(node, expression)
    return results[0] if results else None


def set_value(node: StructuredNode, expression: str, value: Any) -> int:
    """按 JSONPath 表达式设置节点值。

    Args:
        node: 根节点。
        expression: JSONPath 表达式。
        value: 新值（字符串或 JSON 兼容类型）。

    Returns:
        修改的节点数。
    """
    targets = query(node, expression)
    for t in targets:
        t.value = value
        if not isinstance(value, (str, int, float, bool)):
            t.kind = "string"
            t.value = str(value)
    return len(targets)


def set_value_by_path_keys(root: StructuredNode, keys: list[str], value: Any) -> bool:
    """按 key 链设置值（用于 set action 的 path="a.b.c" 风格）。"""
    node = root
    for k in keys[:-1]:
        child = node.child_by_key(k)
        if child is None:
            child = StructuredNode(key=k, kind="object")
            node.children.append(child)
        node = child
    last_key = keys[-1]
    existing = node.child_by_key(last_key)
    if existing:
        existing.value = value
        existing.kind = type(value).__name__ if isinstance(value, (str, int, float, bool)) else "string"
    else:
        node.children.append(StructuredNode(
            key=last_key,
            kind=type(value).__name__ if isinstance(value, (str, int, float, bool)) else "string",
            value=value,
        ))
    return True
