# Delphi 编码规范
> 最后更新: 2026-06-24 | 版本: 1.13.0

## 工作流总览
```
环境检查 → 查KB确认API → 写代码(自动备份) → 格式化 → 编译验证 → 代码审核 → 清理
  ①          ②               ③               ④         ⑤          ⑥        ⑦
                                                                     ↓ 可选
                                                    ┌────────────────────────────┐
                                                    │  ⑧ 自动化UI交互测试        │
                                                    │  ⑨ 控制台程序交互验证       │
                                                    └────────────────────────────┘

    调用工具      →  (MCP 工具名)
  ① 环境检查     →  check_environment / get_coding_rules
  ② 查KB确认API  →  delphi_kb / delphi_file
  ③ 写代码       →  delphi_file(action="write")
  ④ 格式化       →  delphi_file(action="format")
  ⑤ 编译验证     →  project(action="compile")
   ⑥ 代码审核     →  get_coding_rules(section="review")
   ⑦ 清理         →  delphi_file
   ⑧ 自动化UI测试 →  automate_delphi
   ⑨ 控制台测试   →  subprocess (Python 侧)
  🔧 辅助参考:
     人机协同     →  get_coding_rules(section="human_collab")   (§⑩ 卡点时申请介入)
     经验库       →  get_coding_rules(section="experience")     (§⑪ 沉淀解决方法)
```

---

<!-- 自动化测试架构内容已迁移到 src/resources/automation/architecture.md -->
<!-- 详细技术参考：MCP Resource delphi://automation/index（入口），delphi://automation/architecture（架构方法论） -->

## ⚙ 自动化测试架构

自动化测试的完整方法论（RTTI/OCR 决策矩阵、感知-规划-执行-反馈循环、代码感知测试、提示词模板、经验闭环、断言系统等）已迁移到独立目录：

```
resources/automation/
├── index.md              ← 总入口（@when: 自动化测试时）
├── architecture.md       ← 架构方法论（原 coding-rules.md §§A-J）
├── reference/            ← 框架参考（脚本格式/协议/修复循环）
└── scenarios/            ← 场景模板（A-O，含可复用 JSON）
```

**入口**: `get_coding_rules(section="automation")` → 自动读取 `resources/automation/index.md`
**架构方法**: `resources/automation/architecture.md`
**命令参考**: `delphi://automation/script-schema`（MCP Resource）
**场景模板**: `resources/automation/scenarios/`（A-O 文件）


<!-- 以下 §§A-J 自动化架构详细内容已迁移到 resources/automation/architecture.md -->
<!-- 此处不再重复 -->

## ① 环境检查
```python
check_environment(action="check")       # 确认编译器状态
get_coding_rules()                       # 获取工作流总览 + 章节索引（默认）
get_coding_rules(section="writing")      # 编码前：拉取编码规范
get_coding_rules(section="review")       # 编译后：拉取审核表
get_coding_rules(section="list")         # 列出所有可用章节名
```

---

## ② KB 搜索（编码前必做）
**写任何引用的代码前，先查 KB 确认 API 定义，禁止凭空编造。**

### 搜索优先级
| 优先级 | 方式 | 适用 |
|--------|------|------|
| ⭐1 | `delphi_kb(query="TStringList")` 精确类名 | 已知类名 |
| ⭐2 | 换名 `TMainForm`→`TfrmMain` 再试 | 第一个无结果 |
| ⭐3 | `search_type="function"` 搜函数（FF+FP） | 查函数 |
| ⭐4 | `search_type="reference"` 查引用 | 评估修改影响 |
| ⭐5 | `search_type="semantic"` 中文兜底 | 精确搜不到 |

> `search_type="function"` 同时匹配函数(FF)和过程(FP)。`search_type="procedure"` 只查过程。

### 知识库范围
| 参数 | 目标 | project_path |
|------|------|-------------|
| `kb_type="delphi"` | VCL/FMX/RTL 官方 | 不需要 |
| `kb_type="project"` | 项目自有代码 | **必须传**（或自动检测CWD .dproj） |
| `kb_type="thirdparty"` | 三方组件 | 不需要 |
| `kb_type="document"` | Delphi 帮助文档（ZVec 全文索引） | 不需要 |
| 默认（不传） | 全部三库 | — |

### 项目路径自动检测
```python
# 不传 project_path 时自动扫描 CWD 及父目录下的 .dproj
# 找到唯一 .dproj 时自动使用；多个同名时匹配目录名
delphi_kb(query="TfrmMain", kb_type="project")  # 依赖自动检测
delphi_kb(query="TfrmMain", kb_type="project", project_path="C:/MyProject/Project.dproj")  # 显式指定
```

### 读源码
```python
delphi_file(action="read", search_type="class", type_name="TButton")              # Delphi 官方源码
delphi_file(action="read", search_type="function", function_name="Create")         # Delphi 官方
delphi_file(action="read", search_type="class", type_name="TfrmMain", search_in="project", project_path="...")  # 项目源码
delphi_file(action="read", file_path="...", start_line=100, limit=200)             # 按路径读
```

### KB 搜不到的排查
```
搜不到类/函数 → 检查 kb_type 是否正确（项目代码用 project）
             → 尝试部分匹配（仅类名不含命名空间）
             → 检查三方库是否已安装/构建
             → 直接按文件路径搜索 System.SysUtils → 搜文件名
```

---

## ③ 写 Delphi 代码

> **卡点入口**：写代码过程中遇到错误、方案不确定、反复试同一方案、或信息不足需要猜测时 → 先查 **§⑩ 前置自检**，按触发条件评估是否申请人工介入。

### 文件编码检查（修改前必做）
- **修改任何 Delphi 源文件前，必须先确认文件编码，避免中文乱码。**
- ⭐ 优先使用 `delphi_file(action="read", file_path=...)` 读取文件（自动检测编码、支持 BOM/UTF-16/GBK，无需手动处理）
- `delphi_file` 不可用时（如直接在 bash/python 脚本中操作文件），降级到手动检测：
  ```python
  # 手动编码检测（仅作为 delphi_file 不可用时的降级方案）
  try:
      raw.decode('utf-8')
      encoding = 'utf-8'
  except UnicodeDecodeError:
      encoding = 'gbk'  # 中文 Windows 上常见
  ```
- **写回时必须保持原始编码**，不可将 GBK 文件强行以 UTF-8 写出
- 使用 `delphi_file(action="write")` 默认自动备份并保持原始编码；`delphi_file(action="format")` 默认自动备份
- 如果文件含 BOM（UTF-8 BOM / UTF-16 LE/BE），保留 BOM 不删除
- **新建 Delphi 文件统一使用 `utf-8-sig`（UTF-8 with BOM）**：Delphi 编译器将无 BOM 文件中的中文字符串视为 `AnsiString`，触发 `W1057 Implicit string cast from 'AnsiString' to 'string'` 警告。使用 `encoding="utf-8-sig"` 写入 BOM 后，编译器正确识别为 `UnicodeString`，消除该警告。统一使用也避免了"是否含中文"的判断歧义。

### 自动备份
- `delphi_file(action="write", backup=True)` **默认开启自动备份**，写入前自动在 `__history` 目录创建备份，无需手动调用
- 备份文件命名: `文件名.~版本号~`（与 Delphi IDE 兼容）
- 二进制 DFM 文件的备份是原始二进制版本，恢复时 100% 还原
- ❌ 禁止直接使用原生 edit/write 工具修改 .pas/.dfm 文件而不通过 delphi_file 进行备份
- ❌ 禁止用 `apply_patch`、shell 重定向、PowerShell/Python 直接写入、IDE 默认编辑器修改 `.pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx`
- ✅ Delphi 文件必须通过 `delphi_file` 或 Daofy 内部已登记的 Delphi 工具写入；Daofy edit guard 会在文件监听启用时记录绕过 Daofy 的外部写入告警
- 手动备份/恢复/列表:
  ```python
  delphi_file(action="backup", file_path="src/Unit1.pas")                           # 手动创建备份
  delphi_file(action="backup", backup_action="list", file_path="src/Unit1.pas")     # 列出备份版本
  delphi_file(action="backup", backup_action="restore", file_path="src/Unit1.pas", version=3)  # 恢复
  ```

### 命名
- **类型**：`T`类 `I`接口 `E`异常 `P`指针
- **字段**：`F`前缀 `FName: string;`
- **属性**：大驼峰 `property Name: string read FName;`
- **方法**：大驼峰 `procedure CalculateTotal;`
- **事件**：`OnCreate`→`Form1Create`；`Before`/`After` 保留
- **参数**：未以 A 开头加 A `procedure SetName(AName: string);`
- **枚举**：值前缀取自枚举类型名去掉 T 的缩写，例如 `TAlignment → taLeft, taRight, taCenter`
- **常量**：全大写 `MAX_BUFFER_SIZE`；作用域常量同规则

### 格式
- 缩进 2 空格，行宽 ≤120
- 赋值/运算符前后加空格，逗号后加，括号内侧不加
- `begin` 独占一行；泛型嵌套 `>>` 在现代 Delphi 中无需额外空格
- `uses` 子句默认合并为单行（`format_delphi` 的 `uses_style="compact"`），
  如需 pasfmt 默认展开风格传 `uses_style="pasfmt_default"`
```delphi
uses System.SysUtils, System.Classes,  // 系统
     Vcl.Forms, Vcl.Controls,          // VCL/FMX
     madBasic, madDisAsm,              // 第三方
     MyUnit1, MyUnit2;                 // 项目
```

### 泛型
- 泛型参数使用描述性名称 `TKey, TValue`，而非单字母 `T`
- 多约束泛型的 `where` 子句每条约束独占一行以提高可读性
- 避免深层嵌套泛型，超过 2 层时用 type alias 简化：`type TStringArrayList = TArray<TList<string>>`
- 泛型方法重载时确保签名歧义能被编译器正确分辨

### 运算符重载
- 仅对值类型（record）定义运算符重载，类类型（class）避免
- 运算符语义须符合直觉，不得改变常规含义（如 `+` 不能表示减法）
- 定义类型转换运算符（`Implicit`/`Explicit`）时，同时提供命名转换方法供显式调用

### 异步与多线程
- 后台线程操作 UI 控件必须通过主线程同步机制完成
- 共享资源访问须加锁保护，锁粒度尽量小，避免死锁
- 异步任务的生命周期须明确管理，任务取消或失败时确保已分配资源得到清理
- 避免在异步回调中直接引用对象，使用接口引用或弱引用模式防止悬空

### 代码组织
- 每个单元职责单一，避免"万能单元"；一个单元的代码量建议不超过 500 行
- `interface` 区按 `uses` → 类型声明 → 常量 → 变量 → 过程/函数声明 顺序排列
- `implementation` 区按 `uses` → 辅助过程/函数 → 接口方法实现 顺序排列
- `uses` 子句分组排列，组间空行分隔，组内字母序，每组末尾标注分组名（如上示例）

### 版本兼容
- 跨版本差异使用条件编译包裹，并注释所针对的版本号：`{$IFDEF VER370} // Delphi 13`
- 目标版本范围应在项目文件或配置文件中统一声明，而非散落在代码中
- 使用新版 API 时提供旧版本回退实现，避免强制升级编译器

### delphi_file 写入规则

**`delphi_file` 的所有行号参数和输出均为 1-indexed 左闭右闭区间。**

| 参数 | 说明 |
|------|------|
| `start_line=1` | 从文件第 1 行开始（第 1 行 = 1） |
| `start_line=5, end_line=10` | 替换第 5~10 行（1-indexed `[5, 10]`） |
| `start_line=4, end_line=4` | 只替换第 4 行（1-indexed `[4, 4]`） |

**write 统一使用 edits 参数：**
```python
# 创建新文件（文件不存在时自动创建）
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 1, "content": "unit Unit1;\n\ninterface\n\nimplementation\n\nend.\n"}])

# 全量替换已有文件
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 1, "content": "unit ..."}])

# 部分替换（替换第 5~10 行）
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 5, "end_line": 10, "content": "新内容"}])

# 多段替换（顺序不限，内部自动排序）
delphi_file(action="write", file_path="Unit1.pas", edits=[
    {"start_line": 10, "end_line": 12, "content": "..."},
    {"start_line": 5, "end_line": 7, "content": "..."},
])

# 预览模式（不写盘，不清除脏标记）
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 5, "end_line": 10, "content": "新内容"}], preview=True)
```

### 连续编辑与脏标记保护（v2026.06.12+）

**write / format / uses 操作后文件被标记为脏**，直接再次 write 会收到错误提示：

```
请先调用 read 获取最新行号，或使用 preview=true 预览本次修改。
```

**继续写入的方式：**
- 调用 `read`（自动清除脏标记）
- 在每个 edit 中提供非空 `old_content`（写入前校验当前命中范围）
- 调用 `write(preview=True)` 仅预览 diff；preview 不清除脏标记
- 调用 `write(allow_dirty=True)`（风险自负，仅在确保行号准确时使用）

**连续编辑的行号偏移算法：**

每次 `write` 会返回偏移量信息：
```
wrote: Unit1.pas, 1-indexed [5, 10] → [5, 13] (offset: +3) (指定 6), encoding: utf-8
```
- `[5, 10] → [5, 13] (offset: +3)`：**实际行号区间** → 写入后行号，偏移量显式给出 `+3`
- 如果指定行号与实际行号不同，末尾标注 `(指定 N)` 以提示 AI 行号调整情况
- 如果开启了 `auto_format=True`，返回的 offset **已包含格式化造成的行数变化**（如 uses 展开、空行调整等），无需额外叠加
- 当此前编辑产生了累积偏移时，会在 diff 底部追加 `ℹ 偏移: 此前 +N 行偏移, 实际行号=指定行号+N` 提示

Agent 根据以下规则计算后续行号：

```
设某次 write 返回的编辑后行号范围为 [s, e_new]
则后续用原行号 L 计算新行号:
  L < s     → 新行号 = L         (在编辑区域前，不变)
  L ≥ e_old → 新行号 = L + offset  (在编辑区域后，累加偏移)
  s ≤ L < e_old → 该行已被替换/删除，不能再用作后续编辑目标
```

有多次 write 时，脏标记会阻止第二次 write，必须先 read 确认行号。
不同文件可并行写。

