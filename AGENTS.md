# AGENTS.md - Agent Coding Guidelines

Daofy — Python 3.10-3.14, Windows, pytest.

## Quick Command Reference

| Action | Command |
|--------|---------|
| Install deps | `pip install -r requirements.txt && pip install -e ".[dev]"` |
| Run all tests | `pytest` (or `python tests/run_all_tests.py` for basic) |
| Run one test | `pytest tests/test_validator.py -v` |
| Lint/type | `mypy src/` |
| Environment | Always set `$env:PYTHONIOENCODING='utf-8'` on Windows |
| Run server | `python src/server.py` |

## Project Structure

```
src/
├── server.py              # MCP entry point
├── tools/                 # MCP tool implementations (file_tool, code_hosting, create_component_dfm, compile_project, delphi_kb, ...)
├── services/              # Business logic
│   ├── compiler_service.py, config_manager.py, process_manager.py, args_generator.py
│   └── knowledge_base/    # KB modules (schema, smart_cache, project, thirdparty, scan, embedding, async_task_manager)
├── models/                # Pydantic/dataclass models
└── utils/                 # Utilities (delphi_env, dproj_parser, validator, logger)
```

## Agent 编码工作流（优先级顺序）

### 编辑 Delphi 文件前

```
① check_environment(action="check")       → 确认编译器
② get_coding_rules(project_path=...)       → 获取编码规则
③ delphi_kb(query=...)                     → 搜索 API 定义（下面详述）
④ file_tool(action="read", file_path=...)  → 读源码（确认修改点）
⑤ file_tool(action="write", content=...)   → 写代码（默认自动备份到 __history）
⑥ file_tool(action="format", file_path=...) → 格式化
⑦ compile_project(project_path=...)         → 编译验证
```

### 知识库搜索（先猜精确名，再模糊搜）

| 优先级 | 方式 | 示例 |
|--------|------|------|
| 1 | 猜精确类名 → `search_by_name` | `TStringList` |
| 2 | 猜函数名 → `search_type="function"` | `Create` |
| 3 | 多关键字尝试 | `TJSONObject`→`TJsonSerializer` |
| 4 | `search_type="reference"` 查引用 | 评估修改影响 |
| 5 | `search_type="semantic"` 兜底 | 中文需求 |

**`project_path` 规则**：`kb_type="project"` 时必须传；`kb_type="all"` 时可选（不传则只搜 delphi+thirdparty）；`delphi`/`thirdparty`/`document` 不需要。

**典型错误**：`delphi_kb(query="帮我找分割函数", search_type="semantic")` → 应改为 `delphi_kb(query="Split", search_type="function")`。

**搜索**：单元名（如 `System.DateUtils`）自动回退到文件路径匹配；`search_type="function"` 同时匹配 FF+FP。

```
需要写代码
  → 引用已有类型/函数? → 猜类名/函数名 → delphi_kb 精确搜索 → 看定义/继承链 → 生成代码
  → 否则 → 直接生成代码
  → compile_project 验证
```

### 知识库范围

| kb_type | 目标 | project_path |
|---------|------|-------------|
| `project` | 项目自有代码 | **必须传** |
| `delphi` | VCL/FMX/RTL 官方 | 不需要 |
| `thirdparty` | 三方组件 | 不需要 |
| `document` | Delphi 帮助文档 | 不需要 |

### Entity Kind Codes

`TC`=class `TR`=record `TI`=interface `TE`=enum `TS`=set `TY`=type alias `FF`=function `FP`=procedure `CC`=const `CR`=resourcestring `KS`=string literal `TH`=helper

## Code Style (Python)

- **类型**: 全部用 type hints
- **导入顺序**: stdlib → third-party → local (每组空格分隔, 内部字母序)
- **命名**: `snake_case` 函数/变量, `PascalCase` 类, `UPPER_SNAKE` 常量, `_前缀` 私有
- **文档**: Google-style docstring, 公共函数必须有
- **异常**: 用具体异常类型, 不要 `except Exception: pass`
- **测试**: `test_*.py`, `test_` 前缀函数, pytest fixture, `unittest.mock` 打桩

