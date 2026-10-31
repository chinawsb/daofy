# 编译工具链配置 — Delphi 版本与 MSBuild

> 版本：v1.0 | 最后更新：2026-10-31

本文说明 Daofy 如何选择 **Delphi 版本** 和 **MSBuild**，以及单版本、多版本、旧版 Delphi、包安装、部署、CI 等场景应该怎么配置。

---

## 目录

1. [概述](#1-概述)
2. [配置文件与查找顺序](#2-配置文件与查找顺序)
3. [项目级配置参数](#3-项目级配置参数)
4. [全局配置参数](#4-全局配置参数)
5. [选择优先级](#5-选择优先级)
6. [典型场景](#6-典型场景)
7. [诊断与错误码](#7-诊断与错误码)
8. [从旧配置迁移](#8-从旧配置迁移)
9. [注意事项](#9-注意事项)

---

## 1. 概述

Daofy 的编译工具链由三部分组成：

| 部分 | 作用 |
|------|------|
| **Delphi 版本** | 决定 `rsvars.bat`、`dcc32/dcc64`、RTL/第三方库搜索路径、BPL/DCP 目录、IDE 注册表项 |
| **MSBuild 路径** | 决定用哪个 `MSBuild.exe` 编译 `.dproj` |
| **编译器配置** | `compilers.json` 中的 `dcc32.exe` / `dcc64.exe` 路径，供直接编译和单文件编译使用 |

核心原则：

> **同一个工程使用的 Delphi 版本、MSBuild、库路径必须来自同一套工具链，不能跨版本混用。**

---

## 2. 配置文件与查找顺序

### 2.1 项目级配置（推荐）

在工程目录或任意父目录放置：

```text
<工程目录>/.daofy/project.json
<工程目录>/daofy.project.json
```

查找顺序：

1. 从 `.dproj` / `.dpr` / `.dpk` 所在目录开始
2. 先找 `.daofy/project.json`，再找 `daofy.project.json`
3. 没有命中就逐级向父目录查找，最多 8 层
4. **离工程最近的配置文件生效**；同一配置文件内未写的字段继续按下一级规则查找

推荐把配置放在工程根目录：

```text
MyWorkspace/
├─ LegacyApp/
│  ├─ .daofy/project.json      ← LegacyApp 使用 XE4
│  └─ LegacyApp.dproj
├─ ModernApp/
│  ├─ .daofy/project.json      ← ModernApp 使用 Delphi 12
│  └─ ModernApp.dproj
└─ Shared/
   └─ .daofy/project.json      ← 工作区默认（可选）
```

### 2.2 全局配置（`compilers.json`）

`compilers.json` 保存编译器列表和按版本映射的 MSBuild：

```text
<Python 环境>/Lib/site-packages/src/config/compilers.json   # pip 安装
<项目根>/src/config/compilers.json                          # 源码运行
```

> 全局配置不再提供“所有工程统一钉死版本/统一 MSBuild”的开关。单工程差异请用项目级配置。

---

## 3. 项目级配置参数

最小示例：

```json
{
  "delphi_version": "11.0",
  "msbuild_path": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe"
}
```

### 3.1 参数表

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `delphi_version` | string | 否 | 该工程使用的 Delphi 版本 |
| `compiler_version` | string | 否 | `compilers.json` 中的编译器名称；也可直接写版本号 |
| `msbuild_path` | string | 否 | 该工程使用的 `MSBuild.exe`；相对路径按配置文件所在目录解析 |

三个字段都可以单独使用，也可以组合。未写的字段继续走全局/自动探测。

### 3.2 `delphi_version` 支持的写法

```json
{ "delphi_version": "11.0" }
```

| 写法 | 解释 |
|------|------|
| `"11.0"` / `"11"` | 注册表版本 11.0 = **Delphi XE4** |
| `"16.0"` | Delphi XE8 |
| `"19.0"` | Delphi 10.2 Tokyo |
| `"22.0"` / `"Delphi 11 Alexandria"` | Delphi 11 Alexandria |
| `"23.0"` / `"Delphi 12 Athens"` | Delphi 12 Athens |
| `"XE4"` / `"Delphi XE4"` | 按产品名匹配 |
| `"14.6"` | `.dproj ProjectVersion` → 注册表 14.0（XE6） |
| `"18.2"` | `.dproj ProjectVersion` → 注册表 18.0（10.1 Berlin） |
| `"19.2"` | `.dproj ProjectVersion` → 注册表 19.0（10.2 Tokyo） |

注意纯数字的歧义：

- `"12.0"` 表示**注册表版本 12.0 = XE5**
- 想表示 **Delphi 12 Athens**，请写 `"23.0"` 或 `"Delphi 12 Athens"`

### 3.3 `compiler_version`

用于直接指定 `compilers.json` 中的编译器，例如：

```json
{
  "compiler_version": "Delphi XE4 Win32"
}
```

也支持版本号/产品名：

```json
{
  "compiler_version": "11.0"
}
```

优先级与冲突规则：

- 同时配置 `compiler_version` 和 `delphi_version` 时，**以 `compiler_version` 为准**，版本不一致会在日志中告警
- `compiler_version` 写错但 `delphi_version` 有效时，会回退到 `delphi_version`
- 两者都不可用时**直接失败**，不会回退到其它 Delphi 版本

### 3.4 `msbuild_path`

```json
{
  "msbuild_path": "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\MSBuild\\Current\\Bin\\MSBuild.exe"
}
```

- 绝对路径直接使用
- 相对路径按**配置文件所在目录**解析，例如：

```text
<工程>/.daofy/project.json
<工程>/tools/MSBuild.exe
```

```json
{ "msbuild_path": "tools/MSBuild.exe" }
```

- 路径不存在时，使用 MSBuild 编译会直接报错 `MSBUILD_CONFIG_INVALID`，**不会回退到其它 MSBuild**
- `.dpr` / `.dpk` 有对应 `.dproj` 时，也不会回退到 dcc 直编来掩盖配置错误

### 3.5 配置校验

以下情况会让编译直接失败，而不是静默忽略：

- 配置文件不是合法 JSON
- `delphi_version` 无法识别
- `msbuild_path` 指向的文件不存在
- `compiler_version` 与 `delphi_version` 都无法解析

---

## 4. 全局配置参数

### 4.1 `compilers` 数组

```json
{
  "compilers": [
    {
      "name": "Delphi XE4 Win32",
      "path": "C:\\Embarcadero\\RAD Studio\\11.0\\bin\\dcc32.exe",
      "is_default": false,
      "version": "Delphi XE4",
      "registry_version": "11.0",
      "compiler_type": "delphi"
    }
  ],
  "default_compiler": "Delphi XE4 Win32"
}
```

| 字段 | 说明 |
|------|------|
| `name` | 编译器显示名称，也是 `compiler_version` 匹配的名称 |
| `path` | `dcc32.exe` / `dcc64.exe` 路径 |
| `is_default` | 是否默认编译器 |
| `version` | 产品名，如 `"Delphi XE4"` |
| `registry_version` | 注册表版本号，如 `"11.0"`；缺失时可按产品名回退匹配 |
| `compiler_type` | `"delphi"` 或 `"lazarus"` |

### 4.2 `default_compiler`

默认编译器名称。没有项目配置时，直接编译会优先使用它。

### 4.3 `show_timing`

工具返回中是否包含 `timing` 字段。

### 4.4 `msbuild_by_delphi_version`

按 Delphi 版本映射 MSBuild，适合“这台机器上 XE4 用 v3.5、Delphi 12 用 VS2022”这类场景：

```json
{
  "msbuild_by_delphi_version": {
    "11.0": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe",
    "16.0": "C:\\Windows\\Microsoft.NET\\Framework\\v4.0.30319\\MSBuild.exe",
    "23.0": "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\MSBuild\\Current\\Bin\\MSBuild.exe"
  }
}
```

- 键支持注册表版本号、产品名（`"XE4"`）或 `.dproj ProjectVersion`（`"14.6"`）
- 值支持绝对路径，或以 `compilers.json` 所在目录为基准的相对路径
- 配置了映射但没有命中当前版本时，日志会输出警告
- 映射路径无效时直接失败

### 4.5 已移除的配置

以下配置已移除，旧文件中的键会被忽略并输出迁移警告：

| 已移除 | 替代方案 |
|--------|----------|
| `msbuild_path` | 项目级 `msbuild_path` 或 `msbuild_by_delphi_version` |
| `default_registry_version` | 项目级 `delphi_version` |
| 环境变量 `DAOFY_MSBUILD` | 项目级 `msbuild_path` |
| 环境变量 `DAOFY_DELPHI_VERSION` | 项目级 `delphi_version` |

---

## 5. 选择优先级

### Delphi 版本

```text
工具参数 compiler_version
> 项目配置 compiler_version
> 项目配置 delphi_version
> .dproj ProjectVersion 推断
```

### MSBuild

```text
项目配置 msbuild_path
> compilers.json 的 msbuild_by_delphi_version[版本]
> 自动探测
```

自动探测顺序：

1. 按工程 Delphi 版本优先：XE4 及更早找 `.NET Framework\v3.5\MSBuild.exe`
2. XE5–10 Seattle 找 `.NET Framework\v4.0.30319\MSBuild.exe`
3. `vswhere` 查询 Visual Studio 2017+
4. 常见 VS 2019/2022 安装路径
5. Delphi 安装目录自带的 MSBuild
6. `PATH` 中的 `msbuild.exe`

> 自动探测是启发式。对“某个 Delphi 版本必须搭配某个特定 VS/MSBuild”的场景，请显式配置。

---

## 6. 典型场景

### 6.1 单版本 Delphi，没有特殊需求

不需要任何配置。Daofy 会：

- 从注册表读取唯一安装的 Delphi 版本
- 自动探测 MSBuild
- 使用 `compilers.json` 中的默认编译器

### 6.2 多版本 Delphi，不同工程使用不同版本

推荐每个工程单独配置：

**XE4 工程**

```json
{
  "delphi_version": "11.0",
  "msbuild_path": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe"
}
```

**XE8 工程**

```json
{
  "delphi_version": "16.0"
}
```

**Delphi 10.2 Tokyo 工程**

```json
{
  "delphi_version": "19.0",
  "msbuild_path": "C:\\Program Files (x86)\\Microsoft Visual Studio\\2019\\Community\\MSBuild\\Current\\Bin\\MSBuild.exe"
}
```

这样 XE4 工程不会因为机器上还装了 Delphi 12 而用错 `rsvars.bat`、dcc 或库路径。

### 6.3 `.dproj ProjectVersion` 与想用的 Delphi 不一致

例如工程文件里是：

```xml
<ProjectVersion>14.6</ProjectVersion>
```

14.6 对应 XE6（注册表 14.0），但你希望用 XE4 编译。**只配 `msbuild_by_delphi_version["11.0"]` 不会生效**，因为版本推断结果是 14.0。必须显式写：

```json
{
  "delphi_version": "11.0",
  "msbuild_path": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe"
}
```

### 6.4 旧版 Delphi（XE4 及更早）需要 .NET 3.5 MSBuild

XE4 等旧版本通常需要：

```text
C:\Windows\Microsoft.NET\Framework\v3.5\MSBuild.exe
```

如果该文件不存在：

- 自动探测会输出警告，然后继续尝试 VS/PATH 的 MSBuild（可能不兼容）
- 建议安装 .NET Framework 3.5，或在项目配置里指向一个可用的兼容 MSBuild
- 需要严格失败而不是尝试其它 MSBuild 时，直接写项目级 `msbuild_path`；路径无效会立即报错

### 6.5 机器上没有 Visual Studio，只有 Delphi

自动探测会继续检查：

- Delphi 安装目录自带的 MSBuild
- `PATH` 中的 `msbuild.exe`

如果都没有：

- `.dproj` 编译会返回 `MSBUILD_NOT_FOUND`
- `.dpr` / `.dpk` 有 `.dproj` 时会回退到 dcc 直接编译
- 最稳妥的方式是给工程配置一个可用的 `msbuild_path`

### 6.6 包安装（`install_package`）

包工程的项目配置会同时作用于：

- `rsvars.bat` 版本
- 编译使用的 Delphi/MSBuild
- BPL/DCP 输出目录（`Documents\Embarcadero\Studio\<版本>\...`）
- IDE `Known Packages` 注册表项（`HKCU\Software\Embarcadero\BDS\<版本>\Known Packages`）

因此不要把 XE4 的包工程放在一个全局默认 Delphi 12 的环境里直接安装；请给包工程加 `.daofy/project.json`。

### 6.7 部署（`deploy`）

部署时也会按工程配置解析 MSBuild 版本。

> 已知限制：部署流程目前只解析 MSBuild 路径，不会自动执行 `rsvars.bat`。如果部署目标依赖 `BDS`/Delphi 环境变量，请先在启动 MCP 的终端加载对应版本的 `rsvars.bat`。

### 6.8 CI / 团队协作

- 把 `.daofy/project.json` 提交到仓库，保证每台机器/每个 Agent 使用同一套工具链
- 不要把机器相关的 `compilers.json` 提交到仓库（已在 `.gitignore` 中）
- CI 机器需要安装对应 Delphi 版本，并保证 `compilers.json` 中有对应编译器路径
- 旧版 Delphi 需要额外确认 `.NET Framework v3.5` 的 MSBuild 已安装

### 6.9 工作区默认 + 工程覆盖

可以在工作区根目录放一份默认配置，再在子工程覆盖：

```text
Workspace/
├─ .daofy/project.json          { "delphi_version": "16.0" }   ← 工作区默认 XE8
├─ Legacy/
│  └─ .daofy/project.json       { "delphi_version": "11.0" }   ← 覆盖为 XE4
└─ Modern/
   └─ Legacy.dproj
```

就近命中的配置优先；子工程只写需要覆盖的字段即可。

---

## 7. 诊断与错误码

### 7.1 `check_environment`

```python
check_environment(action="check")
```

可以查看：

- 编译器列表及路径是否有效
- 默认编译器
- `msbuild_by_delphi_version` 的映射及文件是否存在
- 项目级配置入口提示

> `check_environment` 显示的是全局编译器与版本映射；某个工程最终选中的版本/MSBuild 以编译日志为准。

### 7.2 常见错误码

| 错误码 | 含义 | 处理方式 |
|--------|------|----------|
| `MSBUILD_NOT_FOUND` | 自动探测不到 MSBuild | 安装 VS/Build Tools，或在项目配置中写 `msbuild_path` |
| `MSBUILD_CONFIG_INVALID` | 项目/版本映射的 MSBuild 路径无效 | 修正路径；不会回退其它 MSBuild |
| `RSVARS_NOT_FOUND` | 目标 Delphi 版本未安装或注册表缺失 | 安装对应 Delphi，或修正 `delphi_version` |
| `COMPILER_VERSION_UNRESOLVED` | 项目 `compiler_version` 无效且无法推断版本 | 修正 `compiler_version`，或改用 `delphi_version` |
| `COMPILER_NOT_FOUND` | `compilers.json` 中没有可用编译器 | 运行 `check_environment(action="detect")` 或手动补配置 |
| `PROJECT_CONFIG_INVALID` | 项目配置 JSON/`delphi_version` 非法 | 修正 `.daofy/project.json` |
| `INVALID_PROJECT_PATH` | 工程路径不存在或不是 `.dproj/.dpr/.dpk` | 检查 `project_path` |

### 7.3 配置不生效

1. 确认配置文件在工程目录或父目录，且文件名是 `.daofy/project.json` 或 `daofy.project.json`
2. 确认 JSON 合法（不支持注释）
3. 确认修改后已**重启 Daofy MCP 服务/IDE**
4. 查看日志中是否出现“加载项目配置 ...”
5. 旧全局配置/环境变量已移除，不要再用 `compilers.json` 的 `msbuild_path`、`default_registry_version` 或 `DAOFY_*` 环境变量

---

## 8. 从旧配置迁移

如果之前使用过：

```json
{
  "msbuild_path": "...",
  "default_registry_version": "11.0"
}
```

请改为项目级配置：

```text
<工程>/.daofy/project.json
```

```json
{
  "delphi_version": "11.0",
  "msbuild_path": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe"
}
```

如果只是“某个版本对应某个 MSBuild”，保留全局映射：

```json
{
  "msbuild_by_delphi_version": {
    "11.0": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe"
  }
}
```

环境变量 `DAOFY_MSBUILD` / `DAOFY_DELPHI_VERSION` 不再生效，请从 MCP 客户端配置中删除。

---

## 9. 注意事项

- **项目配置可以指定任意可执行文件路径，只应在可信工程中使用**
- 显式配置优先于自动探测；显式配置无效时直接失败，不会“猜”另一个版本
- `msbuild_by_delphi_version` 只负责 MSBuild，不会改变 Delphi 版本；想覆盖 `.dproj ProjectVersion` 仍需项目级 `delphi_version`
- 自动匹配编译器时，如果 `.dproj` 对应版本没有配置编译器，仍可能按原有策略回退到更高版本（日志会警告）；需要严格版本时使用项目级 `delphi_version`
- 修改配置后需要重启 MCP 服务/IDE
- 版本号、编译器路径、MSBuild 路径都属于机器相关配置，建议只把 `.daofy/project.json` 纳入版本控制，不要提交 `compilers.json`

---

## 附：完整示例

```json
{
  "delphi_version": "11.0",
  "compiler_version": "Delphi XE4 Win32",
  "msbuild_path": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe"
}
```

对应的 `compilers.json` 片段：

```json
{
  "compilers": [
    {
      "name": "Delphi XE4 Win32",
      "path": "C:\\Embarcadero\\RAD Studio\\11.0\\bin\\dcc32.exe",
      "is_default": false,
      "version": "Delphi XE4",
      "registry_version": "11.0",
      "compiler_type": "delphi"
    }
  ],
  "default_compiler": "Delphi XE4 Win32"
}
```
