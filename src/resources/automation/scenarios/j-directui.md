<!-- @when: 处理 VCL Style / IFileDialog / TTaskDialog / 非 VCL 自绘弹窗 -->
<!-- @part-of: ui-testing -->

#### J. DirectUI 弹窗 / 现代系统对话框

| 要素 | 内容 |
|------|------|
| **目标** | 处理 VCL Style 渲染的 DirectUI 弹窗、Windows IFileDialog、TTaskDialog 等标准 Win32 消息无法覆盖的对话框 |
| **策略** | 分三级：①优先 VCL 管道命令（RTTI 穿透）→ ②`uia.xxx` 回退 → ③截图 OCR 兜底 |
| **关键命令** | `uia.click`, `uia.goto`, `uia.set`, `uia.scan`, `uia.wait`, `capture`+`daofy_ocr` |

**背景**：DirectUI 控件（VCL Style 渲染、OwnerDraw 自绘、DevExpress Skin）底层仍是 VCL 对象，DaofyAutomation 的 `goto`/`rget`/`click` 可通过管道内 RTTI 正常操作，无需特殊处理。**真正需要 `uia.xxx` 的是以下情况**：

| 情况 | 原因 | 推荐手段 |
|------|------|---------|
| IFileDialog（Windows 10+ 现代 Open/Save） | COM 对话框，非 VCL Form | `uia.click`/`uia.goto` |
| TTaskDialog / TCustomTaskDialog | 使用 `TaskDialogIndirect` API，非标准 MessageBox | `uia.scan` + `uia.click` |
| 第三方 DirectUI 框架（如 Chromium Embedded） | 单 HWND 内自绘所有控件 | `capture` + OCR |
| VCL Styles 主题化的 TForm | 外观变了但 VCL 控件仍在 | 管道命令正常（无需 uia） |

##### J0. `uia.xxx` 使用规则（强制）

当测试涉及以下对话框时，**必须**提供 `uia.xxx` 回退分支：

| 触发场景 | 必须用 uia.xxx 的理由 | 否则后果 |
|---------|----------------------|---------|
| `dlgfile` 操作后未检测到 OpenDialog | Windows 10+ 的 IFileDialog 是 COM 对话框，非 VCL 窗口 | `msgscan` 返回 NOD，测试卡死 |
| 点击按钮后应弹出"另存为"标准对话框 | 现代 Windows 资源管理器对话框 | `dlgscan` 找不到，步骤挂起 |
| 确认框使用 `TTaskDialog`（非 MessageBox） | 使用 `TaskDialogIndirect` API，无标准消息泵 | `msgscan` 一直 NOD |
| 删除/批量操作出现自定义样式确认弹窗 | 不确定是 VCL 还是现代对话框 | 先 `msgscan` 尝试 → 超时后 fallback 到 `uia.scan` |

`uia.xxx` 回退集成模式：

```json
[
  {"cmd":"click","target":"BtnImport","note":"触发 OpenDialog"},

  {"cmd":"msgscan","timeout":2000,"note":"先快速尝试 msgscan（VCL MessageBox）"},
  {"cmd":"wait","ms":300,"note":"给对话框渲染时间"},

  {"cmd":"uia.goto","target":"打开","timeout":5000,
   "note":"msgscan 无结果，回退 uia.goto 找 IFileDialog 标题"},

  {"cmd":"uia.set","target":"文件名(N):","text":"C:\\data\\import.xlsx"},
  {"cmd":"uia.click","target":"打开(&O)"},

  {"cmd":"goto","target":"TMainForm","timeout":10000},
  {"cmd":"capture","target":"import_fallback_done"},
  {"cmd":"exit"}
]
```

**规则**：任何涉及文件对话框的测试步骤，必须 `msgscan`（快速尝试验 VCL 对话框）+ `wait 300ms`（给系统渲染时间）+ `uia.goto` 兜底（5s 超时）。三步保底确保不因对话框类型判断错误而卡死。

