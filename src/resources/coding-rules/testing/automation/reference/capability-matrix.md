<!-- @when: 需要根据场景选择自动化命令/工具时 -->
<!-- @see: controls-operation-reference.md（按控件类型查推荐命令与陷阱） -->
# 自动化能力选型矩阵

MCP URI: `delphi://automation/capability-matrix`

## 自动化能力分类表

大模型在选择自动化命令时，先按下方流程判断场景，再从场景表中选择能力。

### 快速判断流程

```
目标 UI 在 Delphi 进程内？
  ├─ 是 → 有 RTTI/源码？→RTTI (rget/rset/rcall/rinspect) | 否→黑盒 (click/type/key/waitfor/capture)
  ├─ 否 → OS 弹窗？→文件→dlgfile | 文件夹→dlgfile path=目录 | 消息→msgscan+msgclick/close | 其他→UIA
  ├─ 否 → 浏览器？→ Chrome 层→UIA | 网页 DOM→Playwright/Selenium | 截图可见→OCR
  └─ 否 → 第三方 Win 应用？→有 UIA→UIA | 仅 Win32 消息→msgscan/click/close | 均不可→OCR
```

### 场景 → 能力映射

| # | 场景 | 测试类型 | 推荐命令 | 可选/后备 | 不可用 | 理由 |
|---|------|---------|---------|----------|-------|------|
| 1 | **读取 Delphi 组件属性** | 白盒/灰盒 | `rget` | — | `uia.get` | RTTI 暴露全部 published 属性；UIA 仅读 Name/Value/ControlType |
| 2 | **修改 Delphi 组件属性** | 白盒/灰盒 | `rset` | `click`（仅 Toggle） | `uia.set` | RTTI 直接写属性；黑盒应改用 click 模拟用户操作 |
| 3 | **调用 Delphi 组件方法** | 白盒/灰盒 | `rcall` | — | `click` | RTTI 方法调用最精确；仅用于测试夹具初始化/诊断 |
| 4 | **探查 Delphi 组件结构** | 白盒/灰盒 | `rinspect`(支持 visibility 参数) | — | `uia.scan` | RTTI 返回完整类型信息，UIA 只返回有限属性 |
| 4b | **RTTI 单元测试** | 白盒/灰盒 | `automate_delphi(action="test")` | `run_tests`(底层协议) | `rcall`(单步) | `target/className` 双模式；支持 `RegisterTestClass`、`RegisterFixture`、构造/方法参数、重载、`expected`、`expected_exception`、`assert_expr`、逐例 timeout 和稳定统计。详见 `delphi://automation/rtti-test-runner` |
| 5 | **黑盒操作 Delphi 控件** | 黑盒 | `click` | — | `rcall`/`rset` | click 模拟真实用户操作，不依赖内部实现 |
| 6 | **向 Delphi 输入框输文本** | 黑盒 | `type` | — | `rset` | 黑盒应模拟用户打字完整行为 |
| 7 | **发送键盘按键** | 黑盒 | `key` | — | — | key 发送虚拟键码 |
| 8 | **等待控件状态** | 所有 | `waitfor` | — | `time.sleep` | waitfor 内部轮询+超时，不阻塞事件循环 |
| 9 | **获取 Delphi 窗口 UI 快照** | 所有 | `formsum`/`dumpstate` | — | `uia.scan` | 返回结构化 JSON，含组件层次/属性值 |
| 10 | **列出所有顶层窗口** | 所有 | `listwnd` | `uia.scan` | — | listwnd 枚举所有可见 HWND |
| 11 | **拖拽控件** | 黑盒 | `drag` | — | — | 管道原生支持 drag |
| 12 | **截图对比回归验证** | 所有 | `capture` + OCR `diff` | — | — | capture 管道截图，diff 像素对比 |
| 13 | **OS 文件打开/保存对话框** | 所有 | `dlgfile` | — | `click` 定位文件名框 | dlgfile 通过 HWND 操作 |
| 14 | **按显示文本定位控件边界**（替代 OCR） | 所有 | `textbounds` | `capture`+OCR `recognize` 或 `uia.*` | — | ⚠️ **仅覆盖 GDI/GDI+ 渲染栈**（VCL/FMX Windows/第三方 GDI 库）；**不覆盖 DirectUI/WPF/UWP/Electron/Qt Quick**（用 `uia.*`），不覆盖 WebView（用 OCR）。详见 `script-schema.md` textbounds 章节"适用范围与限制" |