**两大致命错误（绝不能犯）：**
1. ❌ 写操作传 `start_line=5` 以为是第 5 行开始 → 正确（1-indexed），但不要混淆为 0-indexed
2. ❌ 脏标记阻止后强行继续 → 行号已过时，必须 read、preview 或设 allow_dirty=true（仅确保行号准确时使用）

**注意：`uses` action 也会标记脏和偏移行号。**
`delphi_file(action="uses", ...)` 返回的偏移量格式与 write 一致。

**推荐做法：**
- 一处修改 → `read` → `write(edits=[...])` 
- 多处不连续修改 → `read` → 规划全部 edits → 一次 `write(edits=[...])`
- 增加 uses 单元 → 用 `delphi_file(action="uses", ...)`，不要手动算行号
- 不确定行号时 → 先 `read` 再写

### delphi_file 紧凑输出格式（v2026.06.12+）

**read 输出**:
```
# encoding: utf-8, 1-indexed [1, 200] (truncated)
```
| 字段 | 说明 |
|------|------|
| `encoding:` | 文件编码 (utf-8 / utf-16-le / utf-16 / gbk / 等) |
| `1-indexed [s, e]` | 本次返回的 1-indexed 左闭右闭区间 |
| `(truncated)` | 文件超出 2000 行被截断（可选标记） |

**write 输出** (edits):
```
wrote: 1 edits, Unit1.pas, encoding: utf-8, backup: __history\Unit1.pas.~1~

  [5, 10] → [5, 13]  edit #0
    - L5_old
    - L6_old
    + L5_new
    + L6_new
    + L7_new
```
- `wrote: N edits` = 成功的 edit 数
- 每个 edit 后跟 `- / +` diff 预览（≤5 行时全量, 超过则省略）
- DFM 转换 / 编码回退会附加额外标记: `ℹ transcoded: utf-16 → utf-8` / `⚠ fallback: gbk → utf-8` / `format: binary DFM converted` / `formatted: yes`

**preview 输出**:
```
preview: 1 edits, Unit1.pas, encoding: utf-8, preview: true（未写入磁盘）

  [5, 10] → [5, 13]  edit #0
    - L5_old
    + L5_new
```

**uses 输出**:
```
wrote: Unit1.pas, action: added System.SysUtils in interface, uses: SysUtils, 1-indexed [2, 3] → [2, 4], encoding: utf-8
```

### write 使用建议

| 场景 | 推荐 |
|------|------|
| 一次性改 1~2 个不连续位置 | `read` → `write(edits=[...])` |
| 一次性改 3+ 个不连续位置 | `read` → `write(edits=[...])`（批量写入已合并到 write） |
| 涉及 uses 单元变更 | `uses` action（专做 uses 子句, 自动算偏移） |
| 改 1 个完整方法/过程 | `read` → 记下行号 → `write(edits=[{start_line:N, end_line:M, content:"..."}])` |

**务必核对 write 响应中的 `- / +` 预览**: 看到 `- L4_old` 配 `+ L3_NEW` 之类的不匹配时, 立即 `read` 文件确认目标行号, 然后重新规划 edits。

---

## ④ 格式化
```python
delphi_file(action="format", file_path="src/Unit1.pas")
# 使用 pasfmt 格式化，自动处理泛型嵌套 `>>` 格式
```

## ⑤ 编译
```python
project(action="compile", project_path="Project.dproj")                         # 整体编译
project(action="compile", project_path="Unit1.pas")                             # 语法检查
project(action="compile", project_path="Project.dproj", build_configuration="Release", target_platform="win64")
# 可选参数：conditional_defines=["DEBUG"], unit_search_paths=["..."], output_path="..."
```

### 运行验证（run_verify）
```python
project(action="compile", project_path="Project.dproj", run_verify=True)
```

编译成功后自动启动 exe 检测运行时崩溃：

**① 注入 StackTrace 单元** — 临时修改 `.dproj`/`.dpr`，验证完自动恢复：
- `.dproj`：添加 `DCCReference` 指向 `tools/stacktrace/StackTrace.pas`、`DCC_UnitSearchPath` 追加 `tools/stacktrace/`、强制 `DCC_MapFile=3`（Detailed map）
- `.dpr`：`uses` 追加 `, StackTrace`，`begin` 后插入：
  ```pascal
  TStackTraceManager.Enabled := True;
  TStackTraceManager.Current.EnableDefaultLogger;
  ```

**② 重新编译**（注入 StackTrace 后）

**③ 运行 exe** — `Popen + wait(timeout=5)`，5 秒超时自动 `kill()`

**④ 检查 `exception.log`**：
- 文件存在 → 用 `detect_encoding()` 读取，内容嵌入编译结果
- 文件不存在 → 标记 `passed`

**⑤ 恢复** — `.dproj`/`.dpr` 从 `.verify_bak` 备份还原

**返回值 `_verify` 字段**：
```json
{"_verify": {"passed": true}}                                          // 通过
{"_verify": {"error": "runtime exception", "log": "异常日志内容..."}}    // 有异常
{"_verify": {"error": "injected compile failed", "log": "..."}}        // 注入后编译失败
```

> **注意**：`StackTrace.pas` 位于 `tools/stacktrace/`，run_verify 使用该内置诊断单元捕获调用栈。
> 当前默认关闭局部变量值快照。如需局部变量，需额外设置 `TStackTraceManager.CaptureVariables := True`。

### 编译失败处理

编译失败是调试中最频繁的场景，按结构化流程处理：

```
编译失败
  │
  ├─ ① 确认编译器状态
  │   └─ check_environment(action="check")
  │
  ├─ ② 分类错误级别
  │   ├─ Fatal → 先处理（通常是路径/配置缺失）
  │   ├─ Error → 主要修复目标
  │   └─ 仅 Warning/Hint → 可暂缓（见 §8.8 错误分类表）
  │
  ├─ ③ 增量 vs 全量
  │   ├─ 首次失败 → 检查最近修改的代码
  │   ├─ 怀疑缓存损坏 → 删 .dcu/.map/.dres 后全量编译
  │   └─ 全量编译通过但增量失败 → 增量缓存问题
  │
  ├─ ④ 路径/配置检查
  │   ├─ DCC_UnitSearchPath 是否包含所有三方库路径
  │   ├─ DCCReference 是否注册了所有依赖单元
  │   └─ 条件编译符号是否匹配当前配置（DEBUG/RELEASE）
  │
  ├─ ⑤ 单文件隔离
  │   ├─ 错误集中在少量单元 → compile_file 单文件验证
  │   ├─ 大量错误 → 从第一个 Error 开始（后续常为连带错误）
  │   └─ 疑难错误 → 二分法隔离（见 §8.9）
  │
  ├─ ⑥ 查经验库
  │   └─ experience(search, query="DCC {错误号} {关键词}")
  │
  ├─ ⑦ 假设驱动分析（§8.7）
  │   └─ 进入假设驱动循环 → 生成 2~3 个假设 → 并行验证
  │
  ├─ ⑧ 二分法隔离（§8.9）
  │   └─ 编译错误二进制搜索 / 运行时崩溃二分 / 回归定位
  │
  ├─ ⑨ 维护调试日志（§8.10）
  │   └─ 每次尝试后更新：假设→验证→结果→推断
  │
  └─ ⑩ 3 次失败仍未解决 → 转 §8.1 评估人工介入
      └─ 检查 §8.14 升级检查点，确认已满足全部条件后再申请介入
```

> **编译事件**：.dproj 中的 PreBuildEvent/PostBuildEvent/PreLinkEvent 自动执行。编译失败时可临时禁用事件排除干扰：在 dproj 中注释相关 `<Event>` 行。
> **编译安全**：`shell=True` 执行事件前记录 `logger.warning`；长轮询 ≤30 秒，超时后切换短轮询。

## ⑥ 代码审核

**编译通过后，按下方审核表逐项审查代码。** 重点覆盖：

| 维度 | 要点 |
|------|------|
| 一致性 | 命名/异常模式/排版的统一性 |
| 完整性 | 分支覆盖、边界条件、输入验证、资源释放 |
| 资源泄露 | Create/Free 配对、句柄/接口释放 |
| Delphi 特有陷阱 | 接口引用计数、字符串类型、TComponent 所有权等 |
| 代码质量 | 圈复杂度、魔法数字、重复代码 |
| 安全 | SQL 注入、硬编码凭据、缓冲区溢出 |

> 审核表的具体检查项见下方「审核」章节。

## ⑦ 清理 & 验证
- **备份验证**：`delphi_file(action="write")` 默认自动备份到 `__history`，修改后可用 `delphi_file(action="backup", backup_action="list", file_path=...)` 确认备份存在
- **整理**：删未用变量/导入/函数/类（直接删，无需人工确认）
- **已存在的死代码**：标记为废弃（添加注释标注），等待人工确认后清理
- **编码**：文件保持原始编码；修改后执行 `delphi_file(action="format", ...)`

---

## 审核

### 一致性

| 检查项 | 说明 |
|--------|------|
| `__history` 备份完整性 | 确认 `__history` 目录中存在本次修改文件的备份，且版本号 ≥ 1 |
| 命名规范 | 类型/字段/方法/参数命名符合规则，新旧代码风格统一 |
| 异常模式 | 同一模块内异常处理方式一致（全部检查返回值或全部抛异常）；`try...finally` 用于资源释放（无论是否异常均执行），`try...except` 用于异常处理（仅在异常时执行）；混合使用时需注释各自职责 |
| 排版 | 缩进、空格、begin/end 风格与项目现有代码一致 |
| 错误处理 | 类似场景使用相同的错误处理模式 |
| OleVariant 与 Variant | 明确区分使用场景，COM 交互用 `OleVariant`，普通逻辑用 `Variant` |
| 平台兼容细节 | `SizeOf` vs `Length` 在不同平台下的行为差异、字节序问题、`NativeInt`/`NativeUInt` 替代 Integer |
| 事件释放（多线程） | 置 nil 时检查多线程竞争，必要时加锁或使用原子操作 |

### 完整性

| 检查项 | 说明 |
|--------|------|
| 所有路径 | if/else、case/else、try/except 覆盖全部分支 |
| 边界条件 | 数组 0 长度、nil 对象、空字符串、MaxInt 值 |
| 输入验证 | 外部传入的参数/文件/流做合法性检查 |
| 资源释放路径 | finally 块确保异常路径下资源也释放 |
| 并发安全 | 共享变量的锁保护，死锁风险，线程退出时资源清理 |
| 函数返回值 | 函数必须有显式返回值，禁止隐式返回未初始化的 Result；`Result` 命名统一 |
| const/out/in 参数 | 输出参数用 `out`/`var` 标注，`const` 参数禁止修改，审计参数传递方式一致性 |
| Assert 使用 | 调试断言用于前置/后置条件检查；注意 `Assert` 在 Release 下被 `{$DEFINES}` 剔除 |
| 初始化/终结段 | `initialization`/`finalization` 段中是否存在资源泄漏或顺序依赖问题 |
| 日志输出 | 日志应区分级别（调试/信息/警告/错误），生产环境只输出必要级别；每条日志包含时间戳、严重级别、可定位问题的上下文信息；异常日志需包含异常类型和调用栈 |

### 资源泄露

| 检查项 | 说明 |
|--------|------|
| Create/Free 配对 | 每个 Create 有对应的 Free/FreeAndNil，record 的 Create 不是类 |
| try/finally | 资源获取后立即 try，finally 中释放 |
| 文件/句柄 | TFileStream、THandle、TMemoryStream 等使用后关闭 |
| 数据库连接 | TSQLConnection、TADOConnection 等用完释放 |
| GDI/系统资源 | TFont、TBitmap、TPen、TBrush、TCanvas、HPEN、HBRUSH |
| 接口引用 | 接口变量超出作用域前确保引用释放，避免循环引用 |
| 字符串/数组 | 大字符串/动态数组不再使用时及时清空释放内存（`SetLength(s, 0)`） |
| TObjectList/TList | `OwnsObjects` 设置正确，确保对象随容器释放 |

### Delphi 特有

| 检查项 | 说明 |
|--------|------|
| 接口引用计数 | 接口赋值自动 `_AddRef`，出作用域自动 `_Release`，避免手动干预 |
| 循环引用 | 两个对象通过接口互相引用会导致内存泄漏，用弱引用或 `[weak]` 破除 |
| TComponent 所有权 | Owner 接收 `Free` 通知，子组件随 Owner 释放，不要重复 Free |
| 字符串类型 | string=UnicodeString 自动管理；AnsiString/WideString 注意编码转换 |
| 字符串拼接 | 循环内大量字符串拼接用 `TStringBuilder`，不用 `+` |
| Variant | 尽量用具体类型替代，Variant 涉及 COM 时注意引用计数 |
| published 区 | 流式加载的属性/事件保持 public 或 published |
| RTTI | `TRttiContext` 用完 Release，避免泄漏 |
| 平台兼容 | Win32/Win64 下指针/句柄大小差异，`NativeInt`/`NativeUInt` 替代 Integer |
| Record 方法与引用 | Record 是值类型，方法内修改字段仅对副本生效；传递给 var/out 参数时注意引用语义 |
| 枚举与子范围 | case 语句覆盖所有枚举值（建议加 `else raise`）；子范围类型注意边界溢出 |
| Set 类型 | Set 元素上限 256 个，元素类型必须为序数类型；空 Set 用 `[]` 而非 `nil` |
| Class Helper 冲突 | 多个 Helper 对同一类的扩展方法命名冲突会导致编译错误，审计命名唯一性 |
| 委托方法生命周期 | 匿名方法/委托捕获变量时注意生命周期，局部变量被引用后释放会导致悬空指针 |

### 常见错误模式

| 检查项 | 说明 |
|--------|------|
| 空异常处理 | `except` 块内必须至少记录日志，**禁止空 `except...end`** 吞噬异常 |
| 类型转换安全 | `as` 转换会抛异常，确认类型应先 `is` 再 `as`；避免硬转 `Type(x)` |
| 事件释放 | 对象释放前将事件字段置 nil（`OnClick := nil`），避免悬空事件回调 |
| 匿名方法捕获 | 循环内创建匿名方法时用局部变量拷贝捕获值，而非引用循环变量 |
| 线程访问 VCL | 后台线程操作 VCL/FMX 控件必须用 `TThread.Queue`/`Synchronize` |
| `with` 语句 | **避免使用 `with`**，导致命名冲突和可读性下降 |
| 动态数组混用 | 明确 `array of T` / `TArray<T>` / open array 参数的区别，不自作聪明转换 |
| record 管理字段 | record 含 `string`/`TArray`/`IInterface` 时注意赋值语义（非引用，会复制） |

