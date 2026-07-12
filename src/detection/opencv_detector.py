"""
opencv_detector — OpenCV 传统 CV UI 元素检测

零额外依赖基线方案，可用于快速原型验证。
使用 OpenCV 形态学操作检测 UI 元素边界并启发式分类。

依赖: opencv-python-headless, numpy（项目 OCR 可选依赖已包含）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    """单个检测到的 UI 元素。"""

    class_id: int          # YOLO 兼容的类别 ID
    class_name: str        # 可读的类别名称
    confidence: float      # 置信度 (0-1)
    x: int                 # left
    y: int                 # top
    w: int                 # width
    h: int                 # height
    text: str = ""         # OCR 提取的文字（初始为空，后续填充）

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def to_dict(self) -> dict:
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": self.confidence,
            "x": self.x, "y": self.y,
            "w": self.w, "h": self.h,
            "text": self.text,
        }


# 启发式分类规则：按宽高比和面积判断元素类型
_CLASS_RULES = [
    # (min_w/h_ratio, max_w/h_ratio, min_area, max_area, class_id, class_name)
    # 按钮: 宽高比在 1.5~6 之间，面积适中
    (1.5, 6.0,  400,  50000,  1, "TButton"),
    # 输入框: 宽高比 > 3，面积适中
    (3.0, 20.0, 500,  80000,  2, "TEdit"),
    # 标签: 宽高比较小，面积小
    (0.5, 6.0,  50,   30000,  3, "TLabel"),
    # 下拉框: 宽高比 > 3，右侧有箭头特征
    (3.0, 15.0, 600,  60000,  4, "TComboBox"),
    # 复选框: 接近正方形
    (0.8, 1.5,  80,   2500,   5, "TCheckBox"),
    # 单选钮: 接近正方形
    (0.8, 1.5,  80,   2500,   6, "TRadioButton"),
    # 列表: 非常大的纵向矩形
    (0.3, 4.0,  5000, 500000, 7, "TListBox"),
    # 面板/容器: 面积大
    (0.3, 5.0,  8000, 999999, 9, "TPanel"),
]


class OpenCVDetector:
    """基于 OpenCV 传统 CV 的 UI 元素检测器。

    使用形态学操作 + 轮廓分析检测控件边界，
    然后按宽高比/面积启发式分类。
    """

    def __init__(self, min_element_area: int = 50):
        """
        Args:
            min_element_area: 最小元素面积，小于此值的轮廓被忽略。
        """
        self.min_area = min_element_area

    def detect(self, image_path: str) -> List[Detection]:
        """检测截图中的 UI 元素。

        Args:
            image_path: 截图文件路径。

        Returns:
            检测到的元素列表，按面积降序排列。
        """
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"无法读取图片: {image_path}")

        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 1. 自适应阈值二值化
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 21, 5,
        )

        # 2. 形态学闭运算：合并文字区域为块
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1))
        kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_h, iterations=2)
        closed = cv2.morphologyEx(closed, cv2.MORPH_CLOSE, kernel_v, iterations=1)

        # 3. 膨胀：扩大边缘，连接相邻区域
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        dilated = cv2.dilate(closed, kernel_dilate, iterations=2)

        # 4. 轮廓提取
        contours, _ = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )

        detections: List[Detection] = []

        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            if cw < 8 or ch < 8:  # 过小的区域跳过
                continue
            area = cw * ch
            if area < self.min_area:
                continue

            # 在原始灰度图上取内部区域，辅助分类
            roi = gray[y : y + ch, x : x + cw]
            mean_brightness = float(np.mean(roi))
            std_brightness = float(np.std(roi))

            class_id, class_name = self._classify(cw, ch, area, mean_brightness, std_brightness)
            if class_id < 0:
                continue

            detections.append(Detection(
                class_id=class_id,
                class_name=class_name,
                confidence=0.5,  # 传统 CV 统一用 0.5
                x=x, y=y, w=cw, h=ch,
            ))

        # 5. 按面积降序排列（容器优先）
        detections.sort(key=lambda d: d.area, reverse=True)

        # 6. 合并高度重叠的检测框（NMS 简化版）
        detections = self._merge_overlapping(detections)

        logger.info(
            "OpenCV 检测完成: %d 个元素 (原图 %dx%d)",
            len(detections), w, h,
        )
        return detections

    def _classify(
        self, cw: int, ch: int, area: int,
        mean_brightness: float, std_brightness: float,
    ) -> tuple[int, str]:
        """启发式分类：按宽高比、面积、亮度特征判断元素类型。

        Returns:
            (class_id, class_name) 或 (-1, "") 表示未知。
        """
        ratio = cw / max(ch, 1)

        # 接近正方形的极小元素 → 复选框或单选钮
        if 0.8 <= ratio <= 1.5 and 80 <= area <= 2500:
            # 亮度较高且标准差较大 → 复选框（勾选框通常有较亮的背景）
            if mean_brightness > 150 and std_brightness > 40:
                return (5, "TCheckBox")
            return (6, "TRadioButton")

        # 大面积的平坦区域 → 面板
        if area > 8000 and cw > 100 and ch > 50:
            return (9, "TPanel")

        # 按规则表匹配
        for min_r, max_r, min_a, max_a, cid, cname in _CLASS_RULES:
            if min_r <= ratio <= max_r and min_a <= area <= max_a:
                return (cid, cname)

        # 无法分类
        return (-1, "")

    def _merge_overlapping(self, detections: List[Detection],
                           iou_thresh: float = 0.6) -> List[Detection]:
        """合并高度重叠的检测框（保留面积较大的）。"""
        if not detections:
            return []

        keep = [True] * len(detections)
        for i in range(len(detections)):
            if not keep[i]:
                continue
            for j in range(i + 1, len(detections)):
                if not keep[j]:
                    continue
                iou = self._iou(detections[i], detections[j])
                if iou > iou_thresh:
                    # 保留面积较大的框
                    if detections[i].area >= detections[j].area:
                        keep[j] = False
                    else:
                        keep[i] = False
                        break

        return [d for i, d in enumerate(detections) if keep[i]]

    @staticmethod
    def _iou(a: Detection, b: Detection) -> float:
        """计算两个检测框的 IoU。"""
        x1 = max(a.x, b.x)
        y1 = max(a.y, b.y)
        x2 = min(a.x + a.w, b.x + b.w)
        y2 = min(a.y + a.h, b.y + b.h)
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        union = a.area + b.area - inter
        return inter / max(union, 1)
