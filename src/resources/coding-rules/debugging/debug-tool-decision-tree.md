<!-- @when: 不确定用什么工具排查当前问题类型时 -->
<!-- @chain: before=post-mortem.md, after=debug-log.md -->

### 8.11 调试工具选择决策树

| 问题类型 | ⭐ 首选 | ☆ 备选 |
|---------|---------|---------|
| **编译错误** | delphi_project(compile) / compile_file | delphi_file(read) / delphi_kb / experience |
| **运行时崩溃** | classify(8.13) → msgscan / StackTrace / delphi_rtti | guide user in IDE / experience |
| **逻辑错误** | delphi_file(read) / delphi_kb / LSP | automate_delphi(rget/capture) / experience |
| **环境问题** | check_environment / delphi_project(info) | git diff / experience |

**通用原则**：
- 先查经验库再动手：`experience(search, ...)` 可能 30 秒给出答案
- 先确认 API 再修代码：不确定 API 时用 `delphi_kb` 查定义
- 单文件验证优先：编译错误优先 `compile_file`
- 先隔离再分析：通过二分法缩小范围后深入分析
