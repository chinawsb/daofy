<!-- @when: 填写表单字段（文本框/下拉框/日期选择）并提交流程 -->
<!-- @part-of: ui-testing -->

#### C. 表单数据录入

| 要素 | 内容 |
|------|------|
| **目标** | 填写表单字段（文本框/下拉框/日期选择）并提交 |
| **策略** | type 文本 → click 下拉选项 → click 提交 → waitfor 结果 → rget 验证写入 |
| **关键命令** | `type`, `click`（含 `@` 选项点击）, `waitfor`, `rget` |

```json
[
  {"cmd":"goto","target":"TEditCustomerForm"},
  {"cmd":"type","target":"EdtName","text":"张三"},
  {"cmd":"type","target":"EdtPhone","text":"13800138000"},
  {"cmd":"click","target":"cbCity@北京","note":"下拉框选项点击: ControlName@ItemCaption"},
  {"cmd":"click","target":"BtnSave"},
  {"cmd":"waitfor","target":"StatusBar","prop":"Caption","value":"保存成功","timeout":5000},
  {"cmd":"rget","target":"EdtName.Text","assert_expr":"actual=='张三'","note":"验证回填"},
  {"cmd":"capture","target":"form_saved"},
  {"cmd":"exit"}
]
```

**陷阱**：保存前字段验证会弹提示框 → 先 `msgscan` 检测再继续；日期选择器用 `type` + 文本而非 click 日历。
