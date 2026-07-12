# UI 布局完整性检测 — 技术调研与方案设计

> 目标：从 UI 截图自动检测完整的布局结构信息（元素类型、位置、文本、层次关系），
> 输出结构化 JSON/DFM，供大模型引用以生成 Delphi 界面代码。

---

## 1. 背景与动机

当前项目已具备：

| 能力 | 工具 | 局限性 |
|------|------|--------|
| PP-OCRv6 文字识别 | `ocr` tool | 只识别文字，不理解元素类型和结构 |
| 文本边界捕获 | `textbounds` (paint-hook) | 只捕获 GDI/GDI+ 文本，不区分元素类型 |
| 图像差异对比 | `ocr diff` | 只能比较两图差异，不分析单张布局 |
| 静态 DFM 审计 | `layout_audit` | 需要 DFM 源码，不能从截图工作 |
| 控件树提取 | `dumpstate` / `formsum` | 需要 Delphi 运行时，不能从截图工作 |
| DFM 生成 | `manage_component` / `create_component_dfm` | 需要 Pascal 代码，不能从截图工作 |

**核心缺失**：截图 → DFM 的逆向管线，即从一张 UI 截图反推出 Delphi DFM 描述文件。

与"截图中检测元素"的一般 CV 任务不同，Delphi DFM 包含大量**无法从像素推断**的信息：

| 信息 | 从截图恢复难度 | 来源 |
|------|:-------------:|------|
| **位置 / 尺寸** (Left/Top/Width/Height) | ⭐ 容易 | 像素坐标精确测量 |
| **文字内容** (Caption/Text/Items) | ⭐⭐ | OCR 提取，需匹配到控件 |
| **层次结构**（Panel→GroupBox→Button） | ⭐⭐ | 空间包含 + 间距分析推断 |
| **控件类型**（TButton/TcxGrid...） | ⭐⭐⭐ | 视觉风格 → 分类（需训练） |
| **属性值**（Enabled/ReadOnly/Visible） | ⭐⭐⭐⭐ | 颜色/灰度暗示，不完全可靠 |
| **事件绑定**（OnClick 等） | ⭐⭐⭐⭐⭐ | 纯代码逻辑，截图不可见 |
| **控件名称**（Name 属性） | ⭐⭐⭐⭐⭐ | 无命名规范则无法推断 |

---

## 2. 推荐方案：合成数据 + ONNX 推理

### 2.1 核心思路

项目独特的优势是 **`dumpstate` + `capture` 可以零成本自动生成标注数据**：

```
训练数据生成（只需跑一次）:
  capture(screenshot) + dumpstate(labels)
        ↓                        ↓
    截图 (PNG) ∪ 精确标签 (控件类型 + bbox + 文本 + 层次)
        ↓
    训练 YOLO → 导出 ONNX → 推理时仅需 11MB 权重

推理管线（每次调用）:
  new_screenshot → YOLOv11n ONNX → 元素框 + 类型 → OCR → 层次推理 → DFM
```

### 2.2 管线架构

```
输入：UI 截图 (PNG/JPEG)
         │
         ▼
┌─────────────────────────────────────────┐
│ Layer 1: 元素检测                        │
│ ───────────────────────                  │
│ 方法 A: 传统 CV (OpenCV) — 零依赖基线     │
│   Sobel/Canny → 形态学闭运算 → 轮廓提取    │
│   → 按宽高比/面积分类                     │
│                                          │
│ 方法 B: YOLOv11n ONNX — 精确检测 (推荐)    │
│   onnxruntime 推理 → 8400 候选框 → NMS   │
│   → 输出元素类型 + bbox + 置信度           │
│                                          │
│ → 输出: [{class_id, bbox, confidence},...]│
├─────────────────────────────────────────┤
│ Layer 2: 文字提取                         │
│ ─────────────────────                    │
│ PP-OCRv6 (项目已有)                      │
│   对每个检测到的元素区域 → OCR 识别文字     │
│   匹配文字到对应元素                       │
│                                          │
│ → 输出: [{..., text}, ...]               │
├─────────────────────────────────────────┤
│ Layer 3: 层次结构推理                      │
│ ───────────────────────                  │
│ 空间包含分析 → 容器-子元素关系             │
│ 对齐集群分析 → HStack/VStack/Grid         │
│ 间距分析 → 等距推断布局类型                │
│ 表单配对 → Label-Input 关联               │
│                                          │
│ → 输出: 层次化布局树                       │
├─────────────────────────────────────────┤
│ Layer 4: DFM 生成                         │
│ ─────────────────                        │
│ 用 DfmComponent 数据结构构建 DFM 树        │
│ 控件类型 → Delphi 类名映射                │
│ 默认属性填充 (TabOrder, Align, Anchors...) │
│ serialize_component() → DFM 文本          │
│                                          │
│ → 输出: DFM 文本 (可直接编译)              │
└─────────────────────────────────────────┘
```

