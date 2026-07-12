<!-- @when: GUI 程序编译通过后，需进行 UI 交互验证 -->
<!-- @chain: before=console-testing.md, after=review-table.md -->

## ⑧ 自动化 UI 交互测试

编译通过（可选 run_verify）后，对 GUI 程序进行交互操作和截图验证。

> AI 生成或修改 DFM 后，先执行 `delphi_project(action="layout", base_dir="...")` 做静态布局审计；通过后再进入本章的运行时 UI 验证。

### 启用流程

首次接入 → 按 [../automation/scenarios/base.md](../automation/scenarios/base.md) 的「启用流程」操作（前置判断 → 修改 .dpr → 编译 → 冒烟验证）。

关键约束：
- **`AutoStart` 必须在 `Application.Initialize` 之前调用**
- **优先用 `in` 子句直接引用**（无需改 .dproj 配置，AI 可直接写）；已有搜索路径体系的项目可用搜索路径方式
- 已配置过的项目直接跳到「工具调用」开始写脚本

### 工具调用
```python
automate_delphi(app_path="App.exe", script=[...])
automate_delphi(action="gui", app_path="App.exe", script=[...])
automate_delphi(action="auto", app_path="App.exe", script="script.json", keep_alive=True)
```
`action="auto"` 自动检测 PE 头 Subsystem 字段。

### 通信架构
```
Python                              Delphi
  ── CreateFile(\\.\pipe\daofy_auto) → 管道线程接收 JSON
  ── WriteFile(JSON request)        → 主线程执行
  ←── ReadFile(JSON response)       ← 返回结果/ACK
```

### 命令同步/异步分类
| 同步 | 异步 |
|------|------|
| goto, capture, dumpstate, listwnd, formsum | click, rclick, dblclick |
| wait, waitfor, dlgscan, msgscan, msgclose | hover, move, drag |
| dlgfile, snapdir, exit | type, key |
| rget, rinspect | rcall, rset, msgclick, dlgclick |

### keep_alive
- `keep_alive=True` 进程保持运行，5 分钟未用自动清理
- 新建进程首次调用自动设置 snapdir

### 协议
- 同步命令阻塞等待返回；异步立即 ACK
- 响应：`{"reqId":"step_0","status":"ok","data":"OK"}`
- >64KB 自动分块（ERROR_MORE_DATA 循环读）

---

### 场景索引

完整脚本字段定义见 `delphi://automation/script-schema`（MCP Resource）。各场景文件包含策略描述和可复用 JSON 模板：

| 场景 | 对应文件 | 适用时机 |
|------|---------|---------|
| A. 冒烟测试 | [../automation/scenarios/a-smoke.md](../automation/scenarios/a-smoke.md) | 验证程序可启动、主窗体就绪 |
| B. 登录流程 | [../automation/scenarios/b-login.md](../automation/scenarios/b-login.md) | 用户名密码输入、登录状态切换 |
| C. 表单数据录入 | [../automation/scenarios/c-data-entry.md](../automation/scenarios/c-data-entry.md) | 填写表单并提交保存 |
| D. 列表/表格行操作 | [../automation/scenarios/d-grid.md](../automation/scenarios/d-grid.md) | 新增/编辑/删除数据行 |
| E. 树形导航 | [../automation/scenarios/e-tree-navigation.md](../automation/scenarios/e-tree-navigation.md) | 树节点展开/折叠/选中 |
| F. 搜索/筛选 | [../automation/scenarios/f-search.md](../automation/scenarios/f-search.md) | 搜索命中、未命中、结果更新 |
| G. 模态对话框 | [../automation/scenarios/g-modal-dialogs.md](../automation/scenarios/g-modal-dialogs.md) | MessageBox / OpenDialog / 确认框 |
| H. 多步向导 | [../automation/scenarios/h-wizard.md](../automation/scenarios/h-wizard.md) | Wizard 步骤切换和提交 |
| I. 右键菜单 | [../automation/scenarios/i-context-menu.md](../automation/scenarios/i-context-menu.md) | ContextMenu 弹出和选择 |
| J. DirectUI 弹窗 | [../automation/scenarios/j-directui.md](../automation/scenarios/j-directui.md) | IFileDialog / TTaskDialog / uia.xxx 命令 |
| K. 文本完整性 | [../automation/scenarios/k-text-completeness.md](../automation/scenarios/k-text-completeness.md) | OCR 检测截断/省略号/溢出 |
| L. 布局视觉对齐 | [../automation/scenarios/l-layout.md](../automation/scenarios/l-layout.md) | 左对齐/间距/重叠/跨 DPI |
| M. 控件定位策略 | [../automation/scenarios/m-control-targeting.md](../automation/scenarios/m-control-targeting.md) | 文本优先/坐标校准/DPI 系数 |
| N. 等待与条件同步 | [../automation/scenarios/n-wait-strategy.md](../automation/scenarios/n-wait-strategy.md) | waitfor 优先/禁用裸固定延时 |
| O. 控件重建安全 | [../automation/scenarios/o-control-rebuild.md](../automation/scenarios/o-control-rebuild.md) | Rescan/Reload 后控件重建等待 |
| 附录: 核对表 | [../automation/scenarios/checklist.md](../automation/scenarios/checklist.md) | 27 条黑盒测试质量门禁 |

### 场景选择原则

先跑冒烟(A)确认主流程通畅 → 再按测试目标选 B-O。同一测试文件可组合多个场景的步骤（如 登录B → 搜索F → 选中行D → 编辑D → DPI异常检查K → 布局对齐L → 控件定位校准M → 重建安全O）。

通配模板（快速套用任意场景）：
```json
[
  {"cmd":"goto","target":"T<目标窗体>","note":"等待窗体就绪"},
  {"cmd":"<命令>","target":"<目标>","<参数>":"<值>"},
  {"cmd":"waitfor","target":"<状态目标>","prop":"<属性>","value":"<期望值>","timeout":5000},
  {"cmd":"capture","target":"<截图名称>"},
  {"cmd":"exit"}
]
```

> 场景文件位于 `automation/scenarios/` 目录，通过相对路径引用。基础设施（通信/协议/tool 调用）见 [../automation/scenarios/base.md](../automation/scenarios/base.md)。架构方法论见 `automation/architecture.md`。
