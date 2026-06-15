"""MCP Tool: delphi_rtti — Delphi RTTI 桥接

发现和调用 Delphi 应用程序的运行时能力。

三步法：
  ① discover → 扫描 RTTI 暴露的方法和参数 Schema
  ② call → 调用方法
  ③ guide → 返回完整使用指南
"""

import json
import time
import ctypes
from ctypes import wintypes

from src.services.rtti_bridge import get_rtti_bridge
from src.services.automation_service import _send_command_to_pipe


def _call_via_pipe(pipe_name: str, req: dict, timeout_ms: int = 15000) -> dict:
    """通过管道调用 rcall（async 协议：ack → 轮询 peekresult）。

    rcall 在 Delphi 端是异步的：
      1. 立即返回 {"status":"ack"}
      2. 主线程处理后将结果存入 FAsyncResults（以 reqId 为 key）
      3. 客户端需用 peekresult 命令轮询直到结果就绪
    """
    from src.services.automation_service import (
        _open_pipe, _write_pipe, _read_pipe_message, _CloseHandle,
        _send_command_to_pipe, _GetLastError,
    )

    req_id = req.get("reqId", "call_" + str(int(time.time() * 1000)))
    req["reqId"] = req_id

    # 第一步：发送 rcall，读取 ack
    handle = _open_pipe(pipe_name, timeout_ms)
    if handle is None:
        return {"status": "error", "message": f"pipe_unavailable (err={_GetLastError()})"}
    try:
        cmd_bytes = json.dumps(req, ensure_ascii=False).encode("utf-8")
        if not _write_pipe(handle, cmd_bytes):
            return {"status": "error", "message": f"write_failed (err={_GetLastError()})"}

        raw = _read_pipe_message(handle)
        if raw is None:
            return {"status": "error", "message": "no ack response"}
        ack_resp = json.loads(raw.decode("utf-8", errors="replace").strip())
        if ack_resp.get("status") != "ack":
            # 意外：直接返回了实际结果
            data_raw = ack_resp.get("data", "")
            if data_raw:
                try:
                    data_resp = json.loads(data_raw)
                    return {
                        "status": data_resp.get("status", "ok"),
                        "data": data_resp.get("data", ""),
                        "response": ack_resp,
                    }
                except (json.JSONDecodeError, TypeError):
                    pass
            return {
                "status": ack_resp.get("status", "error"),
                "data": data_raw,
                "response": ack_resp,
            }
    finally:
        _CloseHandle(handle)

    # 第二步：轮询 peekresult
    deadline = time.time() + (timeout_ms / 1000)
    peek_req = json.dumps({
        "reqId": f"peek_{req_id}",
        "cmd": "peekresult",
        "target": req_id,
    }, ensure_ascii=False)

    while time.time() < deadline:
        resp = _send_command_to_pipe(pipe_name, peek_req, 5000)
        if resp.startswith("ERR:"):
            time.sleep(0.1)
            continue

        try:
            peek = json.loads(resp)
        except (json.JSONDecodeError, TypeError):
            time.sleep(0.1)
            continue

        if peek.get("status") != "ok":
            time.sleep(0.1)
            continue

        data_raw = peek.get("data", "")
        if data_raw.startswith("NR:"):
            # 结果尚未就绪，等主线程处理完 rcall
            time.sleep(0.1)
            continue

        # 有结果了！（data 字段中是 HandleRCall 返回的完整响应 JSON）
        try:
            result_resp = json.loads(data_raw)
            if isinstance(result_resp, dict):
                return {
                    "status": result_resp.get("status", "ok"),
                    "data": result_resp.get("data", ""),
                    "response": result_resp,
                }
            # 非 dict（如 JSON 数组）→ 直接作为 data 返回
            return {
                "status": "ok",
                "data": data_raw,
            }
        except (json.JSONDecodeError, TypeError):
            return {
                "status": "ok",
                "data": data_raw,
            }

    return {"status": "error", "message": f"timeout: result not ready for req_id={req_id}"}

# ── 完整使用指南（L3 按需加载）──

