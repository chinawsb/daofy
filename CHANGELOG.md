# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2026.07.13] - 2026-07-13

### Added

- **DFM 布局完整性检测模块** (`src/detection/`): DFM 布局检测，支持 OpenCV/YOLO/合成数据生成。包括 `layout_parser.py`（DFM 解析）、`opencv_detector.py`（OpenCV 检测）、`yolo_onnx.py`（YOLO ONNX 推理）、`synthetic_data_generator.py`（合成数据生成）、`train_yolo.py`（YOLO 训练）。
- **DaofyAutomation 三层架构更新**: Fmx/Vcl/Base 三层新增命令和改进，增强 GUI 自动化能力。
- **新增测试文件**: `test_detection_module.py`（688 行）、`test_file_tool_grep.py`（716 行）、`test_automation_textbounds.py`（248 行）、`test_project_compile_extra_args.py`（114 行）。

### Fixed

- **`delphi_file` grep action 回退**: `file_path` 参数现在可选，未传时自动使用 `project_path` 或工作区根目录作为搜索范围。
- **`add_source` 绝对路径归一化**: 接收绝对路径时自动 `os.path.relpath` 转为相对于 `.dproj` 目录的路径，避免项目不可移植。
- **资源泄露修复**: `experience_service` 多线程连接泄露（单连接+锁模式）；`automation_service` 添加后台守护线程定时清理过期进程池。
- **`tool_help` action_params 补齐**: `delphi_file` 6 个缺失的 action_params；11 个工具新增 action_params 文档；`delphi_rtti` 补充 pipe 参数。
- **目录约束**: `coding-rules.md` 新增目录约束章节（标准结构、命名规范、清理规则）。
- **管道故障诊断**: `automation/scenarios/base.md` 新增管道建立失败诊断流程。

### Changed

- **`.gitignore` 更新**: 整个 `config/` 目录加入忽略，排除 ML 模型产物。
- **文档同步**: `project.md`、`automation/`、`coding-rules/` 更新。

## [2026.07.05] - 2026-07-05

### Added

- **文档全量同步**: docs/ 中全部 `project(action=...)` → `delphi_project(action=...)`；project.md/delphi_kb.md/get_coding_rules.md 内容与实现对齐；tutorial 文档同步修正。

### Changed

- **版本号**: v2026.06.22 → v2026.07.05

## [2026.06.22] - 2026-06-22

### Added

- **`delphi_rtti` 工具**: RTTI 桥接 — 通过 Enhanced RTTI 发现和调用 Delphi 应用的 published 方法（三步法：guide/discover/call）。包括 `DaofyAutomation.RttiDiscovery.pas` 能力发现单元、`src/services/rtti_bridge.py` 桥接服务（5 分钟缓存）、`src/tools/delphi_rtti.py` MCP handler。
- **`generate_copyright` 工具**: 软著文档自动生成（源代码/说明书/摘要，PDF 浏览器渲染+自动校验）。重构为通用工具，移除 Daofy 硬编码。
- **`daofy_update` 工具**: Daofy 自身版本检查和更新管理（check/update/version），支持 git pull 自动更新和 pip 升级提示。
- **`layout_audit` 工具**: 静态 DFM UI 布局审计 — 检测控件重叠、越界、对齐不一致、TabOrder 视觉顺序偏差等 AI 常见布局问题。
- **`agent_skill_installer` 服务**: MCP Server 启动时自动同步 Daofy Agent Skill 到用户级共享目录（`%USERPROFILE%\.agents\skills\daofy\SKILL.md`），强化 delphi_file/code_hosting 路由规则。
- **示例知识库支持**: `kb_type="example"` 全文搜索 Delphi 官方 Demos/Samples 和三方库 Demos/Tests。
- **Callgraph 诊断链**: 统一 stacktrace callgraph 诊断、异常解释增强、test selection coverage、boundary rule exceptions、refactor checks 保守模式、orphan candidates 分类、diff-style impact analysis、failure diagnostic coverage 记录。
- **`project` 工具描述标注【仅限 Delphi】**: 防止非 Delphi 用户在 AI 工具调用时误触。

### Changed

- **`project` → `delphi_project` 重命名**: 工具名从 `project` 改为 `delphi_project`，防止非 Delphi 用户在 AI 工具调用时误触。更新 server.py、tool_docs、tests 中所有引用。
- **`HTMLProcessor`/`WebDocumentProcessor` 移除 BeautifulSoup**: html2text 已自带跳过 script/style，BS4 的 tag.decompose() 和 sections/code_examples 提取在 ZVec 中不存储，属于无用计算。改用正则 `<title>` 提取标题。构建时间从 17:41 → 10:24（-41%）。
- **`scan_directory` 改为生产者-消费者模式**: ProcessPoolExecutor 替换为 `mp.Process` + `mp.Queue(maxsize=200)`，worker 逐条放入队列，主进程实时消费写入 ZVec，内存峰值从天降至 KB 级。
- **扫描器重组为固定 worker 池**: 生产者-消费者进一步优化，预清理首行重复警告。
- **文档知识库存储引擎**: SQLite FTS5 → ZVec 全文索引，文档存储路径 `data/document-knowledge-base/` 不再包含 SQLite 文件。`example_knowledge_base`/`thirdparty_knowledge_base` 同步迁移。
- **`scan_generic_documents.py` 缩减**: +230/-620 行，移除 FTS5 写入、SQLite 备份/恢复、偏移量计算等废弃逻辑。
- **`tool_docs.py` 迁至 `src/`**: 从 `src/config/tool_docs.py` 移到 `src/tool_docs.py`，更新所有 import。
- **`generate_copyright` 通用化**: 移除 Daofy 硬编码依赖，改为通用软著文档生成工具。
- **`DaofyAutomation` rget/rcall/waitfor 增加索引属性 [Index] 支持**: 支持通过 `object[Index]` 语法访问集合元素。
- **自动化资源文件结构化**: `src/resources/automation/` 目录按 reference/scenarios 分层组织，新增 `script-schema.md`、`l-layout.md` 等文档。
- **文档同步**: README 补充 `generate_copyright`/`daofy_update` 工具列表，AGENTS.md 补齐 services 清单，docs/ 中全部 `project()` → `delphi_project()` 修复。
- **新建 Delphi 文件统一使用 utf-8-sig 编码**: 避免中文注释在旧版 IDE 中显示乱码。
- **`src/config/` 移出版本控制**: `compilers.json` 等本地配置不再跟踪，避免开发环境差异导致的提交冲突。
- **`benchmarks/` 移出版本控制**: 性能基准测试目录不再跟踪。
- **`automation_service` 重构**: console/gui 模式拆分，支持 `proc_async` 异步进程读取，提升交互测试稳定性。
- **`delphi_edit_guard` DFM 脏标记增强**: 跨文件引用追踪，防止编辑行号错位。
- **Coding-rules 模块化拆分**: `src/resources/coding-rules/` 按 writing/review/compile/format/debugging 等独立文件组织，共 20 个 section。

### Fixed

- **`scan_directory` chunk_id 全量冲突**: `path_val = result.get('full_path')` 对同一 CHM 内所有 HTML 页返回相同路径（CHM 文件路径），导致所有 chunk_id 的 md5 相同，ZVec 覆盖写入仅保留 19 条 → 最终数据仅 4.15MB。修复为 `result.get('path')`（每个 HTML 页唯一路径）+ `chm#html` 复合格式保证跨 CHM 唯一。重建后 169,951 条、1.1 GB。
- **`col.insert()` 超过 ZVec 1024 批处理上限**: `batch_buffer` 在 `for result in docs` 循环外才 flush，单个 CHM 返回 45000+ 页面时单批超限报错。修复为每个 result 后 + 到达 BATCH_SIZE(500) 时 flush。
- **`add_web_document` 调用不存在的 `col.close()`**: ZVec Collection 无 close() 方法，改为 `del col + gc.collect() + sleep`。
- **进度回调百分比错误**: 传 2 参数 `(processed, total)` 被 `update_progress` 误识别为"单数值百分比"。改为传 3 参数触发 `(current, total, message)` 分支正确计算。
- **`HTMLProcessor` 中 `file_path.stem` 不支持 str 参数**: 当 process() 被直接传入字符串路径时报 `'str' object has no attribute 'stem'`。改为 `Path(file_path).stem`。
- **dcc32 直编路径修复**: 优先读取同目录 `.dproj` 的 `DCC_ExeOutput` / `DCC_DcuOutput` 确定输出路径；合并 BDS+Studio 注册表配置单元的 IDE 全局搜索路径。
- **异常退出日志丢失**: 进程退出前强制 flush 日志，避免最后一条日志因缓冲未写入。

