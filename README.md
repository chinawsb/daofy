# Delphi MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![Delphi 2005-13](https://img.shields.io/badge/Delphi-2005%20to%2013-red.svg)

一个为 AI 助手(如 Claude Desktop、CodeArts Agent 等)提供 Delphi 工程编译能力和知识库查询功能的 MCP Server。如果您觉得有用，请不要吝啬您的 Star! ⭐

## 项目简介

Delphi MCP Server 是一个基于 Model Context Protocol (MCP) 的服务器,它允许 AI 助手直接编译 Delphi 项目并查询 Delphi 知识库。通过这个工具,您可以在与 AI 助手的对话中直接编译 Delphi 工程、查询 API 文档、搜索代码示例,无需手动切换到 IDE 或命令行。

**主要优势:**

- 无缝集成到 AI 助手工作流中
- 自动检测和配置 Delphi 编译器
- 内置 Delphi 源码知识库,支持语义搜索
- 项目级知识库,自动追踪三方库和项目源码
- 通用文档知识库支持 Delphi CHM 帮助文档全文搜索
- 支持所有主流 AI 助手平台
- 完整的编译事件支持
- 详细的错误诊断和日志

## 功能特性

### 编译功能

- **工程整体编译**: 支持编译完整的 Delphi 工程(.dproj/.dpr),生成可执行文件或动态链接库
- **MSBuild 编译**: 优先使用 MSBuild 编译,自动处理依赖关系和编译事件
- **单文件编译**: 支持编译单个 Delphi 单元文件(.pas),进行语法检查
- **自动检测编译器**: 自动从注册表检测已安装的 Delphi 编译器,无需手动配置
- **智能库路径解析**: 自动分析项目依赖，智能选择需要的第三方库路径，避免命令行过长
- **编译事件支持**: 支持 PreBuildEvent、PostBuildEvent、PreLinkEvent,包含完整的参数替换
- **命令行参数生成**: 支持生成 Delphi 编译器命令行参数,便于调试和预览
- **编译器配置管理**: 支持配置和管理多个 Delphi 编译器版本
- **环境检查**: 提供编译器环境状态检查功能
- **丰富的编译选项**: 支持条件编译符号、搜索路径、优化选项、调试信息、警告控制等

### 知识库功能

- **Delphi 源码知识库**: 内置 Delphi 官方源码知识库,支持类、函数搜索和语义搜索
- **项目知识库**: 为每个项目构建独立知识库,自动追踪三方库和项目源码
- **三方库知识库**: 从 .dproj 文件自动提取三方库路径并构建知识库
- **增量更新**: 自动检测源码变动,增量更新项目知识库
- **通用文档知识库**: 支持 txt/md/html/docx/doc/pdf/epub/hlp/chm 和网页文档的扫描与搜索
  - 必需依赖: `beautifulsoup4`, `html2text`, `lxml`, `requests` (已在 requirements.txt)
  - 可选依赖: `python-docx` (Word .docx 支持), `antiword/catdoc` (旧版 Word .doc 支持), `PyMuPDF` (PDF 支持，推荐) 或 `pdfplumber` (PDF 支持，备选)
- **智能去重**: 基于完整路径去重，正确处理同名不同目录的文件

### 构建 Delphi 帮助文档知识库

用户首次使用或需要重建 Delphi API 文档时，调用 `delphi_kb` 工具构建文档知识库：

```
delphi_kb(
    action="build",
    kb_type="document",
    async_mode=true
)
```

说明：
- **不传 directory 时自动检测**最新安装的 Delphi 帮助目录（通过注册表或默认路径）
- 也可手动指定：`directory="C:\Program Files (x86)\Embarcadero\Studio\<版本>\Help\Doc"`
  - 版本对照：37.0=Delphi 13, 23.0=Delphi 12, 22.0=Delphi 11, 21.0=Delphi 10.4, 20.0=Delphi 10.3