### 2.3 三种方案的依赖与精度对比

| 方案 | 新增依赖 | 磁盘增量 | 精度 | 适用场景 |
|------|---------|:--------:|:----:|---------|
| **传统 CV** (OpenCV 形态学) | 无（已有）| **0 MB** | 60-70% | 基线、粗糙定位 |
| **YOLOv11n ONNX** ⭐ | `onnx` + 权重 | **~19 MB** | 85-95%* | **推荐——轻量精确** |
| **YOLOv11n + PyTorch 全量** | `torch` + `torchvision` | **~1.2 GB** | 85-95%* | 仅训练时需要，推理没必要 |

*标注：85-95% 指用 Delphi 合成数据训练后的精度。如果用通用 Rico 预训练权重（不含 Delphi 控件），精度会显著降低。

---

## 3. 合成数据生成流水线

这是本方案的核心竞争力——**不需要人工标注**。

### 3.1 原理

利用项目已有的 `automate_delphi` 能力，自动执行：

```python
# 合成数据生成伪代码
for form_name in all_forms:
    for state in states:           # 不同数据填充
        for dpi in dpis:           # DPI 变体
            # 1. 导航到窗体
            cmd_goto(form_name)
            
            # 2. 填充不同数据
            type_data(state.data)
            
            # 3. 截图 + dumpstate 同步采集
            screenshot = capture(form_name)     # → 训练图片
            labels = dumpstate(form_name)       # → ground truth
            
            # 4. 标签格式转换: dumpstate → YOLO 格式
            yolo_labels = convert_to_yolo(labels)
            save(screenshot, yolo_labels)
```

### 3.2 每窗体的标注产出

以典型客户管理窗体为例：

| dumpstate 字段 | YOLO 标签用途 |
|----------------|--------------|
| `class`: "TcxButton" → `category_id: 1` | 元素类型 |
| `props.Left / Top / Width / Height` → `[cx, cy, w, h]` | 归一化 bbox |
| `props.Caption`: "保存" → 训练时忽略（推理时用 OCR 替代） | 文本内容 |
| `props.Enabled`: True/False → 可额外标注 disabled 态 | 状态属性 |
| `children[...]` 嵌套关系 → 训练层次并非 YOLO 任务（留给 Phase 3 做） | 布局结构 |

### 3.3 产量估算

| 数据来源 | 每窗产能 |
|----------|---------|
| 控件实例 | 30-80 个（因窗体复杂度不同） |
| 状态变体 | 3 种（空数据 / 少量数据 / 大量数据） |
| DPI 变体 | 2 种（100% / 150%） |
| **每窗合计** | **~180-480 标注实例** |

**生成速度**：每个窗体约 500ms（goto + capture + dumpstate + 格式转换）

```
50 窗体 × 3 状态 × 2 DPI × 0.5s = 150s ≈ 2.5 分钟
产出: ~9,000-24,000 个标注实例
```

**2.5 分钟即可产出数万级 Delphi 专用标注数据**。

### 3.4 Delphi 控件 → YOLO 类别映射（示例）

初次训练建议覆盖最常用的 15-20 种控件类型：