### 操作系统弹窗专项

| # | 弹窗类型 | 推荐策略 | 步骤 |
|---|---------|---------|------|
| 14 | **MessageBox/确认弹窗** | `msgscan` + `msgclick`/`msgclose` | ① msgscan 轮询；② msgclick（按钮文本）或 msgclose（WM_CLOSE） |
| 15 | **打开文件对话框**（TOpenDialog） | `msgscan` + `dlgfile` | ① msgscan 检测；② dlgfile path="C:\\file.txt" |
| 16 | **保存文件对话框**（TSaveDialog） | 同上 | 同上，文件不存在时自动创建 |
| 17 | **SHBrowseForFolder 文件夹选择** | `dlgfile path=目录` | 优先 dlgfile；不支→uia.scan 找 TreeView(经典)/uia.get 找地址栏 Combobox→type 路径→key Enter |
| 18 | **系统颜色/字体对话框** | `uia.xxx`（fallback OCR） | 先 uia.scan 探查；UIA 不可用时 OCR 视觉定位 |
| 19 | **UAC 提权弹窗** | ❌ 不可自动化 | 在安全桌面，UIA/消息/OCR 均无法访问 |

### UIA 命令全集（非注入黑盒）

通过 Python uiautomation 库跨进程操作 UIA 兼容控件，无需修改被测程序源码。

| 命令 | 用途 | 关键参数 |
|------|------|---------|
| `uia.click` | 左键单击 | target, timeout |
| `uia.rclick` | 右键单击 | target, timeout |
| `uia.dblclick` | 双击 | target, timeout |
| `uia.hover` | 鼠标悬停 | target, timeout |
| `uia.drag` | 拖拽到偏移 | target, x, y |
| `uia.set` | 设置文本值 | target, text, timeout |
| `uia.type` | 键盘打字 | target, text, timeout |
| `uia.key` | 发送按键 | keys |
| `uia.toggle` | 切换开关 | target, timeout |
| `uia.select` | 选中列表项 | target, item, timeout |
| `uia.expand` | 展开节点 | target, timeout |
| `uia.collapse` | 折叠节点 | target, timeout |
| `uia.invoke` | 调用默认动作 | target, timeout |
| `uia.goto` | 激活/聚焦窗口 | target, timeout |
| `uia.find` | 查找控件 | target, condition, depth |
| `uia.scan` | 扫描控件树 | target, depth, props |
| `uia.list` | 列出子控件 | target, depth |
| `uia.get` | 读取属性 | target, prop, timeout |
| `uia.exists` | 判断存在 | target, timeout |
| `uia.state` | 读取窗口状态 | target, timeout |
| `uia.close` | 关闭窗口 | target, timeout |
| `uia.minimize` | 最小化 | target, timeout |
| `uia.maximize` | 最大化 | target, timeout |
| `uia.restore` | 恢复窗口 | target, timeout |
| `uia.move` | 移动窗口 | target, x, y |
| `uia.resize` | 调整尺寸 | target, width, height |
| `uia.scroll` | 滚动控件 | target, direction, amount |
| `uia.wheel` | 鼠标滚轮 | delta |
| `uia.scrollinto` | 滚动项到视区 | target, item |
| `uia.screenshot` | 截图 | target, path |
| `uia.wait` | 等待条件 | target, timeout, condition |
| `uia.rect` | 获取边界矩形 | target |

### OCR 视觉能力（pip install daofy-for-delphi[ocr]）