- `extensions=[".chm"]`：只扫描 CHM 文件，工具会自动解压并导入 HTML 文档
- `async_mode=true`：异步执行（耗时数分钟），提交后返回 task_id，通过 `async_task(action=status, task_id=...)` 轮询进度
- 需要系统安装 7-Zip（可放在 `tools/7z/` 目录下免安装）

### 编码规范功能

- **编码规则查询**: 获取 Delphi 源码编码规则,供 AI 助手用于代码审核和生成
- **默认规则支持**: 内置默认编码规则文件,包含命名规则、格式化规则、修改规则和审核规则
- **自定义规则支持**: 支持项目级别的自定义编码规则,优先于默认规则
- **规则优先级**: 项目自定义规则 > 默认规则

## MCP 工具列表

### 编译相关工具

| 工具名称 | 功能描述 | 主要参数 |
|----------|----------|----------|
| `compile_project` | 编译 Delphi 项目或检查 .pas 文件语法 | `project_path`, `target_platform`(win32/win64), `build_configuration`(Debug/Release), `output_path`, `timeout`, `debug_info_enabled`, `get_args_only`(可选) |
| `check_environment` | 诊断编译环境、检测编译器、安装pasfmt | `action`(check/detect/install/format_install), `search_path`, `install_dir`, `delphi_version` |
| `install_package` | 编译并安装 Delphi 组件包到 IDE | `package_path`, `target_platform`, `build_configuration`, `timeout`, `install` |
| `list_installed_packages` | 列出已安装到 IDE 的 Delphi 组件包 | - |
| `get_coding_rules` | 获取 Delphi 编码规范(命名/格式化/审核规则) | `project_path`(可选) |

### 知识库工具

| 工具名称 | 功能描述 | 主要参数 |
|----------|----------|----------|
| `delphi_kb` | 搜索代码/类/函数/文档，查看统计或构建知识库 | `action`(search/stats/build/scan/web), `query`, `kb_type`(all/delphi/project/thirdparty/document), `search_type`, `top_k`, `project_path`(项目知识库可选，不传时自动从当前目录检测 .dproj), `directory`(扫描目录, 构建文档KB时可省略自动检测), `url`(网页URL), `content_type`(文档类型), `extensions`(文件扩展名) |

### 源码读取工具

| 工具名称 | 功能描述 | 主要参数 |
|----------|----------|----------|
| `read_source_file` | 读取指定文件内容或搜索类/函数位置 | `file_path`, `search_type`(path/class/function), `type_name`, `function_name`, `search_in`, `project_path`(项目知识库查找), `start_line`, `max_lines` |

### 代码格式化工具

| 工具名称 | 功能描述 | 主要参数 |
|----------|----------|----------|
| `format_delphi` | 格式化 Delphi 源码/代码，检查/设置 pasfmt | `action`(file/code/check/set_path/status), `file_path`, `code`, `backup`, `in_place`, `path`, `check_rad`, `delphi_version` |

### 异步任务工具

| 工具名称 | 功能描述 | 主要参数 |
|----------|----------|----------|
| `async_task` | 管理后台任务（构建知识库等） | `action`(start/status/result/list/cancel), `task_id`, `task_type`, `task_params`, `show_progress` |

### 编码规范工具

| 工具名称 | 功能描述 | 主要参数 |
|----------|----------|----------|
| `get_coding_rules` | 获取 Delphi 编码规范(命名/格式化/审核规则) | `project_path`(可选) |

## 系统要求

- Python 3.10-3.14
- Delphi 编译器(dcc32.exe 或 dcc64.exe)
- Windows 操作系统
- Git
- 7-Zip (用于解压 CHM 帮助文件,可选)

## 知识库存储位置

所有知识库数据存储在项目根目录的 `data/` 文件夹下：

