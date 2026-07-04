# StackTrace / StackTracer 迁移计划与功能比对

**状态**: P0b 迁移完成  
**日期**: 2026-07-03  
**目标**: 统一历史 `StackTrace.pas` 运行时诊断能力与当前 `StackTracer.pas` callgraph 能力，避免把历史版本中已有问题重新带入 Daofy 工具链。

## 1. 版本盘点

| 路径 | 时间 | 大小 | SHA256 前缀 | 定位 |
|------|------|------|-------------|------|
| `C:\user\daofy-agent\ddebug\.backup_shortnames\src\Common\StackTrace.pas` | 2026-05-26 | 126.7 KB | `A4B51C61127EE748` | 旧大版早期备份 |
| `tools/daudit/StackTrace.pas` | 2026-05-29 | 127.7 KB | `4178D489B9742E27` | Daofy 仓库旧大版 |
| `C:\user\daofy-agent\daudit\Diagnostics\StackTrace.pas` | 2026-06-01 | 129.9 KB | `A466ED907B143476` | daudit 诊断版 |
| `C:\user\daofy-agent\common\StackTrace.pas` | 2026-06-09 | 136.0 KB | `91FCEE43E85633FE` | 公共库较新版 |
| `C:\user\qlang\Editor\StackTrace.pas` | 2026-06-26 | 141.1 KB | `8B71D80A1E8E36BF` | 最新大版候选基线 |
| `C:\user\daofy-agent\daudit2\StackTracer.pas` | 2026-07-03 15:49 | 17.8 KB | `400350319FDB0B01` | callgraph 初版 |
| `tools/stacktrace/StackTracer.pas` | 2026-07-03 22:53 | 23.6 KB | `8A4BFADD77F82A5B` | 当前 callgraph 版 |

结论：

- 大版 `StackTrace.pas` 是运行时诊断引擎线：异常 hook、MAPDATA、token 化、局部变量快照、默认 `exception.log`。
- 小版 `StackTracer.pas` 是 callgraph 线：`.map` 解析、`.text` `$E8` direct call 扫描、callees/callers 查询。
- 当前目标不是二选一，而是把大版诊断引擎作为主线，把小版 callgraph 合并为诊断引擎的一个查询能力。

## 2. 功能矩阵

| 能力 | ddebug 早期 | daofy daudit | daudit Diagnostics | common | qlang Editor | daudit2 StackTracer | 当前 StackTracer | 迁移策略 |
|------|-------------|--------------|--------------------|--------|--------------|---------------------|------------------|----------|
| `TStackTraceManager` | 有 | 有 | 有 | 有 | 有 | 无 | 无 | 必须恢复 |
| 异常 hook | 有 | 有 | 有 | 有 | 有 | 无 | 无 | 以 `qlang Editor` 为基线审计迁入 |
| VEH 展开前捕获 | 有 | 有 | 有 | 有 | 有 | 无 | 无 | 迁入，但必须保留重入保护 |
| 默认 `exception.log` | 有 | 有 | 有 | 有 | 有 | 无 | 无 | 迁入并标准化 UTF-8 输出 |
| 符号解析 + 行号 | 有 | 有 | 有 | 有 | 有 | 简化版 | 简化版 | 统一为 tokenized MAPDATA 优先，外部 `.map` 兜底 |
| `TMapDataSerializer` | 有 | 有 | 有 | 有 | 有 | 无 | 无 | 必须迁入 |
| token 化符号表 | 有 | 有 | 有 | 有 | 有 | 无 | 无 | 必须迁入，降低内存 |
| 压缩/解压 MAPDATA | 有 | 有 | 有 | 有 | 有 | 无 | 无 | 必须迁入 |
| 嵌入 EXE 资源 | 有 | 有 | 有 | 有 | 有 | 无 | 无 | 迁入但默认不自动自写入 |
| 局部变量快照 | 有 | 有 | 有 | 有 | 有 | 无 | 无 | 分阶段迁入，默认关闭 |
| Overlay 符号 provider | 无/弱 | 有 | 有 | 有 | 有 | 无 | 无 | 保留接口，先不强依赖 |
| callgraph 正向 | 无 | 无 | 无 | 无 | 无 | 有 | 有 | 合并进新主线 |
| callgraph 反向 | 无 | 无 | 无 | 无 | 无 | 无 | 有 | 保留当前实现 |
| callgraph JSON | 无 | 无 | 无 | 无 | 无 | 简化 | 当前较完整 | 保持兼容 |
| `LastError` / `MapLoadError` | 无 | 无 | 无 | 无 | 无 | 弱 | 有 | 保留并并入诊断状态 |

