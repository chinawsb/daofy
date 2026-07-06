# Callgraph 语义增强路线图（基于 daudit）

**计划状态**: Roadmap  
**计划日期**: 2026-07-04  
**适用范围**: `callgraph` / `callgraph_impact` / `callgraph_select_tests` / `callgraph_boundary_check` / `callgraph_refactor_check` / `callgraph_orphan_candidates` / `callgraph_explain_exception`，以及后续 daudit AST/语义分析结果到调用图的融合。  
**前置依赖**: daudit AST 解析、项目级符号索引、引用追踪和增量缓存稳定后实施。

相关文档：

- `docs/ast-audit-engine-spec.md`: daudit AST、语义分析、审计规则和 KB 集成规格。
- `docs/callgraph-enhancement-plan.md`: 当前二进制 direct-call callgraph、用途层命令和 Win64 支持记录。
- `docs/stacktrace-migration-plan.md`: `StackTrace.pas` 运行时诊断、MAPDATA、token 化和 callgraph facade 迁移记录。

## 1. 背景

当前 callgraph 已经能基于 `StackTrace.pas` 的 MAPDATA 和 `.text` direct `E8 rel32` 扫描返回正向、反向、路径、影响分析和用途层诊断结果。这个能力适合确认“编译产物里确实存在的直接调用边”，但无法完整覆盖 Delphi 源码里的高层语义：

- DFM 事件绑定、Action 绑定和运行时事件赋值。
- 虚方法、接口调用、回调、匿名方法、消息分发、RTTI/反射调用。
- `Obj.Save` 这类需要追溯接收者类型的成员调用。
- property getter/setter、constructor/destructor、`inherited`、overload/default 参数等源码级语义。

因此后续方向不是把 `StackTrace.pas` 扩成反汇编器，而是在 daudit 完成后，把 AST/语义分析作为主图来源；现有二进制扫描保留为“编译确认层”和运行时诊断补充。

## 2. 目标

1. 建立多来源语义调用图：AST、DFM、MAPDATA/binary、RTTI、运行时观测和可选 LLM 辅助都归一到同一图模型。
2. 让所有调用边都带来源、证据、置信度和失败语义，避免把候选边误当成确定调用。
3. 在 daudit 稳定后，将影响分析、测试选择、边界审计、重构检查、孤岛候选和异常解释升级到语义图。
4. 保持现有 `cmd=callgraph` 默认行为兼容；语义图通过显式 `sources` / `mode` 或新封装逐步启用。

## 3. 非目标

1. 不在 `StackTrace.pas` 中实现完整反汇编、虚表恢复或接口分派恢复。
2. 不宣称无运行时证据时可以精确解析所有动态目标。
3. 不用 LLM 直接生成高置信调用图；LLM 只能作为歧义解释器或候选排序器。
4. 不在 daudit AST 未稳定前重写当前已验证的二进制 callgraph 路径。

## 4. daudit 依赖顺序

| 依赖阶段 | daudit 能力 | callgraph 可推进内容 |
|----------|-------------|----------------------|
| D0 | 单文件 AST JSON 稳定，routine/class/interface/record/property/field 基础节点完整 | 定义语义调用图 schema，建立 AST 节点到 callgraph 节点的 adapter |
| D1 | 作用域、uses、类型绑定、方法归属、overload 基础解析可用 | 生成 direct procedure/function call、同类方法调用、`Self.Xxx`、`inherited` 边 |
| D2 | 项目级索引和增量缓存稳定，跨 unit 引用可解析 | 建立全项目 semantic graph cache，支持 file/line 到 routine 的稳定映射 |
| D3 | 引用追踪输出可区分 identifier、member access、property access、constructor、assignment | 支持 `Obj.Save` 接收者追溯、property getter/setter、运行时事件赋值 |
| D4 | DFM 解析或 DFM 事件绑定表可用 | 合并 `OnClick=Handler`、Action/OnExecute、Form/Frame 入口边 |
| D5 | 继承链、接口实现、虚方法 override 关系稳定 | 生成 virtual/interface candidate 边，并按静态接收者类型收窄候选集 |
| D6 | 审计规则和引用图可复用到 MCP 层 | 用语义图驱动影响分析、测试选择、边界审计和重构检查 |

## 5. 图模型

