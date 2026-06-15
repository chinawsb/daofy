#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RTTI 集成测试 — 编译 Delphi 示例程序并验证 RTTI 发现输出

测试流程：
  1. 用 dcc32 编译 tests/rtti_sample_test.dpr
  2. 运行生成的 exe，捕获 stdout JSON
  3. 验证 JSON 结构与预期 Schema 一致

这是一个端到端示例测试，展示 TRttiDiscoverer 在实际 Delphi 代码上的效果。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ═══════════════════════════════════════════════════════════════
# 预期输出（TSampleService 的 RTTI Schema）
# ═══════════════════════════════════════════════════════════════

EXPECTED_TOOLS = {
    "Add": {
        "kind": "function",
        "returnType": {"type": "integer"},
        "parameters": {
            "type": "object",
            "properties": {
                "A": {"type": "integer"},
                "B": {"type": "integer"},
            },
        },
    },
    "Greet": {
        "kind": "function",
        "returnType": {"type": "string"},
        "parameters": {
            "type": "object",
            "properties": {
                "Name": {"type": "string"},
            },
        },
    },
    "GetStatus": {
        "kind": "function",
        "returnType": {"type": "string"},
    },
    "Reset": {
        "kind": "procedure",
    },
}

EXPECTED_PROPERTIES = {
    "CallCount": {
        "schema": {"type": "integer"},
        "readable": True,
        "writable": False,
    },
    "LastResult": {
        "schema": {"type": "string"},
        "readable": True,
        "writable": True,
    },
}


# ═══════════════════════════════════════════════════════════════
# 编译并运行
# ═══════════════════════════════════════════════════════════════

def _find_dcc32() -> str | None:
    """从 compilers.json 中查找 dcc32 路径。"""
    config_path = project_root / "config" / "compilers.json"
    if not config_path.exists():
        return None
    try:
        import json as _json
        cfg = _json.loads(config_path.read_text(encoding="utf-8"))
        for ver in cfg.get("compilers", []):
            dcc = ver.get("dcc32_path", "")
            if dcc and Path(dcc).exists():
                return dcc
    except Exception:
        return None
    return None


