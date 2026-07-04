# Callgraph 能力增强规划

**计划状态**: 可实施规划  
**规划日期**: 2026-07-03  
**适用范围**: `automate_delphi(gui)` 的 `callgraph` / `callgraph_diff` / `callgraph_impact`，Delphi 端 `DaofyAutomation.CallGraph.pas` / `StackTrace.pas`，Python 协议层、文档与测试。独立 `StackTracer.pas` 兼容壳已移除，统一使用 `StackTrace.pas`。

## 1. 当前基线

| 能力 | 当前状态 | 证据 | 主要缺口 |
|------|----------|------|----------|
| 正向调用图 | 已支持 `direction=callees` | `StackTrace.pas:TStackTracer.GetCallChain`, `DaofyAutomation.CallGraph.pas:233` | 只扫描 near direct call `$E8` |
| 反向调用图 | 已支持 `direction=callers` | `StackTrace.pas:TStackTracer.GetCallerChain`, `DaofyAutomation.CallGraph.pas:231` | 查询时遍历全部边，项目大时会慢 |
| 项目过滤 | 已支持 `project_only` 和 `exclude_prefixes` | `DaofyAutomation.CallGraph.pas:226`, `DaofyAutomation.CallGraph.pas:228` | 只有排除前缀，没有 include/分类 |
| 差异对比 | 已支持 `callgraph_diff` | `automation_service.py:557`, `automation_service.py:598`, `automation_service.py:1504` | 当前比较键包含地址，重编译后容易产生噪音 |
| 错误态结构化输出 | 已修正，`status=err` 时仍解析 `data` | `automation_service.py:1630` | 还缺少统一错误码清单 |
| Delphi 端本地保护 | 已在 `HandleCallGraph` 层保留 `ReqId` | `DaofyAutomation.CallGraph.pas:196` | 仍需扩展更多诊断字段 |
| Win64 兼容边界 | 已验证真实项目 smoke | `StackTrace.pas:TStackTracer.ScanCallGraph`, `tests/test_stacktrace_callgraph.py`, `tests/test_stacktrace_callgraph_runtime.py` | Win64 进入共享扫描路径；QLangEditor Win64 callgraph 已返回非空调用边 |
| 增强用途入口 | 已支持 U1-U8 Python 侧初版 | `automation_service.py`, `tests/test_console_automation.py` | 路径输出和真实项目工作流仍需继续打磨 |

## 2. 目标

1. 让 `callgraph` 从“能查一条调用链”升级为“可用于审计、影响分析和回归定位”的稳定诊断能力。
2. 保持现有脚本兼容，默认 `cmd=callgraph` 行为不破坏已验证的 QLangEditor 用例。
3. 所有增强项都必须有 Python 协议测试、文档同步和至少一个真实项目验证路径。

## 3. 非目标

1. 本阶段不把 `StackTrace.pas` 中的 callgraph facade 做成完整反汇编器。
2. 本阶段不承诺完整覆盖虚方法、接口调用、事件回调和 RTTI 动态分发。
3. 本阶段不把 Win64 支持和间接调用扫描混入 P0/P1，避免影响当前 Win32 可用基线。

## 4. 阶段规划

### P0 - 输出稳定性与审计可用性

#### P0.1 `callgraph_diff` 增加比较策略

**状态**: 已实施。`callgraph_diff` 默认 `compare_by=name`，可显式传 `addr` 或 `full`；非法值在 Python 层失败，不发送 Delphi 请求。

**问题**: 当前 `_callgraph_edge_key()` 使用 `from/name/address + to/name/address`，同一源码重编译后地址变化会被误判为删除和新增。  
**方案**: 增加 `compare_by=name|addr|full`，默认 `name`；`full` 保留当前行为。  
**修改点**:

- `src/services/automation_service.py`: `_callgraph_edge_key(edge, compare_by)`、`_diff_callgraphs(..., compare_by)`、`callgraph_diff` 参数解析。
- `tests/test_console_automation.py`: 覆盖默认 name 比较、full 比较、非法参数报错。
- `docs/automate_test_guide.md`、`src/tool_docs.py`、automation resource 镜像同步。

**验收标准**:

- from/to 名称相同但地址不同，默认不产生 added/removed。
- `compare_by=full` 时保留现有地址敏感结果。
- 非法 `compare_by` 在 Python 层返回清晰错误，不发送 Delphi 请求。

#### P0.2 边去重和输出上限

**状态**: 已实施。当前在 `DaofyAutomation.CallGraph.pas` 输出层按 caller/callee 名称、地址和 `CallAddr` 去重，并按 `edge_limit` 截断；保留同一 caller/callee 的不同调用点。

**问题**: direct call 扫描可能产生重复边；大函数或框架入口可能返回过大 JSON。  
**方案**: 增加边去重和 `edge_limit`，响应包含 `truncated=true|false`、`edge_count`、`returned_count`。  
**修改点**:

- `tools/auto/DaofyAutomation.CallGraph.pas`: 在输出层按 caller/callee/name/address/callsite 去重。
- `tools/auto/DaofyAutomation.CallGraph.pas`: 解析 `edge_limit`，裁剪输出并补充 metadata。
- `src/services/automation_service.py`: 校验 `edge_limit` 范围，例如 `1..5000`。