## 3. 候选基线选择

推荐基线：`C:\user\qlang\Editor\StackTrace.pas`。

理由：

- 时间最新、体量最大，包含 `common` 之后的修补。
- 已看到相对早期版本更明确的 VEH 重入保护：`VEHReentrancyGuard` 防止 handler 内 AV 递归。
- logger 异常不再完全静默，部分路径写入 `OutputDebugString`。
- 源路径解析失败会写入 `LAstDbg`，比早期空 `except` 更可审计。

不能直接覆盖的原因：

- 文件仍叫 `unit StackTrace`；早期自动化 callgraph 使用过 `unit StackTracer`，现已统一为 `uses StackTrace`，独立兼容壳已删除。
- 不包含当前 `GetCallerChain`、`CallChainToJSON(root, direction)`、`LastError`、`MapLoadError`。
- 源路径解析已移除固定 `BDS\22.0` / `BDS\23.0` 注册表版本号，改为枚举 `Software\Embarcadero\BDS` 子键并选择最高可用安装；递归扫描逻辑后续继续按 Daofy 配置/环境服务语义收束。
- `EmbedMapData` 涉及修改 EXE 资源，必须显式调用，不能作为导入即自动行为。

## 4. 历史问题清单

| 风险 | 来源证据 | 处理要求 |
|------|----------|----------|
| 空 `except` 吞错 | `common` 等早期版本的 dproj 解析、registry fallback、recursive search 存在空 handler | 禁止原样迁入；所有异常至少写入 debug diagnostics 或状态字段 |
| registry 版本硬编码 | 大版中显式读取 `BDS\22.0`、再 fallback `BDS\23.0` | 已改为遍历可用 BDS key 并选择最高有效 `RootDir` |
| VEH handler 可重入 | 旧大版 VEH 内读 EBP 链，若自身 AV 可能递归 | 必须采用 `qlang Editor` 的重入保护思路，并加最小压力测试 |
| logger 失败静默 | 早期 logger 调用异常被吞 | logger 异常写 `OutputDebugString`，且不得影响原异常传播 |
| 局部变量读栈风险 | `ReadStackVarValue`、EBP offset 读取可能越界或读失效对象 | `CaptureVariables` 默认关闭；开启时限制类型、大小、帧数，并捕获读错误 |
| EXE 自写入风险 | `EmbedMapData` / `EmbedFinalize` 会写 EXE 资源 | 只能显式调用；运行时默认只读资源和 `.map` |
| 递归路径搜索开销 | 大版源文件解析会 `TDirectory.GetFiles(... soAllDirectories)` | 已默认关闭；仅 `DAOFY_STACKTRACE_RECURSIVE_SOURCE_LOOKUP=1` 时启用，默认优先 dproj search path 与已知 Delphi source path |
| 旧版不含 callgraph | 所有 `StackTrace.pas` 大版都没有 `ScanCallGraph` | callgraph 作为新增模块合入，不从旧版推导 |
| 小版内存效率低 | 当前 `StackTracer.pas` 保存完整字符串数组和线性查找 | 使用 tokenized symbol table 替代直接 string table，保留兼容 facade |
| Win64 覆盖不足 | 当前 callgraph 主要按 Win32 PE/map 语义验证 | Win64 单独里程碑，不混入 P0 |

## 5. 命名决策

最终主单元使用 `tools/stacktrace/StackTrace.pas`，unit 名称为 `StackTrace`。

理由：

- 这是旧版运行时诊断引擎的延续，核心能力是 exception stack trace、MAPDATA、符号解析和局部变量快照，`StackTrace` 比 `StackTracer` 更贴近功能边界。
- 现有 `run_verify`、文档和历史项目已经围绕 `uses StackTrace; TStackTraceManager...` 建立心智模型，继续使用该名称迁移成本最低。
- `StackTracer` 更像当前 callgraph 小版的临时名字，不适合作为最终公共诊断单元。

兼容策略：

- `tools/stacktrace/StackTrace.pas` 是唯一主实现，同时提供 `TStackTraceManager` 和 `TStackTracer`。
- `tools/stacktrace/StackTracer.pas` 迁移期薄兼容壳已删除；调用方统一 `uses StackTrace`，继续使用 `StackTrace.pas` 中的 `TStackTracer` / `TCallEdge`。
- 禁止同时把 `tools/daudit` 和 `tools/stacktrace` 中的 `StackTrace.pas` 加进同一个 Delphi 项目的 search path，避免 unit 名冲突。

