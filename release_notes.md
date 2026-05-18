## v2026.05.14 (2026-05-14)

### 新增

- **`get_coding_rules` 支持 section 参数**：按章节获取编码规范（workflow/writing/review/safety 等 20+ 命名章节），默认返回索引，Agent 按需拉取节省 token
- **CODING_RULES.mdc 补充编码规范**：泛型/运算符重载/异步/代码组织/版本兼容/日志/数据转换/测试命名/规则模板
- **工作流嵌入审核步骤**：①-⑥ → ①-⑦，编译通过后强制代码审核
- **pasfmt uses 压缩后处理**：新增 `uses_style` 参数（compact/pasfmt_default），默认合并 uses 为单行
- **类内 type 段扫描**：识别 `private type` / `public type` 段，捕获 `PItem = ^TItem` 等类型别名并补全 parent 链接
- **字符串字面量索引**（KS 实体）：搜索错误消息直击代码行
- **合并三方库 KB + DF 中文搜索**

### 测试

- **新增 3 个测试文件**：`test_coding_rules.py`(20例/90%覆盖)、`test_process_manager.py`(16例/92%覆盖)、`test_environment.py`(12例/95%覆盖)
- **总测试数 144 → 186**，零弃用警告

### 修复

- `print()` 泄漏修复（install_package/scan_generic_documents/dynamic_worker_optimizer）
- 静默异常处理改进（except:pass -> logger.warning）
- 消除 `# type: ignore` 和 `== False` 风格问题
- 死代码清理（移除未使用的 ProgressCallback 类）
- 测试弃用警告清理（40 条 PytestReturnNotNoneWarning, 9 处 Element truth）
- 字符串提取兼容 // 在字符串内和 #
- 项目 KB 构建改独立子进程
- 日志标签修正 多线程->多进程

### 重构

- 移除 JSON 元数据，全部集中 SQLite metadata 表
- 合并三方库 KB 修复多进程哈希误判
