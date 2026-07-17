"""MCP Tool: ocr — 图像分析（文字识别 + 视觉分析）

使用 PP-OCRv6 medium 模型进行图像文字检测和识别。
纯 ONNX Runtime 实现，零 PaddlePaddle 依赖。
模型首次使用时自动下载到 data/ocr-models/。

Actions:
  recognize  — 完整 OCR：检测 + 识别，返回 [{text, confidence, box}]
  detect     — 仅文本框检测，返回 [{box, score}]
  status     — 模型加载状态
  diff       — 截图差异对比：比较两张截图，返回视觉变化区域
  color      — 区域颜色分析：分析指定区域的平均色/主色/亮度
  match      — 图标模板匹配：在截图中查找指定图标/图案
  analyze    — [统一截图分析] 串联 OCR + OpenCV 检测 + 布局 + 颜色，
               返回结构化元素列表（含 type/text/rect/state/paired_label），
               供 LLM 直接从文本推理 UI 结构，不需要多模态模型。
"""

import logging
import os

from src.services.ocr_service import get_ocr_service

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 视觉分析函数（纯 Pillow/OpenCV，不依赖 PP-OCR 模型）
# ═══════════════════════════════════════════════════════════════


def _image_diff(baseline_path: str, current_path: str,
                threshold: int = 10, output_dir: str = "") -> dict:
    """比较两张截图，找出视觉差异区域。

    Args:
        baseline_path: 基线截图路径
        current_path: 当前截图路径
        threshold: 像素差异阈值（0-255，默认 10）
        output_dir: 差异图输出目录（空则不保存）

    Returns:
        dict: {changed, diff_pixels, diff_percent, regions, diff_image?}
    """
    import cv2
    import numpy as np

    img1 = cv2.imread(baseline_path)
    img2 = cv2.imread(current_path)

    if img1 is None:
        raise FileNotFoundError(f"无法读取基线图片: {baseline_path}")
    if img2 is None:
        raise FileNotFoundError(f"无法读取当前图片: {current_path}")

    # 尺寸不一致时 resize 当前图匹配基线
    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

    diff = cv2.absdiff(img1, img2)
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

    diff_pixels = int(np.sum(thresh > 0))
    total_pixels = thresh.size
    diff_percent = round(diff_pixels / total_pixels * 100, 4)

    # 连通域分析找出变化区域
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)

    regions = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w * h < 16:  # 过滤微小噪点
            continue
        area_pct = round((w * h) / total_pixels * 100, 4)
        mean_diff = float(np.mean(gray[y:y + h, x:x + w]))
        regions.append({
            "bbox": [int(x), int(y), int(x + w), int(y + h)],
            "area_pct": area_pct,
            "mean_diff": round(mean_diff, 1),
        })

    regions.sort(key=lambda r: r["area_pct"], reverse=True)

    result = {
        "changed": diff_pixels > 0,
        "diff_pixels": int(diff_pixels),
        "diff_percent": diff_percent,
        "regions": regions[:50],
    }

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(baseline_path))[0]
        diff_path = os.path.join(output_dir, f"diff_{base}.png")
        cv2.imwrite(diff_path, diff)
        result["diff_image"] = diff_path

    return result


