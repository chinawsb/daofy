<!-- @when: 开发 MCP 工具或排查工具异常时 -->
<!-- @chain: after=collaboration-workflow.md -->

### 8.6 MCP 工具异常处理约定

| 层级 | 处理方式 |
|------|---------|
| `tools/*.py` handler | 捕获具体异常，返回 `{"error":"..."}` + `exc_info=True` 日志；不抛出 |
| `server.py call_tool` | 顶层兜底捕获所有异常，格式化为 `CallToolResult(isError=True)`；禁止裸抛 |
| `services/*.py` | 业务异常用自定义异常类，保留调用链；记录日志但不吞异常 |
| `utils/*.py` | 通常不捕获，让上层统一处理 |