### 5.1 节点

调用图节点统一表示“可执行入口”，而不是只表示二进制符号：

- `routine`: 全局 procedure/function。
- `method`: class/record/interface method。
- `constructor` / `destructor`。
- `property_accessor`: getter/setter 归一后的入口。
- `event_handler`: DFM 或运行时事件绑定的 handler。
- `message_handler`: `message WM_*` 或消息映射入口。
- `anonymous_callback`: 匿名方法、回调参数、timer/thread callback 等候选入口。
- `external_symbol`: RTL/VCL/第三方/系统 API。

### 5.2 边

每条边至少包含：

| 字段 | 说明 |
|------|------|
| `from` / `to` | 规范化节点 ID，优先 `unit.scope.name(signature)` |
| `edge_kind` | `direct_call`、`method_call`、`property_access`、`constructor_call`、`event_binding`、`runtime_event_assignment`、`virtual_candidate`、`interface_candidate`、`callback_candidate`、`message_dispatch`、`reflection_candidate`、`binary_confirmed`、`runtime_observed` |
| `sources` | `ast`、`dfm`、`binary`、`mapdata`、`rtti`、`runtime_stack`、`runtime_trace`、`llm` |
| `confidence` | `exact`、`high`、`medium`、`low`、`candidate` |
| `evidence` | 文件、行号、列号、AST node id、DFM object/property、callsite address、runtime frame 等 |
| `resolution` | receiver 类型、overload 选择、继承链、接口实现候选、未解析原因 |
| `warnings` | `ambiguous_receiver`、`dynamic_dispatch`、`missing_dfm`、`missing_unit`、`binary_not_confirmed`、`llm_only` 等 |

高置信边必须有可复查证据。没有证据的边只能进入候选集，不能影响“可安全重构”这类结论。

## 6. 多来源融合策略

| 来源 | 用途 | 置信度规则 |
|------|------|------------|
| daudit AST | 主图来源，解析源码调用、类型、作用域、引用 | direct call 且唯一解析为 `exact/high`；接收者不明为 `candidate` |
| DFM | UI 入口、设计期事件、Action 绑定 | handler 存在且签名匹配为 `exact/high`；缺失源码为 `medium` 并记录 warning |
| MAPDATA/binary | 编译确认、第三方/DCU、异常地址映射 | 与 AST 边匹配时提升为 `binary_confirmed`；单独发现的 direct call 为 `medium/high` |
| RTTI | published 方法、类型清单、部分方法地址辅助 | 用于收窄候选，不单独把虚调用标成 exact |
| runtime stack/trace | 异常栈、测试运行期间观测到的真实路径 | 观测边为 `runtime_observed`，可提升相关候选置信度 |
| LLM | 歧义解释、候选排序、源代码语义补充 | 只作为 advisory；没有 AST/DFM/运行时证据不得进入 high/exact |

冲突处理：

1. AST exact + binary confirmed：确定边。
2. AST exact 但 binary 未确认：保留为源码边，标记 `binary_not_confirmed`，可能由 inline、优化、未编译路径或 map 缺失导致。
3. binary direct call 无 AST 边：保留为编译边，标记 `source_unresolved`，用于第三方/DCU/编译器生成代码。
4. DFM handler 无 AST routine：保留入口节点，标记 `handler_not_found`，供项目修复或路径检查。
5. 多候选动态边：全部保留为 candidate，路径查询默认可配置是否纳入。

## 7. 实施里程碑

### R0 - Schema 与兼容层

目标：先把图模型定下来，不改变当前 callgraph 默认行为。

任务：

- 定义 semantic graph JSON schema 和 edge confidence 规则。
- 给当前 binary callgraph 增加 adapter，把 direct-call 边映射到新 schema。
- Python 层增加 `sources` / `confidence_min` / `include_candidates` 参数设计，但默认保持旧行为。
- 增加 schema golden tests，保证旧响应和新语义响应可以并存。

验收：

- 现有 `callgraph`、`callgraph_path`、`callgraph_impact` 测试不回退。
- 新 schema 中每条边都有 `sources`、`confidence`、`evidence`。

### R1 - AST 静态调用图

目标：以 daudit AST 项目索引为主来源，生成源码级 direct graph。

任务：

