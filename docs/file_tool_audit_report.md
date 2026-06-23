# file_tool 工具接口审计报告

**项目**: Daofy for Delphi
**审计范围**: `src/tools/file_tool.py`（1494 行）及 `src/server.py` 中的调用链
**审计日期**: 2026-06-18
**审计方法**: 逐行代码审查 + 跨文件调用追踪

---

## 前置说明

`file_tool` 在 MCP 中注册为 `delphi_file`（旧名 `file_tool` 保留为别名）。
以下统称 `file_tool`，指 `src/tools/file_tool.py`。

---

## 审计结论（一句话）

**代码质量良好，没有安全漏洞，接口设计合理。发现一处轻微 bug 和三处代码质量建议。**

---

## 发现清单

| # | 类型 | 严重度 | 说明 |
|---|------|--------|------|
| 1 | Bug | 轻微 | `handle_read` 提前清除脏标记 |
| 2 | 质量 | 建议 | `_release_*_lock` 中有冗余的 TOCTOU 模式 |
| 3 | 质量 | 建议 | 重叠检测变量名 `s0_1`/`e0_1` 误导 |
| 4 | 质量 | 建议 | `_validate_path` 的 `project_path` 参数未使用 |

---

## 详细分析

### 1. [Bug/轻微] `handle_read` 提前清除脏标记

**位置**: `file_tool.py:327-333`

```python
# 读取清除脏标记：AI 重新读到了最新行号
_clear_dirty(file_path)                           # ← 先清除

# 获取读取许可（多读单写：多个读取可并发，写入时不可读）
read_lock_err = _acquire_read_lock(file_path)     # ← 后获取锁
if read_lock_err:
    return _wrap_error(read_lock_err)             # 锁失败，但脏标记已清除
```

**问题**: 如果读锁获取失败（文件正在被写入），脏标记已被提前清除。下次对该文件调用 `write` 时，脏检查（`_check_dirty`）会通过（脏标记不存在），但 AI 实际上并未成功读取文件的最新行号。

**触发条件**: 仅发生在多线程并发场景——一个线程正在写此文件，另一个线程同时调用 `read`。单线程（MCP 串行调用）不会触发。

**建议修复**:
```python
# 先获取读锁
read_lock_err = _acquire_read_lock(file_path)
if read_lock_err:
    return _wrap_error(read_lock_err)

# 确认可以读取后，再清除脏标记
_clear_dirty(file_path)
```

---

### 2. [建议] `_release_read_lock` / `_release_write_lock` 的冗余模式

**位置**: `file_tool.py:421-466`

```python
def _release_read_lock(file_path: str) -> None:
    normalized = os.path.abspath(file_path)
    with _file_rw_dict_lock:                          # 查 entry
        entry = _file_rw_locks.get(normalized)
        if entry is None:
            return
    with entry["lock"]:                               # 修改 counts
        entry["readers"] = max(0, entry["readers"] - 1)
```

**问题**:

`_release_read_lock` 和 `_release_write_lock` 用 `_file_rw_dict_lock` 保护 entry 查找，释放该锁后再获取 `entry["lock"]`。两个操作之间存在 TOCTOU 窗口。虽然 entries 从不删除、此模式不会造成数据竞争（`entry` 引用始终有效），但代码可以更简洁：

**建议修复**:
```python
def _release_read_lock(file_path: str) -> None:
    entry = _get_rw_entry(file_path)       # 内部已用 _file_rw_dict_lock 保护
    with entry["lock"]:
        entry["readers"] = max(0, entry["readers"] - 1)
```

行为完全等价，更简洁，消除了 TOCTOU 的编码气味。

`_release_write_lock` 同理。

---

### 3. [建议] 重叠检测中变量名误导

**位置**: `file_tool.py:686-698`

```python
for i in range(len(validated_edits) - 1):
    s0_1, e0_1, _, _, _, _ = validated_edits[i]
    s1_0, _, _, _, _, _ = validated_edits[i + 1]
```

`validated_edits` 每个元素的格式是 `(s_0, e_0, c, desc, s_1, e_1)`：
- 索引 0: `s_0`（0-indexed start）
- 索引 1: `e_0`（0-indexed exclusive end，或 None）
- 索引 4: `s_1`（1-indexed start）
- 索引 5: `e_1`（1-indexed inclusive end）

