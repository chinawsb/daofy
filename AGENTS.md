# AGENTS.md - Agent Coding Guidelines

This file provides guidelines for agentic coding agents operating in this repository.

## Project Overview

This is a **Delphi MCP Server** - a Model Context Protocol server that provides Delphi project compilation capabilities and knowledge base querying for AI assistants (Claude Desktop, CodeArts Agent, etc.).

- **Language**: Python 3.10-3.14
- **Platform**: Windows
- **Test Framework**: pytest
- **Key Dependencies**: mcp>=0.9.0, pydantic>=2.0.0, beautifulsoup4, lxml, requests

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
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -e ".[dev]"
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

### Running Tests

```bash
pytest
pytest tests/test_knowledge_base.py
pytest --cov=src --cov-report=html
```

### Running the Server

```bash
python src/server.py
```

---

## Knowledge Base Architecture

### Database Schema (3 Tables)

| Table | Description | Records |
|-------|------------|---------|
| **metadata** | Key-value pairs (total_files, total_lines, scan_date) | 3 |
| **files** | Source file information | ~2,768 |
| **vocabularies** | Unified entity table with kind codes | ~774,024 |

**注意**: 没有 `entities` 表。实体数据存储在 `vocabularies` 表中。

### Kind Codes (Two-Letter)

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

### Entity Structure

```python
{
    'name': 'TFontStyles',    # Entity name
    'kind': 'TS',             # Kind code
    'parent': None,          # Parent class/interface
    'line': 83,              # Line number
    'definition': 'set'      # Definition string
}
```

---

## Knowledge Base Builder

### Building Knowledge Bases

```bash
# FMX only (~30s, 311 files)
python build_kb_fmx.py

# Full source (~65s, 2768 files, 3.5M lines)
python build_kb.py
```

### Multiprocessing Best Practices

**关键点**:
1. 先收集所有目录的文件，再统一分配给进程池
2. Worker数量: `min(max(1, total_files // 100), cpu_cores - 1)`
3. Chunk size: `max(50, total_files // max_workers)` - 减少IPC开销
4. ProcessPoolExecutor 必须在脚本层创建（`if __name__ == "__main__"`）

```python
# build_kb.py
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
from src.services.knowledge_base.scan_delphi_sources import _analyze_file_worker

def main():
    cpu_cores = cpu_count()
    all_files = collect_all_files(base_dir)
    total_files = len(all_files)
    
    max_workers = min(max(1, total_files // 100), max(1, cpu_cores - 1))
    chunk_size = max(50, total_files // max_workers)
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = executor.map(_analyze_file_worker, all_files, chunksize=chunk_size)
```

### Scan Results Storage

直接插入到 files 和 entities 表，不保存 JSON：

```python
# 直接插入 files
cursor.execute("""
    INSERT INTO files (path, full_path, extension, size, line_count, hash, last_modified, units, uses)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (path, full_path, ext, size, lines, hash, modified, json.dumps(units), json.dumps(uses)))

# 直接插入 entities
cursor.execute("""
    INSERT INTO entities (file_id, name, kind, parent, line, definition)
    VALUES (?, ?, ?, ?, ?, ?)
""", (file_id, name, kind, parent, line, definition))
```

---

## Code Style Guidelines

### General Principles

- Use **type hints** for all function parameters and return types
- Use **Pydantic models** or **dataclasses** for data structures
- Use **async/await** for I/O operations
- Follow **PEP 8** conventions

### Imports

Order: Standard library → Third-party → Local application

### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Modules | snake_case | `scan_delphi_sources.py` |
| Classes | PascalCase | `DelphiSourceScanner` |
| Functions | snake_case | `_analyze_file_worker()` |
| Variables | snake_case | `source_files` |
| Constants | UPPER_SNAKE | `KIND_CLASS = 'TC'` |

### Kind Constants

使用两字母代码定义在 `scan_delphi_sources.py`:

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

### Regex Patterns for Entity Extraction

All regex patterns are defined in `scan_delphi_sources.py`:

```python
# 类型定义 (type alias)
_TYPE_PATTERN_1 = re.compile(r'^\s*type\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([^;(]+)', re.MULTILINE)
_TYPE_PATTERN_2 = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*array\s+of', re.MULTILINE)
_TYPE_PATTERN_3 = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*procedure\s*\([^)]*\)', re.MULTILINE)
_TYPE_PATTERN_PTR = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\^', re.MULTILINE)

# 常量定义
_CONST_PATTERN = re.compile(r'^\s*(const|resourcestring)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([^\n;]+)', re.MULTILINE | re.IGNORECASE)
_CONST_PATTERN_TYPED = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*[^\s=]+\s*=\s*([^\n;]+)', re.MULTILINE | re.IGNORECASE)
_CONST_PATTERN_SIMPLE = re.compile(r'^\s*([A-Z][a-zA-Z0-9_]*)\s*=\s*([^;{]+);', re.MULTILINE | re.IGNORECASE)
```

**支持的实体类型**:
- `TYPE_PATTERN_1`: `type TMyType = Integer;`
- `TYPE_PATTERN_2`: `TMyArray = array of Integer;`
- `TYPE_PATTERN_3`: `TProc = procedure; TNotifyEvent = procedure(Sender) of object;`
- `TYPE_PATTERN_PTR`: `PPointerList = ^TPointerList;`
- `CONST_PATTERN`: `const L1=1;` 或 `resourcestring S1='a';`
- `CONST_PATTERN_TYPED`: `SMenuSeparator: string = '-';`
- `CONST_PATTERN_SIMPLE`: `SIntOverflow = 'Integer overflow'; toInteger = Char(3);`

