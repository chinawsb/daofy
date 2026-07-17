<!-- @when: Console 程序编译通过后，需进行 stdin/stdout 交互验证 -->
<!-- @chain: before=human-collab.md, after=ui.md -->

## ⑨ 控制台程序交互验证

Console 类型程序通过 `automate_delphi` console 模式进行 stdin/stdout 交互。**不需 Delphi 端改造。**

`action="auto"` 自动检测 PE 头 Subsystem；也可显式 `action="console"`。

### 工具调用
```python
automate_delphi(app_path="Tool.exe", input="Y\n", expect="Continue?")
automate_delphi(action="console", app_path="Deploy.exe", args=["--silent"], timeout=60)
```

### 通信模式
```
Python                               Console Delphi
  ── Popen(stdin=PIPE, stdout=PIPE) → begin..end 启动
  ── proc.stdin.write("input\n")    → ReadLn 接收
  ←── proc.stdout.read()            ← WriteLn 输出
  ←── proc.wait(timeout=5)          ← exit
```

### 分步交互（keep_alive）
```python
proc = subprocess.Popen([exe_path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
proc.stdin.write(b"Y\n"); proc.stdin.flush()
while True:
    line = proc.stdout.readline()
    if not line: break
    if b"Continue?" in line: proc.stdin.write(b"N\n"); proc.stdin.flush(); break
proc.wait(timeout=5)
```

### 注意事项
| 注意点 | 说明 |
|--------|------|
| 超时控制 | `communicate(timeout=...)` 必须设置 |
| 管道缓冲 | 大量输出用 `readline()` 逐行读 |
| stderr | 建议 `STDOUT` 合并 |
| exit code | `proc.returncode` 判断正常退出 |
| 编码 | Windows 控制台通常是 gbk |

---

### 测试质量红线

6 条一票否决红线（禁止跳过式通过、断言验证具体状态、截图必须有验证、外部依赖降级路径、执行时间匹配、运行证据支撑）见 [`automation/scenarios/base.md` § 测试质量红线`](../automation/scenarios/base.md#测试质量红线)。
