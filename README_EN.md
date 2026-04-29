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
| Help Documentation KB | `data/help-knowledge-base/` | Delphi CHM help documentation |
| Generic Document KB | `data/document-knowledge-base/` | txt/md/html/docx generic documents |
| Project KB | `<project-dir>/.delphi-kb/` | Project-level KB, stored in project directory |

Each knowledge base directory contains:
- `knowledge_base.sqlite` or `knowledge.sqlite` - SQLite database file
- `config.json` - Knowledge base configuration file

## Knowledge Base Configuration

Each knowledge base is configured via `config.json` file, supporting custom database, source paths, build parameters, etc.

### Delphi Source Knowledge Base Configuration

Location: `data/delphi-knowledge-base/config.json`

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

| Configuration | Description | Default |
|--------------|-------------|---------|
| `source.type` | Source type: `link`=symlink, `copy`=copy | `link` |
| `source.path` | Delphi source root directory | Auto-detect |
| `source.extensions` | File extensions to scan | `[".pas", ".dfm", ".inc"]` |
| `database.file` | Database filename | `knowledge_base.sqlite` |
| `database.cache_size` | Vector cache size | `10000` |
| `build.incremental` | Enable incremental build | `true` |
| `build.incremental_hash_mode` | Change detection: `mtime_size`=fast, `md5`=accurate | `mtime_size` |
| `build.parallel_workers` | Parallel worker processes | Auto-calculate |
| `build.batch_size` | Batch size | `1000` |

### Generic Document Knowledge Base Configuration

Location: `data/document-knowledge-base/config.json`

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
    "supported_extensions": [".txt", ".md", ".markdown", ".htm", ".html", ".docx", ".doc", ".pdf"]
  }
}
```

| Configuration | Description | Default |
|--------------|-------------|---------|
| `database.file` | Database filename | `documents.sqlite` |
| `build.parallel_workers` | Parallel workers (`null`=auto-calculate) | `null` |
| `build.batch_size` | Batch size | `50` |
| `build.supported_extensions` | Supported document formats | 8 formats |

### Third-party Library Knowledge Base Configuration

Location: `data/thirdparty-knowledge-base/config.json`

Same format as Delphi Source Knowledge Base, auto-generated via `delphi_kb(action=build, kb_type=thirdparty)`.

### Project Knowledge Base Configuration

Location: `<project-dir>/.delphi-kb/config.json`

Project KB config is auto-generated on first build, containing project source paths and third-party library paths.

### Configuration Effectiveness

All configuration items use default values when missing, ensuring system runs correctly:

- ✅ `database.file` - Effective
- ✅ `database.cache_size` - Effective
- ✅ `source.type/path` - Effective
- ✅ `build.incremental_hash_mode` - Effective
- ✅ `build.parallel_workers` - Effective
- ✅ `build.batch_size` - Effective
- ✅ `build.supported_extensions` - Effective (Document KB)

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
| `compile_project` | Compile Delphi project or check .pas file syntax | `project_path`, `target_platform`(win32/win64), `build_configuration`, `get_args_only` |
| `check_environment` | Diagnose environment, detect compilers, install pasfmt | `action`(check/detect/install/format_install) |
| `install_package` | Compile and install Delphi package to IDE | `package_path`, `target_platform`, `install` |
| `list_installed_packages` | List packages installed to IDE | - |

### Knowledge Base Tools

| Tool Name | Description | Key Parameters |
|-----------|-------------|----------------|
| `search_knowledge` | Search code/API/docs, build/view knowledge base | `action`(search/stats/build), `query`, `kb_type`, `search_type`, `top_k` |

### Source Code Tools

| Tool Name | Description | Key Parameters |
|-----------|-------------|----------------|
| `read_source_file` | Read file content or search by class/function name | `file_path`, `search_type`(path/class/function), `type_name`, `function_name` |

### Formatting Tools

| Tool Name | Description | Key Parameters |
|-----------|-------------|----------------|
| `format_delphi` | Format Delphi source code, check/set pasfmt | `action`(file/code/check/set_path/status), `file_path`, `code` |

### Async Task Tools

| Tool Name | Description | Key Parameters |
|-----------|-------------|----------------|
| `async_task` | Manage background tasks (e.g., build knowledge base) | `action`(start/status/result/list/cancel), `task_id` |

### Coding Standards Tools

| Tool Name | Description | Key Parameters |
|-----------|-------------|----------------|
| `get_coding_rules` | Get Delphi coding standards | `project_path`(optional) |

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

### v2026.04.26 (2026-04-26)

- Fixed multiple MCP interface bugs
  - `check_environment`: detect action parameter passing error; added install/format_install action implementation
  - `search_knowledge`: search result file path showing N/A (wrong key name); search_type filtering not working
  - Missing `config.set_config_manager` call causing "config manager not initialized" error
- Added `get_coding_rules` tool, exposing coding standards via MCP tool interface
- Added MCP resource export (`delphi://coding-rules`), AI agents can read coding rules via resources protocol
- Cleaned up invalid old code (net deletion of 1251 lines)
  - Removed 18 deprecated functions (build_knowledge_base, search_class, search_function, semantic_search, etc.)
  - Removed 5 deprecated config functions (set_compiler_config, detect_compilers, search_delphi_compilers, etc.)
  - Cleaned up 21 deprecated exports in __init__.py
