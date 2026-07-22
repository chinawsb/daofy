<!-- @when: 了解自动化测试架构全貌，需从顶层入口导航到各子模块时 -->
<!-- @chain: after=index.md, before=reference/*.md -->

# 自动化测试架构总览

MCP resource URI: `delphi://automation/architecture`。

```
大模型（脑）:  感知 → 规划 → 执行指令 → 分析反馈 → 调整策略
                   ↕          ↕
MCP 服务器（手脚）:  提供工具感知 UI 状态 + 执行 UI 操作
```

大模型负责**决策和规划**，MCP 工具负责**感知和执行**。二者形成闭环。

## 架构模块

| 模块 | URI | 说明 |
|------|-----|------|
| RTTI vs OCR 决策矩阵 | `delphi://automation/rtti-ocr-matrix` | 功能性验证 vs 视觉完整性验证的场景对照表 |
| 规划方法论 | `delphi://automation/planning-methodology` | 分层降级策略、动作序列规范、失败处理模式 |
| 经验驱动优化闭环 | `delphi://automation/experience-loop` | 经验检索/保存/融合机制，让 AI 从历史中学习 |
| 代码感知测试 | `delphi://automation/code-aware-testing` | 从 DFM/PAS 源码推导测试路径和代码派生断言 |
| RTTI 单元测试 | `delphi://automation/rtti-test-runner` | 直接测试类方法、fixture 生命周期、逐例超时与稳定统计 |

## 相关工作流

| 文档 | URI |
|------|-----|
| 自动化测试完整工作流 | `delphi://automation/reference/workflow` |
| 脚本生成工作流 | `delphi://automation/script-generation-workflow` |
| 能力选型矩阵 | `delphi://automation/capability-matrix` |
| 脚本格式规范 + 断言 + 缓存 | `delphi://automation/script-schema` |
| RTTI 单元测试运行器 | `delphi://automation/rtti-test-runner` |

## 相关参考

| 文档 | URI |
|------|-----|
| UIA 命令参考 | `delphi://automation/uia-commands` |
| 提示词模板 | `delphi://automation/prompts` |
| 报告格式 | `delphi://automation/report-schema` |
| 失败修复循环 | `delphi://automation/repair-loop` |
| 项目接入指南 | `delphi://automation/inline-unit` |
