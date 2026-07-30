"""
ProtoBuf 格式适配器 — 读写 .proto / .pb 文件 ↔ StructuredNode。

支持两种模式:
  1. 动态编译 .proto 文件 → 用生成的 XXX_pb2 模块序列化/反序列化
  2. 直接解析已有的 .proto 描述文件为 Schema

依赖: pip install protobuf
"""

from __future__ import annotations

import os
import re
import tempfile
from typing import Any, Optional

from .schema import StructuredNode


# ═════════════════════════════════════════════════════════════════════
#  第1部分: .proto 文件解析为描述性 JSON
# ═════════════════════════════════════════════════════════════════════

PROTO_MESSAGE_RE = re.compile(
    r"message\s+(\w+)\s*\{"
)
PROTO_FIELD_RE = re.compile(
    r"(repeated\s+|optional\s+|required\s+)?"
    r"(?P<type>[\w.]+)"
    r"\s+(?P<name>\w+)\s*=\s*(?P<tag>\d+)"
)


def parse_proto_descriptor(proto_text: str) -> list[dict[str, Any]]:
    """解析 .proto 文件中的消息定义，返回描述列表。"""
    messages: list[dict[str, Any]] = []
    pos = 0
    while True:
        m = PROTO_MESSAGE_RE.search(proto_text, pos)
        if not m:
            break
        msg_name = m.group(1)
        # 找匹配的闭合括号（简单处理，不支持嵌套消息）
        brace_start = m.end()
        depth = 1
        p = brace_start
        while depth > 0 and p < len(proto_text):
            if proto_text[p] == "{":
                depth += 1
            elif proto_text[p] == "}":
                depth -= 1
            p += 1
        body = proto_text[brace_start : p - 1]

        fields: list[dict[str, Any]] = []
        for fm in PROTO_FIELD_RE.finditer(body):
            fields.append({
                "repeated": bool(fm.group(1) and "repeated" in fm.group(1)),
                "type": fm.group("type"),
                "name": fm.group("name"),
                "tag": int(fm.group("tag")),
            })

        messages.append({"name": msg_name, "fields": fields})
        pos = p

    return messages


# ═════════════════════════════════════════════════════════════════════
#  第2部分: 已知 protobuf 消息序列化 ↔ dict
# ═════════════════════════════════════════════════════════════════════


def message_to_dict(msg_obj) -> dict[str, Any]:
    """将 protobuf 消息对象转为 JSON 兼容 dict。

    Args:
        msg_obj: protobuf 消息实例（如 my_pb2.MyMessage()）。
    """
    try:
        from google.protobuf.json_format import MessageToDict
        return MessageToDict(
            msg_obj,
            preserving_proto_field_name=True,
            including_default_value_fields=False,
        )
    except ImportError:
        raise ImportError("需要 protobuf 库: pip install protobuf")


def dict_to_message(data: dict[str, Any], msg_class) -> Any:
    """从 JSON 兼容 dict 反构造 protobuf 消息。"""
    try:
        from google.protobuf.json_format import ParseDict
        return ParseDict(data, msg_class())
    except ImportError:
        raise ImportError("需要 protobuf 库: pip install protobuf")


# ═════════════════════════════════════════════════════════════════════
#  第3部分: parse() / serialize() — 通过动态编译 .proto
# ═════════════════════════════════════════════════════════════════════


def compile_and_parse(
    proto_file: str,
    message_name: str,
    binary_data: bytes,
) -> StructuredNode:
    """编译 .proto 文件并用其反序列化二进制数据。

    Args:
        proto_file: .proto 文件路径。
        message_name: 顶层消息名（如 "MyMessage"）。
        binary_data: Protobuf 序列化字节。

    Returns:
        StructuredNode。
    """
    import importlib
    import sys

    from google.protobuf import descriptor_pb2, compiler

    # 编译 .proto 到临时目录
    tmp_dir = tempfile.mkdtemp(prefix="proto_")
    try:
        # protoc --python_out=tmp_dir proto_file
        proto_base = os.path.basename(proto_file)
        proto_module_name = proto_base.replace(".proto", "_pb2")

        compiler.main([
            "protoc",
            f"--proto_path={os.path.dirname(proto_file) or '.'}",
            f"--python_out={tmp_dir}",
            proto_file,
        ])

        sys.path.insert(0, tmp_dir)
        try:
            pb2_module = importlib.import_module(proto_module_name)
        finally:
            sys.path.pop(0)

        msg_class = getattr(pb2_module, message_name)
        msg_obj = msg_class()
        msg_obj.ParseFromString(binary_data)

        d = message_to_dict(msg_obj)
        return StructuredNode.from_json_compatible(d, key="")

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def serialize_message(msg_class, data: dict[str, Any]) -> bytes:
    """从 dict 构造 protobuf 消息并序列化。

    Args:
        msg_class: protobuf 消息类（如 MyMessage）。
        data: JSON 兼容 dict。

    Returns:
        序列化字节。
    """
    msg = dict_to_message(data, msg_class)
    return msg.SerializeToString()
