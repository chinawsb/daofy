"""
JSON Schema 生成 — 从 StructuredNode 树递归生成 JSON Schema。

生成的 Schema 可以让 LLM 理解文档结构，从而精确构造路径表达式。
"""

from __future__ import annotations

from typing import Any

from .schema import StructuredNode


def generate_schema(
    node: StructuredNode,
    title: str = "StructuredDocument",
    description: str = "",
) -> dict[str, Any]:
    """从 StructuredNode 树递归生成 JSON Schema。

    Args:
        node: 根节点。
        title: Schema title。
        description: Schema description。

    Returns:
        JSON Schema dict (draft/2020-12)。
    """
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": title,
        "type": "object",
    }
    if description:
        schema["description"] = description

    _build_properties(schema, node)
    return schema


def _build_properties(schema: dict[str, Any], node: StructuredNode) -> None:
    """递归填充 schema 的 properties。"""
    if node.attributes:
        meta: dict[str, Any] = {}
        for k, v in node.attributes.items():
            meta[k] = {"type": "string", "const": v}
        schema.setdefault("properties", {})["@meta"] = {
            "type": "object",
            "description": "Format-specific metadata",
            "properties": meta,
        }

    if node.kind == "object":
        props: dict[str, Any] = {}
        for child in node.children:
            props[child.key] = _child_schema(child)
        if props:
            schema["properties"] = props

    elif node.kind == "array":
        schema["type"] = "array"
        if node.children:
            schema["items"] = _child_schema(node.children[0])
        else:
            schema["items"] = {}
        schema.pop("properties", None)

    elif node.kind == "string":
        schema["type"] = "string"

    elif node.kind == "number":
        schema["type"] = "number"

    elif node.kind == "boolean":
        schema["type"] = "boolean"

    elif node.kind == "null":
        schema["type"] = "null"


def _child_schema(child: StructuredNode) -> dict[str, Any]:
    """为单个子节点生成 Schema entry。"""
    entry: dict[str, Any] = {"type": child.kind}

    if child.attributes.get("class_name"):
        entry["description"] = child.attributes["class_name"]

    if child.kind == "object":
        subs: dict[str, Any] = {}
        for c in child.children:
            subs[c.key] = _child_schema(c)
        if subs:
            entry["properties"] = subs

    elif child.kind == "array":
        if child.children:
            entry["items"] = _child_schema(child.children[0])
        else:
            entry["items"] = {}

    return entry