## Agent 操作硬规则

### 脚本执行
- ❌ 绝不用 `python -c "..."`（PowerShell 引号转义必炸）
- ✅ 始终用 `write` 创建 `.py` 文件 → `bash` 执行 `python script.py` → `Remove-Item script.py` 清理

### 字符串格式化
- ❌ f-string 内嵌字典 `f'{d["key"]}'`（引号冲突）
- ✅ 用 `.format()` 或 `%`

### Python 陷阱
- **不要在函数内局部 `import`**：函数内任何地方出现 `from X import Y` 会使 `Y` 在整个函数作用域成为局部变量。放在头部的引用也会 `UnboundLocalError`。始终写在模块顶部。
- **`if x:` vs `if x is not None:`**：0、`""`、`[]` 都是 False。数字可选参数用 `Optional[int]` 并用 `is not None` 判断。
- **`$()` 宏展开**：注册表变量键名（`SKIADIR`）不含 `$()` 前缀，加入 `macros` 字典时必须 `macros[f'$({k})'] = v`。用 `update(dict)` 会导致 `str.replace('SKIADIR', ...)` 错误匹配 `$(SKIADIR)` → 路径残缺。

### 多进程 Worker
- **Worker 内部禁用 `print()`**：MCP 环境下 stdout 是 JSON-RPC 通信管道，worker print 破坏协议边界，构建从 8s 飙到 172s
- Worker 标准模式：
  ```python
  def worker(args):
      import io, sys
      sys.stdout = sys.stderr = io.StringIO()
      try:
          ...  # 实际工作
          return result
      except:
          return None  # 错误通过返回值传递
  ```

### 数据库
- **DDL 统一**：所有建表语句集中在 `schema.py`，各 Builder 调 `create_source_tables()`/`create_document_tables()`
- **同一 DB 文件所有连接用相同 journal 模式**：本项目统一使用 WAL（`PRAGMA journal_mode=WAL`），切换模式需要独占锁，运行中若有其他连接会 locked
- 修改表结构后 `grep` 全项目旧表名/列名的所有 INSERT/DELETE/SELECT/ALTER 引用

### 文件修改前备份
- `file_tool(action="write", file_path=..., content=...)` **默认 `backup=True`**，自动备份到 `__history`，无需手动调用
- 如需单独创建备份：`file_tool(action="backup", file_path="src/Unit1.pas")`
- 恢复：`file_tool(action="backup", backup_action="restore", file_path="src/Unit1.pas", version=3)`
- 列出备份：`file_tool(action="backup", backup_action="list", file_path="src/Unit1.pas")`
- ❌ 禁止直接使用 edit/write 工具修改 .pas/.dfm 文件而不通过 file_tool 进行备份

### 编译
- `shell=True` 执行编译事件前记录 `logger.warning`（命令来自 `.dproj` 文件）
- 长轮询 ≤30 秒（MCP 请求通道约 60s 超时），超时后切换短轮询

## 源码审计

### 审计触发条件
当用户要求以下内容时，Agent 必须执行源码审计流程：

| 触发词 | 说明 |
|--------|------|
| "审计代码"、"审查代码"、"代码审核"、"review code"、"audit" | 全面审计 |
| "安全检查"、"漏洞扫描"、"安全隐患"、"security review" | 安全专项审计 |
| "性能分析"、"性能审计"、"慢在哪"、"performance" | 性能专项审计 |
| "资源泄漏"、"内存泄漏"、"句柄泄漏"、"resource leak" | 资源管理专项审计 |

### 审计工作流

```
① 确定审计对象
   ├─ Delphi 代码（.pas/.dproj/.dpk）→ get_coding_rules(section="review")
   └─ Python 项目（当前 MCP Server）→ 按下方 Python 审计要求逐项检查
② 确定审计范围（全局/指定文件/新增代码）
③ 搜索相关 API 定义，评估用法（Delphi 用 delphi_kb，Python 用 grep/LSP）
④ 按对应标准的审计类别逐项检查
⑤ compile_project / pytest 验证（如果涉及代码修改）
⑥ 输出审计报告
```

