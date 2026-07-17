<!-- @when: 使用 delphi_file 写入或修改 Delphi 文件时 -->
<!-- @chain: before=format.md, after=writing.md -->

## delphi_file 写入规则

**工具路由规则**：Delphi 文件必须用 `delphi_file` 读写/搜索/正则匹配+替换，不要用内置 `Read/Edit/Write/grep`。

**行号统一 1-indexed 左闭右闭。** write 统一使用 `edits=[...]`。

📋 示例: examples/delphi-file/write-edits.md — write(edits=[...]) 批量写入示例（新建/全量/部分/多段/预览）

### 脏标记保护（v2026.06.12+）

📋 示例: examples/delphi-file/dirty-flag.md — 脏标记保护示例（写入前后 read/preview 流程）
