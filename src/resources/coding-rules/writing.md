<!-- @when: 写 Delphi 代码前，确认编码/命名/格式规范 -->
<!-- @chain: before=delphi-file-rules.md, after=workflow.md -->

## ③ 写 Delphi 代码

**卡点入口**：遇到错误、方案不确定、反复试同一方案 → 先查 ⑩ 前置自检。

### 文件编码（修改前必做）
- 修改前先确认文件编码，避免中文乱码
- ⭐ 优先用 `delphi_file(action="read", file_path=...)`（自动检测编码/BOM/GBK）
- 写回时保持原始编码；新建文件统一 `utf-8-sig`（UTF-8 with BOM，消除 W1057 警告）
- 含 BOM 的文件保留 BOM

### 自动备份
- `delphi_file(action="write", backup=True)` 默认自动备份到 `__history/`
- ❌ 禁止直接用 edit/write/shell/Python 修改 `.pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx`
- 手动操作：
  ```python
  delphi_file(action="backup", file_path="src/Unit1.pas")                                # 手动备份
  delphi_file(action="backup", backup_action="list", file_path="src/Unit1.pas")          # 列出版本
  delphi_file(action="backup", backup_action="restore", file_path="src/Unit1.pas", version=3)
  ```

### 命名规则
| 类别 | 约定 | 示例 |
|------|------|------|
| 类/接口/异常 | T/I/E/P 前缀 | `TMyClass`, `IMyInterface` |
| 字段 | F 前缀 | `FName: string;` |
| 属性/方法 | 大驼峰 | `property Name` / `procedure CalculateTotal` |
| 事件 | On→Form 后缀 | `Form1Create` |
| 参数 | A 前缀 | `procedure SetName(AName: string);` |
| 枚举 | 类型前缀缩写 | `taLeft, taRight, taCenter` |
| 常量 | 全大写 | `MAX_BUFFER_SIZE` |

### 格式
- 缩进 2 空格，行宽 ≤120
- `begin` 独占一行；运算符/逗号后加空格，括号内侧不加
- `uses` 分组 + 组尾注释 + 组内字母序

### 泛型
- 描述性参数名 `TKey, TValue`；多约束 `where` 一行一条
- 嵌套 ≥3 层用 type alias：`type TStringArrayList = TArray<TList<string>>`

### 运算符重载
- 仅对 record 定义；语义须符合直觉
- 定义 `Implicit`/`Explicit` 时同时提供命名转换方法

### 异步与多线程
- UI 控件访问须主线程同步；共享资源加锁
- 任务取消/失败时清理资源；避免异步回调直接引用对象

### 代码组织
- 单元 ≤500 行，单一职责
- `interface`：uses → 类型 → 常量 → 变量 → 声明
- `implementation`：uses → 辅助函数 → 接口实现

### 版本兼容
- 跨版本差异用条件编译包裹并标注版本号
- 用新版 API 时提供旧版本回退实现