| class_id | Delphi 控件类 | 视觉特征 | 对应 DFM 属性 |
|:--------:|--------------|---------|--------------|
| 0 | `background`（背景）| 整个截图的背景区域 | — |
| 1 | `TButton` / `TcxButton` / `TBitBtn` | 矩形凸起按钮 | Caption, ModalResult |
| 2 | `TEdit` / `TcxTextEdit` / `TMaskEdit` | 空心矩形输入框 | Text, MaxLength |
| 3 | `TLabel` / `TcxLabel` / `TStaticText` | 纯文字标签 | Caption, FocusControl |
| 4 | `TComboBox` / `TcxComboBox` | 带下拉箭头的框 | Items, ItemIndex |
| 5 | `TCheckBox` / `TcxCheckBox` | 带勾选方块 | Checked, State |
| 6 | `TRadioButton` / `TcxRadioButton` | 圆形单选钮 | Checked |
| 7 | `TListBox` / `TcxListBox` | 列表区域 | Items, ItemIndex |
| 8 | `TMemo` / `TRichEdit` / `TcxMemo` | 多行文本区 | Lines, ScrollBars |
| 9 | `TPanel` / `TcxGroupBox` / `TGroupBox` | 容器/面板 | Caption, Align |
| 10 | `TPageControl` / `TcxPageControl` | 页签条 | Pages, ActivePage |
| 11 | `TStringGrid` / `TcxGrid` / `TDBGrid` | 表格 | Cells, ColCount |
| 12 | `TTreeView` / `TcxTreeList` | 树形控件 | Items, Selected |
| 13 | `TDateTimePicker` / `TcxDateEdit` | 日期/时间选择 | Date, Time |
| 14 | `TProgressBar` / `TcxProgressBar` | 进度条 | Position, Max |
| 15 | `TScrollBar` / 滚动条 | 滚动条 | Position, Min, Max |
| 16 | `TMainMenu` / 菜单栏 | 顶部菜单 | Items |
| 17 | `TToolBar` / `TCoolBar` / 工具栏 | 按钮条 | Buttons |
| 18 | `TStatusBar` | 底部状态栏 | Panels |
| 19 | `TImage` / `TcxImage` | 图片/图标 | Picture |
| 20+ | 其他第三方控件 | 各具特征 | 按需扩展 |

### 3.5 训练流程（需 PyTorch 环境，可在另一台机器做）

```
训练阶段（需要 GPU / 或 CPU 慢跑）:
  ┌─────────────────────────────────────────────┐
  │ conda create -n yolo-train python=3.11        │
  │ pip install ultralytics torch torchvision     │  ← ~1.2 GB，仅训练用
  │                                               │
  │ yolo train                                     │
  │   model=yolo11n.pt                             │  ← 从 COCO 预训练迁移
  │   data=delphi_dataset.yaml                     │
  │   epochs=200                                   │
  │   imgsz=640                                    │
  │                                               │
  │ 输出: best.pt → 导出 best.onnx (~11MB)         │
  └─────────────────────────────────────────────┘

推理阶段（ONNX only，无 PyTorch）:
  ┌─────────────────────────────────────────────┐
  │ pip install onnxruntime onnx                  │  ← +~15 MB 仅需一次
  │ download best.onnx (~11MB)                    │
  │                                               │
  │ # onnxruntime 推理，无需 torch                 │
  │ session = ort.InferenceSession("best.onnx")    │
  │ outputs = session.run(None, {input_name: img}) │
  └─────────────────────────────────────────────┘
```

---

## 4. 层次结构推理算法

YOLO 检测输出是**扁平的 bbox 列表**，需要后处理构建层次树。

### 4.1 空间包含检测

```python
def build_hierarchy(detections: list[Detection]) -> TreeNode:
    """通过空间包含关系构建元素树。"""
    # 按面积降序排序（保证容器先处理）
    sorted_dets = sorted(detections, key=lambda d: d.area, reverse=True)
    roots = []
    
    for det in sorted_dets:
        parent = find_container(det, roots)
        if parent:
            parent.children.append(det)
        else:
            roots.append(TreeNode(element=det))
    return roots

def find_container(det: Detection, roots: list[TreeNode]) -> TreeNode | None:
    """找包含 det 的最小容器。"""
    candidates = []
    for root in roots:
        if contains(root.bbox, det.bbox):
            # 递归在子树中查找更精确的父容器
            sub = find_container_in_tree(det, root)
            if sub:
                candidates.append(sub)
            else:
                candidates.append(root)
    # 返回面积最小（最精确）的容器
    return min(candidates, key=lambda n: n.area) if candidates else None
```

