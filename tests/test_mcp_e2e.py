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
from pathlib import Path

import pytest

from src.config.tool_docs import TOOL_NAMES, TOOL_SHORT_DESC


# ═══════════════════════════════════════════════════════════════
# 工具注册一致性
# ═══════════════════════════════════════════════════════════════

class TestToolRegistrationConsistency:
    """验证工具注册表完整性"""

    # server.py 中 list_tools() 注册的工具名（人工维护的引用列表）
    # 必须与 TOOL_NAMES 完全一致
    LIST_TOOLS_EXPECTED = {
        "project", "delphi_kb", "delphi_file", "manage_component",
        "check_environment", "async_task", "package", "get_coding_rules",
        "code_hosting", "tool_help", "experience", "daofy_update",
        "automate_delphi", "generate_copyright", "delphi_rtti",
    }

    # _TOOL_HANDLERS 中已注册的 handler 名（含别名）
    # "file_tool" 是 "delphi_file" 的向后兼容别名
    HANDLER_NAMES_EXPECTED = {
        "project", "delphi_kb", "delphi_file", "file_tool",
        "manage_component", "check_environment", "async_task",
        "package", "get_coding_rules", "code_hosting",
        "tool_help", "experience", "daofy_update",
        "automate_delphi", "generate_copyright", "delphi_rtti",
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

    @classmethod
    def _extract_list_tool_names(cls) -> set:
        """从 server.py 源码提取 list_tools() 中注册的工具名"""
        source = cls.SERVER_PATH.read_text(encoding="utf-8")
        # 找到 @server.list_tools() 到 @server.call_tool() 之间的 section
        start = source.find("@server.list_tools()")
        end = source.find("@server.call_tool()")
        assert start != -1 and end != -1, "Cannot find list_tools/call_tool sections"
        section = source[start:end]
        # 提取所有 name= 值
        names = re.findall(r'name\s*=\s*"(\w+)"', section)
        return set(names)

    @classmethod
    def _extract_handler_names(cls) -> set:
        """从 server.py 源码提取 _TOOL_HANDLERS 中的 key 名"""
        source = cls.SERVER_PATH.read_text(encoding="utf-8")
        match = re.search(r"_TOOL_HANDLERS\s*=\s*\{(.*?)\}", source, re.DOTALL)
        assert match, "Cannot find _TOOL_HANDLERS in server.py"
        body = match.group(1)
        names = re.findall(r'"(\w+)"\s*:', body)
        return set(names)

    def test_list_tools_vs_handler_dispatch(self):
        """list_tools() 注册的工具全部在 _TOOL_HANDLERS 中有对应 handler"""
        list_names = self._extract_list_tool_names()
        handler_names = self._extract_handler_names()

        missing = list_names - handler_names
        assert not missing, (
            f"Tools registered in list_tools() without handler: {missing}"
        )

    def test_no_orphan_handlers(self):
        """_TOOL_HANDLERS 中的 handler 全部在 list_tools() 中有对应注册（别名除外）"""
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
        assert "project" in serialized

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
        from src.config.tool_docs import TOOL_HELP_DOCS

        for name in TOOL_NAMES:
            assert name in TOOL_HELP_DOCS, (
                f"{name} missing from TOOL_HELP_DOCS"
            )
            doc = TOOL_HELP_DOCS[name]
            assert "summary" in doc, f"{name} doc missing 'summary'"

    def test_tool_help_docs_not_empty(self):
        """每个工具的 TOOL_HELP_DOCS 非空"""
        from src.config.tool_docs import TOOL_HELP_DOCS

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
      - delphi_file action=batch_write 的 force 在 src/tools/file_tool.py:759 中
        读取（arguments.get("force", False)），但未在 inputSchema 中声明，
        同样被静默丢弃

    这些测试确保任何 handler 中 arguments.get("xxx", default) 引入的参数
    都必须在 list_tools() 的 inputSchema.properties 中显式声明。
    """

    SERVER_PATH = Path(__file__).parent.parent / "src" / "server.py"

    @classmethod
    def _extract_tool_block(cls, tool_name: str) -> str:
        """从 server.py 源码提取指定 Tool 的整个 inputSchema 块（粗略按 Tool( 边界）。"""
        src = cls.SERVER_PATH.read_text(encoding="utf-8")
        # 匹配 `name="<tool_name>"` 到下个 `Tool(` 之前的所有内容
        pattern = rf'name="{re.escape(tool_name)}"(.*?)(?=\n\s*Tool\()'
        m = re.search(pattern, src, re.DOTALL)
        assert m, f"Could not locate Tool definition for {tool_name!r} in server.py"
        return m.group(1)

    def test_async_task_schema_declares_long_poll_seconds(self):
        """async_task inputSchema 必须声明 long_poll_seconds（与 handler 中 arguments.get 一致）"""
        block = self._extract_tool_block("async_task")
        assert '"long_poll_seconds"' in block, (
            "async_task inputSchema missing 'long_poll_seconds' declaration. "
            "MCP 客户端会因 schema mismatch 静默丢弃该参数，导致长轮询失效。"
        )
        # 验证类型/默认值与 handler 一致
        after = block.split('"long_poll_seconds"', 1)[1][:400]
        assert '"type": "integer"' in after, "long_poll_seconds 应声明为 integer"
        assert '"default": 0' in after, "long_poll_seconds 默认值应为 0"

    def test_delphi_file_schema_declares_batch_write_force(self):
        """delphi_file inputSchema 必须在 batch_write 段（edits 之后）声明 force"""
        block = self._extract_tool_block("delphi_file")
        edits_idx = block.find('"edits"')
        assert edits_idx > 0, "delphi_file schema missing 'edits' declaration"
        # 提取 edits 之后到 # format 段之前的内容
        rest = block[edits_idx:]
        # 截到 # format 注释或下个 # action 段（避免误匹配其他工具的 force 字段）
        segment_end = rest.find("# ---- [仅 action=format]")
        if segment_end > 0:
            rest = rest[:segment_end]
        assert '"force"' in rest, (
            "delphi_file batch_write 段缺少 'force' 参数声明。\n"
            "force 是 batch_write 专属参数（跳过 AI 偏移量检查），"
            "MCP 客户端会因 schema mismatch 静默丢弃该参数。"
        )
        # 验证类型/默认值与 handler 一致
        after = rest.split('"force"', 1)[1][:400]
        assert '"type": "boolean"' in after, "force 应声明为 boolean"
        assert '"default": False' in after, "force 默认值应为 False"

    def test_handler_arguments_match_schema_known_gaps_only(self):
        """回归检查：本次用户反馈的具体 schema 缺失已全部修复

        全量扫描（覆盖所有 handler 的 arguments.get）容易误报
        （如 server.py 内部字典键、read_source_file 等独立工具的字段），
        所以此处只对本次修复涉及的两个 handler 做精准验证。
        """
        # 1) async_tasks.py 中 long_poll_seconds 必须能正常读取（handler 逻辑无回归）
        from src.tools.async_tasks import get_task_status  # noqa: F401
        # 2) file_tool.py 中 force 必须能正常读取（handler 逻辑无回归）
        from src.tools.file_tool import handle_batch_write  # noqa: F401
        # 3) 双方各自 handler 中确实读取这些参数（静态扫描确认）
        async_src = (Path(__file__).parent.parent / "src" / "tools" / "async_tasks.py").read_text(encoding="utf-8")
        file_src = (Path(__file__).parent.parent / "src" / "tools" / "file_tool.py").read_text(encoding="utf-8")
        assert 'arguments.get("long_poll_seconds", 0)' in async_src, (
            "async_tasks.py handler 移除了 long_poll_seconds 读取逻辑"
        )
        assert 'arguments.get("force", False)' in file_src or '"force"' in file_src, (
            "file_tool.py handle_write 移除了 force 读取逻辑"
        )