后续命名迁移不在本轮执行。若未来重命名单元，遵守 Delphi namespaced unit / 文件名规则，使用 `Daofy.xxx.pas` 形态，例如 `Daofy.Diagnostics.pas`、`Daofy.StackTrace.pas` 或更细的 `Daofy.Diagnostics.StackTrace.pas`。本轮不采用该方案，因为它会破坏旧版 API 和注入链路；等功能和验证全部收口后再做集中查找替换。

## 6. 目标架构

主文件 `tools/stacktrace/StackTrace.pas` 对外提供两个兼容层：

1. `TStackTraceManager`：旧大版主 API，负责异常 hook、MAPDATA、符号解析、局部变量快照。
2. `TStackTracer`：当前 callgraph facade，继续提供 `GetCallChain`、`GetCallerChain`、`CallChainToJSON`、`LastError`、`MapLoadError`。

内部结构建议：

| 组件 | 职责 |
|------|------|
| map parser | 解析 Detailed `.map`，生成 `TMapSymbol` / `TLineInfo` |
| MAPDATA serializer | token 化、delta address、压缩、验证、反序列化 |
| symbol resolver | 运行时地址到函数名/源码行；优先 MAPDATA 资源，其次外部 `.map` |
| exception manager | 安装/卸载 Delphi RTL hook 与 VEH |
| exception logger | 输出 `exception.log`，格式稳定、UTF-8 |
| variable snapshot | 可选捕获局部变量/参数，默认关闭 |
| callgraph scanner | 基于 symbol resolver 和 `.text` direct call 扫描构图 |

## 7. 迁移阶段

### P0 - 基线合并与只读诊断

目标：把旧大版的 tokenized MAPDATA 与异常报告主干迁入，不启用高风险写入和局部变量读取。

任务：

1. 以 `qlang Editor` 版为基线，创建 `tools/stacktrace/StackTrace.pas`，恢复 `TStackTraceManager`、`TMapDataSerializer`、异常 hook、默认 logger。
2. P0a 先保留当前 `TStackTracer` callgraph 实现不变，避免异常诊断迁移和 callgraph 行为重写叠加风险。
3. P0b 再把 `TStackTracer` facade 合并到 `StackTrace.pas`，并删除独立 `tools/stacktrace/StackTracer.pas` 兼容壳。
4. 默认启用 hook 的策略重新确认：工具注入场景可以启用，普通引用是否自动启用需明确配置。
5. `EmbedMapData` 暂时迁入但默认不调用。
6. `CaptureVariables` 默认 `False`。

验收：

- 最小 Delphi console 程序引用 `StackTrace` 后能生成 `exception.log`。
- 日志包含异常类、消息、至少一个符号化栈帧。
- 当前 `callgraph` / `callgraph_diff` Python 测试继续通过。
- QLangEditor 现有 callgraph 实测仍返回 callers/callees。

### P1 - MAPDATA 资源与内存优化

目标：让生产运行时优先使用嵌入的压缩 tokenized MAPDATA，降低符号表内存占用。

任务：

1. 恢复 `Serialize` / `Deserialize` / `Validate` / `DetectVersion` / `Merge` 覆盖测试。
2. 增加 MAPDATA 文件级 fixture，验证同一 map roundtrip 后符号和行号一致。
3. `TryLoadMapFromResource` 优先，外部 `.map` 兜底。
4. 对比直接字符串表和 tokenized 表的内存估算，形成回归指标。

验收：

- MAPDATA roundtrip 测试通过。
- 加载资源失败不会影响外部 `.map` 兜底。
- 符号解析结果和旧大版基线一致。

### P2 - 局部变量快照

目标：恢复旧版局部变量/参数捕获，但把崩溃风险收束到默认关闭的功能开关内。

任务：

1. 迁入 `LocalVarExtractor`、`ReadFunctionPrologue`、`ComputeVarOffsets`、`ReadStackVarValue`。
2. 增加类型白名单和最大读取字节数。
3. 对字符串、对象、指针读取加 guard，失败返回 `<read-error>`，不抛出。
4. 增加异常日志中 `Params` / `Locals` 的格式化测试。
5. 用手工 `SetLocalVarData` 元数据和模拟 frame buffer 验证 Win32/Win64 的局部变量读取链路。
6. daudit/AST extractor 集成后移为独立任务，不作为当前 StackTrace 迁移完成条件。

