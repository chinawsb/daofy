#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
delphi_rtti MCP 工具测试 — TestDelphiRtti

测试 src/tools/delphi_rtti.py 的 handle_delphi_rtti 函数：
  - guide action 返回使用指南
  - discover action 参数验证和桥接调用
  - call action 参数验证和桥接调用
  - 错误处理（缺少参数、未知 action）
"""

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ═══════════════════════════════════════════════════════════════
# guide action
# ═══════════════════════════════════════════════════════════════

class TestGuide:
    """delphi_rtti(action='guide') 测试"""

    @pytest.mark.asyncio
    async def test_guide_returns_text(self):
        """guide 返回 RTTI 使用指南文本"""
        from src.tools.delphi_rtti import handle_delphi_rtti
        result = await handle_delphi_rtti({"action": "guide"})
        assert not result["isError"]
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert "Delphi RTTI" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_guide_no_app_path_needed(self):
        """guide 不需要 app_path 参数"""
        from src.tools.delphi_rtti import handle_delphi_rtti
        result = await handle_delphi_rtti({})
        assert not result["isError"]

    @pytest.mark.asyncio
    async def test_guide_contains_sections(self):
        """guide 包含关键章节"""
        from src.tools.delphi_rtti import handle_delphi_rtti
        result = await handle_delphi_rtti({"action": "guide"})
        text = result["content"][0]["text"]
        assert "三步工作流" in text or "## 概述" in text
        assert "类型映射" in text
        assert "故障排除" in text


# ═══════════════════════════════════════════════════════════════
# discover action
# ═══════════════════════════════════════════════════════════════

class TestDiscover:
    """delphi_rtti(action='discover') 测试"""

    @pytest.mark.asyncio
    async def test_discover_missing_app_path(self):
        """discover 缺少 app_path 应返回错误"""
        from src.tools.delphi_rtti import handle_delphi_rtti
        result = await handle_delphi_rtti({"action": "discover"})
        assert result["isError"]
        assert "app_path" in result["content"][0]["text"]

    @pytest.mark.asyncio
    @mock.patch("src.tools.delphi_rtti.get_rtti_bridge")
    async def test_discover_success(self, mock_get_bridge):
        """discover 成功返回能力清单"""
        mock_bridge = mock.MagicMock()
        mock_bridge.connect.return_value = {"status": "ok", "reused": True}
        mock_bridge.discover.return_value = {
            "status": "ok",
            "className": "TMainForm",
            "tools": [{"name": "CreateOrder", "kind": "function"}],
            "properties": [],
        }
        mock_get_bridge.return_value = mock_bridge

        from src.tools.delphi_rtti import handle_delphi_rtti
        result = await handle_delphi_rtti({
            "action": "discover",
            "app_path": "C:\\App.exe",
        })
        assert not result["isError"]
        assert "TMainForm" in result["content"][0]["text"]

    @pytest.mark.asyncio
    @mock.patch("src.tools.delphi_rtti.get_rtti_bridge")
    async def test_discover_with_class_filter(self, mock_get_bridge):
        """discover 支持 class_name 过滤"""
        mock_bridge = mock.MagicMock()
        mock_bridge.connect.return_value = {"status": "ok", "reused": True}
        mock_bridge.discover.return_value = {
            "status": "ok",
            "class": {"className": "TMainForm", "tools": []},
        }
        mock_get_bridge.return_value = mock_bridge

        from src.tools.delphi_rtti import handle_delphi_rtti
        result = await handle_delphi_rtti({
            "action": "discover",
            "app_path": "C:\\App.exe",
            "class_name": "TMainForm",
        })
        assert not result["isError"]
        mock_bridge.discover.assert_called_with("C:\\App.exe", "TMainForm", False)

    @pytest.mark.asyncio
    @mock.patch("src.tools.delphi_rtti.get_rtti_bridge")
    async def test_discover_with_force(self, mock_get_bridge):
        """discover 支持 force 参数"""
        mock_bridge = mock.MagicMock()
        mock_bridge.connect.return_value = {"status": "ok", "reused": True}
        mock_bridge.discover.return_value = {"status": "ok", "tools": []}
        mock_get_bridge.return_value = mock_bridge

        from src.tools.delphi_rtti import handle_delphi_rtti
        await handle_delphi_rtti({
            "action": "discover",
            "app_path": "C:\\App.exe",
            "force": True,
        })
        mock_bridge.discover.assert_called_with("C:\\App.exe", "", True)

    @pytest.mark.asyncio
    @mock.patch("src.tools.delphi_rtti.get_rtti_bridge")
    async def test_discover_connect_fails(self, mock_get_bridge):
        """连接失败时 discover 应返回错误"""
        mock_bridge = mock.MagicMock()
        mock_bridge.connect.return_value = {"status": "error", "message": "pipe_unavailable"}
        mock_get_bridge.return_value = mock_bridge

        from src.tools.delphi_rtti import handle_delphi_rtti
        result = await handle_delphi_rtti({
            "action": "discover",
            "app_path": "C:\\App.exe",
        })
        assert result["isError"]
        assert "pipe_unavailable" in result["content"][0]["text"]

    @pytest.mark.asyncio
    @mock.patch("src.tools.delphi_rtti.get_rtti_bridge")
    async def test_discover_app_error(self, mock_get_bridge):
        """Delphi 端返回错误时 discover 报告 isError"""
        mock_bridge = mock.MagicMock()
        mock_bridge.connect.return_value = {"status": "ok", "reused": True}
        mock_bridge.discover.return_value = {"status": "error", "message": "no rtti"}
        mock_get_bridge.return_value = mock_bridge

        from src.tools.delphi_rtti import handle_delphi_rtti
        result = await handle_delphi_rtti({
            "action": "discover",
            "app_path": "C:\\App.exe",
        })
        assert result["isError"]


# ═══════════════════════════════════════════════════════════════
# call action
# ═══════════════════════════════════════════════════════════════

class TestCall:
    """delphi_rtti(action='call') 测试"""

    @pytest.mark.asyncio
    async def test_call_missing_app_path(self):
        """call 缺少 app_path 应返回错误"""
        from src.tools.delphi_rtti import handle_delphi_rtti
        result = await handle_delphi_rtti({"action": "call"})
        assert result["isError"]
        assert "app_path" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_call_missing_class_name(self):
        """call 缺少 class_name 应返回错误"""
        from src.tools.delphi_rtti import handle_delphi_rtti
        result = await handle_delphi_rtti({
            "action": "call",
            "app_path": "C:\\App.exe",
        })
        assert result["isError"]
        assert "class_name" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_call_missing_method(self):
        """call 缺少 method 应返回错误"""
        from src.tools.delphi_rtti import handle_delphi_rtti
        result = await handle_delphi_rtti({
            "action": "call",
            "app_path": "C:\\App.exe",
            "class_name": "TMainForm",
        })
        assert result["isError"]
        assert "method" in result["content"][0]["text"]

    @pytest.mark.asyncio
    @mock.patch("src.tools.delphi_rtti.get_rtti_bridge")
    async def test_call_success(self, mock_get_bridge):
        """call 成功返回响应"""
        mock_bridge = mock.MagicMock()
        mock_bridge.connect.return_value = {"status": "ok", "reused": True}
        mock_bridge.call.return_value = {
            "status": "ok",
            "data": "42",
            "response": {"reqId": "call_1", "status": "ok", "data": "42"},
        }
        mock_get_bridge.return_value = mock_bridge

        from src.tools.delphi_rtti import handle_delphi_rtti
        result = await handle_delphi_rtti({
            "action": "call",
            "app_path": "C:\\App.exe",
            "class_name": "TMainForm",
            "method": "CreateOrder",
            "params": {"customerName": "张三", "amount": 100},
        })
        assert not result["isError"]
        assert "42" in result["content"][0]["text"]

    @pytest.mark.asyncio
    @mock.patch("src.tools.delphi_rtti.get_rtti_bridge")
    async def test_call_connect_fails(self, mock_get_bridge):
        """连接失败时 call 应返回错误"""
        mock_bridge = mock.MagicMock()
        mock_bridge.connect.return_value = {"status": "error", "message": "pipe_unavailable"}
        mock_get_bridge.return_value = mock_bridge

        from src.tools.delphi_rtti import handle_delphi_rtti
        result = await handle_delphi_rtti({
            "action": "call",
            "app_path": "C:\\App.exe",
            "class_name": "TMainForm",
            "method": "Method",
        })
        assert result["isError"]
        assert "pipe_unavailable" in result["content"][0]["text"]

    @pytest.mark.asyncio
    @mock.patch("src.tools.delphi_rtti.get_rtti_bridge")
    async def test_call_method_error(self, mock_get_bridge):
        """方法调用返回错误时报告 isError"""
        mock_bridge = mock.MagicMock()
        mock_bridge.connect.return_value = {"status": "ok", "reused": True}
        mock_bridge.call.return_value = {"status": "error", "data": "NM:UnknownMethod", "response": {}}
        mock_get_bridge.return_value = mock_bridge

        from src.tools.delphi_rtti import handle_delphi_rtti
        result = await handle_delphi_rtti({
            "action": "call",
            "app_path": "C:\\App.exe",
            "class_name": "TMainForm",
            "method": "UnknownMethod",
        })
        assert result["isError"]


# ═══════════════════════════════════════════════════════════════
# 未知 action
# ═══════════════════════════════════════════════════════════════

class TestUnknownAction:
    """未知 action 处理"""

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        from src.tools.delphi_rtti import handle_delphi_rtti
        result = await handle_delphi_rtti({"action": "reboot", "app_path": "C:\\App.exe"})
        assert result["isError"]
        assert "未知 action" in result["content"][0]["text"]
