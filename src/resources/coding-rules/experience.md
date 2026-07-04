<!-- @when: 问题解决后需保存经验；排查困难问题时查经验库 -->
<!-- @chain: before=maintenance.md, after=human-collab.md -->

## ⑪ 经验保存 — 将知识沉淀到经验库

`experience` 工具将有效方法持久化到经验知识库，下次直接复用。

### 必须保存的场景

| 场景 | 优先级 |
|------|--------|
| 人工介入解决后 | 🔴 必须 |
| 非显而易见 Bug 修复 | 🔴 必须 |
| 编译器/工具链兼容问题 | 🟡 推荐 |
| 不常见 API 用法 | 🟡 推荐 |
| 新编码规则触发 | 🟡 推荐 |

### 保存流程（搜索 → 泛化 → 保存）

```
① search(query=..., tags=...) 查是否已有同类经验
   已有 → ③ update/merge
   无   → ② 泛化问题描述（抽象通用场景，不用具体文件名）
          ③ save(problem=..., solution=..., tags=...)
          ④ rebuild_embedding（可选，模型后加载时自动补全）
          ⑤ search 验证可召回
```

### 自动去重逻辑

```
save(problem, solution)
 ├─ similarity > 0.85 → 自动合并到旧记录（solution 拼接, tags 去重, score +0.05）
 ├─ similarity > 0.7  → 拦截提醒，建议 merge/update；传 force=true 跳过
 └─ similarity ≤ 0.7  → 新建记录
```

### 质量规范
| 维度 | 要求 | 反例 |
|------|------|------|
| problem | 含关键触发条件的通用场景 | `Form1 报错` |
| solution | 步骤化，可复现 | `改一下配置` |
| tags | 3~5 标签覆盖多角度 | `["bug"]` |

### 定期维护
- **prune**: 价值 = hit_count × score × time_decay；30 天半衰期衰减
- **merge**: 同类经验合并，problem/solution 拼接，tags/tools_used 去重
- hit_count ≥ 3 → 评估升级为编码规则

### Embedding 降级策略
- 模型未加载：save() 不存向量，search() 用 LIKE 降级
- 模型后加载：首次 search() 自动触发生成缺失向量
- 手动重建：`experience(action="rebuild_embedding")`