### Removed

- **`fts5_lazy_manager.py`**: 文档 KB 不再使用 FTS5，整模块删除。
- **`schema.py` 中文档相关 SQLite 表定义**: 标记为废弃。
- **`knowledge_base.py` 中 `_build_document_zvec`**: 不再需要独立构建步骤。
- **`async_tasks.py` 中 SQLite→ZVec 转换步骤**: 扫描器直接写入 ZVec。

## [2026.06.15.1] - 2026-06-15

### Changed

- **`compiler_service` 过时 typing 迁移至原生泛型**: 移除 `typing.List` 导入，4 处 `List[str]`/`List[Path]` 迁移至 Python 3.10+ 原生泛型 `list[str]`/`list[Path]`。项目要求 Python >= 3.10，原生泛型完全兼容。

## [2026.06.15] - 2026-06-15

### Added

- **`compiler_service` Delphi >= XE5 自动启用响应文件编译**: 检测到 Delphi 版本 >= 12.0 时，自动添加 `DCC_UseMSBuildExternally=true` 参数，解决 MSBuild 命令行过长 (>32K) 导致编译失败的问题。
- **`knowledge_base._resolve_project_path` 支持 .dpr/.dpk**: 项目路径自动检测扩展为按优先级搜索 `.dproj` > `.dpr` > `.dpk`，优先匹配目录同名项目文件。
- **`tool_docs`/`delphi_rtti`/`automate_delphi` 文档补充 DaofyAutomation 单元选择**: 明确标注 VCL 项目用 `Vcl.DaofyAutomation.pas`，FMX 项目用 `Fmx.DaofyAutomation.pas`，以及 tools\\auto\ 路径说明。

### Changed

- **`file_tool` 连续重复行检测降级为警告**: 不再阻断写入，仅警告提示AI verify 结果。`force` 参数描述同步更新为"跳过续重行检测（默认 false 时检测到重复仅警告不阻断写入）"。
- **`file_tool` format action 移除偏移量计算**: pasfmt 可能非线性重构代码结构（展开 uses、调整 begin/end 等），格式化前后的行号无线性对应关系。移除偏移量计算，format 后仅标记脏标记强制 re-read。
- **`file_tool` auto_format 偏移显示优化**: 新增单独警告行显示 auto_format 额外偏移和累计总偏移，不再修改 per-edit 的偏移量显示。
- **`file_tool` preview 模式补充 auto_format 提示**: 预览时标注 `⚠️ preview 不含 auto_format 偏移`。
- **`project_knowledge_base` 日志降级**: 非 `.dproj` 文件的三方库路径提取从 `logger.warning` 降为 `logger.debug`，减少冗余日志。
- **`delphi_rtti` 故障排除文档更新**: pipe_unavailable 错误提示补充 VCL/FMX 单元选择说明。
- **`server.py` delphi_kb/project_path 描述更新**: 补充 `.dpr/.dpk` 扩展名支持说明。
- **`tool_help` 新增 auto_unit_paths 显示**: delphi_rtti/automate_delphi 的帮助信息中新增 DaofyAutomation 单元选择提示。

### Fixed

- **`file_tool` 批量写入 orig_e_display 导出错误**: 当 `e` 为 None（替换到文件末尾）时，原代码使用编辑后的 `total` 而非编辑前的 `before_len`，导致偏移显示错误。
- **`file_tool` format action 遗留代码清理**: 移除格式化前/后行数计算的无用代码（~20 行）。
- **`file_tool` auto_format 后 fmt_diff 未初始化**: 当 pasfmt 未格式化（fmt_msg 为空）时，Python 的局部变量 `fmt_diff` 可能未定义。

### Tests

- **`test_post_merge_dup_detection` → `test_post_merge_dup_warning`**: 适配重复行检测降级为警告的新行为，测试断言改为验证写入成功 + 文件中含预期内容。
- **`test_format_offset_in_response` → `test_format_calls_pasfmt`**: 移除格式化返回偏移量的断言，改为验证 format 成功且 dirty flag 阻止后续 write。
- **`test_auto_format_offset_correction`**: 适配新的偏移显示格式（per-edit offset=0，auto_format 额外偏移单独行显示）。
- **`test_format_action_returns_offset` → `test_format_action_marks_dirty`**: 验证 format 后不应包含偏移量，且 dirty flag 阻止 write。

## [2026.06.13] - 2026-06-14

### Added

- **`delphi_rtti` MCP 工具**: Delphi RTTI 桥接 — 通过 Enhanced RTTI 发现和调用 Delphi 应用的 published 方法。三步法：`action=guide`（使用指南）、`action=discover`（扫描能力）、`action=call`（调用方法）。返回 JSON Schema 格式的参数定义。
- **`DaofyAutomation.RttiDiscovery.pas`**: 新增 TRttiDiscoverer 类，实现 `DiscoverClass(AClass)` 扫描 published 方法/属性，`TypeToSchema(AType)` 将 Delphi 类型→JSON Schema 映射（支持 Integer/Float/Boolean/字符串/枚举/集合/DynamicArray/TDateTime/Variant/Pointer 等 15 类类型）。
- **`DaofyAutomation.Base.pas` RTTI 支持**: 新增 `rtti_discover` 命令路由、`HandleRttiDiscover()` 处理器、基类 `GetRttiClasses()` 虚方法（返回空数组 TClass[]）。
- **`Vcl.DaofyAutomation.pas` RTTI 支持**: 重写 `GetRttiClasses()` 返回 VCL Application 中所有已注册 Form 的 ClassType（`Screen.Forms[*].ClassType`）。
- **`src/services/rtti_bridge.py`**: RttiBridge 服务 — 管理 Delphi 应用 RTTI 连接，5 分钟缓存（`_cache_ttl`），支持 `connect()`/`discover()`/`call()`/`clear_cache()`，复用现有命名管道通信。
- **`src/tools/delphi_rtti.py`**: MCP Tool handler — `action=guide` 返回完整使用指南（~80 行 Markdown），`action=discover` 先 connect 再 discover，`action=call` 先 connect 再 call；参数校验（app_path/class_name/method 缺失时返回明确错误）。
- **`.opencode/skills/delphi-rtti-bridge/`**: 权威 SKILL.md（YAML frontmatter + 渐进式 L3 文档）+ `references/type-mapping.md`（15 类类型映射表）+ `references/examples.md`（5+ 完整工作流示例）。
- **`scripts/build-skills.py`**: 多平台分发脚本，支持 claude-code/cursor/windsurf 一键分发。
- **`tests/test_rtti_bridge.py`**: 22 个测试用例 — 缓存生命周期（命中/过期/清除）、discover（完整/缓存/强制/类过滤/管道错误/JSON 错误）、call（成功/管道错误/方法找不到/类找不到）、connect（新建/复用/失败）。
- **`tests/test_delphi_rtti.py`**: 16 个测试用例 — guide（文本内容/章节完整性）、discover（参数校验/mock 调用/连接失败/错误传递）、call（参数校验/mock 调用/错误传递）、未知 action。

- **DaofyAutomation 三层架构拆分**: `tools/auto/` 拆分为 `DaofyAutomation.Base.pas`、`Vcl.DaofyAutomation.pas`、`Fmx.DaofyAutomation.pas` 三层架构，每层独立单元、独立职责。
- **Overlapped I/O 管道通信**: 使用 `WaitForMultipleObjects` 实现零延迟推送，`FAsyncResults` 60 秒 TTL 自动清理，异步结果通过 `peekresult` 按 reqId 取回。
- **全部命令标准化**: 所有 `HandleCmd*` 统一 reqId 回显；`rcall`/`rset`/`type`/`key` 改为异步（防模态弹窗阻塞管道）。
- **扩展命令集**: 新增 `move`/`drag`/`key`/`waitfor`/`listwnd`/`rcall`/`dlgfile`/`peekresult` 等命令。
- **FMX 截图支持**: `PaintTo`/`Context.CopyToBitmap`/`fsModal` 检测，覆盖 FMX 2D 和 3D 程序。
- **`dumpstate`/`dlgscan`/`rinspect` 改为管道返回**: 不再写文件，通过命名管道直接返回结果。
- **进程池复用**: `keep_alive` 参数支持进程复用，避免反复启动 Delphi 应用。
- **测试项目**: VCL/FMX 2D/FMX 3D 三个测试程序 + 4 个测试脚本（`test_all_commands.py`、`test_capture_all.py`、`test_dlgclick_msgbox.py`、`test_json_protocol.py`）。
- **完整命令集文档**: `docs/automate_test_guide.md`。

