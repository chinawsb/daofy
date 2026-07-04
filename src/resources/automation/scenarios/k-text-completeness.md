<!-- @when: 检测文本在控件内是否完整显示（无截断、省略号、溢出），尤其跨 DPI -->
<!-- @part-of: ui-testing -->

#### K. 文本显示完整性验证 — 截断/溢出/省略号

| 要素 | 内容 |
|------|------|
| **目标** | 检测文本在控件内是否完整显示（无截断、无省略号、无溢出），尤其在不同 DPI 缩放下 |
| **策略** | `recognize` 取文本 + bounding box → `detect` 检测文本实际渲染区域 → 与控件边界/预期宽度对比 |
| **关键命令** | `recognize`, `detect`, `color`, `diff` |

**背景**：Delphi 控件在不同 DPI 缩放（100% / 125% / 150% / 200%）下字体缩放而控件尺寸可能未同步调整，导致文本截断。RTTI 只能读到 `Caption` 原始值，无法感知渲染结果是否被裁剪。OCR 是唯一可靠的验证手段。

##### K1. 省略号检测 — 文本末尾被截断

```python
# 识别目标区域的文本
r = daofy_ocr(action="recognize", image_path="label_caption.png")
first = r["results"][0] if r["results"] else {"text": ""}

# 检查省略号
if "..." in first["text"] or "…" in first["text"]:
    print(f"⚠️ 文本截断: {first['text']}")
elif r["results"]:
    print(f"✅ 文本完整: {first['text']}, 置信度: {first['confidence']}")
```

注意：Delphi 的 `TLabel` 和 `TCaption` 截断用省略号取决于 `TLabel.Layout` 和 `AutoSize=False` 时 Windows 自动截断行为。部分控件可能直接裁剪而不加省略号 → 需结合 K2 检测。

##### K2. 渲染宽度 vs 控件宽度 — 检测溢出

```python
# 识别文本并取 bounding box
r = daofy_ocr(action="recognize", image_path="label_caption.png")
if not r["results"]:
    print("⚠️ OCR 未识别到文本，可能完全溢出或颜色过浅")
else:
    # box 格式: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] 顺时针
    box = r["results"][0]["box"]
    render_width = box[1][0] - box[0][0]   # 右上.x - 左上.x
    render_height = box[2][1] - box[1][1]  # 右下.y - 右上.y

    # 控件的预期渲染区域（根据设计时的控件位置和尺寸）
    control_width = 150  # 已知 Label.Width
    control_outer = 12   # 左右内边距合计

    if render_width >= control_width - control_outer:
        print(f"⚠️ 文本宽度 {render_width}px 接近控件边界 {control_width}px，可能溢出")
    else:
        print(f"✅ 文本在控件内: {render_width}/{control_width}px")
```

##### K3. 多行文本行数检测 — 确认所有行完整渲染

```python
r = daofy_ocr(action="recognize", image_path="memo_text.png")

# 统计检测到的文本行（每个 result 是一行）
lines = [item["text"] for item in r["results"]]

# 检查最后一行是否显得未完成（过短或宽度明显小于平均）
if len(lines) > 1:
    widths = [
        item["box"][1][0] - item["box"][0][0]
        for item in r["results"]
    ]
    last_width = widths[-1]
    avg_width = sum(widths[:-1]) / (len(widths) - 1)

    if last_width < avg_width * 0.4 and last_width < 50:
        print(f"⚠️ 最后一行宽度异常({last_width}px vs avg {avg_width:.0f}px)，可能被截断")
    else:
        print(f"✅ 多行文本完整 ({len(lines)} 行)")
else:
    print(f"✅ 单行文本: {lines[0] if lines else '无'}")
```

##### K4. 跨 DPI 对比 — 同一控件在不同缩放下的渲染差异

```python
# 预先在已知无截断的 DPI(如 100%) 下截图作为基线
baseline = daofy_ocr(action="recognize", image_path="caption_100pct.png")
base_box = baseline["results"][0]["box"]
base_width = base_box[1][0] - base_box[0][0]

# 在 150% DPI 下对比
current = daofy_ocr(action="recognize", image_path="caption_150pct.png")
cur_box = current["results"][0]["box"]
cur_width = cur_box[1][0] - cur_box[0][0]

# 预期宽度变化 = 缩放比例 (150%/100% = 1.5 倍)
expected_width = base_width * 1.5
if cur_width < expected_width * 0.9:
    print(f"⚠️ 150% DPI 下文本宽度异常: 实际 {cur_width:.0f}px < 预期 {expected_width:.0f}px")
    print("   → 文本可能被截断或控件未正确缩放")
elif cur_width > expected_width * 1.1:
    print(f"⚠️ 宽度超出预期: {cur_width:.0f}px vs {expected_width:.0f}px，超出控件边界风险")
else:
    print(f"✅ DPI 缩放正常: {cur_width:.0f}px (预期 ~{expected_width:.0f}px)")
```

