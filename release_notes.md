# v2026.06.08 Release Notes

## Fixed

- **`ExperienceMemoryService.delete()` 方法定义缺失修复**：`experience_service.py` 中 `delete()` 的 `def delete(...)` 方法头丢失，docstring 与方法体成为 `rebuild_embeddings()` `return` 后的死代码。`merge()` 中 `self.delete(did)` 调用会抛出 `AttributeError`。已在 `prune_list()` 与 `rebuild_embeddings()` 之间补充完整的方法定义，并移除死代码。

- **`embedding_service.py` `os.environ` 线程竞态修复**：`_worker` daemon 线程与主线程 `_restore_env()` 同时操作 `os.environ`，底层的 `os.putenv`/`os.unsetenv` 非线程安全。新增 `_env_lock = threading.Lock()` 保护全部 `os.environ` 写操作。

- **`test_is_dfm_file` 断言修正**：`tests/test_file_tool.py` 中断言 `_is_dfm_file("test.fmx") is False` 写反，`.fmx` 与 `.dfm` 使用完全相同格式，函数本身已正确处理，仅修正测试断言。

## Added

- **`search()` 自动重建缺失向量**：`experience_service.py` 的 `search()` 在模型已加载但语义搜索无结果时，自动触发 `rebuild_embeddings()` 补全缺失向量后重试，无需用户手动调用 `rebuild_embedding` action。

## Changed

- **`CODING_RULES.mdc` / `AGENTS.md` 经验文档更新**：保存流程与维护规则中补充 `rebuild_embedding` 自动补全说明。
- **`README.md` / `README_EN.md` 工具描述更新**：`experience` 工具描述补充 merge、prune、delete、rebuild_embedding 完整功能。