### 4.2 布局类型推断

```python
def infer_layout_type(elements: list[Detection]) -> str:
    """推断一组子元素的布局排列。"""
    if len(elements) < 2:
        return "single"
    
    centers_x = [e.cx for e in elements]
    centers_y = [e.cy for e in elements]
    tops = [e.top for e in elements]
    lefts = [e.left for e in elements]
    
    y_spread = max(centers_y) - min(centers_y)
    x_spread = max(centers_x) - min(centers_x)
    avg_h = sum(e.h for e in elements) / len(elements)
    avg_w = sum(e.w for e in elements) / len(elements)
    
    # HStack: Y 中心接近
    if y_spread < avg_h * 0.5:
        return "hstack"
    # VStack: X 中心接近
    if x_spread < avg_w * 0.5:
        return "vstack"
    # Grid: 检查行列间距一致性
    if is_uniform_spacing(tops, lefts):
        return "grid"
    return "zstack"
```

### 4.3 表单项配对（Label-Input 关联）

```python
def pair_form_fields(elements: list[Detection]) -> list[FormField]:
    """识别标签+输入框配对。"""
    labels = [e for e in elements if e.class_id == 3]   # TLabel
    inputs = [e for e in elements if e.class_id in (2, 4)]  # TEdit, TComboBox
    
    pairs = []
    for label in labels:
        # 在标签右方或正下方找最近的输入框
        nearest = find_nearest_right_below(label, inputs)
        if nearest and vertical_align_tolerance(label, nearest, pixels=5):
            pairs.append(FormField(label=label, input=nearest))
    return pairs
```

---

## 5. ONNX 推理代码模板

```python
"""src/detection/yolo_onnx.py — YOLOv11n ONNX 推理封装"""

import numpy as np
import cv2
import onnxruntime as ort
from dataclasses import dataclass

@dataclass
class Detection:
    class_id: int
    confidence: float
    x: int      # left
    y: int      # top
    w: int      # width
    h: int      # height

class YOLOONNXDetector:
    """纯 ONNX Runtime 的 YOLO 检测器，无 PyTorch 依赖。"""
    
    def __init__(self, model_path: str, conf_thresh: float = 0.25):
        self.session = ort.InferenceSession(model_path)
        self.input_name = self.session.get_inputs()[0].name
        self.conf_thresh = conf_thresh
        
        # YOLOv11n 输出形状: [1, 84, 8400] (cx,cy,w,h + 80 COCO class probs)
        # 我们替换为自定义类别后输出形状: [1, N+4, 8400]
    
    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """预处理：resize 到 640×640 + 归一化。"""
        h, w = image.shape[:2]
        scale = min(640 / w, 640 / h)
        nw, nh = int(w * scale), int(h * scale)
        resized = cv2.resize(image, (nw, nh))
        
        # pad 到 640×640
        dw, dh = (640 - nw) // 2, (640 - nh) // 2
        padded = cv2.copyMakeBorder(
            resized, dh, dh + (640 - nh) % 2,
            dw, dw + (640 - nw) % 2,
            cv2.BORDER_CONSTANT, value=(114, 114, 114)
        )
        # HWC → CHW, BGR → RGB, 归一化
        blob = padded.astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))[np.newaxis, ...]
        return blob, scale, dw, dh
    
    def postprocess(self, outputs: np.ndarray, scale: float, dw: int, dh: int,
                    orig_shape: tuple) -> list[Detection]:
        """后处理：解算 bbox + NMS。"""
        # outputs shape: [1, 84+N, 8400]
        outputs = outputs[0]  # [84+N, 8400]
        
        # 提取 bbox (cx, cy, w, h) 和 class probs
        bboxes = outputs[:4, :]    # [4, 8400]
        scores = outputs[4:, :]    # [N, 8400]
        class_ids = scores.argmax(axis=0)
        confs = scores.max(axis=0)
        
        # 过滤低置信度
        mask = confs > self.conf_thresh
        if not mask.any():
            return []
        
        bboxes = bboxes[:, mask]
        class_ids = class_ids[mask]
        confs = confs[mask]
        
        # 反算回原始坐标
        detections = []
        for i in range(len(class_ids)):
            cx, cy, w, h = bboxes[:, i]
            # 去除 padding
            cx = (cx - dw) / scale
            cy = (cy - dh) / scale
            w = w / scale
            h = h / scale
            
            x = int(cx - w / 2)
            y = int(cy - h / 2)
            
            detections.append(Detection(
                class_id=int(class_ids[i]),
                confidence=float(confs[i]),
                x=max(0, x), y=max(0, y),
                w=int(w), h=int(h),
            ))
        
        # NMS 去重
        return self._nms(detections)
    
    def detect(self, image_path: str) -> list[Detection]:
        """完整推理管线。"""
        img = cv2.imread(image_path)
        orig = img.shape[:2]
        blob, scale, dw, dh = self.preprocess(img)
        outputs = self.session.run(None, {self.input_name: blob})
        return self.postprocess(outputs[0], scale, dw, dh, orig)
```

