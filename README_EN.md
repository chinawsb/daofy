# Delphi MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Delphi](https://img.shields.io/badge/Delphi-2005%20to%2013-red.svg)](https://www.embarcadero.com/products/delphi)

An MCP Server that provides Delphi project compilation capabilities and knowledge base query functionality for AI assistants (such as Claude Desktop, CodeArts Agent, etc.). If you find it useful, please don't hesitate to give it a Star! ⭐

## Project Introduction

Delphi MCP Server is a server based on Model Context Protocol (MCP) that allows AI assistants to directly compile Delphi projects and query Delphi knowledge bases. With this tool, you can compile Delphi projects, query API documentation, search code examples directly in conversations with AI assistants, without manually switching to IDE or command line.

**Key Advantages:**
- Seamless integration into AI assistant workflow
- Automatic detection and configuration of Delphi compilers
- Built-in Delphi source code knowledge base with semantic search support
- Project-level knowledge base, automatically tracking third-party libraries and project source code
- Help documentation knowledge base for quick API documentation queries
- Support for all mainstream AI assistant platforms
- Complete build event support
- Detailed error diagnostics and logging

## Features

### Compilation Features
- **Project Compilation**: Supports compiling complete Delphi projects (.dproj/.dpr), generating executable files or dynamic link libraries
- **MSBuild Compilation**: Prioritizes MSBuild compilation, automatically handling dependencies and build events
- **Single File Compilation**: Supports compiling individual Delphi unit files (.pas) for syntax checking
- **Automatic Compiler Detection**: Automatically detects installed Delphi compilers from Windows registry, no manual configuration required
- **Build Event Support**: Supports PreBuildEvent, PostBuildEvent, PreLinkEvent with complete parameter substitution
- **Command Line Argument Generation**: Supports generating Delphi compiler command line arguments for debugging and preview
- **Compiler Configuration Management**: Supports configuring and managing multiple Delphi compiler versions
- **Environment Checking**: Provides compiler environment status checking functionality
- **Rich Compilation Options**: Supports conditional compilation symbols, search paths, optimization options, debug information, warning control, etc.

### Knowledge Base Features
- **Delphi Source Code Knowledge Base**: Built-in Delphi official source code knowledge base, supports class, function search and semantic search
- **Project Knowledge Base**: Builds independent knowledge base for each project, automatically tracking third-party libraries and project source code
- **Third-party Library Knowledge Base**: Automatically extracts third-party library paths from .dproj files and builds knowledge base
- **Incremental Updates**: Automatically detects source code changes and incrementally updates project knowledge base
- **Help Documentation Knowledge Base**: Extracts content from Delphi CHM help files, supports API documentation queries

### Coding Standards Features
- **Coding Rules Query**: Retrieves Delphi source code coding rules for AI assistants to use in code review and generation
- **Default Rules Support**: Built-in default coding rules file, including naming rules, formatting rules, modification rules, and review rules
- **Custom Rules Support**: Supports project-level custom coding rules, takes priority over default rules
- **Rule Priority**: Project custom rules > Default rules

## System Requirements

- Python 3.10-3.14
- Delphi compiler (dcc32.exe or dcc64.exe)
- Windows operating system
- Git
- 7-Zip (for extracting CHM help files, optional)

## Installation

### AI Assistant Automatic Installation Prompt

Please follow these steps to install Delphi MCP Server:

[] Check and install Git/Python 3.10-3.14/7-Zip (prioritize using domestic mirror sources for faster downloads during installation)
[] Install `https://github.com/chinawsb/delphi-complier-mcp-server.git`
[] After installation, verify results and configure current client for me

### Manual Installation Steps

#### 1. Clone or Download Project

```bash
git clone https://github.com/chinawsb/delphi-complier-mcp-server.git
cd delphi-complier-mcp-server
```

#### 2. Create Virtual Environment

```bash
python -m venv venv
```

#### 3. Activate Virtual Environment

Windows:
```bash
venv\Scripts\activate
```

Linux/macOS:
```bash
source venv/bin/activate
```

#### 4. Install Dependencies (using mirror sources for faster download)

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

Optional mirror sources:
- Tsinghua University: https://pypi.tuna.tsinghua.edu.cn/simple
- Aliyun: https://mirrors.aliyun.com/pypi/simple/
- USTC: https://pypi.mirrors.ustc.edu.cn/simple/

## Configure AI Assistant

### Automatic Detection of Delphi Compiler

**On first use, MCP Server will automatically detect installed Delphi compilers from Windows registry, no manual configuration required.**

Supported Delphi versions for automatic detection:
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

### Manual Compiler Configuration (Optional)

If you need to manually configure or add a custom compiler, you can use the MCP tool `set_compiler_config` for configuration, or directly edit the `config/compilers.json` file.

### Configure Claude Desktop

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

