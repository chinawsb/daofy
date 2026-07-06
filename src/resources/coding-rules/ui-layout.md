<!-- @when: AI 生成或修改 VCL/FMX 窗体、Frame、Dialog 后，需要检查 UI 布局质量 -->
<!-- @chain: before=ui-testing.md, after=review-table.md -->

## UI 布局规范与审计

AI 生成 Delphi GUI 后，必须把布局质量当作代码质量的一部分审计。编译通过只说明代码可运行，不说明界面舒适、整齐、可读。

### 目标

| 维度 | 要求 |
|------|------|
| 对齐 | 同一列内容控件 Left 一致，按钮组 Top/Height 一致，文本标签与字段中心线对齐 |
| 间距 | 使用 8px 基准网格；文本标签到字段建议 4~16px；同类控件垂直间距保持一致 |
| 层次 | 表单内容按区域组织，优先用 Panel/GroupBox/PageControl 分区，不让控件散落 |
| 边界 | 控件不得超出父容器；不同 DPI 下不得截断、压缩、重叠 |
| Resize | 会拉伸的内容区域设置 Anchors 或 Align；底部按钮保持稳定位置 |
| TabOrder | Tab 顺序与视觉阅读顺序一致：从上到下、从左到右 |

### 静态审计

AI 生成或修改 DFM 后，先运行静态布局审计：

```python
delphi_project(action="layout", base_dir="src")
delphi_project(action="layout", file_path="MainForm.dfm")
delphi_project(action="layout", file_path="MainForm.dfm", output_format="json")
```

`layout` 会读取文本 DFM，二进制 DFM 会尽量临时转换为文本；不修改原文件。审计依据是 DFM 属性和几何关系，不依赖固定控件类型名单。当前检查项：

| 规则 | 检查内容 | 典型修复 |
|------|----------|----------|
| LAYOUT-001 | 同一父容器内手工布局控件重叠 | 调整位置/尺寸，或用容器分区 |
| LAYOUT-002 | 控件超出父容器边界 | 修正 Width/Height/Left/Top，或引入 ScrollBox |
| LAYOUT-003 | 同列内容控件 Left 不一致 | 统一同列 Left |
| LAYOUT-004 | 同列内容控件垂直间距不一致 | 统一行高和行间距 |
| LAYOUT-005 | 文本标签与字段垂直中心未对齐 | 调整文本标签 Top 或字段 Top |
| LAYOUT-006 | 文本标签与字段水平间距过大或过小 | 统一文本标签右边缘到字段左边缘间距 |
| LAYOUT-007 | TabOrder 与视觉顺序不一致 | 重新设置 TabOrder |

### 生成规范

创建窗体时按以下顺序布局：

1. 先确定内容区域：标题区、输入区、列表区、操作区、状态区。
2. 每个区域使用独立容器，容器内部再放控件。
3. 输入表单使用两列结构：文本标签列右对齐，字段列左对齐。
4. 不用微调随机坐标；同一组控件的 Left、Top、Width、Height 使用统一数列。
5. 表格、Memo、TreeView、ListView 这类主内容区域优先使用 `Align=alClient` 或 `Anchors=[akLeft, akTop, akRight, akBottom]`。
6. 底部按钮区域保持固定高度，按钮按主次顺序排列，间距一致。
7. 中文 Caption 预留足够宽度，不依赖 AutoSize 挤压相邻控件。

### 运行时验证

静态审计通过后，再做真实运行时验证：

```python
automate_delphi(action="gui", app_path="App.exe", script=[
    {"cmd": "goto", "target": "TMainForm"},
    {"cmd": "dumpstate", "props": "name,left,top,width,height,class,anchors,align"},
    {"cmd": "capture", "target": "layout-main"},
    {"cmd": "exit"}
])
```

运行时重点验证：

- 100% / 125% / 150% DPI 下无重叠、截断、文字省略。
- 主窗体缩放后，内容区域能伸缩，按钮和状态区不漂移。
- 弹窗、向导页、TabSheet 内部也要单独审计，不能只看主窗体。
- 自绘、WebView、ActiveX 等非 VCL 控件使用 `ocr(action="detect")` 检查文本框位置和截断。

### 审计结论

布局审计发现严重项时，不应继续交付界面。先修复重叠、越界、明显错位，再进行编译和自动化 UI 验证。
