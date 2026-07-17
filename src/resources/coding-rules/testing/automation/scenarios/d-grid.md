<!-- @when: 测试列表/表格的新增、选中、编辑、删除行操作 -->
<!-- @part-of: ui-testing -->

#### D. 列表/表格行操作

| 要素 | 内容 |
|------|------|
| **目标** | 新增、选中、编辑、删除列表行，验证数据变更 |
| **策略** | click 新增 → 填写 → click 保存 → rget 首行内容验证 → click 编辑/删除 → 状态确认 |
| **关键命令** | `rget` 读单元格, `click` 选中行, `waitfor` 确认状态 |

```json
[
  {"cmd":"goto","target":"TGridForm"},
  {"cmd":"rget","target":"DBGrid1.Columns[0].Title.Caption","note":"读表头,确认网格类型"},
  {"cmd":"click","target":"BtnAddRow"},
  {"cmd":"waitfor","target":"TEditDialog","prop":"Visible","value":"True","timeout":3000},
  {"cmd":"type","target":"EdtValue","text":"新数据"},
  {"cmd":"click","target":"BtnOK"},
  {"cmd":"waitfor","target":"TGridForm","prop":"Visible","value":"True","timeout":3000},
  {"cmd":"rget","target":"DBGrid1.DataSource.DataSet.RecordCount","assert_expr":"int(actual)>0"},
  {"cmd":"capture","target":"grid_after_add"},
  {"cmd":"exit"}
]
```

**陷阱**：DBGrid 行号在增删后变化 → 用 DataSet.RecNo 定位而非假设行号；删除前的确认框用 `msgscan`+`dlgclick` 处理。