| 知识库类型 | 存储路径 | 说明 |
|-----------|---------|------|
| Delphi 源码知识库 | `data/delphi-knowledge-base/` | Delphi 官方源码 (RTL/VCL/FMX 等) |
| 第三方库知识库 | `data/thirdparty-knowledge-base/` | 第三方组件库源码 |
| 通用文档知识库 | `data/document-knowledge-base/` | Delphi CHM 帮助文档 + 通用文档 |
| 项目知识库 | `<项目目录>/.delphi-kb/` | 项目级知识库，存放在项目目录下 |

每个知识库目录包含：
- `documents.sqlite` / `knowledge_base.sqlite` / `knowledge.sqlite` - SQLite 数据库文件
- `config.json` - 知识库配置文件

## 知识库配置说明

每个知识库通过 `config.json` 文件进行配置，支持自定义数据库、源码路径、构建参数等。

### Delphi 源码知识库配置

位置：`data/delphi-knowledge-base/config.json`

```json
{
  "name": "delphi-knowledge-base",
  "type": "delphi-source",
  "version": "2.0",
  "source": {
    "type": "link",
    "path": "C:\\Program Files (x86)\\Embarcadero\\Studio\\22.0\\source",
    "extensions": [".pas", ".dfm", ".inc"],
    "encoding": "utf-8"
  },
  "database": {
    "file": "knowledge_base.sqlite",
    "cache_size": 10000
  },
  "build": {
    "auto_rebuild": false,
    "incremental": true,
    "incremental_hash_mode": "mtime_size",
    "parallel_workers": 4,
    "batch_size": 1000
  }
}
```

| 配置项 | 说明 | 默认值 |
|-------|------|--------|
| `source.type` | 源码类型：`link`=符号链接，`copy`=复制 | `link` |
| `source.path` | Delphi 源码根目录 | 自动检测 |
| `source.extensions` | 扫描的文件扩展名 | `[".pas", ".dfm", ".inc"]` |
| `database.file` | 数据库文件名 | `knowledge_base.sqlite` |
| `database.cache_size` | 向量缓存大小 | `10000` |
| `build.incremental` | 是否增量构建 | `true` |
| `build.incremental_hash_mode` | 变更检测：`mtime_size`=快速，`md5`=准确 | `mtime_size` |
| `build.parallel_workers` | 并行工作进程数 | 自动计算 |
| `build.batch_size` | 批处理大小 | `1000` |

### 通用文档知识库配置

位置：`data/document-knowledge-base/config.json`

```json
{
  "name": "document-knowledge-base",
  "type": "generic-documents",
  "version": "1.0",
  "database": {
    "file": "documents.sqlite"
  },
  "build": {
    "parallel_workers": null,
    "batch_size": 50,
    "supported_extensions": [".txt", ".md", ".markdown", ".htm", ".html", ".docx", ".doc", ".pdf", ".hlp"]
  }
}
```

| 配置项 | 说明 | 默认值 |
|-------|------|--------|
| `database.file` | 数据库文件名 | `documents.sqlite` |
| `build.parallel_workers` | 并行工作进程数（`null`=自动计算） | `null` |
| `build.batch_size` | 批处理大小 | `50` |
| `build.supported_extensions` | 支持的文档格式 | 9 种格式 |

### 第三方库知识库配置

位置：`data/thirdparty-knowledge-base/config.json`

配置格式与 Delphi 源码知识库相同，通过 `delphi_kb(action=build, kb_type=thirdparty)` 自动生成。

### 项目知识库配置

位置：`<项目目录>/.delphi-kb/config.json`

项目知识库配置会在首次构建时自动生成，包含项目源码路径和第三方库路径。

### 配置项生效说明

所有配置项在缺失时使用默认值，保证系统正常运行：

- ✅ `database.file` - 生效
- ✅ `database.cache_size` - 生效
- ✅ `source.type/path` - 生效
- ✅ `build.incremental_hash_mode` - 生效
- ✅ `build.parallel_workers` - 生效
- ✅ `build.batch_size` - 生效
- ✅ `build.supported_extensions` - 生效（文档知识库）

## 安装

### AI 助手自动安装提示词

