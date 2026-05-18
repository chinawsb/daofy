# Daofy

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Delphi](https://img.shields.io/badge/Delphi-2005%20to%2013-red.svg)](https://www.embarcadero.com/products/delphi)

An MCP Server that provides Delphi project compilation capabilities and knowledge base query functionality for AI assistants (such as Claude Desktop, CodeArts Agent, etc.). If you find it useful, please don't hesitate to give it a Star! ⭐

Daofy — Spread your wings for creativity.

## Project Introduction

Daofy is a server based on Model Context Protocol (MCP) that allows AI assistants to directly compile Delphi projects and query Delphi knowledge bases. With this tool, you can compile Delphi projects, query API documentation, search code examples directly in conversations with AI assistants, without manually switching to IDE or command line.

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
- **Smart Library Path Resolution**: Automatically analyzes project dependencies and intelligently selects required third-party library paths to avoid command line length issues
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
- **Generic Document Knowledge Base**: Supports scanning and searching of txt/md/html/docx/doc/pdf/epub and web documents
  - Required dependencies: `beautifulsoup4`, `html2text`, `lxml`, `requests` (already in requirements.txt)
  - Optional dependencies: `python-docx` (Word .docx support), `antiword/catdoc` (legacy Word .doc support), `PyMuPDF` (PDF support, recommended) or `pdfplumber` (PDF support, fallback)
- **Smart Deduplication**: Deduplicates based on full path, correctly handles files with same name in different directories

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

## Knowledge Base Storage Locations

All knowledge base data is stored in the `data/` folder under the project root:

| Knowledge Base Type | Storage Path | Description |
|--------------------|--------------|-------------|
| Delphi Source KB | `data/delphi-knowledge-base/` | Delphi official source (RTL/VCL/FMX etc.) |
| Third-party Library KB | `data/thirdparty-knowledge-base/` | Third-party component library source |
| Generic Document KB | `data/document-knowledge-base/` | Delphi CHM help + generic docs |
| Project KB | `<project-dir>/.delphi-kb/` | Project-level KB, stored in project directory |

Each knowledge base directory contains:
- SQLite database file
- `config.json` - Knowledge base configuration file

## Knowledge Base Configuration

Each knowledge base has a `config.json` file. Configs are auto-generated on first build and rarely need manual changes.

| KB Type | Location |
|---------|----------|
| Delphi Source | `data/delphi-knowledge-base/config.json` |
| Third-party | `data/thirdparty-knowledge-base/config.json` |
| Documents | `data/document-knowledge-base/config.json` |
| Project | `<project-dir>/.delphi-kb/config.json` |

## Installation

### AI Assistant Automatic Installation Prompt

Please follow these steps to install Daofy:

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

If you need to manually configure or add a custom compiler, you can directly edit the `config/compilers.json` file, or use the `check_environment` tool with `detect` action to re-detect.

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

### Configure Trae

**Windows**: `C:\Users\<username>\.trae-cn\mcp_config.json`

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

**Note**: Please modify the paths to your actual installation paths.

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

| Tool Name | Description | Key Parameters |
|-----------|-------------|----------------|
| `compile_project` | Compile Delphi project or check .pas file syntax | `project_path`, `target_platform`(win32/win64), `build_configuration`(Debug/Release), `output_path`, `timeout`, `debug_info_enabled`, `get_args_only`(optional) |
| `check_environment` | Diagnose environment, detect compilers, install pasfmt | `action`(check/detect/install/format_install), `search_path`, `install_dir`, `delphi_version` |
| `install_package` | Compile and install Delphi package to IDE | `package_path`, `target_platform`, `build_configuration`, `timeout`, `install` |
| `list_installed_packages` | List packages installed to IDE | - |
| `get_coding_rules` | Get Delphi coding standards, supports section-based retrieval | `project_path`(optional), `section`(optional, e.g. workflow/writing/review/safety) |

### Knowledge Base Tools

| Tool Name | Description | Key Parameters |
|-----------|-------------|----------------|
| `delphi_kb` | Search code/classes/functions/docs, view stats, or build knowledge base | `action`(search/stats/build/scan/web), `query`, `kb_type`(all/delphi/project/thirdparty/document), `search_type`(function=functions+procedures, procedure=procedures only), `top_k`(default 200, max 500) |

### File Operations

| Tool Name | Description | Key Parameters |
|-----------|-------------|----------------|
| `file_tool` | Unified file operations: read/write/format/backup | `action`(read/write/format/backup), `file_path`, `content`, `search_type`, `type_name`, `function_name`, `start_line`, `max_lines`, `backup`, `encoding`(see action descriptions for details)

### DFM Code Generation

| Tool Name | Description | Key Parameters |
|-----------|-------------|----------------|
| `generate_component_dfm` | Compile + run AI-written Pascal code to generate component DFM definitions | `code`(required), `uses`, `type_decl`, `init_code`, `compile_timeout`, `exec_timeout` |

### Code Hosting Tools

| Tool Name | Description | Key Parameters |
|-----------|-------------|----------------|
| `code_hosting` | Unified operations for Gitea/GitHub/GitLab + local Git operations | `platform`(gitea/github/gitlab), `action`(create_issue/close_issue/add_comment/list_issues/git_clone/git_commit/git_push, etc.), `base_url`, `token`, `repo`, `work_dir` |

### Async Task Tools

| Tool Name | Description | Key Parameters |
|-----------|-------------|----------------|
| `async_task` | Manage background tasks (e.g., build knowledge base) | `action`(start/status/result/list/cancel), `task_id` |

### Coding Standards Tools

| Tool Name | Description | Key Parameters |
|-----------|-------------|----------------|
| `get_coding_rules` | Get Delphi coding standards | `project_path`(optional) |

## Knowledge Base

| Knowledge Base Type | Location | Description |
|---------------------|----------|-------------|
| Delphi Source Code | `data/delphi-knowledge-base/` | Delphi official source code |
| Third-party Library | `data/thirdparty-knowledge-base/` | Shared third-party libraries |
| Generic Documents | `data/document-knowledge-base/` | CHM help + generic docs |
| Project Specific | `<project directory>/.delphi-kb/` | Project-specific KB |

| Knowledge Base | Documents | Classes | Functions |
|----------------|-----------|---------|-----------|
| Delphi Source | 3,081 | 17,731 | 168,925 |

## Troubleshooting

### 1. Compiler Not Found
- Check `config/compilers.json` paths
- Use `check_environment(action='detect')` to re-detect

### 2. MCP Server Cannot Start
- Check Python: `pip install -r requirements.txt`
- Verify MCP: `pip show mcp`

### 3. No Search Results
- Build KB: `delphi_kb(action='build', kb_type='project')`

## License

MIT License - See [LICENSE](LICENSE) file.

## Version History

### v2026.05.14 (Latest)

- New `generate_component_dfm` tool: compile+run Pascal code to generate DFM
- `file_tool` enhanced: DFM binary auto-conversion, backup management, search positioning
- Install script refactored: Python-first with bat bootstrap, global/project modes
- Server restructuring: MCP tool registration and invocation logic separation
- New tests: file_tool, create_component_dfm, mcp_client, pasfmt
- New `code_hosting` tool: unified Gitea/GitHub/GitLab operations

### v2026.05.13

- Regex overhaul: constructor/destructor/class function support
- Search enhancement: function matches FF+FP, unit name fallback, top_k default 200
- Performance fix: nested parenthesis regex from 219s → 0.002s

Full history: See [CHANGELOG.md](CHANGELOG.md)

## Contributing

Issues and Pull Requests are welcome!
