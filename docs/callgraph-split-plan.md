# Callgraph 拆分实施计划

**计划状态**: 已实施
**审计日期**: 2026-07-03
**适用范围**: `automate_delphi(gui)` 新增 `callgraph` 能力、Delphi 自动化内联单元、StackTrace 诊断单元、文档和测试。

## P0.1 需求澄清

| 检查项 | 内容 |
|--------|------|
| 显式需求 | 将 `callgraph` 从 `DaofyAutomation.Base.pas` 拆分为可选诊断能力，并按 Daofy 规范生成可审计计划。 |
| 隐式需求 | 不能让普通 VCL/FMX 自动化用户因为未启用 callgraph 而新增编译依赖；`callgraph` 可用时必须返回可靠错误语义和可验证数据。 |
| 边界范围 | 本计划只拆分和修正 callgraph 诊断能力，不重写 UIA、RTTI、截图、msgscan/dlgscan 等既有自动化命令。 |
| 输入/输出 | 输入为 GUI 脚本步骤 `{ "cmd": "callgraph", "target": "<函数名>", "max_depth": N }`；输出为 JSON 图结构或明确错误。 |
| 实现选择 | 主实现统一为 `tools/stacktrace/StackTrace.pas`；独立 `tools/stacktrace/StackTracer.pas` 兼容壳已移除。 |
| 性能需求 | 首次扫描 `.text` 允许一次性成本，但单次 `callgraph` 目标查询应复用缓存；典型 GUI 程序首次扫描目标耗时控制在 2 秒内，后续查询控制在 200 ms 内。 |
| 安全需求 | 不读取用户指定任意路径；默认只读取目标 exe 同名 `.map`。不执行外部命令，不写目标项目源码。 |
| 文档需求 | 同步 `tool_docs.py`、automation resource、`docs/automate_test_guide.md`、教程示例和发布说明。 |

## P0.2 影响分析

| 文件/区域 | 实施前证据 | 修改点 | 风险 |
|-----------|----------|--------|------|
| `tools/auto/DaofyAutomation.Base.pas` | 实施前 line 19 无条件 `uses StackTracer`；line 704 分发 `callgraph` | 已移除 `StackTracer` 依赖和 `callgraph` 分支，恢复 Base 只承载基础协议 | 需要确保普通自动化命令行为不变 |
| `tools/stacktrace/StackTrace.pas` | `TStackTracer.ScanCallGraph` / `GetCallChain` / `GetCallerChain` | 作为统一诊断主单元，承载异常报告、tokenized MAPDATA 和 callgraph facade | Delphi PE/map 解析存在 Win32/Win64 差异 |
| 新增 `tools/auto/DaofyAutomation.CallGraph.pas` | 实施前不存在 | 已新建可选命令单元，注册 `callgraph` 处理器并调用 `StackTrace.TStackTracer` | 需要设计最小侵入的命令扩展接口 |
| `src/services/automation_service.py` | line 1303 构造步骤请求；line 1456 反序列化 `callgraph` data | 透传 `max_depth`，校验范围，保留 JSON state 解析 | 协议字段变化需要测试 |
| `src/tool_docs.py` | line 847/857/908 文档声明 `callgraph` | 明确 `callgraph` 需要启用可选 Delphi 单元和 Detailed map | 避免误导普通 GUI 用户 |
| `src/server.py` prepare | line 1481 返回 `tools/auto` + `tools/stacktrace` | prepare 输出应说明 callgraph 是可选能力；普通自动化不强制 stacktrace | 兼容已注册路径 |
| `src/tools/compile_project.py` | run_verify 使用 `tools/stacktrace/StackTrace.pas`；callgraph 也通过 `StackTrace.pas` 暴露 `TStackTracer` facade | 保持 run_verify 诊断能力与 callgraph 查询能力同属 StackTrace 主单元 | 独立 `StackTracer.pas` 已不再发布 |
| docs/resources/tutorial | 多处只写 `tools/auto` | 增加可选 callgraph 接入方式：引用 `DaofyAutomation.CallGraph` + `tools/stacktrace` | 文档和资源镜像需同步 |
| tests | 当前无 `callgraph` 覆盖 | 添加 Python 协议测试、文档一致性测试、map parser fixture 测试 | Delphi 实机编译测试可能依赖环境 |

