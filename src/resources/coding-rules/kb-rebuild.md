<!-- @when: 知识库数据缺失、需重建索引 -->
<!-- @chain: independent -->

## 知识库重建

```python
# Delphi 源码 KB（~1分钟, 163737 类/300228 函数）
delphi_kb(action="build", kb_type="delphi", rebuild=True, async_mode=true)
# 三方库 KB（~6秒, 5606 类/51265 函数）
delphi_kb(action="build", kb_type="thirdparty", rebuild=True, async_mode=true)
# 文档 KB（~6分钟, 含 DCC 错误码解释文档）
delphi_kb(action="build", kb_type="document", rebuild=True, confirm=True, async_mode=true)
# 项目 KB
delphi_kb(action="build", kb_type="project", project_path="Project.dproj", rebuild=True)

# 进度查询（long_poll ≤30s）
async_task(action="status", task_id="task_xxx")
```

> **文档 KB 重建安全**：对非空文档 KB 设 `rebuild=True` 时需追加 `confirm=True`，防止误清除已抓取的网页文档。保留旧内容可传旧源或改用增量构建。