请按以下步骤安装 Delphi MCP Server:

[] 检查并安装 Git/Python 3.10-3.14/7-Zip (安装时优先使用国内镜像源加速下载)

[] 安装 `https://github.com/chinawsb/delphi-complier-mcp-server.git`

[] 安装完成后验证结果并帮我配置当前客户端

### 手动安装步骤

#### 1. 克隆或下载项目

```bash
git clone https://github.com/chinawsb/delphi-complier-mcp-server.git
cd delphi-complier-mcp-server
```

#### 2. 创建虚拟环境

```bash
python -m venv venv
```

#### 3. 激活虚拟环境

Windows:

```bash
venv\Scripts\activate
```

Linux/macOS:

```bash
source venv/bin/activate
```

#### 4. 安装依赖 (使用国内镜像源加速)

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

可选国内镜像源:

- 清华大学: <https://pypi.tuna.tsinghua.edu.cn/simple>
- 阿里云: <https://mirrors.aliyun.com/pypi/simple/>
- 中科大: <https://pypi.mirrors.ustc.edu.cn/simple/>

## 配置 AI 助手

### 自动检测 Delphi 编译器

**首次使用时,MCP Server 会自动从 Windows 注册表检测已安装的 Delphi 编译器,无需手动配置。**

自动检测支持的 Delphi 版本:

- Delphi 13 Florence (37.0)
- Delphi 12 Athens (23.0)
- Delphi 11 Alexandria (22.0)
- Delphi 10.4 Sydney (21.0)
- Delphi 10.3 Rio (20.0)
- Delphi 10.2 Tokyo (19.0)
- Delphi 10.1 Berlin (18.0)
- Delphi 10 Seattle (17.0)
- Delphi XE8 (16.0)
- Delphi XE7 (15.0)
- Delphi XE6 (14.0)
- Delphi XE5 (12.0)
- Delphi XE4 (11.0)
- Delphi XE3 (10.0)
- Delphi XE2 (9.0)
- Delphi XE (8.0)
- Delphi 2010 (7.0)
- Delphi 2009 (6.0)
- Delphi 2007 (5.0)
- Delphi 2006 (4.0)
- Delphi 2005 (3.0)

### 手动配置编译器 (可选)

如果需要手动配置或添加自定义编译器,可以直接编辑 `config/compilers.json` 文件,或使用 `check_environment` 工具的 `detect` action 重新检测。

### 配置 Claude Desktop

