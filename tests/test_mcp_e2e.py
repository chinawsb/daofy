#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP 端到端协议测试 — 工具注册 / 分发 / 错误处理一致性

测试策略:
  1. 工具注册一致性 — TOOL_NAMES ↔ TOOL_SHORT_DESC ↔ list_tools() ↔ _TOOL_HANDLERS
  2. 帮助文档覆盖 — 每个工具都能通过 tool_help 获取完整文档
  3. 错误处理模式 — CallToolResult 构建、异常捕获、参数校验
  4. 分发完整性 — 无孤立工具或 handler
"""

import re
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.tool_docs import TOOL_NAMES, TOOL_SHORT_DESC


# ═══════════════════════════════════════════════════════════════
# 工具注册一致性
# ═══════════════════════════════════════════════════════════════

class TestToolRegistrationConsistency:
    """验证工具注册表完整性"""

    # server.py 中 list_tools() 注册的工具名（人工维护的引用列表）
    # 必须与 TOOL_NAMES 完全一致
    LIST_TOOLS_EXPECTED = {
        "delphi_project", "delphi_kb", "delphi_file", "manage_component",
        "check_environment", "async_task", "package", "get_coding_rules",
        "code_hosting", "tool_help", "experience", "daofy_update",
        "automate_delphi", "generate_copyright", "delphi_rtti",
        "ocr",
        "lazarus_compile", "lazarus_project", "lazarus_kb", "lazarus_file",
    }

    # _TOOL_HANDLERS 中已注册的 handler 名（含别名）
    # "file_tool" 是 "delphi_file" 的向后兼容别名
    HANDLER_NAMES_EXPECTED = {
        "delphi_project", "delphi_kb", "delphi_file", "file_tool",
        "manage_component", "check_environment", "async_task",
        "package", "get_coding_rules", "code_hosting",
        "tool_help", "experience", "daofy_update",
        "automate_delphi", "generate_copyright", "delphi_rtti",
        "ocr",
        "lazarus_compile", "lazarus_project", "lazarus_kb", "lazarus_file",
    }

    HANDLER_ALLOWED_ALIASES = {"file_tool"}

    def test_tool_names_match_list_tools(self):
        """TOOL_NAMES 必须与 list_tools() 注册的工具一致"""
        assert set(TOOL_NAMES) == self.LIST_TOOLS_EXPECTED, (
            f"TOOL_NAMES mismatch. "
            f"Missing: {self.LIST_TOOLS_EXPECTED - set(TOOL_NAMES)}. "
            f"Extra: {set(TOOL_NAMES) - self.LIST_TOOLS_EXPECTED}"
        )

    def test_all_tools_have_short_desc(self):
        """每个工具都有简短说明（显示在 list_tools 的 description 字段）"""
        for name in TOOL_NAMES:
            assert name in TOOL_SHORT_DESC, f"{name} missing from TOOL_SHORT_DESC"
            desc = TOOL_SHORT_DESC[name]
            assert len(desc) > 10, f"{name} TOOL_SHORT_DESC too short: {desc!r}"

    def test_delphi_file_short_desc_routes_builtin_file_tools(self):
        """list_tools 的 delphi_file 描述必须约束 Agent 内置 Read/Edit/Write。"""
        desc = TOOL_SHORT_DESC["delphi_file"]
        assert "Read/Edit/Write" in desc
        assert "Delphi 文件专用" in desc
        assert "读取" in desc
        assert ".pas" in desc
        assert ".dfm" in desc
        assert "apply_patch" in desc

    def test_tool_names_deduplicated(self):
        """TOOL_NAMES 无重复条目"""
        assert len(TOOL_NAMES) == len(set(TOOL_NAMES)), "TOOL_NAMES has duplicates"

    def test_all_handler_names_have_tools(self):
        """每个 handler 名都有对应的 list_tools() 注册（别名除外）"""
        handler_set = self.HANDLER_NAMES_EXPECTED
        list_set = self.LIST_TOOLS_EXPECTED
        aliases = self.HANDLER_ALLOWED_ALIASES
        extra = handler_set - list_set - aliases
        assert not extra, f"Handlers without list_tools() entry: {extra}"

    def test_all_list_tools_have_handlers(self):
        """每个 list_tools() 注册的工具都有对应的 handler"""
        missing = self.LIST_TOOLS_EXPECTED - self.HANDLER_NAMES_EXPECTED
        assert not missing, f"list_tools() tools without handler: {missing}"


# ═══════════════════════════════════════════════════════════════
# 服务端分发逻辑（源码级验证）
# ═══════════════════════════════════════════════════════════════

class TestServerDispatch:
    """验证 server.py 的 _TOOL_HANDLERS 与 list_tools() 一致性

    通过解析 server.py 源码提取工具名和 handler 名做交叉验证。
    这是运行时可验证的合约检查。
    """

    SERVER_PATH = Path(__file__).parent.parent / "src" / "server.py"

    def test_initialize_instructions_are_registered(self):
        """MCP initialize 响应必须携带 instructions，供客户端注入系统上下文。"""
        source = self.SERVER_PATH.read_text(encoding="utf-8")
        assert "MCP_SERVER_INSTRUCTIONS" in source
        assert "MCP_SERVER_DESCRIPTION" in source
        assert "instructions=MCP_SERVER_INSTRUCTIONS" in source
        assert "version=__version__" in source
        assert "description=MCP_SERVER_DESCRIPTION" in source

        instructions_start = source.find("MCP_SERVER_INSTRUCTIONS")
        instructions_end = source.find("\n", instructions_start + len("MCP_SERVER_INSTRUCTIONS"))
        instructions_block = source[instructions_start:instructions_end + 200]
        assert "delphi_file" in instructions_block
        assert "get_coding_rules" in instructions_block
        assert "tool_help" in instructions_block

    def test_raw_initialize_response_includes_description_and_instructions(self):
        """Raw JSON-RPC initialize must expose serverInfo.description and instructions."""
        env = os.environ.copy()
        env.update({
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "DAOFY_AGENT_SKILL_INSTALL": "off",
        })
        proc = subprocess.Popen(
            [sys.executable, str(self.SERVER_PATH)],
            cwd=str(self.SERVER_PATH.parent.parent),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "pytest-init-probe", "version": "0.1"},
            },
        }
        try:
            assert proc.stdin is not None
            assert proc.stdout is not None
            proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            line = ""
            deadline = time.time() + 30
            while time.time() < deadline:
                line = proc.stdout.readline()
                if line:
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
            assert line, "Daofy server did not return an initialize response"
            payload = json.loads(line)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)

        result = payload["result"]
        assert result["instructions"]
        assert "delphi_file" in result["instructions"]
        assert result["serverInfo"]["description"]
        assert "Delphi 项目编译" in result["serverInfo"]["description"]

    @classmethod
    def _extract_list_tool_names(cls) -> set:
        """从 registry.collect_tools() 获取 list_tools() 中注册的工具名

        Phase 4: list_tools() 已改为从 registry 动态生成 Tool 对象，
        不再在源码中硬编码 Tool(name=...) 块。
        Phase 5: 加入 Lazarus handler 模块。
        此处创建独立的 PluginRegistry 实例并注册相同的 handler dicts，
        与 server.py 启动时的注册逻辑完全一致。
        """
        from src.plugins.registry import PluginRegistry
        from src.plugins.core.handlers import CORE_HANDLERS, CORE_TOOL_DESCRIPTIONS, CORE_TOOL_SCHEMAS
        from src.plugins.delphi.handlers import DELPHI_HANDLERS, DELPHI_TOOL_DESCRIPTIONS, DELPHI_TOOL_SCHEMAS
        from src.plugins.lazarus.handlers import LAZARUS_HANDLERS, LAZARUS_TOOL_DESCRIPTIONS, LAZARUS_TOOL_SCHEMAS

        reg = PluginRegistry()
        reg.register_handlers(CORE_HANDLERS, CORE_TOOL_DESCRIPTIONS, CORE_TOOL_SCHEMAS, owner="core")
        reg.register_handlers(
            DELPHI_HANDLERS, DELPHI_TOOL_DESCRIPTIONS, DELPHI_TOOL_SCHEMAS,
            owner="delphi", aliases={"file_tool"}
        )
        reg.register_handlers(
            LAZARUS_HANDLERS, LAZARUS_TOOL_DESCRIPTIONS, LAZARUS_TOOL_SCHEMAS,
            owner="lazarus",
        )
        return {td.name for td in reg.collect_tools()}

    @classmethod
    def _extract_handler_names(cls) -> set:
        """从插件 handlers 模块提取已注册的工具名"""
        # Phase 3: handler 已提取到 src/plugins/{core,delphi,lazarus}/handlers.py
        core_path = Path(__file__).parent.parent / "src" / "plugins" / "core" / "handlers.py"
        delphi_path = Path(__file__).parent.parent / "src" / "plugins" / "delphi" / "handlers.py"
        lazarus_path = Path(__file__).parent.parent / "src" / "plugins" / "lazarus" / "handlers.py"
        names: set = set()
        for path in (core_path, delphi_path, lazarus_path):
            if not path.exists():
                continue
            source = path.read_text(encoding="utf-8")
            match = re.search(
                r"(?:CORE_HANDLERS|DELPHI_HANDLERS|LAZARUS_HANDLERS)"
                r"(?::\s*\w+(?:\[.*?\])?)?\s*=\s*\{(.*?)\}",
                source, re.DOTALL,
            )
            if match:
                names.update(re.findall(r'"(\w+)"\s*:', match.group(1)))
        assert names, "Cannot find handler registrations in plugin modules"
        return names

    def test_list_tools_vs_handler_dispatch(self):
        """list_tools() 注册的工具全部在插件 handlers 中有对应 handler"""
        list_names = self._extract_list_tool_names()
        handler_names = self._extract_handler_names()

        missing = list_names - handler_names
        assert not missing, (
            f"Tools registered in list_tools() without handler: {missing}"
        )

    def test_no_orphan_handlers(self):
        """插件 handlers 中的 handler 全部在 list_tools() 中有对应注册（别名除外）"""
        list_names = self._extract_list_tool_names()
        handler_names = self._extract_handler_names()

        allowed_aliases = {"file_tool"}  # delphi_file 的向后兼容别名
        extra = handler_names - list_names - allowed_aliases
        assert not extra, (
            f"Handlers without list_tools() registration: {extra}"
        )


# ═══════════════════════════════════════════════════════════════
# 工具帮助文档覆盖
# ═══════════════════════════════════════════════════════════════

class TestToolHelpCoverage:
    """验证 tool_help 为每个工具提供完整文档"""

    def test_tool_help_returns_for_each_tool(self):
        """每个已注册的工具都能通过 get_tool_help 获取文档"""
        from src.tools.tool_help import get_tool_help

        for name in TOOL_NAMES:
            result = get_tool_help(tool_name=name)
            assert isinstance(result, dict), (
                f"tool_help('{name}') returned {type(result)}, expected dict"
            )
            # 必须有实质内容 — 不同工具返回不同的 key
            content_keys = ["summary", "tool_name", "description", "content", "help", "status"]
            has_content = any(result.get(k) for k in content_keys)
            assert has_content, f"tool_help('{name}') returned empty: {result}"

    def test_tool_help_unknown_returns_error(self):
        """未知工具名返回错误标识"""
        from src.tools.tool_help import get_tool_help

        result = get_tool_help(tool_name="nonexistent_tool")
        assert isinstance(result, dict)
        text = str(result).lower()
        assert any(
            word in text for word in ["未知", "unknown", "not found", "错误", "error"]
        ), f"Expected error indication, got: {result}"


# ═══════════════════════════════════════════════════════════════
# CallToolResult 格式与错误处理
# ═══════════════════════════════════════════════════════════════

class TestCallToolResult:
    """验证 MCP 返回结果格式"""

    def test_error_result_structure(self):
        """验证错误返回的 CallToolResult 格式"""
        from mcp.types import CallToolResult, TextContent

        result = CallToolResult(
            content=[TextContent(type="text", text='{"error": "test error"}')],
            isError=True
        )
        assert result.isError is True
        assert len(result.content) == 1
        assert isinstance(result.content[0].text, str)
        # 必须可 JSON 解析
        parsed = json.loads(result.content[0].text)
        assert "error" in parsed

    def test_success_result_structure(self):
        """验证成功返回的 CallToolResult 格式"""
        from mcp.types import CallToolResult, TextContent

        result = CallToolResult(
            content=[TextContent(type="text", text='{"success": true, "data": "ok"}')],
            isError=False
        )
        assert result.isError is False
        parsed = json.loads(result.content[0].text)
        assert parsed.get("success") is True

    def test_tool_help_names_serializable(self):
        """TOOL_NAMES 可 JSON 序列化（供 tool_help 的 enum 字段使用）"""
        serialized = json.dumps(TOOL_NAMES, ensure_ascii=False)
        assert isinstance(serialized, str)
        assert "delphi_project" in serialized

    @pytest.mark.asyncio
    async def test_project_tool_missing_action_returns_error(self):
        """project 工具缺失必需 action 参数时返回错误"""
        from src.tools.project import handle_project

        result = await handle_project()
        assert isinstance(result, dict)
        # 应包含错误信息
        assert "error" in result or "message" in result

    def test_tool_help_validates_tool_name(self):
        """tool_help 的参数校验"""
        from src.tools.tool_help import get_tool_help

        # 空字符串应返回错误
        result = get_tool_help(tool_name="")
        text = str(result).lower()
        assert any(w in text for w in ["未知", "unknown", "错误", "error", "required"])


# ═══════════════════════════════════════════════════════════════
# 旧 test_mcp_tools.py 的关键测试迁移
# ═══════════════════════════════════════════════════════════════

class TestMigratedMCPTools:
    """从 test_mcp_tools.py 迁移的关键注册一致性测试"""

    def test_all_list_tools_have_docs(self):
        """list_tools() 中的每个工具都有 TOOL_HELP_DOCS 文档（含 summary）"""
        from src.tool_docs import TOOL_HELP_DOCS

        for name in TOOL_NAMES:
            assert name in TOOL_HELP_DOCS, (
                f"{name} missing from TOOL_HELP_DOCS"
            )
            doc = TOOL_HELP_DOCS[name]
            assert "summary" in doc, f"{name} doc missing 'summary'"

    def test_tool_help_docs_not_empty(self):
        """每个工具的 TOOL_HELP_DOCS 非空"""
        from src.tool_docs import TOOL_HELP_DOCS

        for name, doc in TOOL_HELP_DOCS.items():
            assert len(str(doc)) > 50, f"{name} TOOL_HELP_DOCS too short"


# ═══════════════════════════════════════════════════════════════
# 工具 inputSchema 完整性（2026-06-07 用户反馈 bug 修复回归）
# ═══════════════════════════════════════════════════════════════

class TestToolSchemaCompleteness:
    """验证工具 inputSchema 声明了所有 handler 中实际读取的参数

    历史 bug (2026-06-07 用户反馈):
      - async_task 的 long_poll_seconds 在 src/tools/async_tasks.py:325 中读取
        (arguments.get("long_poll_seconds", 0))，但未在 inputSchema 中声明，
        导致 MCP 客户端（Claude Desktop、Qoder 等）静默丢弃该参数
      - delphi_file write 的 force/old_content 参数必须在 inputSchema 中声明，
        否则 MCP 客户端会静默丢弃这些安全控制参数

    Phase 4: schema 已迁移到插件 handler 模块，由 registry 统一收集。
    测试直接从 handler 模块导入 TOOL_SCHEMAS + TOOL_DESCRIPTIONS。
    """

    @classmethod
    def _get_all_schemas(cls) -> dict:
        """从 handler 模块导入所有工具 schema"""
        from src.plugins.core.handlers import CORE_TOOL_SCHEMAS
        from src.plugins.delphi.handlers import DELPHI_TOOL_SCHEMAS
        return {**CORE_TOOL_SCHEMAS, **DELPHI_TOOL_SCHEMAS}

    @classmethod
    def _get_all_descriptions(cls) -> dict:
        """从 handler 模块导入所有工具描述"""
        from src.plugins.core.handlers import CORE_TOOL_DESCRIPTIONS
        from src.plugins.delphi.handlers import DELPHI_TOOL_DESCRIPTIONS
        return {**CORE_TOOL_DESCRIPTIONS, **DELPHI_TOOL_DESCRIPTIONS}

    def test_async_task_schema_declares_long_poll_seconds(self):
        """async_task inputSchema 必须声明 long_poll_seconds（与 handler 中 arguments.get 一致）"""
        schema = self._get_all_schemas()["async_task"]
        props = schema.get("properties", {})
        assert "long_poll_seconds" in props, (
            "async_task inputSchema missing 'long_poll_seconds' declaration. "
            "MCP 客户端会因 schema mismatch 静默丢弃该参数，导致长轮询失效。"
        )
        lps = props["long_poll_seconds"]
        assert lps.get("type") == "integer", "long_poll_seconds 应声明为 integer"
        assert lps.get("default") == 0, "long_poll_seconds 默认值应为 0"

    def test_delphi_file_schema_declares_write_safety_params(self):
        """delphi_file inputSchema 必须声明 write 的 force/old_content 安全参数，且不再声明 batch_write"""
        import json as _json

        schema = self._get_all_schemas()["delphi_file"]
        props = schema.get("properties", {})
        action_enum = props.get("action", {}).get("enum", [])

        # action 不能有已移除的 batch_write
        assert "batch_write" not in action_enum, "delphi_file schema must not expose removed batch_write action"
        assert "replace" in action_enum, "delphi_file schema missing replace action"
        assert "insert" in action_enum, "delphi_file schema missing insert action"
        assert "delete" in action_enum, "delphi_file schema missing delete action"

        # edits 声明
        assert "edits" in props, "delphi_file schema missing 'edits' declaration"
        edits_items = props["edits"].get("items", {})
        edits_props = edits_items.get("properties", {})
        assert "position" in edits_props, "delphi_file schema missing insert position"
        assert edits_items.get("required") == ["start_line"], "edits items required should be ['start_line']"

        # old_content 带非空校验说明
        assert "old_content" in edits_props, "delphi_file schema missing per-edit old_content"
        assert "非空" in edits_props["old_content"].get("description", ""), "old_content schema must document non-empty guard requirement"

        # 已移除的参数不能出现
        schema_str = _json.dumps(schema, ensure_ascii=False)
        assert "expected_old_hash" not in schema_str, "delphi_file schema must not expose removed expected_old_hash"
        assert "base_file_sha256" not in schema_str, "delphi_file schema must not expose removed base_file_sha256"
        assert "preview" not in schema_str, "delphi_file schema must not expose removed preview parameter"

        # write 安全参数
        assert "force" in props, "delphi_file schema missing 'force' parameter"
        assert props["force"].get("type") == "boolean", "force 应声明为 boolean"
        assert props["force"].get("default") is False, "force 默认值应为 False"
        assert "dry_run" in props, "delphi_file schema must expose dry_run for write previews"

    def test_delphi_file_schema_matches_read_insert_and_grep_contract(self):
        """delphi_file schema 必须与 file_tool 的现行参数契约一致。"""
        schema = self._get_all_schemas()["delphi_file"]
        props = schema.get("properties", {})

        file_path_schema = props.get("file_path", {})
        variants = file_path_schema.get("oneOf", [])
        assert {variant.get("type") for variant in variants} == {"string", "array"}
        array_variant = next(variant for variant in variants if variant.get("type") == "array")
        assert array_variant.get("items", {}).get("type") == "string"

        for name in (
            "start_line", "end_line", "limit", "pattern", "patterns",
            "include", "exclude", "filter_pattern", "exclude_pattern",
        ):
            assert name in props, f"delphi_file schema missing {name!r}"

        assert props["patterns"].get("type") == "array"
        assert props["patterns"].get("items", {}).get("type") == "string"
        assert "search_pattern" not in props
        assert "line_number" not in props

        edit_props = props["edits"]["items"]["properties"]
        assert edit_props["position"].get("type") == "string"
        assert edit_props["position"].get("enum") == ["before", "after"]

    def test_tool_help_schema_declares_optional_action(self):
        """tool_help 的 action 过滤参数必须在 MCP schema 中公开。"""
        schema = self._get_all_schemas()["tool_help"]
        props = schema.get("properties", {})
        assert "action" in props, "tool_help schema missing optional 'action'"
        assert props["action"].get("type") == "string"
        assert "action" not in schema.get("required", [])

    def test_delphi_project_schema_declares_real_extra_args(self):
        """delphi_project 的真实编译附加参数仍必须在 schema 中声明。"""
        schema = self._get_all_schemas()["delphi_project"]
        props = schema.get("properties", {})
        assert "extra_args" in props, "delphi_project schema missing 'extra_args'"
        ea = props["extra_args"]
        assert ea.get("type") == "array", "extra_args 应声明为 array"
        assert ea.get("items", {}).get("type") == "string", "extra_args items 应为 string"
        assert "占位" not in ea.get("description", ""), "extra_args 不应被描述为占位参数"

    def test_dynamic_tool_descriptions_direct_to_tool_help(self):
        """复杂工具的短描述应指导模型按 action 查询帮助，而不是猜参数。"""
        descriptions = self._get_all_descriptions()
        for tool_name in (
            "code_hosting", "experience", "daofy_update", "generate_copyright", "ocr",
            "delphi_project", "delphi_kb", "manage_component", "check_environment",
            "package", "automate_delphi", "delphi_rtti",
        ):
            desc = descriptions[tool_name]
            assert "tool_help(tool_name=" in desc, f"{tool_name} description missing tool_help guidance"
            assert "action='<action>'" in desc, f"{tool_name} description missing action guidance"

    def test_dynamic_schemas_do_not_expose_fake_extra_args(self):
        """不支持通用 extra_args 的工具不得暴露伪占位字段。"""
        schemas = self._get_all_schemas()
        for tool_name in (
            "code_hosting", "experience", "daofy_update", "generate_copyright", "ocr",
            "delphi_kb", "manage_component", "check_environment", "package",
            "automate_delphi", "delphi_rtti",
        ):
            assert "extra_args" not in schemas[tool_name].get("properties", {}), tool_name

    def test_server_instructions_use_public_tool_help_action(self):
        """服务器总指令必须使用 tool_help 的公开参数名 action。"""
        source = (Path(__file__).parent.parent / "src" / "server.py").read_text(encoding="utf-8-sig")
        assert "tool_help(tool_name, action)" in source
        assert "action_name" not in source

    def test_delphi_file_schema_mentions_builtin_read_edit_write(self):
        """schema 描述也要给客户端路由模型明确提示，读取 Delphi 文件也走 delphi_file。"""
        desc = self._get_all_descriptions()["delphi_file"]
        assert "Read/Edit/Write" in desc
        assert "即使只是读取" in desc
        assert ".pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx" in desc

    def test_handler_arguments_match_schema_known_gaps_only(self):
        """回归检查：本次用户反馈的具体 schema 缺失已全部修复

        全量扫描（覆盖所有 handler 的 arguments.get）容易误报
        （如 server.py 内部字典键、read_source_file 等独立工具的字段），
        所以此处只对本次修复涉及的两个 handler 做精准验证。
        """
        # 1) async_tasks.py 中 long_poll_seconds 必须能正常读取（handler 逻辑无回归）
        from src.tools.async_tasks import get_task_status  # noqa: F401
        # 2) file_tool.py 中 force 必须能正常读取（handler 逻辑无回归）
        from src.tools.file_tool import handle_write  # noqa: F401
        # 3) 双方各自 handler 中确实读取这些参数（静态扫描确认）
        async_src = (Path(__file__).parent.parent / "src" / "tools" / "async_tasks.py").read_text(encoding="utf-8")
        file_src = (Path(__file__).parent.parent / "src" / "tools" / "file_tool.py").read_text(encoding="utf-8")
        assert 'arguments.get("long_poll_seconds", 0)' in async_src, (
            "async_tasks.py handler 移除了 long_poll_seconds 读取逻辑"
        )
        assert 'arguments.get("force", False)' in file_src or '"force"' in file_src, (
            "file_tool.py handle_write 移除了 force 读取逻辑"
        )
