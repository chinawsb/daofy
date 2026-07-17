<!-- @title: 编码规则导航（多语言） -->
<!-- @purpose: 按编程语言选择对应的编码规则入口。使用 get_coding_rules(section=..., language=...) 获取。 -->

## 编码规则导航
> 最后更新: 2026-07-17 | 版本: 1.14.0

选择编程语言获取对应的编码规则：

- **Delphi** → `get_coding_rules(language="delphi")` — Embarcadero Delphi 编码规范
- **Lazarus/Free Pascal** → `get_coding_rules(language="lazarus")` — Lazarus/FPC 编码规范

未指定 `language` 时默认返回 Delphi 规则（向后兼容）。

各语言入口包含：工作流总览 → 环境检查 → API 搜索 → 编码规范 → 格式 → 编译 → 清理 → 审核 → 经验保存

所有语言共享的通用规则（Agent 操作规范、调试、经验管理）自动合并到返回结果中。