### Delphi 审计

审计 Delphi 代码时，直接引用 `CODING_RULES.mdc` 的「审核」章节作为检查项来源：

> **检查项来源**：`get_coding_rules(section="review")` 获取完整的 Delphi 审核表
>（一致性、完整性、资源泄露、Delphi 特有、常见错误模式、代码质量、数据转换、安全、性能）。

### Python 项目审计（当前 MCP Server）

审计本 MCP Server 项目（Python 代码）时，按以下类别逐项检查：

#### 1. 安全审计（Security）
| # | 检查项 | 说明 |
|---|--------|------|
| 1.1 | 命令/Shell 注入 | `subprocess`/`Popen`/`os.system` 参数拼接用户输入 → 必须用列表参数 `["cmd", arg]`，禁用 `shell=True` 传参 |
| 1.2 | 路径遍历 | 用户传入路径未经 `resolve()`/`abspath()` 校验直接文件操作 → 限制在允许目录内 |
| 1.3 | 注册表安全 | `winreg` 读写仅读 HKLM/HKCU 的 Embarcadero BDS 路径，不写关键系统位置 |
| 1.4 | 敏感信息泄露 | `compilers.json` 等配置文件中密钥/密码 → 环境变量替代；日志中不输出 token/password |
| 1.5 | 临时文件安全 | `tempfile` 模块创建临时文件用 `NamedTemporaryFile(delete=True)`，防竞争 |
| 1.6 | Pickle 反序列化 | 禁止 `pickle.loads` 从不可信源加载数据 → 用 JSON 替代 |

#### 2. MCP 协议与工具审计（MCP Protocol）
| # | 检查项 | 说明 |
|---|--------|------|
| 2.1 | 工具注册一致性 | `list_tools()` 和 `call_tool()` 必须同步注册 — 所有 call_tool 中处理的工具必须在 list_tools 中声明 |
| 2.2 | 参数校验 | 工具输入参数前置校验，缺失必需参数返回明确错误信息 |
| 2.3 | 异常安全 | 工具内全部异常在顶层 `call_tool` 中统一捕获并返回 `CallToolResult(isError=True)`，不得泄露 traceback 给 MCP 客户端 |
| 2.4 | 返回格式统一 | 所有工具最终返回 `CallToolResult(content=[TextContent(...)], isError=...)`，不得直接返回 dict |
| 2.5 | 超时控制 | 编译等耗时操作设置 `timeout` 参数，避免 MCP 通信通道超时（约 60s） |
| 2.6 | 子进程通信保护 | Worker 进程 stdout 已 pipe 为 JSON-RPC 通道时禁用 `print()`，使用 `sys.stderr` 或 logging |

#### 3. 并发与进程审计（Concurrency & Process）
| # | 检查项 | 说明 |
|---|--------|------|
| 3.1 | Worker print 禁令 | `multiprocessing` worker 内部禁用 `print()`，MCP 环境下 stdout 是通信管道，print 破坏协议边界 |
| 3.2 | 子进程退出清理 | 使用 `Popen`/`ProcessPoolExecutor` 后确保进程退出时资源清理（`terminate()`/`join()`/`cancel()`） |
| 3.3 | 竞态条件 | 共享变量（`_pkb_cache` 等）加锁保护，用 `threading.Lock` 而非 `global` 裸访问 |
| 3.4 | 跨平台兼容 | Windows `spawn` 模式下子进程重新导入模块 → 在 `if __name__ != '__mp_main__'` 保护下延迟导入 |
| 3.5 | 长轮询超时 | 编译状态轮询 ≤30 秒，超时后切换短轮询，防止阻塞 MCP 请求通道 |

