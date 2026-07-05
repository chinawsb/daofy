# Delphi AST 语义分析引擎 — 知识库增强 + 代码审计规格书

> 版本：v1.0  
> 用途：Daofy MCP Server 配套 AST 解析器（daudit.exe）开发规格  
> 集成方式：Delphi 控制台程序 → subprocess JSON 管道 → Python KB 服务

---

## 目录

1. [架构概述](#1-架构概述)
2. [集成协议](#2-集成协议)
3. [知识库增强接口](#3-知识库增强接口)
4. [审计规则完整清单](#4-审计规则完整清单)
5. [数据库 Schema 扩展](#5-数据库-schema-扩展)
6. [Python 集成改动](#6-python-集成改动)
7. [实施路线图](#7-实施路线图)

---

## 1. 架构概述

```
┌──────────────────────────────────────────────────────────────────┐
│                     daudit.exe (Delphi Console)                    │
│                                                                   │
│  ┌──────────┐   ┌──────────────────┐   ┌───────────────────────┐  │
│  │  Lexer   │ → │   Parser (AST)    │ → │  Semantic Analysis   │  │
│  └──────────┘   └────────┬─────────┘   │ · Scope Resolution   │  │
│                          │             │ · Type Binding       │  │
│                          │             │ · Reference Tracking │  │
│                          │             │ · Audit Rule Engine  │  │
│                          │             └──────────┬────────────┘  │
│                          │                        │               │
│                          ▼                        ▼               │
│                    ┌────────────────────────────────────────┐      │
│                    │         JSON Output (stdout)           │      │
│                    │ · --mode audit 代码审计违规报告          │      │
│                    │ · --mode ast   AST 语法解析             │      │
│                    └──────────────────┬─────────────────────┘      │
└───────────────────────────────────────┼───────────────────────────┘
                                        │ stdout (JSON)
                                        ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Python MCP Server 侧                           │
│                                                                   │
│  smart_cache_knowledge_base.py  ← 消费 JSON, 写入 SQLite          │
│  tools/knowledge_base.py        ← 搜索接口, 向 AI 返回结果        │
│  tools/audit.py (新增)          ← 审计接口, 向 AI 返回违规报告    │
└──────────────────────────────────────────────────────────────────┘
```

### 核心分层

| 层 | 职责 | 技术载体 |
|----|------|---------|
| **AST 解析** | 将 Delphi 源码解析为语法树，覆盖 class/record/interface/function/property/field/const/enum 等全部语法结构 | daudit.exe `--mode ast` |
| **语义分析** | 作用域解析（实体归属）、类型绑定（类型名→定义）、引用追踪（谁用了谁）、继承链解析 | daudit.exe `--mode ast` |
| **审计引擎** | 在 AST + 语义分析结果上，运行预定义规则集，输出违规报告 | daudit.exe `--mode audit` |
| **AI 决策** | 消费审计报告，分类严重程度、排除误报、生成修复建议、输出最终报告 | MCP Server + LLM |

---

## 2. 集成协议

### 2.1 命令行接口

```bash
# ── 模式 1：AST 语法解析（实体提取） ──
daudit.exe --mode ast "C:\Dev\Unit1.pas" [--format json] [--compact]

# ── 模式 2：代码审计（返回违规列表） ──
# 全项目审计
daudit.exe --mode audit --source-dir "C:\Project\src" --output "audit_report.json" [--rules P0,P1]

# 指定规则
daudit.exe --mode audit --source-dir "C:\Project\src" --rules C001,C002,R001

# 增量审计（只审计 git 变更的文件）
daudit.exe --mode audit --git-diff HEAD~1 --source-dir "C:\Project\src"
```

### 2.2 STDIO 协议标准

```
stdin:   批处理模式时接收文件列表 JSON
stdout:  JSON（主输出通道，每行一个完整 JSON 或批处理整体 JSON）
stderr:  日志/诊断（不影响 MCP 通信管道）
exit:    0 = 全部成功, 1 = 部分文件失败, 2 = 严重错误
```

### 2.3 批处理输入格式

```json
{
  "files": [
    "C:\\Project\\src\\Unit1.pas",
    "C:\\Project\\src\\Unit2.pas",
    "C:\\Project\\src\\Unit3.pas"
  ],
  "options": {
    "threads": 4,
    "timeout_ms": 30000
  }
}
```

---

## 3. AST 语法解析输出格式（`--mode ast`）

### 3.1 输出 JSON Schema

```json
{
  "file": "System.Classes.pas",
  "status": "ok",
  "error_msg": null,

  "unit_name": "System.Classes",
  "file_hash": "md5_or_mtime_size",
  "parse_time_ms": 45,

  "file_stats": {
    "total_lines": 16789,
    "total_entities": 342
  },

  "uses": {
    "interface": ["System.SysUtils", "System.Types"],
    "implementation": ["System.Variants", "System.RTLConsts"]
  },

  "entities": [
    {
      "kind": "TC",
      "name": "TStringList",
      "name_lower": "tstringlist",
      "parent_scope": null,
      "visibility": "published",
      "modifiers": ["sealed"],

      "start_line": 1234,
      "end_line": 1456,
      "start_offset": 45000,
      "end_offset": 52000,
      "body_length": 7000,
      "code_block": "TStringList = class(TStrings)\n  ...\nend;",

      "definition": "class(TStrings)",
      "signature": "TStringList = class(TStrings)",

      "inherits_from": "TStrings",
      "inheritance_chain": ["TStringList", "TStrings", "TPersistent", "TObject"],

      "members": [
        {"kind": "FF", "name": "Add", "line": 1300},
        {"kind": "MF", "name": "FList", "line": 1280}
      ],
      "member_count": 42,

      "type_refs": [
        {"name": "TStrings", "resolved_kind": "TC"},
        {"name": "TList<string>", "base_type": "TList", "type_args": ["string"]}
      ]
    },
    {
      "kind": "FF",
      "name": "Add",
      "parent_scope": "TStringList",
      "start_line": 1300,
      "end_line": 1320,
      "code_block": "function TStringList.Add(const S: string): Integer;\nbegin\n  ...\nend;",
      "signature": "function Add(const S: string): Integer;",
      "return_type": "Integer",
      "params": [
        {"name": "S", "type": "string", "modifier": "const"}
      ],
      "modifiers": [],
      "visibility": "public",
      "calls": ["Grow", "InsertItem"]
    }
  ],

  "errors": [
    {"line": 567, "message": "Unresolved type: TSomeUndefinedType", "severity": "warning"}
  ]
}
```

### 3.2 实体 kind 编码表

| 编码 | 含义 | 关键附加字段 |
|------|------|-------------|
| `TC` | Class | inherits_from, inheritance_chain, members, visibility, modifiers |
| `TR` | Record | inherits_from (如果有), members |
| `TI` | Interface | inherits_from, guid |
| `TH` | Class/Record Helper | parent_scope = 目标类型 |
| `TE` | Enum | values[] |
| `TS` | Set | base_type |
| `TY` | Type Alias | definition, is_pointer, is_array |
| `AT` | Array Type | dimensions, element_type |
| `PT` | Pointer Type | pointed_type |
| `FF` | Function | signature, return_type, params[], calls[] |
| `FP` | Procedure | signature, params[] |
| `OP` | Operator Overload | signature, operator_symbol (Add/Implicit/Explicit/...), return_type |
| `CC` | Const | value |
| `CR` | ResourceString | value |
| `GV` | Global Variable | var_type, visibility |
| `MF` | Field | parent_scope, visibility |
| `MP` | Property | parent_scope, prop_type, read_spec, write_spec |
| `MM` | Method Pointer/Type | signature |
| `ME` | Event | parent_scope, event_type |
| `UI` | Unit (uses) | — |
| `KS` | String Literal | value |
| `DF` | DFM Property | prop_name, decoded_value |
| `AB` | Custom Attribute | attribute_name, params |

---

## 4. 审计规则完整清单（`--mode audit`）

### 4.1 规则总表

三条优先级：**P0 = 必须实现**，P1 = 高价值，P2 = 后续迭代。

每条规则包含：
- 检测机制：告诉 AST 引擎在语法树中找什么
- 输出格式：统一 `AuditViolation` JSON
- is_ai_needed：false = AST 直接出结论，true = 需要 AI 再判断

---

#### P0 规则（21 条，ROI 最高）

| ID | 类别 | 规则 | 检测方法 | is_ai_needed |
|----|------|------|---------|:-----------:|
| **C001** | 错误模式 | `with` 语句检测 | 找所有 `WithStatement` 节点 | false |
| **C002** | 错误模式 | 空 `except` 块 | `ExceptBlock` 内无语句 | false |
| **C003** | 错误模式 | `as` 前无 `is` 检查 | `AsExpression` 前 5 行无 `IsExpression` | false |
| **C004** | 错误模式 | `raise` 前无日志 | `ExceptBlock` 中只有 `raise;`，无日志调用 | false |
| **R001** | 资源泄露 | `Create`/`Free` 不配对 | 类作用域内统计 Create:N vs Free/FreeAndNil:N | false |
| **R002** | 资源泄露 | `TFileStream`/`THandle` 未释放 | 变量路径上无 `.Free`/`.Close` | false |
| **R003** | 资源泄露 | `TObjectList.OwnsObjects` 未设置 | `TObjectList.Create` 无参数或未赋值 | false |
| **R004** | 资源泄露 | `TStringBuilder`/`TEncoding` 未释放 | 临时创建的实例使用后无 `.Free` | false |
| **Q001** | 代码质量 | 方法超长 >80 行 | `end_line - start_line > 80` | false |
| **Q002** | 代码质量 | 圈复杂度 >3 | 递归统计 `if/for/while/case/try` 嵌套深度 | false |
| **Q003** | 代码质量 | 魔法数字 | 数值字面量过滤 `0/1/-1/True/False/已命名常量/类型边界` | false |
| **Q004** | 代码质量 | 方法参数 >5 个 | `MethodDeclaration.params.length > 5` | false |
| **Q005** | 代码质量 | 类方法 >50 个 | `ClassDeclaration.methods.length > 50` | false |
| **D001** | Delphi | 循环内字符串 `+` | 循环体内 `BinaryExpression(op='+', string)` | false |
| **D002** | Delphi | 循环内 `Create` | 循环体内 `CallExpression(.Create)` | false |
| **D003** | Delphi | 枚举 case 遗漏 | `CaseStatement` 分支数 < 枚举元素数 | true |
| **D004** | Delphi | override 缺 `inherited` | 方法 `modifiers:['override']` 体内无 `InheritedCall` | true |
| **S001** | 安全 | SQL 字符串拼接 | `SQL.Add`/`SQL.Text` + `+` 拼接表达式 | false |
| **S002** | 安全 | 函数返回值缺失 | 有多路 `if/else` 但部分路径无 `Result:=` 赋值 | false |
| **S003** | 安全 | 输出参数未标注 | 引用传递参数（非 string/record/interface）无 `var`/`out` | false |
| **U001** | 一致性 | uses 未引用 | uses 列表中的单元在 AST 符号引用中从未出现 | false |

#### P1 规则（15 条，需要基础语义分析）

| ID | 类别 | 规则 | 检测方法 | 依赖 |
|----|------|------|---------|------|
| **R005** | 资源 | try 未紧接获取 | 资源创建后下一句不是 `try` | AST 邻接检查 |
| **R006** | 资源 | 数据库连接未关闭 | `TSQLConnection`/`TADOConnection` 变量无 `.Close`/`.Free` | 类型绑定 |
| **C005** | 错误 | 事件未置 nil | `destructor` 中无 `OnXxx := nil` | 类属性表 + 析构体 |
| **C006** | 错误 | 匿名方法循环捕获 | 循环内 `AnonymousMethod` 引用循环变量 | 作用域分析 |
| **C007** | 错误 | 线程访问 VCL | `TThread.Execute` 调用链中有 VCL 控件访问 | 调用图 + 类型绑定 |
| **D005** | Delphi | class helper 冲突 | 同目标类型多 helper 定义同名方法 | 跨文件注册表 |
| **D006** | Delphi | published 非流式 | `published` 段含泛型/非流式类型 | 类型绑定 |
| **D007** | Delphi | AnsiString/WideString | 所有 AnsiString/WideString 声明 | 类型绑定 |
| **D008** | Delphi | Variant 使用 | 所有 Variant 声明和赋值 | 类型绑定 |
| **Q006** | 质量 | IntToStr 低效 | 循环字符串拼接中出现 `IntToStr` | 调用追踪 |
| **Q007** | 质量 | 循环内重复 `as` | 循环体内相同类型的 `AsExpression` | 表达式匹配 |
| **S004** | 安全 | 硬编码凭据 | string literal 含 `password`/`secret`/`api.key` 模式 | 字符串分析 |
| **S005** | 安全 | 用户字符串硬编码 | `ShowMessage`/`MessageDlg` 参数为 literal | 函数调用分析 |
| **P001** | 性能 | 循环内重复 `as` | 同 Q007，标记严重级别更高 | 表达式匹配 |
| **P002** | 性能 | RTTI 高频调用 | 方法内多次 `GetType`/`GetDeclaredMethods` 等 RTTI 调用（每次创建接口包装有开销） | 调用计数 |

#### P2 规则（9 条，后续迭代）

| ID | 类别 | 规则 | 说明 |
|----|------|------|------|
| **R007** | 资源 | 接口循环引用 | 类型引用图中 A→B→A，AST 标出可疑 |
| **R008** | 资源 | TComponent 重复 Free | Owner/Parent 链上的重复释放 |
| **C008** | 错误 | 空 `finally` 块 | finally 内无操作 |
| **D009** | Delphi | init/finalization 泄漏 | 段中有 Create 无 Free |
| **D010** | Delphi | 类型硬转换 `Type(x)` | 找所有 HardCast |
| **Q008** | 质量 | 代码克隆 | AST 子树相似度匹配 |
| **Q009** | 质量 | 命名规范 | 可配置的命名约定检查 |
| **S006** | 安全 | 缓冲区溢出 | Move/CopyMemory 目标大小检查 |
| **A001** | 综合 | 影响范围分析 | 改一个实体标记所有影响文件 |

### 4.2 审计违规 JSON 格式

```json
{
  "audit_summary": {
    "source_dir": "C:\\Project\\src",
    "total_files": 25,
    "total_lines": 48900,
    "total_violations": 42,
    "by_severity": {"critical": 3, "warning": 15, "suggestion": 24},
    "by_rule": {"C001": 5, "R001": 3, "Q003": 12, ...},
    "scan_time_ms": 28500
  },

  "violations": [
    {
      "rule_id": "C001",
      "rule_name": "with 语句",
      "severity": "suggestion",
      "category": "常见错误模式",
      "file": "Unit1.pas",
      "line": 42,
      "column": 3,
      "code_snippet": "with StringList do",
      "message": "使用 with 语句可能导致命名冲突和可读性下降",
      "is_ai_needed": false,
      "fix_example": "for I := 0 to StringList.Count - 1 do\n  StringList[I] := ...;"
    },
    {
      "rule_id": "R001",
      "rule_name": "Create/Free 不配对",
      "severity": "critical",
      "category": "资源泄露",
      "file": "Unit2.pas",
      "line": 85,
      "code_snippet": "FBitmap := TBitmap.Create;",
      "context_code": "...\nconstructor TMyClass.Create;\nbegin\n  FBitmap := TBitmap.Create;\nend;\n\ndestructor TMyClass.Destroy;\nbegin\n  // FBitmap.Free;  ← 缺失\n  inherited;\nend;",
      "message": "TMyClass 中 TBitmap.Create 在构造中创建，但析构中无对应 Free",
      "is_ai_needed": false,
      "fix_example": "destructor TMyClass.Destroy;\nbegin\n  FBitmap.Free;\n  inherited;\nend;"
    },
    {
      "rule_id": "D003",
      "rule_name": "枚举 case 遗漏",
      "severity": "warning",
      "category": "Delphi 特有",
      "file": "Unit3.pas",
      "line": 200,
      "code_snippet": "case Color of\n  Red: ...;\n  Green: ...;\nend;",
      "message": "枚举 TColor 有 4 个值，case 只覆盖了 2 个，遗漏: Blue, Yellow",
      "is_ai_needed": true,
      "extra_data": {
        "enum_name": "TColor",
        "enum_values": ["Red", "Green", "Blue", "Yellow"],
        "covered_values": ["Red", "Green"],
        "missing_values": ["Blue", "Yellow"]
      },
      "fix_example": "case Color of\n  Red: ...;\n  Green: ...;\n  Blue: ...;\n  Yellow: ...;\nelse\n  raise Exception.Create('未知颜色');\nend;"
    }
  ],

  "context_data": {
    "inheritance_trees": [
      {"class": "TMyForm", "ancestors": ["TMyForm", "TForm", "TCustomForm", "TWinControl", "TControl", "TComponent", "TPersistent", "TObject"]}
    ],
    "dependency_graph": {
      "nodes": [...],
      "edges": [...]
    }
  }
}
```

### 4.3 严重级别定义

| 级别 | 含义 | AI 处理方式 |
|------|------|-----------|
| `critical` | 必然导致资源泄漏/崩溃/安全漏洞 | 必须修复，AI 直接出修复方案 |
| `warning` | 大概率是问题 | AI 验证后出修复方案 |
| `suggestion` | 风格/质量建议 | AI 判断是否采用，纳入报告"建议"段 |

---

## 5. 数据库 Schema 扩展

### 5.1 vocabularies 表新增列

```sql
-- 知识库已有表 vocabularies，新增 AST 增强字段
ALTER TABLE vocabularies ADD COLUMN end_line INTEGER;
ALTER TABLE vocabularies ADD COLUMN end_offset INTEGER;
ALTER TABLE vocabularies ADD COLUMN body_length INTEGER;
ALTER TABLE vocabularies ADD COLUMN code_block TEXT;
ALTER TABLE vocabularies ADD COLUMN signature TEXT;
ALTER TABLE vocabularies ADD COLUMN modifiers TEXT;         -- JSON: ["virtual", "override"]
ALTER TABLE vocabularies ADD COLUMN visibility TEXT;        -- "private"|"protected"|"public"|"published"
ALTER TABLE vocabularies ADD COLUMN type_refs TEXT;         -- JSON: [{"name":"TList","resolved_kind":"TC"}]
ALTER TABLE vocabularies ADD COLUMN member_count INTEGER;
ALTER TABLE vocabularies ADD COLUMN inheritance_chain TEXT; -- JSON: ["TStringList","TStrings","TPersistent","TObject"]
ALTER TABLE vocabularies ADD COLUMN generics TEXT;          -- JSON: {"T":"class,constructor"}
ALTER TABLE vocabularies ADD COLUMN values TEXT;            -- 枚举值/常量值 JSON
ALTER TABLE vocabularies ADD COLUMN params TEXT;            -- 函数参数 JSON
ALTER TABLE vocabularies ADD COLUMN return_type TEXT;       -- 函数返回类型
ALTER TABLE vocabularies ADD COLUMN calls TEXT;             -- 函数调用列表 JSON
ALTER TABLE vocabularies ADD COLUMN ref_count INTEGER;      -- 被引用次数（由语义分析填充）
ALTER TABLE vocabularies ADD COLUMN source TEXT;            -- "ast" | "regex" (标识数据来源)
```

### 5.2 新增 entity_refs 表（引用图谱）

```sql
CREATE TABLE IF NOT EXISTS entity_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,          -- vocabularies.id（引用者）
    target_name TEXT NOT NULL,            -- 被引用的实体名
    target_kind TEXT,                     -- 被引用的实体 kind (TC/FF/...)
    target_file_id INTEGER,              -- 被引用的目标所在文件
    ref_type TEXT NOT NULL,               -- 'type_ref' | 'call' | 'inherits' | 'uses' | 'access'
    line INTEGER,                         -- 引用发生的行号
    code_snippet TEXT,                    -- 引用处的代码片段（简短）
    FOREIGN KEY (source_id) REFERENCES vocabularies(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_entity_refs_source ON entity_refs(source_id);
CREATE INDEX IF NOT EXISTS idx_entity_refs_target ON entity_refs(target_name, target_kind);
CREATE INDEX IF NOT EXISTS idx_entity_refs_target_file ON entity_refs(target_file_id);
```

### 5.3 新增 audit_results 表（审计结果缓存）

```sql
CREATE TABLE IF NOT EXISTS audit_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path TEXT NOT NULL,
    file_path TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,               -- 'critical' | 'warning' | 'suggestion'
    line INTEGER,
    code_snippet TEXT,
    message TEXT,
    is_ai_confirmed INTEGER DEFAULT 0,   -- 0=AST自动, 1=AI已确认, 2=已修复已验证
    fix_suggestion TEXT,
    scan_timestamp REAL,
    created_at REAL DEFAULT (julianday('now')),
    UNIQUE(project_path, file_path, rule_id, line)
);

CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_results(project_path);
CREATE INDEX IF NOT EXISTS idx_audit_severity ON audit_results(severity);
CREATE INDEX IF NOT EXISTS idx_audit_rule ON audit_results(rule_id);
```

---

## 6. Python 集成改动

### 6.1 知识库解析函数替换

文件：`src/services/knowledge_base/smart_cache_knowledge_base.py`

```python
@staticmethod
def _parse_delphi_file_static(file_path_str: str) -> Tuple[str, List[Dict], int, List[str]]:
    """解析 Delphi 文件：优先 AST 引擎，失败则 fallback 正则"""
    
    ast_result = _call_daudit_kb(file_path_str)
    
    if ast_result and ast_result["status"] == "ok":
        items = []
        for ent in ast_result["entities"]:
            item = {
                'type': ent['kind'],
                'name': ent['name'],
                'line': ent['start_line'],
                'base_class': ent.get('inherits_from'),
                'description': ent.get('definition', ''),
                # AST 增强字段
                'end_line': ent.get('end_line'),
                'code_block': ent.get('code_block', ''),
                'signature': ent.get('signature', ''),
                'modifiers': json.dumps(ent.get('modifiers', []), ensure_ascii=False),
                'visibility': ent.get('visibility', 'published'),
                'type_refs': json.dumps(ent.get('type_refs', []), ensure_ascii=False),
                'inheritance_chain': json.dumps(ent.get('inheritance_chain', []), ensure_ascii=False),
                'params': json.dumps(ent.get('params', []), ensure_ascii=False),
                'return_type': ent.get('return_type', ''),
                'calls': json.dumps(ent.get('calls', []), ensure_ascii=False),
                'source': 'ast',
            }
            items.append(item)
        
        uses = ast_result.get('uses', {})
        uses_list = uses.get('interface', []) + uses.get('implementation', [])
        total_lines = ast_result.get('file_stats', {}).get('total_lines', 0)
        
        return (file_path_str, items, total_lines, uses_list)
    
    # fallback: 当前正则逻辑
    return _regex_fallback(file_path_str)


def _call_daudit_kb(file_path: str) -> Optional[Dict]:
    """调用 daudit.exe --mode kb 单文件模式"""
    ```python
    import subprocess, json
    
    daudit_path = _find_daudit()
    if not daudit_path:
        return None
    
    try:
        result = subprocess.run(
            [daudit_path, "--mode", "kb", "--input", file_path, "--format", "json"],
            capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
        logger.warning("AST 解析失败 %s: %s", file_path, e)
    
    return None


def _find_daudit() -> Optional[str]:
    """查找 daudit.exe 路径"""
    candidates = [
        Path(__file__).parent.parent.parent.parent / "tools" / "daudit" / "daudit.exe",
        Path.cwd() / "tools" / "daudit" / "daudit.exe",
    ]
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    return None
```

### 6.2 新增审计 MCP 工具

文件：`src/tools/audit.py`（新增）

```python
"""
审计 MCP 工具

提供 daudit --mode=audit 的 AI Agent 调用接口。
"""

import json
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from mcp.types import CallToolResult, TextContent

logger = logging.getLogger(__name__)


def _find_daudit() -> Optional[str]:
    """查找 daudit.exe"""
    candidates = [
        Path(__file__).parent.parent.parent / "tools" / "daudit" / "daudit.exe",
        Path.cwd() / "tools" / "daudit" / "daudit.exe",
    ]
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    return None


def _call_audit(source_dir: str, rules: Optional[str] = None) -> Optional[Dict]:
    """调用 daudit.exe --mode=audit"""
    daudit = _find_daudit()
    if not daudit:
        return None
    
    cmd = [daudit, "--mode=audit", "--source-dir", source_dir]
    if rules:
        cmd.extend(["--rules", rules])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=300,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode in (0, 1) and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
        logger.error("审计失败: %s", e)
    
    return None


async def run_audit(arguments: Dict[str, Any]) -> CallToolResult:
    """
    执行代码审计
    
    参数:
    - source_dir: 源码目录（必需）
    - rules: 规则集，如 "P0" / "P0,P1" / "C001,R001"（可选，默认 P0）
    - severity: 最低严重级别 "suggestion" | "warning" | "critical"（可选，默认 suggestion）
    - output_format: "report" | "json"（可选，默认 report）
    """
    source_dir = arguments.get("source_dir", "")
    rules = arguments.get("rules", "P0")
    severity = arguments.get("severity", "suggestion")
    output_format = arguments.get("output_format", "report")
    
    if not source_dir:
        return CallToolResult(
            content=[TextContent(text="必须提供 source_dir 参数")],
            isError=True,
        )
    
    # 调用 AST 引擎
    result = _call_audit(source_dir, rules)
    if not result:
        return CallToolResult(
            content=[TextContent(text="审计执行失败，请检查 daudit.exe 是否可用")],
            isError=True,
        )
    
    if output_format == "json":
        return CallToolResult(content=[TextContent(text=json.dumps(result, indent=2, ensure_ascii=False))])
    
    # 格式化为可读报告
    return CallToolResult(content=[TextContent(text=_format_audit_report(result, severity))])


def _format_audit_report(result: Dict, min_severity: str) -> str:
    """将审计结果格式化为 Markdown 报告"""
    summary = result.get("audit_summary", {})
    violations = result.get("violations", [])
    
    severity_level = {"suggestion": 0, "warning": 1, "critical": 2}
    min_level = severity_level.get(min_severity, 0)
    
    report = []
    report.append("# 代码审计报告")
    report.append("")
    report.append(f"**扫描目录**: {summary.get('source_dir', 'N/A')}")
    report.append(f"**文件数**: {summary.get('total_files', 0)}")
    report.append(f"**违规总数**: {summary.get('total_violations', 0)}")
    report.append(f"**扫描耗时**: {summary.get('scan_time_ms', 0)}ms")
    report.append("")
    
    # 按严重级别分组
    groups = {"critical": [], "warning": [], "suggestion": []}
    for v in violations:
        lv = severity_level.get(v.get("severity", "suggestion"), 0)
        if lv >= min_level:
            groups[v.get("severity", "suggestion")].append(v)
    
    for severity_label in ["critical", "warning", "suggestion"]:
        items = groups[severity_label]
        if not items:
            continue
        label_map = {"critical": "🔴 严重", "warning": "🟡 一般", "suggestion": "🔵 建议"}
        report.append(f"## {label_map[severity_label]} ({len(items)} 条)")
        report.append("")
        
        for v in items:
            report.append(f"### [{v['rule_id']}] {v['rule_name']}")
            report.append(f"- **文件**: {v['file']}:{v['line']}")
            report.append(f"- **说明**: {v['message']}")
            if v.get('code_snippet'):
                report.append(f"- **代码**:")
                report.append(f"  ```pascal")
                report.append(f"  {v['code_snippet']}")
                report.append(f"  ```")
            if not v.get('is_ai_needed', True):
                report.append(f"- **修复示例**:")
                report.append(f"  ```pascal")
                report.append(f"  {v.get('fix_example', '')}")
                report.append(f"  ```")
            report.append("")
    
    return "\n".join(report)
```

### 6.3 Server 注册

文件：`src/server.py`（追加）

```python
from src.tools.audit import run_audit

# 在 list_tools() 中以 project 工具注册（2026.05 合并）:
tools.append(Tool(
    name="project",
    description="项目全生命周期管理: 编译/配置/审计",
    inputSchema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["compile", "audit", "ast", "runtime", ...]},
            "project_path": {"type": "string", "description": "项目文件路径"},
        },
        "additionalProperties": True,
        "required": ["action"],
    },
))

# 在 call_tool() 中分发:
# delphi_project(action="audit", ...) 路由到 run_audit(arguments)
```

> **注意**: 2026.05 重构后，`run_audit`、`compile_project`、`dproj_tool` 已合并为 `project` 工具，
> 通过 action 参数切换功能。详见 `tool_help("project")`。

---

## 7. 实施路线图

### Phase 0 — 基础能力（1-2 周）

目标：AST 引擎能跑通，替换当前正则解析

```
[ ] Lexer + Parser 基础骨架
[ ] 支持 class/record/interface/function/procedure/const/enum 解析
[ ] --mode ast 单文件/批量模式
[ ] --mode audit 审计模式
[ ] Python 集成：_parse_delphi_file_static 双通道（AST + fallback）
[ ] 6 条 P0 审计规则：C001, C002, Q003, Q001, R001, D004
```

### Phase 1 — 作用域 + 语义（2-3 周）

目标：实体归属、继承链、基础类型绑定

```
[ ] 作用域解析：每个实体知道自己的 parent_scope
[ ] 继承链解析：class → 所有祖先类
[ ] 基础类型绑定：TMyVar: TStringList → type_ref
[ ] --mode=audit 全项目模式
[ ] 全部 21 条 P0 规则实现
```

### Phase 2 — 完整审计（2-3 周）

目标：审计引擎可以投入生产使用

```
[ ] 15 条 P1 规则实现
[ ] 跨文件类型注册表（class helper 冲突、枚举引用）
[ ] 引用图（entity_refs 表）
[ ] AI Agent 审计报告格式化（run_audit MCP 工具）
[ ] 增量审计（git diff 模式）
```

### Phase 3 — 图谱 + 高级（持续迭代）

```
[ ] 9 条 P2 规则实现
[ ] 代码克隆检测
[ ] 影响范围分析
[ ] 审计结果历史追踪（audit_results 表比对）
```

---

## 附录：`CODING_RULES.mdc` 审核表映射

下面是从 CODING_RULES.mdc 审计清单到 AST 规则 ID 的完整映射，用于追踪覆盖情况：

| CODING_RULES 检查项 | AST 规则 ID | 覆盖率 |
|--------------------|------------|--------|
| 命名规范 | Q009 (P2) | 部分覆盖 |
| 异常模式 | — (AI 独占) | 0% |
| OleVariant vs Variant | D008 (P1) | 100% |
| 平台兼容 | — | 0%（无法自动化） |
| 事件释放（多线程） | C005 (P1) | 部分覆盖 |
| 所有路径 | S002 (P0) | 部分覆盖（函数返回值） |
| 边界条件 | — (AI 独占) | 0% |
| 输入验证 | — (AI 独占) | 0% |
| **资源释放路径** | **R001-R004 (P0)** | **100%** |
| **并发安全** | **C007 (P1)** | **部分覆盖（线程→VCL）** |
| **函数返回值** | **S002 (P0)** | **100%** |
| const/out/in 参数 | S003 (P0) | 100% |
| 初始化/终结段 | D009 (P2) | 部分覆盖 |
| **Create/Free 配对** | **R001 (P0)** | **100%** |
| try/finally | R005 (P1) | 100% |
| 文件/句柄 | R002 (P0) | 100% |
| 数据库连接 | R006 (P1) | 100% |
| GDI/系统资源 | R002 (P0) | 100% |
| 接口引用 | R007 (P2) | 部分覆盖 |
| **TObjectList.OwnsObjects** | **R003 (P0)** | **100%** |
| **字符串拼接** | **D001 (P0)** | **100%** |
| published 区 | D006 (P1) | 100% |
| **RTTI** | **P002 (P1)** | **部分覆盖（高频调用检测）** |
| **枚举 case** | **D003 (P0)** | **100%** |
| Class Helper 冲突 | D005 (P1) | 100% |
| **空 except** | **C002 (P0)** | **100%** |
| **类型转换安全** | **C003 (P0)** | **100%** |
| 事件释放 | C005 (P1) | 100% |
| **匿名方法捕获** | **C006 (P1)** | **100%** |
| **线程访问 VCL** | **C007 (P1)** | **100%** |
| **with 语句** | **C001 (P0)** | **100%** |
| **函数/方法规模** | **Q001 (P0)** | **100%** |
| **圈复杂度** | **Q002 (P0)** | **100%** |
| **魔法数字** | **Q003 (P0)** | **100%** |
| 代码重复 | Q008 (P2) | 100% |
| **SQL 注入** | **S001 (P0)** | **100%** |
| 硬编码凭据 | S004 (P1) | 100% |
| 国际化 | S005 (P1) | 部分覆盖 |
| **循环内内存分配** | **D002 (P0)** | **100%** |
| **字符串操作** | **D001 (P0)** | **100%** |

**粗体** = 高优先级（P0/P1），总计约 35 项可自动化，覆盖 CODING_RULES 约 70% 的检查项。

---

> 本文档是 Ast 引擎开发的技术规格。  
> 后续开发应从这里开始：**Phase 0 的 AST 解析器核心 + 6 条 P0 规则先行验证**。