### 代码质量

| 检查项 | 说明 |
|--------|------|
| 函数/方法规模 | 单个方法建议不超过 80 行，职责单一，过长需拆分 |
| 圈复杂度 | 嵌套层级不超过 3 层（if/for/while/case 嵌套），过深需用卫语句或抽取方法简化 |
| 魔法数字 | 禁止硬编码魔法数字，需提取为具名常量（`MAX_RETRY = 3`） |
| 注释规范 | 关键逻辑、算法、TODO/FIXME 需有注释；过时/误导注释及时清理；禁止无意义的逐行注释 |
| 代码重复 | 相同或相似逻辑块抽取为公共方法，禁止复制粘贴（DRY 原则） |
| 测试方法命名 | 测试方法命名应清晰描述被测行为及预期结果，格式如 `Test_[方法名]_[条件]_[预期]`；测试代码与生产代码保持相同质量水准 |

### 数据转换

| 检查项 | 说明 |
|--------|------|
| 转换隔离 | 数据与外部格式（JSON/XML/二进制）之间的转换使用专用层或辅助函数，不直接在业务逻辑中操作格式细节 |
| 字段映射 | 避免手写逐字段映射，优先使用声明式映射或自动化机制以减少遗漏 |
| 输入校验 | 反序列化/导入时对数据做结构和范围验证，不信任外部来源 |
| 编码一致 | 文本数据转换时明确指定字符编码，不依赖系统默认编码 |

### 安全

| 检查项 | 说明 |
|--------|------|
| SQL 注入 | 动态拼接 SQL 必须使用参数化查询（`Params.ParamByName`），**禁止字符串直接拼接** |
| 硬编码凭据 | **禁止**在代码中硬编码密码、密钥、API Key 等敏感信息，应使用配置/环境变量 |
| 国际化 (i18n) | 用户可见字符串禁止硬编码，应使用资源字符串（`resourcestring`） |
| 缓冲区溢出 | 数组/缓冲区边界检查，特别是与外部输入相关的拷贝操作（`Move`/`CopyMemory`） |
| 输入消毒 | 来自外部（文件/网络/用户输入）的数据需做格式和范围校验 |

### 性能

| 检查项 | 说明 |
|--------|------|
| 循环内内存分配 | 循环内禁止创建对象/分配大内存，应提到循环外预分配 |
| 字符串操作 | 长字符串拼接用 `TStringBuilder`；`StringReplace` 大数据量时评估性能 |
| 不必要的类型转换 | 避免循环内重复的 `as`/`Type()` 转换，应缓存转换结果 |
| 避免不必要的 RTTI | `TRttiContext` 创建开销大，高频调用途径应缓存类型信息 |

### 审核结果确认

审核发现的修改项，AI **必须等待用户确认后才能执行修改**，不得擅自改动。

| 分类 | 处理方式 |
|------|---------|
| 🔴 影响逻辑/架构的问题 | 必须在报告中标注「需用户确认」，等待确认再改 |
| 🟡 设计决策/有歧义的问题 | 列出选项让用户选择，确认后再改 |
| 🟢 明显编码错误（类型不匹配、缺少引用等） | 可以先修后报，在报告中注明已修复 |

---

## 知识库重建
```python
# Delphi 源码 KB（~1分钟，163737类/300228函数）
delphi_kb(action="build", kb_type="delphi", rebuild=True, async_mode=true)
# 三方库 KB（~6秒，5606类/51265函数）
delphi_kb(action="build", kb_type="thirdparty", rebuild=True, async_mode=true)
# 文档 KB（~6分钟；含 Delphi CHM 中的 DCC 编译器错误说明，共约 1278 个错误/警告文档）
# 构建后可用 delphi_kb(query="E2003", kb_type="document") 查编译器错误官方解释
# ⚠️ rebuild=True 会清除现有文档 KB 中所有内容，如需确认请加 confirm=True
delphi_kb(action="build", kb_type="document", rebuild=True, confirm=True, async_mode=true)
# 项目 KB
delphi_kb(action="build", kb_type="project", project_path="Project.dproj", rebuild=True)

# 轮询进度用短轮询（long_poll ≤30s，超时切换短轮询）
async_task(action="status", task_id="task_xxx")
```

> **文档 KB 重建安全机制**：对文档 KB 设置 `rebuild=True` 时，若 KB 中已有文档（非空），系统会返回当前 KB 统计并要求添加 `confirm=True` 才能继续。这是为了防止意外清除已有的文档内容（如网页抓取的历史文档）。如果你希望保留旧内容，可将旧文档源在新构建参数中一并传入，或移除 `rebuild` 改用增量构建。

---

## Agent 操作硬规则

### 脚本执行
- ❌ 绝不用 `python -c "..."`（PowerShell 引号转义必炸）
- ✅ 始终用 `write` 创建 `.py` 文件 → `bash` 执行 `python script.py` → `Remove-Item script.py` 清理

### 字符串格式化
- ❌ f-string 内嵌字典 `f'{d["key"]}'`（引号冲突）
- ✅ 用 `.format()` 或 `%`

### Python 陷阱
- **不要在函数内局部 `import`**：函数内任何地方出现 `from X import Y` 会使 `Y` 在整个函数作用域成为局部变量。放在头部的引用也会 `UnboundLocalError`。始终写在模块顶部。
- **`if x:` vs `if x is not None:`**：0、`""`、`[]` 都是 False。数字可选参数用 `Optional[int]` 并用 `is not None` 判断。
- **`$()` 宏展开**：注册表变量键名（`SKIADIR`）不含 `$()` 前缀，加入 `macros` 字典时必须 `macros[f'$({k})'] = v`。用 `update(dict)` 会导致 `str.replace('SKIADIR', ...)` 错误匹配 `$(SKIADIR)` → 路径残缺。

---

## ⑧ 自动化UI交互测试

在编译通过（可选 `run_verify` 通过）后，对 GUI 程序进行交互操作和截图验证。

### 接入方式

在 Delphi 程序的 `.dpr` 中添加自动化单元：
```pascal
uses
  Vcl.DaofyAutomation in 'path\to\tools\auto\Vcl.DaofyAutomation.pas',
  DaofyAutomation.Base in 'path\to\tools\auto\DaofyAutomation.Base.pas';

begin
  Vcl.DaofyAutomation.AutoStart;   // 启动命名管道线程
  Application.Initialize;
  Application.CreateForm(TMainForm, MainForm);
  Application.Run;
  Vcl.DaofyAutomation.AutoStop;
end.
```
`AutoStart` 在被测程序中创建命名管道 `\\.\pipe\daofy_auto`，等待外部命令。

### 工具调用
```python
# 自动检测：GUI exe → 命名管道，Console exe → subprocess
automate_delphi(app_path="App.exe", script=[...])
automate_delphi(app_path="App.exe", script="script.json", keep_alive=True)

# 也可显式指定模式
automate_delphi(action="gui", app_path="App.exe", script=[...])
automate_delphi(action="console", app_path="Tool.exe", input="Y\n", expect="Continue?")
```
`action="auto"`（默认）自动检测 PE 头 Subsystem 字段区分 GUI/控制台程序。
脚本由 JSON 命令数组组成，每条命令结构：`{"cmd": "...", "target": "...", ...}`。

### 通信架构

```
Python (automation_service.py)              Delphi (TAutomationProcessorBase)
  ── CreateFile(\\.\pipe\daofy_auto) ──→      管道线程接收 JSON 请求
  ── WriteFile(JSON request)          ──→     主线程执行操作
  ←── ReadFile(JSON response)         ────    返回结果/ACK
```
传输层：Windows 命名管道（命名管道 JSON 请求/响应），零外部依赖。

### 命令列表

> 各命令的详细描述、典型场景、优先级见 §A 工具分类（perceive/execute/verify）。
> 下表仅补充**同步/异步**属性（§A 未标注）。

| 命令 | 同步/异步 | 说明 |
|------|-----------|------|
| `goto` / `snapdir` / `exit` / `dlgfile` | 同步 | 菜单级状态变更，需确认完成 |
| `capture` / `dumpstate` / `listwnd` / `formsum` | 同步 | 感知类，需等待完整数据返回 |
| `wait` / `waitfor` | 同步 | 时序控制，本身设计为阻塞 |
| `dlgscan` / `msgscan` / `msgclose` | 同步 | 弹窗扫描需完整结果 |
| `rget` / `rinspect` | 同步 | RTTI 读取需返回值 |
| `click` / `rclick` / `dblclick` | 异步 | UI 操作不阻塞管道 |
| `hover` / `move` / `drag` | 异步 | 鼠标事件异步提交 |
| `type` / `key` | 异步 | 输入队列异步推送 |
| `rcall` / `rset` | 异步 | RTTI 调用不等待业务完成 |
| `msgclick` / `dlgclick` | 异步 | 弹窗按钮点击后立即 ACK |

### keep_alive 机制

- `keep_alive=True` 时进程保持运行，后续调用直接复用
- 进程 5 分钟未被使用自动清理
- 新建进程首次调用自动设置 `snapdir` 到截图目录

### 协议细节
- 同步命令（goto/capture/waitfor/wait/dumpstate/listwnd/dlgscan/msgscan/msgclose/dlgfile/snapdir/exit/rget/rinspect）阻塞等待返回
- 异步命令（click/rclick/dblclick/hover/move/drag/msgclick/dlgclick/rcall/key/rset/type）立即返回 ACK，结果在后续步骤中通过 peekresult 获取（内存结果，无文件落盘）
- 响应格式：`{"reqId":"step_0","status":"ok","data":"OK"}`
- 消息大于 64KB 时自动分块（`ERROR_MORE_DATA` 循环读取）
- 超时支持：`waitfor` 命令内置 `timeout` / `interval` 参数（单位 ms）

### 测试脚本示例
```json
[
  {"cmd": "goto", "target": "TMainForm"},
  {"cmd": "capture", "target": "main_initial"},
  {"cmd": "click", "target": "BtnLogin"},
  {"cmd": "waitfor", "target": "StatusBar", "prop": "Caption", "value": "登录成功", "timeout": 5000},
  {"cmd": "capture", "target": "main_logged_in"},
  {"cmd": "exit"}
]
```

---

## ⑨ 控制台程序交互验证

针对控制台（console）类型的 Delphi 程序，通过 `automate_delphi` 工具的 console 模式进行 stdin/stdout 交互。
**不需要 Delphi 端做任何改造**——控制台 I/O 完全在 Python 侧处理。

`action="auto"` 时会自动检测 PE 头 Subsystem 字段，GUI=命名管道，Console=subprocess。
也可显式指定 `action="console"`。

### 工具调用
```python
# 自动检测（推荐）
automate_delphi(app_path="Tool.exe", input="Y\n", expect="Continue?")

# 显式指定
automate_delphi(action="console", app_path="Tool.exe", input="Y\n", expect="Continue?")
automate_delphi(action="console", app_path="Deploy.exe", args=["--silent"], timeout=60)
```

### 测试模式

```
Python (subprocess)                           Console Delphi exe
  ── Popen(stdin=PIPE, stdout=PIPE) ──→       begin..end. 启动
  ── proc.stdin.write("input\n")     ──→       ReadLn 接收
  ←── proc.stdout.read()             ────     WriteLn 输出
  ←── proc.wait(timeout=5)           ────     exit
```

### 基础用法
```python
import subprocess

proc = subprocess.Popen(
    [exe_path, "--arg1", "value"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    cwd=work_dir,
)
stdout, stderr = proc.communicate(input=b"user input\n", timeout=10)
```

### 分步交互（keep_alive 模式）
```python
proc = subprocess.Popen(
    [exe_path],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)

# 发送输入
proc.stdin.write(b"Y\n")
proc.stdin.flush()

# 读取输出（等待 prompt 出现）
import select
while True:
    line = proc.stdout.readline()
    if not line:
        break
    if b"Continue?" in line:
        proc.stdin.write(b"N\n")
        proc.stdin.flush()
        break

proc.wait(timeout=5)
```

### expect 式等待（等待指定输出模式）
```python
def expect_output(proc: subprocess.Popen, pattern: str, timeout: float = 5.0) -> list[str]:
    """等待 stdout 中出现指定模式。"""
    import re
    deadline = time.time() + timeout
    lines: list[str] = []
    while time.time() < deadline:
        import select
        reads, _, _ = select.select([proc.stdout], [], [], 0.5)
        if reads:
            line = proc.stdout.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace")
            lines.append(decoded)
            if re.search(pattern, decoded):
                return lines
    raise TimeoutError(f"未在 {timeout}s 内匹配到模式: {pattern}")
```

### 适用场景
- 命令行工具的功能测试（参数解析、输出格式）
- 批处理流程的逐步操作（菜单选择、确认提示）
- 安装程序的无人值守自动化
- 长时间运行任务的输出监控

### 注意事项
- **超时控制**：`communicate(timeout=...)` 或 `wait(timeout=...)` 必须设置，避免进程卡死
- **管道缓冲**：大量输出时注意系统管道缓冲区（默认 4KB-64KB），用 `readline()` 逐行读避免死锁
- **stderr**：建议 `stderr=subprocess.STDOUT` 合并输出，或单独捕获
- **exit code**：通过 `proc.returncode` 判断程序是否正常退出
- **编码**：Windows 控制台输出通常是 `gbk`，用 `.decode('gbk', errors='replace')` 处理

---

## ⑩ 人机协同 — 异常诊断与人工介入

### 概述

AI Agent 不是万能的。当遇到无法独立解决的问题时，及时、高质量地申请人工介入，
比死磕更高效。本节定义异常的诊断流程、人工介入的触发条件和交接标准。

### 前置自检（所有任务通用）

开始执行或遇到卡点时，先暂停并按以下清单自检，逐一核对是否满足 §10.1 触发条件：

- 🔴 工具返回错误或结果异常 → 交叉验证一次，仍异常则暂停检查
- 🟡 不确定接下来选哪个方案 → 检查是否触发「方案选择歧义」条件
- 🟡 准备重试时发现和上一次尝试本质相同 → 触发「连续同质方案」条件
- 🟡 缺少关键信息需要猜测 → 触发「信息不足猜测」条件

