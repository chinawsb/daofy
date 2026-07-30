"""
DFM/LFM/FMX 格式适配器 — 读写 Delphi/Lazarus 表单文件 ↔ StructuredNode。

复用 ``src.tools.dfm_parser`` 的 DfmComponent/DfmProperty 解析器，
将组件树映射为统一的 StructuredNode。
"""

from __future__ import annotations

from typing import Any, Optional

from .schema import StructuredNode

# 延迟导入 dfm_parser（避免循环 import 和启动时加载 KB）
_DFM_PARSER = None


def _get_parser():
    global _DFM_PARSER
    if _DFM_PARSER is None:
        from src.tools.dfm_parser import (
            parse_dfm_text,
            serialize_component,
            DfmComponent,
            DfmProperty,
        )
        _DFM_PARSER = (parse_dfm_text, serialize_component, DfmComponent, DfmProperty)
    return _DFM_PARSER


def parse(text: str) -> StructuredNode:
    """解析 DFM/LFM 文本为 StructuredNode。"""
    parse_dfm_text, serialize_component, DfmComponent, DfmProperty = _get_parser()
    root_comp = parse_dfm_text(text)
    if root_comp is None:
        raise ValueError("DFM 解析失败")
    return _component_to_node(root_comp)


def _component_to_node(comp) -> StructuredNode:
    """DfmComponent → StructuredNode。"""
    from src.tools.dfm_parser import DfmProperty

    node = StructuredNode(key=comp.name, kind="object")
    node.attributes["class_name"] = comp.class_name

    # 属性
    for prop in comp.properties:
        val = prop.raw_value
        # 尝试类型推断
        if val.isdigit():
            child = StructuredNode(key=prop.name, kind="number", value=int(val))
        elif val.replace(".", "", 1).isdigit() and val.count(".") <= 1:
            try:
                child = StructuredNode(key=prop.name, kind="number", value=float(val))
            except ValueError:
                child = StructuredNode(key=prop.name, kind="string", value=val)
        elif val.lower() in ("true", "false"):
            child = StructuredNode(key=prop.name, kind="boolean", value=val.lower() == "true")
        else:
            child = StructuredNode(key=prop.name, kind="string", value=val)
        if prop.is_event:
            child.attributes["event"] = "1"
        node.children.append(child)

    # 子组件 — 按 class_name 分组
    child_classes: dict[str, list] = {}
    for child_comp in comp.children:
        cc = child_comp.class_name
        child_classes.setdefault(cc, []).append(child_comp)

    for cc, items in child_classes.items():
        if len(items) == 1:
            node.children.append(_component_to_node(items[0]))
        else:
            arr = StructuredNode(key=cc, kind="array")
            for item in items:
                arr.children.append(_component_to_node(item))
            node.children.append(arr)

    return node


def serialize(node: StructuredNode) -> str:
    """将 StructuredNode 序列化为 DFM 文本。

    注意: 此函数产生简化的 DFM 文本。精确的 DFM 文本生成
    建议通过 manage_component 工具使用正式的 dfm_parser.serialize_component。
    """
    lines: list[str] = []
    _node_to_dfm(node, lines, 0)
    return "\n".join(lines)


def _node_to_dfm(node: StructuredNode, lines: list[str], indent: int) -> None:
    """StructuredNode → DFM 文本行。"""
    pad = "  " * indent
    class_name = node.attributes.get("class_name", "")
    if class_name:
        lines.append(f"{pad}object {node.key}: {class_name}")
    else:
        lines.append(f"{pad}object {node.key}")

    for child in node.children:
        key = child.key

        # 跳过以 @ 开头的元属性
        if key.startswith("@"):
            continue

        if child.attributes.get("event"):
            lines.append(f"{pad}  {key} = {child.value or ''}")
        elif child.kind in ("object", "array"):
            _node_to_dfm(child, lines, indent + 1)
        elif child.kind == "number":
            lines.append(f"{pad}  {key} = {child.value}")
        elif child.kind == "boolean":
            lines.append(f"{pad}  {key} = {str(child.value).lower()}")
        else:
            val = str(child.value or "")
            # 简单转义
            if " " in val or "'" in val:
                val = val.replace("'", "''")
                val = f"'{val}'"
            lines.append(f"{pad}  {key} = {val}")

    lines.append(f"{pad}end")


def can_parse(text: str) -> bool:
    """检测是否为 DFM/LFM 文本格式。"""
    text = text.strip()
    if not text.startswith("object ") and not text.startswith("inherited "):
        return False
    try:
        parse_dfm_text, serialize_component, DfmComponent, DfmProperty = _get_parser()
        root = parse_dfm_text(text)
        return root is not None
    except Exception:
        return False


def detect_format(file_path: str) -> Optional[str]:
    """按文件扩展名检测具体格式。"""
    ext = file_path.lower()
    if ext.endswith(".dfm"):
        return "dfm"
    if ext.endswith(".lfm"):
        return "lfm"
    if ext.endswith(".fmx"):
        return "fmx"
    return None
