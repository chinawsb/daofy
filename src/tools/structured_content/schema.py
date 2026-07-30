"""
StructuredNode — 结构化文档的统一数据模型。

所有格式（DFM/LFM/FMX/XML/JSON/MessagePack/ProtoBuf）
都归一化为 StructuredNode 树，后续路径查询 / Schema 生成 /
修改操作都在此模型上进行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class StructuredNode:
    """结构化文档的通用节点模型。

    Attributes:
        key: 当前节点的键名（根节点为 ``""``）。
        kind: 值类型 —  ``"object"`` / ``"array"`` / ``"string"`` /
               ``"number"`` / ``"boolean"`` / ``"null"``。
        value: 叶子节点的原生值（str / int / float / bool / None）。
        children: 子节点列表（kind=object/array 时非空）。
        attributes: 格式特定的元信息，如 DFM 的 class_name／XML 的 namespace。
    """
    key: str = ""
    kind: str = "object"  # object | array | string | number | boolean | null
    value: Any = None
    children: list[StructuredNode] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)

    # ── 导航 ──────────────────────────────────────────────────────

    def child_by_key(self, key: str) -> Optional[StructuredNode]:
        """按 key 查找直接子节点。"""
        for c in self.children:
            if c.key == key:
                return c
        return None

    def find_by_path_keys(self, keys: list[str]) -> Optional[StructuredNode]:
        """按 key 链逐级查找（如 root/component/properties/Left）。"""
        node: Optional[StructuredNode] = self
        for k in keys:
            if node is None:
                return None
            node = node.child_by_key(k)
        return node

    def find_all(self, predicate) -> list[StructuredNode]:
        """递归查找所有匹配的节点。

        Args:
            predicate: 匹配条件 — str（按 key 匹配）或 callable（按自定义条件匹配）。

        Returns:
            匹配节点列表。
        """
        result: list[StructuredNode] = []
        if callable(predicate):
            matches = predicate(self)
        else:
            matches = (self.key == predicate)
        if matches:
            result.append(self)
        for c in self.children:
            result.extend(c.find_all(predicate))
        return result

    # ── 序列化 ─────────────────────────────────────────────────────

    def to_json_compatible(self) -> Any:
        """递归转 JSON 原生类型（dict/list/str/int/float/bool/None）。"""
        if self.kind == "object":
            d: dict[str, Any] = {}
            if self.attributes:
                d["@attributes"] = dict(self.attributes)
            for c in self.children:
                d[c.key] = c.to_json_compatible()
            return d
        if self.kind == "array":
            return [c.to_json_compatible() for c in self.children]
        return self.value

    @classmethod
    def from_json_compatible(cls, data: Any, key: str = "") -> StructuredNode:
        """从 JSON 原生类型反构造 StructuredNode。"""
        if isinstance(data, dict):
            node = cls(key=key, kind="object")
            attrs = data.get("@attributes")
            if key and isinstance(attrs, dict):
                node.attributes = dict(attrs)
            for k, v in data.items():
                if k == "@attributes":
                    continue
                node.children.append(cls.from_json_compatible(v, key=k))
            return node
        if isinstance(data, list):
            node = cls(key=key, kind="array")
            for i, item in enumerate(data):
                node.children.append(cls.from_json_compatible(item, key=str(i)))
            return node
        if isinstance(data, str):
            return cls(key=key, kind="string", value=data)
        if isinstance(data, bool):
            return cls(key=key, kind="boolean", value=data)
        if isinstance(data, int):
            return cls(key=key, kind="number", value=data)
        if isinstance(data, float):
            return cls(key=key, kind="number", value=data)
        if data is None:
            return cls(key=key, kind="null", value=None)
        return cls(key=key, kind="string", value=str(data))

    def __repr__(self) -> str:
        v = f"={self.value!r}" if self.value is not None else ""
        children_n = f" [{len(self.children)} children]" if self.children else ""
        attr_s = f" attrs={self.attributes}" if self.attributes else ""
        return f"<Node:{self.key}:{self.kind}{v}{children_n}{attr_s}>"