**按触发条件优先级执行**：🔴 P0 立即停 → 🔴 P1 停 → 🟡 P2 停 → 其余继续。

### 8.1 人工介入触发条件

满足以下任一条件时，AI Agent **必须主动停止尝试并申请人工介入**：

| 优先级 | 触发条件 | 示例 |
|--------|---------|------|
| 🔴 P0 | 连续 3+ 次修复尝试均失败（AI 应在 3 次失败后停止并申请介入） | 编译报错 3 次未解决 |
| 🔴 P0 | 报错原因指向 AI 无法访问的封闭代码/环境 | 第三方闭源 DLL 崩溃、硬件驱动问题 |
| 🔴 P1 | 问题涉及需要人工确认的设计决策 | 架构变更、API 兼容性取舍 |
| 🟡 P2 | 错误信息不完整，无法确定根因 | 内存损坏（Access Violation 无调用栈） |
| 🟡 P2 | 需要访问外部受限资源 | 企业内部 Git、VPN 环境、License 服务器 |
| 🟡 P2 | 2+ 个可行方案但不确定哪条更优（方案选择歧义） | API 调用方式有 3 种等价写法、修复策略有 2 种不同路径 |
| 🟡 P2 | 连续两次尝试的方案本质相似（仅换参数/顺序再试） | 编译失败后换个 flag 又试一次、换个顺序再读一次文件 |
| 🟡 P2 | 信息不足时强行猜测 | 错误消息只说"找不到文件"不给路径，AI 自行猜测路径去试 |
| 🟡 P2 | 同一工具连续失败 2 次 | project(compile) 连续 2 次编译器报错，AI 仍继续调 compile 而不是换思路 |
| 🟢 P3 | 问题本身很简单但 AI 验证环境不匹配 | 用户本机特有的注册表状态、DLL 版本差异 |

> **例外**：如果失败原因是 AI 编码错误（如明显逻辑 bug、缺少引用单元），
> 不属于人工介入范畴，应继续修复。

**补充细则**：

- **方案选择歧义**：`list_tools()` 中有多个工具都能完成同一目标，或同一问题有多种等价修复路径时，不得默认选一个。必须在 1 轮内列出选项及判断依据，申请人工介入选择。例："方案 A：...，方案 B：...，请选择"
- **信息不足不猜测**：工具返回的结果或错误消息缺少决定性信息时，先尝试其他工具补全信息（如先用 `delphi_file(action="read")` 读源码），仍不足则追问用户，不得自行编造缺失信息。连续猜测 2 次仍错 → 申请人工介入。
- **同一工具连败换方向**：同一个工具连续失败 2 次时，先检查是否用错了工具，尝试更换其他工具或完全不同的策略方向。仍无效 → 申请人工介入。
- **结果异常应核实**：工具返回 `success` 但结果明显不合理时（如空列表、0 行读取、内容为空），须调用其他工具重新读取或交叉验证，确认后再继续。怀疑数据问题时优先重试一次（排除瞬态），不直接申请人工介入。

**优先级交互说明**：
- P2(同工具2次) 先触发 → 换方向 → 换方向后再失败，总计 3+ 次 → 进 P0 直接介入
- P2(信息不足) 猜错 2 次后 → 进 P0 直接介入
- P2 换方向后解决 → 不必走到 P0

### 8.2 异常诊断六步法（分析→计划→审计→备份→执行→验证）

遇到异常时，按以下六步执行。**审计发现问题时必须回退到分析/计划修正；验证失败时必须回退到分析重新排查。**

> 非代码修复场景（仅改配置/注册表/环境变量/更新 DLL，不修改源码）可跳过 ④ 备份和 ⑤ 执行，直接进入 ⑥ 验证，但必须明确记录跳过的原因和理由。

```
        ┌─────────────────────────────────────────────────┐
        │  ① 分析                                         │
        │  采集信息 → 定位根因 → 确定问题性质              │
        └──────────────────────┬──────────────────────────┘
          ▲                    │  
          │   审计退回(🔴)     │  ← 验证退回方向
          │   计划退回(🟡)     │    (⑥ 失败→回 ①)
          │                    │  
        ┌─┼──────────────────────────┐
        │ ② 计划                     │
        │ 设计方案→多方案对比→验证标准 │
        └───────────┬────────────────┘
                    │ 审计退回(🟡边界/规范)
                    ▼
        ┌──────────────────────────────┐
        │ ③ 审计                       │
        │ 按详细检查表逐项审查方案       │
        │ ├─ ✅ 通过 → 继续             │
        │ └─ ❌ 问题 → 退回①分析或②计划│
        └───────────┬──────────────────┘
                    │
                    ▼
        ┌──────────────────────────────┐
        │ ④ 备份                       │
        │ __history备份 + WIP commit   │
        └───────────┬──────────────────┘
                    │
                    ▼
        ┌──────────────────────────────┐
        │ ⑤ 执行                       │
        │ Preview→修改→格式化→编译→commit│
        └───────────┬──────────────────┘
                    │
                    ▼
        ┌──────────────────────────────┐
        │ ⑥ 验证                       │
        │ 按标准验证→清理→保存经验      │
        │ ├─ ✅ 通过 → 完成             │
        │ └─ ❌ 失败 → 退回①分析       │
        └──────────────────────────────┘

| 步骤 | 目标 | 方法和具体事项 | 工具/命令 | 关键检查点 | 产出物 |
|------|------|--------------|-----------|-----------|-------|
| **① 分析**<br>(Analyze) | 全面理解问题，定位根因，区分问题类型 | **1. 采集现场信息**（按 §8.3 模板：异常类型/消息/调用栈/环境/关键变量值）<br>**2. 复现确认**：确定问题能否稳定复现，记录复现步骤<br>**3. 检查最近变更**：`git log --oneline -10` + `git diff` 查看近期修改<br>**4. 搜索经验库**：`experience(search, query="<问题关键词>")` 查同类问题<br>**5. 确认问题性质**：分类为编译错误（§8.8）/ 运行时崩溃（§8.13）/ 逻辑错误 / 环境问题，再按 §8.11 选择对应工具<br>**6. 深入搜索**：编译错误 → §8.8 DCC 分类 + `delphi_kb(query="<错误号>", kb_type="document")`<br>**7. 标记问题严重度**：P0（崩溃/数据丢失）/ P1（功能异常）/ P2（体验/次要）<br>**8. 生成根因假设**：参照 §8.7 假设驱动调试，生成 2~3 个互斥假设<br>**9. 假设验证**：用最少操作验证最可能的假设<br>**10. 判断是否可自行修复**：代码缺陷→继续；环境/权限/闭源→转 §8.1 介入 | `delphi_project(compile)`<br>`delphi_file(read)`<br>`delphi_kb(query=...)`<br>`experience(search, ...)`<br>`git log/diff/bisect`<br>`lsp_diagnostics`<br>`automate_delphi(msgscan)` | 🔴 是否区分了代码缺陷 vs 环境问题？<br>🔴 是否查过经验库？（第 2 次失败前必须有）<br>🔴 是否标记了问题严重度？<br>🟡 假设是否可证伪？（不可证伪 → 细化）<br>🟡 是否检查了最近代码变更？<br>🟡 是单一问题还是连锁问题的结果？ | 根因假设（含置信度）<br>问题分类+严重度标签<br>已排除的候选原因列表<br>是否可自行修复的判断 |
| **② 计划**<br>(Plan) | 设计明确、最小化的修复方案，定义验证标准 | **1. 确定修复范围**：修改哪些文件、哪些行（最小化原则，不修无关代码）<br>**2. 验证 API 用法**：`delphi_kb(query="<API名>", search_type="function")` 确认 API 签名和行为<br>**3. 多方案对比**：存在 2+ 可行方案时，列出对比表（方案/工作量/风险/回滚难度/推荐）<br>**4. 评估影响范围**：修改会影响到哪些调用方？是否有兼容性问题？<br>**5. 定义验证标准**：明确"修复成功"的可观测条件（如：编译 0 Error + 某函数返回特定值 + 某弹窗不再出现）<br>**6. 列出所有修改点**：每处修改明确到 start_line/end_line 和内容<br>**7. 确认编译配置**：Debug/Release/DCC_Define 差异<br>**8. 检查编码规范一致性**：命名/格式/模式是否符合项目惯例<br>**9. 非代码修复**：如仅需改配置/注册表/环境变量/更新 DLL，可跳过 ④~⑤，直接到 ⑥ 验证<br>**10. 如果是环境问题** → 跳 §8.1 申请人工介入，不自行修复 | `delphi_kb(search_type="function"/"class")`<br>`delphi_file(read)`<br>`get_coding_rules(section="review")`<br>`delphi_project(info)` | 🔴 是否每个修改点都有依据，而非猜测？<br>🔴 修复范围是否最小？（不修无关代码）<br>🔴 是否定义了可验证的"修复成功"标准？<br>🟡 存在多方案时是否做了对比？<br>🟡 API 行为是否已确认？（不确定时先查 KB 再动）<br>🟡 是否考虑了 Debug/Release 差异？<br>🟡 是否考虑了 32/64 位平台差异？ | 修复方案清单（文件→行→内容）<br>多方案对比表（如有）<br>验证标准定义<br>影响范围评估<br>API 确认记录 |
| **③ 审计**<br>(Audit) | 按详细检查表（见下方）逐项审查方案的根因匹配、安全风险、完整性、一致性、影响范围，拦截潜在问题 | **审计维度分类**：<br>├─ **方案与根因匹配**：方案是否针对根因（非症状）、是否越界、是否遗漏连锁问题<br>├─ **安全与风险**：是否引入新崩溃路径、回滚可逆性、接口/数据/并发安全<br>├─ **方案完整性**：分支覆盖、边界条件、资源释放、输入验证、验证标准<br>├─ **编码规范一致性**：命名、异常模式、风格、注释<br>├─ **影响范围**：编译/平台/版本兼容、公共函数影响、文档更新、配置变更<br>├─ **经验与记录**：经验库已查、调试日志已更新、介入条件是否已满足<br><br>**审计结论**：通过 / 退回分析（🔴 项不通过）/ 退回计划（🟡 ≥2 项不通过） | `get_coding_rules(section="review")`<br>`get_coding_rules(section="consistency")`<br>`get_coding_rules(section="safety")`<br>`delphi_kb(search_type="reference")`<br>`lsp_find_references` | 🔴 有 🔴 项不通过？→ **必须退回**<br>🔴 修改了公共工具函数/基类？→ 检查所有调用方<br>🔴 验证标准未定义？→ 退回补充<br>🟡 🟡 不通过项 ≥2？→ 退回计划 | 审计结论（通过/退回）<br>问题清单（每项：通过/不通过/不适用）<br>退回目标（分析/计划） |
| **④ 备份**<br>(Backup) | 确保代码可安全回滚，降低执行风险 | **1. 确认版本控制状态**：`git status` 检查工作区是否干净<br>**2. 标记涉及的所有文件**：列出本次修改涉及的全部文件（.pas/.dfm/.dproj 等）<br>**3. 逐个备份被修改文件**：对每个文件执行 `delphi_file(action="backup", backup_action="create", ...)`<br>**4. 需要时暂存/提交当前工作**：`git stash` 或 `git commit -m "WIP: <问题描述> before fix"` 保留修改前现场（此为 WIP 标记，非最终提交，⑤ 执行通过后会重新正式提交）<br>**5. 记录修改前快照**：必要时截图/保存原始文件副本<br>**6. 确认所有文件已成功备份**：验证每个文件的备份存在于 `__history/` 目录 | `delphi_file(backup, create)`<br>`code_hosting(git_status)`<br>`code_hosting(git_stash)` | 🔴 是否所有涉及文件都有 __history 备份？<br>🔴 多文件修改时是否逐一确认备份？<br>🟡 工作区是否有未提交的重要修改？<br>🟡 修改涉及 .dfm/.res 等二进制文件？→ 确认已备份 | 备份确认清单<br>涉及文件列表<br>工作区状态记录 |
| **⑤ 执行**<br>(Execute) | 按计划精确修改代码，确保编译通过 | **1. 预览确认**：`delphi_file(action="write", preview=True)` 确认 diff 符合预期后再正式写入<br>**2. 按序应用修改**：按 start_line 从小到大一次提交所有 edits，多文件先改依赖后改被依赖<br>**3. 格式化代码**：`delphi_file(action="format", file_path=...)` 保持代码风格一致<br>**4. 检查残留调试代码**：确认无 `ShowMessage`/`OutputDebugString`/`WriteLn`/断点/本次调试临时添加的条件编译（如 `{$IFDEF DEBUG_SKIP}`）等<br>**5. 编译验证**：`delphi_project(action="compile", ...)` — 单文件修改用 `compile_file` 快速验证；修改量大或涉及 .dproj 时全量编译；增量失败时删 `.dcu` 后全量重编<br>**6. 提交版本**：编译通过后 `code_hosting(git_add)` + `code_hosting(git_commit)`，提交信息注明 "fix: 问题描述"（此为正式提交，与 ④ 备份中的 WIP 标记不同） | `delphi_file(write, edits=[...])`<br>`delphi_file(format)`<br>`delphi_project(compile)`<br>`delphi_project(action="compile", compile_file=...)`<br>`code_hosting(git_add/commit)` | 🔴 Preview diff 是否与预期一致？<br>🔴 是否有 old_content 校验失败？→ 回读文件修正行号<br>🔴 编译是否有 Error？→ 回到 ① 分析<br>🟡 Warning 是否已知/可忽略？<br>🟡 是否有残留调试代码/断点？<br>🟡 编译通过后是否已 git commit？ | 编译结果<br>格式化确认<br>偏移量记录<br>git commit hash |
| **⑥ 验证**<br>(Verify) | 确认修复有效、无回归，沉淀经验 | **1. 功能验证**：按 ② 计划中定义的验证标准，确认原始问题不再复现<br>**2. 运行验证**：`delphi_project(action="compile", run_verify=True)` 启动 exe 检测运行时崩溃<br>**3. 运行时检查**：`delphi_project(action="runtime", base_dir=...)` 检查组件 uses 完整性<br>**4. 边界测试**：检查相关边界的正确性（空值、极限值、异常路径）<br>**5. 回归范围**：用 `lsp_find_references` / `grep` 搜索被修改函数/类的所有引用，确认关联模块正常<br>**6. LSP 检查**：`lsp_diagnostics` 确认无类型/语法错误<br>**7. 清理**：删除 `{$IFDEF DEBUG_SKIP}` 等临时代码、恢复编译配置、清理调试日志（§8.10）<br>**8. 保存经验**：`experience(action="save", ...)` 将解决方案沉淀到经验库<br>**9. 审计回执**：在调试日志中标记"审计通过，验证完成"，通知用户确认结果<br>**10. 触发复盘判断**：是否满足 §8.12 复盘条件（根因归类+防御评估）<br><br>**验证失败处理**：<br>├─ 编译失败 → 回到 ① 分析，可能是根因判断有误或产生了新问题<br>├─ 运行崩溃 → 回到 ① 分析，方案不完整或根因遗漏<br>├─ 原问题仍存在 → 回到 ① 分析，根因判断错误<br>└─ 回归问题 → 回到 ② 计划，补充边界处理 | `delphi_project(compile, run_verify=True)`<br>`delphi_project(runtime)`<br>`lsp_diagnostics`<br>`experience(save)`<br>`pytest`（如果项目有测试）<br>`automate_delphi`（如果适用） | 🔴 原始问题是否确认不再复现？<br>🔴 是否有新的编译错误？<br>🔴 验证失败是否回到了 ① 分析？（不得直接重复执行）<br>🟡 回归范围：`grep`/`lsp_find_references` 是否已执行？<br>🟡 运行时是否有异常日志生成？<br>🟡 经验是否已保存？（必须有）<br>🟡 是否已通知用户确认结果？<br>🟡 临时代码/调试日志是否已清理？<br>🟡 是否触发了 §8.12 复盘条件？ | 验证报告（含验证标准逐条对照）<br>经验保存记录<br>是否需要复盘的判断<br>用户确认记录 |

**审计回退循环规则**：

```
③ 审计发现问题
  ├─ 🔴 安全问题 / 方案遗漏根因 → 退回 ① 分析，重新采集信息
  ├─ 🔴 影响范围漏评 / API 用法不确定 → 退回 ② 计划，补充分析
  ├─ 🟡 边界条件未覆盖 → 退回 ② 计划，补充边界处理
  └─ 🟡 编码风格/规范问题 → 退回 ② 计划，修正并格式化后可在同次审计中直接通过

  退回原则：
  ① 退回后修正完成，必须重新执行 ③ 审计（递归保证）
  ② 同一问题连续退回 3 次 → 触发 §8.1 P0 人工介入
  ③ 审计发现的问题本身需要深度分析 → 退回 ① 而非 ②
