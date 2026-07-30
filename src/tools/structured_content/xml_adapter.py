"""
XML 格式适配器 — 读写 XML 文件 ↔ StructuredNode。

使用 xml.etree.ElementTree（标准库），将 XML 元素映射为：
  element → StructuredNode(kind="object", key=tag)
  attribute → StructuredNode(key="@<name>", kind="string")
  text → StructuredNode(key="#text", kind="string")
  同标签多子元素 → StructuredNode(kind="array", key=tag)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Optional

from .schema import StructuredNode

# 注册命名空间避免输出 ns0 前缀
try:
    ET.register_namespace("", "")
except Exception:
    pass


def parse(text: str) -> StructuredNode:
    """解析 XML 文本为 StructuredNode。"""
    root = ET.fromstring(text)
    return _element_to_node(root)


def _element_to_node(elem: ET.Element) -> StructuredNode:
    """ET.Element → StructuredNode。"""
    tag = _clean_tag(elem.tag)
    node = StructuredNode(key=tag, kind="object")

    # attributes
    for k, v in elem.attrib.items():
        node.children.append(StructuredNode(key=f"@{k}", kind="string", value=v))

    # children — 按 tag 分组，同 tag 聚合为数组
    child_tags: dict[str, list[ET.Element]] = {}
    for child in elem:
        t = _clean_tag(child.tag)
        child_tags.setdefault(t, []).append(child)

    for t, items in child_tags.items():
        if len(items) == 1:
            node.children.append(_element_to_node(items[0]))
        else:
            arr = StructuredNode(key=t, kind="array")
            for item in items:
                arr.children.append(_element_to_node(item))
            node.children.append(arr)

    # text content — collapse simple text-only element to leaf
    text = (elem.text or "").strip()
    if text and not child_tags and not elem.attrib:
        # <!-- 纯文本叶子节点: <tag>text</tag> → kind="string", value="text" -->
        node.kind = "string"
        node.value = text
        node.children = []
        return node

    if text and not child_tags:
        node.children.append(StructuredNode(key="#text", kind="string", value=text))

    # namespace info
    if "}" in elem.tag:
        ns = elem.tag.split("}")[0].lstrip("{")
        node.attributes["xmlns"] = ns

    return node


def serialize(node: StructuredNode, indent: int = 2) -> str:
    """将 StructuredNode 序列化为 XML 文本。"""
    root = _node_to_element(node)
    ET.indent(root, space=" " * indent)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def _node_to_element(node: StructuredNode) -> ET.Element:
    """StructuredNode → ET.Element。"""
    tag = node.key or "root"
    elem = ET.Element(tag)

    # collapsed leaf: <tag>value</tag>
    if node.kind not in ("object", "array"):
        elem.text = str(node.value or "")
        return elem

    for child in node.children:
        if child.key.startswith("@"):
            elem.set(child.key[1:], str(child.value or ""))
        elif child.key == "#text":
            elem.text = str(child.value or "")
        elif child.kind == "array":
            for item in child.children:
                elem.append(_node_to_element(item))
        else:
            elem.append(_node_to_element(child))

    return elem


def _clean_tag(tag: str) -> str:
    """去除命名空间前缀。"""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def can_parse(text: str) -> bool:
    """检测是否为合法 XML。"""
    text = text.strip()
    if not text.startswith("<"):
        return False
    try:
        ET.fromstring(text)
        return True
    except ET.ParseError:
        return False