def _region_color(image_path: str,
                  region: list | None = None,
                  threshold: float | None = None) -> dict:
    """分析图片指定区域的颜色特征。

    Args:
        image_path: 图片路径
        region: [x, y, w, h] 分析区域，不传则分析全图
        threshold: 亮度阈值(0~1)。设置后将像素按亮度分为暗/亮两组，
                   分别计算 avg_color，便于分离文字色和背景色。

    Returns:
        dict: {avg_color, median_color, brightness, is_grayscale,
               dark_avg?, light_avg?, dark_count?, light_count?}
    """
    from PIL import Image
    import numpy as np

    img = Image.open(image_path).convert("RGB")

    if region:
        x, y, w, h = region
        img = img.crop((x, y, x + w, y + h))

    pixels = np.array(img, dtype=np.float32)

    # 亮度加权公式: 0.299 R + 0.587 G + 0.114 B
    brightness_map = (pixels[:, :, 0] * 0.299 +
                      pixels[:, :, 1] * 0.587 +
                      pixels[:, :, 2] * 0.114) / 255.0

    avg = [round(float(pixels[:, :, i].mean())) for i in range(3)]
    median = [round(float(np.median(pixels[:, :, i]))) for i in range(3)]
    stddev = [float(pixels[:, :, i].std()) for i in range(3)]

    is_gray = bool(all(s < 15 for s in stddev)
                   and max(avg) - min(avg) < 30)
    brightness = round(sum(avg) / (255 * 3), 3)

    result = {
        "avg_color": {"r": avg[0], "g": avg[1], "b": avg[2]},
        "median_color": {"r": median[0], "g": median[1], "b": median[2]},
        "brightness": brightness,
        "is_grayscale": is_gray,
        "region": {"w": img.width, "h": img.height},
    }

    # 亮度阈值分离：将像素按亮度分为暗组(文字/前景)和亮组(背景/高亮)
    if threshold is not None:
        dark_mask = brightness_map < threshold
        light_mask = ~dark_mask

        dark_count = int(dark_mask.sum())
        light_count = int(light_mask.sum())

        if dark_count > 0:
            dark_avg = [round(float(pixels[:, :, i][dark_mask].mean()))
                        for i in range(3)]
            result["dark_avg"] = {"r": dark_avg[0], "g": dark_avg[1],
                                  "b": dark_avg[2]}
        result["dark_count"] = dark_count

        if light_count > 0:
            light_avg = [round(float(pixels[:, :, i][light_mask].mean()))
                         for i in range(3)]
            light_brightness = round(
                (light_avg[0] * 0.299 + light_avg[1] * 0.587 +
                 light_avg[2] * 0.114) / 255.0, 3)
            result["light_avg"] = {"r": light_avg[0], "g": light_avg[1],
                                   "b": light_avg[2]}
            result["light_brightness"] = light_brightness
        result["light_count"] = light_count

    return result


def _template_match(image_path: str, template_path: str,
                    threshold: float = 0.8) -> dict:
    """在截图中查找模板图标/图案。

    Args:
        image_path: 截图路径
        template_path: 模板图片路径
        threshold: 匹配阈值（0-1，默认 0.8）

    Returns:
        dict: {found, match_count, matches[{bbox, confidence}]}
    """
    import cv2
    import numpy as np

    img = cv2.imread(image_path)
    tpl = cv2.imread(template_path)

    if img is None:
        raise FileNotFoundError(f"无法读取图片: {image_path}")
    if tpl is None:
        raise FileNotFoundError(f"无法读取模板: {template_path}")

    if img.shape[0] < tpl.shape[0] or img.shape[1] < tpl.shape[1]:
        return {"found": False, "match_count": 0, "matches": [],
                "error": "模板尺寸大于截图"}

    result_mat = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result_mat >= threshold)

    h, w = tpl.shape[:2]
    raw_matches = []
    for pt in zip(*locations[::-1]):
        x, y = pt
        raw_matches.append({
            "bbox": [int(x), int(y), int(x + w), int(y + h)],
            "confidence": round(float(result_mat[y, x]), 3),
        })

    # 非极大值抑制（NMS）去重
    raw_matches.sort(key=lambda m: m["confidence"], reverse=True)
    kept = []
    for m in raw_matches:
        overlapping = False
        for k in kept:
            if _bbox_overlap(m["bbox"], k["bbox"]) > 0.5:
                overlapping = True
                break
        if not overlapping:
            kept.append(m)

    return {
        "found": len(kept) > 0,
        "match_count": len(kept),
        "matches": kept[:20],
        "threshold_used": threshold,
    }


