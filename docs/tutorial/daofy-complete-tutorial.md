# Daofy for Delphi 完整使用教程

> **版本**: v2026.06.15.1 | **最后更新**: 2026-06-20

---

## 目录

- [第一章：Daofy 概述](#第一章daofy-概述)
- [第二章：安装与配置](#第二章安装与配置)
- [第三章：环境检查与诊断](#第三章环境检查与诊断)
- [第四章：知识库搜索与管理](#第四章知识库搜索与管理)
- [第五章：项目编译与配置管理](#第五章项目编译与配置管理)
- [第六章：Delphi 文件操作](#第六章delphi-文件操作)
  - [6.1 工具概述](#61-工具概述)
  - [6.2 Action 速查](#62-action-速查)
  - [6.3 行号规则](#63-行号规则)
  - [6.4 读取文件](#64-读取文件)
  - [6.5 写入文件](#65-写入文件)
  - [6.6 格式化代码](#66-格式化代码)
  - [6.7 备份管理](#67-备份管理)
  - [6.8 Uses 子句管理](#68-uses-子句管理)
  - [6.9 编码转换（encode）](#69-编码转换encode)
  - [6.10 脏标记机制](#610-脏标记机制)
- [第七章：编码规范与代码审计](#第七章编码规范与代码审计)
- [第八章：代码托管与 Git 操作](#第八章代码托管与-git-操作)
- [第九章：经验记忆管理](#第九章经验记忆管理)
- [第十章：Delphi RTTI 桥接](#第十章delphi-rtti-桥接)
- [第十一章：自动化测试](#第十一章自动化测试)
- [第十二章：OCR 图像文字识别](#第十二章ocr-图像文字识别)
- [第十三章：组件管理](#第十三章组件管理)
- [第十四章：组件包管理](#第十四章组件包管理)
- [第十五章：异步任务管理](#第十五章异步任务管理)
- [第十六章：Daofy 自身更新管理](#第十六章daofy-自身更新管理)
- [第十七章：软著文档生成](#第十七章软著文档生成)
- [第十八章：故障排除与最佳实践](#第十八章故障排除与最佳实践)

---

## 第一章：Daofy 概述

### 1.1 什么是 Daofy？

**Daofy（道飞）**——为创意插上翅膀。

Daofy for Delphi 是一个基于 **Model Context Protocol (MCP)** 的 MCP Server，它允许 AI 助手（如 Claude Desktop、CodeArts Agent、Cursor 等）直接编译 Delphi 项目并查询 Delphi 知识库。通过这个工具，您可以在与 AI 助手的对话中直接编译 Delphi 工程、查询 API 文档、搜索代码示例，无需手动切换到 IDE 或命令行。

### 1.2 核心优势

| 优势 | 说明 |
|------|------|
| **无缝集成** | 嵌入 AI 助手工作流，聊天中完成编译、搜索、编码 |
| **零配置** | 自动从注册表检测 Delphi 编译器，无需手动配置 |
| **知识库内置** | 内置 Delphi RTL/VCL/FMX 源码索引，支持语义搜索 |
| **全生命周期** | 从创建项目、编译、审计到代码托管，一站式完成 |
| **跨版本支持** | 支持 Delphi 2005 到 Delphi 13 全系列版本 |

### 1.3 功能全景概览

Daofy 提供 16 个 MCP 工具：

| # | 工具名 | 功能域 | 一句话用途 |
|---|--------|--------|-----------|
| 1 | `project` | 编译/配置/审计 | 项目全生命周期管理 |
| 2 | `delphi_kb` | 知识库搜索/构建 | Delphi API、项目代码、文档搜索 |
| 3 | `delphi_file` | 文件操作 | Delphi 文件读写/格式化/编码转换/备份 |
| 4 | `manage_component` | 组件管理 | DFM 组件增删改 + PAS 自动同步 |
| 5 | `check_environment` | 环境诊断 | 检查编译器、安装 pasfmt |
| 6 | `async_task` | 后台任务 | 管理知识库构建等耗时任务 |
| 7 | `package` | 组件包管理 | 编译安装 .dpk 组件包 |
| 8 | `get_coding_rules` | 编码规范 | 获取 Delphi 编码规则 |
| 9 | `code_hosting` | 代码托管 | Git 操作 + 平台 API |
| 10 | `tool_help` | 帮助文档 | 获取任意工具完整帮助（详见下文说明） |
| 11 | `experience` | 经验记忆 | 保存/搜索 AI 解决问题的经验 |
| 12 | `daofy_update` | 自身更新 | 检查/更新 Daofy 版本 |
| 13 | `delphi_rtti` | RTTI 桥接 | 发现和调用 Delphi 运行时能力 |
| 14 | `automate_delphi` | 自动化测试 | GUI 截图 + 控制台交互 |
| 15 | `ocr` | 图像分析 | 文字识别/截图对比/颜色分析 |
| 16 | `generate_copyright` | 软著生成 | 生成软件著作权文档 |

> 💡 **`tool_help` 使用提示**：任何时候不确定某个工具的详细用法，可以调用 `tool_help(tool_name="工具名")` 获取该工具的完整帮助，包含参数说明、action 详解、使用示例、触发词等。例如 `tool_help(tool_name="delphi_file")`。

### 1.4 系统要求

| 组件 | 要求 |
|------|------|
| **Python** | 3.10 ~ 3.14 |
| **操作系统** | Windows（Delphi 仅支持 Windows） |
| **Delphi 编译器** | dcc32.exe 或 dcc64.exe（任意版本） |
| **Git** | 用于代码托管功能 |
| **7-Zip** | 可选，用于解压 CHM 帮助文件（可放在 `tools/7z/` 免安装） |

---

## 第二章：安装与配置

### 2.1 方式一：pip 安装（推荐）

```bash
pip install daofy-for-delphi
```

> **国内用户加速**：
> ```bash
> pip install daofy-for-delphi -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```

安装完成后直接跳转到 → [2.3 配置 AI 助手](#23-配置-ai-助手)。

### 2.2 方式二：源码安装

#### 步骤 1：克隆项目

```bash
git clone https://github.com/chinawsb/daofy.git
# 国内用户可用 Gitee 镜像
# git clone https://gitee.com/zuoyouruanjian/daofy.git
cd daofy
```

#### 步骤 2：创建并激活虚拟环境

```bash
python -m venv venv
venv\Scripts\activate     # Windows
# source venv/bin/activate  # Linux/macOS
```

#### 步骤 3：安装依赖

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

#### 步骤 4：安装可选扩展

```bash
# 文件变更监听 —— 自动增量更新项目知识库
pip install daofy-for-delphi[watcher]

# 语义搜索增强 —— 安装后搜索质量显著提升
pip install daofy-for-delphi[embedding]

# OCR 图像文字识别
pip install daofy-for-delphi[ocr]

# Intel CPU OCR 加速（替换 onnxruntime → onnxruntime-openvino）
pip install daofy-for-delphi[ocr-openvino]
```

### 2.3 配置 AI 助手

首次启动 MCP Server 时，会自动从 Windows 注册表检测已安装的 Delphi 编译器，**无需手动配置**。

#### pip 安装的最简配置

```json
{
  "mcpServers": {
    "daofy": {
      "command": "daofy",
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

#### 源码安装配置

**Claude Desktop**（`%APPDATA%\Claude\claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "daofy": {
      "command": "python",
      "args": ["C:\\path\\to\\daofy\\src\\server.py"],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

**Trae**（`C:\Users\<用户名>\.trae-cn\mcp_config.json`）：

```json
{
  "mcpServers": {
    "daofy": {
      "command": "F:\\path\\to\\venv\\Scripts\\python.exe",
      "args": ["F:\\path\\to\\daofy\\src\\server.py"],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

**CodeArts Agent**（`~/.codeartsdoer/mcp/mcp_settings.json`）：

```json
{
  "mcpServers": {
    "daofy": {
      "command": "python",
      "args": ["src\\server.py"],
      "cwd": "C:\\path\\to\\daofy",
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

### 2.4 使用安装脚本（源码安装）

项目提供了 `install.bat` 安装脚本，支持自动检测已安装的 AI 客户端并配置 MCP：

```bash
.\install.bat
```

脚本支持检测的 AI 客户端：
- Claude Desktop
- Trae
- CodeArts Agent
- Cursor
- Windsurf
- Cline
- 通义灵码（Tongyi Lingma）
- 豆包（Doubao）
- Kimi
- OpenCode

### 2.5 验证安装

```bash
python src/server.py
```

看到以下输出表示启动成功：
```
INFO 启动 Daofy v2026.06.15.1
INFO 配置管理器初始化完成
INFO 编译服务初始化完成
...
```

---

## 第三章：环境检查与诊断

### 3.1 工具概述

`check_environment` 是 Daofy 的环境诊断工具，用于检查 Delphi 编译器状态、重新检测已安装的编译器以及安装 pasfmt 格式化工具。

### 3.2 Action 速查

| Action | 用途 |
|--------|------|
| `check`（默认） | 检查当前编译环境状态 |
| `detect` | 从注册表/指定路径重新检测 Delphi 编译器 |
| `install` | 下载并安装 pasfmt 格式化工具 |
| `format_install` | 安装 pasfmt RAD Studio IDE 插件 |

### 3.3 检查编译环境

```python
check_environment(action="check")
```

返回信息包含：
- 可用的编译器列表（名称、版本、路径）
- 默认编译器
- pasfmt 是否已安装
- 环境状态（就绪/部分就绪/未就绪）

### 3.4 检测编译器

```python
# 从注册表检测
check_environment(action="detect")

# 从指定路径检测
check_environment(action="detect", search_path="D:\\Delphi\\Studio")
```

检测流程：
1. 扫描注册表 `HKEY_CURRENT_USER\SOFTWARE\Embarcadero\BDS` 下所有版本
2. 自动检测各版本的编译器路径（dcc32.exe / dcc64.exe）
3. 写入 `config/compilers.json`

### 3.5 安装 pasfmt 格式化工具

```python
# 下载安装到默认位置
check_environment(action="install")

# 安装到指定目录
check_environment(action="install", install_dir="C:\\Tools\\pasfmt")
```

安装后，`delphi_file(action="format")` 即可使用。

### 3.6 支持的 Delphi 版本

自动注册表检测支持 Delphi 2005 ~ Delphi 13 全系列版本：

| 版本 | 注册表版本号 |
|------|------------|
| Delphi 13 Florence | 37.0 |
| Delphi 12 Athens | 23.0 |
| Delphi 11 Alexandria | 22.0 |
| Delphi 10.4 Sydney | 21.0 |
| Delphi 10.3 Rio | 20.0 |
| ... | ... |
| Delphi 2005 | 3.0 |

### 3.7 典型工作流

```python
# 首次使用
check_environment(action="check")    # 确认环境状态
# → 编译器未找到
check_environment(action="detect")   # 从注册表检测
# → 开始编译
project(action="compile", ...)

# 编译失败时
project(action="compile")   # 失败
check_environment(action="check")   # 确认编译器状态
check_environment(action="detect")  # 重新检测后重试
```

---

## 第四章：知识库搜索与管理

### 4.1 工具概述

`delphi_kb` 是 Daofy 的知识库搜索与管理工具。它整合了 **四大知识库**，支持类/函数/语义等多种搜索方式。

**核心用途**：AI 编写 Delphi 代码前，先查知识库确认 API 定义，避免凭空编造。

### 4.2 五大知识库

| 知识库类型 | kb_type | 数据量 | 存储路径 |
|-----------|---------|--------|---------|
| Delphi 源码 | `delphi` | 163,737 类 / 300,228 函数 | `data/delphi-knowledge-base/` |
| 项目知识库 | `project` | 项目自定 | `<项目目录>/.delphi-kb/` |
| 第三方库 | `thirdparty` | 5,724 类 / 28,801 函数 | `data/thirdparty-knowledge-base/` |
| 通用文档 | `document` | 160,328 篇 | `data/document-knowledge-base/` |
| 示例代码 | `example` | 项目自定 | `data/example-knowledge-base/` |

### 4.3 搜索 API

```python
# 搜索类（最常用）
delphi_kb(query="TStringList")

# 搜索函数
delphi_kb(query="Create", search_type="function")

# 语义搜索（自然语言描述需求）
delphi_kb(query="如何创建数据库连接", search_type="semantic")

# 搜索项目代码
delphi_kb(query="TfrmMain", kb_type="project", project_path="Project.dproj")

# 搜索 Delphi 官方 API
delphi_kb(query="TCustomADODataSet", kb_type="delphi")

# 引用查询（评估修改影响范围）
delphi_kb(query="TStringList", search_type="reference")
```

**参数说明**：

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | ✅ | — | 搜索关键词 |
| `kb_type` | ❌ | all | all/delphi/project/thirdparty/document/example |
| `search_type` | ❌ | — | class/function/procedure/record/interface/enum/set/helper/type/const/resourcestring/variable/property/method/field/event/operator/string/dfm/attribute/unit/semantic/reference/all |
| `top_k` | ❌ | 200 | 最大返回结果数（最大 500） |
| `project_path` | ❌ | 自动检测 | 项目路径 |

### 4.4 搜索策略与优先级

> ⭐ **AI 写代码前的标准搜索流程**

```
⭐1  delphi_kb(query="TStringList")            精确类名搜索
     └─ 无结果？→ 换名再试
⭐2  delphi_kb(query="TMainForm")              换名（TMainForm→TfrmMain）
     └─ 仍无结果？→ 搜函数
⭐3  delphi_kb(query="Create",
          search_type="function")             搜索函数（同时匹配 FF+FP）
     └─ 仍无结果？→ 查引用
⭐4  delphi_kb(query="TForm1",
          search_type="reference")            查引用（评估修改影响）
     └─ 仍无结果？→ 语义搜索兜底
⭐5  delphi_kb(query="创建主窗口",
          search_type="semantic")             中文语义搜索兜底
```

### 4.5 知识库统计

```python
delphi_kb(action="stats")
```

| 知识库 | 文件数 | 类数量 | 函数数量 | 数据库大小 |
|--------|-------|--------|---------|-----------|
| Delphi 源码 | 2,798 | 163,737 | 300,228 | 260 MB |
| 三方库 | 1,800 | 5,724 | 28,801 | 27 MB |
| 通用文档 | 160,328 | — | — | 1,306 MB |

### 4.6 构建知识库

```python
# Delphi 源码 KB（~1 分钟）
delphi_kb(action="build", kb_type="delphi", rebuild=True, async_mode=True)

# 三方库 KB（~6 秒）
delphi_kb(action="build", kb_type="thirdparty", rebuild=True, async_mode=True)

# 文档 KB（~6 分钟，160328 文档）
delphi_kb(action="build", kb_type="document", rebuild=True, async_mode=True)

# 项目 KB
delphi_kb(action="build", kb_type="project",
    project_path="Project.dproj", rebuild=True)
```

**参数说明**：

| 参数 | 说明 |
|------|------|
| `async_mode` | 默认 true，异步执行不阻塞 MCP 通道 |
| `rebuild` | 强制完全重建（默认 false） |
| `incremental` | 增量更新，只处理变更的文件 |
| `directory` | 扫描目录（build document 时可指定，默认自动检测 Delphi 帮助目录） |
| `extensions` | 文件扩展名过滤（如 `[".chm"]`） |

### 4.7 构建 Delphi 帮助文档知识库

```python
# 自动检测最新安装的 Delphi 帮助目录
delphi_kb(action="build", kb_type="document",
    extensions=[".chm"], async_mode=True)

# 手动指定目录
delphi_kb(action="build", kb_type="document",
    directory="C:\\Program Files (x86)\\Embarcadero\\Studio\\23.0\\Help\\Doc",
    extensions=[".chm"], async_mode=True)
```

**版本对照**：37.0=Delphi 13, 23.0=Delphi 12, 22.0=Delphi 11, 21.0=Delphi 10.4

### 4.8 文档知识库搜索

构建完成后，就可以像搜索源码一样搜索帮助文档（`kb_type="document"` 路由到独立的文档搜索引擎，支持全文检索）：

```python
# 搜索 API 文档
delphi_kb(query="TCanvas.Draw", kb_type="document")

# 自然语言搜索
delphi_kb(query="怎么用 PrintDialog 设置打印机参数", kb_type="document", search_type="semantic")
```

> 💡 **提示**：`kb_type="document"` 走独立路由搜索文档知识库；`kb_type="all"` 也会自动包含文档搜索结果。

### 4.9 向量索引（Embedding）

向量索引基于 sentence-transformers 模型，实现**语义搜索**——你搜"怎么创建数据库连接"也能匹配到 `TADOConnection.Create`。

```python
# 构建向量索引
delphi_kb(action="build_embedding", async_mode=True)
```

| 功能 | 模型未加载 | 模型已加载 |
|------|-----------|-----------|
| 语义搜索 | 降级为倒排索引 | 真语义搜索，余弦相似度排序 |
| 经验库保存 | 不去重 | 自动 >0.85 去重合并 |
| 经验库搜索 | LIKE 关键词降级 | 语义向量搜索 |

---

## 第五章：项目编译与配置管理

### 5.1 工具概述

`project` 是 Daofy 中最核心的工具，提供 Delphi 项目的**全生命周期管理**——从创建项目、配置编译选项、执行编译到代码审计。

### 5.2 Action 速查

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
| `ast` | 代码骨架提取（最省 token） | `base_dir` |
| `runtime` | 运行时注册检查 | — |

### 5.3 编译项目

```python
# 最简调用 — 自动检测项目类型和配置
project(action="compile", project_path="Project.dproj")

# 完整参数编译
project(action="compile",
    project_path="App.dproj",
    build_configuration="Release",
    target_platform="win64",
    conditional_defines=["RELEASE", "MY_FEATURE"],
    unit_search_paths=["C:\\Libs\\Common", "..\\Shared"],
    optimize=True,
    debug=False,
    output_path=".\\Build\\Release")

# 编译后运行验证（检测运行时崩溃）
project(action="compile",
    project_path="App.dproj",
    run_verify=True)
```

**编译参数说明**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `project_path` | — | .dproj/.dpr/.dpk/.pas 路径 |
| `target_platform` | win32 | win32/win64/osx64/... |
| `build_configuration` | Debug | Debug/Release |
| `compiler_version` | 自动检测最新 | 指定 Delphi 版本 |
| `conditional_defines` | — | 条件编译符号数组 |
| `unit_search_paths` | — | 额外单元搜索路径 |
| `optimize` | true | 是否启用优化 |
| `debug` | true | 是否生成调试信息 |
| `timeout` | 300 | 超时秒数 |
| `run_verify` | false | 编译后启动 3 秒验证是否崩溃 |
| `output_path` | — | 编译输出目录 |

### 5.4 编译事件

`.dproj` 中的 `PreBuildEvent`/`PostBuildEvent`/`PreLinkEvent` 会自动执行，无需手动处理。

`run_verify` 编译成功后自动启动 exe 运行 3 秒，检测到 `exception.log` 时自动读取内容嵌入响应。

### 5.5 单文件语法检查

```python
project(action="compile_file", project_path="Unit1.pas")

# 带搜索路径
project(action="compile_file",
    project_path="Unit1.pas",
    unit_search_paths=["..\\Shared"],
    conditional_defines=["TEST"])
```

### 5.6 创建项目

```python
# 最简创建
project(action="create",
    project_path="MyApp.dproj",
    main_source="MyApp.dpr")

# 带 Form 桩代码
project(action="create",
    project_path="MyApp.dproj",
    main_source="MyApp.dpr",
    framework_type="VCL",
    form_units=["Unit1", "MainForm"],
    configs=["Debug", "Release", "Staging"])
```

### 5.7 读取和修改项目配置

```python
# 读取项目信息
project(action="info", project_path="Project.dproj")

# 修改属性
project(action="set",
    project_path="Project.dproj",
    property_name="DCC_Define",
    value="DEBUG;TEST",
    config="Debug",
    platform="Win32")

# 添加编译配置
project(action="add_config",
    project_path="Project.dproj",
    config_name="Staging",
    base_config="Debug",
    defines=["STAGING"])

# 删除编译配置
project(action="remove_config",
    project_path="Project.dproj",
    config_name="Staging")
```

### 5.8 源文件管理

```python
# 添加源文件
project(action="add_source",
    project_path="Project.dproj",
    source_file="Unit1.pas")

# 删除源文件
project(action="remove_source",
    project_path="Project.dproj",
    source_file="Unit1.pas")
```

### 5.9 编译错误排查

```python
# 常见排查流程
project(action="compile")  失败
check_environment(action="check")   # 确认编译器状态
# → 检查 DCC_UnitSearchPath 是否包含需要的三方库路径
# → 确认目标平台（win32/win64）编译器可用
# → 条件编译符号是否匹配（DEBUG/RELEASE）
```

**常见编译错误**：

| 错误现象 | 可能原因 | 解决 |
|---------|---------|------|
| `Fatal: Unable to execute file` | 编译器路径错误 | `check_environment(action="detect")` 重新检测 |
| `Fatal: File not found: xxx.dcu` | 缺少搜索路径 | 补充 `unit_search_paths` 参数 |
| Exit code 2 | 编译事件失败或语法错误 | 查看详细输出定位错误行 |

---

## 第六章：Delphi 文件操作

### 6.1 工具概述

`delphi_file` 是 Delphi 文件的专用操作工具。支持 `.pas`、`.dpr`、`.dpk`、`.dfm`、`.fmx`、`.inc`、`.dproj`，自动处理编码检测/转换、`__history` 备份、DFM/FMX 二进制转换和同文件读写互斥。

> ⚠️ **禁止使用原生 read/write/edit 工具修改 .pas/.dfm 文件！必须使用 delphi_file。**

### 6.2 Action 速查

| Action | 用途 |
|--------|------|
| `read` | 按路径读取，或按类名/函数名/record 定位后读取 |
| `write` | 兼容写入接口，使用 `edits=[...]` |
| `replace` | 按行范围替换（需提供 old_content 校验） |
| `insert` | 按锚点行插入（需提供 old_content 校验） |
| `delete` | 按行范围删除（需提供 old_content 校验） |
| `format` | 使用 pasfmt 格式化 |
| `backup` | 创建/列出/恢复 `__history` 备份 |
| `encode` | 文件编码转换（自动检测源编码，支持 BOM 处理） |
| `uses` | 增删 uses 子句单元 |

### 6.3 行号规则

所有 `read`/`write`/`uses` 的行号参数和输出均为 **1-indexed inclusive**。

| 示例 | 含义 |
|------|------|
| `start_line=1` | 从第 1 行开始 |
| `start_line=5, end_line=10` | 第 5 到第 10 行，包含两端 |
| `write` 不传 `end_line` | 从 `start_line` 替换到文件末尾 |

### 6.4 读取文件

```python
# 基本读取
delphi_file(action="read", file_path="Unit1.pas")

# 分段读取
delphi_file(action="read", file_path="Unit1.pas", start_line=5, end_line=15)

# 显示行号
delphi_file(action="read", file_path="Unit1.pas", show_line_numbers=True)

# 按类型搜索读取
delphi_file(action="read", search_type="class", type_name="TButton")
delphi_file(action="read", search_type="function", function_name="Create")
delphi_file(action="read", search_type="record", record_name="TPoint")

# 跨知识库搜索
delphi_file(action="read", search_type="class",
    type_name="TMainForm", search_in="project", project_path="Project.dproj")
```

### 6.5 写入文件

**推荐使用 `replace`/`insert`/`delete` 语义操作**（更安全）：

```python
# 替换行范围
delphi_file(action="replace",
    file_path="Unit1.pas",
    edits=[{"start_line": 5, "end_line": 10,
            "old_content": "  OldCall;\n",
            "content": "  NewCall;\n"}])

# 按锚点插入
delphi_file(action="insert",
    file_path="Unit1.pas",
    edits=[{"start_line": 10, "position": "before",
            "old_content": "  OldCall;\n",
            "content": "  NewCall;\n"}])

# 删除行范围
delphi_file(action="delete",
    file_path="Unit1.pas",
    edits=[{"start_line": 10, "end_line": 12,
            "old_content": "  OldCall;\n  OtherCall;\n"}])
```

**兼容的 `write` 接口**：

```python
# 全文替换
delphi_file(action="write",
    file_path="Unit1.pas",
    edits=[{"start_line": 1, "content": "unit Unit1;\n\ninterface\n\nimplementation\n\nend.\n"}])

# 部分替换
delphi_file(action="write",
    file_path="Unit1.pas",
    edits=[{"start_line": 5, "end_line": 10, "content": "  // new code\n"}])

# 多处修改合并到一次 write
delphi_file(action="write",
    file_path="Unit1.pas",
    edits=[
        {"start_line": 5, "end_line": 7, "content": "  // first block\n"},
        {"start_line": 18, "end_line": 21, "content": "  // second block\n"},
    ])

# 预览模式（仅计算 diff，不写盘）
delphi_file(action="write",
    file_path="Unit1.pas",
    edits=[{"start_line": 5, "end_line": 10, "content": "  // new code\n"}],
    preview=True)
```

**写入参数说明**：

| 参数 | 默认 | 说明 |
|------|------|------|
| `backup` | True | 写入前备份到 `__history` |
| `encoding` | auto | 保持原编码；可显式指定 |
| `auto_format` | False | 写入后自动 pasfmt |
| `preview` | False | 仅计算 diff，不写盘 |
| `force` | False | 跳过连续重复行检测 |
| `allow_dirty` | False | 跳过脏标记检查（优先用 old_content） |

### 6.6 格式化代码

```python
delphi_file(action="format", file_path="Unit1.pas")

# 检查模式（仅检查格式，不修改）
delphi_file(action="format", mode="check", file_path="Unit1.pas")

# 格式化代码字符串
delphi_file(action="format", mode="code", code="procedure Test; begin end;")
```

### 6.7 备份管理

```python
# 创建备份
delphi_file(action="backup", file_path="Unit1.pas")

# 列出备份
delphi_file(action="backup", backup_action="list", file_path="Unit1.pas")

# 恢复备份
delphi_file(action="backup", backup_action="restore", file_path="Unit1.pas", version=3)
```

### 6.8 Uses 子句管理

```python
# 添加 uses 单元
delphi_file(action="uses",
    file_path="Unit1.pas",
    uses_action="add",
    unit_name="System.SysUtils",
    uses_section="interface")

# 删除 uses 单元
delphi_file(action="uses",
    file_path="Unit1.pas",
    uses_action="remove",
    unit_name="System.SysUtils",
    uses_section="interface")
```

### 6.9 编码转换（encode）

**功能**：将 Delphi 源文件在不同编码之间转换，自动处理 BOM（Byte Order Mark）。转换前自动备份到 `__history`，确保可回退。

**适用场景**：
- 将 GBK 编码的旧项目文件转换为 UTF-8（推荐现代编码）
- 添加/移除 UTF-8 BOM（`utf-8-sig` ↔ `utf-8`）
- 跨平台协作时统一项目编码

**支持的目标编码**：

| 编码名 | 说明 |
|--------|------|
| `utf-8` | UTF-8 无 BOM（推荐） |
| `utf-8-sig` | UTF-8 带 BOM（Windows 兼容性最佳） |
| `gbk` | 简体中文 GBK（遗留项目兼容） |
| `utf-16` | UTF-16 带 BOM |
| `utf-16-le` | UTF-16 Little Endian |
| `utf-16-be` | UTF-16 Big Endian |
| `ansi` | 系统默认 ANSI 代码页（`locale.getpreferredencoding()`） |

**BOM 处理规则**：

| 源编码 → 目标编码 | BOM 行为 |
|------------------|---------|
| `utf-8-sig` → `utf-8` | 自动**剥离** BOM 字节 |
| `utf-8` → `utf-8-sig` | 自动**添加** UTF-8 BOM（`EF BB BF`） |
| `utf-16`（任意） → 其他 | 自动**剥离**原 BOM，目标编码按需重加 |
| `utf-8-sig` → `utf-8-sig` | 保持原 BOM 不变 |

```python
# UTF-8 无 BOM → UTF-8 带 BOM（Windows 兼容）
delphi_file(action="encode",
    file_path="Unit1.pas",
    to_encoding="utf-8-sig")

# GBK → UTF-8（项目统一编码）
delphi_file(action="encode",
    file_path="LegacyUnit.pas",
    from_encoding="gbk",
    to_encoding="utf-8")

# UTF-8 带 BOM → UTF-8 无 BOM（跨平台协作）
delphi_file(action="encode",
    file_path="Unit1.pas",
    to_encoding="utf-8")

# UTF-8 → UTF-16（特定平台需求）
delphi_file(action="encode",
    file_path="Unit1.pas",
    from_encoding="utf-8",
    to_encoding="utf-16")

# 预览模式（仅显示转换信息，不写盘）
delphi_file(action="encode",
    file_path="Unit1.pas",
    to_encoding="utf-8-sig",
    preview=True)
```

**参数说明**：

| 参数 | 必需 | 默认 | 说明 |
|------|------|------|------|
| `file_path` | ✅ | — | 目标文件路径（仅支持 Delphi 源文件扩展名） |
| `to_encoding` | ✅ | — | 目标编码（`utf-8`/`utf-8-sig`/`gbk`/`utf-16`/`utf-16-le`/`utf-16-be`/`ansi`） |
| `from_encoding` | ❌ | `auto` | 源编码（`auto`=自动检测，**推荐始终用 auto**；如需显式指定，请确保编码名称准确无误，否则会导致解码失败或乱码） |
| `backup` | ❌ | `True` | 转换前自动备份到 `__history` |
| `preview` | ❌ | `False` | 预览模式：只输出转换信息不写盘 |

**返回信息**：

```
转换成功：Unit1.pas
  源编码: utf-8-sig → 目标编码: utf-8
  文件大小: 1,024 B → 1,020 B (减小 4 B)
  备份已创建: __history/Unit1.pas.20260620_123456.bak
```

**安全机制**：

1. **编码合法性校验**：先通过 Python `codecs.lookup()` 验证编码名称。若 `from_encoding` 指定错误导致解码失败，工具会报错并提示纠正，**不会静默写入乱码文件**（备份在读取阶段尚未创建，文件不会被破坏）
2. **回读验证**：写入后重新读取文件，与原文对比确认无损
3. **自动备份**：转换前创建 `__history` 备份，失败后自动清理临时文件
4. **脏标记保护**：转换成功后文件标记为脏，再次写入前需重新读取

### 6.10 脏标记机制

`write`、`format`、`uses` 成功后会把文件标记为**脏**。再次写入同一文件前需要：

1. 先 `read` 重新获取行号
2. 或在每个 edit 内提供非空 `old_content`，由工具校验行号命中的旧内容
3. 或使用 `preview=True` 预览 diff 后重新 read
4. 或在确认行号无误时设置 `allow_dirty=True`

---

## 第七章：编码规范与代码审计

### 7.1 工具概述

`get_coding_rules` 提供 Delphi 编码规范的按需查询。AI Agent 在写/修改任何 Delphi 代码前，**必须先调用此工具**了解编码规范，确保生成的代码风格与项目一致。

### 7.2 获取编码规范

```python
# 获取完整工作流总览 + 章节索引（推荐首次调用）
get_coding_rules()

# 指定章节获取
get_coding_rules(section="workflow")       # 工作流总览
get_coding_rules(section="writing")        # 写代码规范
get_coding_rules(section="review")         # 代码审查
get_coding_rules(section="safety")         # 安全规范
get_coding_rules(section="agent_rules")    # AI 行为规则
get_coding_rules(section="kb_search")      # KB 搜索指南
get_coding_rules(section="format")         # 格式化规则
get_coding_rules(section="compile")        # 编译规则
get_coding_rules(section="automation")     # 自动化测试架构
get_coding_rules(section="list")           # 列出所有可用章节
```

### 7.3 章节索引

| Section | 内容 | 适用场景 |
|---------|------|---------|
| `workflow` | 工作流总览 | 首次接触项目时了解整体流程 |
| `env` | ① 环境检查 | 首次运行/环境异常时 |
| `kb_search` | ② KB 搜索 | 编码前查 API 定义 |
| `writing` | ③ 命名/格式/泛型规则（含写入规则子章节） | 写/改代码前必看 |
| `format` | ④ 格式化 | 格式化代码 |
| `compile` | ⑤ 编译 | 编译验证 |
| `review` | ⑥ 代码审核（含完整审核表） | 编译通过后审查代码 |
| `cleanup` | ⑦ 清理与验证 | 最终清理 |
| `safety` | 安全敏感操作规则 | 涉及注册表、进程、文件操作时 |
| `performance` | 性能规则 | 性能敏感路径 |
| `agent_rules` | AI 操作硬规则 | 了解 AI 的行为限制 |
| `human_collab` | ⑧ 人机协同 — 异常诊断与人工介入 | 异常诊断或需人工介入时 |
| `experience` | ⑨ 经验保存 — 知识沉淀到经验库 | 问题解决后保存经验时 |
| `kb_build` | 知识库重建 | 需要重建 KB 时 |
| `automation` | ⚙ 自动化测试架构（含提示词模板F + 经验优化闭环G） | 执行自动化 UI 测试前 |

**组合章节**：

| Section | 内容 |
|---------|------|
| `coding` | 组合：writing + format + compile（完整编码流程） |

**writing 子章节**：

| Section | 内容 |
|---------|------|
| `delphi_file_write_rule` | delphi_file 写入规则（1-indexed/edits 参数） |
| `delphi_file_dirty_flag` | 连续编辑与脏标记保护 |
| `delphi_file_output_format` | delphi_file 紧凑输出格式 |
| `delphi_file_usage_tips` | write 使用建议 |

**审核子章节**：

| Section | 内容 |
|---------|------|
| `consistency` | 一致性检查 |
| `completeness` | 完整性检查 |
| `resource_leak` | 资源泄露检查 |
| `delphi_specific` | Delphi 特有模式 |
| `common_errors` | 常见错误模式 |
| `code_quality` | 代码质量 |
| `data_conversion` | 数据转换 |
| `performance` | 性能 |
| `safety` | 安全 |

> 使用 `get_coding_rules(section="list")` 获取实时更新的完整章节列表。

### 7.4 规则优先级

```
项目自定义规则 > 默认规则
```

当 `project_path` 指定具体项目时，会先尝试加载该项目下的自定义规则文件（`CODING_RULES.mdc`）；若无自定义规则，则使用内置默认规则。

### 7.5 代码审计

`project` 工具的 audit/ast/runtime 三个 action 提供代码审计功能：

```python
# ⭐ 代码骨架提取（最省 token）
project(action="ast", base_dir="src")

# 单文件骨架提取
project(action="ast", file_path="Unit1.pas")

# 运行 50+ 静态分析规则
project(action="audit", base_dir="src")

# 单文件指定严重级别
project(action="audit",
    file_path="Unit1.pas",
    rules="P0",
    severity="warning",
    output_format="report")

# 运行时注册检查（检测遗漏 uses 单元）
project(action="runtime", base_dir="src")
```

### 7.6 审计工作流

```
① 确定审计对象
   ├─ Delphi 代码 → get_coding_rules(section="review")
   └─ Python 代码 → 按安全/MCP/并发等类别逐项检查
② 确定审计范围（全局/指定文件/新增代码）
③ 搜索相关 API 定义，评估用法
④ 调用 project(audit/ast)
   → mode="ast"（推荐，快速了解代码结构）
   → mode="audit"（深度规则检查，50+ 条规则）
⑤ AI 解读结果，排除误报，生成修复建议
⑥ project(compile) / pytest 验证
⑦ 输出审计报告
```

### 7.7 审计报告模板

```
## 源码审计报告

**项目**: <项目名称>
**审计范围**: <全局 / 文件列表>

### 概览

| 类别 | 发现数 | 严重 | 一般 | 建议 |
|------|--------|------|------|------|
| 安全 | N | N | N | N |
| 资源管理 | N | N | N | N |
| 错误处理 | N | N | N | N |
| **合计** | **N** | **N** | **N** | **N** |

### 严重问题

1. [严重] <文件:F行>: <问题描述>
   - **问题**: ...
   - **风险**: ...
   - **建议修复**: ...

### 一般问题
...

### 审计结论
<整体评估>
```

---

## 第八章：代码托管与 Git 操作

### 8.1 工具概述

`code_hosting` 是 Daofy 中所有 Git 操作和代码托管平台操作的统一入口。提供 Git 本地操作（status/add/commit/push/clone）和多平台 API 操作（Gitea/GitHub/GitLab/Gitee/GitCode）。

> ⚠️ **核心规则**：所有 Git 操作必须使用此工具，禁止用 bash 直接执行 git 命令。

### 8.2 支持的平台

| 平台 | 标识 | 说明 |
|------|------|------|
| Gitea | `gitea` | 自托管 Gitea |
| GitHub | `github` | github.com |
| GitLab | `gitlab` | GitLab CE/EE |
| Gitee | `gitee` | gitee.com 码云 |
| GitCode | `gitcode` | gitcode.net |

### 8.3 Action 速查

| Action 分组 | Action | 用途 |
|------------|--------|------|
| **Git 只读** | `git_status` | 查看仓库状态 |
| | `git_diff` | 查看工作区/暂存区差异（同时查看 diff 时可添加 staged=True） |
| | `git_show` | 查看提交或对象内容 |
| | `git_log` | 查看提交历史 |
| **Git 工作区变更** | `git_add` | 暂存文件（需 files 参数） |
| | `git_restore` | 恢复文件（有破坏性，需 files 参数） |
| | `git_unstage` | 取消暂存（需 files 参数） |
| | `git_stash` | 管理 stash（push/list/pop/apply/drop/show） |
| **Git 提交** | `git_commit` | 创建提交 |
| **Git 分支** | `git_branch` | 查看/创建/删除分支（list/create/delete） |
| | `git_switch` | 切换或创建分支（-c create） |
| | `git_merge` | 合并分支（支持 ff-only/no-commit） |
| | `git_tag` | 列出/创建/删除标签 |
| **Git 远程** | `git_fetch` | 拉取远程引用（支持 --prune） |
| | `git_pull` | 拉取并合并远程分支（支持 rebase/ff-only） |
| | `git_push` | 推送到远程 |
| | `git_push_retry` | 后台自动重试推送（可选 max_retries） |
| **Git 异步** | `git_clone` | 克隆远程仓库 |
| **平台 API — 工单** | `create_issue` | 创建工单 |
| | `get_issue` | 查看工单详情 |
| | `edit_issue` | 修改工单（title/body/state/labels） |
| | `set_labels` | 设置工单标签 |
| | `close_issue` | 关闭工单 |
| | `add_comment` | 添加评论 |
| | `list_issues` | 查询工单列表 |
| **平台 API — PR** | `create_pull` | 创建 Pull Request |
| | `get_pull` | 查看 Pull Request 详情 |
| | `list_pulls` | 查询 Pull Request 列表 |
| | `edit_pull` | 修改 Pull Request |
| | `merge_pull` | 合并 Pull Request |
| | `close_pull` | 关闭 Pull Request（不合并） |
| | `reopen_pull` | 重新打开已关闭的 Pull Request |
| **平台 API — Release** | `create_release` | 创建 Release |
| | `get_release` | 查看 Release 详情 |
| | `list_releases` | 查询 Release 列表 |
| | `edit_release` | 修改 Release |
| | `delete_release` | 删除 Release |
| **平台 API — 其他** | `create_token` | 创建访问令牌（仅 Gitea） |
| | `init_labels` | 批量初始化四维流程标签 |

### 8.4 Git 本地操作

**只读操作**（安全，不会修改仓库）：

```python
# 查看状态
code_hosting(action="git_status")

# 查看工作区差异
code_hosting(action="git_diff")

# 查看暂存区差异（staged）
code_hosting(action="git_diff", staged=True)

# 查看差异统计摘要
code_hosting(action="git_diff", stat=True)

# 查看指定文件的差异
code_hosting(action="git_diff", files=["src/Unit1.pas", "src/Unit2.pas"])

# 查看某次提交内容
code_hosting(action="git_show", ref="HEAD")

# 查看提交历史
code_hosting(action="git_log", limit=10)

# 查看指定文件的提交历史
code_hosting(action="git_log", files=["src/Unit1.pas"])
```

**工作区变更操作**（需 files 参数，避免误操作整个工作区）：

```python
# 暂存指定文件
code_hosting(action="git_add", files=["src/Unit1.pas", "src/Unit2.pas"])

# 恢复工作区文件（有破坏性，必须传 files）
code_hosting(action="git_restore", files=["src/Unit1.pas"])

# 取消暂存
code_hosting(action="git_unstage", files=["src/Unit1.pas"])

# Stash 管理
code_hosting(action="git_stash", op="push", message="wip: refactoring", include_untracked=True)
code_hosting(action="git_stash", op="list")
code_hosting(action="git_stash", op="pop", ref="stash@{0}")
code_hosting(action="git_stash", op="show", ref="stash@{0}")
```

**提交操作**：

```python
# 创建提交
code_hosting(action="git_commit", message="feat: add user authentication module")
```

**分支与标签操作**：

```python
# 列出分支
code_hosting(action="git_branch")

# 列出所有分支（含远程）
code_hosting(action="git_branch", remote_branches=True)

# 创建新分支
code_hosting(action="git_branch", branch="feature/new-ui")

# 删除分支
code_hosting(action="git_branch", branch="old-feature", delete=True)

# 切换分支
code_hosting(action="git_switch", branch="main")

# 创建并切换分支
code_hosting(action="git_switch", branch="feature/new-ui", create=True)

# 从指定起点创建分支
code_hosting(action="git_switch", branch="feature/hotfix", create=True, start_point="v1.0")

# 合并分支
code_hosting(action="git_merge", branch="feature/new-ui")

# Fast-forward only 合并
code_hosting(action="git_merge", branch="feature/bugfix", ff_only=True)

# 列出标签
code_hosting(action="git_tag")

# 创建注解标签
code_hosting(action="git_tag", tag="v1.0.0", message="Release version 1.0.0")

# 删除标签
code_hosting(action="git_tag", tag="v1.0.0-beta", delete=True)
```

**远程操作**：

```python
# 拉取远程引用
code_hosting(action="git_fetch", remote="origin", branch="main")

# 拉取并修剪已删除的远程分支
code_hosting(action="git_fetch", prune=True)

# 拉取并合并远程分支
code_hosting(action="git_pull", remote="origin", branch="main")

# 使用 rebase 方式拉取
code_hosting(action="git_pull", rebase=True, ff_only=True)

# 推送
code_hosting(action="git_push")

# 推送指定分支
code_hosting(action="git_push", branch="main", remote="origin")

# 后台自动重试推送
code_hosting(action="git_push_retry")

# 后台自动重试推送（自定义重试参数）
code_hosting(action="git_push_retry", remote="origin", retry_interval=120, max_retries=5)

# 克隆仓库
code_hosting(action="git_clone",
    url="https://github.com/user/repo.git",
    mirror="https://gitclone.com")    # 国内加速

# 克隆指定分支
code_hosting(action="git_clone",
    url="https://github.com/user/repo.git",
    branch="develop")
```

### 8.5 平台 API 操作

> ⚠️ **参数说明**：所有平台 API 操作的 `repo` 参数均使用 `"owner/repo"` 格式（如 `"myorg/myproject"`），各 handler 内部自动从该字符串中分离 owner 和 repo。

**工单操作**：

```python
# 创建工单
code_hosting(action="create_issue",
    repo="myorg/myproject",
    title="Fix login crash on Windows 11",
    body="## 问题描述\n在 Windows 11 下点击登录按钮时崩溃",
    labels=["bug", "priority-high"])

# 查看工单详情
code_hosting(action="get_issue",
    repo="myorg/myproject",
    issue_number=42)

# 修改工单（可修改 title/body/state/labels）
code_hosting(action="edit_issue",
    repo="myorg/myproject",
    issue_number=42,
    title="更新后的标题",
    body="更新后的描述",
    state="open")

# 单独设置工单标签
code_hosting(action="set_labels",
    repo="myorg/myproject",
    issue_number=42,
    labels=["bug", "priority-high", "in-progress"])

# 关闭工单
code_hosting(action="close_issue",
    repo="myorg/myproject",
    issue_number=42)

# 关闭工单并添加说明
code_hosting(action="close_issue",
    repo="myorg/myproject",
    issue_number=42,
    comment="已在 #43 中修复")

# 添加评论
code_hosting(action="add_comment",
    repo="myorg/myproject",
    issue_number=42,
    body="已在 #43 中修复")

# 查询工单列表
code_hosting(action="list_issues",
    repo="myorg/myproject",
    state="open",
    labels=["bug"])

# 初始化标签
code_hosting(action="init_labels",
    repo="myorg/myproject")
```

**Pull Request 操作**：

```python
# 创建 Pull Request
code_hosting(action="create_pull",
    repo="myorg/myproject",
    title="fix: login crash on Windows 11",
    body="修复 Windows 11 下登录按钮崩溃的问题",
    source_branch="fix/login-crash",
    target_branch="main")

# 查看 Pull Request 详情
code_hosting(action="get_pull",
    repo="myorg/myproject",
    pull_number=42)

# 列出 Pull Request
code_hosting(action="list_pulls",
    repo="myorg/myproject",
    state="open",
    limit=20)

# 修改 Pull Request（可修改 title/body/state/source_branch/target_branch）
code_hosting(action="edit_pull",
    repo="myorg/myproject",
    pull_number=42,
    title="更新后的 PR 标题",
    state="closed")

# 合并 Pull Request
code_hosting(action="merge_pull",
    repo="myorg/myproject",
    pull_number=42,
    merge_style="merge")     # merge/squash/rebase

# 关闭 Pull Request（不合并）
code_hosting(action="close_pull",
    repo="myorg/myproject",
    pull_number=42)

# 重新打开已关闭的 Pull Request
code_hosting(action="reopen_pull",
    repo="myorg/myproject",
    pull_number=42)
```

**Release 操作**：

```python
# 创建 Release
code_hosting(action="create_release",
    repo="myorg/myproject",
    tag_name="v1.0.0",
    name="Version 1.0.0",
    body="## 变更\n- 修复登录崩溃\n- 优化性能",
    draft=True,
    prerelease=False)

# 查看 Release 详情
code_hosting(action="get_release",
    repo="myorg/myproject",
    tag_name="v1.0.0")

# 列出 Release
code_hosting(action="list_releases",
    repo="myorg/myproject",
    limit=10)

# 修改 Release
code_hosting(action="edit_release",
    repo="myorg/myproject",
    tag_name="v1.0.0",
    name="Version 1.0.0 (revised)",
    body="## 变更\n- 修复登录崩溃\n- 优化性能\n- 更新文档")

# 删除 Release
code_hosting(action="delete_release",
    repo="myorg/myproject",
    tag_name="v1.0.0")
```

**令牌与其他操作**：

```python
# 创建 Gitea 访问令牌（需要 base_url + username + password）
code_hosting(action="create_token",
    base_url="https://your-gitea.com",
    username="admin",
    password="your_password",
    name="daofy-ai-token",
    scopes=["read:repository", "write:repository", "read:issue", "write:issue"])
```

### 8.6 完整工作流

```python
# ═══════════════════════════════════════════════
# 日常开发提交
# ═══════════════════════════════════════════════
delphi_file(action="write", ...)              # 编写代码
project(action="compile", ...)                # 编译验证

# 查看变更并提交
code_hosting(action="git_diff", stat=True)     # 查看变更概览
code_hosting(action="git_add", files=["."])   # 暂存
code_hosting(action="git_commit", ...)        # 提交
code_hosting(action="git_push")               # 推送

# ═══════════════════════════════════════════════
# Bug 修复完整闭环
# ═══════════════════════════════════════════════
code_hosting(action="list_issues", repo="myorg/myproject", state="open", labels=["bug"])  # 查看待处理 Bug
# → 创建分支修复
git_switch(branch="fix/login-crash", create=True)
# 修复代码
project(action="compile", ...)                # 编译验证
code_hosting(action="git_add", files=["src/login.pas"])
code_hosting(action="git_commit", message="fix: #42 login crash")
code_hosting(action="git_switch", branch="main")       # 切回主分支
code_hosting(action="git_merge", branch="fix/login-crash")  # 合并
code_hosting(action="git_push")
# 更新工单
code_hosting(action="get_issue", repo="myorg/myproject", issue_number=42)
code_hosting(action="add_comment", repo="myorg/myproject", issue_number=42, body="已在 #43 中修复")
code_hosting(action="close_issue", repo="myorg/myproject", issue_number=42)

# ═══════════════════════════════════════════════
# 功能开发 — 分支管理
# ═══════════════════════════════════════════════
code_hosting(action="git_switch", branch="feature/new-dialog", create=True)  # 创建功能分支
# 开发中...
code_hosting(action="git_stash", op="push", message="wip: unfinished change")  # 临时保存
code_hosting(action="git_switch", branch="main")       # 切换到主分支修紧急问题
# 修复紧急问题
code_hosting(action="git_stash", op="pop")              # 恢复之前的未完成变更
code_hosting(action="git_add", files=["src/dialog.pas"])
code_hosting(action="git_commit", message="feat: add new customer dialog")
code_hosting(action="git_switch", branch="main")
code_hosting(action="git_merge", branch="feature/new-dialog")
code_hosting(action="git_tag", tag="v1.1.0", message="Version 1.1.0")  # 打版本标签
code_hosting(action="git_push", branch="main")
code_hosting(action="git_push", branch="--tags")        # 推送标签

# ═══════════════════════════════════════════════
# 查看历史与调试
# ═══════════════════════════════════════════════
code_hosting(action="git_log", limit=5)                  # 最近 5 条提交
code_hosting(action="git_show", ref="abc1234")           # 查看特定提交
code_hosting(action="git_diff", files=["src/unit1.pas"]) # 查看文件当前变更
```

---

## 第九章：经验记忆管理

### 9.1 工具概述

`experience` 是 Daofy 内置的 **AI 经验记忆系统**，用于持久化存储 AI 在解决问题时发现的有效做法和技巧。

**核心理念**：AI 在编码过程中遇到的问题和解决方案不应被遗忘。经验知识库让每次"踩坑-解决"的循环都有积累。

### 9.2 Action 速查

| Action | 用途 | 必需参数 |
|--------|------|---------|
| `save` | 保存经验（自动去重） | `problem`, `solution` |
| `search` | 语义搜索经验 | `query` |
| `get` | 查看经验详情 | `id` |
| `list` | 浏览列表 | — |
| `update` | 更新经验 | `id` |
| `merge` | 合并多条经验 | `ids`（至少 2 个） |
| `prune` | 列出低价值经验 | — |
| `delete` | 删除经验 | `id` |
| `rebuild_embedding` | 重建缺失向量 | — |

### 9.3 保存经验

```python
# 基本保存
experience(action="save",
    problem="编译 Delphi 项目时 dcc32 返回 exit code 2",
    solution="检查 .dproj 中的 DCC_UnitSearchPath 是否包含所有第三方库路径，"
             "然后在 project(action=compile) 中传入 unit_search_paths 补充",
    tools_used=["project", "delphi_file"],
    tags=["Delphi", "编译", "dcc32"])

# 强制保存（跳过 >0.7 相似度拦截）
experience(action="save",
    problem="...",
    solution="...",
    force=true)
```

### 9.4 搜索经验

```python
# 语义搜索
experience(action="search",
    query="编译报错找不到文件",
    top_k=5)

# 按标签过滤搜索
experience(action="search",
    query="Delphi 编译器配置",
    tags=["Delphi", "编译"])
```

### 9.5 查看和管理

```python
# 查看经验详情
experience(action="get", id="a1b2c3d4e5f6")

# 浏览列表
experience(action="list", limit=20)
experience(action="list", tags=["Delphi"], sort_by="hit_count", limit=10)

# 更新经验
experience(action="update", id="a1b2c3d4e5f6",
    solution="更完善的解决步骤...")

# 合并多条经验
experience(action="merge",
    ids=["a1b2c3d4e5f6", "b2c3d4e5f6a7"])

# 列出低价值经验
experience(action="prune", limit=20)

# 删除经验
experience(action="delete", id="a1b2c3d4e5f6")
```

### 9.6 自动去重机制

`save()` 不是简单 INSERT，而是"先查再决定"的智能流程：

| 相似度 | 处理方式 |
|--------|---------|
| > 0.85 | **自动合并**到旧记录，不新增 |
| > 0.7 | **拦截提醒**，建议人工判断 |
| ≤ 0.7 | **正常新建** |

### 9.7 经验维护最佳实践

1. **保存前先泛化**：先 `search()` 确认是否已有同类经验，找到后用 `merge`/`update` 合并
2. **任务完成后主动合并**：新方案与旧经验相关但方式不同，手动 merge
3. **定期清理**：执行 `prune` 列出低价值记录，审查后 `delete`
4. **发现重复时抽象合并**：同类问题合并为一条抽象经验，`tags` 覆盖各类场景
5. **hit ≥ 3 规则化**：评估是否可以升级为 CODING_RULES 正式规则

---

## 第十章：Delphi RTTI 桥接

### 10.1 工具概述

`delphi_rtti` 通过 Delphi Enhanced RTTI 发现和调用 Delphi 应用程序的运行时能力。三步法：guide → discover → call。

### 10.2 前置条件

在 Delphi 项目的 `.dpr` 文件中添加自动化单元：

```pascal
program MyApp;

uses
  Vcl.Forms,                              // VCL 项目
  // 或 FMX.Forms,                        // FMX 项目
  Vcl.DaofyAutomation in 'path\to\tools\auto\Vcl.DaofyAutomation.pas',
  DaofyAutomation.Base in 'path\to\tools\auto\DaofyAutomation.Base.pas',
  // 或 Fmx.DaofyAutomation (FMX 项目)
  MainForm in 'MainForm.pas';

begin
  Vcl.DaofyAutomation.AutoStart;          // 启动自动化管道线程
  Application.Initialize;
  Application.CreateForm(TMainForm, MainForm);
  Application.Run;
  Vcl.DaofyAutomation.AutoStop;
end.
```

### 10.3 三步工作流

```python
# 第一步：获取使用指南
delphi_rtti(action="guide")

# 第二步：发现能力
delphi_rtti(action="discover",
    app_path="C:\\App\\MyApp.exe")
# 可选：限定类名、保持进程
delphi_rtti(action="discover",
    app_path="C:\\App\\MyApp.exe",
    class_name="TMainForm",
    keep_alive=True)

# 第三步：调用方法
delphi_rtti(action="call",
    app_path="C:\\App\\MyApp.exe",
    class_name="TMainForm",
    method="CreateOrder",
    params={"customerName": "张三", "amount": 100})
```

### 10.4 类型映射

| Delphi 类型 | JSON 类型 | 说明 |
|------------|----------|------|
| string (UnicodeString/AnsiString) | string | UTF-8 编码 |
| Integer, SmallInt, Int64 | integer | — |
| Single, Double, Currency | number | — |
| Boolean, ByteBool | boolean | — |
| TDateTime | string | format: date-time |
| 枚举类型 | string | 带 enum 约束 |
| 动态数组/TArray | array | 元素类型递归映射 |
| TObject 子类 | object | 有限支持 |
| Variant | [string, number, boolean, null] | — |

### 10.5 AI 注解（Custom Attributes）

在 Delphi 方法或参数上添加 `AI` 前缀的属性注解，给 AI Agent 提供更丰富的上下文：

```pascal
[AIDescription('创建客户订单，返回新订单号')]
[AIResultDescription('新创建的订单编号，失败返回 -1')]
[AIExample('CreateOrder("张三", 100) → 10001')]
function CreateOrder(
  [AIParamDescription('客户姓名')] const customerName: string;
  [AIParamDescription('订单金额(元)')] amount: Integer
): Integer;
```

| 属性 | 应用位置 | 说明 |
|------|---------|------|
| `[AIDescription('...')]` | 方法 | 功能描述 |
| `[AIResultDescription('...')]` | 方法 | 返回值说明 |
| `[AIExample('...')]` | 方法 | 调用示例 |
| `[AIParamDescription('...')]` | 参数 | 参数含义 |

---

## 第十一章：自动化测试

### 11.1 工具概述

`automate_delphi` 驱动 Delphi 程序自动化测试，支持 **GUI 截图模式**（Named Pipe）和 **控制台交互模式**（subprocess stdin/stdout）。

### 11.2 Action 速查

| Action | 模式 | 说明 |
|--------|------|------|
| `auto`（默认） | 自动检测 | 读 PE 头自动识别 GUI vs Console |
| `gui` | 命名管道 GUI 操作 | 需要链接 DaofyAutomation 单元 |
| `console` | 控制台交互 | 无需 Delphi 端改造 |

### 11.3 GUI 模式

GUI 模式通过命名管道与 Delphi 程序通信，支持以下命令：

**感知命令**（获取 UI 状态）：
| 命令 | 作用 |
|------|------|
| `capture` | 截取当前窗口截图 |
| `dumpstate` | 导出完整控件树 JSON |
| `formsum` | 窗体摘要（dumpstate 紧凑版） |
| `listwnd` | 枚举所有顶层窗口 |
| `msgscan` | 扫描 MessageBox 弹窗 |
| `dlgscan` | 扫描文件对话框状态（同步） |
| `rinspect` | RTTI 成员发现 |

**执行命令**（操作 UI）：
| 命令 | 作用 |
|------|------|
| `goto` | 导航到目标控件 |
| `click` / `rclick` / `dblclick` | 单击/右键/双击（异步） |
| `type` | 输入文本（异步） |
| `key` | 按键 Tab/Enter/Esc（异步） |
| `hover` / `move` / `drag` | 鼠标操作（异步） |
| `rcall` / `rset` | RTTI 调用方法/设置属性（异步） |
| `msgclick` / `dlgclick` / `msgclose` | 弹窗/菜单点击与关闭（`msgclose` 同步） |
| `dlgfile` | 文件对话框输入路径（同步） |
| `snapdir` | 设置截图输出目录（同步） |
| `exit` | 退出目标进程 |

**验证命令**（确认结果）：
| 命令 | 作用 |
|------|------|
| `waitfor` | 等待条件满足 |
| `wait` | 固定时间等待（毫秒） |
| `rget` | RTTI 读属性值（首选断言方式） |
| `rinspect` | RTTI 成员发现（同步，查看属性名/类型/方法，非值） |

### 11.4 GUI 模式示例

```python
# 基础自动化
automate_delphi(action="gui",
    app_path="C:\\MyApp\\Win32\\Debug\\MyApp.exe",
    script=[
        {"cmd": "goto", "target": "TLoginForm"},
        {"cmd": "type", "target": "EditUser", "value": "admin"},
        {"cmd": "key", "target": "EditPwd", "key": "Tab"},
        {"cmd": "type", "target": "EditPwd", "value": "123456"},
        {"cmd": "click", "target": "BtnLogin"},
        {"cmd": "waitfor", "target": "StatusBar",
         "prop": "Caption", "value": "登录成功", "timeout": "5000"},
        {"cmd": "capture", "target": "login_result"},
    ],
    keep_alive=True)    # 进程复用
```

### 11.5 进程复用模式

`keep_alive=true` 让进程常驻，避免反复启动：

```python
# 第一次：启动并保持
automate_delphi(app_path="MyApp.exe", script=[goto, capture], keep_alive=True)
# → 返回 process_reused:false, process_alive:true

# 第二次：复用已有进程
automate_delphi(app_path="MyApp.exe", script=[click, capture])
# → 返回 process_reused:true, process_alive:true

# 最后：发送 exit 终止
automate_delphi(app_path="MyApp.exe", script=[exit])
# → 返回 process_alive:false
```

### 11.6 Console 模式

Console 模式通过 subprocess stdin/stdout 与控制台程序交互，**无需 Delphi 端改造**：

```python
# 基本交互
automate_delphi(action="console",
    app_path="Deploy.exe",
    input="Y\n",
    expect="Deploy complete",
    args=["--silent"],
    timeout=30)

# 超时测试
automate_delphi(action="console",
    app_path="Tool.exe",
    timeout=5)
```

### 11.7 截图原理

`capture` 命令自动选择最佳截图方式：

| 场景 | 方式 |
|------|------|
| MessageBox/TaskDialog 弹窗 | `FindWindowW('#32770')` → GDI BitBlt → JPEG |
| FMX 模态对话框 | `TFmxFormState.Modal` 检测 → PaintTo |
| FMX 3D 窗体 | `TContext3D.CopyToBitmap` GPU readback |
| FMX 2D 窗体 | `TCustomForm.PaintTo(Canvas)` |
| VCL 窗体 | `GetWindowDC` + GDI BitBlt |

### 11.8 MCP 提示词模板（Prompts）

Daofy 注册了 **7 个 MCP Prompt 模板**，专为自动化测试工作流设计，在客户端支持 MCP Prompts 协议时可注入测试角色、引导代码分析和规划测试步骤。

| 模板名 | 作用 |
|--------|------|
| `automate-expert-primer` | 🎭 **注入测试专家角色**：设定身份、三层递进思考模型 |
| `automate-code-analysis` | 🔍 **代码感知分析**：读 DFM/PAS 生成控件映射表、事件分析、测试路径 |
| `automate-test-plan` | 📋 **启动测试规划**：角色设定 + 代码分析 + 结构化步骤序列 |
| `automate-step-execute` | ⚡ **单步执行协议**：前置感知 → 执行 → 等待 → 验证 |
| `automate-failure-recover` | 🔧 **失败恢复**：诊断 → 决策 → 恢复 → 学习 |
| `automate-save-experience` | 💾 **保存经验**：结构化记录成功/失败模式 |
| `automate-session-end` | 🏁 **结束会话**：保存经验、导出脚本、角色切回开发模式 |

```python
# 使用示例（通过 MCP 协议的 prompts/get）：
# 1. 注入专家角色
prompts/get name="automate-expert-primer" arguments={"app_name": "MyApp.exe", "project_path": "C:\\Project"}

# 2. 代码感知分析
prompts/get name="automate-code-analysis" arguments={"form_name": "TNewCustomerForm", "project_path": "C:\\App"}

# 3. 结合自动化测试工作流使用 —— 完整方法论见 get_coding_rules(section="automation")
```

> **注意**：MCP Prompts 是 MCP 协议的扩展功能，需要 AI 客户端支持。不与 Daofy 的 `automate_delphi` 工具冲突，可以配合使用。

---

## 第十二章：OCR 图像文字识别

### 12.1 工具概述

`ocr` 提供图像分析能力：PP-OCRv6 文字识别、截图差异对比、颜色分析、图标匹配。

> ⚠️ **可选功能**，需要安装：`pip install daofy-for-delphi[ocr]`

### 12.2 Action 速查

| Action | 用途 |
|--------|------|
| `recognize` | 完整 OCR 管线：检测 → 方向分类 → 文字识别 |
| `detect` | 仅文本框检测 |
| `status` | 查询模型加载状态和后端信息 |
| `diff` | 截图差异对比（像素级） |
| `color` | 区域颜色分析 |
| `match` | 图标模板匹配 |

### 12.3 使用示例

```python
# 查询模型状态
ocr(action="status")

# 文字识别
ocr(action="recognize", image_path="screenshot.png")

# 仅文本框检测
ocr(action="detect", image_path="screenshot.png")

# 截图差异对比
ocr(action="diff",
    baseline="before_test.png",
    current="after_test.png",
    threshold=10)

# 区域颜色分析
ocr(action="color",
    image_path="screenshot.png",
    region=[180, 170, 75, 25])    # [x, y, w, h]

# 图标匹配
ocr(action="match",
    image_path="screenshot.png",
    template_path="save_icon.png",
    threshold=0.8)
```

### 12.4 技术架构

| 组件 | 说明 |
|------|------|
| **模型** | PP-OCRv6（~65MB） |
| **推理引擎** | ONNX Runtime（Intel CPU 可选 OpenVINO 加速） |
| **图像处理** | OpenCV + Pillow |
| **首次加载** | 自动下载模型到 `data/ocr-models/` |

### 12.5 响应格式

```json
// recognize 响应
{
  "status": "ok",
  "action": "recognize",
  "count": 3,
  "results": [
    {
      "text": "确定",
      "confidence": 0.97,
      "box": [[10,20],[100,20],[100,50],[10,50]],
      "det_score": 0.85
    }
  ]
}

// diff 响应
{
  "changed": true,
  "diff_pixels": 1234,
  "diff_percent": 0.52,
  "regions": [{"bbox": [10,20,100,60], "area_pct": 0.3, "mean_diff": 45.3}]
}

// color 响应
{
  "avg_color": {"r": 255, "g": 0, "b": 0},
  "is_grayscale": false,
  "brightness": 0.33
}

// match 响应
{
  "found": true,
  "match_count": 1,
  "matches": [{"bbox": [100,200,130,230], "confidence": 0.92}]
}
```

---

## 第十三章：组件管理

### 13.1 工具概述

`manage_component` 管理 Delphi 窗体中的**组件（控件）**，支持 DFM 组件的增删改和 DFM↔PAS 自动同步。

> ⚠️ **注意**：`manage_component` 管理的是窗体上的 UI 组件（如 TButton、TEdit），与 `package` 管理的**组件包**（.dpk 包文件）是不同的概念。

### 13.2 Action 速查

| Action | 用途 | 必需参数 |
|--------|------|---------|
| `create` | 生成组件的 DFM 定义文本（编译+运行序列化） | `code` |
| `add` | 向现有 DFM 添加子组件，自动同步 PAS | `target_dfm`, `new_component_class`（与 `dfm_text` 二选一） |
| `remove` | 从 DFM 删除组件（含子树），自动同步 PAS | `target_dfm`, `component_name` |
| `modify` | 修改 DFM 中组件属性，事件变更时同步 PAS | `target_dfm`, `component_name`, `properties` |

### 13.3 DFM↔PAS 同步规则

`add`/`remove`/`modify` 操作会**自动同步**对应的 PAS 文件：

| 操作 | PAS 同步内容 |
|------|-------------|
| **add** | 新字段声明 + 事件方法桩（procedure 声明+实现） + 新增 uses 单元 |
| **remove** | 删除字段声明 + 删除事件方法（声明+实现） |
| **modify** | 事件属性变更 → 增/删/改事件方法声明（属性值不变时不同步） |

### 13.4 创建组件 DFM（create）

编译并运行指定的 Pascal 代码，从运行时的 RTTI 序列化出组件的 DFM 文本：

```python
manage_component(action="create",
    code='''function CreateComponent(AOwner: TComponent): TComponent;
var
  Btn: TButton;
begin
  Btn := TButton.Create(AOwner);
  Btn.Caption := ''OK'';
  Btn.Name := ''BtnOK'';
  Btn.Left := 100;
  Btn.Top := 50;
  Result := Btn;
end;''',
    uses=["Vcl.StdCtrls"],
    type_decl='',
    init_code='')
```

| 参数 | 必需 | 默认 | 说明 |
|------|------|------|------|
| `code` | ✅ | — | Pascal 实现代码，必须包含 `function CreateComponent(AOwner: TComponent): TComponent;` |
| `uses` | ❌ | [] | 需要引用的单元列表 |
| `type_decl` | ❌ | "" | 类型声明段（用于声明 Form 类、事件桩等） |
| `init_code` | ❌ | "" | 初始化代码（自定义 Form 类需 `RegisterClass`） |
| `compile_timeout` | ❌ | 60 | 编译超时秒数 |
| `exec_timeout` | ❌ | 15 | 执行超时秒数 |

### 13.5 添加组件（add）

向现有的 DFM 文件中添加子组件，并自动同步 PAS 的字段声明和事件方法：

```python
# 基本添加
manage_component(action="add",
    target_dfm="Unit1.dfm",
    target_pas="Unit1.pas",
    parent_name="",
    new_component_class="TButton",
    new_component_name="BtnOK",
    properties={"Caption": "确认", "Left": "100", "Top": "50",
                "OnClick": "BtnOKClick"})

# 添加时不指定名称（自动生成 Button1）
manage_component(action="add",
    target_dfm="Unit1.dfm",
    new_component_class="TButton",
    properties={"Caption": "取消"})

# 使用 DFM 文本片段添加复杂组件
manage_component(action="add",
    target_dfm="Unit1.dfm",
    dfm_text='''object Panel1: TPanel
  Left = 0
  Top = 0
  Width = 300
  Height = 200
  Caption = "Panel"
end''')
```

| 参数 | 必需 | 说明 |
|------|------|------|
| `target_dfm` | ✅ | 目标 DFM 文件路径 |
| `target_pas` | ❌ | PAS 文件路径（提供时自动同步声明） |
| `parent_name` | ❌ | 父组件名称（默认添加到根组件下） |
| `new_component_class` | ✅（与 dfm_text 二选一） | 新组件类名（如 TButton） |
| `new_component_name` | ❌ | 新组件实例名（默认自动生成如 Button1） |
| `properties` | ❌ | 属性字典（如 `{"Caption": "OK", "OnClick": "BtnClick"}`） |
| `dfm_text` | ❌ | DFM 文本片段（替代 new_component_class+properties） |

### 13.6 删除组件（remove）

从 DFM 中删除组件及其子树，同时自动删除 PAS 中对应的字段声明和事件方法：

```python
manage_component(action="remove",
    target_dfm="Unit1.dfm",
    target_pas="Unit1.pas",
    component_name="BtnCancel")
```

| 参数 | 必需 | 说明 |
|------|------|------|
| `target_dfm` | ✅ | 目标 DFM 文件路径 |
| `target_pas` | ❌ | PAS 文件路径（提供时自动同步删除） |
| `component_name` | ✅ | 要删除的组件名称 |

系统会自动处理：
- 删除 DFM 中该组件及其所有子组件
- 删除 PAS 中的字段声明（`BtnCancel: TButton;`）
- 删除 PAS 中绑定的事件方法（声明段和实现段）

### 13.7 修改组件（modify）

修改 DFM 中组件的属性值，当事件绑定变更时自动同步 PAS 声明：

```python
# 修改普通属性
manage_component(action="modify",
    target_dfm="Unit1.dfm",
    target_pas="Unit1.pas",
    component_name="BtnOK",
    properties={"Caption": "确定", "Width": "100"})

# 修改事件绑定（自动同步 PAS 声明）
manage_component(action="modify",
    target_dfm="Unit1.dfm",
    target_pas="Unit1.pas",
    component_name="BtnOK",
    properties={"OnClick": "BtnOKClickNew"})
```

| 参数 | 必需 | 说明 |
|------|------|------|
| `target_dfm` | ✅ | 目标 DFM 文件路径 |
| `target_pas` | ❌ | PAS 文件路径（事件变更时自动同步） |
| `component_name` | ✅ | 要修改的组件名称 |
| `properties` | ✅ | 属性字典（要修改的属性名和值） |

**事件同步规则**：
| 变化类型 | PAS 处理 |
|---------|---------|
| 新增事件绑定（如 `OnClick=BtnClick`） | 新增方法声明 `procedure BtnClick(Sender: TObject);` + 空实现 |
| 修改事件绑定（`OnClick=OldClick` → `NewClick`） | 删除 `OldClick` 方法 + 新增 `NewClick` 方法 |
| 删除事件绑定（移除 `OnClick` 属性） | 删除对应事件方法声明+实现 |

> 💡 **关联章节**：
> - [第六章：Delphi 文件操作](#第六章delphi-文件操作) — 了解 DFM 文件的更多读写操作和备份管理
> - [第十章：Delphi RTTI 桥接](#第十章delphi-rtti-桥接) — 了解运行时组件分析和远程调用

---

## 第十四章：组件包管理

### 14.1 工具概述

`package` 管理 Delphi 组件包的编译和安装。支持 `.dproj`/`.dpk`/`.groupproj` 格式的包文件。

### 14.2 Action 速查

| Action | 用途 |
|--------|------|
| `install`（默认） | 编译并安装组件包 |
| `list` | 列出已安装到 IDE 的组件包 |

### 14.3 安装组件包

```python
# 安装 .dpk 包
package(action="install", package_path="MyPackage.dpk")

# 安装 .dproj 包
package(action="install", package_path="MyPackage.dproj")

# 安装 .groupproj 项目组
package(action="install", package_path="MyPackage.groupproj")

# Release 配置，64 位
package(action="install",
    package_path="MyPackage.dpk",
    target_platform="win64",
    build_configuration="Release",
    timeout=300)

# 仅编译不注册（运行期包）
package(action="install",
    package_path="MyRuntime.dpk",
    install=False)
```

### 14.4 列出已安装

```python
package(action="list")
```

### 14.5 安装流程说明

| 包类型 | 处理方式 |
|--------|---------|
| **设计期包**（Design-time） | 编译 + 自动注册到 IDE 的 `Known Packages` |
| **运行期包**（Runtime-only） | 仅编译，不注册 |

---

## 第十五章：异步任务管理

### 15.1 工具概述

`async_task` 管理 Daofy 中的**后台异步任务**。耗时操作（如知识库构建、文档扫描、向量索引构建）会在后台执行，不阻塞 MCP 通信通道。

> 通常知识库构建通过 `delphi_kb(action="build", async_mode=True)` 自动触发，无需手动调用。

### 15.2 Action 速查

| Action | 用途 |
|--------|------|
| `start` | 启动异步任务 |
| `status` | 查询任务状态 |
| `result` | 获取任务结果 |
| `list` | 列出所有任务 |
| `cancel` | 取消运行中的任务 |

### 15.3 使用示例

```python
# 查询任务状态（短轮询）
async_task(action="status", task_id="task_xxx")

# 长轮询（最多等待 30 秒）
async_task(action="status", task_id="task_xxx", long_poll_seconds=30)

# 获取任务结果
async_task(action="result", task_id="task_xxx")

# 列出所有任务
async_task(action="list")

# 取消任务
async_task(action="cancel", task_id="task_xxx")
```

### 15.4 支持的任务类型

| task_type | 说明 |
|-----------|------|
| `build_knowledge_base` | 构建 Delphi 源码知识库 |
| `build_thirdparty_knowledge_base` | 构建三方库知识库 |
| `init_project_knowledge_base` | 初始化项目知识库 |
| `build_document_knowledge_base` | 构建文档知识库 |
| `build_embedding` | 构建向量索引 |

### 15.5 通知机制

Daofy 支持 **TaskStatusNotification 推送通知**——所有异步任务完成/失败/取消时，自动推送通知到 MCP 客户端，**无需轮询**。

---

## 第十六章：Daofy 自身更新管理

### 16.1 工具概述

`daofy_update` 管理 Daofy MCP Server 自身的版本检查和更新。支持两种安装模式的更新：

| 安装方式 | 更新方式 |
|---------|---------|
| **git clone** 源码安装 | `git pull` 拉取最新代码 |
| **pip install** 安装 | 提示使用 `pip install --upgrade daofy-for-delphi` |

### 16.2 Action 速查

| Action | 用途 |
|--------|------|
| `check` | 检查版本（先用缓存/快速检查，失败后自动后台重试） |
| `check_retry` | 强制提交后台自动重试版本检查任务（返回 task_id） |
| `update` | 提交后台 git pull 更新任务（单次，返回 task_id） |
| `update_retry` | 提交后台自动重试 git pull 任务（可指定重试间隔与次数，返回 task_id） |
| `version` | 显示当前版本号和安装方式（git/pip） |

### 16.3 使用示例

```python
# 检查更新（先用缓存/快速检查，失败后自动后台重试）
daofy_update(action="check")

# 强制后台重试版本检查（返回 task_id）
daofy_update(action="check_retry")

# 查看当前版本
daofy_update(action="version")

# 执行更新（git 模式，单次）
daofy_update(action="update")

# 后台自动重试 git pull（可指定参数）
daofy_update(action="update_retry", retry_interval=60, max_retries=10)

# 通过 async_task 查询后台更新进度
async_task(action="status", task_id="task_xxx")
```

### 16.4 更新流程

1. 启动时服务器自动在后台检查更新
2. 发现新版本时通过智能提示通知 AI
3. AI 询问用户是否更新
4. 用户确认后执行 `daofy_update(action="update")`
5. 更新完成后**重启 Daofy 或 AI Agent** 使新版本生效

---

## 第十七章：软著文档生成

### 17.1 工具概述

`generate_copyright` 生成软件著作权申请所需的文档，包括源代码文档、软件说明书和申请信息汇总表。

### 17.2 Action 速查

| Action | 用途 |
|--------|------|
| `generate` | 生成所有软著文档 |
| `validate` | 检查配置完整性 |
| `update_config` | 更新配置信息 |
| `status` | 检查浏览器环境 |
| `list` | 列出已生成的文件 |
| `generate_content` | 生成草稿 |
| `audit` | 审计草稿，识别驳回风险 |

### 17.3 使用示例

```python
# 检查配置
generate_copyright(action="validate")

# 更新配置
generate_copyright(action="update_config",
    config={"contact_person": "张三", "phone": "138xxxxxxxx"})

# 生成文档
generate_copyright(action="generate")

# 审计草稿
generate_copyright(action="audit")
```

---

## 第十八章：故障排除与最佳实践

### 18.1 常见问题排查

#### 编译器未找到

```python
check_environment(action="detect")   # 重新检测
# 或手动指定路径
check_environment(action="detect", search_path="D:\\Delphi\\Studio")
```

#### MCP Server 无法启动

```bash
# 检查 Python 环境
pip install -r requirements.txt
# 检查 MCP 库版本
pip show mcp
```

#### 知识库搜索无结果

```python
# 确保已构建知识库
delphi_kb(action="stats")                    # 查看统计信息
delphi_kb(action="build", kb_type="project") # 构建项目知识库
```

#### 搜索不到类/函数

- 检查 `kb_type` 是否正确（项目代码用 `project`）
- 尝试部分匹配（仅类名不含命名空间）
- 检查三方库是否已安装/构建
- 直接按文件路径搜索

#### 写入文件报错"脏标记"

```python
# 先重新读取文件获取最新行号
delphi_file(action="read", file_path="Unit1.pas")
# 或在 edit 中提供 old_content 校验
```

#### 编译事件超时

```python
# 增大 timeout 参数
project(action="compile", project_path="Project.dproj", timeout=900)
```

### 18.2 知识库存储位置

| 知识库类型 | 存储路径 |
|-----------|---------|
| Delphi 源码知识库 | `data/delphi-knowledge-base/` |
| 第三方库知识库 | `data/thirdparty-knowledge-base/` |
| 通用文档知识库 | `data/document-knowledge-base/` |
| 项目知识库 | `<项目目录>/.delphi-kb/` |
| 示例知识库 | `data/example-knowledge-base/` |
| 经验知识库 | `data/experience-knowledge-base/` |

### 18.3 知识库自动生命周期

| 机制 | 触发时机 | 说明 |
|------|---------|------|
| **启动时自动构建** | MCP Server 启动 | 自动检测 CWD 下的 `.dproj`，提交后台增量 KB 构建 |
| **热切换重建** | 用户手动 rebuild | 构建到临时目录，旧 KB 保持可查，构建完成原子 swap |
| **文件变更监听** | 用户保存 `.pas/.dfm/.dproj` | 需要 `pip install daofy-for-delphi[watcher]`，3 秒去抖后自动触发增量更新 |

### 18.4 最佳实践

#### 开发工作流

```python
# 标准 Delphi 开发工作流
get_coding_rules(section="workflow")          # ① 了解工作流
get_coding_rules(section="writing")           # ② 了解编码规范
delphi_kb(query="TStringList")               # ③ 搜索 API 定义
delphi_file(action="read", file_path=...)    # ④ 读源码确认修改点
delphi_file(action="write", edits=[...])     # ⑤ 写代码
delphi_file(action="format", file_path=...)  # ⑥ 格式化
project(action="compile", project_path=...)  # ⑦ 编译验证
get_coding_rules(section="review")           # ⑧ 审查代码
code_hosting(action="git_add", files=["."])  # ⑨ 提交代码
code_hosting(action="git_commit", ...)       # ⑩ 创建提交
code_hosting(action="git_push")              # ⑪ 推送
```

#### Git 提交信息规范

```bash
feat(scope): 新功能
fix(scope): 修复 Bug
docs(scope): 文档变更
refactor(scope): 重构
test(scope): 测试
chore(scope): 构建/工具变更
```

#### 知识库使用原则

1. **先精确搜索，后语义搜索**：精确类名 > 函数名 > 引用查询 > 语义搜索
2. **尽可能使用英文搜索**：英文 API 名比中文语义搜索准确得多
3. **搜索无结果时换名再试**：`TMainForm` → `TfrmMain` → `Form1`
4. **项目代码用 `kb_type="project"`**：默认 `all` 不包含项目知识库

#### 文件编辑安全原则

1. **多处修改合并到一次 `write`**：不要对同一文件分多次调用
2. **格式化前自动备份**：`backup=True`（默认）确保可回退
3. **脏标记保护**：写入后文件标记脏，再次写入前必须重新 read
4. **old_content 校验**：在 edit 中提供 old_content 可绕过脏标记且确保行号准确

#### 经验库维护原则

1. **保存前先泛化**：先搜索是否已有同类经验，找到后用 merge/update
2. **定期清理**：每月执行 prune 列出低价值记录
3. **hit ≥ 3 规则化**：高频经验升级为 CODING_RULES 正式规则

---

## 附录 A：快速命令参考

### 环境与配置

```python
check_environment(action="check")            # 检查编译环境
check_environment(action="detect")           # 检测编译器
```

### 知识库

```python
delphi_kb(action="stats")                                    # 查看统计
delphi_kb(query="TStringList")                               # 搜索类
delphi_kb(query="Create", search_type="function")             # 搜索函数
delphi_kb(query="JSON compare", search_type="semantic")      # 语义搜索
delphi_kb(action="build", kb_type="document")                # 构建文档 KB
delphi_kb(action="build", kb_type="project")                 # 构建项目 KB
```

### 编译与审计

```python
project(action="compile", project_path="App.dproj")          # 编译项目
project(action="compile_file", project_path="Unit1.pas")     # 语法检查
project(action="ast", base_dir="src")                        # 代码骨架
project(action="audit", base_dir="src")                      # 代码审计
```

### 文件操作

```python
delphi_file(action="read", file_path="Unit1.pas")            # 读文件
delphi_file(action="write", file_path="Unit1.pas",           # 写文件
    edits=[{"start_line": 5, "content": "  // new code\n"}])
delphi_file(action="format", file_path="Unit1.pas")          # 格式化
delphi_file(action="encode", file_path="Unit1.pas",          # 编码转换
    to_encoding="utf-8")
delphi_file(action="uses", uses_action="add",                # 添加 uses
    unit_name="System.SysUtils", file_path="Unit1.pas")
```

### 代码托管

```python
code_hosting(action="git_status")                            # 查看状态
code_hosting(action="git_diff", stat=True)                    # 查看变更摘要
code_hosting(action="git_log", limit=5)                      # 查看提交历史
code_hosting(action="git_add", files=["."])                  # 暂存
code_hosting(action="git_commit", message="feat: xxx")       # 提交
code_hosting(action="git_branch")                             # 列出分支
code_hosting(action="git_switch", branch="feature")          # 切换分支
code_hosting(action="git_merge", branch="feature")           # 合并分支
code_hosting(action="git_fetch")                              # 拉取远程引用
code_hosting(action="git_pull")                               # 拉取并合并
code_hosting(action="git_push")                              # 推送
code_hosting(action="git_tag", tag="v1.0", message="v1.0") # 创建标签
code_hosting(action="create_issue", repo="my/myrepo",       # 创建工单
    title="Bug", body="description")
code_hosting(action="get_issue", repo="my/myrepo",           # 查看工单
    issue_number=42)
code_hosting(action="edit_issue", repo="my/myrepo",          # 修改工单
    issue_number=42, labels=["bug"])
```

### 经验与更新

```python
experience(action="save", problem="...", solution="...")     # 保存经验
experience(action="search", query="...")                     # 搜索经验
daofy_update(action="check")                                 # 检查更新
daofy_update(action="check_retry")                           # 强制后台重试检查
daofy_update(action="update")                                # 后台 git pull 更新
daofy_update(action="update_retry")                          # 后台自动重试 git pull
daofy_update(action="version")                               # 查看版本
```

### 工具帮助

```python
tool_help(tool_name="delphi_file")                           # 查看工具完整帮助
tool_help(tool_name="project")                                # 查看 project 工具帮助
```

### 组件管理

```python
manage_component(action="create", code="...", uses=["Vcl.StdCtrls"])  # 创建组件 DFM
manage_component(action="add", target_dfm="Unit1.dfm",        # 添加组件
    new_component_class="TButton", properties={"Caption": "OK"})
manage_component(action="remove", target_dfm="Unit1.dfm",     # 删除组件
    component_name="BtnCancel")
manage_component(action="modify", target_dfm="Unit1.dfm",     # 修改组件属性
    component_name="BtnOK", properties={"Caption": "确定"})
```

### 高级功能

```python
delphi_rtti(action="discover", app_path="App.exe")           # RTTI 发现
delphi_rtti(action="call", app_path="App.exe",               # RTTI 调用
    class_name="TMainForm", method="CreateOrder")
automate_delphi(action="gui", app_path="App.exe",            # GUI 自动化
    script=[{"cmd":"goto","target":"TForm1"}])
automate_delphi(action="console", app_path="Tool.exe",       # 控制台交互
    input="Y\n", expect="complete")
ocr(action="recognize", image_path="screenshot.png")         # OCR 识别
package(action="install", package_path="MyPackage.dpk")      # 安装组件包
```

---

## 附录 B：环境变量

| 环境变量 | 说明 |
|---------|------|
| `PYTHONUNBUFFERED=1` | 禁用 Python 输出缓冲 |
| `PYTHONIOENCODING=utf-8` | 设置标准 I/O 编码为 UTF-8 |
| `PYTHONUTF8=1` | 启用 UTF-8 模式 |
| `TRANSFORMERS_OFFLINE=1` | 离线模式（embedding 模型已缓存时使用） |

---

## 附录 C：项目结构

```
daofy/
├── src/
│   ├── server.py              # MCP 入口点
│   ├── tools/                 # MCP 工具实现
│   │   ├── project.py         # 项目生命周期管理
│   │   ├── file_tool.py       # Delphi 文件操作
│   │   ├── knowledge_base.py  # 知识库搜索
│   │   ├── code_hosting.py    # Git/代码托管
│   │   ├── delphi_rtti.py     # RTTI 桥接
│   │   ├── environment.py     # 环境检查
│   │   ├── experience.py      # 经验记忆
│   │   └── ...
│   ├── services/              # 业务逻辑
│   │   ├── compiler_service.py
│   │   ├── automation_service.py
│   │   ├── rtti_bridge.py
│   │   └── knowledge_base/    # KB 模块
│   ├── models/                # 数据模型
│   ├── utils/                 # 工具函数
│   └── tool_docs.py           # 工具文档
├── config/
│   ├── CODING_RULES.mdc       # 编码规范
│   └── logging_config.json    # 日志配置
├── tools/
│   ├── auto/                  # DaofyAutomation 单元
│   │   ├── DaofyAutomation.Base.pas
│   │   ├── Vcl.DaofyAutomation.pas
│   │   ├── Fmx.DaofyAutomation.pas
│   │   └── DaofyAutomation.RttiDiscovery.pas
│   └── daudit/                # 代码审计引擎
├── data/                      # 知识库数据（运行时生成）
├── docs/                      # 文档
└── tests/                     # 测试用例
```

---

## 附录 D：MCP 协议资源

Daofy 提供两个 MCP 资源端点：

| 资源 URI | 说明 |
|---------|------|
| `delphi://coding-rules` | Delphi 编码规范（Markdown 格式） |
| `delphi://health` | 服务器健康状态（JSON 格式） |

```python
# 查看服务器状态 → 返回版本号、运行时长、监听器状态
# 通过 MCP resources/read 协议访问
```

---

> **版权信息**：Copyright © 2026 吉林省左右软件开发有限公司 / Equilibrium Software Development Co., Ltd, Jilin
>
> **许可证**：MIT License
>
> **联系方式**：提交 Issue 至 [GitHub](https://github.com/chinawsb/daofy) | QQ 群：250530692