---

## 6. DFM 生成（检测结果 → DFM 文本）

```python
"""src/detection/dfm_generator.py — 检测结果 → DFM 转换"""

from src.tools.dfm_parser import DfmComponent, DfmProperty, serialize_component

# Delphi 控件类名映射
CLASS_MAP = {
    1:  "TButton",   2:  "TEdit",      3:  "TLabel",
    4:  "TComboBox", 5:  "TCheckBox",  6:  "TRadioButton",
    7:  "TListBox",  8:  "TMemo",      9:  "TPanel",
    10: "TPageControl", 11: "TStringGrid",
    # ...
}

def detections_to_dfm(detections: list[Detection],
                      hierarchy: list[TreeNode],
                      screen_w: int, screen_h: int) -> str:
    """将检测结果转为 DFM 文本。"""
    
    def build(node) -> DfmComponent:
        det = node.element
        cls_name = CLASS_MAP.get(det.class_id, "TControl")
        comp = DfmComponent(
            name=_gen_name(cls_name, node),  # Button1, Edit2, ...
            class_name=cls_name,
            properties=[
                DfmProperty(name="Left",   raw_value=str(det.x)),
                DfmProperty(name="Top",    raw_value=str(det.y)),
                DfmProperty(name="Width",  raw_value=str(det.w)),
                DfmProperty(name="Height", raw_value=str(det.h)),
                DfmProperty(name="TabOrder", raw_value="0"),  # 默认，需调整
            ]
        )
        if cls_name in ("TButton", "TLabel", "TCheckBox", "TRadioButton"):
            comp.properties.append(
                DfmProperty(name="Caption", raw_value=det.text or cls_name))
        elif cls_name in ("TEdit", "TMemo", "TComboBox"):
            comp.properties.append(
                DfmProperty(name="Text", raw_value=det.text or ""))
        for child in node.children:
            comp.children.append(build(child))
        return comp
    
    # 创建 Form 根节点
    form = DfmComponent(
        name="Form1", class_name="TForm",
        properties=[
            DfmProperty(name="Left", raw_value="0"),
            DfmProperty(name="Top", raw_value="0"),
            DfmProperty(name="Width", raw_value=str(screen_w)),
            DfmProperty(name="Height", raw_value=str(screen_h)),
        ]
    )
    for root in hierarchy:
        form.children.append(build(root))
    
    return serialize_component(form)

def _gen_name(cls_name: str, node) -> str:
    """生成控件名称（去掉 T 前缀 + 序号）。"""
    prefix = cls_name[1:] if cls_name.startswith("T") else cls_name
    # 简单实现：用全局计数器
    return f"{prefix}{_name_counter[cls_name]}"
```

---

## 7. 输出 JSON Schema（供大模型引用）

