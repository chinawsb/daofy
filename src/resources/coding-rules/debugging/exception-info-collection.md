<!-- @when: 异常发生时，需要采集现场信息定位根因 -->
<!-- @chain: after=six-step-method.md -->

### 8.3 异常信息采集

```python
# Python 异常采集模板
import traceback, sys
def capture_exception_context(exc, locals_dict=None):
    exc_type, exc_value, exc_tb = sys.exc_info()
    return {
        "exc_type": type(exc).__name__,
        "exc_message": str(exc),
        "traceback": traceback.format_exc(),
        "frames": [{
            "file": frame.f_code.co_filename,
            "line": frame.f_lineno,
            "function": frame.f_code.co_name,
            "locals": {k: repr(v) for k, v in frame.f_locals.items()}
        } for frame in traceback.extract_tb(exc_tb)],
    }
```

Delphi 异常采集推荐两种方案（二选一）：

**方案 A：引导用户在 IDE 重现（推荐，零依赖）**
AI 引导用户设断点、单步跟踪、收集调用栈和变量值。
- 必须用 Debug 配置编译
- 用户报告：出错文件+行号、异常消息、Call Stack (Ctrl+Alt+S)、Watch 变量值

**方案 B：接入异常跟踪工具（生产环境）**
| 工具 | 特点 |
|------|------|
| **StackTrace.pas**（项目自带） | VEH 钩子 + MAPDATA 符号解析 + 局部变量快照 |
| **madExcept**（商业） | 黄金标准：完整调用栈+源码行号 |
| **JclDebug**（JEDI 开源） | 编译时嵌入 map 符号 |
| **EurekaLog**（商业） | 支持远程上报 |

推荐优先用 StackTrace.pas：
```pascal
uses StackTrace;
initialization
  TStackTraceManager.Current.EnableDefaultLogger;
  TStackTraceManager.Current.CaptureVariables := True;
end.
```
启用后异常自动生成日志（符号化调用栈 + 源码行号 + 局部变量值）。