def _bbox_overlap(a: list, b: list) -> float:
    """计算两个 bbox 的 IoU。"""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    xi1, yi1 = max(ax1, bx1), max(ay1, by1)
    xi2, yi2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    a_area = (ax2 - ax1) * (ay2 - ay1)
    b_area = (bx2 - bx1) * (by2 - by1)
    union = a_area + b_area - inter
    return inter / union if union > 0 else 0


# ═══════════════════════════════════════════════════════════════
# 统一截图分析（串联 OCR + Detection + 布局 + 颜色）
# ═══════════════════════════════════════════════════════════════


def _bbox_iou(a_box: list, b_box: list) -> float:
    """计算两个 bbox 的 IoU，兼容 OCR 四点格式 [[x1,y1],[x2,y2],...]。"""
    # 兼容四点格式 → [x1,y1,x2,y2]
    def _to_xyxy(box):
        if isinstance(box[0], list):
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            return [min(xs), min(ys), max(xs), max(ys)]
        return box

    a = _to_xyxy(a_box)
    b = _to_xyxy(b_box)
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    xi1 = max(ax1, bx1)
    yi1 = max(ay1, by1)
    xi2 = min(ax2, bx2)
    yi2 = min(ay2, by2)
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    a_area = (ax2 - ax1) * (ay2 - ay1)
    b_area = (bx2 - bx1) * (by2 - by1)
    union = a_area + b_area - inter
    return inter / union if union > 0 else 0


def _infer_element_state(img, x: int, y: int, w: int, h: int) -> str:
    """基于颜色分析推断 UI 元素状态（enabled/disabled）。
    
    简单启发式：平均亮度低 + 低标准偏差 + 低饱和度 → disabled。
    """
    import numpy as np

    img_h, img_w = img.shape[:2]
    x = max(0, x)
    y = max(0, y)
    w = min(w, img_w - x)
    h = min(h, img_h - y)
    if w <= 0 or h <= 0:
        return "enabled"

    roi = img[y:y + h, x:x + w].astype(np.float32)
    brightness = (roi[:, :, 0] * 0.299 + roi[:, :, 1] * 0.587 + roi[:, :, 2] * 0.114) / 255.0
    avg_b = float(np.mean(brightness))
    std_b = float(np.std(brightness))

    # 饱和度
    r, g, b = roi[:, :, 0], roi[:, :, 1], roi[:, :, 2]
    max_rgb = np.maximum(np.maximum(r, g), b).astype(float)
    min_rgb = np.minimum(np.minimum(r, g), b).astype(float)
    sat = float(np.mean((max_rgb - min_rgb) / (max_rgb + 1e-6)))

    # 灰暗 + 低对比度 → disabled
    if avg_b < 0.45 and std_b < 20 and sat < 0.15:
        return "disabled"
    return "enabled"


def _pair_labels_with_inputs(elements: list[dict]):
    """将标签文字与相邻输入框配对（就地修改）。
    
    规则：
    - 标签检测：以 ':'/':'/':' 结尾的文字
    - 输入框在标签右侧，垂直对齐相近
    """
    labels = []
    inputs = []
    for elem in elements:
        text = elem.get("text", "").strip()
        if text.endswith(":") or text.endswith("：") or text.endswith(":"):
            labels.append(elem)
            elem["role"] = "label"
        elif elem.get("type") in ("edit", "combobox", "listbox", "memo", "textbox", "dropdown"):
            inputs.append(elem)

    for label in labels:
        lr = label["rect"]
        cy = lr["y"] + lr["h"] / 2
        right = lr["x"] + lr["w"]

        best = None
        best_dist = float("inf")
        for inp in inputs:
            ir = inp["rect"]
            in_cy = ir["y"] + ir["h"] / 2
            if ir["x"] < right - 5:
                continue
            y_dist = abs(cy - in_cy)
            if y_dist > max(lr["h"], ir["h"]) * 2:
                continue
            dist = (ir["x"] - right) + y_dist * 2
            if dist < best_dist:
                best_dist = dist
                best = inp

        if best:
            best["paired_label"] = text.rstrip(":： ").strip()
            best["paired_label_rect"] = label["rect"]


