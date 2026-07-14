# Delphi Project — 项目全生命周期管理

> 版本：v1.2 | 最后更新：2026-07-10

---

## 目录

1. [概述](#1-概述)
2. [Action 速查](#2-action-速查)
3. [编译相关](#3-编译相关)
4. [配置管理](#4-配置管理)
5. [代码审计](#5-代码审计)
6. [工作流场景](#6-工作流场景)
7. [编译失败排查](#7-编译失败排查)
8. [技术架构](#8-技术架构)
9. [故障排除](#9-故障排除)

---

## 1. 概述

`delphi_project` 是 Daofy 中最核心的工具，提供 Delphi 项目的**全生命周期管理**——从创建项目、配置编译选项、执行编译，到代码审计。它合并了原有的 `compile_project`、`dproj_tool`、`run_audit` 三个工具的功能。

**一句话**：所有 Delphi 项目的编译、配置、审计操作都通过此工具完成。

| 功能域 | 涵盖 |
|--------|------|
| **编译** | `.dproj`/`.dpr`/`.dpk` 项目编译、.pas 语法检查、参数预览 |
| **配置** | 读取/创建/修改 `.dproj` 配置、增删源文件、增删编译配置 |
| **审计** | AST 骨架提取、50+ 静态分析规则、运行时注册检查、DFM UI 布局审计 |

### 硬约束

> ❌ **不得用 bash/cmd 运行 dcc32/msbuild**（绕过 MSBuild 事件处理和依赖解析）

---

## 2. Action 速查

| Action | 用途 | 必需参数 |
|--------|------|---------|
| `compile` | 编译 .dproj/.dpr/.dpk 项目 | `project_path` |
| `compile_file` | 检查 .pas 文件语法 | `project_path` |
| `dry_run` | 预览编译参数，不执行 | — |
| `info` | 读取 .dproj 完整信息 | `project_path` |
| `create` | 创建新 .dproj 文件 | `project_path`, `main_source` |
| `set` | 设置 .dproj 属性值 | `project_path`, `property_name`, `value` |
| `add_config` | 添加编译配置 | `project_path`, `config_name` |
| `remove_config` | 删除编译配置 | `project_path`, `config_name` |
| `add_source` | 添加源文件引用 | `project_path`, `source_file` |
| `remove_source` | 删除源文件引用 | `project_path`, `source_file` |
| `audit` | 运行 50+ 静态分析规则 | — |
| `ast` | ⭐ 代码骨架提取（最省 token） | `base_dir` |
| `runtime` | 运行时注册检查 | — |
| `layout` | 静态 DFM UI 布局审计 | `base_dir` 或 `file_path` |

---

## 3. 编译相关

### 3.1 `compile` — 编译项目

编译 `.dproj`/`.dpr`/`.dpk` 项目。自动检测编译器版本和依赖路径。

```python
# 最简调用 — 自动检测项目类型和配置
delphi_project(action="compile", project_path="Project.dproj")

# 带参数的完整编译
delphi_project(action="compile",
    project_path="App.dproj",
    build_configuration="Release",
    target_platform="win64",
    conditional_defines=["RELEASE", "MY_FEATURE"],
    unit_search_paths=["C:\Libs\Common", "..\Shared"],
    optimize=True,
    debug=False,
    extra_args=["/p:DCC_DebugInfoInTds=true", "/p:DCC_RemoteDebug=true"],
    output_path=".\Build\Release")
```

**参数说明**：

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `project_path` | ✅ | — | .dproj/.dpr/.dpk/.pas 路径 |
| `target_platform` | ❌ | win32 | win32/win64/osx64/... |
| `build_configuration` | ❌ | Debug | Debug/Release |
| `compiler_version` | ❌ | 自动检测最新 | 指定 Delphi 版本 |
| `conditional_defines` | ❌ | — | 条件编译符号数组 |
| `unit_search_paths` | ❌ | — | 额外单元搜索路径 |
| `resource_search_paths` | ❌ | — | 资源搜索路径 |
| `optimize` | ❌ | true | 是否启用优化 |
| `debug` | ❌ | true | 是否生成调试信息 |
| `warning_level` | ❌ | 2 | 警告级别 0-4 |
| `disabled_warnings` | ❌ | — | 禁用警告编号数组 |
| `output_type` | ❌ | gui | gui/console/dll |
| `runtime_library` | ❌ | static | static/dynamic |
| `timeout` | ❌ | 600 | 超时秒数 |
| `auto_install` | ❌ | true | 仅 .dpk：是否自动安装到 IDE |
| `run_verify` | ❌ | false | 编译后启动 3 秒验证是否崩溃 |
| `output_path` | ❌ | — | 编译输出目录 |
| `extra_args` | ❌ | — | 附加到实际编译后端的完整参数数组 |

#### 附加编译参数

`extra_args` 中每个元素必须是一个完整参数。Daofy 会在内建参数之后追加这些参数，并按实际后端解释：

```python
# .dproj 或存在同名 .dproj 的 .dpr：走 MSBuild，请求生成 TDS/RSM 调试符号
delphi_project(action="compile",
    project_path="Project.dproj",
    extra_args=["/p:DCC_DebugInfoInTds=true", "/p:DCC_RemoteDebug=true"])

# 没有同名 .dproj 的 .dpr：直接走 DCC
delphi_project(action="compile",
    project_path="Project.dpr",
    extra_args=["-VT", "-VR"])
```

如果编译器生成了 `.tds`、`.rsm` 文件，它们会列入编译结果的 `output_files`。不要在数组元素中自行添加外层引号；包含空格的单个参数仍作为一个数组元素传入。

#### 编译事件

`.dproj` 中的 `PreBuildEvent`/`PostBuildEvent`/`PreLinkEvent` 会自动执行，无需手动处理。

#### `run_verify` — 崩溃检测

编译成功后自动启动 exe 运行 3 秒，若进程崩溃则标记验证失败。检测到 `exception.log` 时自动读取内容嵌入响应。

### 3.2 `compile_file` — 语法检查

编译单个 .pas 文件进行语法检查，不生成可执行文件。

```python
delphi_project(action="compile_file", project_path="Unit1.pas")

# 带搜索路径
delphi_project(action="compile_file",
    project_path="Unit1.pas",
    unit_search_paths=["..\Shared"],
    conditional_defines=["TEST"])
```

### 3.3 `dry_run` — 预览编译参数

不实际执行编译，只显示将要使用的编译器路径和完整命令行参数。

```python
delphi_project(action="dry_run", project_path="Project.dproj", build_configuration="Release")
```

---

## 4. 配置管理

### 4.1 `info` — 读取项目信息

读取 `.dproj` 文件的完整结构化信息：编译配置、源文件列表、资源文件、编译事件等。

```python
delphi_project(action="info", project_path="Project.dproj")
```

### 4.2 `create` — 创建项目

创建新的 `.dproj` 项目文件，可选同时生成 Form 桩代码。

```python
# 最简创建
delphi_project(action="create",
    project_path="MyApp.dproj",
    main_source="MyApp.dpr")

# 带 Form 桩代码
delphi_project(action="create",
    project_path="MyApp.dproj",
    main_source="MyApp.dpr",
    framework_type="VCL",
    form_units=["Unit1", "MainForm"],
    configs=["Debug", "Release", "Staging"])
```

**参数说明**：

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `project_path` | ✅ | — | 项目文件路径 |
| `main_source` | ✅ | — | 主源文件（.dpr） |
| `project_guid` | ❌ | 自动生成 | 项目 GUID |
| `framework_type` | ❌ | VCL | VCL/FMX |
| `unit_search_paths` | ❌ | — | 初始搜索路径 |
| `namespace` | ❌ | — | 命名空间 |
| `configs` | ❌ | ['Debug','Release'] | 编译配置列表 |
| `sources` | ❌ | — | 初始源文件列表 |
| `form_units` | ❌ | — | 同时生成 Form 桩代码 |

### 4.3 `set` — 修改属性

修改 `.dproj` 中的属性值（PropertyGroup），可指定配置和平台。

```python
# 设置条件编译符号
delphi_project(action="set",
    project_path="Project.dproj",
    property_name="DCC_Define",
    value="DEBUG;TEST",
    config="Debug",
    platform="Win32")
```

### 4.4 `add_config` / `remove_config` — 编译配置管理

```python
# 从现有配置复制创建 Staging 配置
delphi_project(action="add_config",
    project_path="Project.dproj",
    config_name="Staging",
    base_config="Debug",
    defines=["STAGING"],
    optimize=True)

# 删除配置
delphi_project(action="remove_config",
    project_path="Project.dproj",
    config_name="Staging")
```

### 4.5 `add_source` / `remove_source` — 源文件管理

```python
# 添加源文件到项目
delphi_project(action="add_source",
    project_path="Project.dproj",
    source_file="Unit1.pas")

# 添加为主源文件
delphi_project(action="add_source",
    project_path="Project.dproj",
    source_file="MyApp.dpr",
    main_source_flag=True)

# 删除源文件
delphi_project(action="remove_source",
    project_path="Project.dproj",
    source_file="Unit1.pas")
```

---

## 5. 代码审计

### 5.1 `ast` — 代码骨架提取（推荐）

⭐ **最省 token 的方式**，快速了解代码结构。使用 `daudit --mode skeleton --compact` 提取类、方法、字段等骨架信息。

```python
# 提取整个项目的代码骨架
delphi_project(action="ast", base_dir="src")

# 提取单个文件的骨架
delphi_project(action="ast", file_path="Unit1.pas")
```

### 5.2 `audit` — 静态分析

运行 50+ 条静态分析规则，覆盖安全、资源泄漏、代码质量等维度。

```python
# 全量审计
delphi_project(action="audit", base_dir="src")

# 单文件指定严重级别
delphi_project(action="audit",
    file_path="Unit1.pas",
    rules="P0",
    severity="warning",
    output_format="report")
```

**参数说明**：

| 参数 | 说明 |
|------|------|
| `base_dir` | 审计基准目录 |
| `file_path` | 单文件审计 |
| `rules` | 规则集 P0/P1，默认 P0 |
| `severity` | 最低严重级别：suggestion/warning/critical |
| `output_format` | report/json，默认 report |

### 5.3 `runtime` — 运行时注册检查

扫描 `.pas`/`.dfm` 中组件类名，匹配 `runtime_registry.json` 规则表，检测是否遗漏必需 uses 单元。独立于编译步骤，纯源码级分析。

```python
delphi_project(action="runtime", base_dir="src")
```

### 5.4 `layout` — UI 布局审计

扫描 `.dfm` 控件坐标和属性，检测 AI 生成界面常见的布局问题：控件重叠、越界、同列 Left 不一致、垂直间距不一致、文本标签与字段未对齐、文本标签-字段间距异常、TabOrder 与视觉顺序不一致，以及可调整大小的父容器使用绝对坐标却未设置足够的最小尺寸。审计基于几何关系和 DFM 属性推断，不依赖固定控件类型名单。

```python
delphi_project(action="layout", base_dir="src")
delphi_project(action="layout", file_path="MainForm.dfm", output_format="json")
```

`layout` 不需要 daudit；二进制 DFM 会尽量临时转换为文本，不修改原文件。静态审计通过后，再用 `automate_delphi` 做运行时 BoundsRect、截图和跨 DPI 验证。

---

## 6. 工作流场景

### 日常编译

```
delphi_project(action="compile", project_path="Project.dproj")
  ↓ 成功 → 完成
  ↓ 失败 → check_environment(action="check")
          → 调整参数 → 重新 compile
```

### 创建新项目

```
delphi_project(action="create", project_path="NewApp.dproj", main_source="NewApp.dpr", form_units=["MainForm"])
  ↓
delphi_project(action="info", project_path="NewApp.dproj")          # 确认配置
  ↓
delphi_project(action="compile", project_path="NewApp.dproj")       # 验证可编译
```

### 代码审计流程

```
delphi_project(action="ast", base_dir="src")                         # 了解代码结构
  ↓
delphi_file(action="read", ...)                                # 查看具体文件
  ↓
delphi_project(action="audit", base_dir="src")                        # 运行静态分析
  ↓
AI 解读结果 → 排除误报 → 生成修复建议
  ↓
delphi_file(action="write", ...) → delphi_project(action="compile")  # 修复后验证编译
```

### 修改编译配置

```
delphi_project(action="set", property_name="DCC_Define", value="RELEASE", config="Release")
  ↓
delphi_project(action="compile", project_path="Project.dproj", build_configuration="Release")  # 验证
```

---

## 7. 编译失败排查

```
失败 → check_environment(action="check") 确认编译器状态
    → 检查是否缺少搜索路径（dproj 中 DCC_UnitSearchPath 配置）
    → dproj 中的 DCC_UnitSearchPath 是否包含需要的三方库路径
    → 确认目标平台（win32/win64）编译器可用
    → 条件编译符号是否匹配（DEBUG/RELEASE）
    → 3 次修复失败 → 申请人工介入（见 CODING_RULES 8.1）
```

### 常见编译错误

| 错误现象 | 可能原因 | 解决 |
|---------|---------|------|
| `Fatal: Unable to execute file` | 编译器路径错误 | `check_environment(action="detect")` 重新检测 |
| `Fatal: File not found: xxx.dcu` | 缺少搜索路径 | 补充 `unit_search_paths` 参数 |
| `E1026 File not found: xxx.dproj` | 项目路径错误 | 确认 `project_path` 的正确性 |
| Exit code 2 | 编译事件失败或语法错误 | 查看详细输出定位错误行 |
| 运行验证崩溃 | `run_verify=true` 检测到崩溃 | 检查 `exception.log`，排查运行时错误 |

---

## 8. 技术架构

```
AI Agent
    │
    ▼
delphi_project(action="compile"|"info"|"audit"|...)
    │
    ▼
┌─────────────────────────────────────┐
│         src/tools/project.py          │
│   action 分派 + 参数校验 + 异常处理     │
└──────┬────────┬──────────┬───────────┘
       │        │          │
       ▼        ▼          ▼
┌──────────┐ ┌────────┐ ┌──────────┐
│ compile  │ │ dproj  │ │  audit   │
│_project  │ │_tool   │ │  /ast    │
│ .py      │ │ .py    │ │  .py     │
├──────────┤ ├────────┤ ├──────────┤
│· MSBuild │ │· info  │ │· AST解析 │
│· dcc32   │ │· create│ │· 50+规则 │
│· 事件处理│ │· set   │ │· 骨架提取│
│· 路径解析│ │· add/  │ │· 运行时  │
│          │ │ remove │ │  检查    │
└──────────┘ └────────┘ └──────────┘
       │
       ▼
┌──────────────────────┐
│  CompilerService      │
│  · 编译器检测/选择    │
│  · 进程执行/超时控制  │
│  · 输出解析          │
└──────────────────────┘
```

---

## 9. 故障排除

| 现象 | 原因 | 解决 |
|------|------|------|
| 找不到编译器 | 未检测到注册表或无配置 | `check_environment(action="detect")` |
| 编译事件超时 | PreBuildEvent 耗时过长 | 增大 `timeout` 参数 |
| `run_verify` 失败 | 程序启动即崩溃 | 检查 `exception.log` 或降低复杂度排查 |
| MSBuild 路径不正确 | Delphi 安装不完整 | 手动指定 `compiler_version` |
| 命令行过长 | 搜索路径过多 | 自动优化：只包含实际依赖的三方库 |
| `.dpk` 安装失败 | 缺少依赖或版本不兼容 | 检查 `auto_install` 参数和相关包依赖 |
