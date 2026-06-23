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
                  region: list | None = None) -> dict:
    """分析图片指定区域的颜色特征。

    Args:
        image_path: 图片路径
        region: [x, y, w, h] 分析区域，不传则分析全图

    Returns:
        dict: {avg_color, median_color, brightness, is_grayscale}
    """
    from PIL import Image, ImageStat

    img = Image.open(image_path).convert("RGB")

    if region:
        x, y, w, h = region
        img = img.crop((x, y, x + w, y + h))

    stat = ImageStat.Stat(img)
    avg = [round(v) for v in stat.mean]
    median = [round(v) for v in stat.median]
    stddev = stat.stddev

    is_gray = bool(stddev and all(s < 15 for s in stddev)
                   and max(avg) - min(avg) < 30)  # 均值也接近才判灰度
    brightness = round(sum(avg) / (255 * 3), 3)

    return {
        "avg_color": {"r": avg[0], "g": avg[1], "b": avg[2]},
        "median_color": {"r": median[0], "g": median[1], "b": median[2]},
        "brightness": brightness,
        "is_grayscale": is_gray,
        "region": {"w": img.width, "h": img.height},
    }


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
# MCP Tool Handler
# ═══════════════════════════════════════════════════════════════


def handle_ocr(arguments: dict) -> dict:
    """处理 OCR 工具调用。

    Args:
        arguments: 工具参数
            action: "recognize"|"detect"|"status"|"diff"|"color"|"match"
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
            result = _region_color(image_path, region)
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

        else:
            return {"status": "failed",
                    "error": "未知 action，支持: recognize/detect/status/diff/color/match"}

    except FileNotFoundError as e:
        return {"status": "failed", "error": str(e)}
    except ImportError as e:
        return {"status": "failed",
                "error": f"缺少依赖: {e}。请安装: pip install daofy-for-delphi[ocr]"}
    except Exception as e:
        logger.error(f"OCR 处理失败: {e}", exc_info=True)
        return {"status": "failed", "error": f"OCR 处理失败: {e}"}
