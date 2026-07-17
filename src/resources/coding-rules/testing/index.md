# 测试文档导航

自动化测试文档统一位于 `coding-rules/testing/`，按职责分为三层：

```
coding-rules/testing/
├── index.md                    ← 本文件（导航入口）
├── ui.md                       ← ⑧ UI 自动化测试（入口、命令分类、场景索引）
├── console.md                  ← ⑨ 控制台交互验证
└── automation/                 ← 自动化测试详细文档
    ├── index.md                ← 自动化文档总览
    ├── architecture.md         ← 架构方法论（感知→规划→执行→反馈）
    ├── scenarios/              ← 测试场景模板（A-O + 核对表）
    │   ├── base.md             ← 通信协议 + 测试质量红线
    │   ├── a-smoke.md ~ o-control-rebuild.md
    │   └── checklist.md        ← 27 条黑盒测试质量门禁
    └── reference/              ← 技术参考
        ├── script-schema.md    ← 脚本格式规范
        ├── script-generation-workflow.md ← 脚本生成工作流
        ├── capability-matrix.md ← 能力选型矩阵
        ├── workflow.md         ← 完整工作流
        └── ...                 ← 其他参考文档
```

## 入口选择

| 场景 | 入口文件 |
|------|---------|
| 首次了解自动化测试 | [ui.md](ui.md)（⑧ UI 自动化测试） |
| 编写测试脚本 | [automation/reference/script-schema.md](automation/reference/script-schema.md) |
| 选择测试策略 | [automation/reference/capability-matrix.md](automation/reference/capability-matrix.md) |
| 生成测试脚本 | [automation/reference/script-generation-workflow.md](automation/reference/script-generation-workflow.md) |
| 控制台程序测试 | [console.md](console.md)（⑨ 控制台交互验证） |
| 了解测试质量标准 | [automation/scenarios/base.md](automation/scenarios/base.md) § 测试质量红线 |
