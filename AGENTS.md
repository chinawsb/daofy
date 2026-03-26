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
│   ├── models/               # Data models (Pydantic/dataclasses)
│   └── utils/                # Utility functions
├── tests/                    # Test files
├── config/                   # Configuration files
├── data/                    # Knowledge base data
├── docs/                    # Documentation
└── pyproject.toml           # Project configuration
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
pip install -e ".[dev]"  # Install with dev dependencies
```

### Running Tests

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_knowledge_base.py

# Run a single test function
pytest tests/test_knowledge_base.py::test_search_class -v

# Run with coverage
pytest --cov=src --cov-report=html

# Run tests matching a pattern
pytest -k "test_search"
```

### Running the Server

```bash
# Run MCP server directly
python src/server.py

# Or use the installed script
delphi-mcp-server
```

---

## Code Style Guidelines

### General Principles

- Use **type hints** for all function parameters and return types
- Use **Pydantic models** or **dataclasses** for data structures
- Use **async/await** for I/O operations
- Follow **PEP 8** with the conventions below
- Use **UTF-8 encoding** with `utf-8` BOM for Python files (handled automatically)

### Imports

**Order (from top to bottom)**:
1. Standard library imports
2. Third-party imports
3. Local application imports

**Within each group**: alphabetically sorted

```python
# Standard library
import asyncio
import sys
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

# Third-party
from mcp.server import Server
from pydantic import BaseModel

# Local (use relative imports within packages)
from src.services.compiler_service import CompilerService
from src.tools.compile_project import compile_project
from src.utils.logger import get_logger
```

### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Modules | lowercase, snake_case | `compile_project.py`, `knowledge_base.py` |
| Classes | PascalCase | `CompilerService`, `DelphiKnowledgeBaseService` |
| Functions | snake_case | `compile_project()`, `get_compiler_args()` |
| Variables | snake_case | `project_path`, `compiler_service` |
| Constants | UPPER_SNAKE_CASE | `MAX_TIMEOUT`, `DEFAULT_PLATFORM` |
| Private functions | _leading_underscore | `_internal_method()` |
| Type aliases | PascalCase | `CompileResult`, `CompileOptions` |

### Type Hints

```python
# Always use type hints
from typing import Optional, List, Dict, Any, Union

def compile_project(
    project_path: str,
    target_platform: str = "win32",
    output_path: Optional[str] = None,
    timeout: int = 600,
    conditional_defines: Optional[List[str]] = None,
) -> Dict[str, Any]:
    # ...
```

### Docstrings

Use Google-style docstrings:

```python
async def compile_project(
    project_path: str,
    target_platform: str = "win32",
) -> Dict[str, Any]:
    """
    Compile a Delphi project.

    Args:
        project_path: Path to the project file (.dproj or .dpr)
        target_platform: Target platform (win32/win64)
    
    Returns:
        Dictionary containing compilation result with status, errors, and warnings
    
    Raises:
        ValueError: If project_path is invalid
        CompilerError: If compilation fails
    """
    # ...
```

### Error Handling

- Use **specific exception types** when possible
- Log errors with appropriate level before re-raising or returning error results
- Return error dictionaries in MCP tool responses rather than raising exceptions to the caller

```python
# Good pattern for MCP tools
async def compile_project(...) -> Dict[str, Any]:
    logger.info(f"Received compile request: {project_path}")
    
    try:
        # Business logic
        result = await _compiler_service.compile_project(request)
        return result.to_dict()
    
    except ValueError as e:
        logger.error(f"Invalid input: {str(e)}", exc_info=True)
        return {
            "status": "failed",
            "error_code": "INVALID_INPUT",
            "error_message": str(e),
            "duration": 0
        }
    except Exception as e:
        logger.error(f"Compilation failed: {str(e)}", exc_info=True)
        return {
            "status": "failed",
            "error_code": "INTERNAL_ERROR",
            "error_message": str(e),
            "duration": 0
        }
```

### Logging

Use the project's logger:

