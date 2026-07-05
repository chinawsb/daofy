<!-- @when: 验证控件在表单上的位置关系：左对齐、间距一致、无重叠 -->
<!-- @part-of: ui-testing -->

#### L. 布局视觉对齐

| 要素 | 内容 |
|------|------|
| **目标** | 验证控件在表单上的位置关系：左对齐、间距一致、无重叠、标签-字段配对 |
| **策略** | 优先 `rget` 精确读取关键控件 BoundsRect；控件较多时用 `dumpstate props=...` 批量采集；非 VCL 控件回退 `detect` 文本框反推位置 |
| **关键命令** | `rget`, `dumpstate`, `detect` |

**背景**：布局问题在 Delphi GUI 中极难通过编译发现。典型场景：Label 与 Edit 错位、不同 DPI 下间距变形、`Align`/`Anchors` 属性配置错误导致控件重叠、中文字符撑开 Label 导致挤压相邻控件。RTTI 取 `BoundsRect` 是像素级精确手段，远优于截图肉眼判断。

**静态前置**：运行时采集前，先用 `delphi_project(action="layout", base_dir="...")` 审计 DFM 里的重叠、越界、同列对齐、Label-字段间距和 TabOrder。静态通过后再用本场景验证真实运行效果和跨 DPI 稳定性。

##### L1. 采集控件位置 — `rget` / `dumpstate` 走管道 RTTI

```python
# 对单个控件 rget BoundsRect
r = daofy_automate(action="gui", app_path="App.exe", script=[
    {"cmd": "goto", "target": "TMainForm"},
    {"cmd": "rget", "target": "EditName.BoundsRect"},
    {"cmd": "rget", "target": "EditPhone.BoundsRect"},
    {"cmd": "rget", "target": "EditAddr.BoundsRect"},
    {"cmd": "rget", "target": "LabelName.BoundsRect"},
    {"cmd": "exit"},
])
# BoundsRect 返回: (left, top, right, bottom)
# → (x, y, x+w, y+h)
```

也可以用 `dumpstate` 带 `props` 参数批量获取全表单控件位置：

```python
r = daofy_automate(action="gui", app_path="App.exe", script=[
    {"cmd": "goto", "target": "TMainForm"},
    {"cmd": "dumpstate", "props": "name,left,top,width,height,class"},
    {"cmd": "exit"},
])
```

之后在 Python 侧解析 `dumpstate` 返回的控件树，提取每个控件的布局坐标。

##### L2. 左对齐检测 — 同列控件 Left 一致

```python
controls = {
    "EditName":  {"left": 120, "top": 10, "width": 200, "height": 24},
    "EditPhone": {"left": 120, "top": 40, "width": 200, "height": 24},
    "EditAddr":  {"left": 120, "top": 70, "width": 200, "height": 24},
}

left_values = [c["left"] for c in controls.values()]
if max(left_values) - min(left_values) <= 2:
    print(f"✅ 左对齐一致: Left={left_values[0]}")
else:
    print(f"⚠️ 左对齐偏差: {left_values}")
```

##### L3. 间距一致性检测 — 相邻控件垂直间距

```python
# 按 top 排序，计算相邻间距
sorted_controls = sorted(controls.values(), key=lambda c: c["top"])
gaps = []
for i in range(len(sorted_controls) - 1):
    gap = sorted_controls[i + 1]["top"] - (
        sorted_controls[i]["top"] + sorted_controls[i]["height"]
    )
    gaps.append(gap)

if gaps:
    avg_gap = sum(gaps) / len(gaps)
    max_deviation = max(abs(g - avg_gap) for g in gaps)
    if max_deviation <= 2:
        print(f"✅ 间距一致: {avg_gap:.0f}px（最大偏差 {max_deviation}px）")
    else:
        print(f"⚠️ 间距不一致: {gaps}（期望 ~{avg_gap:.0f}px）")
```

##### L4. 重叠检测 — BoundsRect 交叉

```python
def bounds_intersect(a, b):
    """返回两个控件的 BoundsRect 是否重叠。"""
    ax1, ay1, ax2, ay2 = (a["left"], a["top"],
                           a["left"] + a["width"], a["top"] + a["height"])
    bx1, by1, bx2, by2 = (b["left"], b["top"],
                           b["left"] + b["width"], b["top"] + b["height"])
    return (ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1)

# 检查所有控件对
items = list(controls.items())
overlaps = []
for i in range(len(items)):
    for j in range(i + 1, len(items)):
        name_a, ctrl_a = items[i]
        name_b, ctrl_b = items[j]
        if bounds_intersect(ctrl_a, ctrl_b):
            overlaps.append((name_a, name_b))

if overlaps:
    for a, b in overlaps:
        print(f"❌ 重叠: {a} 与 {b}")
else:
    print("✅ 无重叠")
```

