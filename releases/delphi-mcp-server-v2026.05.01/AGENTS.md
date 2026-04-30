# AGENTS.md - Agent Coding Guidelines

This file provides guidelines for agentic coding agents operating in this repository.

## Project Overview

This is a **Delphi MCP Server** - a Model Context Protocol server that provides Delphi project compilation capabilities and knowledge base querying for AI assistants (Claude Desktop, CodeArts Agent, etc.).

- **Language**: Python 3.10-3.14
- **Platform**: Windows
- **Test Framework**: pytest (with pytest-asyncio for async tests)
- **Key Dependencies**: mcp>=0.9.0, pydantic>=2.0.0, beautifulsoup4, lxml, requests
- **Optional Dependencies**: PyMuPDF (recommended for PDF), pdfplumber (fallback for PDF), python-docx

## Project Structure

```
delphi-complier-mcp-server/
├── src/                      # Main source code
│   ├── server.py             # MCP Server entry point
│   ├── tools/               # MCP tool implementations
│   ├── services/            # Business logic services
│   ├── models/              # Data models (Pydantic/dataclasses)
│   └── utils/               # Utility functions
├── tests/                   # Test files
├── config/                  # Configuration files
├── data/                    # Knowledge base data
├── docs/                    # Documentation
├── build_kb.py             # Knowledge base builder (full source)
├── build_kb_fmx.py         # Knowledge base builder (FMX only)
└── pyproject.toml          # Project configuration
```

---

## Build, Lint, and Test Commands

### Environment Setup

```bash
# Create and activate virtual environment (Windows)
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -e ".[dev]"  # Includes pytest, pytest-asyncio, pytest-cov

# Install optional PDF processing libraries
pip install PyMuPDF  # Recommended for PDF processing (better performance)
# OR
pip install pdfplumber  # Alternative for PDF processing (pure Python)
```

### Windows Encoding Settings

**IMPORTANT**: On Windows, always set UTF-8 encoding:

```bash
# Option 1: Per command
PYTHONIOENCODING=utf-8 python your_script.py

# Option 2: For session
set PYTHONIOENCODING=utf-8
python your_script.py
```

### Development Setup

```bash
# Install all dependencies (including dev)
pip install -e ".[dev]"

# Install in development mode with editable source
pip install -e .
```

### Testing Commands

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_knowledge_base.py

# Run tests with verbose output
pytest -v

# Run a single test by name
pytest tests/test_knowledge_base.py::test_search_by_class_name -v

# Run tests with coverage report
pytest --cov=src --cov-report=html

# Run tests and generate XML coverage report for CI
pytest --cov=src --cov-report=xml

# Run tests with specific markers (if any are defined)
pytest -m "not slow"

# Run tests and stop after first failure
pytest -x
```

### Code Quality & Linting

```bash
# Type checking with mypy (if configured)
mypy src/

# Format code with black (if installed)
black src/ tests/

# Sort imports with isort (if installed)
isort src/ tests/

# Lint with flake8 (if installed)
flake8 src/ tests/
```

### Running the Server

```bash
# Run the MCP server
python src/server.py

# Run with specific configuration
python src/server.py --config config/config.json
```

### Building Knowledge Bases

```bash
# Build FMX only knowledge base (~30s, 311 files)
python build_kb_fmx.py

# Build full source knowledge base (~65s, 2768 files, 3.5M lines)
python build_kb.py

# Build project knowledge base (via MCP tool)
# delphi_kb(action="build", kb_type="project", project_path="path/to/project.dproj")

