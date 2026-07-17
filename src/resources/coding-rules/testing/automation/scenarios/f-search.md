<!-- @when: 测试搜索/筛选功能，包括命中、未命中和结果列表更新 -->
<!-- @part-of: ui-testing -->

#### F. 搜索/筛选

| 要素 | 内容 |
|------|------|
| **目标** | 输入搜索条件，验证结果列表/状态变化 |
| **策略** | type 搜索关键词 → waitfor 结果更新 → rget 结果数 → capture |
| **关键命令** | `type`, `waitfor`, `rget`, `capture` |

```json
[
  {"cmd":"type","target":"EdtSearch","text":"张三"},
  {"cmd":"waitfor","target":"DBGrid1","prop":"DataSource.DataSet.RecordCount","value":"1","timeout":5000},
  {"cmd":"rget","target":"DBGrid1.DataSource.DataSet.RecordCount","assert_expr":"int(actual)>=1"},
  {"cmd":"capture","target":"search_result"},
  {"cmd":"type","target":"EdtSearch","text":"不存在的关键词","note":"测试无结果场景"},
  {"cmd":"waitfor","target":"DBGrid1","prop":"DataSource.DataSet.RecordCount","value":"0","timeout":5000},
  {"cmd":"rget","target":"StatusBar.Caption","assert_expr":"'无' in actual or '0' in actual"},
  {"cmd":"capture","target":"search_empty"},
  {"cmd":"exit"}
]
```

**陷阱**：搜索输入有 debounce（300ms-1s）→ waitfor 超时设 5s 以上；清除搜索后需等数据恢复。
