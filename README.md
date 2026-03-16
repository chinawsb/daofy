# Delphi MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Delphi](https://img.shields.io/badge/Delphi-2005%20to%2013-red.svg)](https://www.embarcadero.com/products/delphi)

一个为 AI 助手(如 Claude Desktop、CodeArts Agent 等)提供 Delphi 工程编译能力和知识库查询功能的 MCP Server。如果您觉得有用，请不要吝啬您的 Star! ⭐

## 项目简介

Delphi MCP Server 是一个基于 Model Context Protocol (MCP) 的服务器,它允许 AI 助手直接编译 Delphi 项目并查询 Delphi 知识库。通过这个工具,您可以在与 AI 助手的对话中直接编译 Delphi 工程、查询 API 文档、搜索代码示例,无需手动切换到 IDE 或命令行。

**主要优势:**
- 无缝集成到 AI 助手工作流中
- 自动检测和配置 Delphi 编译器
- 内置 Delphi 源码知识库,支持语义搜索
- 项目级知识库,自动追踪三方库和项目源码
- 帮助文档知识库,快速查询 API 文档
- 支持所有主流 AI 助手平台
- 完整的编译事件支持
- 详细的错误诊断和日志

## 功能特性

### 编译功能
- **工程整体编译**: 支持编译完整的 Delphi 工程(.dproj/.dpr),生成可执行文件或动态链接库
- **MSBuild 编译**: 优先使用 MSBuild 编译,自动处理依赖关系和编译事件
- **单文件编译**: 支持编译单个 Delphi 单元文件(.pas),进行语法检查
- **自动检测编译器**: 自动从注册表检测已安装的 Delphi 编译器,无需手动配置
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
- **帮助文档知识库**: 从 Delphi CHM 帮助文件提取内容,支持 API 文档查询

### 编码规范功能
- **编码规则查询**: 获取 Delphi 源码编码规则,供 AI 助手用于代码审核和生成
- **默认规则支持**: 内置默认编码规则文件,包含命名规则、格式化规则、修改规则和审核规则
- **自定义规则支持**: 支持项目级别的自定义编码规则,优先于默认规则
- **规则优先级**: 项目自定义规则 > 默认规则

## 系统要求

- Python 3.10-3.14
- Delphi 编译器(dcc32.exe 或 dcc64.exe)
- Windows 操作系统
- Git
- 7-Zip (用于解压 CHM 帮助文件,可选)

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
- 清华大学: https://pypi.tuna.tsinghua.edu.cn/simple
- 阿里云: https://mirrors.aliyun.com/pypi/simple/
- 中科大: https://pypi.mirrors.ustc.edu.cn/simple/

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

如果需要手动配置或添加自定义编译器,可以通过 MCP 工具 `set_compiler_config` 进行配置,或直接编辑 `config/compilers.json` 文件。

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

### 编译工具

| 工具名称 | 功能描述 |
|---------|---------|
| `compile_project` | 编译 Delphi 工程 |
| `compile_file` | 编译单个 Delphi 单元文件(仅语法检查) |
| `get_compiler_args` | 获取编译器命令行参数(不执行编译) |
| `set_compiler_config` | 配置 Delphi 编译器 |
| `check_environment` | 检查编译器环境状态 |

### 知识库工具

| 工具名称 | 功能描述 |
|---------|---------|
| `build_knowledge_base` | 构建 Delphi 源码知识库 |
| `search_class` | 搜索 Delphi 类定义 |
| `search_function` | 搜索 Delphi 函数/过程定义 |
| `semantic_search` | 语义搜索 Delphi 代码 |
| `get_knowledge_base_stats` | 获取知识库统计信息 |
| `list_delphi_versions` | 列出已安装的 Delphi 版本 |

### 项目知识库工具

| 工具名称 | 功能描述 |
|---------|---------|
| `init_project_knowledge_base` | 初始化项目知识库 |
| `search_project_class` | 在项目中搜索类定义 |
| `search_project_function` | 在项目中搜索函数定义 |
| `semantic_search_project` | 在项目中进行语义搜索 |
| `get_project_kb_stats` | 获取项目知识库统计信息 |
| `get_thirdparty_paths` | 获取项目的三方库路径 |

### 帮助文档工具

| 工具名称 | 功能描述 |
|---------|---------|
| `build_help_knowledge_base` | 构建 Delphi 帮助文档知识库 |
| `search_help` | 搜索 Delphi 帮助文档 |
| `get_help_kb_stats` | 获取帮助文档知识库统计信息 |

### 编码规范工具

| 工具名称 | 功能描述 |
|---------|---------|
| `get_coding_rules` | 获取 Delphi 源码编码规则 |

## 知识库

### 知识库位置

| 知识库类型 | 位置 | 说明 |
|-----------|------|------|
| Delphi 源码知识库 | `data/delphi-knowledge-base/` | Delphi 官方源码,全局共享 |
| 帮助文档知识库 | `data/help-knowledge-base/` | Delphi CHM 帮助文档,全局共享 |
| 项目知识库 | `<项目目录>/.delphi-kb/` | 项目特定,包含三方库和项目源码 |

### 知识库统计

| 知识库 | 文档数 | 类数量 | 函数数量 |
|-------|--------|--------|----------|
| Delphi 源码 | 3,081 | 17,731 | 168,925 |
| 帮助文档 | 160,174 | - | - |

## 故障排除

### 1. 编译器未找到

**解决方案**:
- 检查 `config/compilers.json` 文件中的编译器路径是否正确
- 使用 `set_compiler_config` 工具重新配置编译器

### 2. MCP Server 无法启动

**解决方案**:
- 检查 Python 环境是否正确配置
- 检查依赖是否已安装: `pip install -r requirements.txt`
- 检查 MCP 库版本: `pip show mcp`

### 3. 知识库搜索无结果

**解决方案**:
- 确保已构建知识库: 使用 `build_knowledge_base` 工具
- 检查知识库目录是否存在

## 许可证

MIT License

Copyright (c) 2026 吉林省左右软件开发有限公司
Copyright (c) 2026 Equilibrium Software Development Co., Ltd, Jilin

详见 [LICENSE](LICENSE) 文件。

## 版本历史

### v2026.03.15 (2026-03-15)
- 新增编码规范功能
  - 新增 `get_coding_rules` 工具,用于获取 Delphi 源码编码规则
  - 支持默认编码规则（config/CODING_RULES.mdc）
  - 支持项目自定义规则（项目目录下的 CODING_RULES.mdc）
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
