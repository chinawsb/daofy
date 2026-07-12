"""
yolo_onnx — YOLOv11 ONNX 推理封装（无 PyTorch 依赖）

使用 onnxruntime 加载 .onnx 格式的 YOLOv11 模型，
完成前处理（letterbox resize）、推理、NMS 后处理。

依赖:
  - onnxruntime（OCR 可选依赖已包含）
  - opencv-python-headless（已包含）
  - numpy（已包含）

用法:
    from src.detection.yolo_onnx import YOLOONNXDetector

    detector = YOLOONNXDetector("yolo11n.onnx", conf_thresh=0.25)
    detections = detector.detect("screenshot.png")
    # → [Detection(class_id=1, class_name="TButton", ...), ...]

支持 nms=True 内嵌的 ONNX 模型与 nms=False 的原始输出。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .opencv_detector import Detection

logger = logging.getLogger(__name__)

# YOLO 默认类别名（仅 fallback，用户训练后应替换为自定义映射表）
_DEFAULT_CLASS_NAMES = {
    0: "TButton",
    1: "TEdit",
    2: "TLabel",
    3: "TComboBox",
    4: "TCheckBox",
    5: "TRadioButton",
    6: "TPanel",
    7: "TGroupBox",
    8: "TListBox",
    9: "TListView",
    10: "TPageControl",
    11: "TTabSheet",
    12: "TStringGrid",
    13: "TcxGrid",
    14: "TcxButton",
    15: "TcxTextEdit",
}


class YOLOONNXDetector:
    """YOLOv11 ONNX 推理封装。

    Args:
        model_path: .onnx 模型文件路径。
        conf_thresh: 置信度阈值，低于此值的检测框被过滤。
        iou_thresh: NMS 的 IoU 阈值，默认 0.45。
        class_names: 类别 ID → 名称的映射字典。
        input_size: 模型输入尺寸 (w, h)，默认 (640, 640)。
    """

    def __init__(
        self,
        model_path: str,
        conf_thresh: float = 0.25,
        iou_thresh: float = 0.45,
        class_names: Optional[dict[int, str]] = None,
        input_size: Tuple[int, int] = (640, 640),
    ):
        self.conf_thresh = conf_thresh
        self.iou_thresh = iou_thresh
        self.class_names = class_names or _DEFAULT_CLASS_NAMES
        self.input_size = input_size

        if not os.path.isfile(model_path):
            raise FileNotFoundError(
                f"ONNX 模型文件不存在: {model_path}\n"
                "请先下载或训练模型，参考 docs/layout-completeness-detection.md"
            )

        import onnxruntime as ort

        # 优先使用 CUDA，不可用时回退 CPU
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        try:
            self.session = ort.InferenceSession(
                model_path, providers=providers,
            )
        except Exception:
            logger.warning("CUDA 不可用，使用 CPU 推理")
            self.session = ort.InferenceSession(
                model_path, providers=["CPUExecutionProvider"],
            )

        # 获取输入/输出信息
        self.input_name = self.session.get_inputs()[0].name
        input_shape = self.session.get_inputs()[0].shape
        self.input_channels = input_shape[1] if len(input_shape) > 1 else 3

        # 判断是否为 nms=True（内嵌 NMS）的模型
        # nms=True 输出: [1, max_det, 6] = (x1, y1, x2, y2, conf, class_id)
        # nms=False 输出: [1, 84, 8400] = (4 bbox + 80 cls × N candidates)
        out_shape = self.session.get_outputs()[0].shape
        # 动态维度可能是字符串（如 'anchors'），需安全取值
        def _dim_val(d, default=0):
            return d if isinstance(d, (int, float)) else default
        dim1 = _dim_val(out_shape[1]) if len(out_shape) > 1 else 0
        dim2 = _dim_val(out_shape[2]) if len(out_shape) > 2 else 0
        # nms=True 模型输出形状为 [1, max_det, 6]，6 表示 (x1,y1,x2,y2,conf,cls_id)
        # nms=False 模型输出形状为 [1, 84, N] 或 [1, 5+num_classes, N]
        self.has_nms = len(out_shape) == 3 and dim2 == 6

        logger.info(
            "YOLO ONNX 已加载: %s (输入 %s, 输出 %s, NMS=%s)",
            Path(model_path).name, input_shape, out_shape, self.has_nms,
        )

    def detect(self, image_path: str) -> List[Detection]:
        """对截图执行 YOLO 检测。

        Args:
            image_path: 截图文件路径。

        Returns:
            检测到的元素列表。
        """
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"无法读取图片: {image_path}")

        orig_h, orig_w = img.shape[:2]

        # 1. 前处理: letterbox resize
        input_tensor, scale, pad_left, pad_top = self._preprocess(img)

        # 2. 推理
        outputs = self.session.run(None, {self.input_name: input_tensor})
        raw = outputs[0]  # [1, N, 6] 或 [1, 84, 8400]

        # 3. 后处理
        if self.has_nms:
            detections = self._postprocess_nms(raw, scale, pad_left, pad_top)
        else:
            detections = self._postprocess_raw(raw, scale, pad_left, pad_top)

        logger.info(
            "YOLO ONNX 检测完成: %d 个元素 (原图 %dx%d, 置信度≥%.2f)",
            len(detections), orig_w, orig_h, self.conf_thresh,
        )
        return detections

    def _preprocess(self, img: np.ndarray) -> Tuple[np.ndarray, float, int, int]:
        """Letterbox resize 前处理。

        Returns:
            (input_tensor, scale, pad_left, pad_top)
                - input_tensor: [1, 3, H, W] float32
                - scale: 缩放比例
                - pad_left/pad_top: 填充像素数
        """
        target_w, target_h = self.input_size
        h, w = img.shape[:2]

        scale = min(target_w / w, target_h / h)
        new_w = int(w * scale)
        new_h = int(h * scale)

        # 缩放
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        # 创建画布 + 填充
        canvas = np.full((target_h, target_w, 3), 114, dtype=np.uint8)
        pad_left = (target_w - new_w) // 2
        pad_top = (target_h - new_h) // 2
        canvas[pad_top:pad_top + new_h, pad_left:pad_left + new_w] = resized

        # 归一化 + CHW + batch
        input_tensor = canvas.astype(np.float32) / 255.0
        input_tensor = input_tensor.transpose(2, 0, 1)  # HWC → CHW
        input_tensor = np.expand_dims(input_tensor, axis=0)  # CHW → NCHW

        return input_tensor, scale, pad_left, pad_top

    def _postprocess_nms(
        self, raw: np.ndarray,
        scale: float, pad_left: int, pad_top: int,
    ) -> List[Detection]:
        """解析 nms=True 模型输出 [1, max_det, 6]。"""
        results: List[Detection] = []
        boxes = raw[0]  # [max_det, 6]

        for row in boxes:
            x1, y1, x2, y2, conf, cls_id = row
            if conf < self.conf_thresh:
                continue

            # 转换回原图坐标
            x1 = (x1 - pad_left) / scale
            y1 = (y1 - pad_top) / scale
            x2 = (x2 - pad_left) / scale
            y2 = (y2 - pad_top) / scale

            w = int(round(x2 - x1))
            h_val = int(round(y2 - y1))
            if w < 2 or h_val < 2:
                continue

            cls_id_int = int(cls_id)
            class_name = self.class_names.get(cls_id_int, f"Unknown_{cls_id_int}")

            results.append(Detection(
                class_id=cls_id_int,
                class_name=class_name,
                confidence=float(conf),
                x=int(round(x1)),
                y=int(round(y1)),
                w=w,
                h=h_val,
            ))

        return results

    def _postprocess_raw(
        self, raw: np.ndarray,
        scale: float, pad_left: int, pad_top: int,
    ) -> List[Detection]:
        """解析 nms=False 模型输出 [1, 84, 8400]。"""
        raw = raw[0]  # [84, 8400]

        # 前 4 行: bbox (cx, cy, w, h)
        # 后续: class confidences
        bbox = raw[:4]  # [4, 8400]
        scores = raw[4:]  # [80, 8400]

        # 解析候选框
        boxes: List[Tuple[float, float, float, float, float, int]] = []
        for i in range(scores.shape[1]):
            max_score = float(np.max(scores[:, i]))
            if max_score < self.conf_thresh:
                continue

            cls_id = int(np.argmax(scores[:, i]))
            cx = float(bbox[0, i])
            cy_val = float(bbox[1, i])
            bw = float(bbox[2, i])
            bh = float(bbox[3, i])

            # 转成 x1, y1, x2, y2
            x1 = cx - bw / 2
            y1_val = cy_val - bh / 2
            x2 = cx + bw / 2
            y2_val = cy_val + bh / 2

            # 转换回原图坐标
            x1 = int(round((x1 - pad_left) / scale))
            y1_val = int(round((y1_val - pad_top) / scale))
            x2 = int(round((x2 - pad_left) / scale))
            y2_val = int(round((y2_val - pad_top) / scale))

            if x2 - x1 < 2 or y2_val - y1_val < 2:
                continue

            boxes.append((float(x1), float(y1_val), float(x2), float(y2_val), max_score, cls_id))

        # NMS
        keep = self._nms(boxes, self.iou_thresh)

        results: List[Detection] = []
        for idx in keep:
            x1, y1_val, x2_val, y2_val, conf, cls_id = boxes[idx]
            cls_id_int = int(cls_id)
            class_name = self.class_names.get(cls_id_int, f"Unknown_{cls_id_int}")
            results.append(Detection(
                class_id=cls_id_int,
                class_name=class_name,
                confidence=conf,
                x=int(x1),
                y=int(y1_val),
                w=int(x2_val - x1),
                h=int(y2_val - y1_val),
            ))

        return results

    @staticmethod
    def _nms(
        boxes: List[Tuple[float, float, float, float, float, int]],
        iou_thresh: float,
    ) -> List[int]:
        """纯 NumPy NMS 实现。"""
        if not boxes:
            return []

        bbox = np.array([b[:4] for b in boxes], dtype=np.float32)
        scores = np.array([b[4] for b in boxes], dtype=np.float32)

        # 按置信度降序排列
        order = scores.argsort()[::-1]

        x1 = bbox[:, 0]
        y1 = bbox[:, 1]
        x2 = bbox[:, 2]
        y2 = bbox[:, 3]

        areas = (x2 - x1 + 1) * (y2 - y1 + 1)
        keep = []

        while order.size > 0:
            i = order[0]
            keep.append(int(i))

            if order.size == 1:
                break

            # 计算交并比
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])

            inter = np.maximum(0, xx2 - xx1 + 1) * np.maximum(0, yy2 - yy1 + 1)
            iou = inter / (areas[i] + areas[order[1:]] - inter)

            idx = np.where(iou <= iou_thresh)[0]
            order = order[idx + 1]

        return keep