- **`automate_delphi` 新增 Console 模式**: 通过 `action="console"` 或 `action="auto"`（自动 PE 头检测）支持 subprocess stdin/stdout 交互。无需 Delphi 端改造，通过 `input`/`expect`/`timeout`/`args` 参数控制。引入 `detect_exe_subsystem()` 读取 PE OptionalHeader Subsystem 字段区分 GUI(2) vs Console(3)。
- **Windows 兼容 expect 模式**: 使用 `threading.Thread` + `queue.Queue` 替代 `select.select`（Windows 不支持 pipe select）。无 expect 时直接用 `proc.communicate()` 避免多线程竞争 pipe 读取。
- **`tests/test_console_automation.py`**: 18 个测试用例覆盖 `detect_exe_subsystem`（PE 检测/边界）、`console_execute`（basic/expect/timeout/keep_alive/stderr/exit_code）、`execute_automation` 分发（gui/console/auto/unknown）、边缘情况。

- **`file_tool` 路径白名单校验**: 新增 `_validate_path()` 函数，集成 `PathValidator` 对文件路径进行白名单式安全校验，限制文件操作在允许目录范围内。
- **`file_tool` 脏标记系统**: 文件写入后标记为"脏"，再次 `write` 前必须 `read` 或 `preview` 确认行号，防止 AI 基于过时行号继续编辑。

- **`CODING_RULES.mdc` §⑧ 自动化UI交互测试**: 新增完整的 GUI 自动化测试规则（单元链接、命令示例、验证流程）。
- **`CODING_RULES.mdc` §⑨ 控制台程序交互验证**: 新增 Console 模式工具调用、测试模式、基础用法、分步交互、进程池复用规则。
- **`CODING_RULES.mdc` delphi_file 规则重构**: 全面重写 delphi_file 写入规则、紧凑输出格式、脏标记保护、行号规则，迁移 AGENTS.md 中详细规则到此统一文档。
- **`src/tool_docs.py`**: 注册 `delphi_rtti` 工具；精简 write 文档为 edits 唯一参数格式；移除 0-indexed 行号说明。
- **`src/server.py` tool 描述更新**: 注册 `delphi_rtti` 和 automation 工具；delphi_file 参数统一至 1-indexed 描述；移除 `batch_write` 独立路由。
- **delphi_rtti 技能分发脚本**: `scripts/build-skills.py` 支持自动分发到 claude-code/cursor/windsurf。

### Fixed

- **`console_execute` Windows pipe 读取**: `select.select` 不适用于 Windows 上的 subprocess pipe（仅支持 socket）。改为 thread + Queue 实现非阻塞 expect 读取，无 expect 时退回 `proc.communicate()`。
- **`batch_write` 独立 action 清理**: 写入统一为 `write(edits=[...])`，不再暴露独立 `batch_write` action。
- **content 首行重复检测修正**: 文件头替换时 content 首行与原文件首行重复属于正常场景，不再误报 `⚠️` 警告。

### Changed

- **`automate_delphi` 参数扩展**: 新增 `input`/`expect`/`timeout`/`args` 参数，`action` 增加 `auto`（默认）和 `console` 模式。`action="auto"` 通过 PE 头自动检测 GUI vs Console。
- **`tool_docs.py` 更新**: automate_delphi 文档拆分为 gui/console 双模式，新增 console 参数说明和示例。
- **`file_tool` 重构**: 统一 1-indexed 行号体系，代码精简化（+297 / -605 行），移除 `batch_write` 独立 action 入口。
- **`AGENTS.md` 精简**: 将 delphi_file 详细规则、行号规则、脏标记、输出格式等迁移至 `CODING_RULES.mdc`，AGENTS.md 仅保留工作流总览和核心要点。
- **`CODING_RULES.mdc` 版本**: 更新至 `1.12.0` / 2026-06-14。
- **copyright 服务**: 更新版权模板和骨架代码，修复 f-string 大括号问题，模板通用化。

## [2026.06.12] - 2026-06-12

### Fixed

- **`auto_format` 后偏移量重算**: `_handle_batch_write_internal` 在 auto_format 写入后重读文件计算真实偏移差，更新最后一个 edit 的 `(offset: +N)` 显示。之前返回的 offset 仅反映原始 edit 的行数变化，不含 formatting 影响（如 uses 展开、空行调整）。
- **`test_sanity_warn_on_dup_first_line` 行号适配**: 替换区间从 `[4,5]` 改为 `[5,5]`（1-indexed 下 `[4,5]` 覆盖 2 行，首行被替换行是 `T=class` 而非 `F1: Integer`，导致 ⚠️ 警告触发条件不满足）。

### Changed

- **`_read_content`/`handle_read` 统一为 1-indexed**: 行号前缀、meta 行号范围、默认 `start_line` 全部改为 1-indexed，与 `write`/`edits` 使用相同的行号体系，消除历史常见的 ±1 错位。
- **`handle_read` 自动清除脏标记**: 读取成功后自动 `_clear_dirty(file_path)`，避免脏标记阻塞后续写入序列。（预览模式 `preview=True` 也清除脏标记。）
- **`handle_read` 锁降级**: 移除 `handle_read` 在读取期间的写锁（实际只读），改为仅获取读锁，允许多 agent 同时读取同一文件。
- **`tool_docs.py` write 文档精简**: action 列表移除 `batch_write` 独立入口，`write` 的文档补充 `edits` 为唯一参数格式，移除 0-indexed 行号说明。
- **`server.py` tool 注册同步**: `call_tool` 中移除 `batch_write` 独立路由（已通过 `write` + `edits` 合并），同步更新 `list_tools` 工具描述。

### Updated

- **`CODING_RULES.mdc`**: §⑧ 人机协同规则（前置自检、触发条件表、优先级交互说明）；§⑥ 审核表末尾确认规则（🔴 等确认 / 🟡 列选项 / 🟢 先修后报）；§⑧ 偏移量文档补充 `auto_format` 影响说明。
- **`AGENTS.md`**: 删除 `project_compile` 历史合并提醒（已合并至主文档）。
- **`CODING_RULES.mdc` 版本**: 更新至 `1.11.0` / 2026-06-12。

## [2026.06.08.1] - 2026-06-08

### Added

- **`delphi_file` 全操作 RWLock 防并发文件损坏**: 所有 `file_tool` 操作（read/write/batch_write/format/backup/uses）引入多读单写锁 `_file_rw_locks`。`_acquire_read_lock` / `_release_read_lock` 用于共享读取，`_acquire_write_lock` / `_release_write_lock` 用于排他写入。多个 agent 同时对同一文件写入时，后到者直接返回明确错误，引导合并为一次 `batch_write`。配套修复 `handle_read` 中 DFM 转换后 `file_path` 重新赋值导致锁释放在错误路径的 bug。
- **`tool_docs.py` 约束强化**: `delphi_file` 文档中新增 `"🚫 禁止对同一个文件并行写入"` 和 `"🚫 同一个文件不要分多次 write"` 约束，推荐使用 `replace`/`insert`/`delete` 替代顶层 `content/start_line/end_line` 参数。
- **`tools/7z/7z.dll` 打包**: 补齐 7z.exe 运行所需的 7z.dll（1.9MB），确保 release 包解压后开箱可用，无需单独安装 7-Zip。

### Changed

- **`.gitignore` 排除 dot-prefixed 目录**: 新增 `.*/` 模式，`git rm --cached .arts .omo .sisyphus`，避免项目内 AI 工作目录被意外追踪。

## [2026.06.08] - 2026-06-08

### Added

- **`delphi_file` write/batch_write 支持 `preview` 预览模式**：`preview=true` 时跳过备份/写盘/格式化，仅计算并返回 diff 预览。write 全量预览返回文件大小变化；write 部分写入预览和 batch_write 预览显示 `- L{行号}:` 格式的 diff。配套 9 个测试用例。

### Fixed

