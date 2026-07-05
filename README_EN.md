# Daofy for Delphi

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Delphi](https://img.shields.io/badge/Delphi-2005%20to%2013-red.svg)](https://www.embarcadero.com/products/delphi)

An MCP Server that provides Delphi project compilation capabilities and knowledge base query functionality for AI assistants (such as Claude Desktop, CodeArts Agent, etc.). If you find it useful, please don't hesitate to give it a Star! ⭐

Daofy — Spread your wings for creativity.

## Project Introduction

Daofy for Delphi is a server based on Model Context Protocol (MCP) that allows AI assistants to directly compile Delphi projects and query Delphi knowledge bases. With this tool, you can compile Delphi projects, query API documentation, search code examples directly in conversations with AI assistants, without manually switching to IDE or command line.

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
- **Generic Document Knowledge Base**: Supports scanning and searching of txt/md/html/docx/doc/pdf/epub and web documents (ZVec-based vector storage + FTS full-text index)
  - Required dependencies: `html2text`, `requests` (already in requirements.txt)
  - Optional dependencies: `python-docx` (Word .docx support), `antiword/catdoc` (legacy Word .doc support), `PyMuPDF` (PDF support, recommended) or `pdfplumber` (PDF support, fallback), `beautifulsoup4` (EPUB support)
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
| Experience KB | `data/experience-knowledge-base/` | AI experience memory (`experiences.sqlite`) |

Each knowledge base directory contains:
- `*.zvec/` - ZVec vector database directory (document/example/project/thirdparty KB)
- `experiences.sqlite` - Experience memory database (experience KB only)
- `config.json` - Knowledge base configuration file

Note: All KB types except experience KB have migrated from SQLite to ZVec vector engine. Document KB no longer uses SQLite FTS5.

## Knowledge Base Configuration

Each knowledge base has a `config.json` file. Configs are auto-generated on first build and rarely need manual changes.

| KB Type | Location |
|---------|----------|
| Delphi Source | `data/delphi-knowledge-base/config.json` |
| Third-party | `data/thirdparty-knowledge-base/config.json` |
| Documents | `data/document-knowledge-base/config.json` |
| Project | `<project-dir>/.delphi-kb/config.json` |
| Experience | `data/experience-knowledge-base/` (SQLite only, no config.json) |

## Installation

### Method 1: pip install (Recommended)

```bash
pip install daofy-for-delphi
```

After installation, skip to → [Configure AI Assistant](#configure-ai-assistant).

> **For users in China**, use a mirror source for faster download:
> ```bash
> pip install daofy-for-delphi -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```

### Method 2: Install from Source

#### AI Assistant Automatic Installation Prompt

Please follow these steps to install Daofy:

[] Check and install Git/Python 3.10-3.14/7-Zip
[] Install `https://github.com/chinawsb/daofy.git`
[] After installation, verify results and configure current client for me

#### Manual Installation Steps

##### 1. Clone or Download Project

```bash
git clone https://github.com/chinawsb/daofy.git
cd daofy
```

##### 2. Create Virtual Environment

```bash
python -m venv venv
```

##### 3. Activate Virtual Environment

Windows:
```bash
venv\Scripts\activate
```

Linux/macOS:
```bash
source venv/bin/activate
```

##### 4. Install Dependencies (using mirror sources for faster download)

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

### Common Configuration (pip install)

If installed via `pip install daofy-for-delphi`, use the simplest config:

```json
{
  "mcpServers": {
    "daofy": {
      "command": "daofy",
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

### Source Install Configuration

The following configs apply to users who installed via git clone. Replace the paths with your actual installation paths.

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

#### Trae

**Windows**: `C:\Users\<username>\.trae-cn\mcp_config.json`

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

**Note**: Please modify the paths to your actual installation paths.

#### CodeArts Agent

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

## Tools

| Tool Name | Description |
|-----------|-------------|
| `delphi_project` | Delphi project lifecycle: compile/configure(info/set/create)/audit(audit/ast/runtime) |
| `check_environment` | Diagnose environment, detect compilers, install pasfmt |
| `package` | Package management: install(action=install) / list installed(action=list) |
| `get_coding_rules` | Get Delphi coding standards, supports section-based retrieval |
| `delphi_kb` | Search code/classes/functions/docs, view stats, or build knowledge base |
| `delphi_file` | Delphi file operations: read/write(edits)/format/backup (encoding detection + auto-backup + DFM conversion) |
| `manage_component` | Manage DFM components: add/remove/modify/create + PAS auto-sync |
| `code_hosting` | Unified operations for Gitea/GitHub/GitLab/Gitee/GitCode + local Git operations |
| `async_task` | Manage background tasks (e.g., build knowledge base) |
| `daofy_update` | Check Daofy version updates, execute git pull (check/update/version), async background tasks |
| `tool_help` | Get full documentation for any tool (on-demand: params/examples/workflows) |
| `generate_copyright` | Generate copyright registration docs: source code/manual/summary (PDF browser render + auto-verify) |
| `automate_delphi` | Delphi GUI/Console automation testing — script-driven (click/type/waitfor/rget/capture), GUI named pipe & console modes, `keep_alive` process reuse |
| `delphi_rtti` | Delphi RTTI bridge — discover and call Delphi app runtime capabilities via RTTI (3-step: discover/call/guide) |
| `experience` | Memory management: save/search/update/merge/delete AI problem-solving experience; prune low-value entries; rebuild_embedding for records missing vectors after model load |
| `ocr` | Image analysis: text recognition(recognize)/textbox(detect)/screenshot diff(diff)/color analysis(color)/icon match(match) |

## Knowledge Base

| Knowledge Base Type | Location | Description |
|---------------------|----------|-------------|
| Delphi Source Code | `data/delphi-knowledge-base/` | Delphi official source code |
| Third-party Library | `data/thirdparty-knowledge-base/` | Shared third-party libraries |
| Generic Documents | `data/document-knowledge-base/` | CHM help + generic docs |
| Project Specific | `<project directory>/.delphi-kb/` | Project-specific KB |

### Knowledge Base Statistics

| Knowledge Base | Documents | Classes | Functions | Size |
|----------------|-----------|---------|-----------|------|
| Delphi Source | 2,798 | 163,737 | 300,228 | 260 MB |
| Third-party Library | 1,800 | 5,724 | 28,801 | 27 MB |
| Generic Documents | 160,328 | — | — | 1,306 MB |

**Total: ~170K classes, 330K functions, 160K document pages**

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

### v2026.06.03 (Latest)

- `delphi_file` write now uses `write(edits=[...])` for one or more edits: sorted by `start_line`, accumulates offsets in memory, and writes once
- `compilers.json` path self-healing: auto-fallback to project root `config/` when not found in `src/config/`, avoiding MCP startup failure due to path mismatch
- 18 `except Exception: pass` blocks now log `logger.debug(msg, exc_info=True)` with traceback for easier debugging
- `search_knowledge` refactor: 597→37 lines, split into 16 module-level sub-functions, behavior fully equivalent
- Full test suite: 727 passed

### v2026.06.01

- `delphi_file` partial write line number fix; later versions use 1-indexed inclusive line numbers consistently, with offsets returned after writes
- `delphi_file(action="uses")` now also returns offset info
- `AGENTS.md`: new partial write rules section; later versions use 1-indexed inclusive semantics with consecutive edit offsets
- Full test suite: 684 passed, 6 skipped

### v2026.05.14

- New `manage_component` tool: DFM component CRUD/create + PAS auto-sync (replaces `generate_component_dfm`)
- `delphi_file` renamed & enhanced: DFM binary auto-conversion, backup management, search positioning (formerly `file_tool`, legacy name still works)
- Install script refactored: Python-first with bat bootstrap, global/project modes
- Server restructuring: MCP tool registration and invocation logic separation
- New tests: file_tool, create_component_dfm, mcp_client, pasfmt
- New `code_hosting` tool: unified Gitea/GitHub/GitLab operations

Full history: See [CHANGELOG.md](CHANGELOG.md)

## Sponsor

If Daofy for Delphi is helpful to you, please consider sponsoring us through the following methods.
Your support means a lot! ❤️

### Alipay

**Account**: guansonghuan@sina.com (Name: 管耸寰, please include your QQ number)

<img src="https://blog.qdac.cc/wp-content/uploads/2018/04/pay_alipay.jpg" alt="Alipay QR Code" width="200"/>

### WeChat

**Account**: wangshengbo (send red packets or transfer)

<img src="https://blog.qdac.cc/wp-content/uploads/2018/04/pay_wechat.jpg" alt="WeChat QR Code" width="200"/>

### QQ

Send red packets to group owner directly.

<img src="https://blog.qdac.cc/wp-content/uploads/2018/04/pay_qq.png" alt="QQ QR Code" width="200"/>

**QQ Official Group**: 250530692

### Bank Transfer

| Bank | Name | Account | Branch |
|------|------|---------|--------|
| China Everbright Bank | 王胜波 | 6226 6208 0391 5552 | Changchun Renmin Street Sub-branch |
| China Construction Bank | 管耸寰 | 4367 4209 4324 0179 731 | Changchun Tuanfeng Savings Office |

## Contributing

Issues and Pull Requests are welcome!
