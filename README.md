# Delphi MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Delphi](https://img.shields.io/badge/Delphi-2005%20to%2013-red.svg)](https://www.embarcadero.com/products/delphi)

一个为 AI 助手(如 Claude Desktop、CodeArts Agent 等)提供 Delphi 工程编译能力的 MCP Server。如果您觉得有用，请不要吝啬您的 Star! ⭐

## 项目简介

Delphi MCP Server 是一个基于 Model Context Protocol (MCP) 的服务器,它允许 AI 助手直接编译 Delphi 项目。通过这个工具,您可以在与 AI 助手的对话中直接编译 Delphi 工程,无需手动切换到 IDE 或命令行。

**主要优势:**
- 无缝集成到 AI 助手工作流中
- 自动检测和配置 Delphi 编译器
- 支持所有主流 AI 助手平台
- 完整的编译事件支持
- 详细的错误诊断和日志

## 功能特性

- **工程整体编译**: 支持编译完整的 Delphi 工程(.dproj/.dpr),生成可执行文件或动态链接库
- **MSBuild 编译**: 优先使用 MSBuild 编译,自动处理依赖关系和编译事件
- **单文件编译**: 支持编译单个 Delphi 单元文件(.pas),进行语法检查
- **自动检测编译器**: 自动从注册表检测已安装的 Delphi 编译器,无需手动配置
- **编译事件支持**: 支持 PreBuildEvent、PostBuildEvent、PreLinkEvent,包含完整的参数替换
- **命令行参数生成**: 支持生成 Delphi 编译器命令行参数,便于调试和预览
- **编译器配置管理**: 支持配置和管理多个 Delphi 编译器版本
- **环境检查**: 提供编译器环境状态检查功能
- **丰富的编译选项**: 支持条件编译符号、搜索路径、优化选项、调试信息、警告控制等

## 系统要求

- Python 3.10 或更高版本
- Delphi 编译器(dcc32.exe 或 dcc64.exe)
- Windows 操作系统

## 安装

### 1. 克隆或下载项目

```bash
git clone <repository-url>
cd delphi_mcp_server
```

### 2. 创建虚拟环境

```bash
python -m venv venv
```

### 3. 激活虚拟环境

Windows:
```bash
venv\Scripts\activate
```

Linux/macOS:
```bash
source venv/bin/activate
```

### 4. 安装依赖

```bash
pip install -r requirements.txt
```

## 配置

### 1. 自动检测 Delphi 编译器

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

**检测原理**: 从注册表 `HKEY_CURRENT_USER\SOFTWARE\Embarcadero\BDS` 读取所有已安装的 Delphi 版本及其安装路径。

### 2. 手动配置编译器 (可选)

如果需要手动配置或添加自定义编译器,可以通过 MCP 工具 `set_compiler_config` 进行配置,或直接编辑 `config/compilers.json` 文件。

示例配置:

```json
{
  "compilers": [
    {
      "name": "Delphi 11 Alexandria Win64",
      "path": "C:\\Program Files (x86)\\Embarcadero\\Studio\\22.0\\bin\\dcc64.exe",
      "is_default": true,
      "version": "Delphi 11 Alexandria"
    },
    {
      "name": "Delphi 11 Alexandria Win32",
      "path": "C:\\Program Files (x86)\\Embarcadero\\Studio\\22.0\\bin\\dcc32.exe",
      "is_default": false,
      "version": "Delphi 11 Alexandria"
    }
  ],
  "default_compiler": "Delphi 11 Alexandria Win64"
}
```

### 3. 配置 AI 助手

#### 2.1 Claude Desktop