- **`ExperienceMemoryService.delete()` 方法定义缺失修复**：`experience_service.py` 中 `delete()` 的 `def delete(...)` 方法头丢失，docstring 与方法体成为 `rebuild_embeddings()` `return` 后的死代码。`merge()` 中 `self.delete(did)` 调用会抛出 `AttributeError`。已在 `prune_list()` 与 `rebuild_embeddings()` 之间补充完整的方法定义，并移除死代码。
- **`embedding_service.py` `os.environ` 线程竞态修复**：`_worker` daemon 线程与主线程 `_restore_env()` 同时操作 `os.environ`，底层的 `os.putenv`/`os.unsetenv` 非线程安全。新增 `_env_lock = threading.Lock()` 保护全部 `os.environ` 写操作。
- **`test_is_dfm_file` 断言修正**：`tests/test_file_tool.py` 中断言 `_is_dfm_file("test.fmx") is False` 写反，`.fmx` 与 `.dfm` 使用完全相同格式，函数本身已正确处理，仅修正测试断言。

### Changed

- **`search()` 自动重建缺失向量**：`experience_service.py` 的 `search()` 在模型已加载但语义搜索无结果时，自动触发 `rebuild_embeddings()` 补全缺失向量后重试，无需用户手动调用 `rebuild_embedding` action。
- **`CODING_RULES.mdc` / `AGENTS.md` 经验文档更新**：保存流程与维护规则中补充 `rebuild_embedding` 自动补全说明。

## [2026.06.03] - 2026-06-03

### Added

- **`delphi_file` 新增 `batch_write` action**：一次传入多个 edit，内部按 `start_line` 升序排列，以备份文件为参照系，内存中累积偏移量后一次性写出。相邻 edit 区间重叠时自动检测并拒绝，防止行号映射错误。
  - 新增 `handle_batch_write()` 函数
  - `edits` 参数：数组，每项含 `start_line`（0-indexed inclusive）、`end_line`（0-indexed exclusive，可选）、`content`、`description`（可选）
  - 支持 `backup`/`encoding`/`auto_format` 参数，兼容 DFM 二进制文件
  - 配套 18 个测试用例（基本功能 + 14 个边界测试：重叠检测、相邻区间、文件边界、大偏移、CRLF、10 edit 混合等）
- **`batch_write` 新增 AI 偏移量错误自动检测**：
  - `force` 参数（默认 false）：设为 true 可跳过重复行检查强制写入
  - per-edit 检查：content 首行与被替换行内容相同时发出 `⚠️` 警告
  - post-merge 扫描：所有 edit 应用后扫描结果中新增的连续重复非空行，检测到时阻止写入并返回明确错误信息
  - 只报告新增重复（排除原始文件已有的连续重复行），避免误报
  - 写入被阻止时文件保持原样不被修改
  - 配套 4 个测试用例（警告/force绕过/重复检测/post-merge force绕过）

### Fixed

- **`compilers.json` 路径自愈**：`config_manager.py` 检测到 `compilers.json` 不在 `src/config/` 时自动回退到项目根 `config/`，存在则切换并打印 INFO 提示。两个候选路径：`[src/config/, 项目根/config/]`，避免 MCP 启动时因路径差异直接报错。
- **18 处 `except Exception: pass` 添加 `logger.debug`**：原 except 块静默吞掉所有异常，调试时无法定位失败原因。改为记录 `logger.debug(msg, exc_info=True)` 附带调用栈，不改变原有控制流（仍 `pass`）。涉及 10 个文件：`__version__.py` / `utils/__init__.py` / `compiler_service.py` / `experience_service.py` / `smart_cache_knowledge_base.py` / `audit.py` / `compile_project.py` / `experience.py` / `read_source_file.py` / `knowledge_base.py`。

### Changed

- **`search_knowledge` 597→37 行重构**：`tools/knowledge_base.py` 单函数从 597 行拆为 37 行主函数 + 16 个模块级子函数（`_filter_by_search_type` / `_trunc_hint` / `_format_symbol` / `_format_document_results` / `_empty_query_guide` / `_has_meaningful_results` / `_search_references` / `_search_symbols` / `_try_semantic_search` / `_start_async_project_rebuild` / `_maybe_search_document` / `_multi_keyword_search` / `_multi_kw_ref_one_kb` / `_multi_kw_sym_one_kb` / `_format_search_output` / `_format_one_section`）。嵌套常量 `_SEARCH_TYPE_TO_KIND` / `_KIND_DESC` 提升为模块级，内联 import 保留在子函数内避免循环依赖，`_format_one_section` 用 `style` 参数统一 4 种输出格式。行为完全等价，pytest 727 passed（零回归）。

## [2026.06.01] - 2026-06-01

### Fixed

- **`delphi_file` 部分写入行号偏差根因消除**：`handle_write()` 文档字符串原本误写为"1-indexed 闭区间"，与实际 0-indexed Python 切片行为矛盾。现修正为"0-indexed 左闭右开"，消除 AI Agent 理解偏差。
- **部分写入返回偏移量信息**：每次 `delphi_file(action="write", start_line=..., end_line=...)` 后，输出中附带 `偏移量: +N（删X行, 插Y行）` 和 `后续编辑: 行号 ≥ E 的新行号 = 原行号 + N`，AI Agent 可据此累加计算后续行号，无需重新读取文件。
- **`uses` action 同步返回偏移量**：`delphi_file(action="uses")` 现在也返回 `替换范围` 和 `偏移量`，避免 uses 操作后行号错位。

### Changed

- **`AGENTS.md` 新增「部分写入规则」章节**：文档化 0-indexed 语义、连续编辑的行号偏移算法（每次 write 返回 s/e/offset，Agent 依次累加）、uses 偏移说明；推荐全文替换替代多次部分写入、用 `uses` action 替代手动 uses 行号计算。
- **`tool_docs.py` `delphi_file` 文档补充**：write/read action 描述中添加 0-indexed 和偏移量说明。

## [2026.05.30] - 2026-05-30

### Changed

- **`delphi_file` read/write 行号改为 0-indexed 左闭右开**：`start_line`/`end_line` 改为 0-indexed 左闭右开区间 `[start, end)`，与 Python `list[start:end]` 切片语义一致。`start_line` 默认值从 `1` 改为 `0`，`end_line` 改为不包含该行。
- **新增 17 个 file_tool 边界测试**：覆盖空区间、负值 clamp、超 EOF、单行替换、删除行、无效范围等场景。全部 60 项 file_tool 测试通过。

### Added

- **`run_verify` 异常日志嵌入 MCP 响应**：编译运行验证时检测到 `exception.log`，使用 `detect_encoding`（与 `file_tool` 同款 BOM/编码检测）读取内容直接嵌入 MCP 响应，无需 AI 额外调用 `file_tool`。原方案仅报告路径和大小。
- **`employee-input` 项目重建**：清理旧文件，重新创建 FireDAC SQLite 员工信息管理演示项目；UTF-8 BOM 编码消除 W1057 警告；左右分栏布局（详情左/列表右）；新增"取消"按钮。
- **CODING_RULES.mdc 补充文件编码指南**：推荐新建含中文 Delphi 文件使用 `utf-8-sig`（UTF-8 with BOM）避免 `W1057 Implicit string cast` 警告。

### Changed

- **`AGENTS.md` `run_verify` 描述更新**：注明 `detect_encoding` + 嵌入日志内容的工作流程改。
- **`compile_project.py`**：`run_verify` 中读取 `exception.log` 改用 `detect_encoding`（从 `file_backup` 导入），与 `file_tool` 保持一致的 BOM/编码检测链。

## [2026.05.14] - 2026-05-14

### Added

- **`get_coding_rules` 新增 `section` 参数**：支持按章节获取编码规范（workflow/writing/review/safety 等 20+ 命名章节），默认返回工作流总览+章节索引，引导 Agent 按需拉取节省 token。新增元章节 `review`（审核指南+审核表）和 `coding`（写代码+格式化+编译）。
- **CODING_RULES.mdc 补充编码规范**：新增泛型命名与约束、运算符重载、异步与多线程、代码组织、版本兼容原则；审核表补充日志输出、数据转换、测试方法命名通用原则；新增规则模板格式。
- **工作流嵌入审核步骤**：①-⑥ → ①-⑦，编译通过后强制代码审核环节。
- **新增 3 个测试文件**：`test_coding_rules.py`(20例/90%覆盖)、`test_process_manager.py`(16例/92%覆盖)、`test_environment.py`(12例/95%覆盖)，总测试数从 144 增至 186。
- **测试弃用警告清理**：消除 40 条 `PytestReturnNotNoneWarning`（`return→assert`）；消除 9 处 `DeprecationWarning: Element truth value`（`if not self.root→is None`）。