def _compile_dpr(dpr: Path, exe_out: Path) -> bool:
    """用 dcc32 编译 .dpr。"""
    dcc32 = _find_dcc32()
    if not dcc32:
        return False
    exe_out.parent.mkdir(parents=True, exist_ok=True)
    unit_paths = [str(project_root / "tools" / "auto")]
    cmd = [
        dcc32,
        f"-E{exe_out.parent}",
        f"-U{';'.join(unit_paths)}",
        "-CC",       # 控制台类型
        str(dpr),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        # dcc32 返回 0 为成功
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


@pytest.fixture(scope="module")
def compiled_exe():
    """找到或编译 rtti_sample_test.exe 并返回路径。"""
    # 1) 优先用已有的编译产物（方便快速验证）
    existing = [
        project_root / "tests" / "Win32" / "rtti_sample_test.exe",
        project_root / "tests" / "Win32_RttiIntegration" / "rtti_sample_test.exe",
    ]
    for exe in existing:
        if exe.exists():
            return exe

    # 2) 没有则尝试编译
    dpr = project_root / "tests" / "rtti_sample_test.dpr"
    output_dir = project_root / "tests" / "Win32_RttiIntegration"
    if not _compile_dpr(dpr, output_dir / "rtti_sample_test.exe"):
        pytest.skip("dcc32 不可用，跳过集成测试（需要 Delphi 编译器）")

    exe = output_dir / "rtti_sample_test.exe"
    assert exe.exists(), f"编译后 exe 仍未生成: {exe}"
    return exe


@pytest.fixture(scope="module")
def rtti_output(compiled_exe):
    """运行 exe 并解析 JSON 输出。"""
    proc = subprocess.run(
        [str(compiled_exe)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, (
        f"exe 返回非零: {proc.returncode}\nstderr: {proc.stderr}"
    )

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        pytest.fail(f"JSON 解析失败: {e}\n输出: {proc.stdout[:500]}")
    return data


# ═══════════════════════════════════════════════════════════════
# 验证 JSON 结构
# ═══════════════════════════════════════════════════════════════

class TestRttiIntegration:
    """端到端 RTTI 发现测试（编译 Delphi → 运行 → 校验 JSON）"""

    def test_class_name(self, rtti_output):
        """className 应为 'SampleService'"""
        assert rtti_output.get("className") == "SampleService"

    def test_ancestor(self, rtti_output):
        """ancestor 应为 'TObject'"""
        assert rtti_output.get("ancestor") == "TObject"

    def test_has_tools_array(self, rtti_output):
        """应包含 tools 数组"""
        tools = rtti_output.get("tools", [])
        assert isinstance(tools, list)
        assert len(tools) == 4, f"应有 4 个方法, 得到 {len(tools)}"

    def test_has_properties_array(self, rtti_output):
        """应包含 properties 数组"""
        props = rtti_output.get("properties", [])
        assert isinstance(props, list)
        assert len(props) == 2, f"应有 2 个属性, 得到 {len(props)}"

    # ── 工具（方法）校验 ──

    def test_tool_add_signature(self, rtti_output):
        """Add(A, B: Integer): Integer"""
        self._assert_tool(rtti_output, "Add")

    def test_tool_greet_signature(self, rtti_output):
        """Greet(Name: string): string"""
        self._assert_tool(rtti_output, "Greet")

    def test_tool_get_status_signature(self, rtti_output):
        """GetStatus: string"""
        self._assert_tool(rtti_output, "GetStatus")

    def test_tool_reset_signature(self, rtti_output):
        """Reset: procedure"""
        self._assert_tool(rtti_output, "Reset")

    # ── 属性校验 ──

    def test_property_callcount(self, rtti_output):
        """CallCount: Integer (readonly)"""
        self._assert_property(rtti_output, "CallCount")

    def test_property_lastresult(self, rtti_output):
        """LastResult: string (read+write)"""
        self._assert_property(rtti_output, "LastResult")

    # ── 类型映射校验 ──

    def test_type_integer(self, rtti_output):
        """Integer 类型映射为 {'type': 'integer'}"""
        add = self._find_tool(rtti_output, "Add")
        assert add["returnType"] == {"type": "integer"}

    def test_type_string(self, rtti_output):
        """String 类型映射为 {'type': 'string'}"""
        greet = self._find_tool(rtti_output, "Greet")
        assert greet["returnType"] == {"type": "string"}

    def test_parameter_order(self, rtti_output):
        """参数应按声明顺序出现"""
        add = self._find_tool(rtti_output, "Add")
        param_names = list(add["parameters"]["properties"].keys())
        assert param_names == ["A", "B"], f"参数顺序应为 [A, B], 得到 {param_names}"

    def test_no_extra_tools(self, rtti_output):
        """不应有多余的 published 方法"""
        tool_names = {t["name"] for t in rtti_output["tools"]}
        expected = set(EXPECTED_TOOLS.keys())
        assert tool_names == expected, f"多余的方法: {tool_names - expected}"

    def test_no_extra_properties(self, rtti_output):
        """不应有多余的 published 属性"""
        prop_names = {p["name"] for p in rtti_output["properties"]}
        expected = set(EXPECTED_PROPERTIES.keys())
        assert prop_names == expected, f"多余的属性: {prop_names - expected}"

    # ── helpers ──

    def _find_tool(self, data, name):
        for t in data.get("tools", []):
            if t["name"] == name:
                return t
        raise AssertionError(f"未找到工具: {name}")

    def _find_property(self, data, name):
        for p in data.get("properties", []):
            if p["name"] == name:
                return p
        raise AssertionError(f"未找到属性: {name}")

    def _assert_tool(self, data, name):
        tool = self._find_tool(data, name)
        expected = EXPECTED_TOOLS[name]
        assert tool["kind"] == expected["kind"], (
            f"{name} kind: 期望 {expected['kind']}, 得到 {tool['kind']}"
        )
        if "returnType" in expected:
            assert tool.get("returnType") == expected["returnType"], (
                f"{name} returnType: 期望 {expected['returnType']}, 得到 {tool.get('returnType')}"
            )
        if "parameters" in expected:
            assert tool.get("parameters") == expected["parameters"], (
                f"{name} parameters: 期望 {expected['parameters']}, 得到 {tool.get('parameters')}"
            )

    def _assert_property(self, data, name):
        prop = self._find_property(data, name)
        expected = EXPECTED_PROPERTIES[name]
        assert prop["schema"] == expected["schema"], (
            f"{name} schema: 期望 {expected['schema']}, 得到 {prop['schema']}"
        )
        assert prop["readable"] == expected["readable"], (
            f"{name} readable: 期望 {expected['readable']}, 得到 {prop['readable']}"
        )
        assert prop["writable"] == expected["writable"], (
            f"{name} writable: 期望 {expected['writable']}, 得到 {prop['writable']}"
        )
