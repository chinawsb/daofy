<!-- @title: Lazarus/FPC 工作流总览 -->
<!-- @purpose: Lazarus 项目从环境检查到交付的完整闭环 -->

## Lazarus/FPC 工作流总览

完整闭环：环境检查 → 查 API → 编码 → 编译 → 审核 → 清理

### ① 环境检查
```powershell
# 确认 lazbuild.exe / fpc.exe 可用
check_environment(action="check")
```
环境检测自动发现 Lazarus 安装路径。如未安装，从 [lazarus-ide.org](https://www.lazarus-ide.org/) 下载。

### ② 查 API（FPC 文档）
FPC 标准库文档可查阅 Free Pascal 官方文档或通过知识库搜索：
```
lazarus_kb(action="search", query="TStringList")
```

### ③ 编码
Free Pascal 编码规范要点：
- 命名: `PascalCase` 类型/类, `camelCase` 变量/函数, `UPPER_CASE` 常量
- Uses 子句按标准分组：`SysUtils, Classes` 等为标准单元
- FPC 模式使用 `{$mode objfpc}` 或 `{$mode delphi}`
- 跨平台注意 `{$IFDEF WINDOWS}` / `{$IFDEF UNIX}` 条件编译
- `string` 类型在 Free Pascal 中默认为 `ShortString`，显式声明 `AnsiString` 或 `UnicodeString`
- 动态数组使用 `TArray<Integer>` 或 `array of Integer`
- 异常处理使用 `try...except...end` 和 `try...finally...end`

### ④ 编译
```
lazarus_compile(project_path="project.lpi", target_platform="win32")
```
- `.lpi` 为 Lazarus 项目文件（XML），`.lpr` 为主源文件（程序入口）
- 编译模式: `build_configuration` 支持 `Default`/`Release`/`Debug`
- 目标平台: `win32` / `win64`

编译完成后检查 `result.status`：
- `success`: 输出产物在项目输出目录
- `failed`: 查看 `result.error` 获取错误详情

### ⑤ 审核
代码审核重点：
- 类型安全: 避免无类型指针和强制类型转换
- 内存管理: 对象使用 `Free`/`FreeAndNil`，接口自动引用计数
- 跨平台: 检查平台相关的条件编译
- FPC 兼容性: 检查使用了 Delphi 特有语法（如 `with` 语句慎用）

### ⑥ 清理
- 删除调试临时文件
- 确认编译产物路径
