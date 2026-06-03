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
├── tools/                 # MCP tool implementations (delphi_file, code_hosting, project, delphi_kb, ...)
├── services/              # Business logic
│   ├── compiler_service.py, config_manager.py, process_manager.py, args_generator.py
│   └── knowledge_base/    # KB modules (schema, smart_cache, project, thirdparty, scan, embedding, async_task_manager)
├── models/                # Pydantic/dataclass models
└── utils/                 # Utilities (delphi_env, dproj_parser, validator, logger)
```

## 工具使用规则

### Git 操作必须使用 code_hosting
所有 Git 操作（status/add/commit/push/clone/push_retry）必须通过 `code_hosting` 工具，禁止直接使用 bash 运行 git 命令。`code_hosting` 会统一格式化输出、自动处理异步推送重试，比原始 bash git 更省 token。

### 经验库维护规则
`experience` 工具会自动去重（embedding 相似度 >0.85 时合并到旧记录而非新增），但 AI 仍需主动维护经验质量：

0. **保存前先泛化**：调用 `experience(action="save")` 前，先 `experience(action="search", query=...)` 搜索是否已存在覆盖同类问题的抽象经验。如果找到，用 `action=merge` 或 `action=update` 将当前场景合并进去，不要另存为一条具体场景的记录。示例：不要存「编译后 output_file 冗余」，而是合并到「MCP 工具接口输出精简」——后者可以覆盖任意工具的返回值清理。
1. **任务完成后**：如果刚解决的问题与已有经验高度相关，但解决方式不同，用 `action=merge` 手动合并两条经验
2. **定期清理**：用 `action=prune` 列出低价值（低 hit_count、长期未更新）的经验，检查后 `action=delete` 删除
3. **抽象合并**：发现多条经验描述的是同一类问题（如不同工具的「消息精简」），手动合并为一条抽象经验，`tags` 要覆盖各类场景

## Agent 编码工作流（优先级顺序）

### 编辑 Delphi 文件前

> ⚠️ **工具调用规则**：以下每一步都使用对应的 **MCP 工具名** 调用。每个工具名即是你在 `list_tools()` 中看到的工具名称。如果工具未出现在列表，刷新 MCP 连接。

| 步骤 | 调用的 MCP 工具 | 说明 |
|------|----------------|------|
| ① 环境检查 | `check_environment(action="check")` | 确认编译器可用 |
| ② 编码规则 | `get_coding_rules(project_path=...)` | 获取项目编码规范 |
| ③ API 搜索 | `delphi_kb(query=...)` | 搜索 API 定义（详见 `config/CODING_RULES.mdc` ② 节） |
| ④ 读源码 | `delphi_file(action="read", file_path=...)` | 读取文件确认修改点 |
| ⑤ 写代码 | `delphi_file(action="write", content=...)` | 写入代码（自动备份到 __history） |
| ⑥ 格式化 | `delphi_file(action="format", file_path=...)` | pasfmt 格式化代码 |
| **⑦ 编译验证** | **`project(action="compile", project_path=...)`** | **编译 `.dproj`/`.dpr`/`.dpk` 项目** |
| **⑧ 运行验证** | **`project(action="compile", ..., run_verify=True)`** | **编译后启动 exe 运行 3 秒，检测运行时崩溃** |
| **⑨ 运行时检查** | **`project(action="runtime", base_dir=...)`** | **扫描组件类名，检测遗漏 uses 单元** |

> **⚠️ 强制规则**：步骤 ⑦⑧⑨ **必须**使用 `project` 工具。`project_compile` 已合并到 `project(action="compile")`，不存在独立的 `project_compile` 工具。禁止用 bash 直接执行 dcc32/msbuild。

各步骤补充说明：

- **⑧ run_verify**: 编译成功后自动启动 exe 运行 3 秒，若进程崩溃则标记验证失败（秒级，自动结束进程）。检测到 `exception.log` 时使用 `detect_encoding`（与 delphi_file 同款 BOM/编码检测）读取内容直接嵌入 MCP 响应，无需 AI 额外调用 delphi_file。
- **⑨ runtime 检查**: 扫描 .pas/.dfm 中组件类名，匹配 `src/rules/runtime_registry.json` 规则表，检测是否遗漏必需 uses 单元（如 FireDAC.DApt）。独立于编译步骤，纯源码级分析。

> 详细 KB 搜索策略、优先级规则、kb_type 范围、Entity Kind Codes 见 `config/CODING_RULES.mdc` ② 节。

## Code Style (Python)

- **类型**: 全部用 type hints
- **导入顺序**: stdlib → third-party → local (每组空格分隔, 内部字母序)
- **命名**: `snake_case` 函数/变量, `PascalCase` 类, `UPPER_SNAKE` 常量, `_前缀` 私有
- **文档**: Google-style docstring, 公共函数必须有
- **异常**: 用具体异常类型, 不要 `except Exception: pass`
- **测试**: `test_*.py`, `test_` 前缀函数, pytest fixture, `unittest.mock` 打桩

## Agent 操作硬规则

> 脚本执行、字符串格式化、Python 陷阱等通用规则见 `config/CODING_RULES.mdc`「Agent 操作硬规则」。

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
- `delphi_file(action="write", file_path=..., content=...)` **默认 `backup=True`**，自动备份到 `__history`，无需手动调用
- 如需单独创建备份：`delphi_file(action="backup", file_path="src/Unit1.pas")`
- 恢复：`delphi_file(action="backup", backup_action="restore", file_path="src/Unit1.pas", version=3)`
- 列出备份：`delphi_file(action="backup", backup_action="list", file_path="src/Unit1.pas")`
- ❌ 禁止直接使用 edit/write 工具修改 .pas/.dfm 文件而不通过 delphi_file 进行备份

### 部分写入规则（start_line/end_line）

**`delphi_file` 的 `start_line`/`end_line` 是 0-indexed 左闭右开区间，不是 1-indexed。**

| 参数 | 说明 |
|------|------|
| `start_line=0` | 从文件第 1 行开始（第 0 行不存在，0 = 第 1 行） |
| `start_line=5, end_line=10` | 替换第 6~10 行（0-indexed `[5,10)`） |
| `start_line=4, end_line=5` | 只替换第 5 行（0-indexed `[4,5)`） |

> **为什么不是 1-indexed？** 代码内部直接用 `lines[s:e]` Python 切片处理，Python 切片是 0-indexed。读取输出的行号标注为 `(0-indexed, [start, end))`。

**连续编辑的行号偏移算法（绝不用重读）：**

每次 `write` 会返回偏移量信息：
```
替换范围: 第 6~10 行 (0-indexed [5,10), 5 行)
偏移量: +3（删5行, 插8行）
后续编辑: 行号 ≥ 10 的新行号 = 原行号 + 3；行号 < 5 的不变
```

Agent 根据以下规则计算后续行号，**不需要重新读取文件**：

```
设某次 write 返回: s=start_line, e=end_line, offset=净偏移
则后续用原行号 L 计算新行号:
  L < s  → 新行号 = L        (在编辑区域前，不变)
  L ≥ e  → 新行号 = L + offset  (在编辑区域后，累加偏移)
  s ≤ L < e → 该行已被替换/删除，不能再用作后续编辑目标