### Fixed

- **`print()` 泄漏修复**：`install_package.py` 注册组件包时的 `print()` 改为 `logger.info/error`；`scan_generic_documents.py` 异步扫描状态的 `print()` 改为 `logger.warning/info`；`dynamic_worker_optimizer.py` Worker 测试失败的 `print()` 改为 `logger.warning`。
- **静默异常处理改进**：`server.py` 中 `_auto_detect_delphi_help_dir` 和 `_cleanup_resources` 的 `except:pass` 改为 `logger.debug/warning`；消除 `# type: ignore`（`async_task_manager` 声明 `_dedup_key` 字段）。
- **代码风格统一**：`server.py` 中 3 处 `== False` 改为 `is False`。
- **死代码清理**：移除 `progress_tracker.py` 中未使用的 `ProgressCallback` 类（34 行，含 `print()` 调用）。
- **`test_semantic_search` 修复**：反转索引降级适配 + `search_by_class_name/function_name→search_by_name` 方法名修正（预存 bug，之前被 `return False` 静默隐藏）。
- **pasfmt uses 压缩后处理**：pasfmt 默认展开 uses 为每行一个，新增 `uses_style="compact"` 选项将 uses 子句合并回单行，通过 `uses_style="pasfmt_default"` 恢复 pasfmt 原样。全局设置 `set_uses_style()` 支持持久化。
- **类内 type 段扫描**：`scan_delphi_sources._extract_all_entities` 新增 `_extract_nested_type_section()`，识别 `private type` / `public type` / 类内 `type` 段中的类型别名（如 `PItem = ^TItem`、`TItemArray = array of TItem`），补全 parent 链接。
- **泛型格式化实测验证**：确认 pasfmt 删除 `>>` 空格在 Delphi 12 编译通过，CODING_RULES.mdc 修正相关误导规则。

## [2026.05.13] - 2026-05-13

### Changed

- 文档同步：精简 README/CHANGELOG，移除冗余版本历史
- pyproject.toml 版本更新为 2026.05.13
- 修复 README_EN.md 中过时引用 (search_knowledge → delphi_kb)
- 合并 CHANGELOG 重复章节

## [2026.05.12] - 2026-05-12

### Added

- **正则表达式增强**：全面改进 Delphi 源码扫描器 regex，覆盖更多语法场景
  - 函数/过程: 支持 `constructor`/`destructor`/`class function`/`class procedure`/`class operator`
  - 函数参数: 支持泛型类型参数 `ToArray<T>`、嵌套括号 `(array of (Integer, String))`
  - 类定义: 排除 `class of` metaclass 误匹配，父类支持泛型 `TList<T>`
  - 接口: 支持 `dispinterface`、GUID `['{...}']` 语法
  - Helper: 支持可选祖先类 `class helper (TBaseHelper) for`
  - 指针: 放开 `PBT` 前缀限制，指向类型可显示
  - 过程类型别名: 支持嵌套括号参数、calling convention
  - 常量: 支持多行字符串值、小写开头的常量名、复杂类型标注 `array[0..9] of Integer`
- **搜索增强**:
  - `search_type="function"` 现在同时匹配函数(FF)和过程(FP)，vs `procedure` 只匹配 FP
  - `search_by_name` 新增文件路径回退: 搜 `System.DateUtils` 返回该文件所有实体
  - 默认 `top_k` 从 10 提升至 200，上限设为 500
  - 截断提示: 结果显示 `(提示: 共 N 条结果，top_k=X，M 条未显示)`
- **性能修复**: 修复 `_FUNC_PATTERN_1` 嵌套括号正则灾难性回溯（单文件从 219s → 0.002s）

### Fixed

- `SQLiteVectorKnowledgeBase._create_tables` 的 `metadata` 表结构与 `build_vector_index` INSERT 不匹配的 schema 问题
- `get_index_hash` 兼容两种 metadata 存储格式
- `match.lastindex` 缺乏 None 检查（3 处，预存 issue）
- `_extract_functions` 引用已删除的 `_FUNC_PATTERN_2`

### Merged

- **编译器自动检测优化**：从硬编码 5 个特定编译器改为动态扫描 bin 目录下所有 `dcc*.exe`，通过文件名映射表自动识别平台
- **数据库性能优化**：`SmartCacheKnowledgeBase._get_connection(use_wal=True)` 构建时 WAL 模式提升写入性能，查询时 DELETE 模式避免 `.wal` 文件残留
- **VACUUM 压缩**：知识库构建完成后自动执行 `VACUUM` 压缩数据库文件体积
- **文档扫描进度优化**：`_estimate_total_docs()` 预估算 CHM 内子文档数，进度平滑不再跳跃
- **自动构建项目知识库**：搜索项目知识库时若 KB 不存在则自动构建

## [2026.05.09] - 2026-05-09

### Added

- **知识库 AI 触达率提升**（P0-P5）
  - P0: 空 `query` 时返回 KB 统计 + 使用示例引导，替代简单的 "请提供参数" 报错
  - P1: `search_type` 默认从 `semantic` 改为 `all`，Agent 无需选参数也能搜到结果
  - P2: MCP tool `description` 嵌入 6 条常用命令示例，Agent 一眼看懂用法
  - P3: 项目 KB / 三方库构建时添加详细进度回调（5%扫描 → 50%写DB → 95%报告 → 100%完成）
  - P5: 新增 `search_type="reference"` 引用查询，可查哪些文件引用了某单元
- **真语义搜索（P4，可选）**：新增 `intfloat/multilingual-e5-small` embedding 引擎
  - 新增 `embedding_service.py`：E5-small 模型懒加载 + 分批编码 + cosine 搜索
  - `semantic_search_classes/functions` 优先使用 embedding，不可用时降级到反转 GLOB
  - 新增 `build_vectors()` 批量构建向量（分批 500 条 + 进度回调）
  - 新增 `action=build_embedding` 异步任务入口，避免模型加载超时
  - 模型自动从 `hf-mirror.com` 回退下载，支持 `TRANSFORMERS_OFFLINE=1` 离线模式
  - 搜索时不自动加载模型，仅当 `build_embedding` 显式触发后才启用
- **项目知识库路径自动检测**：`delphi_kb(action=search/stats/build, kb_type=project)` 不再强制要求 `project_path` 参数
  - 新增 `_resolve_project_path()` 函数，自动扫描 CWD 及父目录查找 `.dproj` 文件
  - 找到多个 `.dproj` 时优先匹配目录名同名的项目文件
  - AI agent 搜索项目知识库时无需显式传递路径
- **引用查询短名解析**：`search_usages()` 从 `.dproj` 读取 `DCC_Namespace` 命名空间前缀
  - `Vcl.Forms` 同时匹配简写 `Forms`，`Winapi.Windows` 匹配 `Windows`
  - 未配置时使用 Delphi 2010+ 默认前缀列表（Winapi/System/Vcl/Data/Web/SOAP/XML 等）
- **错误信息显示**：`search_knowledge()` 输出末尾增加 `project_error`/`thirdparty_error` 显示

### Fixed

- **修复项目知识库加载失败**：`load_knowledge_bases()` 只识别旧 JSON 格式（`.delphi-kb/project/index/source_index.json`），不识新 SQLite 格式（`.delphi-kb/knowledge.sqlite`），导致项目 KB 始终无法加载，搜索返回 0 结果
- **修复统计信息返回全 0**：`get_statistics()` 查询不存在的 `classes`/`functions` 表（新 schema 改为 `vocabularies` 表），导致 stats 显示 0 类 0 函数
- **修复三方库构建写入空 DB**：`build_thirdparty_knowledge_base()` 使用 `SQLiteVectorKnowledgeBase(force_rebuild=True)` 触发损坏的 `build_vector_index()`，该方法先 drop 表再读空表，永远不写入数据。改为直接 SQLite INSERT（与 `build_project_knowledge_base()` 统一 schema）
- **修复共享三方库统计信息**：`ThirdPartyKnowledgeBase.get_statistics()` 只查旧 `classes`/`functions` 表，新 schema 数据在 `vocabularies` 表，导致共享三方库一直显示 0 类 0 函数
- **修复搜索结果被 filter 吞没**：`_filter_by_search_type()` 不识别 `kind_code='class'`（项目 KB 存储格式），只认 `'TC'`（Delphi KB 格式），所有项目 KB 搜索结果被过滤为空
- **修复 `_append_stats_guide()` 无效**：`guide` 字符串参数按值传递，内部 `+=` 不影响调用方，改为返回值模式
- **修复 `search_usages()` 引用查询无结果**：直接在 `units_imported` 搜类名不匹配，改为先查定义单元再搜引用
- **修复 `build_vectors()` 缺少 logger**：`sqlite_vector_query_knowledge_base.py` 从未定义 `logger`，导致 `build_embedding` 崩溃
- **修复 embedding 模型离线加载**：`SentenceTransformer` 即使缓存也会联网验证 SSL，设置 `TRANSFORMERS_OFFLINE=1` + `local_files_only=True` 纯离线加载
- **修复用户 site-packages 路径**：MCP 服务未加载 pip 安装到用户目录的包，添加 `site.addsitedir(site.USER_SITE)`

