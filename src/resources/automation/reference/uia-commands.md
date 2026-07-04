<!-- @when: 查阅 UIAutomation 命令参考时 -->

# UIAutomation 命令参考
MCP resource URI: delphi://automation/uia-commands

#### 单击与鼠标交互

| 命令 | 用途 | 关键参数 |
|------|------|---------|
| `uia.click` | 左键单击控件 | target, [timeout=10] |
| `uia.rclick` | 右键单击控件 | target, [timeout=10] |
| `uia.dblclick` | 双击控件 | target, [timeout=10] |
| `uia.hover` | 悬停控件上方（触发 Tooltip） | target, [timeout=10] |
| `uia.drag` | 从目标拖拽到偏移坐标 | target, x, y, [timeout=10] |

示例：
```json
{"cmd": "uia.click", "target": "打开(&O)"}
{"cmd": "uia.drag", "target": "ScrollBar1", "x": 0, "y": 50}
```

#### 值操作与输入

| 命令 | 用途 | 关键参数 |
|------|------|---------|
| `uia.set` | 设置控件值（ValuePattern） | target, text, [timeout=10] |
| `uia.type` | 模拟键盘打字（SendKeys） | target, text, [timeout=10] |
| `uia.key` | 发送按键（Enter/Tab/Esc/Ctrl+S 等） | keys, [target] |
| `uia.toggle` | 切换开关状态（CheckBox/RadioButton） | target, [timeout=10] |

示例：
```json
{"cmd": "uia.set", "target": "文件名(N):", "text": "C:\\data\\import.xlsx"}
{"cmd": "uia.key", "keys": "{Enter}"}
```

#### 列表、树与选项

| 命令 | 用途 | 关键参数 |
|------|------|---------|
| `uia.select` | 选中项（ComboBox/ListBox/Tab/RadioGroup） | target, [item], [timeout=10] |
| `uia.expand` | 展开可折叠节点（Tree/ComboBox 下拉） | target, [timeout=10] |
| `uia.collapse` | 折叠节点 | target, [timeout=10] |
| `uia.invoke` | 调用控件默认操作（InvokePattern） | target, [timeout=10] |

示例：
```json
{"cmd": "uia.select", "target": "ComboBox1", "item": "选项二"}
{"cmd": "uia.invoke", "target": "确定"}
```

#### 导航与探查

| 命令 | 用途 | 关键参数 |
|------|------|---------|
| `uia.goto` | 查找并激活顶层窗口 | target, [timeout=10] |
| `uia.find` | 按条件查找控件，返回标识信息 | target, [condition], [scope], [timeout=10] |
| `uia.scan` | 扫描控件树，返回结构化 JSON | [target], [depth=3], [props], [timeout=10] |
| `uia.list` | 列出子控件（名称+类型+矩形） | target, [depth=1], [controltype] |

示例：
```json
{"cmd": "uia.goto", "target": "打开", "timeout": 5000}
{"cmd": "uia.scan", "target": "TTaskDialog", "depth": 5, "props": "name,class,rect"}
```

#### 窗口操作

| 命令 | 用途 | 关键参数 |
|------|------|---------|
| `uia.close` | 关闭窗口 | target, [timeout=10] |
| `uia.minimize` | 最小化窗口 | target, [timeout=10] |
| `uia.maximize` | 最大化窗口 | target, [timeout=10] |
| `uia.restore` | 恢复窗口正常大小 | target, [timeout=10] |
| `uia.move` | 移动窗口到指定坐标 | target, x, y, [timeout=10] |
| `uia.resize` | 调整窗口尺寸 | target, width, height, [timeout=10] |
| `uia.state` | 读取窗口状态（normal/minimized/maximized） | target, [timeout=10] |

示例：
```json
{"cmd": "uia.close", "target": "TMainForm"}
{"cmd": "uia.move", "target": "TMainForm", "x": 100, "y": 100}
```

#### 滚动与视区

| 命令 | 用途 | 关键参数 |
|------|------|---------|
| `uia.scroll` | 滚动控件（方向+量） | target, direction, [amount], [timeout=10] |
| `uia.wheel` | 鼠标滚轮滚动 | delta, [target] |
| `uia.scrollinto` | 将子项滚动到可视区域 | target, item, [timeout=10] |

示例：
```json
{"cmd": "uia.scroll", "target": "ListBox1", "direction": "down", "amount": 3}
{"cmd": "uia.scrollinto", "target": "ListView1", "item": "最后一条"}
```

