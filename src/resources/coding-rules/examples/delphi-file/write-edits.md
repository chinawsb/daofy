# delphi_file write(edits=[...]) 批量写入示例

## 基础用法

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
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 5, "end_line": 10, "content": "新内容"}], dry_run=True)
```

## 行号偏移处理（v2026.07+）

write 返回末尾包含"未变"区域提示：
```
  [5, 10] → [5, 13] (+3)  替换了登录逻辑
  [20, 25] → [26, 28] (+3)  更新了错误处理
  未变: [1, 4] 不变, [14, 150] +3
```

**只用查表，不用计算**：
- 你的目标行号落在哪个 `[start, end]` 区间里 → 加上对应的偏移量
- 不在任何区间里的行 → 已被替换，不可再用
- 最保险的做法：write 后 read 刷新行号

## 推荐做法

| 场景 | 做法 |
|------|------|
| 1~2 处改 | `read` → `write(edits=[...])` |
| ≥3 处不连续 | `read` → 规划全部 edits → 一次 write |
| uses 变更 | 用 `uses` action，不要手动算行号 |
| 改完整方法 | `read` → 记行号 → write |
