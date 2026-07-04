<!-- @when: 测试树控件（TreeView/VirtualStringTree）的展开/折叠/选中 -->
<!-- @part-of: ui-testing -->

#### E. 树形导航

| 要素 | 内容 |
|------|------|
| **目标** | 展开/折叠树节点，选中叶子节点 |
| **策略** | click 展开 → waitfor 子节点可见 → click 选中叶子 → capture |
| **关键命令** | `click`（`@` 节点定位）, `waitfor`, `capture` |

```json
[
  {"cmd":"goto","target":"TTreeForm"},
  {"cmd":"click","target":"TreeView1@客户管理","note":"click@节点文本展开"},
  {"cmd":"waitfor","target":"TreeView1","prop":"Items.Count","value":"3","timeout":3000},
  {"cmd":"click","target":"TreeView1@张三"},
  {"cmd":"waitfor","target":"PanelDetail","prop":"Visible","value":"True","timeout":3000},
  {"cmd":"rget","target":"EdtDetailName.Text","assert_expr":"actual=='张三'"},
  {"cmd":"capture","target":"tree_selected"},
  {"cmd":"exit"}
]
```

**陷阱**：`@` 节点匹配是首次匹配 → 同名节点时用 `expand` 命令展开父节点再选；虚拟树节点需 scroll 后才加载。
