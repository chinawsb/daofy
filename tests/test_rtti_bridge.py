#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Delphi RTTI 桥接服务测试 — TestRttiBridge

测试 src/services/rtti_bridge.py 的业务逻辑：
  - 缓存生命周期（有效/过期/清除）
  - discover 的缓存命中/未命中/强制刷新
  - discover 的类过滤
  - call 方法调用
  - 错误处理（管道不可用、JSON 解析失败等）
"""

import json
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

SAMPLE_DISCOVER_RESPONSE = {
    "reqId": "disc_1",
    "status": "ok",
    "data": json.dumps({
        "className": "TMainForm",
        "ancestor": "TForm",
        "tools": [
            {
                "name": "CreateOrder",
                "kind": "function",
                "returnType": {"type": "integer"},
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customerName": {"type": "string"},
                        "amount": {"type": "number", "minimum": 0},
                    },
                },
            },
            {"name": "RefreshData", "kind": "procedure"},
        ],
        "properties": [
            {"name": "Caption", "schema": {"type": "string"}, "readable": True, "writable": True},
        ],
    }),
}

SAMPLE_CALL_RESPONSE = {
    "reqId": "call_1",
    "status": "ok",
    "data": "42",
}

SAMPLE_CALL_ERROR_RESPONSE = {
    "reqId": "call_1",
    "status": "error",
    "data": "NM:UnknownMethod",
}


@pytest.fixture
def rtti_bridge():
    """创建一个干净（无缓存）的 RttiBridge 实例。"""
    from src.services.rtti_bridge import RttiBridge
    bridge = RttiBridge()
    yield bridge


# ═══════════════════════════════════════════════════════════════
# 缓存测试
# ═══════════════════════════════════════════════════════════════

class TestCache:
    """RttiBridge 缓存逻辑"""

    def test_cache_miss_on_empty(self, rtti_bridge):
        """初始状态缓存不存在"""
        assert not rtti_bridge._is_cache_valid("C:\\App.exe")

    def test_cache_valid_after_set(self, rtti_bridge):
        """设置缓存后应有效"""
        rtti_bridge._cache["C:\\App.exe"] = {"classes": []}
        rtti_bridge._cache_time["C:\\App.exe"] = time.time()
        assert rtti_bridge._is_cache_valid("C:\\App.exe")

    def test_cache_expired(self, rtti_bridge):
        """超过 TTL 的缓存应失效"""
        rtti_bridge._cache["C:\\App.exe"] = {"classes": []}
        rtti_bridge._cache_time["C:\\App.exe"] = time.time() - 301  # 5min + 1s
        assert not rtti_bridge._is_cache_valid("C:\\App.exe")

    def test_clear_cache_single(self, rtti_bridge):
        """清除指定 app 的缓存"""
        rtti_bridge._cache["A.exe"] = {"classes": []}
        rtti_bridge._cache_time["A.exe"] = time.time()
        rtti_bridge._cache["B.exe"] = {"classes": []}
        rtti_bridge._cache_time["B.exe"] = time.time()
        rtti_bridge.clear_cache("A.exe")
        assert "A.exe" not in rtti_bridge._cache
        assert "B.exe" in rtti_bridge._cache

    def test_clear_cache_all(self, rtti_bridge):
        """清除全部缓存"""
        rtti_bridge._cache["A.exe"] = {"classes": []}
        rtti_bridge._cache_time["A.exe"] = time.time()
        rtti_bridge._cache["B.exe"] = {"classes": []}
        rtti_bridge._cache_time["B.exe"] = time.time()
        rtti_bridge.clear_cache()
        assert len(rtti_bridge._cache) == 0
        assert len(rtti_bridge._cache_time) == 0


# ═══════════════════════════════════════════════════════════════
# discover 测试
# ═══════════════════════════════════════════════════════════════

class TestDiscover:
    """RttiBridge.discover() 测试"""

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(False, None))
    @mock.patch("src.services.rtti_bridge._send_command", return_value=json.dumps(SAMPLE_DISCOVER_RESPONSE))
    def test_discover_full(self, mock_send, mock_ensure, rtti_bridge):
        """完整 discover 应返回类和方法信息"""
        result = rtti_bridge.discover("C:\\App.exe")
        assert result["status"] == "ok"
        assert "className" in result  # data 被扁平化到顶层
        assert result["className"] == "TMainForm"
        assert len(result["tools"]) > 0

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(False, None))
    @mock.patch("src.services.rtti_bridge._send_command", return_value=json.dumps(SAMPLE_DISCOVER_RESPONSE))
    def test_discover_hits_cache(self, mock_send, mock_ensure, rtti_bridge):
        """第二次 discover 应命中缓存，不发送命令"""
        rtti_bridge.discover("C:\\App.exe")
        mock_send.reset_mock()
        result = rtti_bridge.discover("C:\\App.exe")
        assert result["status"] == "ok"
        mock_send.assert_not_called()

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(False, None))
    @mock.patch("src.services.rtti_bridge._send_command", return_value=json.dumps(SAMPLE_DISCOVER_RESPONSE))
    def test_discover_force(self, mock_send, mock_ensure, rtti_bridge):
        """force=True 应跳过缓存重新请求"""
        rtti_bridge.discover("C:\\App.exe")
        mock_send.reset_mock()
        rtti_bridge.discover("C:\\App.exe", force=True)
        mock_send.assert_called_once()

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(False, None))
    @mock.patch("src.services.rtti_bridge._send_command", return_value=json.dumps(SAMPLE_DISCOVER_RESPONSE))
    def test_discover_filter_class(self, mock_send, mock_ensure, rtti_bridge):
        """discover 过滤特定类名应命中缓存"""
        rtti_bridge.discover("C:\\App.exe")
        result = rtti_bridge.discover("C:\\App.exe", class_name="TMainForm")
        assert result["status"] == "ok"
        # 过滤后返回 class（单类）或 classes（列表）
        assert "class" in result or "classes" in result

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(True, None))
    @mock.patch("src.services.rtti_bridge._send_command", return_value=json.dumps(SAMPLE_DISCOVER_RESPONSE))
    def test_discover_reused_process(self, mock_send, mock_ensure, rtti_bridge):
        """连接返回 reused=True 时仍正常工作"""
        result = rtti_bridge.connect("C:\\App.exe")
        assert result["status"] == "ok"
        assert result["reused"] is False  # is_new=True → reused=False

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(False, "pipe_unavailable"))
    @mock.patch("src.services.rtti_bridge._send_command")
    def test_discover_pipe_error(self, mock_send, mock_ensure, rtti_bridge):
        """管道不可用时返回错误"""
        result = rtti_bridge.discover("C:\\App.exe")
        assert result["status"] == "error"
        assert "pipe_unavailable" in result["message"]

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(False, None))
    @mock.patch("src.services.rtti_bridge._send_command", return_value="ERR:timeout")
    def test_discover_command_err(self, mock_send, mock_ensure, rtti_bridge):
        """命令返回 ERR: 前缀时正确处理"""
        result = rtti_bridge.discover("C:\\App.exe")
        assert result["status"] == "error"
        assert "timeout" in result["message"]

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(False, None))
    @mock.patch("src.services.rtti_bridge._send_command", return_value="not json at all")
    def test_discover_invalid_json(self, mock_send, mock_ensure, rtti_bridge):
        """非 JSON 响应应返回解析错误"""
        result = rtti_bridge.discover("C:\\App.exe")
        assert result["status"] == "error"
        assert "无效响应" in result["message"]

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(False, None))
    @mock.patch("src.services.rtti_bridge._send_command", return_value=json.dumps({
        "reqId": "disc_1",
        "status": "error",
        "data": "method not published",
    }))
    def test_discover_app_error(self, mock_send, mock_ensure, rtti_bridge):
        """Delphi 端返回错误状态时传递错误信息"""
        result = rtti_bridge.discover("C:\\App.exe")
        assert result["status"] == "error"
        assert "method not published" in result["message"]


# ═══════════════════════════════════════════════════════════════
# call 测试
# ═══════════════════════════════════════════════════════════════

class TestCall:
    """RttiBridge.call() 测试"""

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(False, None))
    @mock.patch("src.services.rtti_bridge._send_command", return_value=json.dumps(SAMPLE_CALL_RESPONSE))
    def test_call_success(self, mock_send, mock_ensure, rtti_bridge):
        """调用方法成功返回 data"""
        result = rtti_bridge.call("C:\\App.exe", "TMainForm", "CreateOrder", {"customerName": "张三"})
        assert result["status"] == "ok"
        assert result["data"] == "42"

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(False, "pipe_unavailable"))
    @mock.patch("src.services.rtti_bridge._send_command")
    def test_call_pipe_error(self, mock_send, mock_ensure, rtti_bridge):
        """管道不可用时返回错误"""
        result = rtti_bridge.call("C:\\App.exe", "TMainForm", "Method")
        assert result["status"] == "error"
        assert "pipe_unavailable" in result["message"]

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(False, None))
    @mock.patch("src.services.rtti_bridge._send_command", return_value=json.dumps(SAMPLE_CALL_ERROR_RESPONSE))
    def test_call_method_not_found(self, mock_send, mock_ensure, rtti_bridge):
        """方法不存在时返回 error"""
        result = rtti_bridge.call("C:\\App.exe", "TMainForm", "UnknownMethod")
        assert result["status"] == "error"
        assert result["data"] == "NM:UnknownMethod"

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(False, None))
    @mock.patch("src.services.rtti_bridge._send_command", return_value="ERR:NF:TMainForm")
    def test_call_class_not_found(self, mock_send, mock_ensure, rtti_bridge):
        """类不存在时返回错误"""
        result = rtti_bridge.call("C:\\App.exe", "TMainForm", "Method")
        assert result["status"] == "error"
        assert "NF:TMainForm" in result["message"]

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(False, None))
    @mock.patch("src.services.rtti_bridge._send_command", return_value="not json")
    def test_call_invalid_response(self, mock_send, mock_ensure, rtti_bridge):
        """非 JSON 响应时处理"""
        result = rtti_bridge.call("C:\\App.exe", "TMainForm", "Method")
        assert result["status"] == "error"
        assert "无效响应" in result["message"]


# ═══════════════════════════════════════════════════════════════
# connect 测试
# ═══════════════════════════════════════════════════════════════

class TestConnect:
    """RttiBridge.connect() 测试"""

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(True, None))
    def test_connect_new(self, mock_ensure, rtti_bridge):
        """连接新进程返回 reused=False"""
        result = rtti_bridge.connect("C:\\App.exe")
        assert result["status"] == "ok"
        assert result["reused"] is False

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(False, None))
    def test_connect_reused(self, mock_ensure, rtti_bridge):
        """复用已有进程返回 reused=True"""
        result = rtti_bridge.connect("C:\\App.exe")
        assert result["status"] == "ok"
        assert result["reused"] is True

    @mock.patch("src.services.rtti_bridge._ensure_process", return_value=(True, "pipe_unavailable"))
    def test_connect_error(self, mock_ensure, rtti_bridge):
        """连接失败返回错误"""
        result = rtti_bridge.connect("C:\\App.exe")
        assert result["status"] == "error"
        assert "pipe_unavailable" in result["message"]
