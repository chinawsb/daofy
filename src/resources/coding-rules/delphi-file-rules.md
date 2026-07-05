<!-- @when: 使用 delphi_file 写入或修改 Delphi 文件时 -->
<!-- @chain: before=format.md, after=writing.md -->

## delphi_file 写入规则

**工具路由规则**：看到 `.pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx` 路径时，读取和修改都必须使用 MCP `delphi_file`。不要用 Agent 内置 `Read/Edit/Write`、`apply_patch`、shell 重定向或 Python 直接读写这些文件。

**行号统一 1-indexed 左闭右闭。** write 统一使用 `edits=[...]`。

```python
# 新建文件
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 1, "content": "unit Unit1;\n\ninterface\n\nimplementation\n\nend.\n"}])
# 全量替换
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 1, "content": "unit ..."}])
# 部分替换
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 5, "end_line": 10, "content": "新内容"}])
# 多段替换（顺序不限，自动排序）
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 10, "end_line": 12, "content": "..."}, {"start_line": 5, "end_line": 7, "content": "..."}])
# 预览模式
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 5, "end_line": 10, "content": "新内容"}], preview=True)
```

### 脏标记保护（v2026.06.12+）

**write/format/uses 后文件标记为脏**，再次 write 前必须先 read（清脏标记）或提供 `old_content` 校验命中范围。

**继续写入方式**：
- 调用 `read`（自动清脏标记）
- 每个 edit 提供非空 `old_content`
- `write(preview=True)` 仅预览（不清脏标记）
- `write(allow_dirty=True)`（风险自负）

**行号偏移处理（v2026.07+）**：

```
write 返回末尾包含"未变"区域提示：
  [5, 10] → [5, 13] (+3)  替换了登录逻辑
  [20, 25] → [26, 28] (+3)  更新了错误处理
  未变: [1, 4] 不变, [14, 150] +3
```

**只用查表，不用计算**：
- 你的目标行号落在哪个 `[start, end]` 区间里 → 加上对应的偏移量
- 不在任何区间里的行 → 已被替换，不可再用
- 最保险的做法：write 后 read 刷新行号

### 紧凑输出格式（v2026.06.12+）

- **read**: `# encoding: utf-8, 1-indexed [1, 200]`
- **write**: `[5, 10] → [5, 13] edit #0` + `- / +` diff，末尾追加 `未变:` 行
- **preview**: 同上但标注 `preview: true`（不输出 `未变:` 行）
- **uses**: `wrote: added System.SysUtils in interface, [2, 3] → [2, 4]`

### 推荐做法
| 场景 | 做法 |
|------|------|
| 1~2 处改 | `read` → `write(edits=[...])` |
| ≥3 处不连续 | `read` → 规划全部 edits → 一次 write |
| uses 变更 | 用 `uses` action，不要手动算行号 |
| 改完整方法 | `read` → 记行号 → write |
