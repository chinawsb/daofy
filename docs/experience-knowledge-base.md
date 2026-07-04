# 经验知识库 — 设计与使用手册

> 版本：v1.0 | 最后更新：2026-06-08

---

## 目录

1. [概述](#1-概述)
2. [存储位置与结构](#2-存储位置与结构)
3. [技术架构](#3-技术架构)
4. [操作指南](#4-操作指南)
5. [自动去重机制](#5-自动去重机制)
6. [Embedding 降级策略](#6-embedding-降级策略)
7. [经验维护最佳实践](#7-经验维护最佳实践)
8. [质量保障体系](#8-质量保障体系)
9. [与知识库体系的关系](#9-与知识库体系的关系)
10. [故障排除](#10-故障排除)

---

## 1. 概述

经验知识库（Experience Knowledge Base）是 Daofy 内置的 **AI 经验记忆系统**，用于持久化存储 AI 在解决问题时发现的有效做法和技巧。

**核心理念**：AI 在编码过程中遇到的问题和解决方案不应被遗忘。经验知识库让每次"踩坑-解决"的循环都有积累，下次遇到同类问题时 AI 可直接复用，无需重新探索或请求人工介入。

基于 **SQLite** 存储，可选集成 **sentence-transformers 向量模型** 实现语义搜索，设计上支持 embedding 降级友好（无向量模型时自动回退关键词搜索）。

### 关键特性

| 特性 | 说明 |
|------|------|
| 语义搜索 | 集成向量模型，支持自然语言模糊匹配 |
| 自动去重 | embedding 相似度 > 0.85 时自动合并到旧记录 |
| 降级友好 | 无向量模型时自动降级为 LIKE 关键词搜索 |
| 线程安全 | 每线程独立 SQLite 连接，WAL 模式 |
| 零配置 | 纯 SQLite，无需 config.json |

---

## 2. 存储位置与结构

### 2.1 存储路径

```
data/experience-knowledge-base/
└── experiences.sqlite          # SQLite 数据库文件
```

经验库没有 `config.json`，纯 SQLite，零配置。

### 2.2 数据库 Schema

```sql
CREATE TABLE IF NOT EXISTS experiences (
    id          TEXT PRIMARY KEY,          -- 短 UUID (12 位 hex)
    problem     TEXT NOT NULL,             -- 问题描述
    solution    TEXT NOT NULL,             -- 解决步骤
    tools_used  TEXT DEFAULT '[]',         -- 用到的工具列表 (JSON 数组)
    context     TEXT DEFAULT '{}',         -- 上下文信息 (JSON 对象)
    tags        TEXT DEFAULT '[]',         -- 标签列表 (JSON 数组)
    embedding   BLOB,                      -- 向量嵌入 (float32 bytes, 可选)
    hit_count   INTEGER DEFAULT 1,         -- 被查看/复用次数
    score       REAL DEFAULT 1.0,          -- 质量评分
    created_at  TEXT NOT NULL,             -- 创建时间 (ISO 8601 UTC)
    updated_at  TEXT NOT NULL              -- 最后更新时间 (ISO 8601 UTC)
);

CREATE INDEX IF NOT EXISTS idx_exp_created ON experiences(created_at);
CREATE INDEX IF NOT EXISTS idx_exp_updated ON experiences(updated_at);
```

### 2.3 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PK | 短 UUID（`uuid4().hex[:12]`），唯一标识 |
| `problem` | TEXT | 问题描述，用于语义搜索和展示 |
| `solution` | TEXT | 解决步骤，可多行包含命令/代码 |
| `tools_used` | TEXT | JSON 数组，如 `["project", "delphi_file"]` |
| `context` | TEXT | JSON 对象，如 `{"project": "MyApp.dproj", "compiler": "Delphi 12"}` |
| `tags` | TEXT | JSON 数组，如 `["Delphi", "编译", "dcc32"]` |
| `embedding` | BLOB | `numpy.float32` 向量序列化，NULL 表示未生成 |
| `hit_count` | INTEGER | 被 `get()` 查看的次数，反映复用频率 |
| `score` | REAL | 质量评分，自动合并时递增 0.05 |
| `created_at` | TEXT | ISO 8601 UTC 时间戳 |
| `updated_at` | TEXT | ISO 8601 UTC 时间戳 |

---

## 3. 技术架构

| 层次 | 组件 | 说明 |
|------|------|------|
| **MCP 工具层** | `experience` 工具 (`src/tools/experience.py`) | action 分派入口，格式化输出 |
| **服务层** | `ExperienceMemoryService` (`src/services/experience_service.py`) | CRUD + 语义搜索核心逻辑 |
| **存储层** | SQLite + 可选 embedding | 线程安全连接，WAL 模式 |
| **向量引擎** | `embedding_service`（来自知识库模块） | sentence-transformers，仅模型已加载时启用 |

### 3.1 架构图

```
AI Agent
    │
    ▼
experience(action="save"|"search"|"merge"|...)
    │
    ▼
┌─────────────────────────────────────┐
│    experience.py (MCP 工具层)        │
│  · action 分派                       │
│  · 格式化输出 (_fmt_experience)       │
│  · 错误处理                           │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  ExperienceMemoryService (服务层)    │
│  · save / search / get / list       │
│  · update / merge / delete           │
│  · prune / rebuild_embeddings        │
│  · 自动去重逻辑 (>0.85 合并)         │
│  · embedding 编码/向量搜索           │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  SQLite (存储层)                     │
│  · WAL 模式                          │
│  · 每线程独立连接 (threading.local)  │
│  · busy_timeout=5000                 │
└─────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  embedding_service (向量引擎, 可选)   │
│  · sentence-transformers 模型        │
│  · encode_single / cosine_similarity │
│  · 模型未加载时降级                  │
└─────────────────────────────────────┘
```

### 3.2 线程安全

每个线程维护独立的 SQLite 连接（`threading.local()`）：

```python
def _get_conn(self):
    import sqlite3
    if not hasattr(self._local, 'conn') or self._local.conn is None:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        self._local.conn = conn
        self._init_tables(conn)
    return self._local.conn
```

- `PRAGMA journal_mode=WAL`：读写不互斥，并发性能高
- `PRAGMA busy_timeout=5000`：锁冲突时等待 5 秒
- 优雅关闭：`PRAGMA wal_checkpoint(TRUNCATE)` 后关闭连接

### 3.3 Embedding 编码

```python
def _maybe_encode(self, text: str, prefix: str = "passage"):
    """尝试编码文本为 embedding BLOB"""
    if not _embedding_ok() or encode_single is None or np is None:
        return None
    try:
        vec = encode_single(text, prefix=prefix)
        if vec is not None:
            return np.array(vec, dtype=np.float32).tobytes()
    except:
        return None
```

编码为 `float32` bytes 存入 BLOB，搜索时反序列化计算余弦相似度。

---

## 4. 操作指南

所有操作通过 `experience` MCP 工具的 `action` 参数分派。

### 4.1 `action="save"` — 保存经验

保存经验到数据库。支持自动去重合并（详见第 5 章）。

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

**参数说明**：

| 参数 | 必需 | 说明 |
|------|------|------|
| `problem` | ✅ | 问题描述（简明扼要，80 字内最佳） |
| `solution` | ✅ | 解决步骤（可多行，含具体命令/调用示例） |
| `tools_used` | ❌ | 涉及到的工具列表 |
| `context` | ❌ | 上下文 JSON，如项目路径、编译器版本 |
| `tags` | ❌ | 标签数组，用于分类筛选 |
| `force` | ❌ | 默认 false；true 跳过相似度拦截 |

### 4.2 `action="search"` — 语义搜索经验

```python
# 语义搜索（自动使用 embedding 或降级）
experience(action="search",
    query="编译报错找不到文件",
    top_k=5)

# 按标签过滤搜索
experience(action="search",
    query="Delphi 编译器配置",
    tags=["Delphi", "编译"])
```

**参数说明**：

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | ✅ | — | 搜索关键词（自然语言即可） |
| `top_k` | ❌ | 5 | 返回结果数 |
| `tags` | ❌ | — | 标签过滤（结果必须命中所有指定标签） |

**搜索流程**：
1. 如果 embedding 模型已加载 → 向量编码 query → 余弦相似度计算（扫描最近更新的 `top_k × 10` 行）→ 按相似度降序返回
2. 如果无结果但模型已加载 → 自动触发 `rebuild_embeddings()` 补全缺失向量 → 重试
3. 如果模型不可用 → 降级为 `LIKE %keyword%` 关键词搜索

**返回字段**：`id, problem, solution, tools_used, tags, similarity(匹配度, 0~1), hit_count, score, created_at, updated_at`

### 4.3 `action="get"` — 查看经验详情

```python
experience(action="get", id="a1b2c3d4e5f6")
```

自动递增 `hit_count`（记录复用次数）。

### 4.4 `action="list"` — 浏览经验列表

```python
# 最新更新在前
experience(action="list", limit=20)

# 按标签过滤 + 按使用次数排序
experience(action="list", tags=["Delphi"], sort_by="hit_count", limit=10)
```

**支持的排序字段**：`updated_at`（默认）、`created_at`、`hit_count`、`score`。

### 4.5 `action="update"` — 更新经验

```python
# 更新解决方案
experience(action="update", id="a1b2c3d4e5f6",
    solution="更完善的解决步骤...")

# 同时更新问题描述和标签（更新 problem 会重新生成 embedding）
experience(action="update", id="a1b2c3d4e5f6",
    problem="更精确的问题描述",
    tags=["Delphi", "编译", "MSBuild"])
```

### 4.6 `action="merge"` — 合并多条经验

将多条描述同一类问题的经验合并为一条，删除其余。这是去重和抽象化的主要手段。

```python
# 合并到现有记录（保留目标，删除其余）
experience(action="merge",
    ids=["a1b2c3d4e5f6", "b2c3d4e5f6a7", "c3d4e5f6a7b8"],
    keep="a1b2c3d4e5f6")

# 合并为新记录（全部删除，创建新 ID）
experience(action="merge",
    ids=["a1b2c3d4e5f6", "b2c3d4e5f6a7"])
```

**合并规则**：
| 字段 | 处理方式 |
|------|---------|
| `problem` | 所有 problem 用换行拼接 |
| `solution` | 所有 solution 用换行拼接 |
| `tags` | 去重合并 |
| `tools_used` | 去重合并 |
| `hit_count` | 累加 |
| `score` | 重置为 1.0 |
| `embedding` | 重新编码（模型可用时） |

### 4.7 `action="prune"` — 列出低价值经验

按价值分数升序排列，供 AI 检查后决定是否删除。**prune 不自动删除，只列出候选**。

```python
experience(action="prune", limit=20)
```

**价值计算公式**：

```
value = hit_count × score × time_decay
```

其中 `time_decay`：超过 30 天未更新，按半衰期衰减（每 30 天 × 0.5）。

**典型低价值模式**：
| 模式 | 说明 |
|------|------|
| `hit_count=1` 且长时间未更新 | 存了从未用过 |
| 内容过于具体 | 可泛化为更抽象的经验 |
| 已被其他经验覆盖 | 同一问题的冗余记录 |

### 4.8 `action="delete"` — 删除经验

```python
experience(action="delete", id="a1b2c3d4e5f6")
```

### 4.9 `action="rebuild_embedding"` — 重建缺失向量

当 embedding 模型在已有部分经验后才加载时，旧记录缺少 embedding 向量。此操作为所有 `embedding IS NULL` 的记录生成向量。

```python
# 显式触发重建
experience(action="rebuild_embedding")
```

**注意**：必须先通过 `delphi_kb(action="build_embedding")` 加载向量模型，否则报错。`search()` 在模型已加载但无结果时会自动触发重建，通常无需手动调用。

---

## 5. 自动去重机制

这是经验库最核心的设计。**`save()` 不是简单 INSERT，而是"先查再决定"的智能流程**：

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

### 设计意图

| 阈值 | 含义 | 处理方式 |
|------|------|---------|
| > 0.85 | 几乎同一问题 | **自动合并**，零摩擦 |
| > 0.7 | 可能相关 | **拦截提醒**，建议人工判断 |
| ≤ 0.7 | 不同问题 | **正常新建** |

### 合并时发生了什么

```python
# 自动合并的核心代码（简化）
best = merged[0]
sim = best["similarity"]
if sim > 0.85:
    merged_solution = best["solution"] + "\n" + solution
    merged_tags = list(set(best.get("tags", []) + (tags or [])))
    merged_tools = list(set(best.get("tools_used", []) + (tools_used or [])))
    # UPDATE ... SET solution=?, tags=?, tools_used=?, score=score+0.05
    # 不 INSERT，不创建新 ID
```

合并后返回的记录带有 `_merged: True` 标记，表示此次保存实际是合并到旧记录。

---

## 6. Embedding 降级策略

经验库在没有向量模型时也完全可用，只是搜索精度降低。

### 降级流程

```
search(query)
  │
  ├─ embedding 模型已加载？
  │   ├─ 是 → 语义搜索（余弦相似度排序）
  │   │      └─ 无结果？→ 自动 rebuild_embeddings() 后重试 ✅
  │   └─ 否 → LIKE 关键词降级搜索（%query%）
  │
  └─ 结果返回
```

### 各场景行为对照

| 场景 | `save()` | `search()` |
|------|----------|------------|
| 模型已加载 | 编码 embedding 存入 BLOB，执行去重合并 | 余弦相似度搜索，精准排序 |
| 模型未加载 | BLOB 为 NULL，不去重（直接 INSERT） | `LIKE %keyword%` 降级，不返回 similarity |
| 模型后加载 | — | 首次无结果时自动 `rebuild_embeddings()` 后重试 |

### 自动重建触发条件

```python
def search(self, query, top_k, tags):
    emb_results = self._search_embedding(query, top_k, tags)
    if emb_results:
        return emb_results

    # 模型可用但无结果 → 可能是旧记录缺少向量
    if _embedding_ok():
        rebuilt = self.rebuild_embeddings()
        if rebuilt.get("rebuilt", 0) > 0:
            emb_results = self._search_embedding(query, top_k, tags)
            if emb_results:
                return emb_results

    # 最终降级
    return self._search_keyword(query, top_k, tags)
```

**关键点**：
- 降级是完全透明的，上层无需关心当前使用哪种搜索模式
- 模型后加载后，首次搜索自动补全缺失向量，无需手动干预
- 也可通过 `experience(action="rebuild_embedding")` 显式触发

---

## 7. 经验维护最佳实践

### 7.1 保存前先泛化

不要保存过于具体的场景，先搜索是否已有覆盖同类问题的抽象经验。

```python
# ❌ 错误：保存具体场景
experience(action="save",
    problem="在 Unit1.pas 第 42 行把 TForm1.Caption 改成 'Hello'",
    solution="打开 Unit1.pas，找到 TForm1.FormCreate，添加 Caption := 'Hello'")

# ✅ 正确：抽象出通用问题
experience(action="save",
    problem="运行时修改 TForm.Caption 需确保在 BeforeConstruction 之后赋值",
    solution="1. 确保 Caption 赋值在 TForm.AfterConstruction 或 FormCreate 事件中\n"
             "2. 不要在 BeforeConstruction 或构造函数中设置 Caption")
```

### 7.2 任务完成后主动合并

如果刚解决的问题与已有经验高度相关但解决方式不同，用 `merge` 手动合并，而不是让它们各自独立。

```python
# 已有经验 ID: exp_abc（描述了问题 A 的旧方案）
# 新方案：更优的解决方式
# 合并两者，让一条经验包含两种方案
experience(action="merge",
    ids=["exp_abc", "exp_def"],
    keep="exp_abc")  # 保留旧 ID，融合新内容
```

### 7.3 定期清理低价值条目

```bash
# 每月执行
experience(action="prune", limit=20)
# → 列出价值最低的 20 条
# → 审查每条是否可删除
# → experience(action="delete", id="...")
```

### 7.4 发现重复时抽象合并

发现多条经验描述同一类问题（如不同工具的"消息精简"、"返回值清理"），手动合并为一条抽象经验，`tags` 覆盖各类搜索角度。

### 7.5 规则联动

经验被反复 hit 3 次以上的问题，应考虑升级为内置编码规则资源
`src/resources/coding-rules.md`（MCP Resource: `delphi://coding-rules`）中的正式规则，
让所有 AI Agent 都能受益，而非依赖经验召回。

```
hit_count ≥ 3 的经验
    → 评估是否可规则化
    → 更新 src/resources/coding-rules.md 新增规则
    → 保留经验作为参考用例
```

### 7.6 维护时机总结

| 时机 | 实践 | 说明 |
|------|------|------|
| **保存前** | 先泛化 | 调用 `search()` 确认是否已有同类经验；找到后用 `merge`/`update` 合并 |
| **任务完成** | 主动合并 | 新方案与旧经验相关但方式不同，手动 merge 避免各自独立 |
| **每月** | 清理 prune | 执行 `prune` 列出低价值记录，审查后 `delete` |
| **发现重复** | 抽象合并 | 同类问题合并为一条抽象经验，`tags` 覆盖各类场景 |
| **hit ≥ 3** | 规则化 | 评估是否可以升级为 CODING_RULES 正式规则 |

---

## 8. 质量保障体系

| 保障机制 | 层级 | 说明 |
|----------|------|------|
| **自动去重合并** | `save()` | similarity > 0.85 自动合并，> 0.7 拦截提醒 |
| **自动重建向量** | `search()` | 模型已加载但无结果时自动触发 `rebuild_embeddings()` |
| **时间衰减** | `prune_list()` | 30 天未更新的经验价值按半衰期衰减 |
| **使用计数** | `get()` | 每次查看递增 `hit_count` |
| **超时保护** | `server.py` | 30 秒超时，防止 embedding 加载阻塞 MCP 通道 |
| **线程安全** | 连接层 | 每线程独立 SQLite 连接，WAL 模式防锁 |
| **日志追踪** | 服务层 | 所有异常记录 `logger.debug`，不吞错误 |
| **单例管理** | 全局 | `get_experience_service()` 单例模式，`cleanup()` 优雅关闭 |

### 超时保护

```python
# server.py 中 experience 工具调用带 30s 超时
async def _handle_experience(arguments: dict) -> dict:
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_experience, **arguments),
            timeout=30.0,
        )
        return result
    except asyncio.TimeoutError:
        return {"status": "failed",
                "message": "experience 操作超时（30s），可能是 embedding 模型加载/下载耗时过长。"
                           "请先调用 delphi_kb(action=build_embedding) 加载模型后再使用语义搜索。"
```

### 线程安全连接管理

```python
# 每个线程独立连接
def _get_conn(self):
    if not hasattr(self._local, 'conn') or self._local.conn is None:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        self._local.conn = conn
    return self._local.conn

# 服务关闭时
def cleanup():
    if _instance is not None:
        _instance.close()
        _instance = None
```

---

## 9. 与知识库体系的关系

```
Daofy 知识库体系
│
├── Delphi 源码知识库 (data/delphi-knowledge-base/)
│   └── VCL/FMX/RTL 官方 API、类、函数搜索
│
├── 项目知识库 (.delphi-kb/)
│   └── 项目自有代码 + 三方库追踪
│
├── 通用文档知识库 (data/document-knowledge-base/)
│   └── CHM/PDF/DOCX 等文档全文搜索
│
└── ★ 经验知识库 (data/experience-knowledge-base/) ← 本文
    └── AI 解决问题的经验记忆
```

### 区别对照

| 维度 | 其他知识库 | 经验知识库 |
|------|-----------|-----------|
| **数据来源** | 工具自动构建（源码/文档扫描） | **AI 主动写入**（解决问题后保存） |
| **知识类型** | 声明性知识（"是什么"） | 过程性知识（"怎么做"） |
| **搜索方式** | 精确匹配 + 语义搜索 | 语义搜索 + 关键词降级 |
| **数据格式** | 结构化 API 定义 / 文档全文 | 自由文本（problem + solution） |
| **存储** | SQLite + config.json | 纯 SQLite，无 config.json |
| **去重** | 基于文件路径 | 基于语义相似度（> 0.85） |
| **维护** | 自动增量更新 | 需要 AI 主动 prune/merge |

### 共享组件

经验知识库复用了 Delphi 知识库的 `embedding_service` 做向量编码，因此：

- 向量模型只需加载一次（通过 `delphi_kb(action="build_embedding")`），两个知识库共享
- `embedding_service` 的 `encode_single()` 和 `cosine_similarity()` 为经验库和知识库共用
- 模型加载状态检查 `_embedding_model_loaded()` 是全局的

---

## 10. 故障排除

| 现象 | 原因 | 解决 |
|------|------|------|
| `save` 提示"发现高相似度经验" | 找到 > 0.7 匹配，非 force 模式拦截 | 用 `merge`/`update` 合并到已有记录，或传 `force=true` |
| 语义搜索返回空结果 | embedding 模型未加载或旧记录缺少向量 | 自动触发重建或降级为关键词搜索，无需手动干预 |
| 搜索总用关键词降级 | embedding 模型从未加载 | 调用 `delphi_kb(action="build_embedding")` 加载模型 |
| `save` 后多条内容重复 | 同一问题反复 force 保存 | 用 `merge` 合并，或 `prune` 后 `delete` 冗余 |
| 数据库锁定 | 多线程竞争，WAL 未生效 | 检查 `PRAGMA journal_mode` 是否为 WAL |
| 链接超时 30s | embedding 模型首次加载耗时过长 | 后台加载完成后重试，或先调用 `build_embedding` 预热 |
| `merge` 返回 None | 传入的 ID 无效或不足 2 条 | 先用 `list`/`search` 确认 ID 存在 |
| `rebuild_embedding` 报错 | embedding 模型未加载 | 先调用 `delphi_kb(action="build_embedding")` |
| 经验被误删 | 意外调用 `delete` | 经验库无回收站，建议 `prune` 列出后人工确认再删除 |

---

## 附录 A：源码文件位置

| 文件 | 用途 |
|------|------|
| `src/tools/experience.py` | MCP 工具入口，action 分派，格式化输出 |
| `src/services/experience_service.py` | 核心服务：`ExperienceMemoryService` 类 |
| `src/server.py` | 工具注册 + 超时保护 |
| `src/tool_docs.py` | `experience` 工具的 help 文档 |
| `data/experience-knowledge-base/experiences.sqlite` | 数据库文件（自动创建） |

## 附录 B：数据库诊断

通过 SQLite 命令行可直接查看经验库状态，**仅限诊断只读操作**，禁止手动写操作：

```bash
# 查看经验总数
sqlite3 data/experience-knowledge-base/experiences.sqlite "SELECT COUNT(*) FROM experiences;"

# 查看 embedding 覆盖率
sqlite3 data/experience-knowledge-base/experiences.sqlite \
  "SELECT COUNT(*) AS total,
          SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS with_vec,
          SUM(CASE WHEN embedding IS NULL THEN 1 ELSE 0 END) AS without_vec
   FROM experiences;"

# 查看热门经验 TOP 10
sqlite3 data/experience-knowledge-base/experiences.sqlite \
  "SELECT id, problem, hit_count, score, updated_at
   FROM experiences ORDER BY hit_count DESC LIMIT 10;"
```
