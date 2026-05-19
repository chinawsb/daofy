# Daofy for Delphi

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![Delphi 2005-13](https://img.shields.io/badge/Delphi-2005%20to%2013-red.svg)

一个为 AI 助手(如 Claude Desktop、CodeArts Agent 等)提供 Delphi 工程编译能力和知识库查询功能的 MCP Server。如果您觉得有用，请不要吝啬您的 Star! ⭐

Daofy（道飞）——为创意插上翅膀。

## 项目简介

Daofy for Delphi 是一个基于 Model Context Protocol (MCP) 的 MCP Server，它允许 AI 助手直接编译 Delphi 项目并查询 Delphi 知识库。通过这个工具,您可以在与 AI 助手的对话中直接编译 Delphi 工程、查询 API 文档、搜索代码示例,无需手动切换到 IDE 或命令行。

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
| `get_coding_rules` | 获取 Delphi 编码规范，默认返回工作流+章节索引，支持按章节分段获取 | `project_path`(可选), `section`(可选，如 workflow/env/kb_search/writing/format/compile/review/safety/agent_rules/kb_build/cleanup等) |

### 知识库工具

| 工具名称 | 功能描述 | 主要参数 |
|----------|----------|----------|
| `delphi_kb` | 搜索代码/类/函数/文档，查看统计或构建知识库 | `action`(search/stats/build/scan/web), `query`, `kb_type`(all/delphi/project/thirdparty/document), `search_type`(function=函数+过程, procedure=仅过程), `top_k`(默认200,最大500), `project_path`(项目知识库可选，不传时自动从当前目录检测 .dproj), `directory`(扫描目录, 构建文档KB时可省略自动检测), `url`(网页URL), `content_type`(文档类型), `extensions`(文件扩展名) |

### 文件操作工具

| 工具名称 | 功能描述 | 主要参数 |
|----------|----------|----------|
| `file_tool` | 统一文件操作：读/写/格式化/备份管理 | `action`(read/write/format/backup), `file_path`, `content`, `search_type`, `type_name`, `function_name`, `start_line`, `max_lines`, `backup`, `encoding`(详见对应action说明) |

### DFM 代码生成工具

| 工具名称 | 功能描述 | 主要参数 |
|----------|----------|----------|
| `generate_component_dfm` | 编译+运行 AI 写的 Pascal 代码来生成组件 DFM 定义 | `code`(必需), `uses`, `type_decl`, `init_code`, `compile_timeout`, `exec_timeout` |

### 代码托管工具

| 工具名称 | 功能描述 | 主要参数 |
|----------|----------|----------|
| `code_hosting` | 统一操作 Gitea/GitHub/GitLab 平台 + Git 本地操作 | `platform`(gitea/github/gitlab), `action`(create_issue/close_issue/add_comment/list_issues/git_clone/git_commit/git_push等), `base_url`, `token`, `repo`, `work_dir` |

### 异步任务工具

| 工具名称 | 功能描述 | 主要参数 |
|----------|----------|----------|
| `async_task` | 管理后台任务（构建知识库等） | `action`(start/status/result/list/cancel), `task_id`, `task_type`, `task_params`, `show_progress` |

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

| 知识库类型 | 配置位置 |
|-----------|----------|
| Delphi 源码 | `data/delphi-knowledge-base/config.json` |
| 第三方库 | `data/thirdparty-knowledge-base/config.json` |
| 通用文档 | `data/document-knowledge-base/config.json` |
| 项目级 | `<项目目录>/.delphi-kb/config.json` |

配置文件在首次构建时自动生成，通常无需手动修改。

## 安装

### AI 助手自动安装提示词

请按以下步骤安装 Daofy:

[] 检查并安装 Git/Python 3.10-3.14/7-Zip (安装时优先使用国内镜像源加速下载)

[] 安装 `https://github.com/chinawsb/daofy.git`

[] 安装完成后验证结果并帮我配置当前客户端

### 手动安装步骤

#### 1. 克隆或下载项目

```bash
git clone https://github.com/chinawsb/daofy.git
cd daofy
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
    "daofy": {
      "command": "python",
      "args": ["C:\\path\\to\\daofy\\src\\server.py"],
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
    "daofy": {
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
    "daofy": {
      "command": "python",
      "args": ["src\\server.py"],
      "cwd": "C:\\path\\to\\daofy",
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

| 知识库       | 文件数     | 类数量    | 函数数量    | 数据库大小 |
| ---------    | -------   | ------    | -------    | --------- |
| Delphi 源码  | 2,798     | 163,737   | 300,228    | 260 MB    |
| 三方库        | 1,800     | 5,724     | 28,801     | 27 MB     |
| 通用文档      | 160,328   | -         | -          | 1,306 MB  |

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

### v2026.05.14 (最新)

- 新增 `generate_component_dfm` 工具：编译+运行 Pascal 代码生成 DFM
- `file_tool` 增强：DFM 二进制自动转换、备份管理、搜索定位
- `get_coding_rules` 增强：支持按章节分段获取，节省 token
- 新增 `code_hosting` 工具：统一 Gitea/GitHub/GitLab 操作
- 工作流从 6 步扩展为 7 步（①环境检查→②查KB→③写代码→④格式化→⑤编译→⑥审计→⑦清理）

### v2026.05.13

- 正则表达式大修：覆盖 constructor/destructor/class function 等语法
- 搜索增强：function 同时匹配 FF+FP，单元名自动回退到文件路径，top_k 默认 200
- 性能修复：嵌套括号正则从 219s → 0.002s

完整版本历史详见 [CHANGELOG.md](CHANGELOG.md)

## 贡献

欢迎提交 Issue 和 Pull Request!

## 联系方式

如有问题或建议,请提交 Issue。