##### J1. 现代 OpenDialog（IFileDialog）— `uia.xxx`

```json
[
  {"cmd":"click","target":"BtnImport"},

  {"cmd":"uia.goto","target":"打开","note":"UIA 穿透查找 IFileDialog","timeout":5000},
  {"cmd":"uia.set","target":"文件名(N):","text":"C:\\data\\import.xlsx"},
  {"cmd":"uia.click","target":"打开(&O)"},

  {"cmd":"waitfor","target":"TMainForm","prop":"Visible","value":"True","timeout":10000},
  {"cmd":"rget","target":"StatusBar.Caption","assert_expr":"'导入' in actual or '成功' in actual"},
  {"cmd":"capture","target":"import_uia_done"},
  {"cmd":"exit"}
]
```

##### J2. TTaskDialog 确认弹窗 — `uia.xxx`

```json
[
  {"cmd":"click","target":"BtnDeleteBatch"},

  {"cmd":"uia.scan","target":"TTaskDialog","timeout":5000,
   "expected":"检测到 TTaskDialog"},
  {"cmd":"uia.click","target":"是(&Y)","note":"TaskDialog 按钮无 HWND，必须走 UIA"},

  {"cmd":"waitfor","target":"StatusBar","prop":"Caption","value":"批量删除完成","timeout":5000},
  {"cmd":"capture","target":"taskdialog_done"},
  {"cmd":"exit"}
]
```

##### J3. VCL Style 主题弹窗 — 管道命令仍可用（仅示例）

即使 VCL Style 让 MessageBox 外观完全改变，标准 `msgscan` + `dlgclick` 仍有效（底层还是 `TForm`）：

```json
[
  {"cmd":"click","target":"BtnDelete"},

  {"cmd":"msgscan","expected":"VCL Style 主题化的删除确认"},
  {"cmd":"dlgclick","target":"btnYes","note":"VCL Style 下 dlgclick 仍有效，因为按钮是 VCL 控件"},

  {"cmd":"capture","target":"styled_after_delete"},
  {"cmd":"exit"}
]
```

##### J4. 非 VCL 自绘弹窗 — 截图 OCR 兜底

当 `uia.xxx` 也无法识别控件时（如 WebView2 内弹窗、DirectX Overlay），回退到图像识别：

```json
[
  {"cmd":"click","target":"BtnShowCustom"},

  {"cmd":"waitfor","target":"自定义弹窗类名","prop":"Visible","value":"True","timeout":5000,"note":"等弹窗出现"},
  {"cmd":"goto","target":"TDirectUIPopup","note":"VCL 下仍可 goto，非 VCL 下跳过此步"},
  {"cmd":"capture","target":"directui_popup"},

  {"cmd":"exit"}
]
```

之后在 Python 侧用 `daofy_ocr` 分析截图：
```python
# 识别弹窗文字
ocr = daofy_ocr(action="recognize", image_path="snapshots/directui_popup.png")
# 或颜色分析检测选中状态
color = daofy_ocr(action="color", image_path="snapshots/directui_popup.png", region=[100,200,50,20])
```

**判断流程**（大模型按此决策，不猜测）：

```
遇到弹窗
├─ 是 VCL Form（class 带 T 前缀）→ 管道命令 goto/rget/click，正常处理
├─ 是 MessageBox（ShowMessage/MessageDlg）→ msgscan + dlgclick
├─ 是 IFileDialog / TTaskDialog → uia.xxx
├─ 是 #32770 标准 Dialog → dlgscan/dlgclick 优先，失败回退 uia.xxx
├─ 是 WebView2 / Chromium 内弹窗 → capture + OCR
└─ 完全未知 → capture → OCR 识别文字 → 再选方案
```

**陷阱**：`uia.xxx` 的 target 用 **UI 上显示的文字**（如"打开(&O)"、"是(&Y)"），不是 VCL 控件名；IFileDialog 的文件名输入框用 `uia.set` + `text` 而非 `type`；截图 OCR 兜底是最后手段，优先尝试管道和 UIA。