验收：

- `CaptureVariables=False` 时不读取局部变量。
- `CaptureVariables=True` 时基础整型、布尔、字符串能输出；当前验收以手工元数据 + 模拟 frame smoke 锁定 StackTrace 自身链路。
- 故意构造非法对象/指针时不二次崩溃，并返回稳定的 `<invalid>` / 地址格式化输出。
- 未知 TypeKind 不再按指针解引用，统一返回 `<unsupported type>`；字符串读取受 `MaxCapturedStringChars` 限制。
- 异常日志格式化由 `TStackTraceManager.FormatExceptionContext` 单点控制；`CaptureVariables=True` 输出 `Params` / `Locals`，`False` 时隐藏变量。

### P3 - callgraph 深度整合

目标：把当前 callgraph 变成诊断引擎的正式能力，而不是独立小工具。

任务：

1. callgraph 使用 `TStackTraceManager` 的符号表和 line table。
2. 保留 `GetCallChain`、`GetCallerChain`、`CallChainToJSON` 签名。
3. 补调用点行号、边去重、索引和 diff 稳定比较。
4. 与 `docs/callgraph-enhancement-plan.md` 中 P0/P1 对齐。

验收：

- `DaofyAutomation.CallGraph.pas` 不需要改调用方协议。
- QLangEditor `SaveIfModified callers` 和 `actNewProjectExecute callees` 回归通过。

### P4 - 编译/发布链路替换

目标：Daofy 的 `run_verify` 和发布包都使用统一后的 `tools/stacktrace/StackTrace.pas`。

任务：

1. `src/tools/compile_project.py` 从 `tools/daudit/StackTrace.pas` 切换到 `tools/stacktrace/StackTrace.pas`。
2. 注入代码继续使用 `uses StackTrace`，初始化 API 保持 `TStackTraceManager`。
3. 文档中商业 `tools/daudit` 表述更新为当前开源/内置路径。
4. release 排除规则重新检查，避免漏发诊断单元。

验收：

- `delphi_project(action="compile", run_verify=True)` 能使用新单元捕获启动异常。
- 生成包包含必要 `tools/stacktrace` 文件，不依赖 `tools/daudit`。

## 8. 对历史实现的取舍

| 模块 | 取舍 |
|------|------|
| `TMapDataSerializer` | 迁入。它是内存优化核心，但要补 roundtrip/validate 测试。 |
| `TStackTraceManager` hook | 迁入。以 `qlang Editor` 版为基线，保留重入保护。 |
| `TDefaultExceptionLogger` | 迁入并调整。输出格式保持兼容，但错误路径不可静默。 |
| `EmbedMapData` | 迁入但隔离。禁止 initialization 中自动写 EXE。 |
| `LocalVarExtractor` | 迁入接口。当前只验证手工元数据通路；daudit/AST extractor 后移为独立集成项。 |
| Registry source path discovery | 重写。不能保留 `BDS\22.0/23.0` 硬编码。 |
| Recursive source lookup | 已降级为可选。默认不全项目递归扫描，需显式设置 `DAOFY_STACKTRACE_RECURSIVE_SOURCE_LOOKUP=1`。 |
| `TStackTracer` callgraph | 保留当前版，并逐步改用大版符号表。 |
| `daudit2` callgraph 初版 | 只作历史参考，不作为迁移来源。 |

## 9. 测试计划

### Delphi 实测

1. 最小 console 异常工程：
   - 引用 `StackTrace`。
   - 调用 `TStackTraceManager.Current.EnableDefaultLogger`。
   - 主动 raise `Exception.Create('stacktrace smoke')`。
   - 验证 `exception.log` 包含异常类、消息、函数名、源码行。

2. QLangEditor 回归：
   - 编译 `C:\user\qlang\editor\qlangeditor.dproj`。
   - `callgraph SaveIfModified direction=callers project_only=true`。
   - `callgraph actNewProjectExecute direction=callees project_only=true`。

3. 局部变量快照：
   - 默认关闭时日志不含变量。
   - 开启时基础变量可输出。
   - Win32/Win64 均用手工局部变量元数据和模拟 frame buffer 验证 `Integer`、布尔枚举、`UnicodeString` 读取。
   - 非法对象返回 `<invalid>`；非法指针只格式化地址，不解引用、不导致二次异常。
   - 未知 TypeKind 返回 `<unsupported type>`；长字符串先检查长度上限，再拷贝内容。
   - `FormatExceptionContext` 在 `CaptureVariables=True/False` 下分别验证参数/局部变量显示和隐藏。