#### 4. 资源管理审计（Resource Management）
| # | 检查项 | 说明 |
|---|--------|------|
| 4.1 | 数据库连接泄漏 | SQLite 连接用 `with` 或 `try...finally` 保障关闭，`use_wal=False` 时注意独占锁 |
| 4.2 | 文件句柄泄漏 | `open()` 在 `with` 块内使用，手动 `f.open()` 必须有对应的 `f.close()` |
| 4.3 | 临时文件清理 | 编译过程中创建的临时 `.res`/`.dcu` 文件应在结束时清理 |
| 4.4 | 缓存未清理 | `_pkb_cache` 在服务关闭时通过 `_cleanup_resources()` 清理，确保所有 KB 实例 `close()` |
| 4.5 | 进程残留 | 子进程超时后需 `kill()` 而非仅 `wait()`，避免僵尸进程 |

#### 5. 错误处理审计（Error Handling）
| # | 检查项 | 说明 |
|---|--------|------|
| 5.1 | 空 except | `except: pass` / `except Exception: pass` — 禁止静默忽略，必须记录日志 |
| 5.2 | 异常范围过宽 | 用具体异常类型而非裸 `except:`，区分 IOError/ValueError/KeyError 等 |
| 5.3 | 日志完整性 | `except` 块中记录异常用 `logger.error(msg, exc_info=True)` 附带调用栈 |
| 5.4 | finally 遗漏 | 资源获取（文件/DB/锁）后必须 `try...finally` 确保释放 |
| 5.5 | 外部调用容错 | 调用编译器/外部工具时的异常需降级处理，不因外部异常导致 MCP Server 崩溃 |

#### 6. 代码质量审计（Code Quality）
| # | 检查项 | 说明 |
|---|--------|------|
| 6.1 | Type Hints | 所有函数/方法必须包含完整的类型注解，返回类型不可省略 |
| 6.2 | 导入顺序 | stdlib → third-party → local 三组，空格分隔，组内字母序 |
| 6.3 | 命名规范 | `snake_case` 函数/变量/方法，`PascalCase` 类，`UPPER_SNAKE` 常量，`_前缀` 私有 |
| 6.4 | 文档字符串 | 公共函数必须有 Google-style docstring，说明 Args/Returns/Raises |
| 6.5 | 圈复杂度 | 函数不超过 50 行，嵌套不超过 4 层，过长需拆分 |
| 6.6 | 异步模式 | 异步函数内慎用 `time.sleep()`，使用 `asyncio.sleep()`；避免同步阻塞事件循环 |
| 6.7 | 字符串格式化 | 禁用 f-string 嵌套字典键 `f'{d["key"]}'`（引号冲突），用 `.format()` 或前置变量 |
| 6.8 | 函数内局部 import | 禁止在函数内部出现 `from X import Y`（会使 Y 在整个函数作用域成为局部变量），import 必须写在模块顶部 |

#### 7. 配置与环境审计（Configuration）
| # | 检查项 | 说明 |
|---|--------|------|
| 7.1 | 编译器路径 | `compilers.json` 中的路径在服务启动时可校验有效性，无效路径应有降级 |
| 7.2 | 注册表回退 | 注册表读取失败时自动回退默认路径列表 |
| 7.3 | 编码设置 | Windows 下必须设置 `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1` |
| 7.4 | 依赖完整性 | 新增依赖需同时更新 `requirements.txt` 和 `pyproject.toml` |

### 审计报告模板

