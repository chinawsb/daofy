<!-- @when: 测试右键菜单（ContextMenu/PopupMenu）弹出和菜单项选择 -->
<!-- @part-of: ui-testing -->

#### I. 右键菜单

| 要素 | 内容 |
|------|------|
| **目标** | 右键目标弹出 ContextMenu，选择菜单项 |
| **策略** | rclick 目标 → waitfor 菜单可见 → click 菜单项 → 验证 |
| **关键命令** | `rclick`, `waitfor`, `click`（`@` 菜单项） |

```json
[
  {"cmd":"rclick","target":"DBGrid1"},
  {"cmd":"waitfor","target":"TPopupMenu","prop":"Handle","value":"True","timeout":2000},
  {"cmd":"click","target":"@修改","note":"@文本匹配菜单项"},
  {"cmd":"waitfor","target":"TEditDialog","prop":"Visible","value":"True","timeout":3000},
  {"cmd":"rget","target":"EdtValue.Text","assert_expr":"len(actual)>0"},
  {"cmd":"capture","target":"context_menu_edit"},
  {"cmd":"exit"}
]
```

**陷阱**：右键在不同行/不同列弹出不同菜单 → 先 `goto`/`click` 选中特定行再 `rclick`；多级子菜单用 `@一级菜单>>二级菜单` 路径定位（如适用）。
