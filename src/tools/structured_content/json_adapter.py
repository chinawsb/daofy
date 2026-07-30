"""
JSON 格式适配器 — 读写 JSON 文件 ↔ StructuredNode。
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .schema import StructuredNode


def parse(text: str) -> StructuredNode:
    """解析 JSON 文本为 StructuredNode。"""
    data = json.loads(text)
    return StructuredNode.from_json_compatible(data, key="")


def serialize(node: StructuredNode, indent: int = 2) -> str:
    """将 StructuredNode 序列化为 JSON 文本。"""
    data = node.to_json_compatible()
    return json.dumps(data, ensure_ascii=False, indent=indent)


def can_parse(text: str) -> bool:
    """检测是否为合法 JSON。"""
    text = text.strip()
    if not (text.startswith("{") or text.startswith("[")):
        return False
    try:
        json.loads(text)
        return True
    except (json.JSONDecodeError, ValueError):
        return False
