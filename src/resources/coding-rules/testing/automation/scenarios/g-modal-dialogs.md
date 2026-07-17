<!-- @when: 处理 MessageBox / OpenDialog / 确认框等模态对话框 -->
<!-- @part-of: ui-testing -->

#### G. 模态对话框 — MessageBox / OpenDialog / 确认框

| 要素 | 内容 |
|------|------|
| **目标** | 操作弹出对话框：确认、取消、选择文件 |
| **策略** | 触发弹出动作 → msgscan 检测 → dlgclick 响应 → 验证后续状态 |
| **关键命令** | `msgscan`, `dlgclick`, `msgclose`, `waitfor` |

```json
[
  {"cmd":"click","target":"BtnDelete"},
  {"cmd":"msgscan","expected":"删除确认对话框","assert_expr":"actual=='OK'","note":"检测到MessageBox返回OK,否则NOD"},
  {"cmd":"dlgclick","target":"btnYes","note":"点击 MessageBox 的『是』"},
  {"cmd":"waitfor","target":"StatusBar","prop":"Caption","value":"删除成功","timeout":5000},
  {"cmd":"rget","target":"DBGrid1.DataSource.DataSet.RecordCount","assert_expr":"int(actual)==0","note":"确认行已删除"},
  {"cmd":"capture","target":"dialog_after_delete"},
  {"cmd":"exit"}
]
```

**OpenDialog 文件选择**：
```json
[
  {"cmd":"click","target":"BtnImport"},
  {"cmd":"waitfor","target":"TOpenDialog","prop":"Visible","value":"True","timeout":3000},
  {"cmd":"dlgfile","target":"C:\\data\\import.xlsx","note":"dlgfile 直接写入文件路径+回车"},
  {"cmd":"waitfor","target":"StatusBar","prop":"Caption","value":"导入完成","timeout":10000},
  {"cmd":"capture","target":"import_done"},
  {"cmd":"exit"}
]
```

**陷阱**：`msgscan` 只检测 MessageBox（`MessageDlg`/`ShowMessage`），不检测自定义 Form 弹窗 → 自定义弹窗用 `waitfor`+`click`；OpenDialog 路径用 `\\` 而非 `/`。

> 现代 Windows 对话框（IFileDialog）的检测见 [j-directui.md](j-directui.md) 的 J0-J2。