**验收标准**:

- 同一 caller/callee 重复扫描结果只返回一次。
- 超过上限时结果可用且明确标记截断。
- 现有不传 `edge_limit` 的脚本行为兼容。

#### P0.3 补充调用点文件和行号

**状态**: 已实施。`TCallEdge` 已增加 `CallAddr`、`CallFile`、`CallLine`，direct-call 扫描保存 call 指令地址并用 MAP 行号表解析调用点；JSON 边输出 `call_addr`、`call_file`、`call_line`。

**问题**: 当前 JSON 主要描述 callee 的符号位置，缺少“调用发生在哪一行”，审计时定位成本高。  
**方案**: `TCallEdge` 增加 `CallAddr`、`CallFile`、`CallLine`，用 call 指令地址查 map 行号。  
**修改点**:

- `tools/stacktrace/StackTrace.pas`: 扫描 `$E8` 时保存 call 指令 RVA，并解析 callsite 行号。
- `CallChainToJSON`: 输出 `call_addr`、`call_file`、`call_line`。
- Python diff 键默认仍按名称比较，避免行号变化制造噪音。

**验收标准**:

- QLangEditor 中 `SaveIfModified` 的 callers 结果能给出调用点行号。
- 无行号信息时字段为空或 0，不影响旧客户端解析。

### P1 - 查询性能与路径分析

#### P1.1 建立调用边索引

**状态**: 已实施。`TStackTracer` 扫描后构建 `FCallerIndex` / `FCalleeIndex`，`GetCallChain` / `GetCallerChain` 的 BFS 通过索引取当前节点相关边，不再逐轮遍历全部 `FCallEdges`。QLangEditor Win32 Debug 实测 `SaveIfModified` callers 正常返回 3 条边，并带 `main.pas:586`、`main.pas:683`、`main.pas:719` 调用点。

**问题**: `GetCallChain` 和 `GetCallerChain` 查询时会遍历全部 `FCallEdges`，调用边变多后性能退化明显。  
**方案**: 扫描完成后建立两个索引：`caller_addr -> edges`、`callee_addr -> edges`。  
**修改点**:

- `tools/stacktrace/StackTrace.pas`: 在 `EnsureSymbols` 或 `ScanCallGraph` 后构建索引。
- 保留数组作为原始数据，索引用于 BFS。

**验收标准**:

- 同一目标的 callers/callees 查询结果与当前一致。
- 大项目重复查询耗时明显下降，至少记录一次 QLangEditor 实测耗时。

#### P1.2 增加 `callgraph_path`

**问题**: 审计常问“入口 A 是否能影响函数 B”，现有 callgraph 需要客户端手动过滤。  
**状态**: 已实施。新增 `cmd=callgraph_path`，输入 `source`、`target`、`max_depth`、`max_paths`，返回 `found`、`paths`、`path_count`、`max_paths`、`truncated`。Python 层会在发送前校验 `source`/`target` 和 `max_paths`。  
**修改点**:

- Delphi: `DaofyAutomation.CallGraph.pas` 注册 `callgraph_path`，复用已扫描调用边做 bounded BFS path search。
- Python: `automation_service.py` 增加请求构造、参数校验和响应 JSON 状态解析。
- Docs/tests: `docs/automate_test_guide.md`、automation resources、`src/tool_docs.py`、`src/server.py` 和目标测试已覆盖路径查询。

**验收标准**:

- `source=actNewProjectExecute`、`target=SaveIfModified` 这类查询能返回 `found` 和 `paths`。
- 找不到路径时返回 `found=false`，不是错误。
- `max_paths` 可限制结果数量。
- `tests/test_console_automation.py` 覆盖参数转发、状态解析和本地校验；`tests/test_stacktrace_callgraph.py` 覆盖 Delphi handler 注册和 paths JSON 序列化。

#### P1.3 include 过滤和边分类

**问题**: 现在只能按前缀排除框架符号，不能明确只看项目/第三方/系统边。  
**状态**: 已实施。增加 `include_prefixes`，并在响应中为每条边补充 `category=project|thirdparty|framework|system|unknown`，同时输出 `from_category`/`to_category`。  
**修改点**:

- Delphi: 扩展过滤函数，保留 `exclude_prefixes` 兼容；`category` 按 callee 分类，`from_category`/`to_category` 分别标注边两端。
- Python: `callgraph`、`callgraph_diff`、`callgraph_path`、`callgraph_impact` 均支持 list/string 两种 `include_prefixes` 入参。
- 文档: 协议说明列出 include 过滤和分类字段。

**验收标准**:

- `include_prefixes=["TMainForm."]` 只返回指定范围相关边。
- `project_only=true` 仍保持现有语义。
- 边 JSON 包含 `category`、`from_category`、`to_category`。

### P2 - 审计与自动化集成

#### P2.1 变更影响分析

