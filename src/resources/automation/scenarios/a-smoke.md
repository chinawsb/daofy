<!-- @when: 验证程序可启动、主窗体渲染、关键控件就位 -->
<!-- @part-of: ui-testing -->

#### A. 冒烟测试 — 验证主窗体正常启动

| 要素 | 内容 |
|------|------|
| **目标** | 确认程序可启动、主窗体渲染、关键控件就位 |
| **策略** | goto 主窗体 → rget 关键控件状态 → capture 快照 → exit |
| **关键命令** | `goto`, `rget`, `capture`, `exit` |

```json
[
  {"cmd":"goto","target":"TMainForm","note":"等主窗体就绪,默认超时5s"},
  {"cmd":"rget","target":"MainForm.Caption","assert_expr":"len(actual)>0","note":"主窗体标题非空"},
  {"cmd":"rget","target":"BtnSearch.Enabled","assert_expr":"actual=='True'","note":"关键按钮可用"},
  {"cmd":"rget","target":"StatusBar.Panels[0].Text","note":"状态栏内容,不断言仅记录"},
  {"cmd":"capture","target":"smoke_main","note":"基线截图"},
  {"cmd":"exit"}
]
```

**陷阱**：启动动画/闪屏会导致 goto 超时 → 设超时 15s 或用 `waitfor` 等待闪屏消失。