| 命令 | 用途 | 适用场景 | 不适合 |
|------|------|---------|-------|
| `recognize` | 识别图片中文字 | 网页内容、自定义绘制控件、虚拟化桌面、UIA 不可达 UI | 百毫秒级；文字被遮挡/过小时准确率下降 |
| `detect` | 检测图片中文本框位置 | 需通过坐标点击特定文字区域 | 纯结构验证优先用 rget/uia.get |
| `color` | 分析指定区域颜色 | 验证指示灯状态、UI 主题色、异常颜色告警 | 精确色彩值需有基线 |
| `match` | 图标模板匹配 | 找特定图标/按钮图片位置 | 图标尺寸/颜色变化大时匹配失败 |
| `diff` | 两张截图对比 | 回归测试 UI 像素级差异 | 动效/短暂状态切换导致误报 |

## 能力选型：分场景决策指南

格式：**首选 → 回退 → 兜底**，标记 ❌ 为禁用方案。

### Delphi 进程内控件操作

| 场景 | 灰盒（有 RTTI/源码） | 黑盒（仅 UI 入口） | 禁用 |
|------|---------------------|-------------------|------|
| **点击按钮/菜单/链接** | `click` | `click` | ❌ `rcall`/`rset` |
| **读取属性** | `rget` → `uia.get` | `rget` → `uia.get` | ❌ 黑盒 rcall/rset；rget 只读可用 |
| **写入输入框** | `rset` → `type` | `type` → `uia.set` | ❌ 黑盒 rset |
| **等待控件就绪** | `waitfor` | `waitfor` → `uia.wait` | ❌ 裸 `time.sleep` |
| **获取 UI 快照** | `dumpstate`/`formsum` | `dumpstate`（限安全属性）→ `uia.scan` | ❌ 黑盒 rcall 触发 getter |
| **发送键盘按键** | `key` | `key` | — |
| **拖拽** | `drag` | `drag` → `uia.drag` | — |
| **右键菜单** | `rclick` | `rclick` → `uia.rclick` | — |

### 弹窗处理

| 弹窗类型 | 识别 | 操作 | 回退 | 禁用 |
|---------|------|------|------|------|
| **MessageBox** | `msgscan` | `msgclick`/`msgclose` | — | ❌ 直接 uia.click 坐标 |
| **VCL Form 模态**（fsModal） | `dlgscan` | `dlgclick` | `uia.scan` + `uia.click` | ❌ 裸坐标点击 |
| **TTaskDialog** | `uia.scan` | `uia.click`（按钮文本） | — | ❌ msgscan 检测不到 |
| **IFileDialog**（Win10+） | `uia.goto`（找标题） | `uia.set`（文件名）+ `uia.click`（确认） | `capture` + OCR | ❌ msgscan/dlgfile |
| **TOpenDialog/TSaveDialog**（经典） | `msgscan` | `dlgfile path=...` | `uia.goto` + `uia.set` + `uia.click` | ❌ 坐标点击文件名框 |
| **SHBrowseForFolder** | `uia.scan` | `dlgfile path=目标目录` | `uia.scan` 找 TreeView + `uia.type` 地址栏 + `key` Enter | ❌ 裸键盘导航 |
| **颜色/字体对话框** | `uia.scan` | `uia.click`/`uia.set` | `capture` + OCR | ❌ msgscan |
| **VCL Style 主题化弹窗** | `msgscan`/`dlgscan` | 常规管道命令 | — | — |
| **UAC 提权弹窗** | ❌ 不可自动化 | 需禁用 UAC 或人工确认 | — | — |

### 跨进程 / 第三方应用操作

| 场景 | 首选 | 回退 | 禁用 |
|------|------|------|------|
| **激活/聚焦外部窗口** | `uia.goto` | — | ❌ `goto`（仅 Delphi 进程内） |
| **点击外部控件** | `uia.click` | `uia.invoke`（click 失效时） | ❌ `msgclick` |
| **读取外部控件文本** | `uia.get` | OCR `recognize` | ❌ `rget` |
| **扫描外部窗口控件树** | `uia.scan` | — | ❌ `dumpstate`/`formsum` |
| **向外部输入框打字** | `uia.type` | `uia.set`（支持 ValuePattern） | ❌ `type`（管道无效） |
| **等待外部控件出现** | `uia.wait` | — | ❌ `waitfor`（仅 Delphi 进程内） |
| **外部窗口截图** | `uia.screenshot` | `capture`（需 HWND） | — |

