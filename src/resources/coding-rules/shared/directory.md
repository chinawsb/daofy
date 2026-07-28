<!-- @when: 工作开始前了解目录约定，或需要创建/清理文件时 -->
<!-- @chain: after=workflow.md, before=agent-rules.md -->

## 📁 目录约束

AI Agent 工作时必须遵守以下目录约定，便于后期清理和维护。

### 标准目录结构

```
project/
├── src/                    ← 源码（Python/Delphi）
├── tests/                  ← 测试用例（test_*.py, run_*.py）
├── docs/                   ← 文档（用户手册、设计文档）
├── scripts/                ← 辅助脚本（构建/部署/工具脚本）
├── tools/                  ← 工具程序（pasfmt/7z/daudit 等）
├── data/                   ← 知识库数据（运行时生成，gitignore）
├── logs/                   ← 日志文件（运行时生成，gitignore）
├── config/                 ← 配置文件（compilers.json 等）
├── releases/               ← 发布包（gitignore）
├── benchmarks/             ← 性能基准测试（gitignore）
└── .tmp/                   ← 临时工作目录（gitignore）
```

### 目录用途约束

| 目录 | 用途 | 清理策略 | gitignore |
|------|------|----------|-----------|
| `tests/` | 正式测试用例（test_*.py） | 随项目维护 | ❌ 版本控制 |
| `tests/tmp_*` | 临时测试脚本 | **用完即删** | ✅ `tmp_*.py` |
| `.tmp/` | Agent 临时工作文件 | **任务结束清理** | ✅ `.*/` |
| `.pytest-tmp-*/` | pytest 临时目录 | **测试结束自动清理** | ✅ `.*/` |
| `docs/` | 正式文档 | 随项目维护 | ❌ 版本控制 |
| `docs/todos.md` | 个人笔记 | 不入库 | ✅ |
| `scripts/` | 可复用脚本 | 随项目维护 | ❌ 版本控制 |
| `_dump_*.py` | 一次性调试脚本 | **用完即删** | ✅ `_dump_*.py` |
| `_debug_*.py` | 调试脚本 | **用完即删** | ✅ `_debug_*.py` |
| `logs/` | 运行日志 | **定期清理** | ✅ |
| `data/` | 知识库数据 | 按需重建 | ✅ |
| `snapshots/` | UI 截图快照 | **用完即删** | ✅ |
| `__history/` | Delphi 文件备份 | IDE 自动管理 | ✅ |
| `Win32/` `Win64/` | Delphi 编译输出 | **编译后清理** | ✅ |

### 命名规范

| 类型 | 命名模式 | 示例 |
|------|---------|------|
| 正式测试 | `test_*.py` | `test_compiler.py` |
| 临时测试 | `tmp_test_*.py` | `tmp_test_new_feature.py` |
| 调试脚本 | `_debug_*.py` / `_dump_*.py` | `_dump_ast.py` |
| 临时输出 | `tmp_*` / `test_*.png` | `tmp_output.txt` |

### 清理规则

```
任务完成后必须清理：
1. 临时文件 → 删除 tmp_*, _dump_*, _debug_*
2. 临时目录 → 删除 .tmp/, .pytest-tmp-*
3. 编译输出 → 删除 Win32/, Win64/, *.dcu, *.exe
4. 调试产物 → 删除 test_*.png, temp_*.json
```

### ⚠️ 禁止事项

- ❌ 在 `src/` 下创建临时文件或测试脚本
- ❌ 在项目根目录散放临时脚本（应用 `.tmp/` 或 `scripts/`）
- ❌ 临时文件使用无前缀命名（如 `test.py` 而非 `tmp_test.py`）
- ❌ 任务结束后保留 `.pytest-tmp-*` 目录