- Fixed third-party knowledge base old schema compatibility (auto drop old tables and rebuild)
- Fixed unit type kind code from single-letter 'u' to double-letter 'UI'
- Removed unused SINGLE_TO_DOUBLE old data compatibility mapping
- Optimized 8 tool descriptions: added typical scenarios, action descriptions, parameter applicability

### v2026.04.25 (2026-04-25)

- Added installation script `install.ps1`
  - Auto-detect installed AI Agents (Claude Desktop, Trae, CodeArts, Cursor, OpenCode, Windsurf, Cline, Tongyi Lingma, Doubao, Kimi, etc.)
  - Auto-configure MCP Server to corresponding AI Agent
  - Support force reconfiguration

- Improved AI Agent detection logic
  - CodeArts Agent: Added AppData\Roaming\codearts-agent detection
  - OpenCode: Added ai.opencode.desktop desktop version and npm global installation detection
  - Cursor/Windsurf/Tongyi Lingma: Added AppData directory detection

- Added package installation tools
  - `install_package`: Compile and install .dproj/.dpk/.groupproj packages to IDE
  - `list_installed_packages`: List packages installed to IDE
  - Identify runtime packages (RuntimeOnlyPackage) and design-time packages, only install design-time packages

- Optimized coding standards (see config/CODING_RULES.mdc)
  - Restructured document with clear sections and version info
  - Added unit reference order, type declaration order, comment standards
  - Added event handler naming rules (On prefix removal, Before/After prefix retention)
  - Added enum naming rules (both prefixed and non-prefixed styles supported)
  - Added forward declaration and pointer type declaration order rules
  - Added type judgment warning (record may have Create method)
  - Fixed line width to 120 characters (for 16:9 screens)
  - Fixed code cleanup rules (direct cleanup for modification-introduced dead code)

### v2026.03.29 (2026-03-29)

- Fixed compilation parameter issues
  - Fixed `$(BDSLIB)` macro expansion path error (original path `lib\$(Platform)` caused double expansion)
  - Fixed `BDSCOMMONDIR` environment variable splitting logic error
  - Removed unnecessary quotes (`asyncio.create_subprocess_exec` handles space paths automatically)
  - Added default namespace `-NS` parameter to resolve SysUtils unit resolution issues
  - Updated parameter validation logic to allow semicolons and parentheses in path parameters

- Fixed project dependency analysis
  - Added thirdparty KB path to search path list
  - Supported case-insensitive matching (madbasic → madBasic)

- Unified tool return types
  - `compile_project` returns `CallToolResult`
  - `compile_file` returns `CallToolResult`
  - `get_compiler_args` returns `CallToolResult`

- Tool consolidation
  - Merged search functions into `search_knowledge`
  - Merged build functions into `build_knowledge`
  - Merged stats functions into `get_knowledge_stats`

- All pytest tests passed (15/15)

### v2026.03.28 (2026-03-28)

- Added path macro expansion tools
  - Added `src/utils/delphi_env.py` utility module
  - Support `$(BDS)`, `$(BDSCatalogRepository)`, `$(BDSUSERDIR)` path macro expansion
  - Added `get_catalog_repository_paths()` function to get GetIt component source paths
  - Added `resolve_delphi_search_paths()` function to integrate all search paths

- Optimized third-party library path handling
  - Use latest installed Delphi version (23.0 instead of 22.0)
  - Correctly filter Delphi system directories (Imports, BPL, DCP, etc.)
  - Added Studio Library registry path support
  - Auto-add GetIt CatalogRepository component source paths

- Rebuilt knowledge base
  - Delphi KB: 3207 files, 53943 classes, 442206 functions
  - Third-party KB: 19 paths, 264 files, 1584 classes, 20384 functions

- Fixed tool return type issues
  - Fixed `search_compilers` return type to CallToolResult
  - Fixed `get_compiler_args` return type to CallToolResult
  - Fixed `get_coding_rules` return type to CallToolResult
  - Fixed `check_pasfmt_installation` return type to CallToolResult
  - Fixed `format_code` return type to CallToolResult