def _get_detector():
    """自动选择检测后端：自定义训练模型 → 通用 YOLO → OpenCV（回退）。
    
    Returns:
        (detector, backend_name) 
    """
    base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    
    # 1. 优先使用自定义训练的 Delphi 模型
    custom_path = os.path.join(base, "data", "yolo_models", "daofy_train.onnx")
    if os.path.isfile(custom_path):
        try:
            from src.detection.yolo_onnx import YOLOONNXDetector
            class_names = {
                0: "TButton", 1: "TEdit", 2: "TLabel", 3: "TComboBox",
                4: "TCheckBox", 5: "TRadioButton", 6: "TListBox", 7: "TPanel",
                8: "TGroupBox", 9: "TPageControl", 10: "TTabSheet", 11: "TStringGrid",
                12: "TMemo", 13: "TListView", 14: "TTreeView", 15: "TProgressBar",
                16: "TTrackBar", 17: "TScrollBar", 18: "TScrollBox", 19: "TStatusBar",
            }
            return YOLOONNXDetector(custom_path, conf_thresh=0.3, class_names=class_names), "yolo+custom"
        except Exception as e:
            logger.warning(f"自定义模型加载失败，尝试通用模型: {e}")

    # 2. 回退到通用 Windows UI 模型
    yolo_path = os.path.join(base, "data", "yolo_models", "windows-ui-locator.onnx")
    if os.path.isfile(yolo_path):
        try:
            from src.detection.yolo_onnx import YOLOONNXDetector
            class_names = {
                0: "button", 1: "textbox", 2: "checkbox",
                3: "dropdown", 4: "icon", 5: "tab", 6: "menu_item",
            }
            return YOLOONNXDetector(yolo_path, conf_thresh=0.3, class_names=class_names), "yolo"
        except Exception as e:
            logger.warning(f"通用 YOLO 加载失败，回退 OpenCV: {e}")

    from src.detection.opencv_detector import OpenCVDetector
    return OpenCVDetector(), "opencv"


def _analyze_screenshot(image_path: str) -> dict:
    """统一截图分析：串联 OCR + YOLO/OpenCV 检测 + 布局 + 颜色。
    
    Args:
        image_path: 截图路径
        
    Returns:
        {
            elements: [{type, class_hint, text, rect, state, paired_label?}],
            layout: {树形布局},
            summary: "共N个元素: ...",
            ...
        }
    """
    import cv2

    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"无法读取图片: {image_path}")

    h, w = img.shape[:2]

    # 1. OCR 识别文字
    svc = get_ocr_service()
    ocr_results = svc.recognize(image_path)

    # 2. UI 元素检测（YOLO → OpenCV 回退）
    from src.detection.layout_parser import LayoutParser

    detector, backend = _get_detector()
    detections = detector.detect(image_path)

    # 3. 合并 OCR → 检测结果
    elements = []
    for det in detections:
        det_box = [det.x, det.y, det.x + det.w, det.y + det.h]
        matched = [(ocr["text"], _bbox_iou(det_box, ocr["box"]))
                   for ocr in ocr_results if _bbox_iou(det_box, ocr["box"]) > 0.1]
        text = max(matched, key=lambda x: x[1])[0] if matched else ""

        state = _infer_element_state(img, det.x, det.y, det.w, det.h)

        elements.append({
            "type": det.class_name.removeprefix("T").lower(),
            "class_hint": det.class_name,
            "text": text,
            "rect": {"x": det.x, "y": det.y, "w": det.w, "h": det.h},
            "confidence": det.confidence,
            "state": state,
        })

    # 4. Label-Input 配对
    _pair_labels_with_inputs(elements)

    # 5. 布局树
    parser = LayoutParser()
    layout_roots = parser.build_hierarchy(detections)
    layout_json = parser.to_json(layout_roots, image_path) if layout_roots else {}

    # 6. 摘要
    type_counts: dict[str, int] = {}
    enabled = disabled = 0
    for el in elements:
        t = el["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
        if el["state"] == "disabled":
            disabled += 1
        else:
            enabled += 1

    parts = [f"{c}个{t}" for t, c in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)]

    return {
        "status": "ok",
        "action": "analyze",
        "backend": backend,
        "image": os.path.basename(image_path),
        "dimensions": {"width": w, "height": h},
        "element_count": len(elements),
        "elements": elements,
        "layout": layout_json,
        "state_summary": f"{enabled}个enabled / {disabled}个disabled",
        "summary": f"共{len(elements)}个元素: {', '.join(parts)}",
    }