### Python 测试

```powershell
$env:PYTHONIOENCODING='utf-8'
pytest tests\test_console_automation.py -q -p no:cacheprovider
pytest tests\test_doc_consistency.py -q -p no:cacheprovider
```

需要新增：

- MAPDATA serializer fixture 测试。
- `run_verify` 注入路径测试。
- callgraph facade 兼容测试。

## 10. 回滚策略

| 失败点 | 回滚方式 |
|--------|----------|
| 新 `StackTrace.pas` 编译失败 | 恢复当前 23.6 KB `StackTracer.pas` 小版，保留 callgraph 可用 |
| 异常 hook 导致启动崩溃 | 默认关闭 `TStackTraceManager.Enabled`，只允许 run_verify 显式启用 |
| MAPDATA 解析失败 | 回退外部 `.map` 加载 |
| 局部变量快照不稳定 | 保持 `CaptureVariables=False`，推迟 P2 |
| callgraph 结果回退 | 暂时让 facade 使用当前小版扫描逻辑 |

## 11. 执行顺序建议

1. 复制 `qlang Editor` 大版到临时对照文件，不直接覆盖目标。
2. 新建 `tools/stacktrace/StackTrace.pas` 作为主实现，unit 名称保持 `StackTrace`。
3. P0a 保持当前 `StackTracer.pas` 承载 callgraph，先验证新 `StackTrace.pas` 的异常报告和 run_verify 链路。
4. P0b 将当前 `TStackTracer` API 作为 facade 合并到 `StackTrace.pas`，再删除 `StackTracer.pas` 兼容壳。
5. 编译最小 console 工程，只验证无 callgraph 的异常日志。
6. 再接入 callgraph，跑 Python 协议测试和 QLangEditor 实测。
7. 最后替换 `compile_project.py` 的 run_verify 注入路径。

## 12. 完成定义

P0a 完成必须同时满足：

- `tools/stacktrace/StackTrace.pas` 提供 `TStackTraceManager`、MAPDATA/token 化符号结构、异常 hook 和默认 logger。
- `src/tools/compile_project.py` 的 run_verify 注入路径切到 `tools/stacktrace/StackTrace.pas`。
- 异常日志能力不再依赖 `tools/daudit/StackTrace.pas`。
- 当前 callgraph 协议不破坏，`StackTracer.pas` 暂时保持现有实现。

最终迁移完成必须同时满足：

- `tools/stacktrace/StackTrace.pas` 同时提供 `TStackTraceManager` 和 `TStackTracer`。
- 独立 `tools/stacktrace/StackTracer.pas` 已删除，所有调用方统一使用 `StackTrace.pas`。
- 异常日志能力不依赖 `tools/daudit/StackTrace.pas`。
- tokenized MAPDATA 可用，并有 roundtrip 测试。
- 当前 callgraph 协议不破坏。
- 历史空 `except`、硬编码 BDS、自动 EXE 写入等风险已被修正或隔离。

## 13. P0a 实施记录