```

---

#### ③ 审计详细检查表

审计步骤按以下分类逐项检查修复方案。（严重度：🔴=严重，必须退回；🟡=中等，≥2 项不通过退回；🟢=提示，不阻塞通过。）

| 分类 | 检查项 | 具体检查内容 | 验证方法 | 严重度 | 适用时机 |
|------|--------|------------|---------|--------|---------|
| **方案与根因匹配** | 根因覆盖 | 方案是否直接修复了 §8.2 ① 分析确定的根因，而非只处理了表面症状？ | 对照分析步骤的根因假设，逐条确认方案是否覆盖 | 🔴 | 每次 |
| | 问题边界 | 方案是否只在问题边界内修改，没有越界改动无关代码？ | 检查方案中每处修改是否在问题的影响范围内 | 🔴 | 每次 |
| | 假设验证 | 如果存在多个根因假设，方案是否只针对已证实的假设，而非"顺便修"未证实的？ | 对照 §8.7 假设驱动调试的结论 | 🟡 | 存在多假设时 |
| | 连锁问题 | 当前问题是否可能是更底层问题的连锁症状？修复表层后底层问题是否仍然存在？ | 向上追溯调用链，确认修复点是否足够底层 | 🔴 | 根因不确定时 |
| | 零修改方案 | 是否考虑过"不做代码修改"的选项（如改配置/加环境变量/更新依赖）？ | 对照 §8.11 环境问题分支确认 | 🟡 | 每次 |
| **安全与风险** | 新引入风险 | 修复是否可能引入新的崩溃路径（空指针、越界、除零）？ | 逐条审查修改后的代码路径，特别是异常分支 | 🔴 | 每次 |
| | 回滚可逆性 | 如果修复不生效，能否通过 `__history` 备份或 git revert 干净回退？ | 确认有备份 / git 提交点 | 🔴 | 每次 |
| | 接口兼容性 | 修复是否修改了 public/protected 接口、虚方法签名、 published 区？ | 检查修改是否涉及接口/类声明区 | 🔴 | 涉及接口时 |
| | 数据完整性 | 修复是否涉及数据格式变更（DFM/JSON/DB/注册表）？旧数据能否兼容？ | 检查修改是否涉及流式/序列化逻辑 | 🔴 | 涉及数据时 |
| | 并发安全 | 修复是否涉及多线程共享变量、事件回调、Timer、Socket 等异步路径？ | 检查代码路径中是否有同步原语保护 | 🔴 | 涉及多线程时 |
| **方案完整性** | 分支覆盖 | 修复是否覆盖了所有分支（if/else、case/else、try/except 的正常+异常路径）？ | 对照源码中的所有分支点逐条检查 | 🔴 | 每次 |
| | 边界条件 | 修复是否处理了边界条件（空集合→0 次循环、nil 对象、空字符串、Int.MinValue）？ | 逐条检查修改点涉及的条件判断 | 🔴 | 每次 |
| | 资源释放 | 修改路径上是否所有的 Create/Acquire/Lock 都有对应的 Free/Release/Unlock？ | 检查 try/finally 覆盖 | 🔴 | 涉及资源时 |
| | 输入验证 | 修复是否涉及外部输入（参数/文件/用户输入）？输入是否做了合法性校验？ | 检查输入来源和校验逻辑 | 🟡 | 涉及外部输入时 |
| | 初始化状态 | 修改涉及的新变量/对象是否已正确初始化？ | 检查所有新增变量的初始值 | 🟡 | 涉及新变量时 |
| | 验证标准 | ② 计划中是否定义了可观测的"修复成功"验证标准？ | 对照计划中的验证标准，确认其可测量、可复现 | 🟡 | 每次 |
| **编码规范一致性** | 命名规范 | 新增的标识符是否符合项目命名惯例？ | 对照 `get_coding_rules(section="review")` | 🟡 | 涉及新标识符时 |
| | 异常处理模式 | 异常处理风格是否与模块现有代码一致（返回值 vs 抛异常）？ | 阅读模块中周围代码的异常处理模式 | 🟡 | 涉及异常处理时 |
| | 代码风格 | 缩进、空行、begin/end 位置是否与项目现有代码一致？ | 格式化后检查 | 🟢 | 每次 |
| | 注释与文档 | 修改是否自解释？复杂逻辑是否有注释？ | 判断修改是否需要补充注释 | 🟢 | 每次 |
| **影响范围** | 编译兼容 | 修改在 Debug 和 Release 配置下均能编译通过？ | 确认修改不依赖 `{$IFDEF DEBUG}` 等条件编译符号。同时检查 .dproj 中的条件定义（见下方"项目配置"）是否一致 | 🟡 | 涉及条件编译时 |
| | 平台兼容 | 修改在 Win32 和 Win64 下行为一致？（指针大小、NativeInt、字节对齐） | 检查 `SizeOf` / `Pointer` / `NativeInt` 等使用 | 🔴 | 涉及跨平台时 |
| | 旧版本兼容 | 如果项目支持多 Delphi 版本，修改是否在所有支持版本上兼容？ | 检查使用的 API 是否存在版本差异 | 🟡 | 涉及多版本时 |
| | 公共函数影响 | 如果修改了公共工具函数/基类，是否检查了所有调用方？ | 用 `lsp_find_references` 或 `grep` 搜索所有引用 | 🔴 | 修改公共代码时 |
| | 文档更新 | 修复是否涉及用户可见行为变化？是否需要同步更新文档/CHANGELOG/用户手册？ | 判断修改是否影响界面文案/功能行为/接口签名 | 🟡 | 涉及用户可见变化时 |
| | 三方库依赖 | 修改是否新增了对三方库的依赖？新增依赖是否在项目允许范围内？ | 检查 uses 子句新增的单元来源 | 🟡 | 涉及新增 uses 时 |
| | 项目配置 | 修改是否涉及 .dproj 配置变更（搜索路径/条件编译/链接选项）？ | 检查 .dproj 文件是否有修改。与上方"编译兼容"交叉验证：代码中的 `{$IFDEF}` 需与 .dproj 中的 `DCC_Define` 一致 | 🔴 | 涉及 .dproj 时 |
| **经验与记录** | 经验库查询 | 此问题是否已在经验库中有现成解决方案？ | `experience(search, query="<问题关键词>", top_k=3)` | 🟡 | 第 2 次失败前必须有 |
| | 修改记录 | 修复方案是否已记录到调试日志（§8.10）？ | 确认调试日志已更新 | 🟢 | 每次 |
| | 人工介入标识 | 当前问题是否已满足 §8.1 介入条件？（3 次失败/同质方案/同工具 2 次失败） | 对照 §8.1 表逐条检查 | 🔴 | 每次 |

**审计执行流程**：

```
1. 按上表逐项检查，每项记录：通过 / 不通过（附原因）/ 不适用
2. 汇总审计结论：
   ├─ ✅ 全部通过（或仅 🟢 项不通过）→ 进入 ④ 备份
   ├─ 🔶 有 🟡 项不通过但 ≤1 项 → 记录问题，进入 ④ 备份（注明待改进）
   ├─ 🔶 有 🟡 项不通过且 ≥2 项 → 退回 ② 计划 修正
   └─ ❌ 有任何 🔴 项不通过 → 退回 ① 或 ②（具体路由见上方「审计回退循环规则」）
3. 退回后修正完成 → 全部重新审计（递归保证；编码规范类已在同次审计中修正的可直接通过）
4. 同一问题连续退回 3 次 → 触发 §8.1 P0 人工介入
```

> **非代码修复场景的审计**：如 ② 计划判定为"非代码修复"（仅改配置/注册表/环境变量/更新 DLL），③ 审计仍需执行，但只审计以下范围：
> - 安全与风险（配置变更是否引入安全漏洞、回滚可逆性）
> - 影响范围（配置变更是否影响其他模块）
> - 经验与记录（经验库、调试日志）
> - **跳过**：方案与根因匹配、方案完整性、编码规范一致性（未修改源码）。

> **与现有审核规则的关系**：本表审计的是**修复方案**（执行前），而 `get_coding_rules(section="review")` 审核的是**已完成的代码**（编译后）。二者互补，不可替代。
> - ③ 审计 → 拦截方案缺陷，防患于未然
> - `review` 审核 → 检查编写后的代码质量，兜底补漏
> - 修复流程应先后执行二者：先 ③ 审计方案，修改并编译通过后再执行 `review` 审核代码

**六步法与相关章节的关系**：

| 步骤 | 输入（依赖） | 输出（被依赖） |
|------|------------|--------------|
| ① 分析 | §8.3 异常信息采集模板、§8.7 假设驱动调试、§8.11 工具选择决策树 | → §8.1（环境问题→转介入） |
| ② 计划 | §8.14 尝试升级检查点 | → ③ 审计 |
| ③ 审计 | `get_coding_rules(section="review")`（代码审核）<br>`get_coding_rules(section="consistency")`（一致性）<br>`get_coding_rules(section="safety")`（安全规则） | → ① 或 ②（退回时） |
| ④ 备份 | — | → ⑤ 执行 |
| ⑤ 执行 | `get_coding_rules(section="writing")`（写代码规则） | → ⑥ 验证 |
| ⑥ 验证 | ② 计划中定义的验证标准<br>`get_coding_rules(section="compile")`（编译规则） | → §8.12 复盘判断<br>→ 经验库 `experience(save)`<br>→ ① 分析（验证失败时回退） |


### 8.3 异常的完整信息采集

当异常发生时，按以下模板记录：

```python
# Python 异常采集模板
import traceback, sys

def capture_exception_context(exc: Exception, locals_dict: dict = None) -> dict:
    """采集异常现场信息"""
    exc_type, exc_value, exc_tb = sys.exc_info()
    return {
        "exc_type": type(exc).__name__,
        "exc_message": str(exc),
        "traceback": traceback.format_exc(),           # 完整调用栈
        "frames": [
            {
                "file": frame.f_code.co_filename,
                "line": frame.f_lineno,
                "function": frame.f_code.co_name,
                "code": frame.f_code.co_code,
                "locals": {k: repr(v) for k, v in frame.f_locals.items()}
            }
            for frame in traceback.extract_tb(exc_tb)
        ],
        "exception_args": getattr(exc, "args", []),
    }
