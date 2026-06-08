# v2026.06.08 Release Notes

自上一版本 v2026.05.14 以来的累积变更。

---

## Added

- **`delphi_file` 新增 `batch_write` action**：一次传入多个 edit，内部按 `start_line` 升序排列，以备份文件为参照系，内存中累积偏移量后一次性写出。相邻 edit 区间重叠时自动检测并拒绝，防止行号映射错误。
  - 配套 18 个测试用例（基本功能 + 14 个边界测试）
- **`batch_write` AI 偏移量错误自动检测**：per-edit 检查 content 首行与被替换行是否相同，post-merge 扫描新增连续重复行，检测到时阻止写入并返回明确错误信息。配套 4 个测试用例。
  - `force` 参数（默认 false）：跳过检查强制写入
- **`search()` 自动重建缺失向量**：`experience_service.py` 的 `search()` 在模型已加载但语义搜索无结果时，自动触发 `rebuild_embeddings()` 补全缺失向量后重试，无需手动调用。
- **`run_verify` 异常日志嵌入 MCP 响应**：编译运行验证时检测到 `exception.log`，自动检测编码并读取内容直接嵌入 MCP 响应。
- **CODING_RULES.mdc 补充文件编码指南**：推荐含中文 Delphi 文件使用 `utf-8-sig`（UTF-8 with BOM）避免 W1057 警告。
- **`employee-input` 演示项目重建**：FireDAC SQLite 员工信息管理，UTF-8 BOM 编码消除 W1057 警告。

## Fixed

- **`ExperienceMemoryService.delete()` 方法定义缺失修复**：`delete()` 的 `def delete(...)` 方法头丢失，docstring 与方法体成为 `rebuild_embeddings()` `return` 后的死代码。已在 `prune_list()` 与 `rebuild_embeddings()` 之间补充完整的方法定义并移除死代码。
- **`embedding_service.py` `os.environ` 线程竞态修复**：`_worker` daemon 线程与主线程 `_restore_env()` 同时操作 `os.environ`，底层的 `os.putenv`/`os.unsetenv` 非线程安全。新增 `_env_lock = threading.Lock()` 保护全部 `os.environ` 写操作。
- **`test_is_dfm_file` 断言修正**：`.fmx` 与 `.dfm` 使用完全相同格式，函数本身已正确处理，仅修正测试断言 `is False` → `is True`。
- **`delphi_file` 部分写入行号偏差根因消除**：文档字符串修正为"0-indexed 左闭右开"，与 Python 切片行为一致。
- **部分写入返回偏移量信息**：每次 write/uses 操作后输出附带偏移量，AI Agent 可据此累加计算后续行号，无需重新读取文件。
- **`compilers.json` 路径自愈**：`config_manager.py` 自动检测路径并在 `src/config/` 与项目根 `config/` 之间回退。
- **18 处 `except Exception: pass` 添加 `logger.debug`**：原静默吞异常改为记录日志带调用栈，不改变控制流。涉及 10 个文件。
- **`delphi_file` read/write 行号改为 0-indexed 左闭右开**：`start_line` 默认值从 `1` 改为 `0`，与 Python `list[start:end]` 语义一致。
- **新增 17 个 file_tool 边界测试**：覆盖空区间、负值 clamp、超 EOF、单行替换、删除行、无效范围等。

## Changed

- **`search_knowledge` 597→37 行重构**：单函数拆为 37 行主函数 + 16 个模块级子函数，行为完全等价，pytest 727 passed。
- **`AGENTS.md` 新增「部分写入规则」章节**：文档化 0-indexed 语义、连续编辑的行号偏移算法、uses 偏移说明。
- **`tool_docs.py` `delphi_file` 文档补充**：write/read action 描述中添加 0-indexed 和偏移量说明。
- **`CODING_RULES.mdc` / `AGENTS.md` 经验文档更新**：保存流程与维护规则中补充 `rebuild_embedding` 自动补全说明。
- **`README.md` / `README_EN.md` 更新**：`experience` 工具描述补充 merge/prune/delete/rebuild_embedding；知识库存储表格新增经验知识库。

---

**版本标签**: `v2026.06.08`
**完整日志**: [CHANGELOG.md](CHANGELOG.md)
