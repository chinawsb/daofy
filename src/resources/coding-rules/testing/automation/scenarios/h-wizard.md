<!-- @when: 测试多步向导（Wizard）的步骤切换和数据传递 -->
<!-- @part-of: ui-testing -->

#### H. 多步向导（Wizard）

| 要素 | 内容 |
|------|------|
| **目标** | 按序完成向导每一步 |
| **策略** | step1 填 → click Next → waitfor step2 → step2 填 → click Finish → 验证结果 |
| **关键命令** | `waitfor` 检测步骤页切换, `rget` 验证每步数据 |

```json
[
  {"cmd":"goto","target":"TWizardForm"},
  {"cmd":"type","target":"EdtName","text":"项目A"},
  {"cmd":"click","target":"BtnNext"},
  {"cmd":"waitfor","target":"TWizardForm.PageControl","prop":"ActivePageIndex","value":"1","timeout":3000},
  {"cmd":"type","target":"EdtDescription","text":"描述文本"},
  {"cmd":"click","target":"BtnFinish"},
  {"cmd":"waitfor","target":"TResultForm","prop":"Visible","value":"True","timeout":5000},
  {"cmd":"rget","target":"ResultLabel.Caption","assert_expr":"'成功' in actual"},
  {"cmd":"capture","target":"wizard_done"},
  {"cmd":"exit"}
]
```

**陷阱**：Wizard 每步可能有异步验证 → waitfor 超时设足够长；点 Finish 后如果异步处理未完成（如生成报表），等状态栏而非 Form 切换。