#### 属性与状态读取

| 命令 | 用途 | 关键参数 |
|------|------|---------|
| `uia.get` | 读取控件常用属性 | target, [prop], [timeout=10] |
| `uia.exists` | 判断控件是否存在（不抛异常） | target, [timeout=10] |
| `uia.rect` | 获取控件边界矩形 | target, [timeout=10] |

`uia.get` 支持的 `prop` 取值: `name`, `value`, `enabled`, `automationid`, `classname`, `controltype`, `processid`, `runtimeid`, `isoffscreen`, `iskeyboardfocusable`, `haskeyboardfocus`, `acceleratorkey`, `accesskey`, `helptext`, `itemtype`, `itemstatus`, `culture`, `ispassword`, `labeledby`, `localizedcontroltype`, `orientation`, `frameworkid`, `providerdescription`, `issynchronizedinput`, `boundingrectangle`。省略 `prop` 时默认返回 `name` + `value` + `enabled` + `boundingrectangle`。

示例：
```json
{"cmd": "uia.get", "target": "Edit1", "prop": "value"}
{"cmd": "uia.exists", "target": "保存(&S)", "timeout": 3}
```

#### 可视化

| 命令 | 用途 | 关键参数 |
|------|------|---------|
| `uia.screenshot` | 截取控件/窗口区域截图 | target, [path], [region], [timeout=10] |

`region` 参数格式：`[left, top, width, height]`，相对于 target 控件客户区坐标。省略 `region` 时截取完整控件区域。

**截屏兜底策略**：`uia.screenshot` 基于 UIA `CaptureToImage()`，对 DirectX 3D 场景可能输出黑屏。检测到黑屏时，按以下流程回退：
1. `uia.rect` → 获取 target 的屏幕像素矩形
2. `mss` 截图 → 按像素坐标截取该区域（DXGI/BitBlt，可捕获 3D 内容）
3. 若 `mss` 仍黑屏 → 渲染层为 OpenGL / 硬件 Overlay / DRM 保护内容，当前不可自动化

示例：
```json
{"cmd": "uia.screenshot", "target": "TMainForm", "path": "mainform.png"}
{"cmd": "uia.screenshot", "target": "TMainForm", "region": [0, 0, 200, 50], "path": "titlebar.png"}
```

#### 等待与同步

| 命令 | 用途 | 关键参数 |
|------|------|---------|
| `uia.wait` | 等待控件满足条件 | target, [timeout=30], [condition=exist] |

`condition` 取值: `exist`（默认，等待出现）, `notexist`（等待消失）, `enabled`（等待可用）, `visible`（等待可见）, `ready`（等待空闲，`WindowPattern.WaitForInputIdle()`）。

示例：
```json
{"cmd": "uia.wait", "target": "保存(&S)", "timeout": 15, "condition": "enabled"}
{"cmd": "uia.wait", "target": "进度对话框", "timeout": 60, "condition": "notexist"}
```

#### 查找策略

| 方式 | 格式 | 说明 |
|------|------|------|
| 控件文本（Name） | `"目标文本"` | 按控件的 Name 属性匹配（最常用） |
| AutomationId | `#id值` | 按 AutomationId 精确匹配 |
| 类名 | `.ClassName` | 按 ClassName 匹配，不区分大小写 |
| 控件类型 | `@ControlType` | 按 UIA ControlType 查找 |
| 复合条件 | `条件1 && 条件2` | 同时匹配文本和类名，用 `&&` 连接 |
| 坐标点（由近及远） | `(x,y)` | 从该坐标点向上查找最近的控件 |

示例：
```json
{"cmd": "uia.click", "target": "打开(&O)"}
{"cmd": "uia.click", "target": "#btnSave"}
```

#### 通用参数

所有 `uia.xxx` 命令共享以下可选参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `timeout` | int | 10 | 控件查找超时（秒），超时未找到抛异常 |
| `condition` | string | — | 仅 `uia.wait` 使用，其他命令忽略 |
| `depth` | int | — | 查找深度，不指定则全深度搜索 |
| `scope` | string | `"children"` | `uia.find` / `uia.scan` 搜索范围：`children` / `descendants` / `all` |
| `found_index` | int | 1 | 匹配到多个时取第几个（1-indexed） |

示例：
```json
{"cmd": "uia.click", "target": "打开(&O)", "timeout": 15, "depth": 3}
{"cmd": "uia.get", "target": ".Edit", "prop": "value", "found_index": 2}
```