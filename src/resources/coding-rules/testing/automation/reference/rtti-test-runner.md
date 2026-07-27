<!-- @when: 需要对白盒/灰盒 Delphi 方法执行参数化测试，或替代 DUnitX 的运行与报告能力时 -->
<!-- @chain: after=workflow.md, before=report-schema.md -->

# RTTI 单元测试运行器

MCP resource URI: `delphi://automation/rtti-test-runner`。

`automate_delphi(action="test")` 用于直接测试 Delphi 类方法。它面向白盒/灰盒测试，
通过 RTTI 完成实例创建、参数绑定、方法调用、断言、fixture 生命周期和结构化报告；
UI 用户路径仍应使用 `action="gui"`，不要用 RTTI 调用冒充黑盒测试。

## 1. TestHost 接入

项目需引用 `DaofyAutomation.Base` 以及对应的 VCL/FMX 自动化单元，并在进程启动时调用
`AutoStart`。运行器按 fixture、显式注册类、`TRttiContext.FindType`、`FindClass` 的顺序解析
`className`。已进入 RTTI 类型池且有兼容构造器的类可直接使用，无需调用
`RegisterTestClass`；此时 `className` 使用 RTTI 全限定名，例如 `Tests.TCalculator`。

仅通过测试 JSON 字符串引用的类可能被 Delphi 智能链接器从可执行文件中裁掉。类型无法由 RTTI
发现、需要显式保活或需要自定义别名时，才使用 `RegisterTestClass`：

```pascal
initialization
  TAutomationProcessorBase.RegisterTestClass(
    TCalculator,
    'Tests.TCalculator');

finalization
  TAutomationProcessorBase.UnregisterTestClass('Tests.TCalculator');
```

需要每例 setup/teardown 时注册 fixture：

```pascal
function SetupCalculator: TValue;
begin
  Result := TValue.From<TObject>(TCalculator.Create);
end;

procedure TearDownCalculator(const AValue: TValue);
begin
  if AValue.IsObject then
    AValue.AsObject.Free;
end;

initialization
  TAutomationProcessorBase.RegisterFixture(
    'Tests.TCalculator', SetupCalculator, TearDownCalculator);

finalization
  TAutomationProcessorBase.UnregisterFixture('Tests.TCalculator');
```

直接发现类和显式注册类都由运行器选择并调用构造器；fixture 则由 setup 返回对象或值，
teardown 总是在测试结束后独立执行。setup、构造、test、teardown 的异常阶段会分别记录。

## 2. MCP 调用

`test` action 会提交后台任务，避免长测试占满 MCP 请求通道：

```python
submitted = automate_delphi(
    action="test",
    app_path=r"C:\Tests\TestHost.exe",
    test_timeout=30,
    keep_alive=True,
    tests=[
        {
            "id": "add",
            "className": "Tests.TCalculator",
            "method": "Add",
            "params": [1, 2],
            "expected": "3"
        },
        {
            "id": "invalid-input",
            "className": "Tests.TCalculator",
            "method": "Parse",
            "params": ["bad"],
            "expected_exception": "EConvertError",
            "expected_message": "invalid"
        }
    ]
)

async_task(action="status", task_id=submitted["task_id"], long_poll_seconds=10)
result = async_task(action="result", task_id=submitted["task_id"])
```

> **⚠️ 轮询建议**：对于慢任务（如自动化测试），推荐用 `action="result"` 轮询而非 `action="status"` + `long_poll_seconds`。
> `action="result"` 立即返回当前状态（零等待），不会阻塞 MCP 通道。
> `action="status"` + `long_poll_seconds` 会阻塞等待进度变化，如果任务长时间未完成，可能导致客户端超时。

## 3. 用例字段

| 字段 | 必需 | 说明 |
|------|------|------|
| `id` / `name` | 否 | 稳定标识和显示名称，原样进入结果 |
| `target` | 二选一 | GUI 控件名；与 `className` 互斥 |
| `className` | 二选一 | 类名（见下方查找顺序）；与 `target` 互斥 |
| `method` | 是 | RTTI 方法名 |
| `params` | 否 | 方法参数 JSON 数组，也接受可解析为数组的 JSON 字符串 |
| `constructor_params` | 否 | 直接发现类或显式注册类的构造参数 JSON 数组；省略时绑定无参数构造器 |
| `expected` | 否 | 返回值的精确字符串断言，允许空字符串 |
| `expected_exception` | 否 | 测试阶段应抛出的异常类名，与 `expected` 互斥 |
| `expected_message` | 否 | 异常消息应包含的文本，不区分大小写；需配合 `expected_exception` |
| `assert_expr` | 否 | Python 表达式，变量 `actual` 为返回值字符串；与 `expected`/`expected_exception` 互斥 |
| `visibility` | 否 | 覆盖全局 RTTI 可见度，如 `private,protected,public,published` |
| `timeout` | 否 | 覆盖该例的超时秒数，必须为有限正数 |

### className 查找顺序（优先级从高到低）

