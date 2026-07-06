# Daofy MCP Server 审计报告

**审计日期**: 2026-06-25  
**项目版本**: 2026.06.22  
**审计范围**: 代码质量、项目结构、依赖管理、安全性、文档完整性  
**审计人**: LangRouter Auto

---

## 总体评价

Daofy 是一个成熟的 Python MCP Server，为 Delphi IDE 提供编译、知识库搜索、文件操作、自动化测试等全生命周期工具链。项目结构清晰（services/tools/utils 分层），测试覆盖较完整（60+ 测试文件），编码规范良好。

**整体评级**: B+（良好，存在一些值得关注的问题）

---

## 一、严重问题

### 1.1 `except Exception:` 裸捕获过多

全项目大量使用 `except Exception:` 而不绑定变量（缺少 `as e`），且未用 `exc_info=True` 记录堆栈。这会导致：
- 异常详情丢失，排查困难
- 可能静默吞掉不该吞的错误（如 `KeyboardInterrupt`）

**影响文件**: `server.py` 中 ~15 处，`async_tasks.py`、`file_tool.py`、`knowledge_base.py`、`compile_project.py` 等均有分布

**示例**:
```python
# server.py:2301
except Exception:
    logger.warning("清理 pkb_cache 时发生异常", exc_info=True)

# 虽然用了 exc_info=True，但仍建议捕获具体异常或至少 as e
```

**建议**: 统一改为 `except Exception as e:` + `logger.warning("...", exc_info=True)`，或捕获具体异常类型。

### 1.2 `winreg` 重复导入

`server.py` 第 15 行和第 252 行都执行了 `import winreg`。第 252 行的导入在 `run_server()` 函数体内，属于不必要的重复导入。

**建议**: 删除第 252 行的 `import winreg`，函数体内直接使用模块级导入。

### 1.3 `pydantic` 依赖几乎未使用

`pyproject.toml` 将 `pydantic>=2.0.0` 列为主依赖，但全项目仅在 `server.py:1609` 有一处使用：
```python
from pydantic import AnyUrl
```
使用频率极低，应考虑降级为可选依赖或移除。

---

## 二、代码结构与组织

### 2.1 大模块拆分

| 文件 | 行数 | 评价 |
|------|------|------|
| `src/server.py` | 2368 | 过大，建议拆分 — 尤其是工具 handler 定义（~900 行）和 list_tools schema 定义（~600 行） |
| `src/tool_docs.py` | 1033 | 工具文档与 schema 分离做得好，但仍有拆分空间 |
| `install_mcp.py` | 1980 | 安装脚本过长，可拆分出独立功能模块 |

**建议**: 将 `server.py` 中的 `list_tools()` 的 Tool schema 定义拆分到独立文件（如 `tool_schemas.py`），将 tool handler 拆分到 `handlers/` 目录。

### 2.2 调试文件滞留项目根目录

```text
_debug_ocr.py      (2288 bytes)
_debug_pyclipper.py (3312 bytes)
_test_ocr.py        (1505 bytes)
```

虽已被 `.gitignore` 忽略，但留在磁盘上易造成混淆。建议清理或移入 `tests/debug/`。

### 2.3 `tests/` 中含 Delphi 源码

```text
rtti_comprehensive_test.dpr  (16KB)
rtti_sample_test.dpr
test_attrs_minimal.dpr
test_min.dpr
test_getattrs2.dpr
test_getattrs_minimal.dpr
```

这些 Delphi 项目文件用于 RTTI 集成测试，放在 `tests/` 中合理，但建议移入 `tests/fixtures/` 子目录以区分 Python 测试和测试固件。

---

## 三、依赖管理

### 3.1 已移除的依赖未清理

根据提交 `878c3af`（perf: scanner 移除 BeautifulSoup 依赖，html2text 替代 HTML 处理），`beautifulsoup4` 已不再被 `scanner.py` 使用。但 `pyproject.toml` 仍保留：
```toml
beautifulsoup4>=4.12.0
lxml>=4.9.0
```

**建议**: 确认 `beautifulsoup4` 和 `lxml` 是否仍被其他模块使用，如已无依赖则移出。

### 3.2 `python-docx` 使用情况不明

`pyproject.toml` 依赖了 `python-docx>=0.8.11`，但仅在 `copyright_service.py` 中可能用于 Word 文档生成。建议标注为 optional dependency。

---

## 四、安全性

### 4.1 路径安全验证良好

`file_tool.py` 实现了完整的路径安全性校验（`_validate_path`），包含：
- Null 字节注入检查
- 系统敏感目录保护
- 符号链接解析

**评价**: ✅ 良好实践

### 4.2 子进程参数校验

`code_hosting.py` 实现了 `_validate_git_arg()` 防止参数注入（空字节、换行、`--xxx` 形式的参数），已完成相关测试覆盖。

**评价**: ✅ 良好实践

---