```
## 源码审计报告

**项目**: <项目名称>
**审计范围**: <全局 / 文件列表>
**审计日期**: <日期>

---

### 概览

审计范围是 Delphi 代码时：

| 类别 | 发现数 | 严重 | 一般 | 建议 |
|------|--------|------|------|------|
| 安全 | N | N | N | N |
| 资源管理 | N | N | N | N |
| 错误处理 | N | N | N | N |
| Delphi 特有 | N | N | N | N |
| 一致性 | N | N | N | N |
| **合计** | **N** | **N** | **N** | **N** |

审计范围是 Python MCP Server 时：

| 类别 | 发现数 | 严重 | 一般 | 建议 |
|------|--------|------|------|------|
| 安全 | N | N | N | N |
| MCP 协议与工具 | N | N | N | N |
| 并发与进程 | N | N | N | N |
| 资源管理 | N | N | N | N |
| 错误处理 | N | N | N | N |
| 代码质量 | N | N | N | N |
| 配置与环境 | N | N | N | N |
| **合计** | **N** | **N** | **N** | **N** |

### 严重问题

1. **[严重] <文件:F行>: <问题描述>**
   - **问题**: ...
   - **风险**: ...
   - **建议修复**: ...
   - **代码示例**:
     ```pascal
     // 当前代码
     ...
     // 修复后
     ...
     ```

### 一般问题

...

### 建议项

...

### 审计结论

<整体评估：代码质量评级、主要风险点、建议优先修复项>
```

### 审计工具配合

```
get_coding_rules(section="review")               → 获取 Delphi 审核标准
file_tool(action="read", file_path="unit.pas")   → 查看 Delphi 源码
delphi_kb(query="TThread", search_type="reference") → 查 Delphi API 用法
compile_project(project_path="proj.dproj")        → Delphi 审计后验证编译
--- Python 项目审计用以下工具 ---
grep / ast_grep_search                      → 搜索 Python 代码中的模式
lsp_diagnostics / lsp_symbols               → 类型检查和符号分析
pytest                                      → 审计后运行测试验证
```

## 发布打包流程

### 创建 Release 包

```powershell
$env:PYTHONIOENCODING='utf-8'
$7z="$src\tools\7z\7z.exe"
$src="C:\User\delphi-complier-mcp-server"
$ver="v2026.05.14"  # 替换为当前版本
$out="$src\releases\daofy-for-delphi-$ver"

# 从 git 索引取文件（自动排除 .gitignore 内容）
git ls-files | Where-Object {
    $_ -notmatch '^\.arts/' -and
    $_ -notmatch '^\.coverage$' -and
    $_ -notmatch '^config/history\.json$' -and
    $_ -notmatch '^src/config/compilers\.json$' -and
    $_ -notmatch '^\.gitignore$'
} | ForEach-Object {
    $target = Join-Path "$out" "$_"
    $dir = Split-Path $target -Parent
    if (!(Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item (Join-Path $src $_) $target -Force
}

# 打包三种格式
& $7z a -ttar "$src\releases\daofy-for-delphi-$ver.tar" "$out\*" -bb0 -bsp0
& $7z a -t7z "$src\releases\daofy-for-delphi-$ver.7z" "$src\releases\daofy-for-delphi-$ver.tar" -mx=9 -m0=LZMA2 -bb0 -bsp0
& $7z a -tzip "$src\releases\daofy-for-delphi-$ver.zip" "$out\*" -mx=9 -bb0 -bsp0
Remove-Item "$out" -Recurse -Force
```

**自动包含**：`tools/pasfmt/cli/pasfmt.exe` 等工具文件由 `git ls-files` 自动纳入（已在版本控制中），无需手动处理。

### 发布步骤

1. 运行打包脚本 → 生成 `.7z` / `.tar` / `.zip`
2. 创建 GitHub Release：
   ```bash
   gh release create v2026.05.14 --title "v2026.05.14" --notes-file release_notes.md
   ```
3. 附加包文件到 Release（通过 Web UI 或 `gh release upload`）

## 重构 Checklist

```
[ ] DDL 统一为 schema 模块
[ ] grep 旧表名/列名所有 CRUD 引用
[ ] 删除废弃方法后验证无外部调用
[ ] 检查局部 import 作用域问题
[ ] 同一 DB 的 journal 模式一致
[ ] 0 值用 is not None 判断
[ ] 构建结束时记录 metadata(时间+用时)
[ ] 强制重建用 DELETE FROM (不逐行)
[ ] 全量测试 + KB 构建验证
[ ] MCP 工具超时说明准确
[ ] 多进程 worker 禁用 print()
```