```json
{
  "schema_version": "1.0",
  "canvas": {"width": 1920, "height": 1080},
  
  "children": [
    {
      "type": "container",
      "role": "sidebar",
      "class_hint": "TPanel",
      "rect": {"x": 0, "y": 56, "width": 240, "height": 1024},
      "layout": "vstack",
      "children": [
        {"type": "label", "text": "项目管理", "rect": {...}, "selected": true},
        {"type": "label", "text": "系统设置", "rect": {...}, "selected": false}
      ]
    },
    {
      "type": "container",
      "role": "content",
      "class_hint": "TPanel",
      "rect": {"x": 240, "y": 56, "width": 1680, "height": 1024},
      "layout": "vstack",
      "children": [
        {"type": "label", "text": "客户列表", "class_hint": "TLabel", "rect": {...}},
        {
          "type": "form-row",
          "layout": "hstack",
          "rect": {...},
          "children": [
            {"type": "input", "placeholder": "输入客户名", "class_hint": "TEdit", "rect": {...}},
            {"type": "button", "text": "搜索", "class_hint": "TButton", "rect": {...}}
          ]
        },
        {
          "type": "datagrid",
          "class_hint": "TcxGrid",
          "rect": {...},
          "columns": [
            {"name": "客户名称", "width": 200},
            {"name": "手机号", "width": 150}
          ]
        }
      ]
    }
  ]
}
```

---

## 8. 依赖变更

### pyproject.toml 增量

```toml
# 新增可选依赖组
[project.optional-dependencies]
# ... 现有依赖 ...

# 布局检测 — ONNX YOLO 推理
layout = [
    "onnx>=1.16.0",
]

# 布局检测 — 完整（含训练能力，需 GPU 或另一台机器）
layout-full = [
    "daofy-for-delphi[layout]",
    # 训练需 PyTorch，但在另一台机器做，不包含在此
]
```

### 安装步骤

```bash
# 推理环境（MCP Server 所在机器）
pip install daofy-for-delphi[layout]

# 下载 ONNX 权重（约 11MB）
# 方式 1：从训练结果下载 best.onnx
# 方式 2：使用我们提供的预训练权重（在 releases 中附带）

# 训练环境（另一台有 GPU 的机器，或 CPU 慢跑）
conda create -n yolo-train python=3.11
pip install ultralytics torch torchvision
yolo train model=yolo11n.pt data=delphi_dataset.yaml epochs=200
yolo export model=runs/train/exp/weights/best.pt format=onnx
```

### 新增模块结构

```
src/
├── detection/                     # 新增：布局检测模块
│   ├── __init__.py                # analyze_layout() 入口
│   ├── yolo_onnx.py               # ONNX YOLO 推理封装（无 torch 依赖）
│   ├── opencv_detector.py         # 传统 CV 检测（零额外依赖基线）
│   ├── layout_parser.py           # 层次结构推理
│   ├── dfm_generator.py           # 检测结果 → DFM 转换
│   ├── text_extractor.py          # 文字提取（调用现有 OCR 服务）
│   └── weights/                   # ONNX 权重缓存（.gitignore 排除）
│       └── .gitkeep
```

---

## 9. 实现路径

### Phase 1：合成数据生成 + 传统 CV 基线（3-5 人天）

| 任务 | 产出 |
|------|------|
| 合成数据脚本 | `generate_training_data.py` — 自动截图+dumpstate 采集标注 |
| YOLO 格式转换器 | dumpstate JSON → COCO/YOLO 标签格式 |
| OpenCV 元素检测 | Sobel/Canny + 轮廓 + 矩形过滤 → bbox |
| 元素分类启发式 | 按宽高比/面积/位置分类（Button/Input/Label/Panel） |
| 简单布局推理 | 空间包含 + 对齐集群 |

**依赖增量**：0 MB（全部已有）

### Phase 2：ONNX YOLO 训练与集成（5-8 人天，需另一台机器做训练）

| 任务 | 产出 |
|------|------|
| 安装 `ultralytics` + `torch`（训练机）| 训练环境 |
| 准备 Delphi 数据集（Phase 1 产出）| `dataset.yaml` + 标注文件 |
| 训练 YOLOv11n | `best.pt` + `best.onnx` |
| `yolo_onnx.py` ONNX 推理封装 | 纯 `onnxruntime` 推理，无 torch |
| 双后端融合 | CV + YOLO 结果置信度融合 |

