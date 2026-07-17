<!-- @when: 测试登录流程（用户名密码输入、登录状态切换、失败提示） -->
<!-- @part-of: ui-testing -->

#### B. 登录流程

| 要素 | 内容 |
|------|------|
| **目标** | 验证用户名密码输入、登录状态切换、失败提示 |
| **策略** | type 凭据 → click 登录 → waitfor 状态变化 → rget 验证 → capture |
| **关键命令** | `goto`, `type`, `click`, `waitfor`, `rget`, `capture` |

```json
[
  {"cmd":"goto","target":"TLoginForm"},
  {"cmd":"type","target":"EdtUserName","text":"admin"},
  {"cmd":"type","target":"EdtPassword","text":"123456"},
  {"cmd":"click","target":"BtnLogin"},
  {"cmd":"waitfor","target":"TMainForm","prop":"Visible","value":"True","timeout":8000},
  {"cmd":"rget","target":"StatusBar.Caption","assert_expr":"'成功' in actual"},
  {"cmd":"capture","target":"login_success"},
  {"cmd":"exit"}
]
```

**陷阱**：密码框 `PasswordChar` 属性不响应 `type` → 确认 target 是编辑框本身而非显示文本；登录失败弹 MessageBox 需 `msgscan` 检测。
