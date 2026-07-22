<!-- @when: 需要从源码分析生成测试路径，或使用代码派生断言时 -->

# 代码感知测试

MCP resource URI: `delphi://automation/code-aware-testing`。

## H1. 核心理念

AI 的优势不是模拟点击，而是**读懂代码**。源码就是最好的测试规范。

代码感知测试在「感知→规划→执行→验证」循环的**上游**新增代码分析阶段。

## H2. 代码分析工作流

### 步骤 1：定位目标代码

```python
delphi_kb(query="TNewCustomerForm", search_type="class", kb_type="project")
delphi_file(action="read", file_path="UnitNewCustomer.pas")
delphi_file(action="read", search_type="class", type_name="TNewCustomerForm")
```

### 步骤 2：分析 DFM（控件结构）

提取控件的名称、类型、事件绑定、关键属性，输出供规划阶段使用的控件映射表。

### 步骤 3：分析 PAS（事件处理程序）

| 代码模式 | 测试含义 |
|---------|---------|
| `if edtName.Text = '' then` | 测试空值路径，弹窗验证 |
| `try ... except ... end` | 触发异常，验证降级行为 |
| `ShowMessage('...')` | 操作后 msgscan 验证弹窗文本 |
| `ModalResult := mrOk/mrCancel` | waitfor 窗口关闭 |
| `Insert/Post` | 黑盒 UI 验证；灰盒 rcall 验证数据持久化 |
| `Enabled := False` | rget 验证 Enabled |
| `lblError.Visible := True` | rget 验证 Visible |

### 步骤 4：输出代码分析报告

```
== 代码分析报告 — TNewCustomerForm ==

控件结构:
| 控件名 | 类型 | 事件 |
|--------|------|------|
| edtName | TEdit | — |
| btnSave | TButton | btnSaveClick |

事件处理程序分析:
**btnSaveClick**
1. 验证 edtName.Text 非空 → 空则 ShowMessage('名称不能为空') + Exit
2. 创建 TCustomer → 控件取值 → Insert DB → ShowMessage('保存成功')
3. ModalResult := mrOk

推导的测试路径:
| # | 路径 | 操作 | 代码派生断言 |
|---|------|------|-------------|
| 1 | 成功路径 | 输入有效数据 → Save | 弹窗"保存成功" + 窗口关闭 |
| 2 | 名称为空 | edtName='' → Save | 弹窗"名称不能为空" |
| 3 | 取消操作 | 任意数据 → Cancel | 窗口关闭，DB 无新增 |
```

## H3. 代码路径 → 测试路径映射

| 代码结构 | 测试路径数 |
|---------|-----------|
| 顺序代码（无分支） | 1（成功路径） |
| `if ... then` | 2（真+假） |
| `if ... then ... else` | 2 |
| `case X of ... end` | N+1 |
| `try ... except ... end` | 2（正常+异常） |
| `for/while` | ≥2（0次 + 1+次） |

每条 if/case/try 至少对应一条自动化测试操作和断言。

## H4. 代码派生断言优先级

1. 纯业务类方法：`automate_delphi(action="test")`，通过参数化输入、`expected`、
   `expected_exception` 或 `assert_expr` 验证。
2. UI 状态：`rget` 直接检查属性值——最精确、最稳定。
3. `waitfor` + `msgscan` — 检查弹窗内容。
4. `capture` + OCR — 视觉验证（兜底）。
5. `rcall` 调用业务方法 — 仅用于单步灰盒诊断；可复用测试应进入 RTTI test suite。

纯业务方法测试先读取 `delphi://automation/rtti-test-runner`。用户可见交互仍生成 GUI
黑盒脚本，不能因为 RTTI 更方便就跳过真实 UI 路径。

## H5. 与自动化流程融合

在现有循环前插入代码分析阶段：

```
阶段 0: 代码分析 → 阶段 1-N: 感知→规划→执行→验证
```

代码分析的输出直接指导后续的步骤选择和断言定义。
