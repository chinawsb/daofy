"""
MessagePack 格式适配器 — 读写 .msgpack 文件 ↔ StructuredNode。

依赖: pip install msgpack
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .schema import StructuredNode


def parse(data: bytes) -> StructuredNode:
    """解析 MessagePack 字节数据为 StructuredNode。"""
    import msgpack
    decoded = msgpack.unpackb(data, raw=False)
    return StructuredNode.from_json_compatible(decoded, key="")


def serialize(node: StructuredNode) -> bytes:
    """将 StructuredNode 序列化为 MessagePack 字节。"""
    import msgpack
    data = node.to_json_compatible()
    return msgpack.packb(data, default=str)


def can_parse(data: bytes) -> bool:
    """检测是否为合法 MessagePack。"""
    if not isinstance(data, bytes) or len(data) < 2:
        return False
    try:
        import msgpack
        msgpack.unpackb(data, raw=False)
        return True
    except (ImportError, msgpack.UnpackException, Exception):
        return False


def parse_text(text: str) -> StructuredNode:
    """从 Base64 编码的 MessagePack 文本解析。"""
    import base64
    try:
        data = base64.b64decode(text)
    except Exception:
        # 尝试直接 hex
        data = bytes.fromhex(text.strip())
    return parse(data)


def serialize_text(node: StructuredNode) -> str:
    """序列化为 Base64 编码的文本。"""
    import base64
    data = serialize(node)
    return base64.b64encode(data).decode("ascii")
