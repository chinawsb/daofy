<!-- @when: 需要对 Delphi 程序进行自动化 UI/Console 测试时 -->
<!-- @chain: after=../ui.md -->

## ⚙ 自动化测试架构 — 感知·规划·执行·反馈循环

自动化测试文档统一位于 `resources/coding-rules/testing/automation/`，按职责分为三层：

```
resources/coding-rules/testing/automation/
├── index.md                 ← 本文件，总入口
├── architecture.md          ← 顶层方法论（RTTI/OCR 决策矩阵、感知-执行-验证循环、代码感知测试）
├── reference/               ← 框架参考文档
│   ├── workflow.md          — 自动化测试工作流总览
│   ├── rtti-test-runner.md  — 白盒/灰盒 RTTI 单元测试、fixture、超时与报告
│   ├── script-schema.md     — 脚本格式、命令列表、参数说明
│   ├── script-generation-workflow.md — AI 生成脚本流程
│   ├── report-schema.md     — 报告结构、first_failure 处理
│   ├── repair-loop.md       — 失败信号分类 → 修复 → 重试循环
│   └── inline-unit.md       — 进程内自动化单元与跨平台传输协议
└── scenarios/               ← 场景模板（A-O，含策略描述和可复用 JSON）
    ├── base.md, a-smoke.md … o-control-rebuild.md, checklist.md
```

### 文件索引

| 文件 | @when 适用场景 | 说明 |
|------|---------------|------|
| [architecture.md](architecture.md) | 理解 RTTI/OCR 决策、感知-规划-执行循环、代码感知方法论 | 顶层自动化架构 |
| [reference/workflow.md](reference/workflow.md) | 首次进行自动化测试时 | 自动化测试工作流总览 |
| [reference/rtti-test-runner.md](reference/rtti-test-runner.md) | 直接测试 Delphi 类方法或替代 DUnitX 运行能力时 | RTTI 测试接入、注册、断言、超时和报告 |
| [reference/inline-unit.md](reference/inline-unit.md) | 需了解进程内自动化单元和 NamedPipe/Unix Socket 传输时 | 内联自动化单元文档 |
| [reference/script-schema.md](reference/script-schema.md) | 编写 `automate_delphi` 脚本命令时 | 脚本格式、命令列表、参数说明 |
| [reference/script-generation-workflow.md](reference/script-generation-workflow.md) | 从 Delphi 源码生成自动化脚本时 | AI 生成脚本的工作流程 |
| [reference/report-schema.md](reference/report-schema.md) | 分析自动化测试报告时 | 报告结构、first_failure 处理 |
| [reference/repair-loop.md](reference/repair-loop.md) | 自动化测试失败需要修复时 | 分类失败信号 → 修复 → 重试循环 |

### UI 测试场景（A-O）

各场景文件位于 `scenarios/`，包含策略描述和可复用 JSON 模板：

| 场景 | 文件 | 说明 |
|------|------|------|
| 基础设施（启用） | [scenarios/base.md](scenarios/base.md) | 前置判断/启用流程(4步)/通信架构/协议/keep_alive/故障恢复 |
| A. 冒烟测试 | [scenarios/a-smoke.md](scenarios/a-smoke.md) | 程序启动与主窗体验证 |
| B. 登录流程 | [scenarios/b-login.md](scenarios/b-login.md) | 凭据输入与登录状态切换 |
| C. 表单数据录入 | [scenarios/c-data-entry.md](scenarios/c-data-entry.md) | 表单填写与提交保存 |
| D. 表格行操作 | [scenarios/d-grid.md](scenarios/d-grid.md) | 列表行增删改查 |
| E. 树形导航 | [scenarios/e-tree-navigation.md](scenarios/e-tree-navigation.md) | 树节点展开/折叠/选中 |
| F. 搜索/筛选 | [scenarios/f-search.md](scenarios/f-search.md) | 搜索命中与无结果处理 |
| G. 模态对话框 | [scenarios/g-modal-dialogs.md](scenarios/g-modal-dialogs.md) | 确认框/文件对话框 |
| H. 多步向导 | [scenarios/h-wizard.md](scenarios/h-wizard.md) | Wizard 步骤切换 |
| I. 右键菜单 | [scenarios/i-context-menu.md](scenarios/i-context-menu.md) | 右键弹出与菜单项选择 |
| J. DirectUI 弹窗 | [scenarios/j-directui.md](scenarios/j-directui.md) | IFileDialog/TTaskDialog/uia.xxx 命令 |
| K. 文本完整性 | [scenarios/k-text-completeness.md](scenarios/k-text-completeness.md) | OCR 检测截断/省略号/DPI |
| L. 布局对齐 | [scenarios/l-layout.md](scenarios/l-layout.md) | 静态 layout 审计后，运行时左对齐/间距/重叠/DPI 检测 |
| M. 控件定位策略 | [scenarios/m-control-targeting.md](scenarios/m-control-targeting.md) | 坐标校准/DPI 系数 |
| N. 等待策略 | [scenarios/n-wait-strategy.md](scenarios/n-wait-strategy.md) | 条件等待替代固定延时 |
| O. 控件重建安全 | [scenarios/o-control-rebuild.md](scenarios/o-control-rebuild.md) | Rescan 后控件重建等待 |
| 核对表 | [scenarios/checklist.md](scenarios/checklist.md) | 27 条黑盒测试质量门禁 |

入口文件：[testing/ui.md](../ui.md)（`## ⑧ 自动化 UI 交互测试`）

### 相关工具

```python
automate_delphi(action="auto", app_path="App.exe", script=[...])
automate_delphi(action="gui",  app_path="App.exe", script=[...])
automate_delphi(action="console", app_path="Tool.exe", input="Y\n", expect="Continue?")
automate_delphi(action="test", app_path="TestHost.exe", tests=[...])
```

> 详细命令列表、协议格式和示例见 `reference/script-schema.md`。
> RTTI 单元测试与 fixture 接入见 `reference/rtti-test-runner.md`。
> AI 脚本生成流程见 `reference/script-generation-workflow.md`。
> 修复循环见 `reference/repair-loop.md`。
> UI 测试场景模板见 `scenarios/` 目录下的 A-O 文件。
