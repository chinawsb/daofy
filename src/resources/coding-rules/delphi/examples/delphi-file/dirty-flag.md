# 脏标记保护示例（v2026.06.12+）

## 问题

write/format/uses 后文件标记为**脏**，再次 write 前必须先 read（清脏标记）或提供 `old_content` 校验命中范围。

## 继续写入方式

- 调用 `read`（自动清脏标记）
- 每个 edit 提供非空 `old_content`
- `write(dry_run=True)` 仅预览（不清脏标记）
- `write(allow_dirty=True)`（风险自负）

## 紧凑输出格式

- **read**: `# encoding: utf-8, 1-indexed [1, 200]`
- **write**: `[5, 10] → [5, 13] edit #0` + `- / +` diff，末尾追加 `未变:` 行
- **dry_run**: 同上但标注 `dry_run: true`（不输出 `未变:` 行）
- **uses**: `wrote: added System.SysUtils in interface, [2, 3] → [2, 4]`

## 正确流程

```
1. read → 获取当前行号 + 清脏标记
2. write(edits=[...]) → 写入变更
3. 如果需要再次修改 → 必须先 read 再 write
```

## 错误流程

```
1. write(edits=[...]) → 文件变脏
2. write(edits=[...]) → ❌ 脏标记保护，拒绝写入
```