#### Claude Desktop

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "delphi-compiler": {
      "command": "python",
      "args": ["C:\\path\\to\\delphi_mcp_server\\src\\server.py"],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

### 配置 Trae

**Windows**: `C:\Users\<用户名>\.trae-cn\mcp_config.json`

```json
{
  "mcpServers": {
    "delphi-compiler": {
      "command": "F:\\ProPlus\\DelphiPlus\\Experts\\DelphiMCPServer\\delphi-complier-mcp-server\\venv\\Scripts\\python.exe",
      "args": [
        "F:\\ProPlus\\DelphiPlus\\Experts\\DelphiMCPServer\\delphi-complier-mcp-server\\src\\server.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

**注意**: 请将路径修改为您的实际安装路径。

### 配置 CodeArts Agent

**Windows**: `~/.codeartsdoer/mcp/mcp_settings.json`

```json
{
  "mcpServers": {
    "delphi-compiler": {
      "command": "python",
      "args": ["src\\server.py"],
      "cwd": "C:\\path\\to\\delphi_mcp_server",
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

## 使用方法

### 知识库统计

| 知识库       | 文档数     | 类数量    | 函数数量    |
| --------- | ------- | ------ | ------- |
| Delphi 源码 | 3,081   | 17,731 | 168,925 |
| 通用文档      | 160,328 | -      | -       |

## 故障排除

### 1. 编译器未找到

**解决方案**:

- 检查 `config/compilers.json` 文件中的编译器路径是否正确
- 使用 `check_environment` 工具 `action=detect` 重新检测编译器

### 2. MCP Server 无法启动

**解决方案**:

- 检查 Python 环境是否正确配置
- 检查依赖是否已安装: `pip install -r requirements.txt`
- 检查 MCP 库版本: `pip show mcp`

### 3. 知识库搜索无结果

**解决方案**:

- 确保已构建知识库: 使用 `delphi_kb` 工具的 action=build 构建
- 检查知识库目录是否存在

## 许可证

MIT License

Copyright (c) 2026 吉林省左右软件开发有限公司
Copyright (c) 2026 Equilibrium Software Development Co., Ltd, Jilin

详见 [LICENSE](LICENSE) 文件。

## 版本历史

### v2026.05.01 (2026-05-01)

- **移除帮助知识库**
  - 全线删除 `help_knowledge_base.py`（服务层 + 工具层，共 2901 行）
  - `kb_type` 枚举移除 `help`，清理所有引用
  - 功能完全由文档知识库（CHM 全文搜索）+ 源码知识库（类/函数定义）覆盖
- **文档知识库新增 CHM 格式支持**
  - `ChmProcessor`：使用 7z 解压 CHM，自动跳过图片/CSS/JS 等辅助文件
  - 搜索 7z 路径：`tools/7z/` → `Program Files` → `Program Files (x86)`
  - 未安装 7z 时返回有效下载地址（官网 / SourceForge）
- **扫描引擎优化**
  - `executor.map()` 改为 `as_completed()`，边处理边入库
  - 每 500 文档自动 commit，避免长时间锁库
  - `max_workers` 公式修复：`min(max(2, cpu_cores-1), total_files)`
  - `chunksize` 动态适配文件数，防止大量文件堆积到单个 worker
- **清理冗余代码**
  - 移除 `_IN_PROCESS_POOL_WORKER` 环境变量（已由 `__name__ == '__mp_main__'` 覆盖）
  - 清理 `add_web_document` 中多余的内层 `import subprocess`

### v2026.04.30 (2026-04-30)

- **新增 WinHelp (.hlp) 文档支持**
  - 纯 Python 实现 WinHelp 文件解析器（HlpProcessor）
  - 支持 HC30/HC31/HCW 4.00 格式，LZ77 解压（带 ring buffer）
  - 支持 Hall/old-style 短语解压（\|PhrIndex + \|PhrImage）
  - 解析 TOPICLINK 格式结构，自动拆分为多个文档
  - 增量更新支持（基于文件 mtime）
- **异步任务优化**
  - 统一使用 `task_params` 参数名，移除旧 `params` 兼容写法
  - 任务名称显示具体操作（扫描目录/爬取网站/URL列表）
  - 新增 `init_project_knowledge_base` 任务类型支持
- **FTS5 懒加载机制优化**
  - 插入文档时不同步 FTS 索引，由懒加载机制按需构建
  - 删除文档时同步删除 FTS 索引，避免搜索结果不匹配
- **项目知识库搜索增强**
  - 独立使用 `ProjectKnowledgeBase` 查询项目知识库，不再混入 Delphi 知识库
  - 支持名称搜索 + 语义搜索（类/函数）
- **read_source_file 增强**
  - 新增 `project_path` 参数，支持在项目知识库中按路径多策略匹配查找文件
- **三方库知识库增量构建**
  - 基于文件 hash 对比实现增量更新，输出新增/更新/跳过/删除统计
  - 去重逻辑改为基于完整路径（full_path）
- **共享三方库路径跳过**
  - 项目知识库构建时自动读取共享 `thirdparty_paths.json`，跳过已收录路径
- **扫描扩展名补充**
  - `.dfm`/`.fmx`/`.inc` 文件加入源码扫描范围
  - 扫描器移除 `.hpp`/`.h` 扩展名
- **修复多个 Bug**
  - 修复异步任务参数名不一致问题
  - 修复 LZ77 解压短语表崩溃 bug
  - 修复 Python 位运算溢出导致 GetBit 偏移错误
  - 修复 MCP 工具定义缺少 `build_document_knowledge_base` 任务类型
  - 修复三方库知识库增量构建重复插入数据问题
  - 修复项目知识库搜索结果混入 Delphi 知识库的问题

### v2026.04.29 (2026-04-29)

- 工具 `search_knowledge` 更名为 `delphi_kb`，所有描述改为中文
- 新增 Schema 版本管理机制（SCHEMA_VERSION），metadata 记录版本号
- 移除 entities 表兼容代码，统一使用 vocabularies 表
- SQLite 连接添加 busy_timeout=10000 避免 database is locked
- 知识库搜索支持 project/thirdparty/help 多库并行搜索
- 帮助知识库新增 search_function 支持
- 文件查找改为多策略路径匹配，支持跨知识库自动加载

### v2026.04.26 (2026-04-26)

- 修复 MCP 接口多个 bug
  - `check_environment`: detect action 参数传递错误；补充 install/format_install action 实现
  - `search_knowledge`: 搜索结果文件路径显示 N/A（键名错误）；search_type 过滤未生效
  - 遗漏调用 `config.set_config_manager` 导致 `search_compilers` 报配置管理器未初始化
- 新增 `get_coding_rules` 工具，通过 MCP tool 接口暴露编码规范
- 新增 MCP 资源导出（`delphi://coding-rules`），AI Agent 可通过 resources 协议读取编码规则
- 清理无效旧代码（净删除 1251 行）
  - 删除 18 个废弃函数（build_knowledge_base, search_class, search_function, semantic_search 等）
  - 删除 5 个废弃配置函数（set_compiler_config, detect_compilers, search_delphi_compilers 等）
  - 清理 __init__.py 中 21 个废弃导出
- 修复第三方库知识库旧 schema 兼容问题（自动 drop 旧表重建）
- 修复 unit 类型 kind code 从单字母 'u' 改为双字母 'UI'
- 删除未使用的 SINGLE_TO_DOUBLE 旧数据兼容映射
- 优化 8 个工具的描述：补充典型场景、action 说明、参数适用条件

### v2026.04.25 (2026-04-25)

- 新增安装脚本 `install.ps1`
  - 自动检测已安装的 AI Agent（Claude Desktop, Trae, CodeArts, Cursor, OpenCode, Windsurf, Cline, 通义灵码, 豆包, Kimi 等）
  - 自动配置 MCP Server 到相应的 AI Agent
  - 支持强制重新配置

- 完善 AI Agent 检测逻辑
  - CodeArts Agent: 添加 AppData\Roaming\codearts-agent 检测
  - OpenCode: 添加 ai.opencode.desktop 桌面版和 npm 全局安装检测
  - Cursor/Windsurf/通义灵码: 添加 AppData 目录检测

- 新增组件包安装工具
  - `install_package`: 编译并安装 .dproj/.dpk/.groupproj 组件包到 IDE
  - `list_installed_packages`: 列出已安装到 IDE 的组件包
  - 识别运行时包(RuntimeOnlyPackage)和设计时包，只安装设计时包

- 优化编码规范（见上文）

### v2026.03.29 (2026-03-29)

- 修复编译参数问题
  - 修复 `$(BDSLIB)` 宏展开路径错误（原路径 `lib\$(Platform)` 导致双重展开）
  - 修复 `BDSCOMMONDIR` 环境变量分割逻辑错误
  - 移除非必要引号（`asyncio.create_subprocess_exec` 自动处理空格路径）
  - 添加默认命名空间 `-NS` 参数解决 SysUtils 等单元解析问题
  - 更新参数验证逻辑，允许路径参数中的分号和括号

- 修复项目依赖分析
  - 添加 thirdparty KB 路径到搜索路径列表
  - 支持大小写不敏感匹配（madbasic → madBasic）

- 统一工具返回类型
  - `compile_project` 返回 `CallToolResult`
  - `compile_file` 返回 `CallToolResult`
  - `get_compiler_args` 返回 `CallToolResult`

- 工具整合
  - 合并搜索函数到 `search_knowledge`
  - 合并构建函数到 `build_knowledge`
  - 合并统计函数到 `get_knowledge_stats`

- 所有 pytest 测试通过 (15/15)

### v2026.03.28 (2026-03-28)

- 新增路径宏展开工具
  - 新增 `src/utils/delphi_env.py` 工具模块
  - 支持 `$(BDS)`, `$(BDSCatalogRepository)`, `$(BDSUSERDIR)` 等路径宏展开
  - 新增 `get_catalog_repository_paths()` 函数获取 GetIt 组件源码路径
  - 新增 `resolve_delphi_search_paths()` 函数整合所有搜索路径

- 优化第三方库路径处理
  - 使用最新安装的 Delphi 版本（23.0 而非 22.0）
  - 正确过滤 Delphi 系统目录（Imports, BPL, DCP 等）
  - 添加 Studio Library 注册表路径支持
  - 自动添加 GetIt CatalogRepository 中的组件源码路径

- 重建知识库
  - Delphi 知识库：3207 文件，53943 类，442206 函数
  - 第三方库知识库：19 路径，264 文件，1584 类，20384 函数

- 修复工具返回类型问题
  - 修复 `search_compilers` 返回类型为 CallToolResult
  - 修复 `get_compiler_args` 返回类型为 CallToolResult
  - 修复 `get_coding_rules` 返回类型为 CallToolResult
  - 修复 `check_pasfmt_installation` 返回类型为 CallToolResult
  - 修复 `format_code` 返回类型为 CallToolResult

- 修复搜索结果显示问题
  - 修复所有搜索工具硬编码只显示 3 个结果的问题
  - 修复 `knowledge_base.py` 中 `[:3]` 限制为使用 `top_k` 参数

- 修复项目依赖分析
  - 修复 `analyze_project_dependencies` 除零错误（当项目单元数为0时）
  - 增强注册表路径宏展开支持
  - 支持 GetIt 组件路径解析

- 修复知识库自动加载
  - 修复 `read_source_file` 知识库未自动加载问题
  - 添加 KB 实例为 None 时的自动加载逻辑

- 所有 pytest 测试通过 (11/11)

### v2026.03.26 (2026-03-26)

- 新增 pasfmt 代码格式化工具
  - 新增 `format_delphi_file` 工具，格式化 Delphi 源代码文件
  - 新增 `format_delphi_code` 工具，格式化 Delphi 代码字符串
  - 新增 `install_pasfmt` 工具，下载并安装 pasfmt CLI 或 IDE 插件
  - 新增 `check_pasfmt_installation` 工具，检查 pasfmt 安装状态
  - 新增 `set_pasfmt_path` 工具，设置 pasfmt 可执行文件路径
- 支持从 GitHub 下载预编译的 pasfmt 二进制文件（支持 Windows 32/64 位和 Linux）
- 支持 Delphi 11/12/13 版本的 IDE 插件安装
- 适配 pasfmt v0.7.0 命令行参数
- 支持 UTF-8/UTF-8 BOM/GBK 编码文件
- 修复测试文件导入路径问题

### v2026.03.21 (2026-03-21)

- 新增帮助文档知识库构建功能
  - 新增 `build_help_kb_index` 工具，构建帮助文档向量索引
  - 支持增量构建，可指定外部源目录
  - 支持限制处理文件数量，便于小范围测试
- 增强帮助文档内容提取
  - HTML 转 Markdown，保留更好的结构化信息
  - 提取类、接口、类型、函数、属性、事件、常量等结构化信息
  - 提取方法签名（支持 Delphi 和 C++ 语法）、参数、返回值
  - 提取代码示例（优先从 HTML 提取，支持语法高亮识别）
  - 提取 Uses 引用单元信息（代码示例页面）
  - 保存完整文档内容（最多3000字符用于索引），为 AI 提供充足学习材料
- 改进搜索功能
  - `search_help` 支持语义搜索类、函数和文档
  - 搜索结果包含描述信息和相似度分数
- 新增项目依赖分析功能
  - 新增 `analyze_project_dependencies` 工具，分析项目单元依赖关系
  - 新增 `resolve_smart_library_paths` 工具，智能解析项目需要的第三方库路径
- 优化编译功能
  - `compile_project` 支持智能库路径解析，自动分析项目依赖并选择需要的库路径
  - 动态从注册表获取 Delphi 安装路径，不再硬编码 rsvars.bat 路径
  - 优先使用项目目录下的单元，正确处理同名文件
- 优化知识库去重逻辑
  - 基于完整路径去重，正确处理同名不同目录的文件
  - 保留相对路径和完整路径，查询结果更合理
- 新增源码文件读取功能
  - 新增 `read_source_file` 工具，先在知识库中定位文件，再从磁盘读取源码内容
  - 新增 `search_and_read_file` 工具，搜索类型（类/record/interface）或函数并自动读取所在文件内容
  - 支持指定行号范围读取，便于查看特定代码段
- 增强类型搜索功能
  - 新增 `search_by_filename` 工具，支持按文件名通配符搜索
  - 扩展知识库扫描，支持 class、record、interface、enum 等多种类型
  - 搜索结果添加 `type_kind` 字段，显示类型种类（class/record/interface/enum）

### v2026.03.20 (2026-03-20)

- 新增全局第三方库知识库功能
  - 新增 `get_thirdparty_paths` 工具，获取第三方库路径列表
  - 新增 `search_thirdparty_class` 工具，在第三方库中搜索类
  - 新增 `search_thirdparty_function` 工具，在第三方库中搜索函数
  - 新增 `semantic_search_thirdparty` 工具，在第三方库中进行语义搜索
  - 新增 `get_thirdparty_kb_stats` 工具，获取第三方库知识库统计信息
- 优化帮助文档知识库构建
  - 支持异步模式，避免超时
  - 新增 `get_task_status` 工具，查询后台任务状态
  - 新增 `list_tasks` 工具，列出所有后台任务
- 完全向后兼容

### v2026.03.15 (2026-03-15)

- 新增编码规范功能
  - 新增 `get_coding_rules` 工具,用于获取 Delphi 源码编码规则
  - 支持默认编码规则（config/CODING\_RULES.mdc）
  - 支持项目自定义规则（项目目录下的 CODING\_RULES.mdc）
  - 用户自定义规则优先于默认规则
- 完整的测试验证和文档说明
- 不影响现有功能,完全向后兼容

### v2026.03.11 (2026-03-11)

- 新增项目知识库功能
  - 从 .dproj 文件自动提取三方库路径
  - 构建项目三方库知识库
  - 构建项目源码知识库,支持增量更新
- 新增帮助文档知识库功能
  - 从 CHM 文件提取帮助文档
  - 支持 VCL、FMX、System 等帮助文档
- 新增知识库 MCP 工具接口
- 修复 MCP 库版本兼容性问题
- 优化知识库存储位置

### v2026.03.10 (2026-03-10)

- 更新项目文档和 README
- 添加项目徽章和简介
- 优化项目结构
- 发布到 GitHub

### v2026.03.09 (2026-03-09)

- 初始版本发布
- 支持项目编译和单文件编译
- 支持 MSBuild 编译(优先使用)
- 支持编译事件(PreBuildEvent, PostBuildEvent, PreLinkEvent)
- 支持所有 Delphi 编译事件参数(21个参数)
- 支持自动检测 Delphi 编译器(从注册表)
- 支持 Delphi 2005 到 Delphi 13 的所有版本

## 贡献

欢迎提交 Issue 和 Pull Request!

## 联系方式

如有问题或建议,请提交 Issue。
