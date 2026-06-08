# Delphi Knowledge Base — 知识库搜索与管理

> 版本：v1.0 | 最后更新：2026-06-08

---

## 目录

1. [概述](#1-概述)
2. [知识库类型](#2-知识库类型)
3. [操作指南](#3-操作指南)
4. [搜索策略](#4-搜索策略)
5. [知识库构建](#5-知识库构建)
6. [向量索引（Embedding）](#6-向量索引embedding)
7. [文档知识库](#7-文档知识库)
8. [技术架构](#8-技术架构)
9. [故障排除](#9-故障排除)

---

## 1. 概述

`delphi_kb` 是 Daofy 的知识库搜索与管理工具。它整合了 Delphi 官方源码、项目代码、第三方库和通用文档四大知识库，支持类/函数/语义等多种搜索方式。

**核心用途**：AI 编写 Delphi 代码前，先查知识库确认 API 定义，避免凭空编造。

### 四大知识库一览

| 知识库 | 数据量 | 用途 |
|--------|--------|------|
| Delphi 源码 | 163,737 类 / 300,228 函数 | 查 VCL/FMX/RTL 官方 API |
| 项目知识库 | 项目自定 | 查当前项目自有代码 |
| 第三方库 | 5,724 类 / 28,801 函数 | 查三方组件 API |
| 通用文档 | 160,328 篇 | 查 Delphi 帮助文档/CHM |

### 统计信息

```
Delphi 源码: 2,798 文件, 163,737 类, 300,228 函数, 260 MB
第三方库:   1,800 文件, 5,724 类, 28,801 函数, 27 MB
通用文档:   160,328 文件, 1,306 MB
```

---

## 2. 知识库类型

### 2.1 类型对照表

| kb_type | 名称 | 存储路径 | 是否需要 project_path |
|---------|------|---------|---------------------|
| `delphi` | Delphi 官方源码 | `data/delphi-knowledge-base/` | ❌ |
| `project` | 项目自有代码 | `<项目目录>/.delphi-kb/` | ✅（或自动检测） |
| `thirdparty` | 第三方组件 | `data/thirdparty-knowledge-base/` | ❌ |
| `document` | 通用文档 | `data/document-knowledge-base/` | ❌ |
| `all`（默认） | 全部 | — | — |

### 2.2 项目路径自动检测

不传 `project_path` 时自动扫描当前工作目录及父目录下的 `.dproj`：

- 找到唯一 `.dproj` 时自动使用
- 多个同名时匹配目录名

```python
# 依赖自动检测
delphi_kb(query="TfrmMain", kb_type="project")

# 显式指定
delphi_kb(query="TfrmMain", kb_type="project", project_path="C:/MyProject/Project.dproj")
```

### 2.3 存储结构

每个知识库目录包含：
- `documents.sqlite` / `knowledge_base.sqlite` — SQLite 数据库
- `config.json` — 配置文件（首次构建自动生成）
- 知识库配置支持自定义数据库、源码路径、构建参数

---

## 3. 操作指南

### 3.1 `action="search"` — 搜索

```python
# 搜索类
delphi_kb(query="TStringList")

# 搜索函数
delphi_kb(query="Create", search_type="function")

# 语义搜索（需要先构建向量索引）
delphi_kb(query="如何创建数据库连接", search_type="semantic")

# 搜索项目代码
delphi_kb(query="TfrmMain", kb_type="project", project_path="Project.dproj")

# 搜索 Delphi 官方 API
delphi_kb(query="TCustomADODataSet", kb_type="delphi")

# 搜索引用（评估修改影响）
delphi_kb(query="TStringList", search_type="reference")
```

**参数说明**：

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | ✅ | — | 搜索关键词 |
| `kb_type` | ❌ | all | all/delphi/project/thirdparty/document |
| `search_type` | ❌ | — | function/procedure/class/record/semantic/reference/all 等 |
| `top_k` | ❌ | 200 | 最大返回结果数（最大500） |
| `project_path` | ❌ | 自动检测 | 项目路径（project/thirdparty 时需要） |
| `content_type` | ❌ | — | 文档类型过滤（document 时使用） |

### 3.2 `action="stats"` — 查看统计

查看各知识库的文件数、类数、函数数、末次构建时间。

```python
delphi_kb(action="stats")
```

### 3.3 `action="read"` — 读取内容

读取文档内容或源码文件。

```python
# 按文档 URL/doc_id 读取
delphi_kb(action="read", url="...")
delphi_kb(action="read", doc_id="...")

# 按文件路径读取
delphi_kb(action="read", file_path="System.SysUtils.pas", offset=0, limit=1000)
```

### 3.4 `action="scan"` — 扫描文档

扫描指定目录添加文档到知识库。

```python
delphi_kb(action="scan",
    kb_type="document",
    directory="C:\Docs\Delphi",
    extensions=[".txt", ".md", ".html"],
    max_workers=4)
```

### 3.5 `action="web"` — 添加网页

```python
delphi_kb(action="web",
    url="https://docwiki.embarcadero.com/",
    max_pages=50,
    max_depth=2)
```

### 3.6 `action="build_embedding"` — 构建向量索引

详见第 6 章。

---

## 4. 搜索策略

### 4.1 优先级（写代码前的标准搜索流程）

```
⭐1  delphi_kb(query="TStringList")           精确类名搜索
     └─ 无结果？→ 换名再试
⭐2  delphi_kb(query="TMainForm")             换名（TMainForm→TfrmMain）
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

> `search_type="function"` 同时匹配函数（FF）和过程（FP）。`search_type="procedure"` 只查过程。

### 4.2 KB 搜不到的排查

```
搜不到类/函数 → 检查 kb_type 是否正确（项目代码用 project）
             → 尝试部分匹配（仅类名不含命名空间）
             → 检查三方库是否已安装/构建
             → 直接按文件路径搜索 System.SysUtils → 搜文件名
             → 直接读源码：delphi_file(action="read", ...)
```

### 4.3 与 delphi_file 配合

```python
# 先搜 KB 确认 API
delphi_kb(query="TButton", kb_type="delphi")

# 再读官方源码看具体实现
delphi_file(action="read", search_type="class", type_name="TButton")

# 项目代码
delphi_file(action="read", search_type="class",
    type_name="TfrmMain", search_in="project", project_path="...")
```

---

## 5. 知识库构建

### 5.1 构建命令

```python
# Delphi 源码 KB（~1分钟，163737类/300228函数）
delphi_kb(action="build", kb_type="delphi", rebuild=True, async_mode=True)

# 三方库 KB（~6秒，5606类/51265函数）
delphi_kb(action="build", kb_type="thirdparty", rebuild=True, async_mode=True)

# 文档 KB（~6分钟，160328文档）
delphi_kb(action="build", kb_type="document", rebuild=True, async_mode=True)

# 项目 KB
delphi_kb(action="build", kb_type="project",
    project_path="Project.dproj", rebuild=True)
```

### 5.2 参数说明

| 参数 | 说明 |
|------|------|
| `async_mode` | 默认 true，异步执行不阻塞 MCP 通道 |
| `rebuild` | 强制完全重建（默认 false） |
| `incremental` | 增量更新，只处理变更的文件（默认 false） |
| `build_thirdparty` | 构建项目 KB 时同时构建三方库 KB（默认 true） |
| `build_project` | 是否构建项目 KB（默认 true） |
| `version` | 指定 Delphi 版本 |
| `directory` | 扫描目录（build document 时可指定，默认自动检测 Delphi 帮助目录） |
| `extensions` | 文件扩展名过滤（如 `[".chm"]`） |

### 5.3 启动时自动构建

MCP Server 启动时自动检测 CWD 下的 `.dproj`，提交后台增量 KB 构建（不阻塞 MCP 就绪）。

### 5.4 热切换重建

构建到临时目录 `.delphi-kb-tmp-{ts}/`，旧 KB 在构建期间保持可查，构建完成原子 swap。

---

## 6. 向量索引（Embedding）

### 6.1 概述

向量索引基于 sentence-transformers 模型，将文本编码为向量，实现**语义搜索**——你搜"怎么创建数据库连接"也能匹配到 `TADOConnection.Create`。

### 6.2 加载模型

```python
delphi_kb(action="build_embedding", async_mode=True)
```

首次加载会下载模型（耗时数分钟），用 `async_mode=True` 异步执行。

### 6.3 加载后的效果

| 功能 | 模型未加载 | 模型已加载 |
|------|-----------|-----------|
| 知识库 `search_type="semantic"` | 降级为倒排索引 | 真语义搜索，余弦相似度排序 |
| 经验库 save | 不去重 | 自动 >0.85 去重合并 |
| 经验库 search | LIKE 关键词降级 | 语义向量搜索 |

### 6.4 注意事项

- **只需加载一次**，知识库和经验库共享同一 embedding 模型
- 模型未加载时所有功能**完全可用**，只是搜索精度降低
- 加载过程是异步的，通过 `async_task` 查询进度
- 旧记录（模型加载前保存的）缺少向量，下次搜索时会自动补全

---

## 7. 文档知识库

### 7.1 支持格式

| 格式 | 必需依赖 |
|------|---------|
| TXT / MD / HTML | 内置支持 |
| DOCX | `python-docx`（可选） |
| DOC | `antiword`/`catdoc`（可选） |
| CHM | 需要 7-Zip（可用 `tools/7z/` 免安装版） |
| PDF | `PyMuPDF`（推荐）或 `pdfplumber`（备选） |
| EPUB / HLP | 内置支持 |
| 网页 | `beautifulsoup4`, `html2text`, `lxml`, `requests` |

### 7.2 构建 Delphi 帮助文档知识库

```python
# 自动检测最新安装的 Delphi 帮助目录
delphi_kb(action="build", kb_type="document",
    extensions=[".chm"], async_mode=True)

# 手动指定目录
delphi_kb(action="build", kb_type="document",
    directory="C:\Program Files (x86)\Embarcadero\Studio\23.0\Help\Doc",
    extensions=[".chm"], async_mode=True)
```

**版本对照**：37.0=Delphi 13, 23.0=Delphi 12, 22.0=Delphi 11, 21.0=Delphi 10.4, 20.0=Delphi 10.3

### 7.3 网页抓取参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_pages` | 100 | 最大抓取页数 |
| `max_depth` | 3 | 最大抓取深度 |
| `domain_filter` | — | 域名过滤 |
| `url_pattern` | — | URL 模式过滤 |
| `exclude` | — | 排除目录列表 |

---

## 8. 技术架构

```
AI Agent
    │
    ▼
delphi_kb(action="search"|"build"|"stats"|...)
    │
    ▼
┌───────────────────────────────────────┐
│       src/tools/knowledge_base.py       │
│  action 分派 + 多 KB 查询路由            │
└──────┬──────────┬──────────┬───────────┘
       │          │          │
       ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ Delphi   │ │ Project  │ │ Document │
│ KB       │ │ KB       │ │ KB       │
├──────────┤ ├──────────┤ ├──────────┤
│· RTL/VCL │ │· 项目源码│ │· CHM/PDF │
│· FMX/api │ │· 三方库  │ │· TXT/MD  │
│· 官方源码│ │· 增量更新│ │· 网页    │
└──────────┘ └──────────┘ └──────────┘
       │
       ▼
┌───────────────────────────────────────┐
│    embedding_service (向量引擎)         │
│  · sentence-transformers               │
│  · encode_single / cosine_similarity   │
│  · 经验库复用同一模型                   │
└───────────────────────────────────────┘
```

---

## 9. 故障排除

| 现象 | 原因 | 解决 |
|------|------|------|
| 搜索无结果 | KB 未构建 | `delphi_kb(action="build", ...)` |
| 搜不到类/函数 | kb_type 不对 | 项目代码用 `kb_type="project"` |
| 语义搜索不准确 | 向量索引未构建 | `delphi_kb(action="build_embedding")` |
| 构建 KB 超时 | 数据量大 | 用 `async_mode=True` 异步执行 |
| 构建 KB 失败 | 三方库路径不对 | 检查 `DCC_UnitSearchPath` 配置 |
| CHM 无法解析 | 未安装 7-Zip | 将 7z.exe 放到 `tools/7z/` 目录 |
| 文档 KB 搜索慢 | 未建 FTS5 索引 | 重建时用 `rebuild=True` |
