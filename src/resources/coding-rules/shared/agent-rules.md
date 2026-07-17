<!-- @when: 执行 Python 脚本、字符串格式化、处理可选参数时 -->
<!-- @chain: independent -->

## Agent 操作硬规则

### 脚本执行
- ❌ 绝不用 `python -c "..."`（PowerShell 引号转义必炸）
- ✅ 写 `.py` 文件 → `bash python script.py` → `Remove-Item` 清理

### 字符串格式化
- ❌ f-string 内嵌字典 `f'{d["key"]}'`（引号冲突）
- ✅ 用 `.format()` 或 `%`

### Python 陷阱
- **不在函数内局部 `import`**：`from X import Y` 使 Y 在函数作用域成为局部变量，顶部的引用也会 UnboundLocalError。始终写在模块顶部。
- **`if x:` vs `if x is not None:`**：0、`""`、`[]` 均为 False。可选数值参数用 `Optional[int]` 并用 `is not None` 判断。
- **`$()` 宏展开**：注册表键名不含 `$()`，加入 `macros` 字典时必须 `macros[f'$({k})'] = v`。用 `update(dict)` 会导致 `str.replace('SKIADIR', ...)` 错误匹配 `$(SKIADIR)`。
