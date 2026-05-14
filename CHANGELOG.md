# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