## P0.2.1 源码核验

- `tools/auto/DaofyAutomation.Base.pas:19` 实施前把 `StackTracer` 放在 interface `uses`，导致依赖传播到所有 VCL/FMX 自动化项目。
- `tools/auto/DaofyAutomation.Base.pas:704` 实施前在基础命令分发里处理 `callgraph`，不具备可选启用边界。
- 旧 `tools/stacktrace/StackTracer.pas` 曾记录扫描边地址并在线性 BFS 中直接比较入口地址；P0b 后这部分已迁移到 `StackTrace.pas` 的 `TStackTracer` facade。
- `src/services/automation_service.py:1303` 到 `1414` 没有 `callgraph` 专用请求构造分支，`max_depth` 未透传。
- `src/tool_docs.py:908` 对外声明 `max_depth` 可控，当前实现不满足。
- `src/resources/automation/reference/inline-unit.md:38` 实施前只建议加入 `tools\auto`，和当时的 `StackTracer` 依赖不一致。

## P0.3 方案设计

### 整体思路

将 `callgraph` 从基础自动化协议中拆成可选诊断扩展：普通项目只引用 `Vcl.DaofyAutomation` / `Fmx.DaofyAutomation`；需要调用图时额外引用 `DaofyAutomation.CallGraph` 和 `StackTrace`，并在文档和工具提示里显式声明前置条件。

### 技术方案

1. **命令扩展边界**
   - 在 `DaofyAutomation.Base.pas` 增加轻量扩展注册点，例如 `RegisterCommandHandler(Cmd, Handler)` 或虚方法 `TryHandleExtraCommand`。
   - Base 不直接 `uses StackTrace` / `StackTracer`，只在命令未知前调用扩展 hook。
   - 新单元 `DaofyAutomation.CallGraph.pas` 在 initialization 注册 `callgraph` 处理器。

2. **可选 Delphi 单元**
   - 新建 `tools/auto/DaofyAutomation.CallGraph.pas`。
   - 该单元 `uses StackTrace`，负责读取 `target/max_depth`、调用 `TStackTracer.GetCallChain`、返回统一 JSON。
   - 普通 VCL/FMX 单元不依赖 callgraph。

3. **StackTrace callgraph facade 修正**
   - 统一地址模型为 RVA：map entries、E8 target、caller/callee、BFS 队列全部用 RVA。
   - `LoadMap` 支持 Detailed map 的 segment:offset，允许 base/offset 为 0。
   - `ScanCallGraph` 只记录目标在 `.text` 范围内的 near call，避免把数据中的 `$E8` 或外部 thunk 当作内部调用。
   - `GetCallChain` 返回结构化错误：`map_missing`、`entry_not_found`、`no_edges`、`scan_failed`。

4. **Python 协议层**
   - 在 `automation_service.py` 添加 `cmd == "callgraph"` 分支，透传 `target` 和 `max_depth`。
   - `max_depth` 限制为 `0..20`，非法值直接在 Python 端返回错误，避免 Delphi 端过度扫描。
   - 保留 line 1456 的 JSON state 反序列化。

5. **文档与工具提示**
   - `tool_docs.py` 中将 callgraph 标记为可选诊断命令，说明需要 `DaofyAutomation.CallGraph` 和 Detailed `.map`。
   - `inline-unit.md` / `base.md` / `docs/automate_test_guide.md` 增加可选接入块。
   - 示例 dpr/dproj 增加单独的 callgraph 示例，不污染基础 AutoTest 示例。

