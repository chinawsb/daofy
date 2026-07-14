<!-- Daofy 常驻 Rule（安装到各 MCP 客户端规则目录）。
     本文件是"强制路由"的权威常驻副本：所有 Delphi 相关任务必须路由到 Daofy 工具。
     分层（避免重复注入）：
       - 协议层兜底：MCP initialize.instructions（覆盖所有 honor instructions 的客户端）
       - 详细用法：daofy skill（按需加载，不含本约束）
       - 深度规范：get_coding_rules(section=...)（按需加载）
     本文件只放"必须时刻在场"的路由约束，不堆详细用法。 -->
# Daofy Delphi 强制路由规则（所有 Delphi 任务必须走 Daofy，禁止裸跑 shell/IDE 内置）

**任何 Delphi 相关操作都必须通过当前已连接的 Daofy MCP Server 提供的工具完成，**
**禁止使用 shell(PowerShell)/Python 直接执行 dcc32/dcc64/msbuild/bcc 等 Delphi 命令，**
也禁止使用 Agent / IDE 内置的 Read / Edit / Write / grep 直接读写 Delphi 文件。

适用扩展名：
`.pas` `.dpr` `.dpk` `.dfm` `.fmx` `.inc` `.dproj` `.groupproj`

## 任务 → Daofy 工具映射（按此路由，不要猜）
| 任务 | 必须用 | 禁止 |
| --- | --- | --- |
| 读 / 写 / 搜索 / 正则替换 Delphi 文件 | `daofy.delphi_file(action=read/write/replace/insert/delete/grep)` | 内置 Read/Edit/Write/grep、shell cat/sed |
| **检测编译器 / DCC 环境**（如 dcc32/dcc64 在哪、是否存在） | `daofy.check_environment(action="detect")` （首次编译前先 `check`） | `where dcc32`、`dcc64 --version` 等 shell 探测 |
| **编译 / 构建 Delphi 工程** | `daofy.delphi_project(action="compile"/"compile_file"/"dry_run")` | 手动 `dcc32` / `msbuild` |
| 工程配置查看 / 审计 / AST / 布局 | `daofy.delphi_project(action=info/audit/ast/layout/runtime)` | — |
| 查 API / 类 / 函数 / 工程符号 | `daofy.delphi_kb` | — |
| 编码 / 编译前规范 | `daofy.get_coding_rules(section=...)` | — |
| 所有 Git 操作 | `daofy.code_hosting` | shell 里直接 `git ...` |

## 为什么
- **文件读写**：Delphi 源码常见 UTF-8 BOM / GBK / ANSI，默认工具会按无 BOM UTF-8 或系统 ANSI 重写，
  导致 BOM 丢失、中文乱码、行尾被改写。`delphi_file` 自动保留原编码/BOM，并提供备份、edit guard 等保护。
- **环境/编译**：Delphi 编译器路径、版本、SDK 依赖由 Daofy 统一探测与缓存；裸跑 `dcc32/msbuild`
  容易因 PATH、注册表、平台(win32/win64)、条件编译符号不一致而失败或编出错误目标。

## 例外
- 非 Delphi 文件（Python / Markdown / 配置 / 测试脚本）可按普通流程处理。
- 纯信息查询（如查看 Daofy 工具参数）可用 `daofy.tool_help(tool_name=...)`，不在此限。

<!-- daofy-managed-rule: true -->
