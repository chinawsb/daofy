# Delphi 程序调试指南 — AI 调试工作流

> 版本：v1.1 | 最后更新：2026-06-26
> 适用对象：使用 Daofy MCP Server 调试 Delphi 程序的大模型 AI

---

## 目录

1. [核心原则](#1-核心原则)
2. [调试前的环境确认](#2-调试前的环境确认)
3. [编译错误调试](#3-编译错误调试)
4. [运行时崩溃/异常调试](#4-运行时崩溃异常调试)
5. [逻辑错误调试](#5-逻辑错误调试)
6. [GUI/界面问题调试](#6-gui界面问题调试)
7. [运行时数据探查（RTTI）](#7-运行时数据探查rtti)
8. [内存泄漏/资源泄漏调试](#8-内存泄漏资源泄漏调试)
9. [常见 AI 误判模式](#9-常见-ai-误判模式)
10. [调试工作流速查表](#10-调试工作流速查表)
11. [控制台程序调试](#11-控制台程序调试)
12. [性能问题初诊](#12-性能问题初诊)
13. [工具调用异常恢复](#13-工具调用异常恢复)

---

## 1. 核心原则

### 1.1 先取证，后定论

**不要**凭经验或代码扫一眼就断言原因。Delphi 程序的错误可能来自：

| 错误来源 | 典型特征 | AI 易犯错误 |
|---------|---------|------------|
| 编译器版本/路径 | 编译失败，找不到 .dcu | 直接改代码 |
| 搜索路径缺失 | 找不到单元文件 | 判断为"缺少单元"→ 实际是路径配置问题 |
| 条件编译符号 | 特定配置下才出错 | 误判为代码逻辑错误 |
| DFM 资源问题 | 启动即崩溃 | 误判为代码空指针 |
| 运行时 DLL 缺失 | exe 启动失败 | 误判为代码问题 |
| 三方库版本不匹配 | 链接错误或访问违例 | 误判为 API 使用错误 |
| 编译器优化 bug | Release 才出现 | 误判为代码逻辑 |
| 线程同步 | 偶发崩溃、界面卡死 | 误判为死循环 |

**调试第一原则**：先收集证据链，再下结论。

### 1.2 证据链优先级

```
编译错误 → 先看编译器输出，再用 delphi_project(info) 查配置
运行时崩溃 → 先读 exception.log，再用自动化工具复现
逻辑错误 → 先用 RTTI/rget 探查运行时状态，再读源码
界面问题 → 先 capture 截图，再用 dumpstate 看控件树
```

### 1.3 逐步缩小范围

不要试图一步定位。每步应该排除一类可能性：

```
① 环境问题？    → check_environment
② 配置问题？    → delphi_project(action="info")
③ 编译问题？    → delphi_project(action="compile")
④ 代码逻辑？    → delphi_file(read) + delphi_kb(search)
⑤ 运行时状态？  → automate_delphi(rget) / delphi_rtti(discover)
```

---

## 2. 调试前的环境确认

在开始任何调试之前，先确认编译环境是健康的。

### 2.1 检查编译器状态

```python
check_environment(action="check")
```

返回信息包含：
- 可用编译器列表（名称、版本、路径）
- 默认编译器
- pasfmt 是否安装

### 2.2 检查项目配置

```python
# 获取完整项目配置
delphi_project(action="info", project_path="Project.dproj")
```

关键检查项：
- `DCC_UnitSearchPath` — 单元搜索路径是否完整
- `DCC_Define` — 条件编译符号是否正确（Debug/Release）
- `OutputType` — 输出类型（GUI/Console/DLL）
- `RuntimeLibrary` — 运行时链接方式（static/dynamic）
- `TargetPlatform` — 目标平台
- 源文件列表是否完整

### 2.3 检查注册表运行时环境

```python
delphi_project(action="runtime", base_dir="src")
```

扫描 `.pas`/`.dfm` 中的组件类名，检测是否遗漏必需的 uses 单元。

---

## 3. 编译错误调试

### 3.1 标准调试流程

```
编译失败
  │
  ├─ check_environment(action="check")          → ① 编译器可用？
  │     ↓ 不可用
  │   check_environment(action="detect")         → 重新检测
  │
  ├─ delphi_project(action="info")              → ② 项目配置正确？
  │     ↓
  │   检查 DCC_UnitSearchPath, DCC_Define 等
  │
  ├─ delphi_project(action="compile")           → ③ 重新编译，看完整输出
  │     ↓
  │   记录第一个 error 的位置和描述
  │
  ├─ delphi_file(action="read", file_path=...)  → ④ 读报错文件
  │
  ├─ delphi_kb(query="...", kb_type="delphi")   → ⑤ 查 API 定义
  │
  └─ 修复后重新编译验证
```

### 3.2 常见编译错误对照

| 编译器输出 | 可能原因 | 首选排查手段 |
|-----------|---------|-------------|
| `Fatal: Unable to execute file` | 编译器路径错误 | `check_environment(action="detect")` |
| `Fatal: File not found: xxx.dcu` | 缺少搜索路径 | `delphi_project(action="info")` 检查 `DCC_UnitSearchPath` |
| `E1026 File not found: xxx.dproj` | 项目路径错误 | 确认 `project_path` 指向正确的 `.dproj` |
| `E2003 Undeclared identifier: xxx` | 缺少 uses / 拼写错误 | `delphi_file(read)` 读文件，检查 uses 子句 |
| `E2010 Incompatible types` | 类型不匹配 | `delphi_kb(search_type="function")` 查函数签名 |
| `E2029 ')' expected but ',' found` | 泛型语法错误 | 检查 Delphi 版本是否支持泛型语法 |
| `E2037 Record type 'xxx' not found` | 类型未定义 | 检查 record 定义位置和作用域 |
| `E2064 Left side cannot be assigned to` | 赋值给只读属性 | `delphi_kb` 查该属性是否有 setter |
| `E2198 XE7+ 不支持此语法` | 编译器版本不匹配 | 检查 `.dproj` 中的编译器版本配置 |
| Exit code 2 | 编译事件失败或语法错误 | 查看详细输出定位 |
| `W1000 Symbol 'xxx' is deprecated` | 使用了废弃 API | `delphi_kb` 查替代方案 |
| `H2443 Inline function 'xxx' has not been expanded` | 内联函数未展开 | 加 `{$INLINE ON}` 或忽略 |
| `dcc32 不存在` | 未检测到编译器 | `check_environment(action="detect")` |

### 3.3 搜索路径问题排查

当编译器报告找不到 `.dcu` 或 `.pas` 时：

```python
# 1. 查看当前搜索路径
delphi_project(action="info", project_path="Project.dproj")

# 2. 确认三方库路径
# 使用 delphi_kb 搜索该单元所属的知识库
delphi_kb(query="xxx.pas", kb_type="thirdparty")

# 3. 在搜索路径中添加缺失的目录
delphi_project(action="set",
    project_path="Project.dproj",
    property_name="DCC_UnitSearchPath",
    value="$(BDSLIB)\$(PLATFORM)\release;..\SharedLib\src",
    config="Debug",
    platform="Win32")
```

**⚠️ 注意**：`DCC_UnitSearchPath` 中包含 `$(BDS)`、`$(BDSLIB)`、`$(PLATFORM)` 等 MSBuild 宏变量，不要把它们当作普通路径。

### 3.4 条件编译问题调试

当代码在 Debug 下正常、Release 下出错时：

```python
# 对比两个配置的编译符号
delphi_project(action="info", project_path="Project.dproj")
# 检查 DCC_Define 在不同配置中的差异

# 查看条件编译块的代码
delphi_file(action="read", file_path="Unit1.pas", start_line=line_no)
```

常见的原因：
- `{$IFDEF DEBUG}` 块中的辅助代码在 Release 下被跳过
- Release 下启用了优化导致时序问题
- `{$IFDEF RELEASE}` 中的代码有隐藏 bug

### 3.5 三方库/组件包编译失败

```python
# 1. 确认三方库知识库已构建
delphi_kb(action="stats")

# 2. 搜索三方库中的相关 API
delphi_kb(query="TComponentName", kb_type="thirdparty")

# 3. 检查组件包安装状态
delphi_project(action="info", project_path="Package.dproj")
```

### 3.6 文件编码相关问题

中文本地化环境下，源文件编码不一致会导致编译错误（非法字符、乱码）。

**常见场景**：
- 文件保存为 GBK 但编译器期望 UTF-8（或反之）
- BOM 头缺失导致编译器误判编码
- 多人协作时不同编辑器使用不同编码保存

**排查方法**：
```python
# 用不同编码读取文件，确认文件实际编码
delphi_file(action="read", file_path="Unit1.pas", encoding="gbk")
delphi_file(action="read", file_path="Unit1.pas", encoding="utf-8")

# 确认编码后可以转换编码
delphi_file(action="encode", file_path="Unit1.pas",
    to_encoding="utf-8-sig")  # 推荐统一转 UTF-8 with BOM
```

**预防**：项目统一使用 UTF-8 with BOM（`utf-8-sig`）编码保存所有 `.pas`/`.dfm` 文件。

---

## 4. 运行时崩溃/异常调试

### 4.1 标准流程

```
程序崩溃
  │
  ├─ 检查 exception.log / 错误对话框
  │     ↓
  │   记录异常类名、消息、地址
  │
  ├─ delphi_project(action="compile", run_verify=true)  → 复现崩溃
  │     ↓ run_verify 自动捕获崩溃
  │
  ├─ 分析异常类型：
  │     ├─ EAccessViolation    → 空指针 / 悬挂引用
  │     ├─ EInvalidPointer     → 重复 Free / 野指针
  │     ├─ EOutOfMemory        → 内存泄漏 / 大对象分配
  │     ├─ EAssertionFailed    → Assert 检查失败
  │     ├─ EConvertError       → 类型转换失败
  │     ├─ EExternalException  → 外部异常（DLL/COM）
  │     └─ EOSError            → Windows API 错误
  │
  ├─ automate_delphi(gui) 启动程序并探查状态
  │
  └─ 定位到具体代码行后修复
```

### 4.2 使用 run_verify 自动检测崩溃

```python
# 编译后自动运行 3 秒，检测是否启动即崩溃
delphi_project(action="compile",
    project_path="App.dproj",
    build_configuration="Debug",
    run_verify=True)  # ← 关键参数
```

`run_verify` 会自动：
1. 启动编译后的 exe
2. 等待 3 秒观察进程是否存活
3. 若崩溃，自动读取 `exception.log` 嵌入响应

### 4.3 使用自动化工具复现崩溃

对于复杂的运行时崩溃，使用 `automate_delphi` 复现：

```python
# 启动程序并执行操作复现崩溃
automate_delphi(
    action="gui",
    app_path="Win32/Debug/App.exe",
    keep_alive=True,
    script=[
        {"cmd": "goto", "target": "TMainForm"},
        {"cmd": "type", "target": "EditName", "value": "test"},
        {"cmd": "click", "target": "BtnSubmit"},
        # 等 5 秒看是否崩溃
        {"cmd": "wait", "ms": "5000"},
        {"cmd": "dumpstate"},  # 如果没崩溃，获取状态
    ])
```

**⚠️ 关于 run_verify 和 automate_delphi 的关系：**

| 场景 | 使用工具 | 说明 |
|------|---------|------|
| 编译后快速验证是否启动崩溃 | `compile(run_verify=true)` | 轻量，只等 3 秒 |
| 特定操作触发的崩溃 | `automate_delphi` | 可执行具体操作复现 |
| 长时间运行后的崩溃 | `automate_delphi` + `keep_alive` | 保持进程运行，逐步操作 |
| 偶发崩溃 | 多次 `automate_delphi` | 循环操作提高复现概率 |

### 4.4 常见运行时异常分析

#### EAccessViolation（访问违例）

```
可能原因：
  ├─ 对象已释放仍访问         → 检查 FreeAndNil 使用
  ├─ 字符串/数组越界          → 检查 Length 和索引
  ├─ 窗口句柄未创建           → 检查 HandleAllocated()
  ├─ 线程同步问题              → 检查 TThread.Synchronize / TMonitor
  ├─ DLL 导入函数签名不匹配    → 检查 external 声明
  └─ 接口引用计数错误          → 检查 _AddRef / _Release 平衡
```

**排查步骤**：

```python
# 1. 定位出错的代码区域
# 从异常地址或错误描述中找到相关单元和行号

# 2. 读取相关源码
delphi_file(action="read", file_path="Unit1.pas", start_line=line_no-20, end_line=line_no+10)

# 3. 检查涉及的对象创建和释放
# 搜索对象的 Free/Destroy 调用
# 搜索 FreeAndNil / Free 的使用

# 4. 查 API 确认对象创建方式
delphi_kb(query="TStringList", kb_type="delphi")
```

#### EInvalidPointer（无效指针）

```
几乎总是同一个原因：重复释放（Double Free）。
排查方向：
  ├─ 是否手动 Free 后又触发自动析构（Ownership 混淆）
  ├─ TObjectList 的 OwnsObjects 是否正确设置
  ├─ TComponent.FreeNotification 回调中重复释放
  ├─ 接口引用计数 + 手动 Free 混合使用
  └─ 多线程中同时释放同一对象
```

#### EOutOfMemory（内存不足）

```
排查方向：
  ├─ 内存泄漏累积 → 长时间运行后出现
  ├─ 大文件/图片一次性加载 → 流式处理
  ├─ 递归无终止条件 → 检查递归函数
  ├─ 字符串拼接导致内存碎片 → 用 StringBuilder
  └─ 三方库内存泄漏
```

### 4.5 运行时库/包缺失排查

当程序启动时提示"无法找到 xxx.bpl"或"无法定位程序输入点"：

```python
# 检查编译链接方式
delphi_project(action="info", project_path="Project.dproj")
# 检查 RuntimeLibrary 属性: static / dynamic
```

| 现象 | 原因 | 解决 |
|------|------|------|
| 找不到 `xxx.bpl` | 动态链接但 BPL 不在 PATH | 静态链接或分发 BPL |
| "无法定位程序输入点" | DLL 版本不匹配 | 检查三方库版本 |
| 启动后立即退出无提示 | FMX 运行时 DLL 缺失 | 静态链接 FMX 或准备运行环境 |
| `XXX.dll 丢失` | Windows 系统 DLL 缺失 | 安装 VC++ 运行库或 DirectX |

### 4.6 线程相关问题调试

偶发崩溃/随机行为往往指向线程同步问题。**这类调试与单线程完全不同**。

**特征识别**：
- 仅在高负载/多次操作后复现
- 每次崩溃位置不同
- Debug 模式下不出现，Release 出现（优化暴露了竞态条件）
- 加 Sleep/MessageBox 后崩溃消失 → 经典竞态条件标志

**排查方向**：

```python
# 1. 代码审查：检查共享变量的保护机制
# 2. 检查 TThread 的 terminated 标志是否被检查
# 3. 检查线程退出时资源是否清理
# 4. 检查 TThread.Synchronize/Queue 回调是否访问了已释放的对象

# 静态分析可检测部分线程安全问题
delphi_project(action="audit", base_dir="src")
```

**⚠️ 关键点**：`TThread.Synchronize` 和 `TThread.Queue` 的回调在*主线程*执行，
因此回调中访问的组件可能已在析构中——需要检查 `csDestroying` 标志。

---

## 5. 逻辑错误调试

### 5.1 代码骨架分析

先了解整体代码结构，避免盲目深入细节：

```python
# 获取项目代码骨架（最省 token 的方式）
delphi_project(action="ast", base_dir="src")

# 或查看单个文件的骨架
delphi_project(action="ast", file_path="Unit1.pas")
```

`ast` 返回所有类、方法、字段的概要，让你快速定位到相关代码区域。

### 5.2 代码审计

```python
# 运行静态分析
delphi_project(action="audit", base_dir="src")
```

50+ 静态分析规则覆盖：
- 空指针风险
- 资源泄漏（File/Handle/GDI/内存）
- 线程安全问题
- 类型转换风险
- 异常安全
- 代码质量（过长方法、过深嵌套）

### 5.3 读取源码定位

```python
# 按类名定位和读取
delphi_file(action="read", search_type="class",
    type_name="TMainForm",
    search_in="project",
    project_path="Project.dproj")

# 按函数名定位
delphi_file(action="read", search_type="function",
    function_name="Button1Click",
    search_in="project",
    project_path="Project.dproj")

# 读取特定行范围
delphi_file(action="read", file_path="Unit1.pas",
    start_line=50, end_line=100, show_line_numbers=True)
```

### 5.4 API 用法验证

AI 经常编造 Delphi API 签名。**在假设 API 用法错误之前，必须查知识库确认**：

```python
# 查 Delphi 官方 API
delphi_kb(query="TStringList.Create", kb_type="delphi")

# 查项目代码中的 API
delphi_kb(query="TMainForm", kb_type="project", project_path="Project.dproj")

# 查函数签名（精确匹配）
delphi_kb(query="TStringList.LoadFromFile", search_type="function")

# 查引用（评估修改影响）
delphi_kb(query="TStringList", search_type="reference", kb_type="project")
```

**⚠️ 重要**：当 AI 对某个 Delphi API 的用法不确信时，必须通过 `delphi_kb` 或 `delphi_file(action="read", search_type="class")` 确认官方定义。不要凭大模型训练数据中的记忆编造。

### 5.5 Git 历史回溯

```python
# 查看最近提交
code_hosting(action="git_log", dir=".", limit=20)

# 查看特定文件的修改历史
code_hosting(action="git_log", dir=".", files=["src/Unit1.pas"], limit=10)

# 查看具体提交的改动
code_hosting(action="git_show", dir=".", ref="abc1234")

# 比较当前和之前的差异
code_hosting(action="git_diff", dir=".", ref="HEAD~1..HEAD")
```

### 5.6 经验库复用

如果之前解决过类似问题，先查经验库：

```python
experience(action="search", query="EAccessViolation TStringList")
experience(action="search", query="列表项删除报错")
```

---

## 6. GUI/界面问题调试

### 6.1 启动自动化环境

使用 `automate_delphi` 的 GUI 模式与运行中的 Delphi 程序交互。

**前提**：目标程序已链接 `DaofyAutomation` 单元。

```python
# 启动程序并获取界面截图
automate_delphi(
    action="gui",
    app_path="App.exe",
    keep_alive=True,
    script=[
        {"cmd": "goto", "target": "TMainForm"},
        {"cmd": "capture", "target": "main_001"},
    ])
```

### 6.2 探查界面结构

```python
# 获取全部控件树（最全面的状态）
automate_delphi(
    action="gui",
    app_path="App.exe",
    script=[
        {"cmd": "goto", "target": "TMainForm"},
        {"cmd": "dumpstate"},  # ← 返回完整控件树 JSON
    ])

# 列出所有窗口
automate_delphi(
    app_path="App.exe",
    script=[{"cmd": "listwnd"}])

# 检视单个控件
automate_delphi(
    app_path="App.exe",
    script=[{"cmd": "rinspect", "target": "EditName"}])
```

### 6.3 获取运行时属性值

```python
# 读取控件属性
automate_delphi(
    app_path="App.exe",
    script=[
        {"cmd": "goto", "target": "TMainForm"},
        {"cmd": "rget", "target": "EditName", "prop": "Text"},
        {"cmd": "rget", "target": "ListBox1", "prop": "Items.Count"},
        {"cmd": "rget", "target": "StatusBar", "prop": "Caption"},
    ])
```

### 6.4 截图对比验证

```python
# 操作前截图
automate_delphi(
    app_path="App.exe",
    script=[
        {"cmd": "goto", "target": "TMainForm"},
        {"cmd": "capture", "target": "before"},
        {"cmd": "click", "target": "BtnRefresh"},
        {"cmd": "waitfor", "target": "ListView1", "prop": "Items.Count",
         "value": "10", "timeout": "5000"},
        {"cmd": "capture", "target": "after"},
    ])
```

### 6.5 对话框/弹窗处理

```python
# 扫描所有弹窗
automate_delphi(
    app_path="App.exe",
    script=[{"cmd": "msgscan"}])

# 关闭弹窗
automate_delphi(
    app_path="App.exe",
    script=[
        {"cmd": "msgclick", "target": "ok"},
    ])

# 弹出菜单
automate_delphi(
    app_path="App.exe",
    script=[
        {"cmd": "rclick", "target": "Grid1"},
        {"cmd": "dlgscan"},
        {"cmd": "dlgclick", "target": "复制"},
    ])
```

### 6.6 进程复用与状态保持

```python
# 第一次：启动并保持
automate_delphi(app_path="App.exe",
    script=[{"cmd": "goto", "target": "TMainForm"}, {"cmd": "capture", "target": "img1"}],
    keep_alive=True)

# 后续操作：复用已有进程
automate_delphi(app_path="App.exe",
    script=[{"cmd": "rget", "target": "EditName", "prop": "Text"}])

# 清理：发送 exit
automate_delphi(app_path="App.exe",
    script=[{"cmd": "exit"}])
```

**⚠️ 注意**：进程 5 分钟无调用会自动 kill，需要长时间保持时注意调用的频率。

### 6.7 控件数量统计（formsum）

快速评估窗体和 Frame 的复杂度，定位性能热点：

```python
automate_delphi(
    action="gui",
    app_path="App.exe",
    script=[{"cmd": "formsum"}])
```

返回信息包含每个 Form/Frame 的控件总数。**当控件数 > 100 时**，该窗体的循环/遍历操作可能是性能瓶颈。

**典型场景**：
- 大数据量 ListView/TreeView 的遍历操作
- 多重嵌套 Panel/Frame 导致的递归渲染
- 动态创建的控件未及时释放

### 6.8 截图文字识别（OCR）

当截图中有文字信息但无法通过 rget 获取时，使用 OCR 识别：

```python
# 先截图
automate_delphi(
    action="gui",
    app_path="App.exe",
    script=[
        {"cmd": "goto", "target": "TMainForm"},
        {"cmd": "capture", "target": "debug_screen"},
    ])

# 再 OCR 识别截图中的文字
ocr(action="recognize", image_path="docs/copyright/snapshots/debug_screen.png")
```

**OCR 与 automate_delphi 的配合方式**：
- `capture` → OCR：适用于错误对话框、提示信息等文本内容
- `capture` before/after → `ocr(diff)`：对比两次截图，自动标注差异区域
- OCR 是 GUI 调试的辅助手段，当 `rget` / `dumpstate` 无法获取文本内容时使用

**不适用场景**（优先用 rget/dumpstate 替代）：
- 控件 Caption/Text 属性 → `rget`
- 控件树结构 → `dumpstate`
- 列表数据 → `rcall` 调用业务方法获取

---

## 7. 运行时数据探查（RTTI）

### 7.1 使用 delphi_rtti 发现和调用

当程序已运行且链接了 DaofyAutomation 单元时，可以通过 RTTI 直接探查运行时状态。

```python
# 第一步：发现能力
delphi_rtti(action="discover", app_path="App.exe")

# 第二步：查看特定类的方法和属性
delphi_rtti(action="discover", app_path="App.exe", class_name="TMainForm")

# 第三步：调用业务方法获取数据
delphi_rtti(action="call",
    app_path="App.exe",
    class_name="TMainForm",
    method="GetOrderList",
    params={"status": "active"})
```

### 7.2 RTTI vs 自动化脚本

| 场景 | 推荐方式 | 原因 |
|------|---------|------|
| 读取控件属性 | `automate_delphi(rget)` | 更轻量，直接返回属性值 |
| 调用业务方法 | `delphi_rtti(call)` | 自动参数 Schema 校验 |
| 了解可用方法 | `delphi_rtti(discover)` | 返回完整方法清单+参数 |
| 复杂交互操作 | `automate_delphi(click/type)` | 模拟真实用户操作 |
| 控件树全量状态 | `automate_delphi(dumpstate)` | 完整的 DFM 控件树 |

---

## 8. 内存泄漏/资源泄漏调试

### 8.1 静态分析检测

```python
# 运行 P0 级审计规则
delphi_project(action="audit", base_dir="src", rules="P0")
```

静态分析可检测：
- TObject.Create 后缺少 Free
- GetWindowDC 后缺少 ReleaseDC
- 文件打开后未关闭
- 接口引用未释放

### 8.2 常见资源泄漏模式

```pascal
// ❌ 异常路径泄漏
procedure TForm1.LoadFile;
var
  SL: TStringList;
begin
  SL := TStringList.Create;
  SL.LoadFromFile('data.txt');  // 如果这句抛异常，SL 泄漏
  // 处理数据
  SL.Free;  // ← 只有正常路径才执行
end;

// ✅ 正确写法
SL := TStringList.Create;
try
  SL.LoadFromFile('data.txt');
  // 处理数据
finally
  SL.Free;
end;
```

```pascal
// ❌ GDI 资源泄漏
Canvas.Font.Name := 'Arial';  // 每次设置创建 GDI 对象
// 频繁调用且不释放 → GDI 对象耗尽

// ✅ 减少 GDI 创建
// 在 FormCreate 设置字体，不要在 Paint 中反复设置
```

### 8.3 代码审计后的误报排除

静态分析会产生误报，AI 需要逐条判断：

| 误报模式 | 判断方法 |
|---------|---------|
| 对象由 Owner 管理 | 检查是否设置了 Owner（`TComponent.Create(AOwner)`） |
| 接口引用计数释放 | Delphi 接口默认有引用计数，除非手动干扰 |
| 全局/单例对象 | 检查对象是否在 initialization/finalization 中管理 |
| 消息/事件中释放 | 检查 PostMessage 延迟释放模式 |

---

## 9. 常见 AI 误判模式

以下是 AI 调试 Delphi 程序时最容易犯的错误，**必须主动避免**：

### 误判 1：跳过环境检查，直接改代码

```
❌ 错误做法：
  "编译失败了，缺少 TStringList 单元 → 加 uses System.Classes"

✅ 正确做法：
  1. check_environment(action="check") → 确认编译器正常
  2. delphi_project(action="info") → 查搜索路径
  3. 定位到真正的错误原因
```

### 误判 2：凭记忆编造 API 签名

```
❌ 错误做法：
  "我记得 TStringList.LoadFromFile 接受一个 TEncoding 参数…"

✅ 正确做法：
  delphi_kb(query="TStringList.LoadFromFile", search_type="function")
  → 看实际签名再用
```

### 误判 3：把运行时错误当作代码错误

```
❌ 错误做法：
  看到 EAccessViolation → 立即判断是"某处空指针"→ 开始改代码

✅ 正确做法：
  1. 用 automate_delphi + dumpstate/rget 探查运行时状态
  2. 确认对象在崩溃时是否存活
  3. 再定位到代码
```

### 误判 4：忽略 DFM 资源问题

```
❌ 错误做法：
  程序启动崩溃 → 找 FormCreate / OnCreate 事件代码

✅ 正确做法：
  先排查 DFM 资源：
  - 检查 DFM 中引用的组件类是否存在
  - 检查 DFM 是否有二进制格式兼容问题
  - 检查 .res 资源文件是否存在
```

### 误判 5：条件编译/平台差异忽略

```
❌ 错误做法：
  "Debug 正常 Release 崩溃 → 肯定是代码有 bug"

✅ 正确做法：
  对比 Debug/Release 的编译设置差异：
  - 优化级别（优化可能暴露时序 bug）
  - 条件编译符号
  - 运行时检查（范围检查、溢出检查）
```

### 误判 6：三方库版本问题当作代码问题

```
❌ 错误做法：
  编译报找不到 xxx.dcu → "删掉这个单元的引用"

✅ 正确做法：
  1. delphi_kb(kb_type="thirdparty") → 搜三方库
  2. 检查三方库路径配置
  3. 可能需要构建三方库知识库
```

### 误判 7：无根据地修改 .dproj 配置

```
❌ 错误做法：
  "加一个搜索路径试试" → 直接修改配置

✅ 正确做法：
  delphi_project(action="info") 先查看当前配置
  → 确认修改前和修改后的影响
  → 用 delphi_project(action="set") 修改
```

### 误判 8：一次修改多处代码

```
❌ 错误做法：
  看到一个问题 → 顺手改了 5 个地方 → 编译失败 → 不知哪个改错了

✅ 正确做法：
  Git 提交或备份：
  1. 改一处 → 编译验证
  2. 改二处 → 编译验证
  3. 出错时 git diff 或 delphi_file(backup/restore) 回退
```

---

## 10. 调试工作流速查表

### 速查：工具选择

| 调试需求 | 使用的工具 | action |
|---------|-----------|--------|
| 编译器是否可用 | `check_environment` | check/detect |
| 项目配置详情 | `delphi_project` | info |
| 重新编译 | `delphi_project` | compile |
| 编译后验证是否崩溃 | `delphi_project` | compile + run_verify |
| 代码静态分析 | `delphi_project` | audit |
| 代码骨架概览 | `delphi_project` | ast |
| 读源代码 | `delphi_file` | read |
| 改源代码 | `delphi_file` | replace/insert/delete |
| API 定义查询 | `delphi_kb` | search |
| API 引用分析 | `delphi_kb` | search(search_type="reference") |
| 编码规范 | `get_coding_rules` | (section) |
| 启动程序并截图 | `automate_delphi` | gui |
| 控件树全貌 | `automate_delphi` | gui(dumpstate) |
| 读运行时属性 | `automate_delphi` | gui(rget) |
| 写运行时属性 | `automate_delphi` | gui(rset) |
| 调用方法 | `automate_delphi` | gui(rcall) |
| 运行时能力发现 | `delphi_rtti` | discover |
| 运行时方法调用 | `delphi_rtti` | call |
| 查看 Git 历史 | `code_hosting` | git_log/git_show |
| 复用经验 | `experience` | search |
| 控制台程序交互 | `automate_delphi` | console |
| 截图文字识别 | `ocr` | recognize |
| 截图对比 | `ocr` | diff |
| 视图控件树统计 | `automate_delphi` | gui(formsum) |
| 文件编码检测/转换 | `delphi_file` | encode |
| 版本回退 | `delphi_file` | backup/restore |
| 格式代码 | `delphi_file` | format |

### 速查：症状 → 首选动作

| 症状 | 第一步 | 第二步 |
|------|-------|--------|
| 编译失败，提示找不到文件 | `delphi_project(action="info")` 查搜索路径 | `check_environment(action="check")` 确认编译器 |
| 编译失败，语法错误 | `delphi_file(action="read")` 读报错文件 | `delphi_kb` 查 API 用法 |
| 程序启动即崩溃 | `compile(run_verify=true)` 捕获异常 | `automate_delphi(gui)` 探查状态 |
| 特定操作触发崩溃 | `automate_delphi(gui)` 复现崩溃 | `dumpstate` + `rget` 探查运行中状态 |
| 界面显示不正确 | `automate_delphi(capture)` 截图 | `dumpstate` 看控件属性 |
| 计算结果错误 | `delphi_project(action="ast")` 骨架分析 | `delphi_file(read)` 读关键代码 |
| 长时间运行后异常 | `delphi_project(action="audit")` 静态分析 | 检查资源泄漏/线程安全 |
| 提示找不到 BPL/DLL | `delphi_project(action="info")` 查链接方式 | 静态链接或准备运行环境 |
| Debug 正常 Release 崩溃 | 对比两个配置的编译设置 | 检查优化级别和条件编译 |
| 三方库编译失败 | `delphi_kb(action="stats")` 查 KB 状态 | 重新构建三方库 KB |
| 控制台输出异常 | `automate_delphi(console)` 交互测试 | 检查 stdin/stdout 处理 |
| 界面响应缓慢 | `automate_delphi(formsum)` 查控件数 | AST 分析主线程耗时操作 |
| 中文乱码/编码问题 | `delphi_file(encode)` 检测编码 | 统一 UTF-8 with BOM 保存 |
| 工具调用超时/失败 | 分类错误类型(§13.1) | 切换探查方式或重启 |

### 速查：每个调试阶段的输出产物

| 阶段 | 应产出的内容 |
|------|------------|
| 问题确认 | 异常信息 / 错误描述 / 复现步骤 |
| 环境确认 | 编译器状态 / 项目配置摘要 |
| 证据收集 | 代码片段 / 控件树 / 属性值 / 截图 |
| 根因分析 | 根因类型（配置/代码/环境/三方库）+ 证据链 |
| 修复方案 | 具体修改内容 + 预期效果 |
| 验证 | 编译通过 / run_verify 通过 / 截图确认 |

---

## 11. 控制台程序调试

### 11.1 自动化模式选择

控制台程序没有 VCL/FMX 窗口，使用 `automate_delphi` 的 `console` 模式而非 `gui` 模式：

```python
# 控制台交互：发送命令 + 等待指定输出
automate_delphi(
    action="console",
    app_path="Win32/Debug/ConsoleApp.exe",
    input="--help\n",              # 发送到 stdin
    expect="Usage:",                # 等待 stdout 中出现此模式
    timeout=15)
```

### 11.2 stdin/stdout 交互

```python
# 连续交互（仅最后一个 expect 作为返回条件）
automate_delphi(
    action="console",
    app_path="App.exe",
    input="user\npass123\n",       # 模拟登录输入
    expect="login successful",
    timeout=10)

# 无 expect：直接运行到退出，返回全部 stdout+stderr
automate_delphi(
    action="console",
    app_path="BackupTool.exe",
    args=["--backup", "data.db"],
    timeout=30)
```

### 11.3 进程复用（keep_alive）

```python
# 启动保持
automate_delphi(action="console", app_path="App.exe",
    keep_alive=True, expect="prompt>")

# 后续复用（app_path 匹配上一条的路径）
automate_delphi(action="console", app_path="App.exe",
    input="process file.txt\n", expect="OK")

# 退出清理
automate_delphi(action="console", app_path="App.exe",
    input="exit\n", keep_alive=False)
```

**⚠️**：控制台调试的 `keep_alive` 超时为 5 分钟，GUI 模式和 console 模式的 keep_alive 各自独立。

### 11.4 控制台 vs GUI 模式选择

| 判断依据 | 用 console | 用 gui |
|---------|-----------|--------|
| 有窗口界面 | — | ✅ |
| 纯命令行工具 | ✅ | — |
| 需要截图验证 | — | ✅ |
| 需要读控件属性 | — | ✅ (rget/dumpstate) |
| 只需 stdin/stdout | ✅ | — |
| 不确定 | (auto 模式自动检测 PE 头) |

---

## 12. 性能问题初诊

### 12.1 GUI 性能（formsum）

编译时计算所有 Form/Frame 的控件总量，预判 DFM 性能风险：

```python
automate_delphi(
    action="gui",
    app_path="App.exe",
    script=[
        {"cmd": "formsum"},
    ])
```

返回每个 Form/Frame 的控件数量，**优先排查控件数 > 100 的窗体中循环/遍历操作**。

### 12.2 响应延迟诊断

```python
# 1. AST 骨架快速了解整体架构
delphi_project(action="ast", base_dir="src")

# 2. 检查是否有耗时操作在主线程（文件/网络/数据库）
# 用 delphi_kb 搜索 TThread.CreateAnonymousThread 用法
delphi_kb(query="TThread", search_type="class", kb_type="project")

# 3. 检查是否缺少必要的异步处理模式
# 大数据量加载 → 分页 / 虚拟列表
# 文件操作 → TTask / TThread
# 数据库查询 → 异步查询 + 回调更新 UI
```

### 12.3 启动速度慢

```python
# 1. 检查 DFM 中是否有大量设计时将图片/数据嵌入
# 2. 检查 FormCreate / OnCreate 中的初始化逻辑
# 3. 检查是否有 DLL/BPL 延迟加载
delphi_project(action="info", project_path="Project.dproj")
# 检查 RuntimeLibrary 链接方式
```

### 12.4 工具选择速查

| 需求 | 工具/命令 |
|------|----------|
| 统计控件数量 | `automate_delphi(formsum)` |
| 代码骨架 | `delphi_project(ast)` |
| 静态分析（含性能模式） | `delphi_project(audit)` |
| 配置查看 | `delphi_project(info)` |

---

## 13. 工具调用异常恢复

### 13.1 异常分类与处理

工具调用失败时，不要立即重试或绕过——先分类：

| 错误现象 | 可能原因 | 处理方式 |
|---------|---------|---------|
| `File not found: xxx.dproj` | 项目路径错误 | 用 `delphi_kb` 或 `Glob` 搜索正确的 `.dproj` 位置 |
| `Timeout` (30s+) | 编译超时/进程卡死 | 增大 timeout 或检查 DCC 是否存在死循环编译 |
| `Access Denied` | 文件被占用 | 检查 IDE 是否打开该文件 |
| `Invalid JSON response` | 管道通信异常 | 重启程序（exit → 重新 launch） |
| `Connection lost` | 目标程序已退出 | 用 `compile(run_verify=true)` 检查是否启动即崩溃 |
| `RTTI discovery failed` | 程序未链接 DaofyAutomation | 改用 `automate_delphi(gui)` |
| `Unknown command: xxx` | 命令拼写错误 | `automate_delphi(gui)` 中 async 命令执行后返回 ACK 立即返回，需等待后续命令验证 |
| exit code 2 | 预/后编译事件失败 | 查看详细输出；检查 git hooks / 事件脚本 |

### 13.2 异步命令等待策略

`automate_delphi(gui)` 脚本中的命令分为 async 和 sync。async 命令（click/type/key/rcall/rset/move/drag/dlgclick/msgclick）发出后立即返回 ACK，不等待副作用完成。

**陷阱**：async 命令后立即执行依赖其副作用的 sync 命令，可能读到过时状态。

```
❌ 错误：点击后立即截图
  click → capture  → 可能截图时界面尚未更新

✅ 正确：点击后等待
  click → wait(ms=500) → capture
  或 click → waitfor(target=..., prop=..., value=...) → capture
```

### 13.3 回退与重试策略

```python
# 第一层：增加超时重试
# 第二层：切换探查方式
#    automate_delphi(gui) 失败 → 尝试 delphi_rtti 或反之
# 第三层：使用经验库查之前是否解决过同类异常
experience(action="search", query="工具调用异常 管道 超时")
```

### 13.4 并发写入保护

多个工具调用同时修改同一文件会导致冲突。`delphi_file(action="write")` 使用脏标记检测——未被读取就尝试写入的文件会被标记为"脏"并报错。

**安全做法**：
1. `delphi_file(action="read")` 读文件
2. 分析并确定修改方案
3. `delphi_file(action="write", edits=[...])` 提交编辑
4. 每次修改前确保已 read 最新版本

---

## 附录：调试信息速查

### Delphi 异常类层级

```
Exception
  ├─ EAbort                  不显示错误对话框的 silent 异常
  ├─ EAccessViolation        访问违例（空指针/悬挂引用）
  ├─ EAssertionFailed        Assert 失败
  ├─ EArgumentException      参数错误
  │    ├─ EArgumentOutOfRangeException
  │    └─ EArgumentNilException
  ├─ EConvertError          类型转换失败（StrToInt 等）
  ├─ EDatabaseError          数据库错误
  ├─ EDivByZero              整数除零
  │    └─ EZeroDivide        浮点除零
  ├─ EExternalException      Windows 结构化异常包装
  ├─ EInvalidCast            类型转换无效（as 操作符）
  ├─ EInvalidOperation       组件操作无效（没有 Handle 时操作）
  ├─ EInvalidPointer         无效指针（通常双重释放）
  ├─ EOSError                Windows API 错误
  ├─ EOutOfMemory            内存不足
  ├─ EOverflow               整数溢出
  ├─ ERangeError             范围检查失败（{$R+} 时）
  ├─ EStackOverflow          栈溢出（通常无限递归）
  └─ EStringListError        TStringList 操作错误
```

### .dproj 关键属性

| 属性名 | 意义 | 调试中查看的原因 |
|--------|------|----------------|
| `DCC_UnitSearchPath` | 单元搜索路径 | 找不到 .dcu 时 |
| `DCC_Define` | 条件编译符号 | Debug/Release 行为差异 |
| `DCC_Optimize` | 是否优化 | Release 崩溃 |
| `DCC_AssertionsAtRuntime` | 运行时 Assert | AssertionFailed 异常排查 |
| `DCC_RangeChecking` | 范围检查 | ERangeError 排查 |
| `DCC_OverflowChecking` | 溢出检查 | EOverflow 排查 |
| `RuntimeLibrary` | 运行时库链接方式 | 找不到 BPL 时 |
| `OutputType` | 输出类型 | exe/dll 相关配置 |
| `Base` | 基础输出目录 | 产物路径 |

### 调试相关命令行（仅用于参考，不得直接使用 dcc32/msbuild）

| 概念 | MSBuild 属性 | dcc32 参数 |
|------|-------------|-----------|
| 搜索路径 | `DCC_UnitSearchPath` | `-U` |
| 条件编译 | `DCC_Define` | `-D` |
| 输出路径 | `DCC_ExeOutput` | `-E` |
| 调试信息 | `DCC_DebugInfoInExe` | `-$D+` |
| 优化 | `DCC_Optimize` | `-$O+` |
| 范围检查 | `DCC_RangeChecking` | `-$R+` |

### 调试修改安全机制

`delphi_file` 在修改文件时有以下安全机制，AI 需理解并与工作流配合：

| 机制 | 触发条件 | AI 应对 |
|------|---------|--------|
| **重复检测** | 写入的内容与文件内容相同 | 无需处理，操作被跳过 |
| **脏标记** | 文件被读取后又被其他操作修改，未经重新读取就尝试写入 | 重新 `read` 获取最新内容后再提交编辑 |
| **自动备份** | 每次 write/replace/insert/delete 前自动创建备份并存于 `__history` | 无需手动操作，可在误修改后用 `backup/restore` 恢复 |
| **预览模式** | `preview=true` | 预览 diff 后再决定是否实际写入 |

```python
# 回退到上一个版本
delphi_file(action="backup", backup_action="restore",
    file_path="Unit1.pas")

# 列出所有备份版本
delphi_file(action="backup", backup_action="list",
    file_path="Unit1.pas")
```

**原则**：为防止 AI 一次修改多处导致难以回溯，应在每次修改后编译验证。出现意外时使用 `backup/restore` 回退。
