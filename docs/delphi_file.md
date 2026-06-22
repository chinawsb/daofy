# Delphi File — Delphi 文件专用操作

> 最后更新：2026-06-18

`delphi_file` 是 Daofy 中用于读写 Delphi 源文件和表单文件的专用工具。支持 `.pas`、`.dpr`、`.dpk`、`.dfm`、`.fmx`、`.inc`、`.dproj`，自动处理编码检测、`__history` 备份、DFM/FMX 二进制转换和同文件读写互斥。

## Action 速查

| Action | 用途 |
|--------|------|
| `read` | 按路径读取，或按类名/函数名/record 定位后读取 |
| `replace` | ⭐ 推荐替换，按行范围替换（需 `old_content` 校验） |
| `insert` | ⭐ 推荐插入，按锚点行插入（需 `old_content` 校验） |
| `delete` | ⭐ 推荐删除，按行范围删除（需 `old_content` 校验） |
| `write` | 兼容写入接口，使用 `edits=[...]`（新调用优先用 `replace`/`insert`/`delete`） |
| `format` | 使用 pasfmt 格式化 |
| `backup` | 创建、列出、恢复 `__history` 备份 |
| `uses` | 增删 uses 子句单元 |

## 行号规则

所有 `read`/`write`/`uses` 的行号参数和输出均为 **1-indexed inclusive**。

| 示例 | 含义 |
|------|------|
| `start_line=1` | 从第 1 行开始 |
| `start_line=5, end_line=10` | 第 5 到第 10 行，包含两端 |
| `write` 不传 `end_line` | 从 `start_line` 替换到文件末尾 |

## Read

```python
delphi_file(action="read", file_path="Unit1.pas")
delphi_file(action="read", file_path="Unit1.pas", start_line=5, end_line=15)
delphi_file(action="read", file_path="Unit1.pas", show_line_numbers=True)
```

按类型搜索：

```python
delphi_file(action="read", search_type="class", type_name="TButton")
delphi_file(action="read", search_type="function", function_name="Create")
delphi_file(action="read", search_type="record", record_name="TPoint")
```

项目源码搜索需要项目路径：

```python
delphi_file(
    action="read",
    search_type="class",
    type_name="TMainForm",
    search_in="project",
    project_path="Project.dproj")
```

`search_in` 可选值：`all`、`delphi`、`project`、`thirdparty`。`project` 必须提供 `project_path`。

读取输出首行示例：

```text
# encoding: utf-8, 1-indexed [5, 15]
```

如果后续还要修改同一区间，可把读取到的原文放进 `edit.old_content`。写入前工具会用“行号 + 旧内容”一起校验命中的范围。

## Structured Write

推荐新调用使用 `replace` / `insert` / `delete`，都使用 `edits` 数组。

替换行范围：

```python
delphi_file(
    action="replace",
    file_path="Unit1.pas",
    edits=[{
        "start_line": 5,
        "end_line": 10,
        "old_content": "  OldCall;\n",
        "content": "  NewCall;\n"
    }])
```

按锚点插入，不需要在 `content` 中复制锚点行：

```python
delphi_file(
    action="insert",
    file_path="Unit1.pas",
    edits=[{
        "start_line": 10,
        "position": "before",
        "old_content": "  OldCall;\n",
        "content": "  NewCall;\n"
    }])
```

删除行范围：

```python
delphi_file(
    action="delete",
    file_path="Unit1.pas",
    edits=[{
        "start_line": 10,
        "end_line": 12,
        "old_content": "  OldCall;\n  OtherCall;\n"
    }])
```

`replace` / `insert` / `delete` 对现有文件要求每个 edit 都提供非空 `old_content`。`insert` 的 `old_content` 是锚点行原文，`position` 可为 `before` 或 `after`。

## Write

`write` 是兼容写入入口。新调用优先使用 `replace` / `insert` / `delete`。不要再使用旧的顶层 `content/start_line/end_line` 参数。

全文替换：

```python
delphi_file(
    action="write",
    file_path="Unit1.pas",
    edits=[{"start_line": 1, "content": "unit Unit1;\n\ninterface\n\nimplementation\n\nend.\n"}])
```

部分替换：

```python
delphi_file(
    action="write",
    file_path="Unit1.pas",
    edits=[{"start_line": 5, "end_line": 10, "content": "  // new code\n"}])
```