**依赖增量（推理机）**：~19 MB（onnx + 权重）

### Phase 3：层次推理 + DFM 生成（3-5 人天）

| 任务 | 产出 |
|------|------|
| `layout_parser.py` | 空间包含 + 对齐 + 表单配对 → 层次树 |
| `dfm_generator.py` | 检测结果 → DFM 文本 |
| Schema 设计 | 供 LLM 引用的结构化 JSON 输出 |
| 属性默认值优化 | TabOrder/Align/Anchors 等合理默认值 |

### Phase 4：迭代优化（持续）

| 任务 | 产出 |
|------|------|
| 扩充训练数据类别 | 覆盖更多第三方控件（DevExpress, TMS, JVCL） |
| 布局类型精度提升 | 改进 Grid/复杂嵌套的推断 |
| 文本-控件匹配 | OCR 文字正确归属于对应的控件 |
| 事件推断 | 按钮点击行为等（VLM 辅助） |

---

## 10. 与现有工具的协同

```
截图 → 布局检测 → JSON → 大模型 → DFM + PAS 代码
                            ↓
                     manage_component → 精确插入到现有 DFM
                            ↓
                     create_component_dfm → 验证生成的 DFM 可编译
                            ↓
                     layout_audit → 检查布局质量（重叠/对齐/间距）
```

---

## 11. 参考资源

| 资源 | 链接 |
|------|------|
| YOLOv11 (Ultralytics) | https://docs.ultralytics.com/models/yolo11/ |
| ONNX Runtime | https://onnxruntime.ai/ |
| ONNX 导出文档 | https://docs.ultralytics.com/integrations/onnx |
| UIED (传统 CV 参考) | https://github.com/MulongXie/UIED |
| Rico Dataset | https://interactionmining.org/archive/rico |
| PP-OCRv6 (项目已有) | `src/services/ocr_service.py` |
| DFM Parser (项目已有) | `src/tools/dfm_parser.py` |
| Layout Audit (项目已有) | `src/tools/layout_audit.py` |
| create_component_dfm (项目已有) | `src/tools/create_component_dfm.py` |

---

## 12. 结论

**推荐方案：合成数据驱动的 YOLOv11n ONNX 推理**，原因：

1. **合成数据零成本** — `dumpstate` + `capture` 可在 2.5 分钟产出数万级 Delphi 专用标注
2. **推理依赖仅 +19 MB** — `onnxruntime` 项目已预装，只需加 `onnx` 包和 ~11MB ONNX 权重
3. **无需 GPU** — ONNX 推理在 CPU 上跑，~30-100ms/图
4. **Phase 1 零增量依赖即可开工** — OpenCV + NumPy 已装好
5. **DFM 生成复用现有工具** — `dfm_parser.serialize_component()` 直接产出 DFM 文本

---

## 13. 审计发现与方案改进

### 13.1 ✅ 已验证的假设

| 假设 | 结果 | 证据 |
|------|:----:|------|
| YOLO ONNX 输出格式 `[1, 4+N, 8400]` | ✅ 正确 | Ultralytics 文档确认，代码模板中的 post-processing 流程无误 |
| 可导出 NMS 内嵌的 ONNX (`nms=True`) | ✅ 可行 | 导出时加 `nms=True`，输出简化 `[1, max_det, 6]`，省去 Python 端 NMS |
| 合成数据可控制类别分布 | ✅ 可行 | 训练时通过 dataset.yaml 的采样权重或生成脚本控制 |
| `onnxruntime` 已安装 | ✅ 项目已装 | `onnxruntime 1.27.0` 已存在于 OCR 可选依赖中 |
| **`onnx` 包在推理侧不需要** | ✅ 确认 | `onnxruntime` 直接加载 `.onnx` 文件推理，`onnx` 包仅用于训练后的模型验证 |

### 13.2 ⚠️ 审计问题汇总

#### 问题 1：小控件检测（已解决）

**问题**：YOLOv11n 默认输入 640×640，若原始截图为 1920×1080 则缩放比 ~0.33，16×16 图标变为 ~5px → 不可检测。

