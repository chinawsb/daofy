# Package — 组件包管理

> 版本：v1.0 | 最后更新：2026-06-08

---

## 目录

1. [概述](#1-概述)
2. [Action 速查](#2-action-速查)
3. [Install — 编译安装组件包](#3-install--编译安装组件包)
4. [List — 列出已安装](#4-list--列出已安装)
5. [工作流](#5-工作流)
6. [故障排除](#6-故障排除)

---

## 1. 概述

`package` 管理 Delphi 组件包的编译和安装。支持 `.dproj`/`.dpk`/`.groupproj` 格式的包文件。

**核心特点**：
- 自动将**设计期包**注册到 IDE
- **运行期包**仅编译，不注册
- 支持多平台（win32/win64）编译
- 自动处理包依赖关系

---

## 2. Action 速查

| Action | 用途 |
|--------|------|
| `install`（默认） | 编译并安装组件包 |
| `list` | 列出已安装到 IDE 的组件包 |

---

## 3. Install — 编译安装组件包

### 基本用法

```python
# 安装 .dpk 包
package(action="install", package_path="MyPackage.dpk")

# 安装 .dproj 包
package(action="install", package_path="MyPackage.dproj")

# 安装 .groupproj 项目组
package(action="install", package_path="MyPackage.groupproj")
```

### 编译选项

```python
# Release 配置，64 位
package(action="install",
    package_path="MyPackage.dpk",
    target_platform="win64",
    build_configuration="Release")

# 仅编译不注册（运行期包）
package(action="install",
    package_path="MyRuntime.dpk",
    install=False)

# 长超时（大包）
package(action="install",
    package_path="BigPackage.dproj",
    timeout=600)
```

### 参数说明

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `package_path` | ✅ | — | 包文件路径（.dproj/.dpk/.groupproj） |
| `target_platform` | ❌ | win32 | 目标平台 |
| `build_configuration` | ❌ | Debug | 编译配置 |
| `timeout` | ❌ | 300 | 超时秒数 |
| `install` | ❌ | true | 是否自动安装到 IDE |

---

## 4. List — 列出已安装

列出已注册到 Delphi IDE 中的组件包。

```python
package(action="list")
```

返回已安装的包名列表，用于验证安装是否成功。

---

## 5. 工作流

### 安装组件包

```
package(action="install", package_path="MyPackage.dpk")
  ↓
package(action="list")            → 验证安装成功
```

### 多平台编译

```
package(action="install", package_path="MyPackage.dpk",
    target_platform="win32")
  ↓
package(action="install", package_path="MyPackage.dpk",
    target_platform="win64")
```

---

## 6. 故障排除

| 现象 | 原因 | 解决 |
|------|------|------|
| 编译失败 | 缺少依赖包 | 先安装依赖包，再重试 |
| 安装失败 | 包签名/版本冲突 | 检查 `install` 参数，尝试加 `timeout` |
| 64 位编译失败 | 缺少 64 位编译器 | `check_environment(action="detect")` 检测 |
| list 不显示刚安装的包 | IDE 未刷新 | 重启 IDE 后再次 list |