```

Delphi 异常采集比 Python 复杂得多——运行时无法直接获取符号化调用栈。
因此推荐以下两种实用方案（**二选一即可，不需要在代码中手动采集**）：

---

**方案 A：AI 引导用户在 IDE 中重现（推荐，零依赖）**

AI 无法直接接触 Delphi IDE 调试器，但可以引导用户操作：

```
┌──────────────────────────────────────────────────────────────┐
│ AI → 用户引导清单                                              │
│                                                                │
│ ① 准备工作                                                   │
│    "在 Delphi IDE 中打开项目文件 {项目名}.dproj"               │
│    "确认当前配置为 Debug（Project → Build Configuration → Debug）"│
│    "Release 模式下无调试符号，无法设断点和查看变量"             │
│    "在 Project Manager 中找到 {文件名}.pas，双击打开"          │
│                                                                │
│ ② 定位问题点                                                  │
│    "在 {函数名} 的第一行左侧点击设断点（或 F5）"              │
│    "在 {可疑变量名} 上右键 → Add Watch"                        │
│                                                                │
│ ③ 触发异常                                                   │
│    "按 F9 运行程序，复现 {操作步骤}"                            │
│    "等断点命中后，单步跟踪（F7/F8）直到 {关键行}"              │
│                                                                │
│ ④ 收集信息报给 AI                                            │
│    用户报告以下内容即可：                                      │
│    - **出错文件**：{单元名}.pas，第 XXX 行                     │
│    - **异常消息**：IDE 弹出的异常对话框内容                    │
│    - **调用栈**：IDE 的 Call Stack 窗口（Ctrl+Alt+S），全选后 Ctrl+C 复制粘贴给 AI │
│    - **关键变量**：Watch 窗口中显示的变量值                    │
│                                                                │
│ ⑤ 修复验证                                                   │
│    AI 根据信息给出修复代码，用户应用后重新编译运行             │
└──────────────────────────────────────────────────────────────┘
```

> **适用场景**：偶发异常、逻辑错误、需要在调试器中观察变量状态的场景。
> **成本**：需要用户手动操作，但信息最准确。
> **注意**：必须使用 **Debug 配置**编译（生成完整调试符号），Release 配置下无法设断点、调用栈不完整、变量值为空。

---

**方案 B：接入异常跟踪工具（适合生产环境）**

| 工具 | 来源 | 特点 |
|------|------|------|
| **StackTrace.pas** | **项目公共库** (`../common/`) | 自研方案：VEH 异常钩子 + MAPDATA 符号解析 + 局部变量值快照 + 日志输出 |
| **madExcept** | 第三方商业 | 黄金标准，捕获完整调用栈+源码行号，自动写日志/发邮件 |
| **JclDebug** (JEDI) | 第三方开源 | JCL 一部分，编译时嵌入 map 文件符号 |
| **EurekaLog** | 第三方商业 | 功能强大，支持远程上报 |

**推荐优先使用 StackTrace.pas（项目公共库自带）**：

```delphi
// 在项目引入 StackTrace.pas（位于 ../common/ 目录）
// 只需在工程入口处调用 EnableDefaultLogger
uses
  StackTrace;

initialization
  // 一行启用：挂载 VEH 异常钩子 + 从资源加载 MAPDATA 符号表
  TStackTraceManager.Current.EnableDefaultLogger;
  TStackTraceManager.Current.CaptureVariables := True;  // 同时捕获局部变量值
end.
```

启用后效果：
- 程序异常时自动生成日志文件（含完整符号化调用栈 + 源码行号 + 局部变量值）
- AI 直接读取日志文件即可分析根因，无需用户手动操作
 - MAPDATA 通过 `.map` 文件嵌入到 EXE 资源中，无外部依赖
 - **局部变量捕获需额外运行 `daudit --embed`** 命令，将符号表 + 局部变量元数据嵌入 EXE 资源后才能生效

```delphi
// 如需在 except 块中手动触发：
uses
  StackTrace;

var
  Context: TExceptionContext;
begin
  try
    // 可能出错的代码
  except
    on E: Exception do
    begin
      Context := TStackTraceManager.BuildExceptionContext(E, nil);
      // 写入日志文件供 AI 分析
      WriteExceptionLog(Context);
    end;
  end;
end;
```

> **适用场景**：生产环境部署、需要自动抓取 Crashes、无法复现的偶发异常。
> **注意事项**：编译时需生成 `.map` 文件（`Project → Options → Linking → Map file = Detailed`），
> 首次运行会自动将 map 符号嵌入 EXE 资源。madExcept 和 EurekaLog 需单独安装。

### 8.4 人工介入交接清单

申请人工介入时，必须提供以下信息（**缺一不可**）：

```
┌────────────────────────────────────────────────────────────┐
│                   人工介入申请书                             │
├────────────────────────────────────────────────────────────┤
│ [一] 问题摘要                                               │
│   一句话描述问题                                           │
│                                                             │
│ [二] 已尝试的方案（逐条列出）                                │
│   ① 尝试了什么 → 结果如何 → 为什么失败                      │
│   ② ...                                                     │
│   ③ ...                                                     │
│                                                             │
│ [三] 异常现场（见 8.3 模板）                                 │
│   ├─ 完整异常消息 + 调用栈                                  │
│   ├─ 关键变量的值                                          │
│   └─ 复现步骤（从启动到异常的最简路径）                     │
│                                                             │
│ [四] 环境信息                                               │
│   ├─ Daofy 版本、Python 版本、操作系统版本                  │
│   ├─ Delphi 编译器版本                                      │
│   ├─ 项目类型（VCL/FMX/Console）和关键配置                  │
│   └─ 最近变更（与问题相关的代码/配置改动）                  │
│                                                             │
│ [五] 预期结果                                                │
│   你希望人工帮你做什么                                      │
│   例如: "请确认这个 DLL 导出函数签名是否正确"               │
│         "请提供 XXX 组件的授权文件"                         │
│                                                             │
│ [六] 最小复现示例（MRE）                                     │
│   如果能剥离出最小独立复现用例，附上代码                    │
└────────────────────────────────────────────────────────────┘
```

### 8.5 协同工作流

```
  AI Agent                        人工（开发者）
     │                                 │
      │─── 独立尝试解决问题 ──────────→  │  （P0/P1 问题自动触发）
     │                                 │
     │─── 提交介入申请书 ────────────→  │
     │    (按 8.4 清单)                │
     │                                 │
     │←── 人工响应 ──────────────────── │
     │    (定位根因 / 提供信息 /       │
     │     授权访问 / 修正设计)         │
     │                                 │
     │─── 根据人工反馈继续修复 ──────→  │
     │    完成后验证                   │
     │                                 │
     │←── 验收确认 ──────────────────── │
     │    (通过/需要调整)              │
     │                                 │
```

**关键规则**：

1. **AI 必须主动申请介入** — 不要死磕，满足 8.1 任一条件立即触发。浪费时间比"显得无能"更糟糕。
2. **介入申请必须完整** — 缺少 8.4 清单中任何一项，人工可以要求补充后再处理。
3. **人工响应后 AI 继续跟进** — 人工提供了信息/方案后，AI 负责继续执行修复并验证。
4. **经验沉淀** — 问题解决后，使用 `experience(action="save")` 将解决过程保存为经验，
   下次同类问题 AI 可自行解决，无需再申请人工介入。
5. **介入后更新规则** — 如果人工介入揭示了编码规范/流程中的盲区，更新
   `src/resources/coding-rules.md`（MCP Resource: `delphi://coding-rules`），避免同类问题重复介入。

### 8.6 MCP 工具的异常处理约定

| 层级 | 异常处理方式 |
|------|-------------|
| `tools/*.py` handler | 捕获具体异常，返回 `{"error": "..."}` + 附带 `exc_info=True` 日志；不抛出 |
| `server.py call_tool` | 顶层兜底捕获所有异常，格式化为 `CallToolResult(isError=True)` 返回；禁止裸抛 |
| `services/*.py` | 业务异常使用自定义异常类，保留完整调用链；记录日志但**不吞异常** |
| `utils/*.py` | 工具函数内部通常不捕获，让上层统一处理 |

---

### 8.7 假设驱动调试循环（Hypothesis-Driven Debugging）

当面对一个尚未定位根因的问题时，不要跳进"猜测→修改→验证"的随机修复循环。
应采用假设驱动的方式，系统性地缩小范围：

```
┌─ 第①步: 信息采集 ──────────────────────────────┐
│  收集所有可用线索，不预设任何原因                   │
│  ├─ 完整错误消息 + 错误号/异常类型                 │
│  ├─ 调用栈（符号化/非符号化均可）                  │
│  ├─ 环境信息（Delphi版本/OS/平台/配置）             │
│  ├─ 复现步骤（确定能否稳定复现）                   │
│  ├─ 最近变更（git log --oneline -10 检查最近修改） │
│  └─ 查经验库: experience(search, query="...")     │
└──────────────────────────────────────────────────┘
                         ↓
┌─ 第②步: 生成 2~3 个独立假设 ────────────────────┐
│  H1: 假设原因A → 预期应观察到A' → 验证方法V1      │
│  H2: 假设原因B → 预期应观察到B' → 验证方法V2      │
│  H3: 假设原因C → 预期应观察到C' → 验证方法V3      │
│                                                    │
│  假设要求:                                         │
│  ├─ 必须基于第①步的证据，而非凭空猜测              │
│  ├─ 互斥或至少独立（不相互依赖）                   │
│  └─ 按 最易验证 > 最可能成立 排序                  │
└──────────────────────────────────────────────────┘
                         ↓
┌─ 第③步: 并行验证 ──────────────────────────────┐
│  ├─ 互不依赖的假设同时验证                         │
│  ├─ 每个验证用最少操作（最小化代码改动）            │
│  ├─ 编译错误用 compile_file 单文件验证，非全量编译  │
│  └─ 运行时问题用 rget/delphi_rtti 快速验证         │
└──────────────────────────────────────────────────┘
                         ↓
┌─ 第④步: 分析结果 → 决策 ───────────────────────┐
│  ├─ H被证实 → 进入修复                            │
│  ├─ 所有H被证伪 → 回到①采集更多信息或触发介入      │
│  └─ 部分证实 → 调整假设缩小范围，重入循环           │
└──────────────────────────────────────────────────┘

最多 3 轮循环仍无法定位根因 → 触发 §8.1 P0 人工介入。
```

**关键规则**：
1. **禁止零假设修复** — 没有形成假设之前不得修改代码
2. **每次只验证一个假设** — 不要同时做多个改动，否则不知道哪个生效
3. **假设可证伪** — 如果假设无法设计验证方法，说明假设不具体，需要细化
4. **维护调试日志** — 按 §8.10 记录已尝试方案，避免 §8.1 的同质方案重复

---

### 8.8 DCC 编译错误分类与解码

#### 文档知识库搜索（首选方案）

Delphi 官方 CHM 帮助文档（`topics.chm`）包含了全部 DCC 编译器错误/警告/提示的**官方说明**（共约 1278 个 HTML 文件，涵盖 875 个 EXXXX 错误 + 20 个 FXXXX 致命错误 + W/H 系列）。
使用文档知识库搜索 DCC 错误是最精确的方案（无需硬编码所有错误码）：

```
前置条件：文档知识库需从 Delphi CHM 构建（仅需一次）
delphi_kb(action="build", kb_type="document", async_mode=true)
# 自动检测 C:\Program Files\Embarcadero\Studio\<版本>\Help\Doc\ 下的 .chm 文件
# 完成后即可搜索

# 如需强制重建（会清除 KB 中现有所有文档）：
# delphi_kb(action="build", kb_type="document", rebuild=True, confirm=True, async_mode=true)
# ⚠️ rebuild=True 会清除 KB 中已有的全部文档，请先确认旧内容已不需要或已包含在新的文档源中

# 搜索具体 DCC 错误号（返回官方解释+修复建议）
delphi_kb(query="E2003", kb_type="document", search_type="semantic")
delphi_kb(query="E2010 incompatible types", kb_type="document", search_type="semantic")
delphi_kb(query="F2613 unit not found", kb_type="document", search_type="semantic")

# 按主题搜索
delphi_kb(query="Delphi Compiler Errors Index", kb_type="document")
delphi_kb(query="Error and Warning Messages (Delphi)", kb_type="document")
delphi_kb(query="Fatal errors", kb_type="document")
```

> 文档 KB 构建后，任何 `delphi_kb(kb_type="document")` 查询直接返回 DCC 错误码的官方解释，
> 不再需要 AI 凭猜测修复。

#### 错误级别速查

| 级别 | 前缀 | 含义 | 处理策略 |
|------|------|------|---------|
| **Fatal** | Fxxxx | 编译器无法继续，必须先解决 | 先修复路径/配置问题，再处理其他错误 |
| **Error** | Exxxx | 语法/语义错误 | 读错误行源码 → 查文档 KB → 修复 |
| **Warning** | Wxxxx | 潜在问题 | 评估是否影响功能；已知警告（如 W1057）可忽略 |
| **Hint** | Hxxxx | 风格/类型建议 | 仅整理代码时处理，调试阶段可跳过 |

#### 常见 DCC 错误速查表（常用 8 条，完整列表见文档 KB）

| 错误号 | 典型消息 | 常见原因 | 解决方向 |
|--------|---------|---------|---------|
| E2003 | Undeclared identifier: 'X' | 缺 uses 单元 / 拼写错误 | 检查 uses 子句 + 标识符大小写 |
| E2010 | Incompatible types: 'X' and 'Y' | 类型不匹配 | 检查赋值/参数类型，必要时显式转换 |
| E2029 | Statement expected but 'X' found | 语法结构错误 | 检查括号/分号/begin..end 配对 |
| E2037 | Record, object or class type required | 对非对象类型使用 '.' 访问 | 检查变量类型声明 |
| E2066 | Missing operator or semicolon | 前一行漏分号 | 回溯错误行前一行末尾 |
| E2251 | Ambiguous overloaded call to 'X' | 重载函数匹配歧义 | 用显式类型转换消除歧义 |
| E2506 | Unit 'X' not compiled (Y.dcu out of date) | DCU 缓存过期 | 全量编译或删除 .dcu 文件 |
| F2613 | Unit 'X' not found | 搜索路径未包含目标单元 | 检查 DCC_UnitSearchPath / 添加 DCCReference |

#### 编译错误处理流程

```
编译失败
  │
  ├─ ① 分类错误级别
  │   ├─ Fatal → 先处理（通常是路径/配置问题）
  │   ├─ Error → 主要修复目标
  │   └─ 仅 Warning/Hint → 可暂缓
  │
  ├─ ② 单文件 vs 全量
  │   ├─ 增量编译出错 → 先 clean（删 .dcu/.map/.dres）再全量编译
  │   ├─ 错误集中在少量单元 → compile_file 单文件验证
  │   └─ 大量错误 → 从第一个 Error 开始（后续常为连带错误）
  │
  ├─ ③ Error 定位（优先级从高到低）
  │   1️⃣ delphi_kb(query="{错误号}", kb_type="document")  → 查官方解释
  │   2️⃣ delphi_kb(query="{关键词}", kb_type="document")  → 语义搜索
  │   3️⃣ 对照 DCC 速查表 + 读错误行源码上下文
  │   4️⃣ delphi_kb(search_type="function") 查 API 定义
  │   5️⃣ 修复后增量编译验证
  │
  └─ ④ 疑难/重复失败
      ├─ 二分法隔离（见 §8.9）
      ├─ 查经验库：experience(search, query="DCC Exxxx ...")
      └─ 3 次失败 → 转 §8.1 P0 人工介入
```

#### 增量编译缓存问题

