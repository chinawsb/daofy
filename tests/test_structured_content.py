"""tests for structured_content — StructuredNode, JSONPath, schema_gen, format adapters."""

from __future__ import annotations

import json
import os
import tempfile

import msgpack
import pytest

from src.tools.structured_content.schema import StructuredNode
from src.tools.structured_content.path import query, query_first, set_value
from src.tools.structured_content.schema_gen import generate_schema
from src.tools.structured_content.parser import detect_format, read_file, write_file


@pytest.fixture
def sample_node() -> StructuredNode:
    root = StructuredNode(key="", kind="object")
    root.children.append(StructuredNode(key="name", kind="string", value="MyForm"))
    root.children.append(StructuredNode(key="width", kind="integer", value=800))
    root.children.append(StructuredNode(key="height", kind="integer", value=600))
    obj = StructuredNode(key="child", kind="object")
    obj.children.append(StructuredNode(key="left", kind="integer", value=10))
    obj.children.append(StructuredNode(key="top", kind="integer", value=20))
    obj.children.append(StructuredNode(key="caption", kind="string", value="Hello"))
    root.children.append(obj)
    arr = StructuredNode(key="items", kind="array")
    arr.children.append(StructuredNode(key="0", kind="string", value="a"))
    arr.children.append(StructuredNode(key="1", kind="string", value="b"))
    arr.children.append(StructuredNode(key="2", kind="integer", value=42))
    root.children.append(arr)
    return root


@pytest.fixture
def temp_json() -> str:
    data = {"name": "MyForm", "width": 800, "items": [1, 2, 3]}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
        path = f.name
    yield path
    os.unlink(path)


@pytest.fixture
def temp_xml() -> str:
    xml = '<?xml version="1.0"?><root><name>MyForm</name><width>800</width></root>'
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write(xml)
        path = f.name
    yield path
    os.unlink(path)


class TestStructuredNode:
    def test_to_json_compatible(self, sample_node):
        j = sample_node.to_json_compatible()
        assert j["name"] == "MyForm"
        assert j["width"] == 800
        assert j["child"]["left"] == 10
        assert j["items"] == ["a", "b", 42]

    def test_from_json_compatible(self):
        src = {"name": "Test", "nums": [1, 2], "nested": {"x": 10}}
        node = StructuredNode.from_json_compatible(src, key="")
        assert node.key == ""
        assert len(node.children) == 3
        name_n = node.child_by_key("name")
        assert name_n is not None and name_n.value == "Test"

    def test_child_by_key_missing(self, sample_node):
        assert sample_node.child_by_key("nonexistent") is None

    def test_find_by_path_keys(self, sample_node):
        result = sample_node.find_by_path_keys(["child", "left"])
        assert result is not None and result.value == 10

    def test_find_by_path_keys_root(self, sample_node):
        assert sample_node.find_by_path_keys([]) is sample_node

    def test_find_all_by_key(self, sample_node):
        results = sample_node.find_all("left")
        assert len(results) == 1 and results[0].value == 10

    def test_find_all_by_predicate(self, sample_node):
        nodes = sample_node.find_all(lambda n: n.kind == "integer")
        assert len(nodes) >= 3

    def test_repr(self):
        n = StructuredNode(key="k", kind="string", value="v")
        assert "k" in repr(n) and "string" in repr(n)


