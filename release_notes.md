# v2026.06.15.1 Release Notes

自上一版本 v2026.06.08 以来的累积变更（包含 v2026.06.08.1 / v2026.06.12 / v2026.06.13 / v2026.06.15 / v2026.06.15.1）。

---

## 新增功能

### Delphi RTTI 桥接（v2026.06.13）
- **`delphi_rtti` MCP 工具**：通过 Enhanced RTTI 发现和调用 Delphi 应用的 published 方法
  - `action=guide`：返回完整使用指南
  - `action=discover`：扫描 Delphi 应用的所有可调用能力
  - `action=call`：调用 Delphi 应用的 published 方法
- **`DaofyAutomation.RttiDiscovery.pas`**：TRttiDiscoverer 类，支持 15 类 Delphi 类型→JSON Schema 映射
- **`src/services/rtti_bridge.py`**：RttiBridge 服务，5 分钟缓存，复用命名管道通信
- **配套测试**：22 个 rtti_bridge + 16 个 delphi_rtti 测试用例
- **Skill 分发脚本**：`scripts/build-skills.py` 支持分发到 claude-code/cursor/windsurf

### 自动化测试框架重构（v2026.06.13）
- **DaofyAutomation 三层架构拆分**：`Base.pas` / `Vcl.*.pas` / `Fmx.*.pas`，每层独立单元
- **Overlapped I/O 管道通信**：`WaitForMultipleObjects` 零延迟推送，60 秒 TTL 自动清理
- **全部命令标准化**：统一 reqId 回显，`rcall`/`rset`/`type`/`key` 改为异步
- **扩展命令集**：新增 `move`/`drag`/`key`/`waitfor`/`listwnd`/`rcall`/`dlgfile`/`peekresult`
- **FMX 截图支持**：`PaintTo`/`Context.CopyToBitmap`/`fsModal` 检测
- **Console 模式**：`automate_delphi` 新增 `action=console`/`auto`，支持 PE 头自动检测 GUI vs Console
- **测试项目**：VCL / FMX 2D / FMX 3D 三个测试程序 + 4 个 Python 测试脚本

### 编译器与项目管理（v2026.06.15）
- **Delphi >= XE5 自动启用响应文件编译**：`DCC_UseMSBuildExternally=true`，解决 MSBuild 命令行过长问题
- **项目路径支持 .dpr/.dpk**：自动检测按 `.dproj` > `.dpr` > `.dpk` 优先级搜索
- **文件路径白名单校验**：`file_tool` 集成 `PathValidator` 限制文件操作在允许目录内
- **脏标记系统**：文件写入后标记脏，再次 write 前必须 read/preview 确认行号

### 文件编辑增强（v2026.06.08.1 ~ v2026.06.15）
- **RWLock 防并发文件损坏**：`file_tool` 所有操作引入多读单写锁，并行写入自动引导为 batch_write
- **auto_format 偏移量重算**：formatting 后自动重读文件计算真实偏移差
- **format action 移除偏移量计算**：pasfmt 可能非线性重构代码，format 后仅标记脏标记
- **重复行检测降级为警告**：不再阻断写入，仅提示 AI verify 结果
- **1-indexed 行号统一**：read/write 全部统一为 1-indexed，消除 ±1 错位历史问题
- **读取自动清除脏标记**：read 成功后自动清除脏标记
- **`uses_style="compact"`**：pasfmt 格式化后 uses 子句可合并回单行

## Bug 修复

- **批量写入 orig_e_display 导出错误**：`e` 为 None（替换到文件末尾）时偏移显示错误
- **auto_format 后 fmt_diff 未初始化**：pasfmt 未格式化时局部变量可能未定义
- **format action 遗留代码清理**：移除格式化前后行数计算的无用代码（~20 行）
- **console_execute Windows pipe 读取**：`select.select` 不适用于 Windows pipe，改为 thread + Queue
- **batch_write experimental 标记移除**：batch_write 正式作为标准接口
- **batch_write content 首行重复检测修正**：s=0 时（文件头替换）不再误报
- **`tool_docs.py`/`server.py` 参数同步**：delphi_rtti 注册；delphi_file 统一 edits 参数格式

## 重构与改进

- **`compiler_service` typing 迁移至原生泛型**（v2026.06.15.1）：移除 `typing.List`，4 处迁移至 `list[str]`/`list[Path]`
- **`file_tool` 重构**（v2026.06.13）：统一 1-indexed 行号体系，+297 / -605 行
- **`CODING_RULES.mdc` 规则重构**：全面重写 delphi_file 写入规则、紧凑输出格式、脏标记保护
- **`AGENTS.md` 精简**：详细规则迁移至 `CODING_RULES.mdc`，仅保留工作流总览
- **`project_knowledge_base` 日志降级**：非 `.dproj` 文件的三方库路径提取降为 debug
- **tools/7z/7z.dll 打包**：补齐 7z.dll（1.9MB），确保 release 包开箱可用
- **经验库维护规则更新**：保存前先泛化、embedding 自动补全、抽象合并

## 文档

- **`docs/automate_test_guide.md`**：完整 GUI 自动化测试指南
- **`docs/delphi_file.md`**：行号规则与偏移量说明
- **`docs/tutorial/`**：自动测试教程（含 VCL/FMX 3D 演示项目）
- **CODING_RULES.mdc 新增章节**：§⑧ 自动化UI交互测试、§⑨ 控制台程序交互验证
- **`tool_help` 新增 auto_unit_paths 显示**：DaofyAutomation 单元选择提示
- **`.windsurfrules`**：Windsurf 规则配置

---

**版本标签**: `v2026.06.15.1`
**完整日志**: [CHANGELOG.md](CHANGELOG.md)