### Changed

- **标准化 type 编码**：所有知识库的 `vocabularies.type` 统一使用 Delphi 双字母编码（`TC`/`FF`/`CC`/`MP`/`ME` 等），与 Delphi 源码知识库一致
  - `build_project_knowledge_base()` / `build_thirdparty_knowledge_base()` / `ThirdPartyKnowledgeBase` 全部改为写入双字母编码
  - `_SEARCH_TYPE_TO_KIND` 和 `_KIND_DESC` 映射同步更新
  - 已有数据库通过 UPDATE 迁移，无需重新扫描
- **移除旧格式兼容**：删除 `source_index.json` 和 `metadata.json` 写入、`_project_kb_service` 死代码
- **AGENTS.md 补充搜索策略**：引导 Agent 先猜精确类名再搜（⭐1→⭐5 优先级），减少无用语义搜索
- **`_semantic_search_embedding` 改为仅模型已加载时启用**：搜索不自动加载 embedding 模型，避免首次搜索延时

### Security

- **SQLite 连接安全**：`build_thirdparty_knowledge_base()` 添加 `try/finally` 确保异常时连接关闭

### Removed

- **帮助知识库全线删除**：`services/knowledge_base/help_knowledge_base.py`（2086 行）+ `tools/help_knowledge_base.py`（815 行）
- `kb_type` 枚举移除 `help`，清理 `server.py`、`knowledge_base.py`、`__init__.py` 中所有引用
- 移除 `_IN_PROCESS_POOL_WORKER` 环境变量（`smart_cache_knowledge_base.py`、`sqlite_vector_query_knowledge_base.py`）
- 移除 `embedding_service.py` 中未使用的 `vector_to_blob()` 函数和 `Tuple` import

## [2026.05.01] - 2026-05-01

### Removed

- **帮助知识库全线删除**：全线删除 `help_knowledge_base.py`（服务层 + 工具层，共 2901 行）
- `kb_type` 枚举移除 `help`，清理所有引用
- 功能完全由文档知识库（CHM 全文搜索）+ 源码知识库（类/函数定义）覆盖

### Added

- **文档知识库新增 CHM 格式支持**
  - `ChmProcessor`：使用 7z 解压 CHM，自动跳过图片/CSS/JS 等辅助文件
  - 搜索 7z 路径：`tools/7z/` → `Program Files` → `Program Files (x86)`
  - 未安装 7z 时返回有效下载地址（官网 / SourceForge）
- **扫描引擎优化**
  - `executor.map()` 改为 `as_completed()`，边处理边入库
  - 每 500 文档自动 commit，避免长时间锁库
  - `max_workers` 公式修复：`min(max(2, cpu_cores-1), total_files)`
  - `chunksize` 动态适配文件数，防止大量文件堆积到单个 worker
- **子进程检测简化**：`server.py` 改用 `__name__ == '__mp_main__'` 单条件检测
- 文档知识库新增 `.chm` 扩展名支持

### Changed

- AGENTS.md 更新：移除帮助 KB 引用，补充 CHM 格式说明
- `server.py` 移除 `import subprocess` 内联导入（已有模块级导入）

## [2026.04.30] - 2026-04-30

### Added

- **WinHelp (.hlp) 文档支持**：纯 Python 实现的 HlpProcessor，支持 HC30/HC31/HCW 4.00 格式
  - LZ77 解压（带 ring buffer）
  - Hall/old-style 短语解压（\|PhrIndex + \|PhrImage）
  - TOPICLINK 格式结构解析，自动拆分为多个文档
  - 增量更新支持（基于文件 mtime）
- 通用文档知识库：扫描、搜索和管理 txt/md/html/docx/doc/pdf/epub/hlp 和网页文档
- `delphi_kb` 工具新增 `action=scan/web` 和 `kb_type=document`
- 新增文档处理器：TextProcessor、MarkdownProcessor、HTMLProcessor、DocxProcessor、DocProcessor、PDFProcessor、WebDocumentProcessor、HlpProcessor
- 新增依赖 `python-docx>=0.8.11`，推荐 `PyMuPDF` 或备选 `pdfplumber`
- **项目知识库独立搜索**：`delphi_kb` 的 `kb_type=project` 改用 `ProjectKnowledgeBase` 独立查询，支持名称搜索 + 语义搜索（类/函数）
- **read_source_file 项目知识库支持**：新增 `_search_project_kb_db()` 函数及 `project_path` 参数，按路径多策略匹配
- **异步任务类型补充**：`async_task` 新增 `init_project_knowledge_base` 任务参数（project_path/version/force_rebuild/build_thirdparty/build_project）
- **扩展名扫描补充**：`DelphiSourceScanner` 扩展扫描 `.dfm`/`.fmx`/`.inc` 文件
- **共享三方库路径跳过**：项目知识库构建时自动读取共享知识库 `thirdparty_paths.json`，跳过已收录路径
- **三方库增量构建**：基于文件 hash 对比实现增量更新，输出新增/更新/跳过/删除统计

### Changed

- **异步任务参数统一**：移除 `params` 兼容写法，**仅保留 `task_params`** 参数名
- **三方库去重逻辑**：从基于 `relative_path` 改为基于 `full_path`（完整路径）去重，更准确
- `compile_project` 和 `delphi_kb` 的 `project_path` 描述补充 `.dpk` 扩展名
- 扫描器文件扩展名调整：移除 `.hpp`/`.h`，补充 `.dfm`
- **FTS5懒加载机制优化**：插入文档时不同步FTS索引，由懒加载机制按需构建
- **任务名称优化**：文档知识库构建任务显示具体操作（扫描目录/爬取网站/URL列表）
- AGENTS.md 更新：补充测试命令、代码风格指南、错误处理规范

### Fixed

- 修复异步任务参数名不一致问题，统一为 `task_params`
- 修复文档知识库构建任务名称显示"0 个URL"的问题
- 修复删除文档时未同步删除FTS5索引导致搜索结果不匹配的问题
- 修复 LZ77 解压中 match 后重置 bits_left 导致短语表崩溃的 bug
- 修复 Python 位运算溢出导致 \|PhrIndex GetBit 偏移错误
- 修复 MCP 工具定义缺少 `build_document_knowledge_base` 任务类型
- 修复三方库知识库增量构建时重复插入数据的问题（使用 `INSERT OR REPLACE`）
- 修复项目知识库搜索混入 Delphi 知识库结果的问题

## [2026.04.29] - 2026-04-29

### Added

- **FTS5 懒加载全文索引**：独立的 `FTS5LazyManager` 模块，支持按需增量构建
- 文档知识库集成 FTS5：自动降级搜索 + 后台异步构建
- 帮助知识库集成 FTS5：vocabularies 表的全文搜索
- **compile_project 支持 .dpk 文件**：自动检测设计期包并安装
- 设计期包检测：支持 `{$DESIGNONLY}`、`requires dsnide` 等标记
- 设计期包自动安装：注册到 IDE 注册表 `Known Packages`
- **逆序索引优化**：文档知识库添加 `title_lower` 和 `title_rev` 字段
- 搜索评分排序：标题匹配 > 前缀匹配 > 后缀匹配 > 内容匹配
- **delphi_kb 统一接口**：集成 `read_source_file` 功能
- **文档语言检测**：自动检测并存储 `language` 字段
- **中文搜索提示**：根据文档库语言分布智能建议翻译

### Changed