1. **RegisterTestClass 注册名**（如 `'Agent.EditEngineV3Test'`）— 通过 `GetTestClass` 查字典，最稳定，不会被链接器裁剪
2. **TRttiContext.FindType 全限定名**（如 `'Tests.TCalculator'`）— RTTI 必须可发现，且类必须是 instance type
3. **FindClass**（Delphi VCL 类名）— 仅限 `TComponent` 派生类

> ⚠️ **不要传 Delphi 源码中的裸类名**（如 `TEditEngineV3Test`）。必须传上述三种之一。
> 推荐优先使用 `RegisterTestClass` 注册名，因为它不依赖 RTTI 链接且不会被智能链接器裁掉。

### 断言模式互斥规则

三种断言模式**互斥**，每例只能选一种：

| 模式 | 字段 | 执行方 | 语义 |
|------|------|--------|------|
| 精确匹配 | `expected` | Delphi | `result.ToString = expected` |
| 异常匹配 | `expected_exception` | Delphi | `phase=test` 时异常类名 + 消息匹配 |
| Python 表达式 | `assert_expr` | Python | `eval(assert_expr, actual=返回值)` |

> ❌ **禁止组合**：`assert_expr` 会覆盖 Delphi 侧的 `assert` 字段。如果同时设置
> `expected` 和 `assert_expr`，Delphi 的精确匹配结果会被 Python 表达式静默覆盖，
> 导致 `result=PASS` + `assert=fail` 的困惑。验证层会拒绝这种组合。

`assert_expr` 在 MCP 服务进程中按标准 Python 表达式执行，可使用 Python 内建能力；
只运行可信测试定义。自然语言说明应放在 `name` 或外部测试说明中，不要写进表达式。

## 4. RTTI 绑定规则

- 支持整数、Int64、布尔/枚举、浮点、字符串、字符和 class `nil` 参数。
- `var/out`、record、动态数组、接口等尚未支持的参数会明确报错，不会猜测绑定。
- 重载按参数数量和类型选择；多个兼容重载会返回 `ambiguous overload`。
- RTTI 返回的继承链同签名方法会去重，构造器优先选择声明在最派生类型上的版本。
- `expected` 当前按 Delphi `TValue.ToString` 结果精确比较；复杂比较和容差使用
  `assert_expr`。

## 5. 生命周期与超时

每个测试通过独立 `run_tests` 请求执行：

1. 校验完整 suite，非法输入不会启动 TestHost。
2. 启动或复用进程，等待 PID 派生的自动化端点（Windows NamedPipe；POSIX Unix Domain Socket）。
3. setup/构造实例，绑定并调用方法。
4. 执行 Delphi 侧 `expected` / expected-exception 断言。
5. 独立执行 teardown；teardown 失败不会覆盖原始测试异常。
6. Python 侧执行 `assert_expr` 并汇总稳定统计。

默认 `test_timeout=30` 秒，可由每例 `timeout` 覆盖。传输读取达到 deadline 后会终止
TestHost，下一例自动启动新进程。超时结果包含 `ms` 字段（实际耗时）和 `timeout_sec`
字段（超时阈值），便于区分"卡死"和"真慢"。`keep_alive=true` 是 test action 默认值；
传 false 时 suite 完成后关闭传输连接并终止 TestHost。

只有 `phase=test` 的异常能满足 `expected_exception`。setup、构造和 teardown 异常始终是
error；异常类型错误、消息不匹配或没有抛出预期异常属于 assertion failure。

## 6. 结果结构

```json
{
  "status": "failed",
  "total": 4,
  "passed": 1,
  "failed": 2,
  "errors": 1,
  "duration_seconds": 0.475,
  "process_reused": false,
  "results": [
    {
      "id": "invalid-input",
      "status": "ok",
      "exception_class": "EConvertError",
      "exception_message": "invalid value",
      "assert": "pass"
    }
  ],
  "raw_responses": []
}
```

- `passed`：方法完成且所有声明的断言通过。
- `failed`：方法执行完成，但返回值、Python 表达式或预期异常断言失败。
- `errors`：启动、传输、setup/构造、未预期 test 异常或 teardown 错误。
- `status`：全部测试通过时为 `ok`，否则为 `failed`。
- `raw_responses`：保留 Delphi 原始协议响应，供诊断统计或编码问题。

## 7. 面向模型的生成流程

1. 读取目标类源码，枚举正常、边界和异常路径。
2. 为纯业务方法优先生成 `action="test"` 用例；用户可见流程生成 GUI 黑盒脚本。
3. RTTI 可发现且有兼容构造器的类直接使用；需要保活/别名时用 `RegisterTestClass`，需要
   setup/teardown 时用 `RegisterFixture`。
4. 用 JSON primitive 构造参数化数据；对异常路径声明 `expected_exception`。
5. 编译 TestHost，提交任务并轮询 `async_task`。
6. 首先修复 error，再处理 assertion failure；修复后重跑完整 suite。