```python
from src.utils.logger import get_logger

logger = get_logger(__name__)

logger.debug("Detailed debug information")
logger.info("Normal operation information")
logger.warning("Warning message")
logger.error("Error message", exc_info=True)
```

### Data Models

Use **Pydantic BaseModel** for input validation and **dataclasses** for internal data:

```python
# For API/input models - use Pydantic
from pydantic import BaseModel, Field
from enum import Enum

class TargetPlatform(str, Enum):
    WIN32 = "win32"
    WIN64 = "win64"

class CompileOptions(BaseModel):
    target_platform: TargetPlatform = TargetPlatform.WIN32
    timeout: int = Field(default=600, ge=1)
    optimization_enabled: bool = True

# For internal data - use dataclasses
from dataclasses import dataclass, field

@dataclass
class CompileMessage:
    file_path: str
    line: int
    column: int
    message: str
    message_type: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {...}
```

### Async/Await

- Use `async def` for I/O-bound operations
- Use `await` for all async calls
- Use `asyncio.gather()` for parallel operations when appropriate

```python
async def some_function() -> Dict[str, Any]:
    # Good: gather multiple async calls
    results = await asyncio.gather(
        service_a.fetch_data(),
        service_b.fetch_data(),
    )
    return {"data": results}
```

### String Formatting

- Use f-strings for simple interpolation
- Use `.format()` for complex formatting
- Use logging with f-strings for user-facing messages

```python
# Good: f-strings for simple cases
logger.info(f"Compiling project: {project_path}")

# Good: format for multi-line or complex
message = "Project: {}\nStatus: {}\nDuration: {}ms".format(
    project_path,
    result.status,
    result.duration
)
```

### File Encoding

Always use UTF-8 encoding. The project sets encoding at startup:

```python
import sys
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'

if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
```

---

## Delphi Coding Rules (for generated code)

This project also contains tools for working with Delphi source code. The coding rules are in `config/CODING_RULES.mdc`:

### Naming Rules
- **Constants**: UPPER_CASE with underscores
- **Keywords**: all lowercase
- **Types** (classes, records, interfaces, enums): PascalCase with `T` prefix
- **Interfaces**: PascalCase with `I` prefix
- **Exceptions**: PascalCase with `E` prefix
- **Pointers**: PascalCase with `P` prefix (e.g., `PIpAddr`)
- **Private/protected fields**: `F` prefix (e.g., `FName`)
- **Properties**: PascalCase, no prefix
- **Parameters**: `A` prefix (e.g., `AFileName`), except:
  - Loop variables: `I`, `J`, `K`
  - Pointer variables: `p`, `ps`, `pd`
  - String variables: `s`
  - Temporary variables: `T`

### Code Formatting
- Follow Delphi default formatting rules
- Correct Delphi's generic formatting issues

### Modification Rules
- Backup files to `__history/` before modifying (following Delphi's `.~N~` convention)
- Check file encoding and convert if needed before modifying
- After modifying, compile and check for syntax errors
- Before modifying identifiers, search to confirm scope

### Review Rules
- Memory leak detection
- Exception handling completeness (try/except/finally)
- Identifier naming compliance
- Array and pointer bounds checking
- Thread synchronization verification

---

## MCP Tool Development

When adding new MCP tools:

1. **Define the tool** in `src/server.py` under `@server.list_tools()`:
   ```python
   Tool(
       name="tool_name",
       description="Tool description",
       inputSchema={...}
   )
   ```

2. **Implement the handler** in `@server.call_tool()`:
   ```python
   elif name == "tool_name":
       result = await tool_module.tool_function(**arguments)
   ```

3. **Use Pydantic models** for input validation:
   - Define request models in `src/models/`
   - Use enums for constrained values

4. **Return structured results**:
   - Return `Dict[str, Any]` for tool results
   - Include `status`, error codes, and messages
   - Use consistent error handling patterns

---

## Additional Notes

- The server runs on stdio - no HTTP server needed
- MCP tools must be async-compatible
- All paths should handle both Windows and cross-platform concerns where needed
- Knowledge bases are stored in `data/` directory
- Configuration is in `config/` directory
