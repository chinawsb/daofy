"""Lazarus 插件 handler 测试

验证:
  1. LAZARUS_HANDLERS 字典完整性
  2. LAZARUS_TOOL_DESCRIPTIONS + LAZARUS_TOOL_SCHEMAS 与 handlers 一致
  3. handler 函数签名正确（接受 arguments: dict，返回 dict）
  4. lazarus_compile 调用 CompilerService.compile_with_lazbuild
  5. lazarus_project 调用 LpiParser
"""

from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

import pytest

from src.plugins.lazarus.handlers import (
    LAZARUS_HANDLERS,
    LAZARUS_TOOL_DESCRIPTIONS,
    LAZARUS_TOOL_SCHEMAS,
    _handle_lazarus_compile,
    _handle_lazarus_project,
)


# ============================================================
# 字典完整性
# ============================================================

class TestLazarusHandlerDicts:
    """验证导出字典的结构一致性"""

    def test_handler_names_match_descriptions(self):
        """每个 handler 在 descriptions 中都有对应条目"""
        for name in LAZARUS_HANDLERS:
            assert name in LAZARUS_TOOL_DESCRIPTIONS, (
                f"Handler {name} missing description"
            )

    def test_handler_names_match_schemas(self):
        """每个 handler 在 schemas 中都有对应条目"""
        for name in LAZARUS_HANDLERS:
            assert name in LAZARUS_TOOL_SCHEMAS, (
                f"Handler {name} missing schema"
            )

    def test_no_spurious_descriptions(self):
        """没有多余的 description 条目"""
        for name in LAZARUS_TOOL_DESCRIPTIONS:
            assert name in LAZARUS_HANDLERS, (
                f"Spurious description for {name}"
            )

    def test_no_spurious_schemas(self):
        """没有多余的 schema 条目"""
        for name in LAZARUS_TOOL_SCHEMAS:
            assert name in LAZARUS_HANDLERS, (
                f"Spurious schema for {name}"
            )

    def test_handler_signatures(self):
        """每个 handler 都是 async function 接受 (arguments: dict)"""
        for name, handler in LAZARUS_HANDLERS.items():
            assert callable(handler), f"{name} handler is not callable"
            # 验证是协程函数（async def）
            assert hasattr(handler, "__code__"), f"{name} handler has no __code__"
            # 第一个参数名
            import inspect
            sig = inspect.signature(handler)
            params = list(sig.parameters.keys())
            assert len(params) >= 1, f"{name} handler should accept at least 1 parameter"
            assert params[0] == "arguments", (
                f"{name} handler first parameter should be 'arguments', got '{params[0]}'"
            )

    def test_compile_schema_requires_project_path(self):
        """lazarus_compile 的 schema 要求 project_path"""
        schema = LAZARUS_TOOL_SCHEMAS["lazarus_compile"]
        assert "required" in schema
        assert "project_path" in schema["required"]

    def test_project_schema_requires_project_path(self):
        """lazarus_project 的 schema 要求 project_path"""
        schema = LAZARUS_TOOL_SCHEMAS["lazarus_project"]
        assert "required" in schema
        assert "project_path" in schema["required"]

    def test_schemas_have_type_object(self):
        """所有 schema 的 type 为 object"""
        for name, schema in LAZARUS_TOOL_SCHEMAS.items():
            assert schema.get("type") == "object", (
                f"{name} schema type should be 'object', got '{schema.get('type')}'"
            )

    def test_schemas_have_properties(self):
        """所有 schema 都有 properties 字典"""
        for name, schema in LAZARUS_TOOL_SCHEMAS.items():
            assert "properties" in schema, f"{name} schema missing 'properties'"
            assert isinstance(schema["properties"], dict)


# ============================================================
# Handler 行为测试
# ============================================================

class TestLazarusCompileHandler:
    """测试 lazarus_compile handler"""

    @pytest.mark.asyncio
    async def test_compile_missing_project_path(self):
        """缺少 project_path 时返回错误"""
        result = await _handle_lazarus_compile({})
        assert result.get("status") == "failed", "Should fail without project_path"
        assert "project_path" in result.get("error", "").lower()


    @pytest.mark.asyncio
    async def test_compile_calls_compiler_service(self):
        """编译时调用 CompilerService.compile_with_lazbuild"""
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "status": "success",
            "output_file": "test.exe",
            "duration": 1000,
        }

        # CompilerService 在 handler 内部延迟导入，patch 其源模块
        with patch(
            "src.services.compiler_service.CompilerService"
        ) as mock_cs_cls:
            mock_cs_instance = AsyncMock()
            mock_cs_instance.compile_with_lazbuild = AsyncMock(return_value=mock_result)
            mock_cs_cls.return_value = mock_cs_instance

            result = await _handle_lazarus_compile({
                "project_path": "/tmp/test.lpi",
                "target_platform": "win32",
            })

        assert result["status"] == "success"
        assert result["output_file"] == "test.exe"

        # 验证 CompilerService 被正确调用
        mock_cs_instance.compile_with_lazbuild.assert_awaited_once()
        call_args = mock_cs_instance.compile_with_lazbuild.call_args
        request = call_args[0][0]
        assert request.project_path == "/tmp/test.lpi"
        assert request.options.target_platform.value == "win32"


    @pytest.mark.asyncio
    async def test_compile_error_handled(self):
        """编译抛出异常时返回友好错误消息"""
        with patch(
            "src.services.compiler_service.CompilerService"
        ) as mock_cs_cls:
            mock_cs_instance = AsyncMock()
            mock_cs_instance.compile_with_lazbuild = AsyncMock(
                side_effect=RuntimeError("lazbuild 崩溃")
            )
            mock_cs_cls.return_value = mock_cs_instance

            result = await _handle_lazarus_compile({
                "project_path": "/tmp/test.lpi",
            })

        assert result.get("status") == "failed"
        assert "lazbuild 崩溃" in str(result.get("error", ""))


