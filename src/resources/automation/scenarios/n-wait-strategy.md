<!-- @when: 消除固定延时，使用条件等待（waitfor/goto）替代裸 wait -->
<!-- @part-of: ui-testing -->

#### N. 等待与条件同步 — 禁用裸固定延时

| 要素 | 内容 |
|------|------|
| **目标** | 消除 `{"cmd": "wait", "ms": 固定值}` 的脆弱等待模式，代之以条件触发等待 |
| **策略** | `waitfor` 属性等待 → `goto` 窗体等待 → `wait` 仅做最后手段 |
| **关键命令** | `waitfor`, `goto`, `wait`（仅兜底） |

**背景**：固定延时 `wait 500ms` 在快机器上浪费时间，在慢机器上又不足够。测试编写者无法预知 CI 环境的性能。条件等待（`waitfor` + 属性/状态）自动适配任何执行速度。

##### N1. `waitfor` 优先规则（强制）

```
等待某个状态
├─ 等待控件变为可见/可用
│  ├─ 有目标窗体 → goto T目标窗体（内置 5s 超时轮询）
│  └─ 需要检查属性 → waitfor target prop value timeout
├─ 等待状态栏变化 → waitfor StatusBar Caption "成功" timeout=5000
├─ 等待对话框出现 → msgscan + assert_expr
├─ 等待异步任务完成
│  ├─ LLM API 等后端 → waitfor StatusBar Caption "完成" timeout=120000
│  └─ 无法轮询属性 → 循环 capture + OCR diff 检测画面变化
└─ 等待固定时长（仅限非条件场景）
   └─ wait ms=300（如动画播放、输入防抖，最长 1000ms）
```

| 应避免 ❌ | 应使用 ✅ |
|-----------|----------|
| `{"cmd":"wait","ms":1200}` | `{"cmd":"goto","target":"TfrmSettings","timeout":5000}` |
| `{"cmd":"wait","ms":3000}` | `{"cmd":"waitfor","target":"StatusBar","prop":"Caption","value":"就绪","timeout":5000}` |
| `{"cmd":"wait","ms":120000}` | `{"cmd":"waitfor","target":"lblStatus","prop":"Caption","value":"翻译完成","timeout":130000}` |
| `{"cmd":"wait","ms":500}` | 仅用于 UI 动画的极小延迟（`< 1000ms`） |

##### N2. 默认超时表

| 场景 | 建议超时 | 说明 |
|------|---------|------|
| 主窗体 goto/就绪 | 10-15s | 含闪屏/启动动画 |
| 对话框打开 waitfor/goto | 3-5s | 普通模态对话框 |
| 操作后状态栏变化 waitfor | 5s | 保存/删除/导入等常规操作 |
| 文件打开/保存 dlgfile | 10s | OpenDialog/SaveDialog |
| 网络请求/LLM API | 120s+ | 后端响应不确定，设足够长 |
| 右键菜单弹出 | 2-3s | TPopupMenu 弹出 |
| 数据刷新/重建 | 10-30s | Rescan/Reload 等重量操作 |

##### N3. 异步操作等待模式

对于 LLM 翻译、文件批处理等不确定时长的操作，推荐分层等待：

```json
[
  {"cmd":"click","target":"BtnBatchTranslate"},

  {"phase":"perceive","cmd":"waitfor","target":"ProgressBar","prop":"Visible","value":"True","timeout":5000,
   "note":"等进度条出现，确认任务已开始"},

  {"phase":"perceive","cmd":"waitfor","target":"StatusBar","prop":"Caption","value":"翻译完成","timeout":180000,
   "note":"等异步翻译完成（最长 3 分钟）"},

  {"phase":"verify","cmd":"rget","target":"vstProject.RootNodeCount","assert_expr":"int(actual)>0","note":"验证树数据"},
  {"phase":"verify","cmd":"capture","target":"translate_done"}
]
```

如果目标进程无可见状态属性可轮询，使用截图画面对比：

```python
# Python 轮询：每 5 秒 capture + OCR diff，直到画面稳定或超时
import time
last_checksum = None
for i in range(36):  # 最多 3 分钟
    r = daofy_ocr(action="diff", baseline="prev_screenshot.png", current="current.png")
    if r["diff_pixels"] < 50:  # 画面基本稳定
        break
    time.sleep(5)
```

**陷阱**：`waitfor` 的属性值比较是字符串相等 → 数值型属性需要 Python 侧断言；`goto` 默认超时 5s 可用 `timeout` 参数调整；`wait` 允许的最小粒度 100ms，但仅在 UI 动画同步时使用（最长 1000ms）。
