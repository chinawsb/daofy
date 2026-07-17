<!-- @when: 使用 delphi_file 写入或修改 Delphi 文件时 -->
<!-- @chain: before=format.md, after=writing.md -->

## delphi_file 写入规则

**工具路由规则**：Delphi 文件必须用 `delphi_file` 读写/搜索/正则匹配+替换，不要用内置 `Read/Edit/Write/grep`。

**行号统一 1-indexed 左闭右闭。** write 统一使用 `edits=[...]`。

### DFM 中文内容（重要）

DFM 文件中的中文内容（Caption、Text、Hint 等属性值）**直接写原文，不需要转义**。

```python
# ✅ 正确：直接写中文
delphi_file(action="write", file_path="MainForm.dfm", edits=[
    {"start_line": 5, "end_line": 5, "new_text": '    Caption = #20013#25991#26631#39064'}
])

# ✅ 更简单：直接用中文字符串（delphi_file 自动处理编码）
delphi_file(action="write", file_path="MainForm.dfm", edits=[
    {"start_line": 5, "end_line": 5, "new_text": '    Caption = "中文标题"'}
])

# ❌ 错误：不要手动转义 Unicode
delphi_file(action="write", file_path="MainForm.dfm", edits=[
    {"start_line": 5, "end_line": 5, "new_text": '    Caption = \u4e2d\u6587\u6807\u9898'}
])
```

**原理**：`delphi_file` 读写时自动处理编码（GBK/UTF-8/BOM），中文内容保持原文写入，工具内部处理编码转换。

📋 示例: examples/delphi-file/write-edits.md — write(edits=[...]) 批量写入示例（新建/全量/部分/多段/预览）

### 脏标记保护（v2026.06.12+）

📋 示例: examples/delphi-file/dirty-flag.md — 脏标记保护示例（写入前后 read/preview 流程）
