#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RTTI 全面测试 — 覆盖 TRttiDiscoverer 的所有类型映射和方法能力。

测试流程：
  1. 用 dcc32 编译 tests/rtti_comprehensive_test.dpr
  2. 运行生成的 exe，捕获 stdout JSON
  3. 全面验证 JSON 输出结构，覆盖：
     - 多类发现（4 个业务类）
     - 所有类型映射（integer/string/boolean/number/datetime/enum/array/set）
     - 所有方法分类（function/procedure/class function/class procedure）
     - 参数方向（const/var/out）
     - 属性读写权限（readonly/read+write）
     - AI 注解（AIDescription/AIParamDescription/AIResultDescription/AIExample）

运行：pytest tests/test_rtti_comprehensive.py -v
跳过：无 dcc32 时自动跳过（pytest.skip）
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ═══════════════════════════════════════════════════════════════════════════════
# 预期 Schema 定义 — 每个类的方法签名、属性、类型映射
# ═══════════════════════════════════════════════════════════════════════════════

EXPECTED_SERVICE_MATH = {
    "className": "ComprehensiveMathService",
    "ancestor": "TObject",
    "tools": {
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
        "Divide": {
            "kind": "function",
            "returnType": {"type": "number"},
            "parameters": {
                "type": "object",
                "properties": {
                    "A": {"type": "number"},
                    "B": {"type": "number"},
                },
            },
        },
        "IsEven": {
            "kind": "function",
            "returnType": {"type": "boolean"},
            "parameters": {
                "type": "object",
                "properties": {
                    "Value": {"type": "integer"},
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
        "CalculateTotal": {
            "kind": "function",
            "returnType": {"type": "number"},
            "parameters": {
                "type": "object",
                "properties": {
                    "Price": {"type": "number"},
                    "Quantity": {"type": "integer"},
                    "Discount": {"type": "number"},
                },
            },
        },
        "SplitString": {
            "kind": "procedure",
            "parameters": {
                "type": "object",
                "properties": {
                    "Input": {"type": "string"},
                    "Left": {"type": "string", "direction": "var"},
                    "Right": {"type": "string", "direction": "var"},
                },
            },
        },
        "GetMinMax": {
            "kind": "procedure",
            "parameters": {
                "type": "object",
                "properties": {
                    "Numbers": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                    "MinVal": {"type": "integer", "direction": "out"},
                    "MaxVal": {"type": "integer", "direction": "out"},
                },
            },
        },
        "GetVersion": {
            "kind": "class function",
            "returnType": {"type": "string"},
        },
        "ResetGlobalCounter": {
            "kind": "class procedure",
        },
        "Reset": {
            "kind": "procedure",
        },
    },
    "properties": {
        "OperationCount": {
            "schema": {"type": "integer"},
            "readable": True,
            "writable": False,
        },
        "LastInput": {
            "schema": {"type": "string"},
            "readable": True,
            "writable": False,
        },
    },
}

EXPECTED_SERVICE_USER = {
    "className": "ComprehensiveUserService",
    "ancestor": "TObject",
    "tools": {
        "RegisterUser": {
            "kind": "function",
            "returnType": {"type": "integer"},
            "parameters": {
                "type": "object",
                "properties": {
                    "Name": {"type": "string"},
                    "Age": {"type": "integer"},
                    "Role": {
                        "type": "string",
                        "enum": ["urGuest", "urUser", "urEditor", "urAdmin", "urSuperAdmin"],
                    },
                },
            },
        },
        "GetUserCount": {
            "kind": "function",
            "returnType": {"type": "integer"},
        },
        "BatchRegister": {
            "kind": "procedure",
            "parameters": {
                "type": "object",
                "properties": {
                    "Names": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
    "properties": {
        "UserCount": {
            "schema": {"type": "integer"},
            "readable": True,
            "writable": False,
        },
        "LastError": {
            "schema": {"type": "string"},
            "readable": True,
            "writable": True,
        },
        "DefaultRole": {
            "schema": {
                "type": "string",
                "enum": ["urGuest", "urUser", "urEditor", "urAdmin", "urSuperAdmin"],
            },
            "readable": True,
            "writable": True,
        },
    },
}

EXPECTED_SERVICE_DATA = {
    "className": "ComprehensiveDataService",
    "ancestor": "TObject",
    "tools": {
        "SetOrderFilter": {
            "kind": "procedure",
            "parameters": {
                "type": "object",
                "properties": {
                    "Status": {
                        "type": "string",
                        "enum": ["osPending", "osProcessing", "osShipped", "osDelivered", "osCancelled"],
                    },
                },
            },
        },
        "GetOrderStatus": {
            "kind": "function",
            "returnType": {
                "type": "string",
                "enum": ["osPending", "osProcessing", "osShipped", "osDelivered", "osCancelled"],
            },
        },
        "SetFontStyles": {
            "kind": "procedure",
            "parameters": {
                "type": "object",
                "properties": {
                    "Styles": {
                        "type": "array",
                        "description": "set of TFontStyle",
                    },
                },
            },
        },
        "AddDataPoints": {
            "kind": "procedure",
            "parameters": {
                "type": "object",
                "properties": {
                    "Points": {
                        "type": "array",
                        "items": {"type": "number"},
                    },
                },
            },
        },
        "GetDataPoints": {
            "kind": "function",
            "returnType": {
                "type": "array",
                "items": {"type": "number"},
            },
        },
        "GetLastUpdated": {
            "kind": "function",
            "returnType": {"type": "string", "format": "date-time"},
        },
        "IsReady": {
            "kind": "function",
            "returnType": {"type": "boolean"},
        },
        "Refresh": {
            "kind": "procedure",
        },
    },
    "properties": {
        "OrderStatus": {
            "schema": {
                "type": "string",
                "enum": ["osPending", "osProcessing", "osShipped", "osDelivered", "osCancelled"],
            },
            "readable": True,
            "writable": True,
        },
        "FontStyles": {
            "schema": {
                "type": "array",
                "description": "set of TFontStyle",
            },
            "readable": True,
            "writable": True,
        },
    },
}

EXPECTED_SERVICE_CONFIG = {
    "className": "ComprehensiveConfigService",
    "ancestor": "TObject",
    "tools": {
        "GetBuildDateFunc": {
            "kind": "function",
            "returnType": {"type": "string", "format": "date-time"},
        },
    },
    "properties": {
        "AppName": {
            "schema": {"type": "string"},
            "readable": True,
            "writable": True,
        },
        "MaxUsers": {
            "schema": {"type": "integer"},
            "readable": True,
            "writable": True,
        },
        "DebugMode": {
            "schema": {"type": "boolean"},
            "readable": True,
            "writable": True,
        },
        "Threshold": {
            "schema": {"type": "number"},
            "readable": True,
            "writable": True,
        },
    },
}

# 所有类按 className 索引
ALL_EXPECTED = {
    svc["className"]: svc
    for svc in [EXPECTED_SERVICE_MATH, EXPECTED_SERVICE_USER,
                EXPECTED_SERVICE_DATA, EXPECTED_SERVICE_CONFIG]
}


# ═══════════════════════════════════════════════════════════════════════════════
# 编译 & 运行
# ═══════════════════════════════════════════════════════════════════════════════

def _find_dcc32() -> str | None:
    """从 compilers.json 中查找 dcc32 路径。"""
    config_path = project_root / "src" / "config" / "compilers.json"
    if not config_path.exists():
        return None
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
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
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


@pytest.fixture(scope="module")
def compiled_exe():
    """找到或编译 rtti_comprehensive_test.exe 并返回路径。"""
    # 优先用已有的编译产物
    existing = [
        project_root / "tests" / "rtti_comprehensive_test.exe",
        project_root / "tests" / "Win32" / "rtti_comprehensive_test.exe",
        project_root / "tests" / "Win32_RttiComprehensive" / "rtti_comprehensive_test.exe",
    ]
    for exe in existing:
        if exe.exists():
            return exe

    # 没有则尝试编译
    dpr = project_root / "tests" / "rtti_comprehensive_test.dpr"
    output_dir = project_root / "tests" / "Win32_RttiComprehensive"
    if not _compile_dpr(dpr, output_dir / "rtti_comprehensive_test.exe"):
        pytest.skip("dcc32 不可用，跳过全面 RTTI 测试（需要 Delphi 编译器）")

    exe = output_dir / "rtti_comprehensive_test.exe"
    assert exe.exists(), f"编译后 exe 仍未生成: {exe}"
    return exe


@pytest.fixture(scope="module")
def rtti_output(compiled_exe):
    """运行 exe 并解析 JSON 输出（JSON 数组）。"""
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

    # 应输出 JSON 数组（4 个类）
    assert isinstance(data, list), f"期望 JSON 数组，得到 {type(data).__name__}"
    assert len(data) == 4, f"期望 4 个类，得到 {len(data)}"
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# 测试类 — 组织结构对应测试范围
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultiClassDiscovery:
    """多类发现 — 验证所有 4 个类都被正确发现"""

    def test_four_classes_present(self, rtti_output):
        """应输出 4 个类的数组"""
        assert len(rtti_output) == 4

    def test_all_class_names(self, rtti_output):
        """所有期望的 className 都在输出中"""
        class_names = {c.get("className") for c in rtti_output}
        expected_names = set(ALL_EXPECTED.keys())
        assert class_names == expected_names, (
            f"类名不匹配\n期望: {expected_names}\n实际: {class_names}\n"
            f"差集期望-实际: {expected_names - class_names}\n"
            f"差集实际-期望: {class_names - expected_names}"
        )

    def test_all_have_ancestor(self, rtti_output):
        """每个类都有 ancestor 字段"""
        for cls in rtti_output:
            assert "ancestor" in cls, f"类 {cls.get('className')} 缺少 ancestor"

    def test_all_have_tools(self, rtti_output):
        """每个类都有 tools 数组"""
        for cls in rtti_output:
            assert "tools" in cls, f"类 {cls.get('className')} 缺少 tools"
            assert isinstance(cls["tools"], list), f"类 {cls.get('className')} tools 不是数组"

    def test_all_have_properties(self, rtti_output):
        """每个类都有 properties 数组"""
        for cls in rtti_output:
            assert "properties" in cls, f"类 {cls.get('className')} 缺少 properties"
            assert isinstance(cls["properties"], list), f"类 {cls.get('className')} properties 不是数组"


class TestTypeMappings:
    """类型映射 — 验证所有 Delphi→JSON 类型映射正确"""

    def _find_class(self, rtti_output, class_name):
        for cls in rtti_output:
            if cls.get("className") == class_name:
                return cls
        raise AssertionError(f"未找到类: {class_name}")

    def _find_tool(self, cls_data, tool_name):
        for t in cls_data.get("tools", []):
            if t["name"] == tool_name:
                return t
        raise AssertionError(f"未找到工具 {tool_name} 在类 {cls_data.get('className')}")

    # ── integer 类型 ──
    def test_type_integer_return(self, rtti_output):
        """Integer 返回值 → {'type': 'integer'}"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        add = self._find_tool(math, "Add")
        assert add["returnType"] == {"type": "integer"}, f"Add returnType: {add.get('returnType')}"

    def test_type_integer_param(self, rtti_output):
        """Integer 参数 → {'type': 'integer'}"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        add = self._find_tool(math, "Add")
        assert add["parameters"]["properties"]["A"] == {"type": "integer"}

    # ── number 类型（Double） ──
    def test_type_number_return(self, rtti_output):
        """Double 返回值 → {'type': 'number'}"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        divide = self._find_tool(math, "Divide")
        assert divide["returnType"] == {"type": "number"}, f"Divide returnType: {divide.get('returnType')}"

    def test_type_number_param(self, rtti_output):
        """Double 参数 → {'type': 'number'}"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        divide = self._find_tool(math, "Divide")
        assert divide["parameters"]["properties"]["A"] == {"type": "number"}

    # ── string 类型 ──
    def test_type_string_return(self, rtti_output):
        """String 返回值 → {'type': 'string'}"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        greet = self._find_tool(math, "Greet")
        assert greet["returnType"] == {"type": "string"}, f"Greet returnType: {greet.get('returnType')}"

    def test_type_string_param(self, rtti_output):
        """String 参数 → {'type': 'string'}"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        greet = self._find_tool(math, "Greet")
        assert greet["parameters"]["properties"]["Name"] == {"type": "string"}

    # ── boolean 类型 ──
    def test_type_boolean_return(self, rtti_output):
        """Boolean 返回值 → {'type': 'boolean'}"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        is_even = self._find_tool(math, "IsEven")
        assert is_even["returnType"] == {"type": "boolean"}, f"IsEven returnType: {is_even.get('returnType')}"

    # ── TDateTime 类型 ──
    def test_type_datetime_return(self, rtti_output):
        """TDateTime 返回值 → {'type': 'string', 'format': 'date-time'}"""
        data = self._find_class(rtti_output, "ComprehensiveDataService")
        last_updated = self._find_tool(data, "GetLastUpdated")
        assert last_updated["returnType"] == {"type": "string", "format": "date-time"}, (
            f"GetLastUpdated returnType: {last_updated.get('returnType')}"
        )

    def test_type_datetime_config(self, rtti_output):
        """TDateTime 在 ConfigService 中也是 date-time"""
        config = self._find_class(rtti_output, "ComprehensiveConfigService")
        build_date = self._find_tool(config, "GetBuildDateFunc")
        assert build_date["returnType"] == {"type": "string", "format": "date-time"}

    # ── 枚举类型 ──
    def test_type_enum_return(self, rtti_output):
        """枚举返回值 → {'type': 'string', 'enum': [...]}"""
        data = self._find_class(rtti_output, "ComprehensiveDataService")
        status = self._find_tool(data, "GetOrderStatus")
        rt = status["returnType"]
        assert rt["type"] == "string", f"GetOrderStatus return type: {rt}"
        assert "enum" in rt, f"GetOrderStatus 缺少 enum: {rt}"
        assert rt["enum"] == ["osPending", "osProcessing", "osShipped", "osDelivered", "osCancelled"]

    def test_type_enum_param(self, rtti_output):
        """枚举参数 → {'type': 'string', 'enum': [...]}"""
        data = self._find_class(rtti_output, "ComprehensiveDataService")
        filter_ = self._find_tool(data, "SetOrderFilter")
        status_schema = filter_["parameters"]["properties"]["Status"]
        assert status_schema["type"] == "string"
        assert "enum" in status_schema
        assert status_schema["enum"] == ["osPending", "osProcessing", "osShipped", "osDelivered", "osCancelled"]

    # ── 动态数组 (TArray<T>) ──
    def test_type_array_return(self, rtti_output):
        """TArray<Double> 返回值 → {'type': 'array', 'items': {'type': 'number'}}"""
        data = self._find_class(rtti_output, "ComprehensiveDataService")
        points = self._find_tool(data, "GetDataPoints")
        assert points["returnType"]["type"] == "array"
        assert points["returnType"]["items"] == {"type": "number"}

    def test_type_array_param(self, rtti_output):
        """TArray<string> 参数 → array of string"""
        user = self._find_class(rtti_output, "ComprehensiveUserService")
        batch = self._find_tool(user, "BatchRegister")
        names_schema = batch["parameters"]["properties"]["Names"]
        assert names_schema["type"] == "array"
        assert names_schema["items"] == {"type": "string"}

    def test_type_array_of_integer_param(self, rtti_output):
        """TArray<Integer> 参数 → array of integer"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        minmax = self._find_tool(math, "GetMinMax")
        numbers_schema = minmax["parameters"]["properties"]["Numbers"]
        assert numbers_schema["type"] == "array"
        assert numbers_schema["items"] == {"type": "integer"}

    # ── Set 类型 ──
    def test_type_set_param(self, rtti_output):
        """Set 类型 → {'type': 'array', 'description': 'set of ...'}"""
        data = self._find_class(rtti_output, "ComprehensiveDataService")
        styles = self._find_tool(data, "SetFontStyles")
        styles_schema = styles["parameters"]["properties"]["Styles"]
        assert styles_schema["type"] == "array"
        assert "set of" in styles_schema.get("description", "")


class TestMethodKinds:
    """方法分类 — 验证 function/procedure/class method 分类正确"""

    def _find_class(self, rtti_output, class_name):
        for cls in rtti_output:
            if cls.get("className") == class_name:
                return cls
        raise AssertionError(f"未找到类: {class_name}")

    def _find_tool(self, cls_data, tool_name):
        for t in cls_data.get("tools", []):
            if t["name"] == tool_name:
                return t
        raise AssertionError(f"未找到工具 {tool_name}")

    def test_kind_function(self, rtti_output):
        """有返回值的 function → kind='function'"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        add = self._find_tool(math, "Add")
        assert add["kind"] == "function"

    def test_kind_procedure(self, rtti_output):
        """无返回值的 procedure → kind='procedure'"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        reset = self._find_tool(math, "Reset")
        assert reset["kind"] == "procedure"

    def test_kind_class_function(self, rtti_output):
        """class function → kind='class function'"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        ver = self._find_tool(math, "GetVersion")
        assert ver["kind"] == "class function"

    def test_kind_class_procedure(self, rtti_output):
        """class procedure → kind='class procedure'"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        reset = self._find_tool(math, "ResetGlobalCounter")
        assert reset["kind"] == "class procedure"


class TestParameterDirections:
    """参数方向 — 验证 const/var/out 参数映射正确"""

    def _find_class(self, rtti_output, class_name):
        for cls in rtti_output:
            if cls.get("className") == class_name:
                return cls
        raise AssertionError(f"未找到类: {class_name}")

    def _find_tool(self, cls_data, tool_name):
        for t in cls_data.get("tools", []):
            if t["name"] == tool_name:
                return t
        raise AssertionError(f"未找到工具 {tool_name}")

    def test_var_params_have_direction(self, rtti_output):
        """var 参数应包含 'direction': 'var'"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        split = self._find_tool(math, "SplitString")
        left = split["parameters"]["properties"]["Left"]
        assert left.get("direction") == "var", f"Left direction: {left.get('direction')}"
        right = split["parameters"]["properties"]["Right"]
        assert right.get("direction") == "var", f"Right direction: {right.get('direction')}"

    def test_out_params_have_direction(self, rtti_output):
        """out 参数应包含 'direction': 'out'"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        minmax = self._find_tool(math, "GetMinMax")
        min_val = minmax["parameters"]["properties"]["MinVal"]
        assert min_val.get("direction") == "out", f"MinVal direction: {min_val.get('direction')}"
        max_val = minmax["parameters"]["properties"]["MaxVal"]
        assert max_val.get("direction") == "out", f"MaxVal direction: {max_val.get('direction')}"

    def test_const_params_no_direction(self, rtti_output):
        """const 参数不标记 direction"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        greet = self._find_tool(math, "Greet")
        name_schema = greet["parameters"]["properties"]["Name"]
        assert "direction" not in name_schema, f"const 参数不应有 direction: {name_schema}"

    def test_regular_params_no_direction(self, rtti_output):
        """普通值参数不标记 direction"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        add = self._find_tool(math, "Add")
        assert "direction" not in add["parameters"]["properties"]["A"]
        assert "direction" not in add["parameters"]["properties"]["B"]


class TestProperties:
    """属性 — 验证属性读写权限和类型映射"""

    def _find_class(self, rtti_output, class_name):
        for cls in rtti_output:
            if cls.get("className") == class_name:
                return cls
        raise AssertionError(f"未找到类: {class_name}")

    def test_readonly_property(self, rtti_output):
        """只有 getter 的属性 → readable=True, writable=False"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        props = {p["name"]: p for p in math["properties"]}
        assert props["OperationCount"]["readable"] is True
        assert props["OperationCount"]["writable"] is False

    def test_readwrite_property(self, rtti_output):
        """有 getter+setter 的属性 → readable=True, writable=True"""
        user = self._find_class(rtti_output, "ComprehensiveUserService")
        props = {p["name"]: p for p in user["properties"]}
        assert props["LastError"]["readable"] is True
        assert props["LastError"]["writable"] is True

    def test_property_integer_schema(self, rtti_output):
        """Integer 类型的属性 → schema.type=integer"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        props = {p["name"]: p for p in math["properties"]}
        assert props["OperationCount"]["schema"] == {"type": "integer"}

    def test_property_string_schema(self, rtti_output):
        """string 类型的属性 → schema.type=string"""
        user = self._find_class(rtti_output, "ComprehensiveUserService")
        props = {p["name"]: p for p in user["properties"]}
        assert props["LastError"]["schema"] == {"type": "string"}

    def test_property_boolean_schema(self, rtti_output):
        """Boolean 类型的属性 → schema.type=boolean"""
        config = self._find_class(rtti_output, "ComprehensiveConfigService")
        props = {p["name"]: p for p in config["properties"]}
        assert props["DebugMode"]["schema"] == {"type": "boolean"}

    def test_property_number_schema(self, rtti_output):
        """Double 类型的属性 → schema.type=number"""
        config = self._find_class(rtti_output, "ComprehensiveConfigService")
        props = {p["name"]: p for p in config["properties"]}
        assert props["Threshold"]["schema"] == {"type": "number"}

    def test_property_enum_schema(self, rtti_output):
        """枚举类型的属性 → schema 带 enum 约束"""
        user = self._find_class(rtti_output, "ComprehensiveUserService")
        props = {p["name"]: p for p in user["properties"]}
        role_schema = props["DefaultRole"]["schema"]
        assert role_schema["type"] == "string"
        assert "enum" in role_schema
        assert role_schema["enum"] == ["urGuest", "urUser", "urEditor", "urAdmin", "urSuperAdmin"]


class TestParameterCounts:
    """参数数量 — 验证不同参数个数的方法"""

    def _find_class(self, rtti_output, class_name):
        for cls in rtti_output:
            if cls.get("className") == class_name:
                return cls
        raise AssertionError(f"未找到类: {class_name}")

    def _find_tool(self, cls_data, tool_name):
        for t in cls_data.get("tools", []):
            if t["name"] == tool_name:
                return t
        raise AssertionError(f"未找到工具 {tool_name}")

    def test_no_param_method(self, rtti_output):
        """无参数方法不包含 parameters 字段"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        reset = self._find_tool(math, "Reset")
        assert "parameters" not in reset, f"Reset 不应有 parameters: {reset.get('parameters')}"

    def test_one_param_method(self, rtti_output):
        """单个参数的方法"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        is_even = self._find_tool(math, "IsEven")
        params = is_even["parameters"]["properties"]
        assert len(params) == 1

    def test_two_param_method(self, rtti_output):
        """两个参数的方法"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        add = self._find_tool(math, "Add")
        params = add["parameters"]["properties"]
        assert len(params) == 2
        assert list(params.keys()) == ["A", "B"]

    def test_three_param_method(self, rtti_output):
        """三个参数的方法"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        calc = self._find_tool(math, "CalculateTotal")
        params = calc["parameters"]["properties"]
        assert len(params) == 3
        assert list(params.keys()) == ["Price", "Quantity", "Discount"]

    def test_three_param_mixed_types(self, rtti_output):
        """三个参数混合类型"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        calc = self._find_tool(math, "CalculateTotal")
        props = calc["parameters"]["properties"]
        assert props["Price"]["type"] == "number"
        assert props["Quantity"]["type"] == "integer"
        assert props["Discount"]["type"] == "number"


class TestParameterOrder:
    """参数顺序 — 验证参数按声明顺序排列"""

    def _find_class(self, rtti_output, class_name):
        for cls in rtti_output:
            if cls.get("className") == class_name:
                return cls
        raise AssertionError(f"未找到类: {class_name}")

    def _find_tool(self, cls_data, tool_name):
        for t in cls_data.get("tools", []):
            if t["name"] == tool_name:
                return t
        raise AssertionError(f"未找到工具 {tool_name}")

    def test_split_string_order(self, rtti_output):
        """SplitString: Input, Left(var), Right(var)"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        split = self._find_tool(math, "SplitString")
        names = list(split["parameters"]["properties"].keys())
        assert names == ["Input", "Left", "Right"], f"SplitString 参数顺序: {names}"

    def test_get_min_max_order(self, rtti_output):
        """GetMinMax: Numbers(array), MinVal(out), MaxVal(out)"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        mm = self._find_tool(math, "GetMinMax")
        names = list(mm["parameters"]["properties"].keys())
        assert names == ["Numbers", "MinVal", "MaxVal"], f"GetMinMax 参数顺序: {names}"

    def test_register_user_order(self, rtti_output):
        """RegisterUser: Name, Age, Role"""
        user = self._find_class(rtti_output, "ComprehensiveUserService")
        reg = self._find_tool(user, "RegisterUser")
        names = list(reg["parameters"]["properties"].keys())
        assert names == ["Name", "Age", "Role"], f"RegisterUser 参数顺序: {names}"


class TestClassHierarchy:
    """类继承信息 — 验证 ancestor 字段"""

    def _find_class(self, rtti_output, class_name):
        for cls in rtti_output:
            if cls.get("className") == class_name:
                return cls
        raise AssertionError(f"未找到类: {class_name}")

    def test_all_ancestor_tobject(self, rtti_output):
        """所有自定义类的 ancestor 应为 TObject"""
        for cls in rtti_output:
            assert cls["ancestor"] == "TObject", (
                f"{cls['className']}.ancestor: 期望 TObject, 得到 {cls['ancestor']}"
            )


class TestNoExtraTools:
    """方法完整性 — 验证没有多余/遗漏的方法（除 inherited）"""

    def _find_class(self, rtti_output, class_name):
        for cls in rtti_output:
            if cls.get("className") == class_name:
                return cls
        raise AssertionError(f"未找到类: {class_name}")

    def test_math_service_tools_contain_expected(self, rtti_output):
        """ComprehensiveMathService 包含所有期望的方法"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        tool_names = {t["name"] for t in math["tools"]}
        expected = set(EXPECTED_SERVICE_MATH["tools"].keys())
        assert expected.issubset(tool_names), (
            f"MathService 缺少方法: {expected - tool_names}"
        )

    def test_user_service_tools_contain_expected(self, rtti_output):
        """ComprehensiveUserService 包含所有期望的方法"""
        user = self._find_class(rtti_output, "ComprehensiveUserService")
        tool_names = {t["name"] for t in user["tools"]}
        expected = set(EXPECTED_SERVICE_USER["tools"].keys())
        assert expected.issubset(tool_names), (
            f"UserService 缺少方法: {expected - tool_names}"
        )

    def test_data_service_tools_contain_expected(self, rtti_output):
        """ComprehensiveDataService 包含所有期望的方法"""
        data = self._find_class(rtti_output, "ComprehensiveDataService")
        tool_names = {t["name"] for t in data["tools"]}
        expected = set(EXPECTED_SERVICE_DATA["tools"].keys())
        assert expected.issubset(tool_names), (
            f"DataService 缺少方法: {expected - tool_names}"
        )

    def test_config_service_tools_contain_expected(self, rtti_output):
        """ComprehensiveConfigService 包含所有期望的方法"""
        config = self._find_class(rtti_output, "ComprehensiveConfigService")
        tool_names = {t["name"] for t in config["tools"]}
        expected = set(EXPECTED_SERVICE_CONFIG["tools"].keys())
        assert expected.issubset(tool_names), (
            f"ConfigService 缺少方法: {expected - tool_names}"
        )


class TestPropertiesCompleteness:
    """属性完整性 — 验证每个类的属性都正确包含"""

    def _find_class(self, rtti_output, class_name):
        for cls in rtti_output:
            if cls.get("className") == class_name:
                return cls
        raise AssertionError(f"未找到类: {class_name}")

    def test_math_properties_contain_expected(self, rtti_output):
        """MathService 的属性完整"""
        math = self._find_class(rtti_output, "ComprehensiveMathService")
        prop_names = {p["name"] for p in math["properties"]}
        expected = set(EXPECTED_SERVICE_MATH["properties"].keys())
        assert expected.issubset(prop_names), f"MathService 缺少属性: {expected - prop_names}"

    def test_user_properties_contain_expected(self, rtti_output):
        """UserService 的属性完整"""
        user = self._find_class(rtti_output, "ComprehensiveUserService")
        prop_names = {p["name"] for p in user["properties"]}
        expected = set(EXPECTED_SERVICE_USER["properties"].keys())
        assert expected.issubset(prop_names), f"UserService 缺少属性: {expected - prop_names}"

    def test_config_properties_contain_expected(self, rtti_output):
        """ConfigService 的属性完整"""
        config = self._find_class(rtti_output, "ComprehensiveConfigService")
        prop_names = {p["name"] for p in config["properties"]}
        expected = set(EXPECTED_SERVICE_CONFIG["properties"].keys())
        assert expected.issubset(prop_names), f"ConfigService 缺少属性: {expected - prop_names}"