RTTI_GUIDE = """\
# Delphi RTTI 桥接 — 使用指南

## 概述
通过 Delphi 的 Enhanced RTTI 发现和调用应用程序的运行时能力。

## 前提
- Delphi 应用已链接 DaofyAutomation 单元（VCL: uses Vcl.DaofyAutomation; FMX: uses Fmx.DaofyAutomation）
- 应用已编译运行，命名管道已就绪

## 三步工作流

### 第一步：连接并发现
```
delphi_rtti(action="discover", app_path="C:\\App\\MyApp.exe")
```
返回该应用所有类的 published+public 方法/属性清单，包含：
- 方法名和参数 Schema（JSON Schema 格式）
- 参数类型映射
- 参数是否必需

### 第二步：查看能力详情
discover 返回的 tools 数组中包含每个方法的：
- name: 方法名
- description: 方法说明
- parameters: JSON Schema 格式的参数定义

### 第三步：调用方法
```
delphi_rtti(
  action="call",
  app_path="C:\\App\\MyApp.exe",
  class_name="TMainForm",
  method="CreateOrder",
  params={"customerName": "张三", "amount": 100}
)
```

## 类型映射
| Delphi 类型 | JSON 类型 | 说明 |
|------------|----------|------|
| string (UnicodeString, AnsiString, etc.) | string | UTF-8 编码 |
| Integer, SmallInt, Int64, etc. | integer | |
| Single, Double, Currency | number | |
| Boolean, ByteBool | boolean | |
| TDateTime | string | format: date-time |
| TObject / TPersistent | object | 子对象（有限支持） |
| TArray<T> / array of ... | array | 元素类型递归映射 |
| TStrings / TStringList | array of string | |
| 枚举类型 | string | 带 enum 约束 |

## AI 注解（Custom Attributes）

在 Delphi 方法或参数上添加 `AI` 前缀的属性注解，可以给 AI Agent 提供更丰富的上下文：

| 属性 | 应用位置 | 说明 |
|------|---------|------|
| `[AIDescription('...')]` | 方法 | 功能描述 |
| `[AIResultDescription('...')]` | 方法 | 返回值说明 |
| `[AIExample('...')]` | 方法 | 调用示例 |
| `[AIParamDescription('...')]` | 参数 | 参数含义 |

示例：
```pascal
[AIDescription('创建客户订单，返回新订单号')]
[AIResultDescription('新创建的订单编号，失败返回 -1')]
[AIExample('CreateOrder("张三", 100) → 10001')]
function CreateOrder(
  [AIParamDescription('客户姓名')] const customerName: string;
  [AIParamDescription('订单金额(元)')] amount: Integer
): Integer;
```

注解后 discover 的 JSON Schema 会携带 `description`、`example` 等字段。

## 最佳实践
1. **先 discover 再 call** — 始终先获取能力清单
2. **缓存发现结果** — 同一应用的能力在生命周期内不变
3. **使用 keep_alive** — 多次调用的场景保持进程
4. **参数类型匹配** — 对照类型映射表确保参数类型正确

## 故障排除
- "pipe_unavailable" → 确认 Delphi 应用已启动并链接 DaofyAutomation（VCL: uses Vcl.DaofyAutomation; FMX: uses Fmx.DaofyAutomation）
- 方法调用失败 → 检查参数名和类型是否与 discover 返回的 Schema 一致
- 空结果 → 确认目标类的方法标记为 published 或 public
"""


async def handle_delphi_rtti(arguments: dict) -> dict:
    """处理 delphi_rtti 工具调用。

    Args:
        arguments: 工具参数字典，包含 action/app_path/class_name/method/params

    Returns:
        dict: 包含 content 和 isError 的响应
    """
    action = arguments.get("action", "guide")
    bridge = get_rtti_bridge()

    if action == "guide":
        return {
            "content": [{"type": "text", "text": RTTI_GUIDE}],
            "isError": False,
        }

    if action == "list":
        result = bridge.list_running_apps()
        return {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
            "isError": result.get("status") == "error",
        }

    app_path = arguments.get("app_path", "")
    pipe = arguments.get("pipe", "")

    if not app_path and not pipe:
        return {
            "content": [{"type": "text", "text": "错误: app_path 或 pipe 是必需的"}],
            "isError": True,
        }

    if action == "discover":
        class_name = arguments.get("class_name", "")
        force = arguments.get("force", False)
        keep_alive = arguments.get("keep_alive", False)

        if pipe:
            # 使用已运行的管道（无需 app_path）
            result = bridge.discover_from_pipe(pipe, class_name, force)
            return {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                "isError": result.get("status") == "error",
            }

        # 传统方式：通过 app_path 连接
        conn = bridge.connect(app_path)
        if conn.get("status") == "error":
            return {
                "content": [{"type": "text", "text": json.dumps(conn, ensure_ascii=False, indent=2)}],
                "isError": True,
            }

        result = bridge.discover(app_path, class_name, force)

        return {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
            "isError": result.get("status") == "error",
        }

    elif action == "call":
        class_name = arguments.get("class_name", "")
        method = arguments.get("method", "")
        params = arguments.get("params", {})

        if not class_name:
            return {
                "content": [{"type": "text", "text": "错误: class_name 是必需的"}],
                "isError": True,
            }
        if not method:
            return {
                "content": [{"type": "text", "text": "错误: method 是必需的"}],
                "isError": True,
            }

        if pipe:
            # 通过已有管道调用（无需 app_path）
            req = {
                "reqId": f"call_{int(time.time() * 1000)}",
                "cmd": "rcall",
                "target": class_name,
                "method": method,
            }
            if params:
                req["params"] = json.dumps(params, ensure_ascii=False)
            result = _call_via_pipe(pipe, req)
            return {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                "isError": result.get("status") == "error",
            }

        # 传统方式：通过 app_path
        conn = bridge.connect(app_path)
        if conn.get("status") == "error":
            return {
                "content": [{"type": "text", "text": json.dumps(conn, ensure_ascii=False, indent=2)}],
                "isError": True,
            }

        result = bridge.call(app_path, class_name, method, params)
        return {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
            "isError": result.get("status") == "error",
        }

    return {
        "content": [{"type": "text", "text": f"未知 action: {action}，可用: guide, discover, call, list"}],
        "isError": True,
    }