**注意**: `_CONST_PATTERN_SIMPLE` 必须有2个捕获组，否则运行时报错 "no such group"。

---

## Delphi Coding Rules

### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Constants | UPPER_CASE | `MAX_BUFFER_SIZE` |
| Types | PascalCase + T prefix | `TButton`, `TStringList` |
| Interfaces | PascalCase + I prefix | `IInterface`, `IEnumerator` |
| Exceptions | PascalCase + E prefix | `EInvalidArgument` |
| Class Fields | F prefix | `FName`, `FCount` |
| Parameters | A prefix | `AFileName`, `ACount` |
| Single-letter params | Keep as-is | `I: Integer`, `J: Integer` |
| Params already starting with A | Keep unchanged | `Accept` stays as `Accept` |
| Other params | Add A prefix | `Count: Integer` → `ACount: Integer` |

### Code Style

- **NO comments** unless explicitly requested by user
- Keep code concise and self-documenting
- Follow existing code patterns in the file

### Parameter Naming Examples

```delphi
// Correct
procedure ProcessItems(AItems: TArray<Integer>; ACount: Integer);
procedure Connect(AHost: string; APort: Word; AAccept: Boolean);

// Avoid (unless single-letter)
procedure Process(Items: TArray<Integer>; Count: Integer);
```

### Modifications & Backups

- Create historical backups before major modifications
- Backup naming: `filename.backupN` or `backup_YYYYMMDD/`

---

## MCP Tool Development

When adding new MCP tools:

1. Define the tool in `src/server.py`
2. Implement the handler in `@server.call_tool()`
3. Use Pydantic models for input validation
4. Return structured Dict results

---

## Additional Notes

- The server runs on stdio - no HTTP server needed
- MCP tools must be async-compatible
- Knowledge bases stored in `data/` directory
- Always use UTF-8 encoding on Windows

---

## MCP Tools Overview

### Compilation Tools

| Tool | Description |
|------|-------------|
| `compile_project` | 编译 Delphi 项目（支持 .dproj/.dpr/.dpk） |
| `install_package` | 编译并安装 Delphi 组件包 |
| `check_environment` | 检查编译环境配置 |
| `format_delphi` | 格式化 Delphi 源码（使用 pasfmt） |

### Knowledge Base Tools

| Tool | Description |
|------|-------------|
| `delphi_kb` | Delphi 代码知识库查询（类/函数/单元搜索） |
| `read_source_file` | 读取 Delphi 源文件内容 |

### compile_project 支持的文件类型

| 扩展名 | 说明 | 特殊处理 |
|--------|------|---------|
| `.dproj` | 项目文件 | 标准 MSBuild 编译 |
| `.dpr` | 项目源文件 | 查找对应 .dproj 或直接编译 |
| `.dpk` | 组件包文件 | 自动检测包类型，设计期包可自动安装 |

---

## Knowledge Base Features

### Delphi Knowledge Base

- **存储位置**: `data/delphi-knowledge-base/`
- **数据库**: SQLite (knowledge.sqlite)
- **索引**: 逆序索引 (`name_lower_rev`) + 向量索引（TF-IDF）
- **搜索**: 支持语义搜索、模糊搜索、精确搜索

### Document Knowledge Base

- **存储位置**: `data/document-knowledge-base/`
- **支持格式**: txt, md, html, docx, doc, pdf, epub, 网页
- **索引**: 
  - 逆序索引 (`title_rev`) - 优化前缀/后缀匹配
  - FTS5 全文索引 - BM25 排序（懒加载）
- **搜索策略**: 
  - FTS5 覆盖率 ≥ 50% → FTS5 MATCH（快）
  - FTS5 覆盖率 < 50% →/LIKE 降级 + 后台构建 FTS5

### Help Knowledge Base

- **存储位置**: `data/help-knowledge-base/`
- **来源**: Delphi CHM 帮助文件
- **索引**: FTS5 全文索引（懒加载）
- **实体**: 类、函数、属性、事件

---

## PDF Processing

PDF 处理支持两种库（优先级递减）：

1. **PyMuPDF** (推荐) - 性能更好
   ```bash
   pip install PyMuPDF
   ```

2. **pdfplumber** (备选) - 纯 Python
   ```bash
   pip install pdfplumber
   ```

---

## Component Package Compilation

### .dpk 文件编译流程

```python
compile_project("component.dpk")
  ↓
检测包类型（运行期/设计期）
  ↓
编译生成 .bpl 文件
  ↓
设计期包 + install_if_design_package=True
  ↓
注册到 IDE 注册表
```

### 包类型检测

设计期包标记：
- `{$DESIGNONLY}` 编译指令
- `requires dsnide` 依赖
- `requires DesignIntf, DesignEditors` 依赖

### 复用函数

`compile_project` 复用 `install_package` 的函数：
- `_is_runtime_only_package()` - 检测包类型
- `_compile_single_package()` - 编译单个包
- `_register_packages_to_ide()` - 注册到 IDE