class TestPath:
    def test_query_root(self, sample_node):
        results = query(sample_node, "$")
        assert len(results) == 1 and results[0] is sample_node

    def test_query_simple_key(self, sample_node):
        results = query(sample_node, "$.name")
        assert len(results) == 1 and results[0].value == "MyForm"

    def test_query_nested(self, sample_node):
        results = query(sample_node, "$.child.left")
        assert len(results) == 1 and results[0].value == 10

    def test_query_array_index(self, sample_node):
        results = query(sample_node, "$.items[1]")
        assert len(results) == 1 and results[0].value == "b"

    def test_query_wildcard(self, sample_node):
        results = query(sample_node, "$.items[*]")
        assert len(results) == 3

    def test_query_recursive(self, sample_node):
        results = query(sample_node, "$..left")
        assert len(results) == 1 and results[0].value == 10

    def test_query_filter(self, sample_node):
        results = query(sample_node, "$[?(@.key == 'child')]")
        assert len(results) >= 1

    def test_query_empty_path(self, sample_node):
        assert len(query(sample_node, "")) == 0

    def test_query_no_match(self, sample_node):
        assert len(query(sample_node, "$.nosuch")) == 0

    def test_query_first(self, sample_node):
        r = query_first(sample_node, "$.child.left")
        assert r is not None and r.value == 10

    def test_query_first_none(self, sample_node):
        assert query_first(sample_node, "$.nothing") is None

    def test_set_value(self, sample_node):
        n = set_value(sample_node, "$.name", "Renamed")
        assert n == 1
        nn = sample_node.child_by_key("name")
        assert nn is not None and nn.value == "Renamed"

    def test_set_value_nested(self, sample_node):
        n = set_value(sample_node, "$.child.left", 99)
        assert n == 1
        r = sample_node.find_by_path_keys(["child", "left"])
        assert r is not None and r.value == 99


class TestSchemaGen:
    def test_generate_schema(self, sample_node):
        schema = generate_schema(sample_node, title="TestSchema")
        assert schema["title"] == "TestSchema"
        assert schema["type"] == "object"
        assert "name" in schema["properties"]
        assert schema["properties"]["name"]["type"] == "string"

    def test_schema_roundtrip(self, sample_node):
        schema = generate_schema(sample_node)
        assert schema["$schema"].startswith("https://json-schema.org/")


class TestDetectFormat:
    def test_json_ext(self):
        assert detect_format("test.json") == "json"
    def test_xml_ext(self):
        assert detect_format("test.xml") == "xml"
    def test_dfm_ext(self):
        assert detect_format("test.dfm") == "dfm"
    def test_lfm_ext(self):
        assert detect_format("test.lfm") == "lfm"
    def test_fmx_ext(self):
        assert detect_format("test.fmx") == "fmx"
    def test_msgpack_ext(self):
        assert detect_format("test.msgpack") == "msgpack"
    def test_protobuf_ext(self):
        assert detect_format("test.pb") == "protobuf"
        assert detect_format("test.proto") == "protobuf"
    def test_unknown_ext(self):
        assert detect_format("test.xyz") is None
    def test_hint_override(self):
        assert detect_format("test.xyz", hint="json") == "json"