# Run with custom paths
python build_kb.py --source C:\Delphi\Source --output data/delphi-kb/
```

---

## Delphi Knowledge Base Quick Reference

### Entity Types (Two-Letter Codes)

| Code | Type | Description |
|------|------|-------------|
| **TC** | Type/Class | class |
| **TR** | Type/Record | record |
| **TI** | Type/Interface | interface |
| **TE** | Type/Enum | enum |
| **TS** | Type/Set | set of |
| **TY** | Type | type alias |
| **FF** | Function | function |
| **FP** | Function | procedure |
| **CC** | Constant | const |
| **CR** | Constant | resourcestring |

### Search Functions

- Use `search_by_name()` for generic searches (covers all types)
- Use `search_by_class_name()` specifically for class types (TC)
- Prefer generic naming over single-letter codes for clarity

### Knowledge Base Types (via `delphi_kb` tool)

| kb_type | Description | Build Command |
|---------|------------|---------------|
| `delphi` | Delphi 官方源码 (RTL/VCL/FMX 等) | `action=build, version=<ver>` |
| `project` | 项目级知识库 (项目源码 + 三方库) | `action=build, project_path=<.dproj>` |
| `thirdparty` | 全局共享第三方库知识库 | `action=build, version=<ver>` |
| `document` | 通用文档 (txt/md/html/docx/pdf/epub/hlp/chm/网页) | `action=build` + `directory`/`url`/`urls` |

### Source Scanner File Extensions

The `DelphiSourceScanner` scans these extensions:
- `.pas`, `.dpr`, `.dpk`, `.dfm`, `.inc`

### Incremental Build Notes

- **mtime_size mode** (default): Fast change detection using file modification time + size
- **md5 mode**: Accurate but slower, computes file hash for every file
- **Project KB**: Shares third-party paths with global KB to avoid redundant scanning
- **Help KB**: Supports incremental update (skip unchanged files by mtime)

---

## Code Style Guidelines

### General Principles

- Use **type hints** for all function parameters and return types
- Use **Pydantic models** or **dataclasses** for data structures
- Use **async/await** for I/O operations
- Follow **PEP 8** conventions (max line length: 100 chars)
- Use **f-strings** for string formatting (not `%` or `.format()`)

### Imports Order & Grouping

Group imports in this order:
1. Standard library imports
2. Third-party imports  
3. Local application imports

Separate each group with a blank line. Sort imports alphabetically within each group.

```python
# Standard library
import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

# Third-party
import pydantic
from mcp import Client, Server

# Local application
from src.models.delphi_entities import Entity
from src.utils.file_utils import read_file
```

### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Modules | snake_case | `scan_delphi_sources.py` |
| Classes | PascalCase | `DelphiSourceScanner` |
| Functions | snake_case | `_analyze_file_worker()` |
| Variables | snake_case | `source_files` |
| Constants | UPPER_SNAKE | `KIND_CLASS = 'TC'` |
| Private functions | `_prefix` | `_parse_entity()` |
| Test functions | `test_` prefix | `test_search_by_class_name()` |
| Test classes | `Test` prefix | `TestKnowledgeBase` |

### Type Annotations

Always use type hints for function signatures and class attributes:

```python
def process_file(file_path: Path, encoding: str = "utf-8") -> Optional[List[Entity]]:
    """Process a single Delphi source file."""
    
    # Function with docstring and explicit return type
    pass

class DelphiScanner:
    def __init__(self, source_dir: Path, max_workers: int = 4) -> None:
        self.source_dir = source_dir
        self.max_workers = max_workers
        self.files_processed: List[Path] = []
```

### Error Handling

- Use specific exception types, not generic `Exception`
- Include descriptive error messages with context
- Use `try/except` blocks only when you can handle the exception

### Documentation

- Use docstrings for all public functions and classes
- Follow Google-style docstring format
- Include parameter types, return types, and example usage

### Testing Conventions

- Test file names: `test_*.py`
- Test class names: `Test*`
- Test method names: `test_*`
- Use `pytest` fixtures for setup/teardown
- Mock external dependencies using `unittest.mock`

## Agent 编码工作流

### 编译 Delphi 代码前的规则获取

AI Agent 在编译或生成 Delphi 代码前，**必须**先调用 `get_coding_rules` 获取编码规则：

```
步骤:
1. 调用 get_coding_rules(project_path="<项目.dproj路径>")
2. 工具返回 默认规则 + 用户自定义规则的合并内容（用户规则覆盖默认）
3. 严格按返回的规则编写/修改代码
4. 编译项目验证
```

规则包含：命名规则、格式化规则、类型声明顺序、文件头注释、修改代码约束、审核要点等。

### 知识库使用优先级

搜索 Delphi API 时，按以下优先级：

1. `delphi_kb(kb_type="project", project_path=..., ...)` — 项目知识库（项目特有代码，最优先）
2. `delphi_kb(kb_type="document", ...)` — 文档知识库（API 描述、示例、用法）
3. `delphi_kb(kb_type="delphi", ...)` — 源码知识库（RTL/VCL/FMX 定义声明）
4. `delphi_kb(kb_type="thirdparty", ...)` — 三方库知识库（第三方组件）

### Kind Constants

Use two-letter codes defined in `scan_delphi_sources.py`:

```python
KIND_CLASS = 'TC'      # class
KIND_RECORD = 'TR'    # record
KIND_INTERFACE = 'TI' # interface
KIND_ENUM = 'TE'       # enum
KIND_SET = 'TS'        # set of
KIND_TYPE = 'TY'       # type alias
KIND_FUNC = 'FF'       # function
KIND_PROC = 'FP'      # procedure
KIND_CONST = 'CC'     # const
KIND_RESOURCE = 'CR'  # resourcestring
```


