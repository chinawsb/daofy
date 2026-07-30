"""
格式检测与分发 — 自动识别文件格式并调用对应适配器。
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .schema import StructuredNode

# ── 格式枚举 ─────────────────────────────────────────────────────────

SUPPORTED_FORMATS = [
    "dfm",
    "lfm",
    "fmx",
    "xml",
    "json",
    "msgpack",
    "protobuf",
]

TEXT_FORMATS = {"dfm", "lfm", "fmx", "xml", "json"}
BINARY_FORMATS = {"msgpack", "protobuf"}

# ── 扩展名映射 ──────────────────────────────────────────────────────

EXTENSION_MAP: dict[str, str] = {
    ".dfm": "dfm",
    ".lfm": "lfm",
    ".fmx": "fmx",
    ".xml": "xml",
    ".xsd": "xml",
    ".svg": "xml",
    ".json": "json",
    ".msgpack": "msgpack",
    ".msgp": "msgpack",
    ".proto": "protobuf",
    ".pb": "protobuf",
}


def detect_format(
    file_path: str,
    content: Optional[bytes] = None,
    hint: Optional[str] = None,
) -> Optional[str]:
    """检测文件格式。

    Args:
        file_path: 文件路径。
        content: 文件内容（可选，传入时可做 content sniffing）。
        hint: 强制指定格式。

    Returns:
        格式名（dfm/lfm/fmx/xml/json/msgpack/protobuf）或 None。
    """
    if hint and hint in SUPPORTED_FORMATS:
        return hint

    ext = os.path.splitext(file_path)[1].lower()
    fmt = EXTENSION_MAP.get(ext)
    if fmt:
        return fmt

    # 无扩展名时尝试 content sniffing
    if content:
        return sniff_format(content)

    return None


def sniff_format(content: bytes) -> Optional[str]:
    """根据内容前导字节检测格式。"""
    text = content.decode("utf-8", errors="replace").strip()

    # JSON
    if text.startswith("{") or text.startswith("["):
        try:
            import json
            json.loads(text)
            return "json"
        except (json.JSONDecodeError, ValueError):
            pass

    # XML
    if text.startswith("<"):
        try:
            import xml.etree.ElementTree as ET
            ET.fromstring(text)
            return "xml"
        except ET.ParseError:
            pass

    # DFM/LFM
    if text.startswith("object ") or text.startswith("inherited "):
        return "dfm"  # dfm 和 lfm 格式一致，由扩展名区分

    # MessagePack (binary prefix 0x8_ 或 0x9_ 或 0x_ 等)
    if content[:1] in (b"\x80", b"\x90", b"\xa0", b"\xc0"):
        try:
            import msgpack
            msgpack.unpackb(content, raw=False)
            return "msgpack"
        except Exception:
            pass

    return None


# ── 格式读取 ─────────────────────────────────────────────────────────


def read_file(file_path: str, fmt: Optional[str] = None) -> tuple[StructuredNode, str]:
    """读取文件并解析为 StructuredNode。

    Args:
        file_path: 文件路径。
        fmt: 格式（None=自动检测）。

    Returns:
        (root_node, detected_format)。
    """
    with open(file_path, "rb") as f:
        raw = f.read()

    fmt = detect_format(file_path, raw, fmt)
    if fmt is None:
        raise ValueError(f"无法检测文件格式: {file_path}")

    if fmt in ("dfm", "lfm", "fmx"):
        text = raw.decode("utf-8", errors="replace")
        from .dfm_adapter import parse as dfm_parse
        return dfm_parse(text), fmt

    if fmt == "xml":
        text = raw.decode("utf-8", errors="replace")
        from .xml_adapter import parse as xml_parse
        return xml_parse(text), fmt

    if fmt == "json":
        text = raw.decode("utf-8", errors="replace")
        from .json_adapter import parse as json_parse
        return json_parse(text), fmt

    if fmt == "msgpack":
        from .msgpack_adapter import parse as msgpack_parse
        return msgpack_parse(raw), fmt

    if fmt == "protobuf":
        raise NotImplementedError(
            "ProtoBuf 文件需要指定 message_name 和 proto_file 参数。"
            "使用 structured_content(action='read', format='protobuf', "
            "proto_file='...', message_name='...')"
        )

    raise ValueError(f"不支持的格式: {fmt}")


def write_file(
    node: StructuredNode,
    file_path: str,
    fmt: Optional[str] = None,
) -> None:
    """将 StructuredNode 序列化写入文件。

    Args:
        node: StructuredNode。
        file_path: 输出路径。
        fmt: 格式（None=从扩展名推断）。
    """
    fmt = detect_format(file_path, hint=fmt)
    if fmt is None:
        raise ValueError(f"无法推断格式: {file_path}")

    if fmt in ("dfm", "lfm", "fmx"):
        from .dfm_adapter import serialize as dfm_ser
        text = dfm_ser(node)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
        return

    if fmt == "xml":
        from .xml_adapter import serialize as xml_ser
        text = xml_ser(node)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
        return

    if fmt == "json":
        from .json_adapter import serialize as json_ser
        text = json_ser(node)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
        return

    if fmt == "msgpack":
        from .msgpack_adapter import serialize as msgpack_ser
        data = msgpack_ser(node)
        with open(file_path, "wb") as f:
            f.write(data)
        return

    if fmt == "protobuf":
        raise NotImplementedError(
            "ProtoBuf 写入需要指定 message_class 参数。"
            "使用 structured_content(action='write', format='protobuf', ...)"
        )

    raise ValueError(f"不支持的格式: {fmt}")