- `.dcu`/`.map`/`.dres` 缓存损坏会导致幽灵错误（错误行与实际不符）
- **症状**：修复了错误行但仍报相同错误，或错误指向已删除的代码
- **解决**：删除缓存文件后全量编译
- Windows 上 `.map` 文件在 IDE 打开项目时可能被锁定，先关闭 IDE

---

### 8.9 二分法与隔离调试

当面对大型项目、复杂函数、或难以定位的错误时，不要试图一次性理解所有代码。
用二分法（Binary Search）快速缩小可疑范围：

```
编译错误二分法（文件级）:
  ① 将文件从中间分为上下两半
  ② 用 {$IFDEF DEBUG_SKIP}...{$ENDIF} 注释掉上半部分 → 编译
  ③ 错误消失 → 错误在上半部分；仍在 → 错误在下半部分
  ④ 对包含错误的半部分递归二分，直到定位到具体行

运行时崩溃二分法（代码路径级）:
  ① 确定触发崩溃的最简操作路径
  ② 在调用链的中点插入 Exit / 提前返回
  ③ 崩溃消失 → 问题在后面半段；仍在 → 问题在前面半段
  ④ 递归缩小范围，直到定位到具体函数

多模块隔离（项目级）:
  ① 临时关闭所有编译事件（PreBuild/PostBuild）
  ② 从 dproj 中逐个移除 DCCReference，定位缺少的单元
  ③ 分批注释 uses 子句，定位循环引用
  ④ 关闭 {$DEFINE} 条件编译符号，逐步开启排查

回归定位（变更级）:
  git bisect 是最可靠的回归定位工具：
  ① git bisect start
  ② git bisect bad          # 当前版本有问题
  ③ git bisect good <tag>   # 上一个已知正常版本
  ④ git bisect run <script> # 自动二分编译验证脚本
  ⑤ 定位到引入问题的 commit

  无 git 时：手动记录"最后正常"的时间点，沿 changelog 逐个版本测试。
```

**隔离原则**：
- 每次隔离**只改变一个变量**（注释一个块/禁用一个单元）
- 确认隔离结果后再进行下一步（不要同时做多个改动）
- 二分法的最优复杂度是 O(log N)，不要用线性扫描替代
- 编译错误隔离用 `{$IFDEF}` 而非删除代码，方便恢复

---

### 8.10 调试状态日志

调试过程中，AI Agent **必须维护结构化调试日志**，显式追踪已尝试的方案和结果。
这直接防止 §8.1 人工介入触发条件表中「连续同质方案」(P2 级，第 2 次失败触发)——有了日志，AI 能精确判断当前尝试是否与之前本质不同。

```
[调试日志] <问题摘要>
═══════════════════════════════════════
问题描述: {一句话描述}

已尝试的方案:
  #1: 假设 H1=... → 验证方法=... → 结果=证伪 → 推断=排除原因A
  #2: 假设 H2=... → 验证方法=... → 结果=证实 → 推断=原因B → 已修复
  #3: ...

当前范围:
  已排除: [模块X, 模块Y, 文件Z, ...]
  剩余可疑: [模块W, ...]
  当前最可能假设: {假设描述 + 依据}

下一步计划: {具体要验证的内容}
是否触发人工介入: 是/否（触发原因）
═══════════════════════════════════════
```

**使用规则**：
- 在开始调试任何问题前创建日志
- 每次尝试后更新日志（假设 → 验证 → 结果 → 推断）
- 进入下一轮假设循环前回顾日志，确认新假设与已证伪的假设**本质不同**
- 日志本身不保存到文件，仅作为本轮调试的工作记忆
- 问题解决后日志可丢弃，但经验必须通过 `experience(save)` 持久化

---

### 8.11 调试工具选择决策树

面对不同性质的问题，选择最高效的工具组合：

```
遇到问题
  │
  ├─ 编译错误（DCC 报错）
  │   ├─ ⭐ delphi_project(action="compile") — 全量/增量编译
  │   ├─ ⭐ delphi_project(action="compile", compile_file=...) — 单文件语法检查
  │   ├─ ☆ delphi_file(action="read") — 读错误行源码上下文
  │   ├─ ☆ delphi_kb(query=...) — 查 API 定义确认用法
  │   └─ ☆ experience(search, query="DCC ...") — 查同类编译错误经验
  │
  ├─ 运行时崩溃（Access Violation / 异常弹窗）
  │   ├─ ⭐ 先分类崩溃子类型 → 按 §8.13 对号入座
  │   ├─ ⭐ automate_delphi(cmd="msgscan") — 捕获异常弹窗内容
  │   ├─ ⭐ StackTrace.pas / madExcept — 获取完整符号化调用栈
  │   ├─ ⭐ delphi_rtti(action="discover") — 检查运行时对象状态
  │   ├─ ☆ guide user in IDE (F7/F8/F9) — 人工引导设断点调试
  │   └─ ☆ experience(search, query="...崩溃...") — 查同类崩溃经验
  │
  ├─ 逻辑错误（结果不对 / 界面显示异常）
  │   ├─ ⭐ delphi_file(action="read") — 读源码确认业务逻辑
  │   ├─ ⭐ delphi_kb(query=...) — 确认 API 行为是否符合预期
  │   ├─ ⭐ LSP diagnostics / lsp_symbols — 检查代码符号
  │   ├─ ☆ automate_delphi(cmd="rget") — 读运行时控件属性值
  │   ├─ ☆ automate_delphi(cmd="capture") — 截图视觉对比
  │   └─ ☆ experience(search, query="...")
  │
  └─ 环境问题（路径/版本/配置）
      ├─ ⭐ check_environment(action="check") — 确认编译器状态
      ├─ ⭐ delphi_project(action="info") — 查看 dproj 配置
      ├─ ☆ git diff — 检查最近配置变更
      └─ ☆ experience(search, query="环境 ...")
```

**优先级**：⭐ 首先尝试 → ☆ 备选或辅助

**通用原则**：
- **先查经验库再动手**：`experience(search, query="...")` 可能在 30 秒内给出答案
- **先确认 API 再修代码**：不确定 API 行为时先用 `delphi_kb` 查定义，不凭猜测修改
- **单文件验证优先**：编译错误优先用 `compile_file` 快速验证，不用每次全量编译
- **错误先隔离再分析**：通过 §8.9 二分法缩小范围后，再深入分析具体代码

---

### 8.12 修复后复盘 — 从调试到防御

修复验证通过后，必须执行复盘（Post-Mortem），将本次调试的成果沉淀为长期资产：

```
┌─ 修复后复盘清单 ──────────────────────────────────┐
│                                                      │
│ ① 根因归类                                           │
│    ├─ 编码错误（逻辑缺陷/语法错误）                   │
│    ├─ API 误用（参数错误/生命周期/约定误解）          │
│    ├─ 环境差异（Delphi版本/OS/三方库版本）            │
│    ├─ 并发/时序问题（竞态/死锁/事件顺序）             │
│    └─ 外部依赖变更（API 废弃/行为变化）               │
│                                                      │
│ ② 评估防御措施                                       │
│    ├─ 加 Assert 在开发阶段捕获？                      │
│    │   → 根因是前置条件不满足 → 加 Assert             │
│    ├─ 加日志让下次调试更快？                          │
│    │   → 根因是信息不足导致定位困难 → 加日志          │
│    ├─ 加自动化测试防止回归？                          │
│    │   → 业务逻辑错误 → 加测试用例                    │
│    └─ 更新 CODING_RULES 让所有 AI 受益？              │
│        → 常见模式 → 新增规则（见 §⑫）                │
│                                                      │
│ ③ 经验保存（必须执行）                                │
│    └─ experience(action="save", ...)                  │
│       problem: "{泛化后的问题描述}"                   │
│       solution: "{修复步骤 + 关键代码}"               │
│       tags: ["调试", "{错误类别}", "{模块名}"]        │
│                                                      │
│ ④ 规则联动检查                                       │
│    ├─ 经验被复用 hit_count ≥ 3？                     │
│    │   → 评估是否升级为 CODING_RULES 正式规则        │
│    └─ 本次调试发现了规则盲区？                        │
│        → 按 §⑫ 模板新增/更新规则                    │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**原则**：
- **每个修复都伴随复盘**：修复不只是改代码，更是改进开发流程
- **经验的半衰期是 30 天**：不记录的经验会随时间衰减价值（见 §9.5）
- **规则是经验的固化**：hit_count ≥ 3 的经验应升级为正式规则
- **复盘不是可选项**：这是调试流程的最后一个步骤，不可跳过

---

### 8.13 Delphi 运行时崩溃分类排查

Delphi 运行时崩溃有 4 种截然不同的根因模式，先分类再排查比笼统定位快得多：

#### 类型 A：Access Violation — 接口引用计数问题

**特征**：调用接口方法时 AV，调用对象方法正常。常见于接口引用跨对象传递后原对象被释放。

```
症状: AV 发生在 interface 方法调用链中
调用栈: TMyClass.SomeMethod → [Interface Dispatch] → AV
```

排查步骤：
```
① 确认是否为接口调用：看调用栈中是否经过 Interface Dispatch
② 检查接口引用来源：
   ├─ 是否从已 Free 的对象获取？（对象的 Free 早于接口使用）
   ├─ 接口是否正确实现了 _Release/_AddRef（手工管理时）
   └─ 是否跨线程传递了接口引用？（线程 A 释放了对象但线程 B 仍有接口引用）
③ 修复方案：
   ├─ 确保对象生命周期 ≥ 接口使用周期
   ├─ 或将接口引用提升为全局/所属对象的字段
   └─ 或使用弱引用（weak reference）模式避免循环引用
```

#### 类型 B：Access Violation — TComponent 所有权/生命周期违规

**特征**：访问已释放的 TComponent 派生对象，通常表现为 AV 在 Form 关闭后或析构链中。

```
症状: AV 在 TForm.Destroy 或 TComponent.Notification 中
典型场景: Timer/Socket 事件的回调中访问了 Owner 已释放的组件
```

排查步骤：
```
① 检查 AV 地址对应的源码行（通过 StackTrace.pas 或 madExcept）
② 确认该组件是否已被 Free / Release
③ 检查组件事件的注册/注销是否配对：
   ├─ OnTimer / OnSocketData 等异步事件回调中访问 Self/组件
   ├─ OnNotify / FreeNotification 是否在析构前已注销
   └─ TThread.Synchronize/Queue 回调中访问了已释放的 Form
④ 修复方案：
   ├─ 在 Form.OnDestroy 中注销所有外部事件回调
   ├─ 异步回调中检查 Assigned(Self) / csDestroying flag
   └─ 使用 TComponent.FreeNotification 接收析构通知
```

#### 类型 C：DFM 流式错误 — Class Not Found / Property Error

**特征**：打开 Form 时 IDE 报错误，或运行期间 DFM 流化异常。

```
典型错误:
  "Class TMyFrame not found"        → 缺少 uses 或未 RegisterClass
  "Property Caption does not exist" → DFM 中的属性名拼写或类型不匹配
  "Error reading X: ..."            → DFM 中的二进制数据损坏或版本不兼容
```

排查步骤：
```
① Class Not Found:
   ├─ 确认该单元已加入 uses 子句（检查 implementation 和 interface 两处）
   ├─ 自定义 Frame/Component 需在 initialization 中调用 RegisterClass
   └─ 检查 DFM 中的类名与 PAS 中的类名是否一致（大小写敏感！）
② Property Error:
   ├─ 对照 DFM 中出错属性和 PAS 类声明，检查属性名/类型是否匹配
   ├─ published 区域是否声明了该属性
   └─ 检查 DFM 中的对象类名是否与 PAS 一致（有时 IDE 会写错继承链）
③ DFM 文件损坏：
   ├─ 尝试另存为文本 DFM（Form → Right Click → Text DFM）再恢复
   ├─ 或从 __history/ 备份恢复
   └─ 运行期间错误 → 检查 TReader/TWriter 的自定义序列化逻辑
```

#### 类型 D：包/动态库加载错误

**特征**：启动或加载 BPL/DLL 时报错。

```
典型错误:
  "Cannot load package XXX"            → BPL 不在搜索路径或版本不匹配
  "The procedure entry point YYY..."   → 导出函数签名不匹配
  "Module not found" / "DLL not found" → 依赖 DLL 缺失
  "Runtime error 216/217"              → 初始化异常或依赖未就绪
```

排查步骤：
```
① 包加载错误:
   ├─ check_environment(action="check") — 确认 BPL 路径包含在系统 PATH
   ├─ delphi_project(action="info") — 检查 RuntimePackages 配置
   ├─ 确认所有依赖包已编译且版本匹配（build number + compiler version）
   └─ requires 链中是否存在循环依赖
② Entry Point Not Found:
   ├─ 导出函数名拼写/C 调用约定是否匹配
   ├─ Delphi 包 → 检查 exports 子句
   └─ 编译版本不一致（Delphi 11 的 BPL 不能在 Delphi 12 加载）
③ Runtime error 216/217（常见于 DPK 初始化和 DLL 加载）:
   ├─ Runtime error 216 = Access Violation（初始化顺序问题）
   ├─ Runtime error 217 = 未处理异常（单元 initialization 中抛异常）
   ├─ 检查所有单元的 initialization/finalization 是否异常
   └─ 从 __history/ 中回溯最近修改的单元
```

#### 崩溃分类决策树

```
运行时崩溃
  ├─ 异常类型明确 → 按匹配类型直接跳到对应 A/B/C/D
  ├─ 调用栈经过 Interface Dispatch → 走 A
  ├─ 调用栈在 TComponent.Notification 或 Form 析构中 → 走 B
  ├─ 错误含 "Class ... not found" 或 "Property ..." → 走 C
  ├─ 错误含 "Cannot load package" / "entry point" / "216" / "217" → 走 D
  └─ 无法分类 → 走通用排查（StackTrace.pas 获取完整调用栈后重分类）