```

有多次 write 时，每次独立计算、**依次累加**：
```
① write(s=5, e=10, offset=+3)  → 后续编辑原行号 20 → 20+3=23
② write(s=8, e=12, offset=-2)  → 上步 23 经过这步: 23≥12 → 23+(-2)=21
```

如果累计偏移后不确定，或修改范围交叠，才需要 `delphi_file(action="read")` 重新读取。

**两大致命错误（绝不能犯）：**
1. ❌ 写操作传 `start_line=5` 以为是从第 5 行开始（实际是第 6 行）→ 偏移 1 行
2. ❌ 不累加偏移量，直接用上次 read 的原始行号发第二次 write → 替换到错误位置

**注意：`uses` action 也会偏移行号。**
`delphi_file(action="uses", ...)` 返回的偏移量格式与 write 一致，Agent 同样需要累加计算。

**推荐替代方案：**
- 如果一次改动涉及多个不连续的位置，优先用 `content` 传完整文件内容（全文替换），而非多次部分写入
- 增加 uses 单元 → 用 `delphi_file(action="uses", uses_action="add", ...)`，不要手动算行号
- 修改已有代码 → 一次 write 尽量覆盖完整方法/过程，避免拆成多个部分写入

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
④ **优先调用 project(audit/ast)**（daudit 不可用时降级为引导）
   → 使用 `mode="ast"`（⭐ 推荐，daudit --mode skeleton --compact）快速了解代码结构
   → 需要深度规则检查时使用 `mode="audit"`（运行 50+ 条静态分析规则）
   → AI 解读结果，排除误报，生成修复建议
   → 补充手动检查（project(action="audit") 标记 is_ai_needed=true 的项）
⑤ project(action="compile") / pytest 验证（如果涉及代码修改）
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
project(action="ast", base_dir="src")           → ⭐ 代码骨架提取（daudit --mode skeleton --compact 最省 token）
project(action="audit", base_dir=".", rules="P0") → 深度静态分析规则检查（可选的）
delphi_file(action="read", file_path="unit.pas")   → 查看 Delphi 源码
delphi_kb(query="TThread", search_type="reference") → 查 Delphi API 用法
project(action="compile", project_path="proj.dproj") → Delphi 审计后验证编译
--- Python 项目审计用以下工具 ---
grep / ast_grep_search                      → 搜索 Python 代码中的模式
lsp_diagnostics / lsp_symbols               → 类型检查和符号分析
pytest                                      → 审计后运行测试验证
```

> `project` 工具是编译/审计/运行时检查的统一入口，无独立的 `project_compile`。**步骤 ⑦⑧⑨ 必须使用 `project` 工具**，不得用 bash 直接执行 dcc32/msbuild。

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
    $_ -notmatch '^\.gitignore$' -and
    $_ -notmatch '^tools/daudit/'
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

**排除项**：`tools/daudit/` 下的文件（含 `StackTrace.pas`）属于商业付费部分，不包含在 Release 包中。

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