变量名 `s0_1` 和 `e0_1` 的 `_1` 后缀暗示是 1-indexed，但实际是 0-indexed 的 `s_0` 和 `e_0`。而 `s1_0` 的后缀 `_0` 暗示 0-indexed，但也容易和"第 1 个 edit 的第 0 个元素"产生二义。

**逻辑分析**: 实际计算是正确的（`s1_0 < e0_1` 是正确的不重叠条件），但阅读这段代码需要看两遍才能确认。变量名可以更自解释。

**建议**:
```python
for i in range(len(validated_edits) - 1):
    curr_s_0, curr_e_0, _, _, _, _ = validated_edits[i]
    next_s_0, _, _, _, _, _ = validated_edits[i + 1]
    if curr_e_0 is None:
        return _wrap_error(...)
    if next_s_0 < curr_e_0:
        return _wrap_error(...)
```

---

### 4. [建议] `_validate_path` 的 `project_path` 参数未生效

**位置**: `file_tool.py:49-72`

```python
def _validate_path(file_path: str, project_path: Optional[str] = None) -> Optional[str]:
```

`project_path` 参数被接受但在函数体内从未使用。`handle_write`（第 558 行）和 `handle_uses`（第 1300 行）都传了 `project_path`，但不产生任何效果。

注释写"保留参数签名兼容"，但调用方传了值，容易让人误以为有 project root 限制。如果想保留未来扩展，建议:

1. 改为 `**kwargs` 避免调用方误解；或
2. 至少加注释说"当前未使用 project_path"；或
3. 实现 project root 白名单（以下可参考）：

```python
def _validate_path(file_path: str, project_path: Optional[str] = None) -> Optional[str]:
    """校验文件路径安全性"""
    if '\0' in file_path:
        return "路径包含 null 字节"
    try:
        resolved = os.path.abspath(os.path.realpath(file_path))
    except (OSError, ValueError) as e:
        return "路径解析失败: %s" % str(e)

    # 系统敏感目录保护
    for sensitive_dir in _SYSTEM_SENSITIVE_DIRS:
        try:
            resolved_relative = os.path.relpath(resolved, sensitive_dir)
            if not resolved_relative.startswith('..'):
                return "路径位于系统敏感目录中: %s" % sensitive_dir
        except ValueError:
            pass

    # 如果传了 project_path，限制在其目录内
    if project_path:
        try:
            proj_resolved = os.path.abspath(os.path.realpath(project_path))
            proj_dir = proj_resolved if os.path.isdir(proj_resolved) else os.path.dirname(proj_resolved)
            rel = os.path.relpath(resolved, proj_dir)
            if rel.startswith('..'):
                return "路径不在项目目录内"
        except (OSError, ValueError):
            pass   # project_path 解析失败时不阻断

    return None
```

---

## 对之前报告的自纠

以下三条原标注「严重」，现更正为「误判」：

| 原结论 | 理由 | 纠正 |
|--------|------|------|
| 路径遍历攻击漏洞 | `os.path.realpath()` 已解析 `..`；调用方是 AI Agent 非外部用户 | 不是漏洞 |
| 编码检测信息泄露 | 错误信息只返回给调用方 Agent，非广播 | 不是安全问题 |
| 脏标记缺乏持久化 | 进程级护栏，重启后会话重置是正确行为 | 设计正确 |

---

## 检查清单

| 维度 | 结论 |
|------|------|
| 接口参数验证 | 完整（类型/范围/重叠/必需字段） |
| 错误处理 | 函数内返回 dict，上层统一转 CallToolResult |
| 返回值一致性 | 统一 `{status, message}` 格式 |
| 编码处理 | 编码检测 + 降级链 + BOM 保持，逻辑自洽 |
| 并发安全 | RWLock 非阻塞，无死锁，释放路径全覆盖 try/finally |
| 脏标记保护 | 机制合理，仅一处提前清除的小 bug |
| 路径安全 | 无 null 字节、无系统敏感目录，无路径遍历 |
| 日志记录 | 关键路径有 logger.debug/warning |
| 文档一致性 | README 与代码基本一致，可补充 `allow_dirty` 参数 |

---

## 建议优先级

1. **选做**: 修复 `_clear_dirty` 提前清除（第 1 条），边缘场景防行号错位
2. **选做**: 简化 `_release_*_lock` 实现（第 2 条），消除 TOCTOU 气味
3. **选做**: `_validate_path` 增加 project_path 限制（第 4 条），防御纵深
4. **可选**: 优化重叠检测的变量名（第 3 条），提升可读性
5. **可选**: README 补充 `allow_dirty` 参数说明