##### L5. 标签-字段配对 — Label 右侧与 Edit 左侧对齐

```python
pairs = [
    ("LabelName", "EditName"),
    ("LabelPhone", "EditPhone"),
    ("LabelAddr", "EditAddr"),
]

misalignments = []
for label_name, edit_name in pairs:
    lbl = controls[label_name]
    edt = controls[edit_name]
    label_right = lbl["left"] + lbl["width"]
    gap = edt["left"] - label_right
    if not (4 <= gap <= 12):
        misalignments.append((label_name, edit_name, gap))

if misalignments:
    for lbl, edt, gap in misalignments:
        print(f"⚠️ {lbl}→{edt} 间距异常: {gap}px（期望 4~12px）")
else:
    print("✅ 所有标签-字段间距正常")
```

##### L6. 跨 DPI 布局稳定性 — 同一公式在不同 DPI 下检查

```python
def check_layout(controls: dict, dpi_label: str):
    """在指定 DPI 下检查布局指标。"""
    print(f"\n--- {dpi_label} ---")

    # L2: 左对齐
    lefts = [c["left"] for c in controls.values()]
    if max(lefts) - min(lefts) > 2:
        print(f"  ⚠️ 左对齐偏差: {lefts}")
    else:
        print(f"  ✅ 左对齐: Left={lefts[0]}")

    # L3: 间距
    sorted_ctrl = sorted(controls.values(), key=lambda c: c["top"])
    gaps = []
    for i in range(len(sorted_ctrl) - 1):
        gap = sorted_ctrl[i + 1]["top"] - (
            sorted_ctrl[i]["top"] + sorted_ctrl[i]["height"]
        )
        gaps.append(gap)
    if gaps:
        print(f"  {'✅' if max(gaps)-min(gaps)<=2 else '⚠️'} 间距: {gaps}")

    # L4: 重叠
    items = list(controls.items())
    over = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a = items[i][1]; b = items[j][1]
            if (a["left"] < b["left"]+b["width"] and
                a["left"]+a["width"] > b["left"] and
                a["top"] < b["top"]+b["height"] and
                a["top"]+a["height"] > b["top"]):
                over += 1
    print(f"  {'✅' if over==0 else '❌'} 重叠: {over} 处")

# 分别传入 100%、125%、150% DPI 下采集的控件坐标
check_layout(controls_100, "100% DPI")
check_layout(controls_125, "125% DPI")
check_layout(controls_150, "150% DPI")
```

**DPI 预期关系**：如果 Delphi 表单启用了 `Scaled=True`（默认），100%→150% 时控件 `Left` 和 `Width` 应精确放大 1.5 倍。偏差 >2px 说明 Scaled 配置异常或 `Anchors` 设置不正确：

```python
for name in controls_100:
    c100 = controls_100[name]
    c150 = controls_150[name]
    ratio_left = c150["left"] / c100["left"] if c100["left"] else 1
    ratio_width = c150["width"] / c100["width"]
    if abs(ratio_width - 1.5) > 0.05:
        print(f"⚠️ {name} 缩放异常: Width {c100['width']}→{c150['width']} (ratio={ratio_width:.2f})")
```

##### L7. 非 VCL 兜底 — OCR `detect` 反推控件位置

当控件不是 VCL 对象（WebView2、ActiveX、自绘 TStringGrid）时，用 `detect` 检测文本 bounding box 作为控件位置的代理：

```python
r = daofy_ocr(action="detect", image_path="form_region.png")
boxes = r["results"]

# 每个 box: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
# 转成 (left, top, width, height)
def box_to_rect(box):
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    return {"left": left, "top": top,
            "width": right - left, "height": bottom - top}

detected = [box_to_rect(b["box"]) for b in boxes]

# 对这些"代理控件"做 L2-L4 对齐分析
lefts = [d["left"] for d in detected]
if max(lefts) - min(lefts) <= 3:
    print(f"✅ 文本区域左对齐: Left≈{lefts[0]}")
```

**陷阱**：
- `dumpstate` 返回的是递归控件树，需要在 Python 侧展平（flatten）后提取 `name/left/top/width/height`。
- 单控件精确值读取使用 `rget Control.Property`，不要用 `rinspect` 读取属性值。
- Anchor 属性（`akLeft`/`akTop`/`akRight`/`akBottom`）影响 DPI 缩放行为，采集布局时应一并获取。
- 检测重叠时要排除 `TForm` 自身和 `TPanel`/`TGroupBox` 等容器控件（它们是子控件的父级，允许重叠）。