- **废弃 TF-IDF 向量索引**：未使用的向量搜索代码已移除
- 文档知识库 schema 升级：添加 `title_lower`、`title_rev`、`language` 字段
- compile_project 复用 install_package 的函数（消除重复代码）
- AGENTS.md 更新：添加 MCP 工具概述、知识库特性、组件包编译说明
- 废弃 `read_source_file` 工具，功能集成到 `delphi_kb(action=read)`

### Fixed

- 修复搜索无评分排序问题
- 修复 LIKE 全表扫描性能问题（使用逆序索引优化）
- 修复依赖检测逻辑：缺少 PDF/DOCX 依赖时正确提示

## [2026.04.29] - 2026-04-29 (2)

### Added

- Schema 版本管理机制（SCHEMA_VERSION），metadata 表记录版本号
- 知识库搜索工具支持 project/thirdparty/help 多库并行搜索
- 帮助知识库新增 `search_function` 支持
- 文件查找改为多策略路径匹配（正斜杠/反斜杠/文件名后缀），支持跨知识库自动加载

### Changed

- 工具 `search_knowledge` 更名为 `delphi_kb`，所有工具描述和参数说明改为中文
- 移除 entities 表兼容代码，统一使用 vocabularies 表（删除 421 行旧代码）
- SQLite 连接添加 `PRAGMA busy_timeout=10000` 避免 database is locked
- 移除 `use_smart_cache` 废弃参数，清理未导出工具函数
- 帮助知识库构建：自动为旧库添加 name_lower_rev 列

### Removed

- 移除 `_build_with_legacy` 方法
- 移除 `sqlite_vector_query_knowledge_base.py` 中的 `_get_file_types`、`_find_parent_from_cache`、`_find_parent_by_line_fast`、`_find_parent_by_line` 方法

## [2026.04.26] - 2026-04-26

### Fixed

- `check_environment`: detect action 传递多余参数导致报错
- `check_environment`: 补充 install/format_install action 实现
- `search_knowledge`: 搜索结果文件路径显示 N/A（使用了错误的键名）
- `search_knowledge`: search_type 参数（class/function 等）未生效，结果未按类型过滤
- `search_knowledge`: 残留 kb_types_debug 和 help_debug 调试信息
- `config.set_config_manager` 未被调用，导致 search_compilers 报"配置管理器未初始化"
- server.py 中 3 处 `[DEBUG]` print 调试输出
- 第三方库知识库旧 schema（path 列）导致索引创建失败，自动 drop 旧表重建
- unit 类型 kind code 使用单字母 'u' 而非双字母 'UI'
- 测试中 `search_by_class_name` 方法不存在（已废弃）
- server.py 中 `set_knowledge_base_service` 导入不存在（已废弃）

### Added

- `get_coding_rules` 工具：通过 MCP tool 接口暴露 Delphi 编码规范
- MCP 资源导出：`delphi://coding-rules`，AI Agent 可通过 resources 协议读取编码规则
- `search_knowledge` 中 search_type 过滤逻辑（class/record/interface/function 等）
- kind code 映射补充 TH/AT/PT 类型描述

### Changed

- 优化 8 个工具的描述：补充典型场景、action 说明、参数适用条件
- 删除 `check_environment` 中无效的 `delphi_install_dir` 参数

### Removed

- 删除 18 个废弃函数：build_knowledge_base, search_class, search_function, semantic_search, get_knowledge_base_stats, list_delphi_versions, detect_compilers, search_delphi_compilers, set_compiler_config, get_compiler_list, remove_compiler_config, get_compile_history, search_by_keywords, search_members, 2 个 main() CLI 入口等
- 删除 SINGLE_TO_DOUBLE 旧数据兼容映射
- 清理 __init__.py 中 21 个废弃导出
- 从 git 追踪中移除 logs/、data/、config/compilers.json、config/history.json

## [2026.04.25] - 2026-04-25

### Added

#### 安装脚本
- 新增 `install.ps1` 安装脚本
- 自动检测已安装的 AI Agent（Claude Desktop, Trae, CodeArts, Cursor, OpenCode, Windsurf, Cline, 通义灵码, 豆包, Kimi 等）
- 自动配置 MCP Server 到相应的 AI Agent
- 支持强制重新配置 `-Force` 参数

#### 组件包安装工具
- 新增 `install_package` 工具：编译并安装 .dproj/.dpk/.groupproj 组件包到 IDE
- 新增 `list_installed_packages` 工具：列出已安装到 IDE 的组件包
- 识别运行时包(RuntimeOnlyPackage)和设计时包，只安装设计时包
- 修复注册表键名使用完整路径而非文件名

### Changed

#### 编码规范优化
- 类型命名添加 `class of` 类型规则
- 公开字段描述修正
- 泛型格式化添加具体问题说明（嵌套泛型、继承链）
- "关键词"改为"Delphi 关键字"
- 空格规则添加括号内侧
- 预声明规则去重合并
- 验证代码正确性改为"根据项目实际情况选择使用"
- 自动更新机制添加必检/可选标记

#### AI Agent 检测增强
- CodeArts Agent: 添加 AppData\Roaming\codearts-agent 检测
- OpenCode: 添加 ai.opencode.desktop 桌面版和 npm 全局安装检测
- Cursor/Windsurf/通义灵码: 添加 AppData 目录检测
- 所有 AI Agent 现在支持多种安装方式检测

## [2026.04.02] - 2026-04-02

### Added

#### 模糊搜索 (Fuzzy Search)
- 新增 `search_type='fuzzy'` 搜索类型
- 使用反转字符串匹配 (`name_lower_rev` 列) 实现模糊搜索
- AI 翻译中文查询为英文后再搜索 (如 "创建一个按钮" → "create button")
- 支持知识库: delphi, project, thirdparty

#### 编译器自动匹配
- 从 `.dproj` 文件自动解析 `ProjectVersion`
- 根据项目版本自动选择最适配的编译器
- 版本映射: 19.x→10.4, 21.x→12 Athens, 22.x→11 Alexandria, 23.x→12 Athens
- 未找到匹配版本时使用默认编译器

### Changed

- 知识库搜索类型 enum 新增 "fuzzy" 选项
- `compile_project` 工具在未指定编译器时自动检测

## [2026.03.28] - 2026-03-28

### Added

#### 路径宏展开工具
- 新增 `src/utils/delphi_env.py` 工具模块
- 支持 `$(BDS)`, `$(BDSCatalogRepository)`, `$(BDSUSERDIR)` 等路径宏展开
- 新增 `get_catalog_repository_paths()` 函数获取 GetIt 组件源码路径
- 新增 `resolve_delphi_search_paths()` 函数整合所有搜索路径

#### 第三方库路径优化
- 使用最新安装的 Delphi 版本（23.0 而非 22.0）
- 正确过滤 Delphi 系统目录（Imports, BPL, DCP 等）
- 添加 Studio Library 注册表路径支持
- 自动添加 GetIt CatalogRepository 中的组件源码路径

### Changed

#### 知识库更新
- 重建 Delphi 知识库：3207 文件，53943 类，442206 函数
- 重建第三方库知识库：19 路径，264 文件，1584 类，20384 函数

### Fixed

#### 工具返回类型统一
- 修复 `search_compilers` 返回类型为 CallToolResult
- 修复 `get_compiler_args` 返回类型为 CallToolResult
- 修复 `get_coding_rules` 返回类型为 CallToolResult
- 修复 `check_pasfmt_installation` 返回类型为 CallToolResult
- 修复 `format_code` 返回类型为 CallToolResult

#### 搜索结果显示问题
- 修复所有搜索工具硬编码只显示 3 个结果的问题
- 修复 `knowledge_base.py` 中 `[:3]` 限制为使用 `top_k` 参数

#### 项目依赖分析
- 修复 `analyze_project_dependencies` 除零错误（当项目单元数为0时）
- 增强注册表路径宏展开支持
- 支持 GetIt 组件路径解析

#### 知识库自动加载
- 修复 `read_source_file` 知识库未自动加载问题
- 添加 KB 实例为 None 时的自动加载逻辑

### Tested

- 所有 pytest 测试通过 (11/11)
- 第三方库知识库工具测试通过
- 帮助文档知识库工具测试通过
- 项目依赖分析工具测试通过

---

## [2026.03.26] - 2026-03-26

### Added