class TestJsonAdapter:
    def test_read(self, temp_json):
        node, fmt = read_file(temp_json)
        assert fmt == "json"
        assert isinstance(node, StructuredNode)

    def test_read_content(self, temp_json):
        node, _ = read_file(temp_json)
        j = node.to_json_compatible()
        assert j["name"] == "MyForm" and j["width"] == 800

    def test_read_write_roundtrip(self):
        data = {"x": 1, "y": {"z": "hello"}, "arr": [10, 20]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(data, f)
            path = f.name
        try:
            node, _ = read_file(path)
            write_file(node, path, "json")
            with open(path, encoding="utf-8") as f:
                assert json.load(f) == data
        finally:
            os.unlink(path)


class TestXmlAdapter:
    def test_read(self, temp_xml):
        node, fmt = read_file(temp_xml)
        assert fmt == "xml" and isinstance(node, StructuredNode)

    def test_read_content_collapsed(self, temp_xml):
        node, _ = read_file(temp_xml)
        j = node.to_json_compatible()
        assert j["name"] == "MyForm"
        assert j["width"] == "800"

    def test_read_write_roundtrip(self):
        xml = '<?xml version="1.0"?>\n<catalog><book><id>1</id><title>Hello</title></book></catalog>\n'
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(xml)
            path = f.name
        try:
            node, _ = read_file(path)
            write_file(node, path, "xml")
            with open(path, encoding="utf-8") as f:
                out = f.read()
            assert "<catalog>" in out and "<title>Hello</title>" in out
        finally:
            os.unlink(path)

    def test_xml_with_attributes(self):
        from src.tools.structured_content.xml_adapter import parse as xml_parse
        node = xml_parse('<root id="42"><name color="red">Alice</name></root>')
        j = node.to_json_compatible()
        # attributes stored as @key directly
        assert j.get("@id") == "42"
        # name has attribute AND text, so it stays object
        name_val = j.get("name", {})
        assert isinstance(name_val, dict)
        assert name_val.get("@color") == "red"


class TestMsgpackAdapter:
    def test_read_write_roundtrip(self):
        data = {"name": "Test", "count": 42, "tags": ["a", "b"]}
        raw = msgpack.packb(data)
        with tempfile.NamedTemporaryFile(suffix=".msgpack", delete=False) as f:
            f.write(raw)
            path = f.name
        try:
            node, fmt = read_file(path)
            assert fmt == "msgpack"
            j = node.to_json_compatible()
            assert j["name"] == "Test" and j["count"] == 42

            from src.tools.structured_content.msgpack_adapter import parse_text, serialize_text
            b64 = serialize_text(node)
            node2 = parse_text(b64)
            assert node2 is not None
            nn = node2.child_by_key("name")
            assert nn is not None and nn.value == "Test"
        finally:
            os.unlink(path)


class TestDfmAdapter:
    def test_parse_simple(self):
        from src.tools.structured_content.dfm_adapter import parse as dfm_parse
        node = dfm_parse("object Form1: TForm\n  Left = 100\n  Caption = 'Hello'\nend\n")
        j = node.to_json_compatible()
        # DFM values are typed: numeric → int, quoted → string
        assert j.get("Left") == 100
        assert j.get("Caption") == "'Hello'"

    def test_parse_nested(self):
        from src.tools.structured_content.dfm_adapter import parse as dfm_parse
        node = dfm_parse("object Form1: TForm\n  object Button1: TButton\n    Left = 10\n    Caption = 'Click'\n  end\nend\n")
        j = node.to_json_compatible()
        assert j.get("Button1", {}).get("Left") == 10


class TestEntryPoint:
    @pytest.mark.asyncio
    async def test_read_json(self, temp_json):
        from src.tools.structured_content import handle_structured_content
        r = await handle_structured_content({"action": "read", "file_path": temp_json})
        assert r["status"] == "success"
        assert r["data"]["value"]["name"] == "MyForm"

    @pytest.mark.asyncio
    async def test_get_schema(self, temp_json):
        from src.tools.structured_content import handle_structured_content
        r = await handle_structured_content({"action": "get_schema", "file_path": temp_json})
        assert r["status"] == "success" and r["data"]["schema"]["type"] == "object"

    @pytest.mark.asyncio
    async def test_search(self, temp_json):
        from src.tools.structured_content import handle_structured_content
        r = await handle_structured_content({"action": "search", "file_path": temp_json, "path": "$.name"})
        assert r["status"] == "success" and r["data"]["match_count"] == 1

    @pytest.mark.asyncio
    async def test_set(self, temp_json):
        from src.tools.structured_content import handle_structured_content
        r = await handle_structured_content({"action": "set", "file_path": temp_json, "path": "$.name", "value": "NewName"})
        assert r["status"] == "success" and r["data"]["modified_count"] == 1
        node, _ = read_file(temp_json)
        nn = node.child_by_key("name")
        assert nn is not None and nn.value == "NewName"

    @pytest.mark.asyncio
    async def test_read_xml(self, temp_xml):
        from src.tools.structured_content import handle_structured_content
        r = await handle_structured_content({"action": "read", "file_path": temp_xml})
        assert r["status"] == "success"

    @pytest.mark.asyncio
    async def test_nonexistent(self):
        from src.tools.structured_content import handle_structured_content
        r = await handle_structured_content({"action": "read", "file_path": "/nonexistent/foo.xyz"})
        assert r.get("status") == "failed" or "error" in r

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        from src.tools.structured_content import handle_structured_content
        r = await handle_structured_content({"action": "bogus"})
        assert "error" in r

    @pytest.mark.asyncio
    async def test_read_schema_output(self, temp_json):
        from src.tools.structured_content import handle_structured_content
        r = await handle_structured_content({"action": "read", "file_path": temp_json, "output": "schema"})
        assert r["status"] == "success" and "schema" in r["data"]

    @pytest.mark.asyncio
    async def test_read_path_filter(self, temp_json):
        from src.tools.structured_content import handle_structured_content
        r = await handle_structured_content({"action": "read", "file_path": temp_json, "path": "$.name"})
        assert r["status"] == "success" and r["data"]["match_count"] == 1 and r["data"]["value"] == "MyForm"
