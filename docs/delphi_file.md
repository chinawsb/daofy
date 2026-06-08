# Delphi File — Delphi 文件专用操作

> 版本：v1.0 | 最后更新：2026-06-08

---

## 目录

1. [概述](#1-概述)
2. [Action 速查](#2-action-速查)
3. [Read — 读取文件](#3-read--读取文件)
4. [Write — 写入文件](#4-write--写入文件)
5. [Batch Write — 批量写入](#5-batch-write--批量写入)
6. [Format — 格式化](#6-format--格式化)
7. [Backup — 备份管理](#7-backup--备份管理)
8. [Uses — 单元引用管理](#8-uses--单元引用管理)
9. [核心概念](#9-核心概念)
10. [技术架构](#10-技术架构)
11. [故障排除](#11-故障排除)

---

## 1. 概述

`delphi_file` 是 Daofy 中专用于操作 Delphi 源文件的工具，支持 `.pas`/`.dfm`/`.dproj`/`.dpk`/`.fmx`/`.inc` 格式。提供读、写、批量写入、格式化、备份管理和单元引用（uses）增删功能。

**核心特性**：
- 自动编码检测（UTF-8 / GBK / UTF-16）
- 自动备份到 `__history` 目录（与 Delphi IDE 兼容）
- DFM 二进制 ↔ 文本透明转换
- 按类名/函数名搜索定位代码

### 硬约束

> ❌ 严禁使用原生 `read`/`write`/`edit`/`bash echo` 直接修改 `.pas`/`.dfm` 文件（会绕过备份 + 编码检测）

### 标准工作流

```
get_coding_rules → delphi_file(read) → delphi_file(write) → delphi_file(format) → project(compile)
```

---

## 2. Action 速查

| Action | 用途 |
|--------|------|
| `read` | 读取文件，支持分段、按类名/函数名定位 |
| `write` | 写入文件，支持全文替换或部分写入 |
| `batch_write` | 🧪 批量写入多处（实验性） |
| `format` | 使用 pasfmt 格式化代码 |
| `backup` | 备份管理（创建/列表/恢复） |
| `uses` | 增删 uses 子句中的单元 |

---

## 3. Read — 读取文件

### 3.1 读取模式

| search_type | 说明 | 参数 |
|------------|------|------|
| `path`（默认） | 按文件路径分段读取 | `start_line`, `end_line`, `limit` |
| `class` | 按类名/接口名/枚举名定位 | `type_name` / `class_name` |
| `function` | 按函数/过程名定位 | `function_name` |
| `record` | 按 record 类型名定位 | `record_name` |

### 3.2 按路径读取

```python
# 读前 500 行
delphi_file(action="read", file_path="Unit1.pas")

# 分段读取（0-indexed [100, 300) 行）
delphi_file(action="read", file_path="Unit1.pas", start_line=100, limit=200)

# 显示行号
delphi_file(action="read", file_path="Unit1.pas", show_line_numbers=True)
```

### 3.3 按类名/函数名定位

```python
# 搜索类定义
delphi_file(action="read", search_type="class", type_name="TForm1")

# 搜索函数
delphi_file(action="read", search_type="function", function_name="Create")

# 搜索项目代码中的类
delphi_file(action="read", search_type="class",
    type_name="TfrmMain", search_in="project", project_path="Project.dproj")
```

### 3.4 输出格式

`read` 输出紧凑格式示例：
```
# encoding: utf-8, 0-based [0, 200) (truncated)
```

- `encoding:` 文件编码
- `0-based [s, e)` 本次返回的 0-indexed 左闭右开区间
- `(truncated)` 文件被截断时标记

### 3.5 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `start_line` | 0 | 起始行号（0-indexed） |
| `end_line` | — | 结束行号（不包含，左闭右开），不传则到文件末尾 |
| `limit` | 500 | 最大返回行数（上限 1000） |
| `show_line_numbers` | false | 是否显示行号前缀（0-based） |
| `search_in` | all | 搜索范围：all/delphi/thirdparty |
| `project_path` | — | 项目路径（搜索项目代码时使用） |

---

## 4. Write — 写入文件

### 4.1 全文替换

```python
delphi_file(action="write", file_path="Unit1.pas", content="unit Unit1;\n...")
```

`content` 必须包含完整的文件内容。

### 4.2 部分写入

```python
# 替换第 6~10 行（0-indexed [5, 10)）
delphi_file(action="write",
    file_path="src/Unit1.pas",
    content="替换后的内容",
    start_line=5,
    end_line=10)
```

### 4.3 行号规则（⚠️ 易错）

`start_line`/`end_line` 是 **0-indexed 左闭右开** 区间：

| 参数 | 含义 |
|------|------|
| `start_line=0` | 从文件第 **1** 行开始 |
| `start_line=5, end_line=10` | 替换第 **6~10** 行（`[5, 10)`） |
| `start_line=4, end_line=5` | 只替换第 **5** 行（`[4, 5)`） |

> **为什么不是 1-indexed？** 内部用 Python 切片 `lines[s:e]` 处理，Python 切片是 0-indexed。

### 4.4 连续编辑的偏移量计算

每次 `write` 返回偏移量信息：

```
wrote: Unit1.pas, 0-based [5, 10) → [5, 13), encoding: utf-8, backup: __history\Unit1.pas.~1~
```

`[5, 10) → [5, 13)` 表示：原 5-10 行被替换为 5-13 行，**偏移量 = 13 - 10 = +3**。

后续编辑需累加偏移：

```
设某次 write 返回: s=start_line, e=end_line, offset=净偏移
则后续用原行号 L 计算新行号:
  L < s  → 新行号 = L           (在编辑区域前，不变)
  L ≥ e  → 新行号 = L + offset  (在编辑区域后，累加偏移)
  s ≤ L < e → 该行已被替换/删除，不能再用作后续编辑目标
```

有多次 write 时，每次独立计算、依次累加。如果累计后不确定，重新 `read`。

### 4.5 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `content` | — | 写入内容（全文或部分替换） |
| `start_line` | — | 起始行号（0-indexed，部分写入） |
| `end_line` | — | 结束行号（不包含，左闭右开） |
| `encoding` | auto | 写入编码：auto/utf-8/gbk/utf-16 |
| `auto_format` | false | 写入后自动调用 pasfmt 格式化 |
| `backup` | true | 写入前自动备份到 `__history` |

---

## 5. Batch Write — 批量写入

> 🧪 **实验性功能**：适合单次 ≥3 处不连续修改的场景。偏移量计算复杂，遇到问题请用多次 `write` 替代。

### 5.1 基本用法

```python
delphi_file(action="batch_write",
    file_path="Unit1.pas",
    edits=[
        {"start_line": 5, "end_line": 10, "content": "新代码段1"},
        {"start_line": 20, "end_line": 22, "content": "新代码段2"},
    ])
```

### 5.2 edits 参数结构

| 字段 | 必需 | 说明 |
|------|------|------|
| `start_line` | ✅ | 起始行号（0-indexed inclusive） |
| `end_line` | ❌ | 结束行号（0-indexed exclusive），不传则到文件末尾 |
| `content` | ✅ | 替换内容（空串=删除行） |
| `description` | ❌ | 文字描述，仅用于返回消息标记 |

### 5.3 使用建议

| 场景 | 推荐 |
|------|------|
| 1~2 处不连续修改 | `read` → `write`（更稳） |
| 3+ 处不连续修改 | `read` → `batch_write` |
| 涉及 uses 变更 | `uses` action |
| 改完整方法 | `write` + 完整 content |

### 5.4 注意事项

- edits 顺序不限，内部自动排序
- 相邻 edit 区间不能重叠（自动检测并拒绝）
- content 应包含替换后的**完整**内容，不要包含已存在的行，否则可能重复
- `force=true` 可跳过 AI 偏移量检查

---

## 6. Format — 格式化

使用 **pasfmt** 工具格式化 Delphi 代码。

```python
# 格式化文件
delphi_file(action="format", file_path="src/Unit1.pas")

# 格式化代码段
delphi_file(action="format", mode="code",
    code="procedure Test; begin end;")

# 仅检查格式，不修改
delphi_file(action="format", file_path="Unit1.pas", dry_run=True)

# 控制 uses 子句风格
delphi_file(action="format",
    file_path="Unit1.pas",
    uses_style="compact")  # compact=合并为一行 / pasfmt_default=每行一个
```

**参数说明**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `mode` | file | file=格式化文件, code=格式化代码段, check=仅检查 |
| `code` | — | 待格式化的代码文本（mode=code 时使用） |
| `config_path` | — | pasfmt 配置文件路径（高级用法） |
| `uses_style` | — | uses 子句风格：compact/pasfmt_default |
| `dry_run` | false | true=仅检查不修改 |

---

## 7. Backup — 备份管理

自动备份到文件所在目录的 `__history` 子目录，命名格式 `文件名.~版本号~`（与 Delphi IDE 兼容）。二进制 DFM 文件的备份是原始二进制版本，恢复时 100% 还原。

```python
# 手动创建备份
delphi_file(action="backup", file_path="src/Unit1.pas")

# 列出所有备份版本
delphi_file(action="backup", backup_action="list", file_path="src/Unit1.pas")

# 恢复指定版本
delphi_file(action="backup", backup_action="restore", file_path="src/Unit1.pas", version=3)

# 恢复最新版本
delphi_file(action="backup", backup_action="restore", file_path="src/Unit1.pas")
```

> `action="write"` 默认 `backup=True`，写入前自动备份，通常情况下无需手动调用 `backup`。

---

## 8. Uses — 单元引用管理

增删 `uses` 子句中的单元，自动处理行号和偏移量。

```python
# 添加单元到 interface uses
delphi_file(action="uses", uses_action="add",
    unit_name="System.SysUtils", file_path="Unit1.pas")

# 添加到 implementation uses
delphi_file(action="uses", uses_action="add",
    unit_name="Vcl.Dialogs", file_path="Unit1.pas",
    uses_section="implementation")

# 删除单元
delphi_file(action="uses", uses_action="remove",
    unit_name="System.SysUtils", file_path="Unit1.pas")
```

**参数说明**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `uses_action` | — | add=添加, remove=删除 |
| `unit_name` | — | 单元名，如 Vcl.Dialogs、System.SysUtils |
| `uses_section` | interface | interface/implementation |

---

## 9. 核心概念

### 9.1 编码处理

| 编码 | 检测方式 | 说明 |
|------|---------|------|
| UTF-8 | 无 BOM 时尝试 UTF-8 解码 | 含中文时推荐 `utf-8-sig`（BOM） |
| UTF-16 LE/BE | BOM 检测 | 保留 BOM 不删除 |
| GBK | UTF-8 失败后自动回退 | 中文 Windows 上常见 |

**新建文件含中文**：推荐用 `encoding="utf-8-sig"`（UTF-8 with BOM），避免编译器将中文字符串视为 AnsiString 触发 `W1057` 警告。

### 9.2 DFM 二进制 ↔ 文本转换

- `read` 时自动检测 DFM 编码，二进制 DFM 自动转换为文本
- `write` 时透明转换回二进制（如需）
- 备份始终为原始格式，恢复时 100% 还原

### 9.3 紧凑输出格式

```
# 读文件
encoding: utf-8, 0-based [0, 200) (truncated)

# 写文件（全文替换）
wrote: Unit1.pas, encoding: utf-8, backup: __history\Unit1.pas.~1~

# 写文件（部分替换）
wrote: Unit1.pas, 0-based [5, 10) → [5, 13), encoding: utf-8, backup: __history\Unit1.pas.~1~

# batch_write
batch_wrote: 2 edits, Unit1.pas, encoding: utf-8, backup: __history\Unit1.pas.~1~
  [5, 10) → [5, 13)  edit #0
    - L5_old
    + L5_new
```

---

## 10. 技术架构

```
AI Agent
    │
    ▼
delphi_file(action="read"|"write"|"format"|...)
    │
    ▼
┌─────────────────────────────────────────────┐
│           src/tools/file_tool.py              │
│  action 分派 + 编码检测 + 备份 + DFM 转换     │
└──────┬──────────┬──────────┬─────────────────┘
       │          │          │
       ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│  编码    │ │  备份    │ │  DFM     │
│  检测    │ │  管理    │ │  转换    │
├──────────┤ ├──────────┤ ├──────────┤
│· UTF-8   │ │· __history│ │· 二进制→│
│· UTF-16  │ │· 版本号   │ │  文本   │
│· GBK     │ │· 恢复    │ │· 文本→  │
│· BOM保留 │ │          │ │  二进制 │
└──────────┘ └──────────┘ └──────────┘
       │
       ▼
┌──────────────────────┐
│   pasfmt (格式化器)   │
│  · 缩进/空格/换行     │
│  · uses 风格控制     │
│  · 泛型/运算符格式   │
└──────────────────────┘
```

---

## 11. 故障排除

| 现象 | 原因 | 解决 |
|------|------|------|
| 写入后中文乱码 | 编码不对 | 指定 `encoding="gbk"` 或 `encoding="utf-8-sig"` |
| 部分替换到错误位置 | 行号偏移未累加 | `read` 文件重新确认行号 |
| `batch_write` 提示重复行 | AI 偏移量误算 | 传 `force=true` 跳过检查 |
| `format` 提示 pasfmt 未安装 | 格式化工具缺失 | `check_environment(action="install")` 安装 |
| 备份恢复后文件不对 | 选错版本号 | `backup_action="list"` 列出所有版本确认 |
| 读取 DFM 报错 | 二进制 DFM 损坏 | 用 `delphi_file` 自动转换 |