### Configure CodeArts Agent

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

## Usage

### Compilation Tools

| Tool Name | Description |
|-----------|-------------|
| `compile_project` | Compile Delphi project |
| `compile_file` | Compile single Delphi unit file (syntax check only) |
| `get_compiler_args` | Get compiler command line arguments (no execution) |
| `set_compiler_config` | Configure Delphi compiler |
| `check_environment` | Check compiler environment status |

### Knowledge Base Tools

| Tool Name | Description |
|-----------|-------------|
| `build_knowledge_base` | Build Delphi source code knowledge base |
| `search_class` | Search Delphi class definitions |
| `search_function` | Search Delphi function/procedure definitions |
| `semantic_search` | Semantic search in Delphi code |
| `get_knowledge_base_stats` | Get knowledge base statistics |
| `list_delphi_versions` | List installed Delphi versions |

### Project Knowledge Base Tools

| Tool Name | Description |
|-----------|-------------|
| `init_project_knowledge_base` | Initialize project knowledge base |
| `search_project_class` | Search class definitions in project |
| `search_project_function` | Search function definitions in project |
| `semantic_search_project` | Semantic search in project |
| `get_project_kb_stats` | Get project knowledge base statistics |
| `get_thirdparty_paths` | Get third-party library paths for project |

### Help Documentation Tools

| Tool Name | Description |
|-----------|-------------|
| `build_help_knowledge_base` | Build Delphi help documentation knowledge base |
| `search_help` | Search Delphi help documentation |
| `get_help_kb_stats` | Get help documentation knowledge base statistics |

### Coding Standards Tools

| Tool Name | Description |
|-----------|-------------|
| `get_coding_rules` | Get Delphi source code coding rules |

## Knowledge Base

### Knowledge Base Locations

| Knowledge Base Type | Location | Description |
|---------------------|----------|-------------|
| Delphi Source Code | `data/delphi-knowledge-base/` | Delphi official source code, globally shared |
| Help Documentation | `data/help-knowledge-base/` | Delphi CHM help documentation, globally shared |
| Project Specific | `<project directory>/.delphi-kb/` | Project specific, includes third-party libraries and project source code |

### Knowledge Base Statistics

| Knowledge Base | Document Count | Class Count | Function Count |
|----------------|----------------|-------------|----------------|
| Delphi Source Code | 3,081 | 17,731 | 168,925 |
| Help Documentation | 160,174 | - | - |

## Troubleshooting

### 1. Compiler Not Found

**Solution:**
- Check if compiler paths in `config/compilers.json` are correct
- Use `set_compiler_config` tool to reconfigure compiler

### 2. MCP Server Cannot Start

**Solution:**
- Check if Python environment is correctly configured
- Check if dependencies are installed: `pip install -r requirements.txt`
- Check MCP library version: `pip show mcp`

### 3. Knowledge Base Search Returns No Results

**Solution:**
- Ensure knowledge base is built: use `build_knowledge_base` tool
- Check if knowledge base directory exists

## License

MIT License

Copyright (c) 2026 吉林省左右软件开发有限公司
Copyright (c) 2026 Equilibrium Software Development Co., Ltd, Jilin

See [LICENSE](LICENSE) file for details.

## Version History

### v2026.03.15 (2026-03-15)
- Added coding standards functionality
  - Added `get_coding_rules` tool for retrieving Delphi source code coding rules
  - Support for default coding rules (config/CODING_RULES.mdc)
  - Support for project custom rules (CODING_RULES.mdc in project directory)
  - User custom rules take priority over default rules
- Complete testing verification and documentation
- No impact on existing functionality, fully backward compatible

### v2026.03.11 (2026-03-11)
- Added project knowledge base functionality
  - Automatically extracts third-party library paths from .dproj files
  - Builds project third-party library knowledge base
  - Builds project source code knowledge base, supports incremental updates
- Added help documentation knowledge base functionality
  - Extracts help documentation from CHM files
  - Supports VCL, FMX, System and other help documentation
- Added knowledge base MCP tool interfaces
- Fixed MCP library version compatibility issues
- Optimized knowledge base storage location

### v2026.03.10 (2026-03-10)
- Updated project documentation and README
- Added project badges and introduction
- Optimized project structure
- Released to GitHub

### v2026.03.09 (2026-03-09)
- Initial version release
- Supports project compilation and single file compilation
- Supports MSBuild compilation (prioritized)
- Supports build events (PreBuildEvent, PostBuildEvent, PreLinkEvent)
- Supports all Delphi build event parameters (21 parameters)
- Supports automatic detection of Delphi compilers (from registry)
- Supports all Delphi versions from Delphi 2005 to Delphi 13

## Contributing

Issues and Pull Requests are welcome!

## Contact

If you have questions or suggestions, please submit an Issue.