在 Claude Desktop 的配置文件中添加 MCP Server 配置:

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "delphi-compiler": {
      "command": "python",
      "args": ["C:\\path\\to\\delphi_mcp_server\\src\\server.py"],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

#### 2.2 CodeArts Agent

在 CodeArts Agent 的配置文件中添加 MCP Server 配置:

**Windows**: `%APPDATA%\codearts-agent\User\settings.json`

```json
{
  "mcp": {
    "servers": {
      "stdio_delphi_compiler": {
        "enabled": true,
        "type": "stdio",
        "command": "python",
        "args": ["C:\\path\\to\\delphi_mcp_server\\src\\server.py"],
        "env": {
          "PYTHONUNBUFFERED": "1"
        },
        "autoApprovedTools": [
          "compile_project",
          "compile_file",
          "get_compiler_args",
          "set_compiler_config",
          "check_environment"
        ]
      }
    }
  }
}
```

#### 2.3 OpenCode

在 OpenCode 的配置文件中添加 MCP Server 配置:

**配置文件位置**: `~/.opencode/config.json` 或项目根目录的 `.opencode/config.json`

```json
{
  "mcpServers": {
    "delphi-compiler": {
      "command": "python",
      "args": ["C:\\path\\to\\delphi_mcp_server\\src\\server.py"],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

#### 2.4 通义千问 (Qwen)

在通义千问的配置文件中添加 MCP Server 配置:

**配置文件位置**: `~/.qwen/config.json`

```json
{
  "mcp": {
    "servers": {
      "delphi-compiler": {
        "command": "python",
        "args": ["C:\\path\\to\\delphi_mcp_server\\src\\server.py"],
        "env": {
          "PYTHONUNBUFFERED": "1"
        }
      }
    }
  }
}
```

#### 2.5 文心一言 (ERNIE Bot)

在文心一言的配置文件中添加 MCP Server 配置:

**配置文件位置**: `~/.ernie/config.json`

```json
{
  "mcpServers": {
    "delphi-compiler": {
      "command": "python",
      "args": ["C:\\path\\to\\delphi_mcp_server\\src\\server.py"],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

#### 2.6 讯飞星火 (Spark)

在讯飞星火的配置文件中添加 MCP Server 配置:

**配置文件位置**: `~/.spark/config.json`

```json
{
  "mcp": {
    "servers": {
      "delphi-compiler": {
        "command": "python",
        "args": ["C:\\path\\to\\delphi_mcp_server\\src\\server.py"],
        "env": {
          "PYTHONUNBUFFERED": "1"
        }
      }
    }
  }
}
```

#### 2.7 智谱清言 (ChatGLM)

在智谱清言的配置文件中添加 MCP Server 配置:

**配置文件位置**: `~/.chatglm/config.json`

```json
{
  "mcpServers": {
    "delphi-compiler": {
      "command": "python",
      "args": ["C:\\path\\to\\delphi_mcp_server\\src\\server.py"],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

#### 2.8 百川智能 (Baichuan)

在百川智能的配置文件中添加 MCP Server 配置:

**配置文件位置**: `~/.baichuan/config.json`

```json
{
  "mcp": {
    "servers": {
      "delphi-compiler": {
        "command": "python",
        "args": ["C:\\path\\to\\delphi_mcp_server\\src\\server.py"],
        "env": {
          "PYTHONUNBUFFERED": "1"
        }
      }
    }
  }
}
```

#### 2.9 MiniMax

在 MiniMax 的配置文件中添加 MCP Server 配置:

**配置文件位置**: `~/.minimax/config.json`

```json
{
  "mcpServers": {
    "delphi-compiler": {
      "command": "python",
      "args": ["C:\\path\\to\\delphi_mcp_server\\src\\server.py"],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

#### 2.10 Moonshot AI (Kimi)

在 Moonshot AI 的配置文件中添加 MCP Server 配置:

**配置文件位置**: `~/.moonshot/config.json`

```json
{
  "mcp": {
    "servers": {
      "delphi-compiler": {
        "command": "python",
        "args": ["C:\\path\\to\\delphi_mcp_server\\src\\server.py"],
        "env": {
          "PYTHONUNBUFFERED": "1"
        }
      }
    }
  }
}
```

### 4. 配置说明

**注意事项:**

1. **路径替换**: 请将 `C:\\path\\to\\delphi_mcp_server` 替换为实际的项目路径
2. **Python 环境**: 确保使用正确的 Python 环境,建议使用绝对路径指定 Python 解释器
3. **环境变量**: `PYTHONUNBUFFERED=1` 确保日志实时输出
4. **权限**: 确保 Python 脚本有执行权限
5. **重启**: 配置完成后需要重启 AI 助手应用

**使用虚拟环境:**

如果使用虚拟环境,请指定虚拟环境中的 Python 解释器:

```json
{
  "command": "C:\\path\\to\\delphi_mcp_server\\venv\\Scripts\\python.exe",
  "args": ["C:\\path\\to\\delphi_mcp_server\\src\\server.py"]
}
```

## 使用方法

### 编译方式

**项目编译优先使用 MSBuild**:
- 自动检测系统中的 MSBuild
- 自动处理项目依赖关系
- 自动执行编译事件(PreBuildEvent、PostBuildEvent、PreLinkEvent)
- 如果 MSBuild 不可用,则回退到直接编译器调用

**编译事件支持**:
- PreBuildEvent: 编译前执行
- PreLinkEvent: 链接前执行
- PostBuildEvent: 编译后执行
- 支持所有 Delphi 编译事件参数(BDS, Config, DEFINES, DIR, INCLUDEPATH, INPUTEXT, INPUTFILENAME, INPUTPATH, LOCALCOMMAND, OUTPUTDIR, OUTPUTEXT, OUTPUTFILENAME, OUTPUTPATH, PATH, Platform, PROJECTDIR, PROJECTFILENAME, PROJECTNAME, PROJECTPATH, SystemRoot, WINDIR)

### 工具列表

#### 1. compile_project - 工程编译

编译 Delphi 工程。

**参数:**
- `project_path` (必需): 项目文件路径(.dproj 或 .dpr)
- `target_platform` (可选): 目标平台(win32/win64),默认 win32
- `output_path` (可选): 输出路径
- `compiler_version` (可选): 编译器版本名称
- `timeout` (可选): 超时时间(秒),默认 600
- `conditional_defines` (可选): 条件编译符号列表
- `unit_search_paths` (可选): 单元搜索路径列表
- `resource_search_paths` (可选): 资源搜索路径列表
- `optimization_enabled` (可选): 是否启用优化,默认 true
- `debug_info_enabled` (可选): 是否生成调试信息,默认 false
- `warning_level` (可选): 警告级别(0-4),默认 2
- `disabled_warnings` (可选): 禁用的警告列表
- `output_type` (可选): 输出类型(console/gui/dll),默认 gui
- `runtime_library` (可选): 运行时库链接方式(static/dynamic),默认 static
- `build_configuration` (可选): 编译配置名称

**示例:**
```
请编译项目 C:\Projects\MyApp\MyApp.dproj,使用 64 位目标平台
```

#### 2. compile_file - 单文件编译

编译单个 Delphi 单元文件(仅语法检查)。

**参数:**
- `file_path` (必需): 单元文件路径(.pas)
- `unit_search_paths` (可选): 单元搜索路径列表
- `warning_level` (可选): 警告级别(0-4),默认 2
- `disabled_warnings` (可选): 禁用的警告列表

**示例:**
```
请检查文件 C:\Projects\MyApp\MainForm.pas 的语法
```

#### 3. get_compiler_args - 获取命令行参数

获取编译器命令行参数(不执行编译)。

**参数:** 同 compile_project

**示例:**
```
请生成项目 C:\Projects\MyApp\MyApp.dproj 的编译命令行参数
```

#### 4. set_compiler_config - 配置编译器

配置 Delphi 编译器。

**参数:**
- `name` (必需): 编译器版本名称
- `path` (必需): 编译器可执行文件路径
- `is_default` (可选): 是否设为默认编译器,默认 false
- `version` (可选): 编译器版本号

**示例:**
```
请配置 Delphi 11 编译器,路径为 C:\Program Files (x86)\Embarcadero\Studio\22.0\bin\dcc64.exe
```

#### 5. check_environment - 检查环境

检查编译器环境状态。

**参数:** 无

**示例:**
```
请检查 Delphi 编译器环境
```

## 故障排除

### 1. 编译器未找到

**错误**: "编译器配置不存在" 或 "编译器文件不存在"

**解决方案**:
- 检查 `config/compilers.json` 文件中的编译器路径是否正确
- 使用 `set_compiler_config` 工具重新配置编译器
- 确保编译器可执行文件存在且有执行权限

### 2. 编译超时

**错误**: "编译超时"

**解决方案**:
- 增加 `timeout` 参数的值
- 检查项目是否过大或编译器是否卡住
- 检查系统资源使用情况

### 3. 路径错误

**错误**: "项目文件不存在" 或 "文件不存在"

**解决方案**:
- 检查路径是否正确
- 确保使用绝对路径
- 检查文件扩展名是否正确(.dproj/.dpr/.pas)

### 4. MCP Server 无法启动

**错误**: Claude Desktop 无法连接到 MCP Server

**解决方案**:
- 检查 Python 环境是否正确配置
- 检查依赖是否已安装
- 查看 Claude Desktop 日志文件获取详细错误信息

## 开发

### 运行测试

```bash
pytest tests/
```

### 代码风格

使用 Python 标准代码风格(PEP 8)。

## 许可证

MIT License

Copyright (c) 2026 吉林省左右软件开发有限公司
Copyright (c) 2026 Equilibrium Software Development Co., Ltd, Jilin

详见 [LICENSE](LICENSE) 文件。

## 版本历史

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
- 支持 10+ AI 助手配置
- 自动 .dcu 文件清理(单文件编译前)

## 贡献

欢迎提交 Issue 和 Pull Request!

## 联系方式

如有问题或建议,请提交 Issue。