## 五、测试覆盖

### 5.1 测试总数

约 60+ 个测试文件，数百个测试用例。主要覆盖：

| 模块 | 测试文件 | 覆盖度 |
|------|---------|--------|
| 文件操作 | `test_file_tool.py` (100KB) | 高 |
| 代码托管 | `test_code_hosting.py` (63KB) | 高 |
| 审计 | `test_audit_integration.py` (43KB) | 高 |
| RTTI 桥接 | `test_rtti_*.py` (多文件) | 高 |
| 知识库 | `test_document_kb.py`, `test_example_kb.py` 等 | 中-高 |
| OCR | `test_ocr_service.py`, `test_ocr_tool.py` | 中 |

### 5.2 测试缺口

- **`test_doc_consistency.py`**: 文档一致性测试（5362 字节），覆盖面有限
- **UI 自动化测试**: `test_console_automation.py` 存在，但 GUI 自动化测试覆盖不足
- **知识库构建的集成测试**: 缺少端到端的 KB 构建 + 搜索验证

---

## 六、文档

### 6.1 文档完整性

`docs/` 目录文档较为完善：

| 文档 | 说明 | 评价 |
|------|------|------|
| `project.md` | 项目整体说明 | ✅ |
| `delphi_kb.md` | 知识库使用 | ✅ |
| `file_tool_audit_report.md` | 文件工具审计 | ✅ |
| `rtti-mcp-bridge-design.md` | RTTI 桥接设计 | ✅ |
| `todos.md` / `tofix.md` | 已知问题和待办 | ✅ |

### 6.2 配置规范文档

`config/CODING_RULES.mdc` 达 155KB，包含详细的 Delphi 编码规范。内容详尽但体积较大，建议拆分或提供快速导航索引。

---

## 七、环境与构建

### 7.1 编译器环境

| 项目 | 状态 |
|------|------|
| Delphi 版本 | 13 Florence (Win32) |
| 编译器数量 | 2 个（均可用） |
| 第三方库路径 | 212 个已配置 |
| Delphi 帮助目录 | 已自动检测 |

### 7.2 AST 分析引擎（daudit）

`tools/daudit/daudit.exe` (8.5MB) 可用。但存在大量构建产物驻留：

| 文件 | 大小 | 建议 |
|------|------|------|
| `daudit.exe.bak` | 5.5 MB | 删除（备份文件） |
| `daudit.map` | 5.8 MB | 删除（调试映射，运行不需要） |
| `daudit.drc` | 33 KB | 可删除（资源编译中间文件） |
| `crash.log`, `exception.log`, `lsp_server.log` | ~1.4MB | 可清理 |
| `cache/` 目录 | ~数百 KB | 按需清理 |

---

## 八、知识库数据

`data/` 目录中存在多个备份版本：

```text
document-knowledge-base          ← 当前版本
document-knowledge-base.bak.v3   ← 可清理
document-knowledge-base.bak.v4   ← 可清理
document-knowledge-base.bak.v5   ← 可清理
```

多个备份占用磁盘空间，建议确认不再需要后清理旧备份。

---

## 九、已知待处理问题（来自 tofix.md）

| 编号 | 问题 | 状态 | 优先级 |
|------|------|------|--------|
| 8 | 新增平台 API 缺少真实平台契约验证 | ⏳ 待验证 | 中 |
| 11 | 运行中的 MCP 服务不自动加载新 schema | 📌 运维提示 | 低 |

---

## 十、优点与亮点

1. **架构清晰**: services/tools/utils 三层分离，模块职责明确
2. **测试完善**: 60+ 测试文件，对核心功能覆盖充分
3. **安全实践好**: 路径校验、命令注入防护
4. **异常日志**: 多数异常场景有 `exc_info=True` 记录堆栈
5. **版本管理**: `__version__.py` 动态读取 `pyproject.toml`，单点维护
6. **智能提示**: `_get_smart_hint()` 在工具返回后提供上下文建议
7. **渐进式功能**: OCR 等功能设计为 optional dependencies，不增加基础安装负担
8. **提交规范**: Git 提交信息清晰，中文描述 + 英文标签

---

## 十一、改进建议优先级

| 优先级 | 建议 |
|--------|------|
| P0 | 修复裸 `except Exception:` 缺乏变量绑定的问题 |
| P1 | 拆分过大的 `server.py`（工具 schema + handler 分离） |
| P1 | 清理 `data/` 中的旧 KB 备份和 `tools/daudit/` 中的构建产物 |
| P2 | 确认 `beautifulsoup4` 和 `lxml` 依赖是否仍需保留 |
| P2 | 将 `pydantic` 从主依赖降级为可选 |
| P2 | 将调试脚本移入 `tests/debug/` 或删除 |
| P3 | 将 Delphi 测试固件移入 `tests/fixtures/` |
| P3 | 拆分 `config/CODING_RULES.mdc` 为大文档 |
