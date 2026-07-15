<!-- @when: Console 程序编译通过后，需进行 stdin/stdout 交互验证 -->
<!-- @chain: before=human-collab.md, after=ui-testing.md -->

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

### pytest 反假通过规则

> 以下规则适用于 Daofy 项目自身的 pytest 测试（`tests/` 目录），以及为 Delphi 程序生成的 Python 测试脚本。与 `base.md` 的测试质量红线一票否决标准一致。

#### 红线 1：禁止跳过式通过

```python
# ❌ 错误：异常后 assert True 混入 passed
def test_compile():
    try:
        result = compile_project("test.dproj")
    except Exception:
        pass
    assert True  # 假通过

# ✅ 正确：显式 skip 或 fail
def test_compile():
    if not compiler_available():
        pytest.skip("Delphi 编译器未安装")
    result = compile_project("test.dproj")
    assert result.exit_code == 0
    assert "Error" not in result.stdout
```

#### 红线 2：断言必须验证具体状态

```python
# ❌ 错误：无信息量的断言
assert result  # result 可能是任何 truthy 值
assert output != ""  # 无法定位问题
assert True

# ✅ 正确：验证具体状态
assert result.exit_code == 0, f"编译失败: {result.stderr}"
assert "163,737 classes" in result.stdout
assert os.path.exists(output_exe), f"输出文件不存在: {output_exe}"
assert file_size > 1024, f"输出文件过小: {file_size} bytes"
```

#### 红线 3：截图/输出必须有后续验证

```python
# ❌ 错误：截图后不检查
def test_ui_layout():
    screenshot("main_form.png")
    # 没有任何验证

# ✅ 正确：截图后验证内容
def test_ui_layout():
    screenshot_path = screenshot("main_form.png")
    # OCR 验证关键文本
    text = ocr_recognize(screenshot_path)
    assert "保存" in text, "保存按钮文本缺失"
    # 像素对比验证布局
    diff = image_diff("baseline.png", screenshot_path)
    assert diff.pixel_diff < 100, f"布局偏移: {diff.pixel_diff} 像素"
```

#### 红线 4：外部依赖必须测试降级路径

```python
# ❌ 错误：依赖外部工具但不检查可用性
def test_with_7zip():
    result = subprocess.run(["7z", "x", "test.7z"], capture_output=True)
    assert result.returncode == 0  # 7z 不存在时直接失败

# ✅ 正确：先检查再测试
@pytest.mark.skipif(shutil.which("7z") is None, reason="7-Zip 未安装")
def test_with_7zip():
    result = subprocess.run(["7z", "x", "test.7z"], capture_output=True)
    assert result.returncode == 0
    assert os.path.exists("extracted_file.txt")

# ✅ 正确：同时测试降级路径
def test_7zip_fallback():
    if shutil.which("7z") is None:
        # 测试降级路径（如内置解压）
        result = fallback_extract("test.7z")
        assert result.success
    else:
        # 测试正常路径
        result = subprocess.run(["7z", "x", "test.7z"], capture_output=True)
        assert result.returncode == 0
```

#### 红线 5：执行时间必须与操作量匹配

```python
# ❌ 错误：循环 100 次但瞬间完成（可能走了 mock/跳过）
def test_batch_compile():
    for i in range(100):
        compile_project(f"test_{i}.dproj")
    assert True  # 100 次编译不可能 0.1 秒完成

# ✅ 正确：验证实际执行时间
def test_batch_compile():
    import time
    start = time.time()
    results = []
    for i in range(10):  # 合理的测试规模
        result = compile_project(f"test_{i}.dproj")
        results.append(result)
    elapsed = time.time() - start

    assert len(results) == 10
    assert elapsed > 5, f"10 次编译仅耗时 {elapsed:.1f}s，可能未真实执行"
    assert all(r.exit_code == 0 for r in results)
```

#### 红线 6：测试报告必须包含执行证据

```python
# ❌ 错误：只报告 passed/failed 数量
# "10 tests passed in 0.5 seconds" — 不可能 10 个真实测试 0.5 秒完成

# ✅ 正确：报告包含执行时间、关键输出、截图路径
def test_report():
    report = {
        "total": 10,
        "passed": 8,
        "skipped": 1,  # 显式标记跳过原因
        "failed": 1,
        "elapsed_seconds": 45.2,  # 真实执行时间
        "evidence": {
            "screenshots": ["main_001.png", "dialog_002.png"],
            "logs": ["compile_output.log"],
            "skip_reasons": {"test_7zip": "7-Zip 未安装"}
        }
    }
```