### 浏览器操作

| 场景 | 首选 | 回退 | 禁用 |
|------|------|------|------|
| **操作地址栏** | `uia.goto` 聚焦 → `uia.type` 地址栏 → `uia.key` Enter | — | ❌ 坐标点击 |
| **点击工具栏按钮** | `uia.click` | — | — |
| **切换标签页** | `uia.click`（标签名） | `uia.select`（标签名） | ❌ 坐标定位 |
| **读取网页标题** | `uia.get`（窗口 Name） | — | ❌ `rget` |
| **操作网页 DOM** | ❌ **用 Playwright/Selenium** | OCR `recognize` + `detect` | ❌ `uia.xxx` |
| **读取网页文字** | ❌ **用 Playwright/Selenium** | OCR `recognize` | ❌ `uia.get` |

### 列表、树与选项操作

| 场景 | 首选 | 回退 | 禁用 |
|------|------|------|------|
| **Delphi TComboBox/ListBox 选中项** | `click ControlName@ItemCaption` | `uia.select` | ❌ 坐标点击 |
| **Delphi TTreeView 展开/折叠** | `click`（节点图标区） | `uia.expand`/`uia.collapse` | ❌ rcall |
| **跨进程 ComboBox 选择** | `uia.select` | `uia.expand` → `uia.click` 选项 | — |
| **跨进程 TreeView 展开** | `uia.expand` | `uia.click`（展开图标） | — |
| **跨进程 Tab 切换** | `uia.click`（标签名） | `uia.select`（标签名） | ❌ 坐标 |
| **CheckBox/RadioButton 切换** | `click`（Delphi 内） | `uia.toggle`（跨进程） | ❌ rset（黑盒） |
| **列表项滚动可见** | `uia.scrollinto` | `uia.scroll` 方向+量 | — |
| **按文本定位列表/树/标签页项** | `textbounds`（mode=auto） | `capture`+OCR | ❌ 裸坐标点击 |

### 验证与断言

| 场景 | 首选 | 回退 | 禁用 |
|------|------|------|------|
| **验证属性值** | `rget` + `assert_expr`（Delphi）/ `uia.get` + `assert_expr`（跨进程） | — | ❌ 无断言的 capture |
| **验证控件存在** | `uia.exists` | `uia.scan` → 搜索 | ❌ try-except 捕获 |
| **验证弹窗未弹出** | `msgscan` + `assert_expr == 'NOD'` | `uia.wait` condition=notexist | ❌ 固定延时 |
| **验证窗口状态** | `uia.state` | — | — |
| **视觉对比（回归）** | `capture` + OCR `diff` | `uia.screenshot` + OCR `diff` | ❌ 仅肉眼观察 |
| **验证文本无截断** | `textbounds`（visible_state=full 即无截断） | `capture` + OCR `recognize` | ❌ 仅测像素宽度 |
| **验证布局对齐** | `capture` + OCR `color`（区块边界） | `uia.rect` 计算间距 | ❌ 凭感觉判断 |

### 通用优先级速查

```
操作目标
├─ Delphi 进程内 + 有 RTTI → RTTI (rget/rset/rcall/rinspect)
├─ Delphi 进程内 + 纯黑盒 → 管道 (click/type/key/waitfor/capture)
├─ Delphi 进程内 + 按文本定位控件 → textbounds（替代 OCR，mode=auto）⚠️ 仅 GDI/GDI+ 渲染栈；FMX 跨平台非 Windows 或 DirectUI/WPF/UWP/Electron/WebView 控件不覆盖，用 uia.* 或 OCR
├─ 系统弹窗
│   ├─ MessageBox → msgscan + msgclick/msgclose
│   ├─ 文件对话框 → dlgfile
│   ├─ 文件夹选择 → dlgfile path=目录
│   ├─ TTaskDialog → uia.xxx
│   └─ IFileDialog → uia.xxx
├─ 第三方 Windows 应用 → uia.xxx
├─ 浏览器 Chrome 层 → uia.xxx
├─ 网页 DOM → Playwright/Selenium
└─ 以上都无法覆盖 → OCR
```