##### K5. 颜色对比度检查 — 浅色背景上浅色文字不可读

```python
c = daofy_ocr(
    action="color",
    image_path="label_caption.png",
    threshold=0.5  # 亮度阈值分离前景/背景
)

if "dark_avg" in c and "light_brightness" in c:
    # 文字(暗) 和 背景(亮) 的亮度对比
    text_brightness = 1 - c["brightness"] if c["dark_count"] > c["light_count"] else c["brightness"]
    contrast = abs(c["light_brightness"] - text_brightness)
    if contrast < 0.3:
        print(f"⚠️ 文字背景对比度过低: {contrast:.2f}（文字可能在浅色背景下不可读）")
    else:
        print(f"✅ 对比度正常: {contrast:.2f}")
```

##### K6. 自动化脚本集成 — 截取各 DPI 下的关键表单

```json
[
  {"cmd":"goto","target":"TMainForm"},
  {"cmd":"capture","target":"main_100pct","note":"在 100% DPI 下运行"},
  {"cmd":"click","target":"BtnOpenForm"},
  {"cmd":"waitfor","target":"TDataForm","prop":"Visible","value":"True","timeout":3000},
  {"cmd":"capture","target":"dataform_100pct"},
  {"cmd":"exit"}
]
```
分别在 100% / 125% / 150% 系统缩放下运行此脚本 → Python 侧对每组截图做 K1-K4 分析。

##### K7. OCR 验证集成到测试 JSON 工作流

OCR 调用本身是 Python 侧的 `daofy_ocr` 工具调用，**不在 JSON 脚本内执行**。但 JSON 脚本应为 OCR 提供足够的输入素材（截图 + 位置参考），使 Python 侧可以自动执行 OCR 断言。

**推荐模式**：capture → Python OCR → assert，形成完整的 test step：

```json
[
  {"cmd":"goto","target":"TfrmMain"},
  {"cmd":"click","target":"BtnOpenSettings"},
  {"cmd":"waitfor","target":"TfrmSettings","prop":"Visible","value":"True","timeout":5000},

  {"cmd":"capture","target":"settings_dialog","note":"供 OCR 识别对话框各控件文本"},

  {"cmd":"rget","target":"Label5.Left","note":"供 Python 侧作为控件位置参考"},
  {"cmd":"rget","target":"Label5.Width"},
  {"cmd":"rget","target":"cbxLanguages.Left"},

  {"cmd":"exit"}
]
```

Python 测试编排器（或大模型后处理脚本）中：

```python
# 1. 识别截图中的文本
r = daofy_ocr(action="recognize", image_path="snapshots/settings_dialog.png")

# 2. 校验关键标签文本完整
for item in r["results"]:
    text = item["text"]
    if "语言" in text and "..." in text:
        print(f"❌ 文本截断: {text}")
        failures.append(f"settings_dialog 中 '{text}' 包含省略号")

# 3. 检查 bounding box 是否超出预期控件范围
#    从 rget 返回的 Label5.Left/Width 可知控件位置
label5_left = 9    # 从 rget 结果获取
label5_right = 100 # 从 rget 结果计算
for item in r["results"]:
    box = item["box"]
    render_right = box[1][0]  # 右上角 x
    if render_right > label5_right + 5:
        print(f"⚠️ 文本渲染超出 Label5 右边界: {render_right} > {label5_right}")
```

**OCR 后处理断言表**（每个 capture 步骤后 Python 侧应检查的内容）：

| capture 目标 | 应做的 OCR 检查 | 通过标准 |
|-------------|----------------|---------|
| 常规对话框/表单 | recognize 检测所有可见文本，对比预期关键词 | 关键字段内容完整、无省略号、信度 >0.6 |
| 错误/警告弹窗 | recognize 识别弹窗文本 | 不包含非预期错误码，按钮文字正确 |
| 语言切换后截图 | detect 检测文本分布是否完整 | 无右边界截断、无重叠文字框 |
| 菜单下拉后截图 | recognize 识别所有菜单项 | 菜单项数 >= 预期数，无乱码 |
| 树展开后截图 | detect 检测节点文本行数 | 行数 >= 预期展开节点数 |
| 重建前后对比 | diff 基线对比 | diff_pixels 在合理范围（有变化但不异常）|

**K7 规则**：每个 `capture` 步骤后必须有对应的 OCR 或 diff 检查。没有 OCR 后处理的 `capture` 等同于人工审查，不属于自动化验证。

**陷阱**：PP-OCR 对旋转文字和艺术字体识别率下降 → `recognize` 信度低于 0.6 时放弃文本检测；`detect` 返回空可能意味着文字颜色与背景太接近（用 `color` 检查对比度）；Delphi 的 `TLabel.AutoSize=True` 时不截断但可能撑破布局 → 需要同时检测相邻控件是否被挤压（用 `diff` 比对基线）。
