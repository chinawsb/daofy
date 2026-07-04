<!-- @when: 操作过程中控件被销毁重建（rescan/reload/theme switch），需安全等待重建 -->
<!-- @part-of: ui-testing -->

#### O. 控件重建安全 — Rescan/Reload 后等待重建

| 要素 | 内容 |
|------|------|
| **目标** | 处理操作过程中控件被销毁重建（rescan、reload、theme switch）后的安全访问 |
| **策略** | 操作后不要立即 rget → 先用 goto 等待控件重建 → 验证关键控件存在 → 再继续 |
| **关键命令** | `goto`, `waitfor`, `rget`（重建后验证） |

**背景**：某些 Delphi 操作会销毁并重建整个窗体或控件树。典型情况：

| 操作 | 行为 | 影响 |
|------|------|------|
| Rescan/重新扫描 | 关闭项目 → 重新加载 → 重建树视图 | `TfrmMain` 及其所有子控件被重建 |
| 切换 VCL Style | 全局资源释放 → 重建所有窗体 | 所有控件句柄失效 |
| 项目 Close/Open | 关闭当前 → 打开新项目 → 重置状态 | 树、菜单、动作全部重建 |
| 重建索引 | 清空数据 → 重新加载 → 更新界面 | 数据集关联控件更新 |
| 语言切换 | 释放资源 → 加载新语言包 → 重建菜单 | 菜单项可能重新创建 |

##### O1. 重建后安全访问模式（强制）

```
操作触发了控件重建
   │
   ├── ① goto T目标窗体
   │     （等待窗体重新出现，默认超时 5s，重建场景设 10-15s）
   │
   ├── ② rget 关键控件名称
   │     （验证控件已在内存中重建，不仅窗口可见）
   │     assert_expr: "actual in ('True','False')" 不关心值，只关心控件存在
   │
   └── ③ 继续后续测试步骤
         （树节点坐标已变化，需重新计算偏移量）
```

```json
[
  {"cmd":"click","target":"RescanMenu","note":"触发 rescan 操作"},
  {"phase":"wait","cmd":"waitfor","target":"ProgressBar","prop":"Visible","value":"True","timeout":5000,
   "note":"等 Rescan 进度条出现"},

  {"phase":"wait","cmd":"waitfor","target":"ProgressBar","prop":"Visible","value":"False","timeout":30000,
   "note":"等 Rescan 进度条消失 = 操作完成"},

  {"phase":"rebuild","cmd":"goto","target":"TfrmMain","timeout":15000,
   "note":"【关键】等待主窗体控件重建（而非仅窗口可见）"},

  {"phase":"rebuild","cmd":"rget","target":"vstProject.RootNodeCount","note":"验证树控件已重建",
   "assert_expr":"actual != ''"},

  {"phase":"rebuild","cmd":"rget","target":"actRescan.Enabled","note":"验证动作已重建",
   "assert_expr":"actual in ('True','False')"},

  {"phase":"verify","cmd":"capture","target":"rescan_done"},
  {"cmd":"exit"}
]
```

##### O2. `phase: rebuild` 标记

所有控件重建后的等待步骤必须标记 `"phase": "rebuild"`。此标记的意义：
- **审计工具**识别 `rebuild` 阶段步骤，检查是否包含 `goto` 重建等待
- 如果 `rebuild` 阶段步骤失败，**不应**判定为测试失败，而是环境/时序问题
- 重建后需要比常规 `waitfor` 更长的超时（最小 10s）

##### O3. 重建前后的快照对比

```json
[
  {"phase":"verify","cmd":"capture","target":"before_rescan","note":"重建前截图"},
  {"phase":"execute","cmd":"click","target":"BtnRescan"},
  {"phase":"wait","cmd":"waitfor","target":"ProgressBar","prop":"Visible","value":"False","timeout":30000},
  {"phase":"rebuild","cmd":"goto","target":"TfrmMain","timeout":15000},
  {"phase":"verify","cmd":"capture","target":"after_rescan","note":"重建后截图"},
  {"cmd":"exit"}
]
```

Python 侧：
```python
# 用 daofy_ocr diff 对比重建前后画面
diff = daofy_ocr(action="diff", baseline="before_rescan.png", current="after_rescan.png")

# 如果有显著变化（diff_pixels > 阈值），说明重建成功
if diff["diff_pixels"] > 500:
    print(f"✅ 重建成功: {diff['diff_pixels']} pixels 变化")
else:
    print(f"⚠️ 重建后画面无明显变化: {diff['diff_pixels']} pixels")
```

**陷阱**：重建后 `rget` 返回 `NF:xxxx` 意味控件尚未重建 → 增加 `goto` 等待时间，或分多次重试；重建后前一步获取的控件引用全部失效 → 任何 `rget` 结果不可缓存；不要在主线程 busy-waiting 时发管道命令 → 先 `waitfor` 等异步操作完成。