- 从 daudit routine/entity/ref 输出建立节点表。
- 解析全局函数调用、同 unit 方法调用、`Self.Xxx`、`ClassName.Xxx`、constructor/destructor、`inherited`。
- 支持 overload 基础选择；无法唯一选择时输出候选和原因。
- file/line 输入优先通过 daudit routine range 定位，不再只依赖 map 行号。

验收：

- fixture 覆盖 global call、method call、constructor、destructor、overload、inherited。
- 对同一 fixture，AST 图与 binary direct-call 图可做交叉确认。

### R2 - DFM / Action / 事件入口

目标：把 UI 入口补进图，解决当前纯二进制扫描无法知道入口来源的问题。

任务：

- 解析 `.dfm` / `.fmx` 中 `OnXxx = Handler`。
- 解析 `TAction.OnExecute`、ActionList、菜单、工具栏等常见入口绑定。
- 从 AST 中识别运行时事件赋值：`Obj.OnXxx := Handler`。
- 将事件绑定建成 `event_binding` 或 `runtime_event_assignment` 边。

验收：

- QLangEditor 设计期事件入口覆盖率达到 95% 以上。
- DFM handler 缺失时输出结构化 warning，不静默丢边。

### R3 - 接收者类型追溯

目标：提升 `Obj.Save` 这类成员调用的可解析比例。

任务：

- 追溯局部变量、参数、字段、`Self`、`Result` 的声明类型。
- 识别简单构造赋值：`Obj := TProject.Create`、factory 返回类型、`as` 类型转换。
- 处理 `with`、属性链、泛型容器、默认属性时输出候选和不确定原因。
- 对 property getter/setter 建立显式边。

验收：

- fixture 覆盖 locals/params/fields/Self/Result/constructor/factory/property。
- QLangEditor 业务调用链 high-confidence 覆盖率达到 85% 以上。

### R4 - 动态分派候选

目标：对虚方法、接口、回调、消息和反射给出“可解释候选”，不误报为确定边。

任务：

- 基于继承链和 override 表生成 `virtual_candidate`。
- 基于接口实现表生成 `interface_candidate`。
- 识别回调参数、匿名方法、线程/timer/message handler 常见模式。
- 识别 `message WM_*` 分派入口。
- 对 RTTI/published 方法和 `MethodAddress` 等反射路径生成 `reflection_candidate`。

验收：

- 每个动态候选都必须带候选集合、来源、置信度和未能精确解析的原因。
- `refactor_check` 遇到动态候选时不能给出“安全”结论，只能降级为需人工确认。

### R5 - 融合与置信度引擎

目标：把 AST、DFM、binary、RTTI、runtime 合成统一图，并为用途层提供稳定过滤。

任务：

- 实现 edge merge：同一 from/to/kind 的多来源证据合并。
- 实现 `confidence_min`、`include_candidates`、`source_filter`。
- `callgraph_path` 支持按置信度找路径，默认排除低置信候选。
- `callgraph_diff` 默认按稳定节点 ID 比较，地址变化只作为附加 evidence 变化。

验收：

- 高置信路径不包含无证据 LLM 边或低置信动态候选。
- diff 不因重编译地址变化产生大面积噪音。

### R6 - 用途层升级

目标：让已有 U1-U8 命令消费语义图，而不是只消费 direct-call 图。

任务：

- `callgraph_impact`: 优先使用 AST file/line 定位和语义 callers。
- `callgraph_select_tests`: 引入 DFM/UI 入口、Action 入口和候选路径说明。
- `callgraph_boundary_check`: 从前缀规则升级到 unit/class/category/namespace 规则。
- `callgraph_refactor_check`: 输出 exact/high/candidate 分层风险。
- `callgraph_orphan_candidates`: 纳入 DFM、runtime event、RTTI 和动态候选，减少误判。
- `callgraph_explain_exception`: 用异常栈地址回连语义图，区分真实运行路径和静态可达路径。

验收：

- 每个用途命令都有“只看 high-confidence”和“包含 candidate”的测试。
- 不完整图只能输出风险和待确认项，不能输出绝对安全结论。

### R7 - QLangEditor 验证基线

目标：用 `C:\user\qlang\editor` 做真实项目基线，验证语义图实际价值。

基线目标：