- Fixed search result display issues
  - Fixed all search tools hardcoding only 3 results
  - Fixed `knowledge_base.py` `[:3]` limit to use `top_k` parameter

- Fixed project dependency analysis
  - Fixed `analyze_project_dependencies` division by zero error (when project units is 0)
  - Enhanced registry path macro expansion support
  - Support GetIt component path resolution

- Fixed knowledge base auto-loading
  - Fixed `read_source_file` knowledge base not auto-loading issue
  - Added auto-load logic when KB instance is None

- All pytest tests passed (11/11)

### v2026.03.26 (2026-03-26)

- Added pasfmt code formatting tools
  - Added `format_delphi_file` tool to format Delphi source files
  - Added `format_delphi_code` tool to format Delphi code strings
  - Added `install_pasfmt` tool to download and install pasfmt CLI or IDE plugin
  - Added `check_pasfmt_installation` tool to check pasfmt installation status
  - Added `set_pasfmt_path` tool to set pasfmt executable path
- Support downloading pre-compiled pasfmt binaries from GitHub (Windows 32/64-bit and Linux)
- Support Delphi 11/12/13 IDE plugin installation
- Adapted to pasfmt v0.7.0 command line parameters
- Support UTF-8/UTF-8 BOM/GBK encoded files
- Fixed test file import path issues

### v2026.03.21 (2026-03-21)
- Added help documentation knowledge base step-by-step build functionality
  - Added `extract_help_chm` tool to extract CHM files separately (step 1)
  - Added `scan_help_html` tool to scan HTML files separately (step 2)
  - Added `build_help_kb_index` tool to build vector index separately (step 3)
  - Supports incremental build, can specify external source directory to avoid repeated extraction
  - Supports limiting the number of files processed for small-scale testing
- Enhanced help documentation content extraction
  - HTML to Markdown conversion for better structured information retention
  - Extracts structured information such as classes, interfaces, types, functions, properties, events, constants
  - Extracts method signatures (supports Delphi and C++ syntax), parameters, return types
  - Extracts code examples (prioritizes extraction from HTML, supports syntax highlighting recognition)
  - Extracts Uses unit references (code example pages)
  - Saves complete document content (up to 3000 characters for indexing) to provide sufficient learning material for AI
- Improved search functionality
  - `search_help` supports semantic search for classes, functions, and documents
  - Search results include description information and similarity scores
- Added project dependency analysis functionality
  - Added `analyze_project_dependencies` tool to analyze project unit dependencies
  - Added `resolve_smart_library_paths` tool to intelligently resolve required third-party library paths
- Optimized compilation features
  - `compile_project` supports smart library path resolution, automatically analyzes project dependencies
  - Dynamically retrieves Delphi installation path from registry, no longer hardcodes rsvars.bat path
  - Prioritizes units in project directory, correctly handles files with same name
- Optimized knowledge base deduplication logic
  - Deduplicates based on full path, correctly handles files with same name in different directories
  - Preserves both relative and full paths for more reasonable query results
- Added incremental build scripts
  - `build_help_kb_incremental.py` supports skipping CHM extraction, directly rebuilds vector index
  - `rebuild_all_kbs.py` supports rebuilding all knowledge bases
- Fixed third-party library knowledge base service initialization issue
  - Fixed "service not initialized" error for `build_thirdparty_knowledge_base` and related tools
- Added source file reading functionality
  - Added `read_source_file` tool to locate file in knowledge base first, then read source content from disk
  - Added `search_and_read_file` tool to search for types (class/record/interface) or functions and automatically read the file content
  - Supports reading specified line ranges for viewing specific code segments
- Enhanced type search functionality (all knowledge bases uniformly support)
  - Added `search_thirdparty_record` tool to specifically search for record types
  - Added `search_by_filename` tool to support wildcard filename search
  - Extended knowledge base scanning to support class, record, interface, enum and other types
  - Added `type_kind` field to search results showing type category (class/record/interface/enum)
  - Official source, third-party library, and project knowledge bases all support record type search

### v2026.03.20 (2026-03-20)
- Added global third-party library knowledge base functionality
  - Added `build_thirdparty_knowledge_base` tool to build global third-party library knowledge base
  - Added `search_thirdparty_class` tool to search classes in third-party libraries
  - Added `search_thirdparty_function` tool to search functions in third-party libraries
  - Added `semantic_search_thirdparty` tool for semantic search in third-party libraries
  - Added `get_thirdparty_kb_stats` tool to get third-party library knowledge base statistics
  - Added `get_thirdparty_paths_global` tool to get third-party library paths list
- Optimized help documentation knowledge base building
  - `build_help_knowledge_base` supports async mode (enabled by default) to avoid timeout
  - Added `get_task_status` tool to query background task status
  - Added `list_tasks` tool to list all background tasks
- Fully backward compatible

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