- 已将 `C:\user\qlang\Editor\StackTrace.pas` 复制为 `tools/stacktrace/StackTrace.pas`；SHA256 前缀保持 `8B71D80A1E8E36BF`。
- 已将 `src/tools/compile_project.py` 的 run_verify 注入目录从 `tools/daudit` 切换为 `tools/stacktrace`。
- 已同步 `src/resources/coding-rules.md` 与 `src/resources/coding-rules/compile.md` 的 run_verify 路径说明。
- 已新增 run_verify 注入路径单测，防止回退到 `tools/daudit`。
- 已验证 `tools/stacktrace/StackTrace.pas` 可单文件编译。
- 已用最小 console 工程执行 `run_verify=True`，确认可生成并回读 `exception.log`，日志包含 `stacktrace smoke` 和源码行号。
- 2026-07-04 复测：同一最小崩溃工程 Win32/Win64 均通过 `run_verify=True` 回读异常日志。Win32 日志包含 `CrashMiddle`、`CrashEntry` 和 DPR 行号；Win64 日志包含 `CrashLeaf`、`CrashMiddle`、`CrashEntry` 和 64 位地址。
- 2026-07-04 Win64 编译修正：`WalkStackFromContext` 的上下文寄存器判断统一使用 `WIN64`；`ExceptionStackInfoProc` 的 EBP 链补充逻辑完整限制在 `WIN32` 条件编译内，避免 Win64 编译触发 `Eip`、未使用变量或未初始化变量问题。
- 2026-07-04 局部变量快照补测：`tests/test_stacktrace_callgraph_runtime.py` 通过手工 `SetLocalVarData` 注入和模拟 frame buffer，在 Win32/Win64 下验证 `Integer`、布尔枚举、`UnicodeString`、非法对象、非法指针和未知 TypeKind 的 `GetFrameSnapshot` 读取链路；同时 `ReadFunctionPrologue` 增加 Win64 `SUB RSP` prologue 扫描，`ComputeVarOffsets` 改为 pointer-sized 本地槽位。
- 2026-07-04 异常日志格式化补测：新增 `TStackTraceManager.FormatExceptionContext`，默认 `TDefaultExceptionLogger` 复用该 formatter；测试验证 `CaptureVariables=True` 时输出 `Params` / `Locals`，`False` 时只输出 frame。
- 2026-07-04 源路径解析修正：`EmbedMapData` 查找 Delphi RTL/VCL 源码时不再硬编码 BDS `22.0` / `23.0`，改为枚举 `Software\Embarcadero\BDS` 已安装版本并选择最高 `RootDir`，覆盖 Delphi 13 / BDS 37 等新版本。
- 2026-07-04 递归路径搜索收束：`EmbedMapData` 默认不再执行 `TDirectory.GetFiles(... soAllDirectories)` 全项目递归搜索；仅当 `DAOFY_STACKTRACE_RECURSIVE_SOURCE_LOOKUP=1` 时启用，并在诊断日志中明确记录默认关闭。
- P0a 阶段 `StackTracer.pas` 仍承载 callgraph 实现；P0b 已合并进 `StackTrace.pas`，兼容壳随后删除。

## 14. P0b 实施记录

- 已在 `tools/stacktrace/StackTrace.pas` 中提供 `TCallEdge`、`TStackSnapshot`、`TStackTracer`。
- `TStackTracer` facade 复用 `TStackTraceManager.EnumerateFunctions` 的 tokenized MAPDATA 符号表，不再维护独立字符串符号表。
- 独立 `tools/stacktrace/StackTracer.pas` 兼容壳已删除；`TCallEdge` / `TStackSnapshot` / `TStackTracer` 均由 `StackTrace.pas` 提供。
- `tools/auto/DaofyAutomation.CallGraph.pas` 已改为 `uses StackTrace`。
- 已验证 `StackTrace.pas`、`DaofyAutomation.CallGraph.pas` 均可 Win32/Win64 单文件编译。
- 已验证最小 Win64 VCL GUI callgraph smoke：`SmokeEntry` callees 返回 2 条边，地址按 64 位宽度输出，并带 `SmokeMain.pas` 行号。
- 已验证 QLangEditor Win64 Debug 真项目 callgraph：`SaveIfModified` callers 返回 3 条边，`actNewProjectExecute` callees 返回 40 条边，地址按 64 位宽度输出，并带 `main.pas` / `ProjectMgr.pas` 等源码行号。

## 15. P4 接入链路核查记录

- `src/tools/compile_project.py` 的 run_verify 注入目录为 `tools/stacktrace`，注入 `StackTrace.pas` 并继续调用 `TStackTraceManager.Current.EnableDefaultLogger`。
- `tests/test_compiler_service.py` 已锁定 run_verify 注入路径必须包含 `tools\stacktrace\StackTrace.pas` 且不能包含 `tools\daudit`。
- 发布脚本使用 `git ls-files` 打包，排除规则只排除 `tools/daudit/`；`tools/stacktrace/StackTrace.pas` 已纳入版本控制后会随 release 包自动包含。
- 代码中与审计工具本体相关的 `daudit` 引用保留，不作为本轮 StackTrace/callgraph 迁移范围。

## 16. P3 深度整合记录

- `TStackTraceManager` 新增 `TryResolveSourceLine`，统一持有运行时地址到源码文件/行号的 line table 解析逻辑。
- `TStackTracer.ScanCallGraph` 不再直接读取 `FLineEntries` / `FSourcePaths`，调用点行号通过 manager API 获取。
- 已新增静态守卫，防止 callgraph facade 重新耦合到 manager 私有 line table。
