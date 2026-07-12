"""
detection — UI 截图布局检测模块

从 UI 截图中检测控件元素（按钮、输入框、标签、面板等），
推断层次结构，并生成 Delphi DFM 文本。

管线架构:
  截图 → 元素检测 → 文字提取 → 层次推理 → DFM 生成

使用方式:
    from src.detection import analyze_layout

    result = analyze_layout("screenshot.png")
    # result["dfm_text"]  → DFM 文本
    # result["layout_json"] → 结构化布局 JSON
    # result["elements"]   → 检测到的元素列表
"""

from .opencv_detector import OpenCVDetector, Detection
from .layout_parser import LayoutParser, LayoutNode
from .dfm_generator import DFMGenerator
from .yolo_onnx import YOLOONNXDetector

__all__ = [
    "analyze_layout",
    "OpenCVDetector",
    "Detection",
    "LayoutParser",
    "LayoutNode",
    "DFMGenerator",
    "YOLOONNXDetector",
]


def analyze_layout(
    image_path: str,
    backend: str = "cv",
    model_path: str | None = None,
    conf_thresh: float = 0.25,
) -> dict:
    """完整管线：截图 → 结构化布局 JSON + DFM 文本。

    ⚠️ 当前版本仅检测元素位置、类型和层次结构。
       文字内容（Caption/Text）需要 OCR 配合提取，
       将在后续 Phase 中集成。

    Args:
        image_path: 截图文件路径。
        backend: 检测后端:
            "cv"    — OpenCV 传统 CV（默认，零依赖基线）
            "yolo"  — YOLOv11 ONNX 推理（需下载权重）
        model_path: YOLO ONNX 模型路径（backend="yolo" 时必填）。
        conf_thresh: 检测置信度阈值。

    Returns:
        {
            "success": True/False,
            "error": "错误信息（失败时）",
            "elements": [Detection, ...],           # 检测到的元素
            "layout_tree": [LayoutNode, ...],        # 层次布局树
            "layout_json": { ... },                  # 结构化 JSON
            "dfm_text": "DFM 文本（成功时）",
            "backend": "cv|yolo",
        }
    """
    # 1. 元素检测
    if backend == "yolo":
        try:
            from .yolo_onnx import YOLOONNXDetector
            detector = YOLOONNXDetector(model_path or "", conf_thresh)
        except ImportError as e:
            return {"success": False, "error": f"YOLO 后端不可用: {e}"}
        except FileNotFoundError as e:
            return {"success": False, "error": str(e)}
    else:
        detector = OpenCVDetector()

    try:
        elements = detector.detect(image_path)
    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}

    if not elements:
        return {
            "success": False,
            "error": "未检测到任何 UI 元素",
            "elements": [],
            "backend": backend,
        }

    # 2. 层次结构推理
    parser = LayoutParser()
    tree = parser.build_hierarchy(elements)

    # 3. 布局 JSON
    layout_json = parser.to_json(tree, image_path)

    # 4. DFM 生成
    generator = DFMGenerator()
    try:
        dfm_text = generator.generate(tree, image_path)
    except Exception as e:
        return {
            "success": False,
            "error": f"DFM 生成失败: {e}",
            "elements": elements,
            "layout_tree": tree,
            "layout_json": layout_json,
            "backend": backend,
        }

    return {
        "success": True,
        "elements": elements,
        "layout_tree": tree,
        "layout_json": layout_json,
        "dfm_text": dfm_text,
        "backend": backend,
    }