- UI/DFM 入口覆盖率：>= 95%。
- 项目业务调用链 high-confidence 覆盖率：>= 85%。
- high-confidence + candidate 覆盖率：>= 90%。
- 所有 unresolved 项都必须有原因分类。
- 语义图构建和增量刷新时间要可记录，避免黑盒测试时产生不可控开销。

重点用例：

- `actNewProjectExecute` 下游路径。
- `SaveIfModified` 上游 callers 和 dirty-close/save 相关脚本选择。
- `actSmartTranslateExecute`、`actTranslateCurrentExecute` 的业务调用链。
- `SourceResEditor` 相关运行时事件赋值。
- Action/菜单/工具栏入口到 handler 的映射。

### R8 - 增量缓存与 CI 集成

目标：让语义图可以长期用于审计和回归，不要求每次全量解析。

任务：

- graph cache 按 file hash、daudit version、MAPDATA id、compiler target 分层。
- 支持 changed file -> affected graph partition 增量刷新。
- CI 中输出 semantic graph snapshot，支持 PR diff。
- 将图构建失败降级为结构化 diagnostic，不阻断基础编译/自动化流程。

验收：

- 修改单个 `.pas` 后只刷新相关 unit 和依赖边。
- snapshot 可用于 `callgraph_diff`，且路径安全沿用 `snapshots_dir` 约束。

## 8. 测试矩阵

| 层级 | 测试内容 |
|------|----------|
| daudit fixture | AST JSON golden、routine range、refs、types、inheritance、interface impl |
| graph builder | 节点规范化、edge merge、confidence 计算、unresolved 分类 |
| DFM fixture | OnClick、OnExecute、ActionList、Frame、缺失 handler |
| type tracing fixture | locals、params、fields、Self、Result、constructor、factory、property |
| dynamic fixture | virtual/interface/callback/anonymous/message/reflection candidate |
| binary confirmation | AST 边与 MAPDATA/binary direct-call 边合并 |
| Python protocol | 参数校验、旧行为兼容、新 schema 响应、错误降级 |
| QLangEditor smoke | Win32/Win64 Debug，重点入口和业务链路覆盖 |

## 9. 风险与约束

| 风险 | 处理策略 |
|------|----------|
| daudit AST 输出还不稳定 | R0 只做 schema 和 adapter；R1 以后依赖 daudit golden tests |
| 动态分派误判 | 默认 candidate，不进入高置信路径；用途层必须显示风险 |
| DFM 与源码不同步 | DFM handler 缺失或签名不匹配必须输出 warning |
| `with` / overload / 泛型导致歧义 | 输出候选和 unresolved reason，不猜唯一目标 |
| LLM 结果不可复现 | 只用于解释和候选排序，不写入 high-confidence 图 |
| 大项目性能 | 项目级缓存、增量刷新、edge limit、按 source/confidence 过滤 |
| 与当前 callgraph 兼容性 | 默认保持二进制 direct-call 行为；语义图显式启用 |

## 10. 完成定义

后续 daudit 完成后，本路线图完成需要同时满足：

1. `callgraph` 能在显式语义模式下返回统一 schema，且旧模式兼容。
2. AST、DFM、binary、runtime 来源能融合到同一节点/边模型。
3. 所有边都有 evidence、confidence 和 source；高置信边没有无证据项。
4. 动态分派、回调、反射只作为候选输出，除非有运行时证据确认。
5. U1-U8 用途层命令都能按置信度工作，并能解释 unresolved。
6. QLangEditor 验证达到 R7 覆盖率目标，并记录 Win32/Win64 smoke 结果。
7. 全量 Python 测试和相关 Delphi fixture 编译/运行测试通过。

## 11. 建议执行顺序

1. 等 daudit D0-D2 稳定后先实施 R0-R1，确保 schema、节点 ID 和 AST direct graph 可用。
2. daudit D4 可用后实施 R2，优先补 UI/DFM 入口，因为这对黑盒自动化和测试选择收益最大。
3. daudit D3/D5 稳定后实施 R3-R4，逐步提升成员调用和动态候选覆盖。
4. 完成 R5 后再升级 U1-U8，避免用途层各自实现不一致的置信度逻辑。
5. 最后用 QLangEditor 和 fixture 项目做 R7/R8 收口，把性能、缓存、CI snapshot 和差异报告稳定下来。