```

---

### 8.14 尝试升级检查点（Attempt Escalation Checkpoints）

§8.1 用「3 次失败」一刀切触发人工介入，但缺少半程检查。本节定义**每次尝试后的检查点**，确保 3 次失败前有合理的换档机制：

#### 第 1 次尝试失败

```
┌─ □ 检查点 1 ──────────────────────────────────────────┐
│  ① 确认方案与上一个失败方案是否本质不同                  │
│     → 如果只是换参数/换顺序再试 → §8.1 P2「同质方案」→ 立即换方向 │
│                                                          │
│  ② 检查是否用对了工具                                    │
│     → 参考 §8.11 决策树，当前问题类别对应 ⭐ 工具用了没有？ │
│                                                          │
│  ③ 创建结构化调试日志（§8.10）                           │
│     → 记录: 假设→验证方法→失败结果→排除的内容              │
│                                                          │
│  ④ 更新假设                                              │
│     → 根据失败结果调整假设，生成新的验证方案               │
└──────────────────────────────────────────────────────────┘
```

#### 第 2 次尝试失败

```
┌─ □ 检查点 2 ──────────────────────────────────────────┐
│  ① 查经验库（必须有）                                   │
│     → experience(search, query="{问题关键词} {错误类型}") │
│     → 如找到匹配经验 → 直接应用，无需重造轮子            │
│                                                          │
│  ② 二分法隔离评估                                       │
│     → 是否可以用 §8.9 二分法缩小范围？                    │
│     → 编译问题 → 文件级/代码行级二分                      │
│     → 运行时问题 → 调用链二分                             │
│     → 如果之前未尝试二分法 → 这是最佳时机                  │
│                                                          │
│  ③ 尝试不同工具或不同方法                                │
│     → 同一个工具连续失败 2 次 → §8.1 P2「同工具2次」→ 换工具 │
│     → 编译问题: 全量→单文件→语法检查→手动审查             │
│     → 运行时: msgscan→StackTrace→RTTI→人工引导            │
│                                                          │
│  ④ 更新调试日志                                         │
│     → 更新已排除范围 / 剩余可疑 / 当前假设                │
└──────────────────────────────────────────────────────────┘
```

#### 第 3 次尝试失败（触发介入前）

```
┌─ □ 检查点 3 — 触发人工介入前置检查 ───────────────────┐
│  ① 调试日志完整性检查                                    │
│     → 确保日志包含: 问题描述 / 所有尝试记录 / 已排除范围   │
│                                                          │
│  ② 经验搜索已执行                                        │
│     → 确认已经查过经验库，结果已记录在调试日志中           │
│                                                          │
│  ③ 异常现场信息完整                                      │
│     → 按 §8.3 模板确保异常消息/调用栈/环境信息已采集       │
│     → 错误消息不完整？先追踪补充，不跳过                  │
│                                                          │
│  ④ 二分法已被尝试                                        │
│     → 如果问题适合二分法隔离但未尝试 → 强制先做二分法      │
│     → 不做二分法直接介入 → 人工可以退回（浪费介入资源）    │
│                                                          │
│  ⑤ 构建人工介入申请书                                    │
│     → 按 §8.4 清单逐项填写                               │
│     → 包含最小复现示例（MRE）或至少精确复现步骤            │
│                                                          │
│  ✅ 以上全部满足 → 提交介入申请                           │
│  ❌ 任何一项不满足 → 回到对应步骤补齐后再申请              │
└──────────────────────────────────────────────────────────┘
```

#### 升级流程总图

```
尝试 #1 失败
  │
  ├─ 同质方案？→ 立即换方向（不浪费 #2）
  │
  └─ 检查点 1 → 更新日志 → 更新假设 → 进入 #2
         │
尝试 #2 失败
  │
  ├─ 查经验库 + 二分法评估
  ├─ 换工具？→ §8.1 同工具2次规则
  │
  └─ 检查点 2 → 更新日志 → 换方向 → 进入 #3
         │
尝试 #3 失败
  │
  └─ 检查点 3（介入前置检查）
      ├─ 通过 → §8.4 申请人工介入
      └─ 不通过 → 补齐后重试（不消耗 #4 计数）
```

**关键规则**：
- 第 1 次和第 2 次之间必须**换方向**（不同假设/不同工具/不同方法）
- 第 2 次和第 3 次之间必须**查经验库 + 评估二分法**
- 如果任何检查点发现「同质方案」→ **立即**触发 P2 换方向，不等到满 3 次
- 严格区分「尝试计数」和「方案计数」：换 3 个不同方法各失败 1 次 = 3 次不同方案（可继续尝试），同一方案改参数试 3 次 = 1 种方案 3 次同质尝试（必须换方向）

---

## ⑪ 经验保存 — 将知识沉淀到经验知识库

### 概述

`experience` 工具将 AI Agent 解决问题的有效方法持久化到 Daofy 的经验知识库中，
下次遇到同类问题时 AI 可直接复用，无需重新探索或请求人工介入。

经验库基于语义向量检索，支持自动去重（相似度 > 0.85 时合并到旧记录）。

### 9.1 哪些场景必须保存经验

| 场景 | 说明 | 优先级 |
|------|------|--------|
| 人工介入解决后 | 见 8.5 关键规则④，问题解决后立即保存 | 🔴 必须 |
| 非显而易见的 Bug 修复 | 根因不直观、排查过程曲折的修复 | 🔴 必须 |
| 编译器/工具链兼容问题 | 特定 Delphi 版本、第三方库的特殊处理 | 🟡 推荐 |
| 不常见的 API 用法 | 官方文档未覆盖的边缘用法、参数组合 | 🟡 推荐 |
| 新的编码规则触发 | 导致新增规则的问题，同时保存经验和规则 | 🟡 推荐 |

### 9.2 保存流程（搜索 → 泛化 → 保存）

```
步骤 ① 搜索是否已有同类经验
        └─ experience(action="search", query="...", tags=...)
        结果: 已有 → 跳到步骤 ③ 合并/更新
              无   → 跳到步骤 ②

步骤 ② 泛化问题描述
        └─ 抽象出通用场景，而非具体文件名/变量名
        正例: "MSBuild 编译时 UI 项目报 EAccessViolation，因 dproj 中 CFG 条件为空"
        反例: "Project1.dproj 编译报错，第 42 行"

步骤 ③ 保存/合并
        └─ 无重复 → experience(action="save", problem=..., solution=..., tags=...)
        已有重复 → experience(action="update", id=..., ...)
        多条相关 → experience(action="merge", ids=[...], ...)

步骤 ④ 重建向量（可选，模型后加载时自动补全）
        └─ 自动: 模型加载后首次 search() 无结果时自动触发
        └─ 手动: experience(action="rebuild_embedding")
        说明: 若首次使用时 embedding 模型未加载，保存的记录缺少向量。
        调用 delphi_kb(action=build_embedding) 加载模型后，首次语义搜索
        会自动为所有 WHERE embedding IS NULL 的记录补生成向量后重试。

步骤 ⑤ 验证
        └─ experience(action="search", query="...") 确认能语义召回
```

`experience(action="save")` 不是简单 INSERT，而是"先查再决定"的智能流程：

```
save(problem, solution)
  │
  ├─ embedding 语义搜索相似记录
  │   │
  │   ├─ similarity > 0.85 ──→ 自动合并到旧记录（不新增）
  │   │   ├─ solution: 旧方案 + 新方案 拼接
  │   │   ├─ tags: 去重合并
  │   │   ├─ tools_used: 去重合并
  │   │   ├─ score: +0.05（不超过 1.0）
  │   │   └─ hit_count: 不变
  │   │
  │   ├─ similarity > 0.7（非 force 模式）──→ 拦截 + 提示
  │   │     返回相似记录列表，建议 AI 用 merge/update 人工合并
  │   │     传 force=true 跳过此检查直接保存
  │   │
  │   └─ similarity ≤ 0.7 ──→ 新建记录 ✅
  │
  └─ embedding 不可用 ──→ 直接新建（无去重，降级为 LIKE 搜索）
```

**设计意图**：

| 阈值 | 含义 | 处理方式 |
|------|------|---------|
| > 0.85 | 几乎同一问题 | 自动合并，零摩擦 |
| > 0.7 | 可能相关 | 提醒 AI 人工判断 |
| ≤ 0.7 | 不同问题 | 正常新建 |

### 9.3 保存示例

```python
# 保存经验
experience(
    action="save",
    problem="MSBuild 编译 UI 项目中途失败，退出码非零，因 dproj 配置条件为空字符串导致 DCC_Define 无效",
    solution="""1. 检查 dproj 中 <PropertyGroup Condition="'$(CFG)'!=''"> 是否匹配实际配置名称
2. 确保条件字符串非空，如 Condition="'$(CFG)'=='Debug|Win32'"
3. 清理 .dcu 缓存后重编译""",
    tags=["编译", "MSBuild", "dproj", "CFG条件"],
)

# 搜索已有经验
experience(
    action="search",
    query="MSBuild 编译失败 DCC_Define 条件",
    tags=["编译"],
)

# 合并多条同类经验为一条抽象经验
experience(
    action="merge",
    ids=["exp_id_1", "exp_id_2"],
)

# 清理低价值经验
experience(
    action="prune",
    limit=20,  # 列出 20 条最低价值经验
)
```

### 9.4 经验质量规范

| 维度 | 要求 | 反例 |
|------|------|------|
| **problem** | 概括通用场景，含关键触发条件 | `Form1 报错`（过于具体） |
| **solution** | 步骤化，可复现，含命令/代码 | `改一下配置就行`（模糊） |
| **tags** | 3~5 个标签，覆盖不同搜索角度 | `["bug"]`（太宽泛） |
| **泛化** | 剥离项目/文件级具体名称 | 用 `{项目名}` 替代 `Project1.dproj` |

### 9.5 定期维护

#### 9.5.1 prune — 清理低价值经验

`experience(action="prune")` 按价值分数升序列出候选删除条目，供 AI 人工判断后 `delete`。

**价值计算公式**：

```
value = hit_count × score × time_decay
```

- `hit_count`: 被查看/复用次数（越高越有价值）
- `score`: 质量评分（越高越有价值）
- `time_decay`: 超过 30 天未更新，按半衰期衰减（每 30 天 × 0.5）

**典型低价值模式**：

| 模式 | 说明 | 处理 |
|------|------|------|
| hit_count=1 且长期未更新 | 存了从未用过 | 考虑删除 |
| 内容过于具体 | 可泛化为更抽象的经验 | 合并到抽象经验后删除 |
| 已被其他经验覆盖 | 描述同一问题的冗余记录 | 保留最佳，删除其余 |

#### 9.5.2 merge — 合并同类经验

当多条经验描述同一类问题时，用 `merge` 合并为一条抽象经验，`tags` 覆盖各类场景。

```python
# 合并到目标记录（保留目标，删除其余）
experience(action="merge",
    ids=["exp_id_1", "exp_id_2", "exp_id_3"],
    keep="exp_id_1")

# 合并为新记录（全部删除，新建）
experience(action="merge",
    ids=["exp_id_1", "exp_id_2"])
```

**合并规则**：problem/solution 拼接、tags/tools_used 去重、hit_count 累加。

#### 9.5.3 经验维护最佳实践

| 时机 | 实践 | 说明 |
|------|------|------|
| 保存前 | **先泛化** | 调用 `search(query=...)` 确认是否已有同类经验；找到后用 `merge`/`update` 合并，不另存具体场景 |
| 任务完成 | **主动合并** | 如果刚解决的方案与已有经验相关但方式不同，手动 merge 避免各自独立 |
| 定期 | **清理 prune** | 每月执行 `prune` 列出低价值记录，审查后 `delete`；保持经验库精炼 |
| 发现重复 | **抽象合并** | 多条经验描述同类问题（如不同工具的「消息精简」），合并为一条抽象经验，`tags` 覆盖各类场景 |

#### 9.5.4 规则联动

经验被反复 hit 3 次以上的问题，应考虑升级为内置编码规则资源中的正式规则，让所有 AI Agent 都能受益，而非依赖经验召回。

```
hit_count ≥ 3 的经验 → 评估是否可规则化 → 更新 src/resources/coding-rules.md → 保留经验作为参考用例
```

---

### 9.6 Embedding 降级策略

经验库在没有向量模型时也完全可用，只是搜索精度降低。降级流程：

```
search(query)
  │
  ├─ embedding 模型已加载？
  │   ├─ 是 → 语义搜索（余弦相似度排序）
  │   │      └─ 无结果？→ 自动 rebuild_embeddings() 后重试
  │   └─ 否 → LIKE 关键词降级搜索（%query%）
  │
  └─ 结果返回
```

**关键点**：

- **模型未加载**：`save()` 不保存 embedding（BLOB 为 NULL），`search()` 用 LIKE 降级
- **模型后加载**：调用 `delphi_kb(action=build_embedding)` 后，首次 `search()` 自动触发生成缺失向量
- **rebuild_embedding**：也可手动调用 `experience(action="rebuild_embedding")` 为所有 `embedding IS NULL` 的记录补向量
- **降级是完全透明的**：上层无需关心当前使用哪种搜索模式

---

### 9.7 质量保障体系

| 保障机制 | 层级 | 说明 |
|----------|------|------|
| 自动去重合并 | save() | similarity > 0.85 自动合并，> 0.7 拦截提醒 |
| 自动重建向量 | search() | 模型已加载但无结果时自动触发 |
| 时间衰减 | prune() | 30 天未更新的经验价值按半衰期衰减 |
| 使用计数 | get() | 每次查看递增 hit_count |
| 超时保护 | server.py | 30 秒超时，防止 embedding 加载阻塞 MCP |
| 线程安全 | 连接层 | 每线程独立 SQLite 连接，WAL 模式防锁 |

> 经验库的唯一标识是 ID（短 UUID），不可手动修改。所有管理操作都通过 experience 工具进行，禁止直接操作 SQLite 文件。

---

## ⑫ 规则维护
修复 bug 后总结为规则加到项目规则文件。添加前检查是否已有相同规则。修改后更新顶部日期版本号。

### 新增规则模板
```markdown
#### [类别] [标题]
- **问题**：此规则要防范什么问题
- **规则**：具体的约束或做法
- **正例**：```delphi {符合规则的代码} ```
- **反例**：```delphi {违反规则的代码} ```
```
示例：
```markdown
#### 常见错误模式 空 except 块
- **问题**：空的 `except...end` 会吞噬所有异常，导致错误被静默忽略
- **规则**：`except` 块内必须至少记录日志并重新抛出，或做有意义的处理
- **正例**：`except on E: Exception do Logger.Error(E); raise; end;`
- **反例**：`except end;`
```