6. **测试策略**
   - Python 单元测试：验证 `max_depth` 透传、范围校验、返回 `state` 解析。
   - Delphi 静态/fixture 测试：用固定 map 文本验证 `LoadMap` 对 segment:offset 的解析。
   - 文档一致性测试：基础接入文档不得要求普通项目引用 `StackTracer`；callgraph 文档必须声明可选依赖。
   - 可用环境下运行一个 VCL demo：普通自动化编译通过；额外引用 callgraph 后 `callgraph` 返回非空或明确错误。

### 子任务清单

| 阶段 | 任务 | 验收标准 |
|------|------|----------|
| T1 | 在 Base 中加入命令扩展 hook，移除 `StackTracer` uses 和内联 `callgraph` 分支 | `tools/auto/DaofyAutomation.Base.pas` 不再出现 `StackTracer`；普通自动化命令路径不变 |
| T2 | 新增 `DaofyAutomation.CallGraph.pas` | 只在该单元依赖 `StackTrace`；引用该单元后 `callgraph` 可分发 |
| T3 | 修正 `StackTrace.pas` 中的 callgraph facade 地址模型和 map 解析 | fixture 测试覆盖入口函数、内部调用边、空图、入口不存在 |
| T4 | 修正 Python 请求构造和输入校验 | `max_depth` 能透传；非法范围返回清晰错误 |
| T5 | 同步文档、资源、工具提示和示例 | 文档说明普通接入与 callgraph 可选接入分离 |
| T6 | 验证与回归 | Python 目标测试通过；可用 Delphi 环境下普通 demo 和 callgraph demo 均编译验证 |

### 验证命令

```powershell
$env:PYTHONIOENCODING='utf-8'
pytest tests\test_console_automation.py tests\test_doc_consistency.py tests\test_mcp_resources.py -q -p no:cacheprovider
```

如修改 Delphi 单元：

```python
delphi_project(action="compile", project_path="<demo>.dproj")
delphi_project(action="compile", project_path="<callgraph-demo>.dproj", run_verify=True)
```

### 回滚方案

- T1/T2 失败：恢复 `DaofyAutomation.Base.pas` 备份，移除新 `DaofyAutomation.CallGraph.pas`。
- T3 失败：保留拆分边界，但禁用 `callgraph` 注册，文档标记为实验能力不可用。
- T4/T5 失败：回滚 Python 协议和文档改动，不影响普通 GUI 自动化。

## P0.4 方案自审

| # | 审查项 | 结论 |
|---|--------|------|
| 1 | 需求覆盖 | 通过。覆盖拆分、协议、Delphi 实现、文档、测试。 |
| 2 | 源码核验 | 通过。计划基于具体文件和行号。 |
| 3 | 现有模式匹配 | 通过。沿用 `tools/auto` 分层和 `automate_delphi` JSON 协议。 |
| 4 | 连锁反应 | 通过。明确普通自动化与可选诊断依赖的边界。 |
| 5 | 风险可控 | 通过。PE/map 解析风险被收束到 `StackTrace.pas` 和 fixture 测试。 |
| 6 | 接口兼容 | 通过。普通命令兼容；`callgraph` 仍保留原 cmd 名。 |
| 7 | 边界处理 | 通过。包含 map 缺失、入口不存在、非法 depth、空图。 |
| 8 | 安全合规 | 通过。不引入任意路径读取或外部命令执行。 |
| 9 | 性能达标 | 通过。定义首次扫描和后续查询预算，并要求缓存复用。 |
| 10 | 可观测完备 | 通过。要求结构化错误码和 JSON state。 |
| 11 | 文档同步 | 通过。列明所有需同步文档和示例。 |
| 12 | 测试完备 | 通过。列明 Python、fixture、文档一致性和 Delphi demo 验证。 |
| 13 | 技术债务可控 | 通过。拆分后 callgraph 只通过 `StackTrace.pas` 独立硬化，不污染基础协议。 |
| 14 | 子任务合理 | 通过。每个阶段可独立验证和回滚。 |

### 审计结论

**通过**。本计划满足 P0.4 要求，已完成 P0b 迁移：`StackTrace.pas` 为统一主实现，独立 `StackTracer.pas` 兼容壳已移除。

