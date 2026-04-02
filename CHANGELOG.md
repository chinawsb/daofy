# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- 支持默认编码规则（config/CODING_RULES.mdc）
- 支持项目自定义规则（项目目录下的 CODING_RULES.mdc）
- 用户自定义规则优先于默认规则
- 返回规则来源、文件路径等详细信息

#### 文档
- `docs/CODING_RULES_USAGE.md` - 编码规则接口使用说明
- `docs/INTEGRATION_TEST_REPORT.md` - 集成测试报告
- `config/CODING_RULES.mdc` - 默认编码规则文件

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