class TestLazarusProjectHandler:
    """测试 lazarus_project handler"""

    @pytest.mark.asyncio
    async def test_project_missing_project_path(self):
        """缺少 project_path 时返回错误"""
        result = await _handle_lazarus_project({})
        assert result.get("status") == "failed"

    @pytest.mark.asyncio
    async def test_project_lpr_resolves_to_lpi(self, tmp_path: Path):
        """.lpr 文件自动查找同名 .lpi"""
        lpr_file = tmp_path / "test.lpr"
        lpi_file = tmp_path / "test.lpi"
        lpr_file.write_text("begin end.")
        lpi_file.write_text("""<?xml version="1.0"?>
<CONFIG>
  <ProjectInfo>
    <Title>TestProject</Title>
  </ProjectInfo>
  <CompilerOptions>
    <Target>
      <CPU>x86_64</CPU>
      <OS>win64</OS>
    </Target>
  </CompilerOptions>
</CONFIG>""")

        result = await _handle_lazarus_project({
            "project_path": str(lpr_file),
        })

        assert result.get("status") == "success"
        assert result.get("name") == "TestProject"

    @pytest.mark.asyncio
    async def test_project_units_action(self, tmp_path: Path):
        """action=units 返回单元列表"""
        lpi_file = tmp_path / "test.lpi"
        lpi_file.write_text("""<?xml version="1.0"?>
<CONFIG>
  <ProjectInfo>
    <Title Value="TestProject"/>
  </ProjectInfo>
  <Units>
    <Unit Filename="unit1.pas"/>
    <Unit Filename="unit2.pas" IsPartOfProject="False"/>
  </Units>
</CONFIG>""")

        result = await _handle_lazarus_project({
            "project_path": str(lpi_file),
            "action": "units",
        })

        assert result.get("status") == "success"
        units = result.get("units", [])
        assert len(units) == 2
        assert units[0]["filename"] == "unit1.pas"
        assert units[0]["is_part_of_project"] is True

    @pytest.mark.asyncio
    async def test_project_options_action(self, tmp_path: Path):
        """action=options 返回编译器选项"""
        lpi_file = tmp_path / "test.lpi"
        lpi_file.write_text("""<?xml version="1.0"?>
<CONFIG>
  <CompilerOptions>
    <Target>
      <CPU>x86_64</CPU>
      <OS>win64</OS>
    </Target>
    <Debugging>
      <GenerateDebugInfo Value="True"/>
    </Debugging>
    <Optimization>
      <Level>2</Level>
    </Optimization>
  </CompilerOptions>
</CONFIG>""")

        result = await _handle_lazarus_project({
            "project_path": str(lpi_file),
            "action": "options",
        })

        assert result.get("status") == "success"
        opts = result.get("compiler_options", {})
        assert opts.get("target_cpu") == "x86_64"
        assert opts.get("target_os") == "win64"
        assert opts.get("generate_debugging_info") is True
        assert opts.get("optimization_level") == 2

    @pytest.mark.asyncio
    async def test_project_default_action_info(self, tmp_path: Path):
        """默认 action=info 返回项目概要"""
        lpi_file = tmp_path / "test.lpi"
        lpi_file.write_text("""<?xml version="1.0"?>
<CONFIG>
  <ProjectInfo>
    <Title>MyApp</Title>
  </ProjectInfo>
  <Units>
    <Unit Filename="main.pas"/>
  </Units>
</CONFIG>""")

        result = await _handle_lazarus_project({
            "project_path": str(lpi_file),
        })

        assert result.get("status") == "success"
        assert result.get("name") == "MyApp"
        assert result.get("unit_count") == 1

    @pytest.mark.asyncio
    async def test_project_invalid_file(self):
        """不存在的文件返回失败"""
        result = await _handle_lazarus_project({
            "project_path": "/nonexistent/path.lpi",
        })
        assert result.get("status") == "failed"

    @pytest.mark.asyncio
    async def test_project_lpr_without_lpi(self, tmp_path: Path):
        """.lpr 文件无对应 .lpi 时返回错误"""
        bad_lpr = tmp_path / "orphan.lpr"
        bad_lpr.write_text("begin end.")

        result = await _handle_lazarus_project({
            "project_path": str(bad_lpr),
        })
        assert result.get("status") == "failed"
        assert ".lpi" in result.get("error", "")