多处修改应合并到一次 `write`：

```python
delphi_file(
    action="write",
    file_path="Unit1.pas",
    edits=[
        {"start_line": 5, "end_line": 7, "content": "  // first block\n"},
        {"start_line": 18, "end_line": 21, "content": "  // second block\n"},
    ])
```

预览不写盘、不备份，也不清除脏标记：

```python
delphi_file(
    action="write",
    file_path="Unit1.pas",
    edits=[{"start_line": 5, "end_line": 10, "content": "  // new code\n"}],
    preview=True)
```

常用参数：

| 参数 | 默认 | 说明 |
|------|------|------|
| `backup` | `True` | 写入前备份到 `__history` |
| `encoding` | `auto` | 保持原编码；可显式指定 `utf-8`/`gbk`/`utf-16` |
| `auto_format` | `False` | 写入后自动 pasfmt |
| `preview` | `False` | 仅计算 diff，不写盘，不清除脏标记 |
| `force` | `False` | 跳过连续重复行检测 |
| `old_content` | 空 | 写在每个 edit 内，表示将被替换区间的非空旧内容 |
| `allow_dirty` | `False` | 跳过脏标记检查，需确认行号准确 |
| `project_path` | 空 | 限制 `file_path` 必须位于项目目录内 |

带 `old_content` 的后续写入：

```python
delphi_file(
    action="write",
    file_path="Unit1.pas",
    edits=[{
        "start_line": 5,
        "end_line": 10,
        "old_content": "  OldCall;\n",
        "content": "  // new code\n"
    }])
```

当每个 edit 都提供非空 `old_content`，且都与当前命中的行范围匹配时，即使文件处于脏标记状态，工具也允许继续写入。不匹配时返回冲突范围附近的小片段且不写盘。比较时会移除换行和字符串外空白，但保留字符串字面量内部空白，因此格式化造成的缩进差异不会误阻断，字符串语义变化仍会阻断。

替换输出示例：

```text
wrote: 1 edits, Unit1.pas, encoding: utf-8, backup: __history\Unit1.pas.~1~

  [5, 10] -> [5, 8] (offset: -2)  edit #0
```

删除输出示例：

```text
wrote: 1 edits, Unit1.pas, encoding: utf-8, backup: __history\Unit1.pas.~1~

  [5, 10] -> deleted before line 5 (offset: -6)  edit #0
```

## 脏标记

`write`、`format`、`uses` 成功后会把文件标记为脏。再次写入同一文件前需要：

- 先 `delphi_file(action="read", file_path=...)` 重新获取行号；
- 或在每个 edit 内提供非空 `old_content`，由工具校验行号命中的旧内容；
- 或使用 `preview=True` 预览 diff 后重新 `read` / 携带 `old_content`；
- 或在确认行号无误时设置 `allow_dirty=True`。

## Format

```python
delphi_file(action="format", file_path="Unit1.pas")
delphi_file(action="format", mode="check", file_path="Unit1.pas")
delphi_file(action="format", mode="code", code="procedure Test; begin end;")
```

## Backup

```python
delphi_file(action="backup", file_path="Unit1.pas")
delphi_file(action="backup", backup_action="list", file_path="Unit1.pas")
delphi_file(action="backup", backup_action="restore", file_path="Unit1.pas", version=3)
```

## Uses

```python
delphi_file(
    action="uses",
    file_path="Unit1.pas",
    uses_action="add",
    unit_name="System.SysUtils",
    uses_section="interface")
```

`uses` 支持 `add` / `remove`，成功后同样会标记文件脏。

## 故障排除

| 现象 | 处理 |
|------|------|
| `请提供 edits 参数` | 使用 `write(edits=[...])`，不要传旧的顶层 `content` |
| `上次写入后行号可能已变化` | 先重新 `read`，或为每个 edit 提供 `old_content`，确认无误才 `allow_dirty=True` |
| `search_in='project' 需要提供 project_path` | 传入 `.dproj/.dpr/.dpk` 路径 |
| `路径不在项目目录内` | `project_path` 启用了路径限制，改用项目目录内文件 |
| 二进制 DFM 转换失败 | 检查 Delphi 编译器/dcc32 是否可用 |
