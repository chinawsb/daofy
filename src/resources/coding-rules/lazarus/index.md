<!-- @title: Lazarus/Free Pascal 编码规则 -->
<!-- @purpose: Lazarus 项目开发全流程指南。调用 get_coding_rules(language="lazarus", section=...) 按需获取。 -->

## Lazarus/Free Pascal 编码规则
> 最后更新: 2026-07-17 | 版本: 1.0.0

按流程选择入口：

```
计划 → get_coding_rules(section="planning", language="lazarus")
流程 → get_coding_rules(section="workflow", language="lazarus")
编码 → get_coding_rules(section="writing", language="lazarus")
编译 → get_coding_rules(section="compile", language="lazarus")
审核 → get_coding_rules(section="review", language="lazarus")
清理 → get_coding_rules(section="cleanup", language="lazarus")
```

使用 `lazarus_compile` 工具编译 `.lpi`/`.lpr` 项目。
使用 `lazarus_project` 工具查询项目信息（单元列表/编译器选项）。

### 通用规则（自动合并）
- Agent 操作硬规则: `get_coding_rules(section="agent_rules")`
- 经验管理: `get_coding_rules(section="experience")`
- 调试指南: `get_coding_rules(section="human_collab")`