**问题**: 有了调用图后，还需要把“改了哪些函数”映射为“哪些入口会受影响”。  
**状态**: 已实施初版。Python 层根据 changed file/line 或函数名调用 `callgraph(direction=callers)`，输出入口函数候选。  
**修改点**:

- `src/services/automation_service.py`: 已先做成 `callgraph_impact` 步骤。
- 后续可与 `delphi_project(action="ast")` 或 map 行号结合。

**验收标准**:

- 输入函数名时能返回 callers 摘要。
- 输入 file/line 时若无法解析函数，返回明确诊断，不猜测。

#### P2.2 黑盒失败报告附加调用图

**问题**: UI 自动化失败时，当前报告能说明失败步骤，但不能直接展示相关代码影响面。  
**状态**: 已实施。脚本启用 `callgraph_diagnostics=true` 且失败步骤带 `handler` / `entry` / `callgraph_target` 时，失败报告会附加 callgraph 摘要。  
**修改点**:

- 自动化报告生成逻辑增加可选 `diagnostics.callgraph`。
- 默认关闭，通过脚本元数据或步骤字段启用，避免额外开销。
- callgraph 查询在自动 `exit` 前执行；失败时只记录 warning，不覆盖原始 UI 自动化失败原因。

**验收标准**:

- 失败步骤的报告包含目标、方向、边数、截断状态。
- callgraph 失败不能覆盖原始 UI 自动化失败原因。
- `tests/test_console_automation.py` 覆盖成功诊断和诊断失败降级两条路径。

#### P2.3 baseline 保存和快照目录约束

**问题**: 当前 `callgraph_diff` 支持读取 baseline，但没有标准保存路径和命名。  
**状态**: 已实施。`callgraph_diff` 增加 `save_as`，Python 层保存当前 callgraph JSON，并把写入位置限制在 `snapshots_dir` 下；`baseline_path` 和用途层 `callgraph_*` 文件型 JSON 输入也会做 resolve 校验，不能越过 `snapshots_dir`。  
**修改点**:

- Python 层执行保存，避免 Delphi 端写文件。
- `save_as` 只能是相对路径，自动补 `.json` 后缀，保存成功返回相对路径和 `edge_count`。
- `baseline_path`/文件型 graph 或 impact 输入允许直接 JSON，也允许快照文件路径；文件路径 resolve 后必须仍在 `snapshots_dir` 内。
- 路径必须做 resolve 校验，禁止目录穿越。
- 测试覆盖合法 baseline 文件读取、baseline 越界拒绝，以及 `save_as` 空值、`../`、绝对路径拒绝。

**验收标准**:

- 保存成功返回相对路径和 edge_count。✅
- `..\`、绝对路径、空文件名均被拒绝。✅

### P3 - 研究项

#### P3.1 间接调用识别

**范围**: `FF /2`、虚方法、接口、事件回调、RTTI 动态分发。  
**风险**: 静态反汇编难以准确解析 Delphi 高层语义，误报和漏报都会高。  
**建议**: 单独建立 fixture 项目，用 AST/RTTI/运行时日志混合验证，不进入 P0/P1。

#### P3.2 Win64 支持

**范围**: PE32+、x64 relative call、PDB/map 差异、栈回溯差异。  
**风险**: 当前 QLangEditor 实测基线是 Win32，Win64 需要单独验证。  
**建议**: 作为独立兼容性里程碑，不和现有 Win32 callgraph 混改。当前阶段已移除 Win64 fail-closed guard：相关单元可 Win64 编译，运行期会进入共享扫描路径；无法解析时应返回 `map_not_loaded`、`text_section_not_found`、`entry_not_found`、`no_edges` 等结构化错误。

##### P3.2.1 当前边界

- `StackTrace.pas`、`DaofyAutomation.CallGraph.pas` 已验证 Win64 单文件编译通过。
- `TStackTracer.ScanCallGraph` 已移除 `SizeOf(Pointer) <> SizeOf(DWORD)` fail-closed guard，Win64 与 Win32 共用扫描路径。
- Python 协议层已覆盖 `status=err` 时仍解析结构化诊断到 `response.state`，包括旧版 `win64_not_supported` 响应。
- W64-1 已完成运行时地址模型预迁移：`TCallEdge`、索引、BFS 队列/visited/depth、`FindFuncAddr`、扫描赋值和 JSON 地址输出已改为 `NativeUInt` / pointer-width 格式化。
- W64-2 已完成 `.text` section 解析边界加固：`LoadTextRange` 显式接受 PE32 `$10B` / PE32+ `$20B` OptionalHeader magic，并继续通过 `FileHeader.SizeOfOptionalHeader` 定位 section table；测试侧已有固定 PE32/PE32+ fixture。
- W64-3 已完成 direct-call rel32 解析基础：`ScanCallGraph` 使用 `ResolveRelativeCallTarget(ACallSite, ARel32)` 统一计算 `$E8 rel32` 目标地址；测试侧已有高位 x64 地址的 forward/backward call fixture。
- 该边界现在依赖 MAPDATA v12 的 RVA 地址模型、`NativeUInt` 运行时地址和 PE32+ `.text` 解析共同保证 Win64 不再误用 Win32 `DWORD` 地址模型。

##### P3.2.2 改造目标

1. 在 Win64 下支持 direct relative call 调用边扫描，输出格式与 Win32 `callgraph` 兼容。
2. 保持 Win32 行为和性能不回退。
3. 在无法解析 Win64 map 或 `.text` 时继续返回结构化错误，不崩溃、不误报成功。
4. 为 Win32/Win64 共用符号解析、地址格式和 JSON 输出建立统一测试。

##### P3.2.3 技术方案

- **地址模型统一**: 将 callgraph 内部地址字段从 `DWORD` 迁移为 `NativeUInt`，JSON 地址输出改为按指针宽度格式化；保留旧字段名 `from_addr` / `to_addr`。
- **PE32+ `.text` 解析**: `LoadTextRange` 明确区分 PE32/PE32+，读取 section table 时不依赖 Win32 optional header 布局假设。
- **x64 direct call 扫描**: 继续识别 opcode `$E8 rel32`，但用 `Int64`/`NativeInt` 计算目标地址，避免 64 位截断。
- **符号匹配**: `ResolveSymbolStart`、`FindFuncAddr`、BFS 队列和 visited 集合统一改为 `NativeUInt`。
- **错误语义**: Win64 不再默认返回 `win64_not_supported`；正常 Win64 扫描失败应细分为 `text_section_not_found`、`map_not_loaded`、`entry_not_found`、`no_edges` 等既有错误码。
- **兼容层**: `TCallEdge` 如需保留 `DWORD` 字段，应新增 `NativeUInt` 字段并逐步迁移；优先避免破坏 `DaofyAutomation.CallGraph.pas` 现有 uses。

##### P3.2.3.1 地址类型审计清单

Win64 支持前必须成组处理以下运行时地址字段，避免只把局部 helper 改成 `NativeUInt` 后仍在其它路径截断：

- ✅ `StackTrace.pas:TCallEdge.CallerAddr/CalleeAddr/CallAddr` 已从 `DWORD` 迁移为 `NativeUInt`。
- ✅ `StackTrace.pas:TStackTracer.TEdgeIndex`、`FindFuncAddr`、`AddEdgeIndex`、`GetCallChain`、`GetCallerChain` 中的索引 key、队列、visited、depth 字典已跟随 `TCallEdge` 地址字段统一为 `NativeUInt`。
- ✅ `StackTrace.pas:TStackTracer.ScanCallGraph` 中 `DWORD(LCallerStart)`、`DWORD(LCalleeStart)`、`DWORD(LCallSite)` 截断点已移除；`SizeOf(Pointer) <> SizeOf(DWORD)` fail-closed guard 也已移除，Win64 会进入扫描路径。
- ✅ `StackTrace.pas:TStackTracer.CallChainToJSON` 和 `DaofyAutomation.CallGraph.pas:EdgeToJSON` 已使用 pointer-width 地址格式化 helper：Win32 输出 8 位十六进制，Win64 输出 16 位十六进制。
- ✅ `DaofyAutomation.CallGraph.pas:PathHasAddr` 与 `TCallEdge` 字段现已同为 `NativeUInt` 模型。

以下字段不要在 W64-1 中盲目改成 `NativeUInt`，应保留或另列专项验证：

- `StackTrace.pas` 的 `TMapSymbol.Addr`、`TLineInfo.Addr`、`TSymbolEntry.Addr`、`TLineEntry.Addr`、`TModuleSymbolTable.NameCache` 已迁移为 `UInt64`，MAPDATA 资源格式提升到 v12。
- MAPDATA v12 统一使用 `WriteVarInt` / `ReadVarInt` 名称承载 ZigZag `Int64` varint；地址字段在解析期归一化为模块 RVA，读写为非负 Int64 varint 后存入 `UInt64`。旧 MAPDATA 资源不再兼容，依赖方需要重新编译并重新嵌入资源。
- `ResolveSourceLine` 的 `LMapOffset` 已迁移为 `UInt64`，运行时 VA 转 MAPDATA RVA 后可直接查询 64 位行号表。
- Windows API 参数中的 `DWORD`、资源大小、`GetCurrentThreadId` 返回值等不是调用图地址模型，不属于 W64-1 截断修复。
- `TStackSnapshot.ThreadId` 当前为 `Cardinal`，语义上可改为 Delphi RTL 的 `TThreadID`。RTL 定义为 `MSWINDOWS: LongWord`、`POSIX: NativeUInt`；它不是 callgraph 地址字段，可作为语义清理单独处理。

##### P3.2.3.2 W64-4 真实 smoke 前置条件

W64-1 到 W64-3、主模块 preferred-base helper，以及 MAPDATA v12 RVA 地址模型已完成：运行时地址容器、PE32+ `.text` 定位、`$E8 rel32` 目标地址计算、`FModuleBase`/`FPreferredBase` 缓存、`MapAddrToRuntimeAddr` / `RuntimeAddrToMapAddr` 双向转换，`ParseMapFile` 的 `UInt64` segment/publics/line-number 解析，以及 `TMapSymbol` / `TLineInfo` / `TSymbolEntry` / `TLineEntry` 的 64 位存储都已经落地。真实 Win64 MSBuild `.map` 样本已确认 `.text` section base 是 `0000000140001000` 这类 preferred-base VA，public symbol 是 segment-local offset；解析期必须通过目标 EXE 的 PE PreferredBase 把 segment VA 归一化成 section RVA，再与 public offset 合成模块 RVA。MAPDATA v12 承载该 RVA 形态，运行期不再猜测 VA/RVA。`ScanCallGraph` 的 Win64 fail-closed guard 已移除，真实 smoke 前置条件收敛为：

- 主模块地址转换不得回退到 `PreferredImageBase=$00400000` 常量公式。`EnumerateFunctions`、`FindSymbolAddress`、`GetFunctionExtent`、`GetFrameSnapshot`、`ResolveFromMap`、`ResolveSourceLine` 和 `StackInfoStringProc` 已迁移到统一 helper；旧的私有 `FormatStackFrame` 死代码已删除。后续改动必须保留对应静态测试，防止重新出现 `FModuleBase + (... - PreferredImageBase)` 这类分散公式。
- 必须用最小 Win64 GUI smoke 验证 `EnsureSymbols`、`.text` 范围、符号二分、行号定位和 JSON 地址输出能在真实 PE32+ 项目上连通。
- 旧 MAPDATA 资源会被 v12 读取器拒绝；迁移验证必须包含重新编译/重新嵌入资源，不能拿旧 exe 直接测试。

##### P3.2.4 子任务

| 阶段 | 任务 | 验收标准 |
|------|------|----------|
| W64-1 | 重构 `TCallEdge`、索引、BFS、扫描赋值和 JSON 地址格式化为 `NativeUInt` 模型 | 已完成；Win32/Win64 单文件编译通过，静态测试锁定无 `DWORD(...)` 运行时地址截断 |
| W64-2 | 增加 PE32+ `.text` 解析测试 | 已完成；固定 PE32/PE32+ fixture 能解析出 `.text` 起止范围，源码守卫锁定 `SizeOfOptionalHeader` 定位 section table |
| W64-3 | 增加 x64 `$E8 rel32` 扫描 fixture | 已完成；构造的高位 x64 forward/backward `$E8 rel32` call 指令能解析到正确目标地址，源码守卫锁定扫描循环使用统一 helper |
| W64-4 | 启用真实 Win64 smoke | 已完成；最小 Win64 console smoke 在 `.map` fallback 和 MAPDATA overlay 嵌入路径均返回 `status=ok`，覆盖 `SmokeEntry -> SmokeMiddle -> SmokeLeaf`；新增 `/DYNAMICBASE` 自动 smoke，确认运行时 `ModuleBase != PreferredBase` 时同一调用边仍可解析 |
| W64-5 | QLangEditor 或等价项目 Win64 回归 | 已完成；QLangEditor Win64 Debug 编译通过，`automate_delphi(gui)` 返回非空调用边：`SaveIfModified` callers=3，`actNewProjectExecute` callees=40，耗时 2.34s |

##### P3.2.5 测试要求

- Python: 保留旧版 `win64_not_supported` err-data 解析兼容测试，同时新增源码守卫确认 `ScanCallGraph` 不再包含 Win64 fail-closed guard；真实 smoke 后补 Win64 成功/明确空图测试。
- Delphi 静态: `StackTrace.pas` / `DaofyAutomation.CallGraph.pas` 必须 Win32 和 Win64 单文件编译通过。
- Fixture: 增加不依赖本机 Delphi 的 PE/map/call instruction 解析测试，覆盖 32/64 位地址。
- 真实项目: 在有 Delphi Win64 环境时运行一个最小 callgraph demo，再运行 QLangEditor 或同等复杂项目 smoke。

##### P3.2.6 回滚策略

- 如果 Win64 扫描引入误报或崩溃，保留编译兼容并恢复 `win64_not_supported` fail-closed 边界。
- 如果地址类型迁移影响 Win32，先恢复 `TCallEdge` 对外字段，再把 `NativeUInt` 迁移限制在内部索引结构。
- 如果 PE32+ map 解析不稳定，Win64 仅开放 `ResolveAddr`/符号查询，不开放调用边扫描。

## 5. 增强用途规划

本节记录 callgraph 增强后要支持的上层用途。原则是：每个用途都必须能落到明确输入、输出、测试和失败语义，避免只停留在“展示调用图”。

| 用途 | 目标用户 | 输入 | 输出 | 依赖能力 | 验收标准 |
|------|----------|------|------|----------|----------|
| U1 变更影响分析 | 代码审计 / PR review | changed function、file/line、git diff 摘要 | 受影响入口函数、调用路径、风险分级 | P0.3、P1.1、P1.2、P2.1 | 给定 `SaveIfModified` 能列出上游入口候选；无法解析 file/line 时返回明确诊断 |
| U2 回归测试选择 | 黑盒自动化 / CI | 变更函数列表、测试脚本到 handler 的映射 | 建议执行的黑盒脚本集合和理由 | U1、P1.2、P2.1 | 修改保存链路时能命中 dirty-close / save 相关脚本，不泛化成全量测试 |
| U3 失败报告增强 | 黑盒自动化 | 失败步骤、handler、当前 UI state | `diagnostics.callgraph` 摘要、相关调用边、截断状态 | P0.2、P2.2 | callgraph 失败不覆盖原始失败原因；成功时报告包含目标、方向、边数 |
| U4 调用图基线回归 | 发布 / 重构评审 | baseline JSON、当前 callgraph | added/removed/unchanged 边、稳定比较策略、快照路径 | P0.1、P2.3 | 同源码重编译默认不因地址变化产生 added/removed 噪音 |
| U5 架构边界检查 | 代码审计 | include/exclude/category 规则 | 违反边界的调用边，例如 UI 直接依赖底层实现 | P1.3 | `project_only`、`include_prefixes`、`exclude_prefixes` 可组合，违规边可复现 |
| U6 重构安全检查 | 重构辅助 | 待改函数、目标替换函数、最大深度 | 受影响调用者、路径、无法覆盖的动态调用提示 | P1.1、P1.2、P3.1 | 重命名/拆分函数前能列出直接和间接受影响调用者 |
| U7 死代码和孤岛候选 | 维护清理 | 全量符号表、入口函数集合 | 无 caller 的候选函数、只被测试或框架调用的候选 | P1.1、P1.3 | 输出必须标记“候选”而非自动判死，避免事件/RTTI 漏报误导删除 |
| U8 异常栈扩展解释 | 运行时诊断 | exception stack、崩溃函数、callgraph cache | 崩溃函数的上游入口和下游影响摘要 | StackTrace P2、P1.2、P2.2 | exception.log 中可选附带调用图摘要；缺失 callgraph 时异常日志照常输出 |

### 5.1 U1 变更影响分析

优先实现 `callgraph_impact` 作为 Python 层辅助命令，不要求 Delphi 端新增写文件能力。

- 输入：`functions`、`file` + `line`、或后续由 git diff 提供的 changed symbols。
- 处理：对每个函数执行 `direction=callers`，结合 `max_depth` 和 `project_only` 输出上游入口候选。
- 输出：`targets`、`entries`、`paths`、`unresolved`、`warnings`。
- 失败语义：无法从 file/line 解析函数时返回 `unresolved`，不猜测函数名。
- 测试：Python 单元测试覆盖函数名输入、file/line 解析、file/line 无法解析、callgraph 返回 `entry_not_found`。
- 当前初版：已支持 `functions`/`targets`/`target` 和 `file`+`line`/`locations` 输入，批量发送 `callgraph direction=callers`，聚合 `entries`、`unresolved`、`warnings` 和 `resolved_locations`。

### 5.2 U2 回归测试选择

在 U1 基础上建立轻量映射：黑盒脚本可声明 `handler` / `entry` / `tags`，影响分析根据调用路径推荐脚本。

- 输入：变更函数列表、脚本元数据、可选 `max_scripts`。
- 输出：推荐脚本、命中路径、置信度、未覆盖函数。
- 默认策略：宁可返回“需要人工确认”，不自动把未知变更归入全量高置信。
- 验证：以 QLangEditor 保存/关闭链路为 fixture，修改 `SaveIfModified` 时必须推荐相关 dirty-close/save 脚本。
- 当前初版：已支持 `cmd=callgraph_select_tests`，基于 `impact` 和测试 `handler`/`tags` 元数据输出 `selected`、`covered_targets`、`uncovered_targets`。

### 5.3 U3 失败报告增强

黑盒失败报告中新增可选 `diagnostics.callgraph`，默认关闭，通过脚本参数启用。

- 输入：失败步骤的 `handler`、`target` 或显式 `callgraph_target`。
- 输出：调用图摘要，不输出过大的完整图；大图通过 `edge_limit` 截断。
- 约束：callgraph 诊断失败只能作为附加 warning，不能改变主步骤的失败原因。
- 验证：构造一个失败 UI 步骤和成功 callgraph 响应，报告中必须同时保留 UI 失败和调用图摘要。
- 当前初版：已支持 `cmd=callgraph_failure_diag`，从失败步骤和 callgraph state 生成 `diagnostics.callgraph` 摘要。

### 5.4 U4 调用图基线回归

把 `callgraph_diff` 用作重构/发布前后的结构变化检查。

- 输入：baseline JSON 或 `baseline_path` 快照文件、当前目标、`compare_by=name|addr|full`、可选 `save_as`。
- 输出：added/removed/unchanged、比较策略、保存路径、边数。
- 路径安全：保存只允许写入 `snapshots_dir`，禁止绝对路径和目录穿越。
- 验证：同名不同地址默认不产生噪音，`compare_by=full` 保留旧地址敏感行为。
- 当前初版：`callgraph_diff` 支持 `save_as`，保存路径被限制在 `snapshots_dir` 下；读取型快照路径也经过同一目录边界校验。

### 5.5 U5 架构边界检查

利用 include/exclude/category 规则把调用图用于边界审计。

- 输入：规则集，例如 `ui -> service allowed`、`ui -> storage forbidden`。
- 输出：违规调用边、调用路径、所属分类、建议入口。
- 分类来源：先用命名前缀和 map symbol，后续再结合项目 KB / AST。
- 验证：固定 fixture 中构造一条 UI 直接调用底层实现的边，必须被报告为违规。
- 当前初版：已支持 `cmd=callgraph_boundary_check`，按 `from_prefix` / `to_prefix` 的 `forbid` 规则输出 violations。

### 5.6 U6 重构安全检查

面向改名、抽取函数、移动模块前的风险扫描。

- 输入：待改函数、最大深度、include/exclude、是否包含框架边。
- 输出：直接调用者、间接调用者、下游依赖、动态调用盲区提示。
- 约束：对虚方法、事件、RTTI 调用必须标注“不完整覆盖”，不能宣称全量。
- 验证：对同一目标函数，Win32 现有结果必须和增强前兼容。
- 当前初版：已支持 `cmd=callgraph_refactor_check`，基于 impact 输出受影响调用者和静态图盲区 warnings。

### 5.7 U7 死代码和孤岛候选

使用全量 symbol 和 caller 索引发现候选，不做自动删除建议。

- 输入：入口函数集合、排除前缀、可选测试入口集合。
- 输出：无 caller 候选、只被测试调用候选、孤岛子图。
- 风险提示：事件处理器、RTTI、虚方法、外部导出可能漏边，结果只能作为候选。
- 验证：候选输出必须带 `confidence` 和 `reason`，禁止只有函数名列表。
- 当前初版：已支持 `cmd=callgraph_orphan_candidates`，输出低置信候选并强制附带不可自动删除 warnings。

### 5.8 U8 异常栈扩展解释

把 StackTrace 异常栈和 callgraph 结合，帮助从崩溃点回看入口、向下看影响。

- 输入：exception.log 中的崩溃函数或栈顶函数。
- 输出：上游入口摘要、下游关键调用、是否截断、callgraph 错误码。
- 默认：异常日志能力优先，callgraph 缺失时不影响异常报告生成。
- 验证：run_verify smoke 中即使 callgraph 不可用，仍能输出原始异常栈。
- 当前初版：已支持 `cmd=callgraph_explain_exception`，根据 stack 顶帧和 callgraph/impact 输出上下游摘要。

## 6. 推荐实施顺序

| 里程碑 | 内容 | 预计收益 | 风险 |
|--------|------|----------|------|
| A | P0.1 + P0.2 | 差异对比稳定，输出不会爆量 | 低 |
| B | P0.3 | 审计定位效率明显提升 | 中 |
| C | P1.1 + P1.2 | 支持影响路径分析，查询更快 | 中 |
| D | P1.3 + P2.1 | 从调用图升级为变更影响分析 | 中 |
| E | P2.2 + P2.3 | 接入黑盒报告和快照流程 | 中 |
| U | U1-U8 Python 侧初版 | 进入审计、回归选择、失败诊断、边界检查和异常解释工作流 | 中 |
| W | P3.2 | Win64 callgraph 从 fail-closed 升级为可扫描 | 高 |
| R | P3.1 | 扩展间接调用覆盖面 | 高 |

## 7. 验证计划

### Python 协议测试

```powershell
$env:PYTHONIOENCODING='utf-8'
pytest tests\test_console_automation.py -q -p no:cacheprovider
```

### 文档一致性测试

```powershell
$env:PYTHONIOENCODING='utf-8'
pytest tests\test_doc_consistency.py -q -p no:cacheprovider
```

### 真实项目验证

使用 `C:\user\qlang\editor` 作为固定回归项目：

1. 编译 `qlangeditor.dproj`。
2. 查询 `SaveIfModified` 的 callers，确认返回项目调用者和调用点。
3. 查询 `actNewProjectExecute` 的 callees，确认 `project_only` 和过滤参数生效。
4. 用保存的 baseline 执行 `callgraph_diff`，确认 added/removed/unchanged 稳定。

### Win64 兼容验证

当前阶段验证目标是 Win64 进入共享扫描路径，并保持结构化错误解析：

```powershell
$env:PYTHONIOENCODING='utf-8'
pytest tests\test_console_automation.py tests\test_stacktrace_callgraph.py -q -p no:cacheprovider
```

有 Delphi Win64 环境时，还需执行：

- `StackTrace.pas` / `DaofyAutomation.CallGraph.pas` 的 Win64 单文件编译。
- 最小 Win64 callgraph demo 必须不再返回 `win64_not_supported`，至少返回 `status=ok` 或明确的 `map_not_loaded` / `text_section_not_found` / `entry_not_found` / `no_edges`。
- 2026-07-04 实测：最小 Win64 console smoke 在 `.map` fallback 和 MAPDATA overlay 嵌入路径均返回 `OK` JSON，包含 `SmokeEntry -> SmokeMiddle -> SmokeLeaf` direct call 边；嵌入后 PE 头保持 `MZ`，overlay footer 为 `MAPOVL01`。
- 2026-07-04 新增自动测试：`tests/test_stacktrace_callgraph_runtime.py` 编译 Win64 `/DYNAMICBASE` console smoke，磁盘 PE 头确认 `IMAGE_DLLCHARACTERISTICS_DYNAMIC_BASE`，运行时确认 `ModuleBase != PreferredBase` 后验证 `SmokeEntry -> SmokeMiddle -> SmokeLeaf` 调用边。
- 2026-07-04 ASLR 路径修正：`GetModulePreferredBase(hModule)` 不再从已映射模块内存头读取 `OptionalHeader.ImageBase`，而是通过 `GetModuleFileName` 定位磁盘 PE，再复用 `GetPEFilePreferredBase`。运行期映射头在 ASLR 后不能作为 PreferredBase 事实来源。
- 2026-07-04 符号反查修正：`BuildSymbolNameCache` 和多模块 `NameCache` 对重复符号名保留首个地址，不再因 MAP 中同名符号触发 `EListError: Duplicates not allowed`；ASLR smoke 已恢复覆盖 `FindSymbolAddress`。
- 2026-07-04 Win64 GUI smoke：最小 VCL GUI 工程以 `automate_delphi(gui)` 查询 `SmokeEntry` callees，返回 `SmokeMain.SmokeEntry -> SmokeMain.SmokeMiddle` 和 `SmokeMain.SmokeMiddle -> SmokeMain.SmokeLeaf` 两条边，地址为 16 位十六进制，行号为 `SmokeMain.pas:36` / `SmokeMain.pas:31`，报告耗时 1.64s。
- 2026-07-04 QLangEditor 回归：Win32 Debug 编译通过；`SaveIfModified` callers 返回 3 条边，`actNewProjectExecute` callees 返回 37 条边，报告耗时 2.24s。Win64 Debug 通过补充 `DCC_Namespace=Winapi;System.Win;Data.Win;Datasnap.Win;Web.Win;Soap.Win;Xml.Win;Bde;$(DCC_Namespace)` 和移除临时 EBP asm 调试块后编译通过；`SaveIfModified` callers 返回 3 条边，`actNewProjectExecute` callees 返回 40 条边，报告耗时 2.34s。
- 2026-07-04 全量 Python 回归：`pytest -q -p no:cacheprovider` 通过，结果为 1093 passed、77 skipped、33 subtests passed。期间补齐 `src/resources/coding-rules/kb-search.md` 分片，并将资源测试断言切到当前中文标题，避免恢复中英文双标题。

## 8. 风险与回滚

| 风险 | 控制方式 | 回滚方式 |
|------|----------|----------|
| diff 默认比较策略改变 | 明确新增 `compare_by=full` 保留旧行为 | 将默认值改回 `full` |
| 输出字段增多影响旧客户端 | 只追加字段，不删除旧字段 | 关闭新增 metadata 输出或保留空值 |
| callsite 行号解析不完整 | 缺失时返回 0/空，不作为错误 | 暂时只输出 `call_addr` |
| 索引实现引入不一致 | 保留原数组，测试对比索引前后结果 | 查询逻辑退回遍历数组 |
| path 查询过深导致耗时 | 限制 `max_depth` 和 `max_paths` | Python 层拒绝过大参数 |
| Win64 扫描误报或崩溃 | 保留源码守卫、编译验证和真实 smoke | 临时恢复 `win64_not_supported` 结构化错误 |
| 增强用途误导自动决策 | 输出置信度、原因和 unresolved，不自动删除或跳过测试 | 关闭对应用途命令，保留基础 callgraph |

## 9. 完成定义

P0 完成后应满足：

- `callgraph_diff` 默认适合源码审计，不因地址漂移产生大量误报。
- `callgraph` 输出有去重、截断标记和调用点定位。
- QLangEditor 真实项目验证通过。
- Python 测试和文档一致性测试通过。

P1 完成后应满足：

- callers/callees 查询使用索引。
- 能回答 source 到 target 的路径问题。
- 过滤能力可表达 include、exclude 和项目分类。

P2 完成后应满足：

- 能从函数变更推导受影响入口候选。
- 黑盒失败报告可选附加 callgraph 摘要。
- baseline 保存和 diff 流程有标准快照约束。

增强用途里程碑完成后应满足：

- U1-U8 至少各有一个 Python 单元测试或复合 fixture 验证。
- 所有用途输出都包含 `warnings` 或 `unresolved` 语义，不把不完整图当作确定事实。
- 用途层失败不影响基础 `callgraph`、`callgraph_diff` 和 UI 自动化主流程。

Win64 里程碑完成后应满足：

- Win64 不再默认返回 `win64_not_supported`。
- Win32/Win64 地址模型共用 `NativeUInt`，不存在地址截断。
- 至少一个真实 Win64 GUI 项目 callgraph smoke 通过：2026-07-04 QLangEditor Win64 已返回 3/40 条非空调用边；最小 VCL GUI smoke 另返回 2 条调用边。
- Win32 QLangEditor 回归仍通过：2026-07-04 `SaveIfModified` callers=3，`actNewProjectExecute` callees=37。