# ═══════════════════════════════════════════════════════════════
# MCP Tool Handler
# ═══════════════════════════════════════════════════════════════


def handle_ocr(arguments: dict) -> dict:
    """处理 OCR 工具调用。

    Args:
        arguments: 工具参数
            action: "recognize"|"detect"|"status"|"diff"|"color"|"match"|"analyze"
            image_path: 图片路径
            baseline/current: diff 的两张图片
            template_path: match 的模板图片
            region: color 的分析区域 [x,y,w,h]
            threshold: diff 阈值(默认10) / match 阈值(默认0.8)
            output_dir: diff 差异图输出目录

    Returns:
        dict: 处理结果
    """
    action = arguments.get("action", "recognize")
    image_path = arguments.get("image_path", "")

    try:
        # === 视觉分析 action（不依赖 PP-OCR 模型）===

        if action == "diff":
            baseline = arguments.get("baseline", "")
            current = arguments.get("current", "")
            if not baseline or not current:
                return {"status": "failed",
                        "error": "diff 需要 baseline 和 current 参数"}
            threshold = int(arguments.get("threshold", 10))
            output_dir = arguments.get("output_dir", "")
            result = _image_diff(baseline, current, threshold, output_dir)
            result.update({"status": "ok", "action": "diff"})
            return result

        if action == "color":
            if not image_path or not os.path.isfile(image_path):
                return {"status": "failed",
                        "error": "color 需要有效的 image_path"}
            region = arguments.get("region")
            threshold = arguments.get("threshold")
            if threshold is not None:
                threshold = float(threshold)
            result = _region_color(image_path, region, threshold)
            result.update({"status": "ok", "action": "color"})
            return result

        if action == "match":
            template_path = arguments.get("template_path", "")
            if not image_path or not template_path:
                return {"status": "failed",
                        "error": "match 需要 image_path 和 template_path"}
            threshold = float(arguments.get("threshold", 0.8))
            result = _template_match(image_path, template_path, threshold)
            result.update({"status": "ok", "action": "match"})
            return result

        # === 原有 OCR action（依赖 PP-OCR 模型）===

        svc = get_ocr_service()

        if action == "status":
            return svc.status()

        if not image_path:
            return {"status": "failed", "error": "缺少必需参数: image_path"}

        if not os.path.isfile(image_path):
            return {"status": "failed", "error": f"文件不存在: {image_path}"}

        if action == "recognize":
            results = svc.recognize(image_path)
            return {"status": "ok", "action": "recognize",
                    "count": len(results), "results": results}

        elif action == "detect":
            results = svc.detect(image_path)
            return {"status": "ok", "action": "detect",
                    "count": len(results), "results": results}

        elif action == "analyze":
            return _analyze_screenshot(image_path)

        else:
            return {"status": "failed",
                    "error": "未知 action，支持: recognize/detect/status/diff/color/match/analyze"}

    except FileNotFoundError as e:
        return {"status": "failed", "error": str(e)}
    except ImportError as e:
        return {"status": "failed",
                "error": f"缺少依赖: {e}。请安装: pip install daofy-for-delphi[ocr]"}
    except Exception as e:
        logger.error(f"OCR 处理失败: {e}", exc_info=True)
        return {"status": "failed", "error": f"OCR 处理失败: {e}"}