**解决方案（用户提供）**：合成数据生成时**主动将窗体截图 resize 到 640×480**（标准 VCL 客户区大小），再送入 YOLO。此时缩放比为 1.0，16×16 图标仍为 16×16 像素，在 P3 特征层（stride 8）覆盖 2×2 网格——**绰绰有余**。

```
特征层   Stride   网格     16×16 覆盖格数   可检测？
P3        8      80×80    2×2             ✅
P4       16      40×40    1×1             ✅
P5       32      20×20    0.5×0.5         ❌ (但不依赖此层)
```

**注意**：训练数据和推理数据的预处理必须一致——都先 resize 到 640×480，再 pad 到 640×640。

#### 问题 2：依赖增量可进一步缩减

原方案写了需安装 `onnx` 包（~8MB）。审计发现**推理侧不需要 `onnx` 包**——`onnxruntime` 可以直接加载 `.onnx` 模型文件：

```python
import onnxruntime as ort
session = ort.InferenceSession("yolo11n.onnx")  # OK，无需 onnx 包
```

因此推理侧**实际新增依赖为 0 个包**，仅需下载 ~11MB 的 ONNX 权重文件。

```diff
- layout = ["onnx>=1.16.0"]
+ # 推理侧无需新增包，onnxruntime 已装
+ # 仅需下载 weights/best.onnx (~11MB)
```

#### 问题 3：`_gen_name` 控件命名实现有 Bug

原代码使用了未初始化且未递增的全局 `_name_counter` 字典。修正：

```python
def _gen_name(cls_name: str, seen_names: set[str]) -> str:
    prefix = cls_name[1:] if cls_name.startswith("T") else cls_name
    idx = 1
    while f"{prefix}{idx}" in seen_names:
        idx += 1
    name = f"{prefix}{idx}"
    seen_names.add(name)
    return name
```

#### 问题 4：ONNX 导出推荐 `nms=True`

`model.export(format="onnx", nms=True)` 导出时内嵌 NMS，输出简化为 `[1, max_det, 6]`，不需要在 Python 端实现 NMS 算法。

#### 问题 5：缺少量化验证指标

需要定义清晰的精度目标，用于判断训练是否收敛：

```yaml
# 评估指标
mAP@0.5:      > 0.85   # 目标
mAP@0.5:0.95: > 0.65   # 目标
Recall:       > 0.90   # 不要漏检控件
Precision:    > 0.85   # 不要误报
Small_AP:     > 0.60   # 小控件（面积<32²）的精度
Container_AP: > 0.80   # 容器类（TPanel）的精度
```

#### 问题 6：需要 Plan B 备选方案

如果 YOLO 训练收敛不理想（数据集太小、类别分布不均衡），备选方案是纯传统 CV：

```
截图 → OpenCV 形态学 → 轮廓 → 矩形区域
     → 按宽高比/面积启发式分类
     → OCR 文字提取
     → 空间包含 → 层次树
     → DFM 生成
```

精度较低（~60-70%）但**零额外依赖、零训练、零等待**。

#### 问题 7：数据增强策略需针对 UI 优化

UI 截图不是自然图像。以下增强**禁止**使用：

| 禁止的增强 | 原因 |
|-----------|------|
| GaussianBlur / noise | 模糊文字笔画，破坏 OCR |
| Heavy color jitter | 改变按钮颜色，影响类型判断 |
| Random rotation | UI 控件从不旋转 |

推荐的结构保持增强：

| 增强 | 说明 |
|------|------|
| Random crop (0.6-1.0) | 模拟不同位置的局部截图 |
| Horizontal flip (p=0.5) | Delphi UI 偶尔对称 |
| Brightness ±20% | 模拟不同显示器亮度 |
| Mosaic (p=0.5) | 拼图增强上下文多样性 |
| Scale ±10% | 模拟不同 DPI |
| Random erasing (p=0.1) | 模拟控件被遮挡 |

#### 问题 8：训练数据去重

不同窗体可能共享相同视觉的控件（如 50 个窗体共用同一个 `TFindUnitDialog`）。直接混合训练会造成分布偏差。

**建议**：生成数据时对每个控件的布局特征（位置+尺寸+类型）做哈希去重，确保训练集不偏向重复出现的控件。
