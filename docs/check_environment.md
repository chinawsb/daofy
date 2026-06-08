# Check Environment — 编译环境诊断

> 版本：v1.0 | 最后更新：2026-06-08

---

## 目录

1. [概述](#1-概述)
2. [Action 速查](#2-action-速查)
3. [Check — 检查环境](#3-check--检查环境)
4. [Detect — 检测编译器](#4-detect--检测编译器)
5. [Install — 安装 pasfmt](#5-install--安装-pasfmt)
6. [Format Install — 安装 RAD 插件](#6-format-install--安装-rad-插件)
7. [支持的 Delphi 版本](#7-支持的-delphi-版本)
8. [工作流](#8-工作流)
9. [故障排除](#9-故障排除)

---

## 1. 概述

`check_environment` 是 Daofy 的环境诊断工具，用于检查 Delphi 编译器状态、重新检测已安装的编译器、以及安装 pasfmt 格式化工具。

**一句话**：首次使用或编译失败时，先调用此工具确认环境就绪。

---

## 2. Action 速查

| Action | 用途 |
|--------|------|
| `check`（默认） | 检查当前编译环境状态 |
| `detect` | 从注册表/指定路径重新检测 Delphi 编译器 |
| `install` | 下载并安装 pasfmt 格式化工具 |
| `format_install` | 安装 pasfmt RAD Studio IDE 插件 |

---

## 3. Check — 检查环境

默认操作，检查当前编译环境状态：列出所有可用的编译器、各编译器的版本和路径。

```python
check_environment(action="check")
```

**返回信息**：
- 可用的编译器列表（名称、版本、路径）
- 默认编译器
- pasfmt 是否已安装
- 环境状态（就绪/部分就绪/未就绪）

---

## 4. Detect — 检测编译器

从 Windows 注册表或指定路径重新检测 Delphi 编译器，更新 `config/compilers.json`。

```python
# 从注册表检测
check_environment(action="detect")

# 从指定路径检测
check_environment(action="detect", search_path="D:\Delphi\Studio")
```

**检测流程**：
1. 扫描注册表 `HKEY_CURRENT_USER\SOFTWARE\Embarcadero\BDS` 下所有版本
2. 自动检测各版本的编译器路径（dcc32.exe / dcc64.exe）
3. 写入 `config/compilers.json`

---

## 5. Install — 安装 pasfmt

下载并安装 **pasfmt**——Delphi 代码格式化工具。

```python
# 下载安装到默认位置
check_environment(action="install")

# 安装到指定目录
check_environment(action="install", install_dir="C:\Tools\pasfmt")
```

pasfmt 安装后，`delphi_file(action="format")` 即可使用。

---

## 6. Format Install — 安装 RAD 插件

将 pasfmt 安装为 RAD Studio IDE 插件，可在 IDE 中直接使用格式化功能。

```python
# 安装到 Delphi 11
check_environment(action="format_install", delphi_version="11")

# 安装到 Delphi 12
check_environment(action="format_install",
    delphi_version="12",
    install_dir="C:\pasfmt")
```

---

## 7. 支持的 Delphi 版本

自动注册表检测支持以下版本：

| 版本 | 注册表版本号 |
|------|------------|
| Delphi 13 Florence | 37.0 |
| Delphi 12 Athens | 23.0 |
| Delphi 11 Alexandria | 22.0 |
| Delphi 10.4 Sydney | 21.0 |
| Delphi 10.3 Rio | 20.0 |
| Delphi 10.2 Tokyo | 19.0 |
| Delphi 10.1 Berlin | 18.0 |
| Delphi 10 Seattle | 17.0 |
| Delphi XE8 | 16.0 |
| Delphi XE7 | 15.0 |
| Delphi XE6 | 14.0 |
| Delphi XE5 | 12.0 |
| Delphi XE4 | 11.0 |
| Delphi XE3 | 10.0 |
| Delphi XE2 | 9.0 |
| Delphi XE | 8.0 |
| Delphi 2010 | 7.0 |
| Delphi 2009 | 6.0 |
| Delphi 2007 | 5.0 |
| Delphi 2006 | 4.0 |
| Delphi 2005 | 3.0 |

---

## 8. 工作流

### 首次使用

```
check_environment(action="check")    → 确认环境状态
  ↓ 编译器未找到
check_environment(action="detect")   → 从注册表检测
  ↓
project(action="compile", ...)       → 开始编译
```

### 编译失败时

```
project(action="compile")  失败
  ↓
check_environment(action="check")   → 确认编译器状态
  ↓ 编译器不可用
check_environment(action="detect")  → 重新检测
  ↓
project(action="compile")  重试
```

### 安装格式化工具

```
check_environment(action="install")          → 下载 pasfmt
  ↓
delphi_file(action="format", file_path=...)  → 使用格式化
```

---

## 9. 故障排除

| 现象 | 原因 | 解决 |
|------|------|------|
| 未检测到编译器 | Delphi 未安装或注册表缺失 | 用 `search_path` 手动指定路径 |
| 检测到但编译失败 | 编译器版本不兼容 | 检查 `config/compilers.json` 中路径是否正确 |
| pasfmt 安装失败 | 网络问题无法下载 | 手动下载并放到 `tools/pasfmt/` 目录 |
| 插件安装失败 | RAD Studio 版本不对 | 确认 `delphi_version` 与实际版本匹配 |
