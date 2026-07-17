<!-- @when: 开始调试任何问题前，需记录调试日志 -->
<!-- @chain: before=debug-tool-decision-tree.md, after=binary-search-isolation.md -->

### 8.10 调试状态日志

AI Agent **必须维护结构化调试日志**，显式追踪已尝试方案和结果，防止同质方案重复。

📋 示例: examples/debugging/debug-log-template.md — 调试日志模板（问题描述/已尝试方案/当前范围/下一步计划）