#### pasfmt 代码格式化工具
- 新增 `format_delphi_file` 工具：格式化 Delphi 源代码文件
- 新增 `format_delphi_code` 工具：格式化 Delphi 代码字符串
- 新增 `download_and_install_pasfmt` 工具：下载并安装 pasfmt CLI
- 新增 `download_and_install_pasfmt_rad` 工具：下载并安装 pasfmt-rad IDE 插件
- 新增 `check_pasfmt_installation` 工具：检查 pasfmt 安装状态
- 新增 `check_pasfmt_rad_installation` 工具：检查 pasfmt-rad IDE 插件安装状态
- 新增 `set_pasfmt_path` 工具：设置 pasfmt 可执行文件路径

#### pasfmt 安装功能
- 支持从 GitHub 下载预编译的 pasfmt 二进制文件
- 支持多个下载镜像源
- 支持从源码编译安装（需要 Rust 工具链）
- 支持 Windows 32/64 位和 Linux
- 支持 Delphi 11/12/13 版本的 IDE 插件安装

### Changed

#### pasfmt 工具适配
- 更新命令行参数以适配 pasfmt v0.7.0：
  - `--config` → `--config-file`
  - `--check` → `--mode check`
  - `--output` → `--mode stdout`
- 优化 check 模式的返回码处理逻辑

#### 测试文件修复
- 修复测试文件中的导入路径问题
- 添加缺失的 pytest fixture

### Fixed

#### pasfmt 工具问题修复
- 修复 logger 导入问题，支持多种导入方式
- 修复默认安装路径搜索，添加项目目录 `tools/pasfmt/cli`
- 修复 `format_code` 返回值包含文件名前缀的问题
- 修复 check 模式的 issues 内容，过滤日志输出
- 支持 UTF-8 BOM 编码文件
- 支持 GBK 编码文件

### Tested
- 所有 pytest 测试通过 (11/11)
- pasfmt CLI 安装测试通过
- pasfmt-rad IDE 插件安装测试通过
- 格式化功能测试通过 (format_code, format_file)
- check 模式功能测试通过
- UTF-8/UTF-8 BOM/GBK 编码支持测试通过

## [2026.03.25] - 2026-03-25

### Added

#### SQLite 线程安全支持
- 实现线程局部存储（Thread-Local Storage）解决 SQLite 线程安全问题
- 每个线程使用独立的数据库连接，避免 `check_same_thread=False` 的绕过方案
- 新增 `_get_connection()` 和 `_close_connection()` 方法管理线程连接

#### 帮助文档知识库优化
- 默认不再自动转换 HTML 为 Markdown，提升构建性能
- 解压的 CHM 文件存储到 `data/help-knowledge-base/files` 目录
- Markdown 文件存储到 `data/help-knowledge-base/markdown` 目录（仅当用户指定时）
- 添加 `save_markdown` 参数控制是否转换 Markdown

#### 任务管理增强
- 添加任务取消功能 (`cancel_task`)
- 添加详细步骤信息显示（当前步骤、总步骤数、步骤索引）
- 添加预计剩余时间计算
- 支持任务状态查询和列表显示

#### 性能优化
- 将 HTML 扫描从线程池改为进程池，充分利用多核 CPU
- 优化进度回调频率（每10个文件报告一次）
- 添加任务取消检查机制

### Changed

#### 代码重构
- 重构 `SQLiteVectorKnowledgeBase` 类，移除 `self.conn` 实例变量
- 所有数据库操作使用 `_get_connection()` 获取线程本地连接
- 移除所有 `check_same_thread=False` 参数
- 更新异常处理，确保连接正确关闭

#### 目录结构调整
- 帮助文档解压目录从 `extracted` 改为 `files`
- Markdown 转换目录为 `markdown`（可选）

#### 默认行为变更
- `save_markdown` 参数默认值从 `True` 改为 `False`
- `cleanup_original` 参数默认值从 `True` 改为 `False`

### Fixed

#### 线程安全问题
- 修复 "SQLite objects created in a thread can only be used in that same thread" 错误
- 修复多线程环境下数据库连接冲突问题
- 修复任务管理器中的参数传递问题

#### 构建过程优化
- 修复 HTML 扫描过程中的进度报告
- 修复任务取消机制
- 修复步骤信息显示

### Tested
- 多线程搜索测试：20个并发线程全部成功
- 混合操作测试：15个混合操作线程全部成功
- 任务管理器测试：任务提交、取消、列表功能正常
- 内存泄漏测试：20次对象创建/销毁无泄漏
- 所有现有功能测试通过

## [2026.03.15] - 2026-03-15

### Added

#### 编码规则查询接口
- 新增 `get_coding_rules` 工具,用于获取 Delphi 源码编码规则
- 支持默认编码规则（当前内置源：`src/resources/coding-rules.md`；早期版本为 `config/CODING_RULES.mdc`）
- 支持项目自定义规则（项目目录下的 CODING_RULES.mdc）
- 用户自定义规则优先于默认规则
- 返回规则来源、文件路径等详细信息

#### 文档
- `docs/CODING_RULES_USAGE.md` - 编码规则接口使用说明
- `docs/INTEGRATION_TEST_REPORT.md` - 集成测试报告
- `src/resources/coding-rules.md` - 默认编码规则文件

### Changed
- 更新 `src/server.py` 集成编码规则工具

### Tested
- 所有现有测试通过（4/4）
- 新功能集成测试通过（4/4）
- 无功能冲突或兼容性问题

## [2026.03.11] - 2026-03-11

### Added

#### 项目知识库功能
- 新增 `ProjectKnowledgeBase` 类,为每个项目构建独立知识库
- 从 .dproj 文件自动提取三方库路径 (`get_thirdparty_paths_from_dproj`)
- 自动排除 Delphi 安装目录下的路径,避免重复索引
- 构建项目三方库知识库 (`build_thirdparty_knowledge_base`)
- 构建项目源码知识库 (`build_project_knowledge_base`)
- 支持增量更新:自动检测源码变动并更新知识库
- 项目知识库存储在项目目录的 `.delphi-kb/` 子目录中

#### 帮助文档知识库功能
- 新增 `DelphiHelpKnowledgeBase` 类,从 CHM 文件提取帮助文档
- 使用 7-Zip 解压 CHM 文件
- 使用 BeautifulSoup 提取 HTML 内容
- 支持以下帮助文档:
  - VCL (Visual Component Library)
  - FireMonkey (FMX)
  - System 单元
  - 运行时库 (Libraries)
  - 数据库 (Data)
  - 主题帮助 (Topics)
  - 代码示例 (CodeExamples)
  - Indy 网络组件
  - TeeChart 图表
- 帮助文档知识库存储在 `data/help-knowledge-base/` 目录

#### 新增 MCP 工具
- `init_project_knowledge_base`: 初始化项目知识库
- `search_project_class`: 在项目中搜索类定义
- `search_project_function`: 在项目中搜索函数定义
- `semantic_search_project`: 在项目中进行语义搜索
- `get_project_kb_stats`: 获取项目知识库统计信息
- `get_thirdparty_paths`: 获取项目的三方库路径
- `build_help_knowledge_base`: 构建帮助文档知识库
- `search_help`: 搜索帮助文档
- `get_help_kb_stats`: 获取帮助文档知识库统计信息

### Changed
- Delphi 源码知识库存储位置从 `~/delphi-knowledge-base` 改为 `data/delphi-knowledge-base`
- 修复 MCP 库版本兼容性问题: `CallToolResult` 从 `mcp.server.models` 移动到 `mcp.types`
- 优化三方库路径提取逻辑,自动排除 Delphi 安装目录

### Fixed
- 修复三方库知识库构建时重复文件路径导致的 UNIQUE 约束错误
- 修复 MCP Server 启动失败问题 (MCP error -32000: Connection closed)

## [2026.03.10] - 2026-03-10

### Added
- 更新项目文档和 README
- 添加项目徽章和简介
- 优化项目结构
- 发布到 GitHub

## [2026.03.09] - 2026-03-09

### Added
- 初始版本发布
- 支持项目编译 (`compile_project`)
- 支持单文件编译 (`compile_file`)
- 支持 MSBuild 编译(优先使用)
- 支持编译事件(PreBuildEvent, PostBuildEvent, PreLinkEvent)
- 支持所有 Delphi 编译事件参数(21个参数)
- 支持自动检测 Delphi 编译器(从注册表)
- 支持 Delphi 2005 到 Delphi 13 的所有版本
- 支持 10+ AI 助手配置
- 自动 .dcu 文件清理(单文件编译前)
- Delphi 源码知识库
  - 类搜索 (`search_class`)
  - 函数搜索 (`search_function`)
  - 语义搜索 (`semantic_search`)
