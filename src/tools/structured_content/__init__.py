"""
structured_content — 结构化文档统一读写/搜索/修改工具。

支持的格式:
  - DFM / LFM / FMX (Delphi / Lazarus 表单)
  - XML
  - JSON
  - MessagePack
  - ProtoBuf (需预先编译 .proto)

核心操作:
  read        读取结构化文件 → JSON / Schema
  get_schema  生成 JSON Schema
  set         按路径修改值
  search      按 JSONPath 搜索节点
"""

from __future__ import annotations

import os
import json as _json
from typing import Any, Optional

from .schema import StructuredNode
from .parser import (
    read_file,
    write_file,
    detect_format,
    SUPPORTED_FORMATS,
)
from .path import query, set_value, query_first
from .schema_gen import generate_schema

__all__ = ["handle_structured_content", "SUPPORTED_FORMATS"]


async def handle_structured_content(arguments: dict) -> dict[str, Any]:
    """``structured_content`` — 结构化文档统一读写/查询/修改。

    Action:
        read         读取文件，返回 JSON / Schema
        get_schema   生成 JSON Schema
        set          按路径修改值
        search       按 JSONPath 搜索

    Args:
        action: 操作类型。
        file_path: 文件路径。
        path: JSONPath 路径（默认 ``$`` 即根）。
        value: set action 时的新值。
        format: 强制格式（dfm/lfm/fmx/xml/json/msgpack/protobuf）。
                默认从文件扩展名检测。
        output: read action 的输出格式（"json" | "schema" | "both"）。
        proto_file: ProtoBuf 模式时传入 .proto 文件路径。
        message_name: ProtoBuf 模式时传入消息名。
    """
    action = arguments.get("action", "read")
    file_path = arguments.get("file_path", "")
    path_expr = arguments.get("path", "$")
    value = arguments.get("value")
    fmt_hint = arguments.get("format")
    output = arguments.get("output", "json")

    if not file_path and action in ("read", "set", "search"):
        return {"error": "file_path is required"}

    # ── 格式检测 ──
    try:
        fmt = detect_format(file_path, hint=fmt_hint) if file_path else fmt_hint
    except Exception as e:
        return {"status": "failed", "error": f"格式检测失败: {e}"}

    # ── read ────────────────────────────────────────────────────
    if action == "read":
        proto_file = arguments.get("proto_file")
        message_name = arguments.get("message_name")

        if fmt == "protobuf":
            if not proto_file or not message_name:
                return {"error": "ProtoBuf 读取需要 proto_file 和 message_name 参数"}
            from .protobuf_adapter import compile_and_parse
            with open(file_path, "rb") as f:
                raw = f.read()
            node = compile_and_parse(proto_file, message_name, raw)
        else:
            try:
                node, fmt = read_file(file_path, fmt)
            except FileNotFoundError:
                return {"status": "failed", "error": f"文件不存在: {file_path}"}
            except ValueError as e:
                return {"status": "failed", "error": str(e)}

        # 按路径截取
        if path_expr and path_expr != "$":
            matched = query(node, path_expr)
            if not matched:
                return {
                    "format": fmt,
                    "path": path_expr,
                    "match_count": 0,
                    "error": f"路径 '{path_expr}' 无匹配",
                }
            result_nodes = matched
        else:
            result_nodes = [node]

        # 产出
        result: dict[str, Any] = {
            "format": fmt,
            "path": path_expr,
            "match_count": len(result_nodes),
        }

        if output in ("schema", "both"):
            result["schema"] = generate_schema(node, title=os.path.basename(file_path))

        if output in ("json", "both"):
            if len(result_nodes) == 1:
                result["value"] = result_nodes[0].to_json_compatible()
            else:
                result["value"] = [n.to_json_compatible() for n in result_nodes]

        return {"status": "success", "data": result}

    # ── get_schema ──────────────────────────────────────────────
    if action == "get_schema":
        try:
            node, fmt = read_file(file_path, fmt)
        except FileNotFoundError:
            return {"status": "failed", "error": f"文件不存在: {file_path}"}
        except ValueError as e:
            return {"status": "failed", "error": str(e)}
        schema = generate_schema(node, title=os.path.basename(file_path))
        return {
            "status": "success",
            "data": {
                "format": fmt,
                "schema": schema,
            }
        }

    # ── set ─────────────────────────────────────────────────────
    if action == "set":
        if value is None:
            return {"error": "set action requires 'value' parameter"}
        try:
            node, fmt = read_file(file_path, fmt)
        except FileNotFoundError:
            return {"status": "failed", "error": f"文件不存在: {file_path}"}
        except ValueError as e:
            return {"status": "failed", "error": str(e)}
        count = set_value(node, path_expr, value)
        write_file(node, file_path, fmt)
        return {
            "status": "success",
            "data": {
                "format": fmt,
                "path": path_expr,
                "modified_count": count,
                "message": f"已修改 {count} 个节点",
            }
        }

    # ── search ──────────────────────────────────────────────────
    if action == "search":
        try:
            node, fmt = read_file(file_path, fmt)
        except FileNotFoundError:
            return {"status": "failed", "error": f"文件不存在: {file_path}"}
        except ValueError as e:
            return {"status": "failed", "error": str(e)}
        matched = query(node, path_expr)
        return {
            "status": "success",
            "data": {
                "format": fmt,
                "path": path_expr,
                "match_count": len(matched),
                "matches": [n.to_json_compatible() for n in matched],
            }
        }

    return {"error": f"未知 action: {action}, 支持: read, get_schema, set, search"}
