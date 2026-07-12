"""
layout_parser — 层次结构推理

将扁平的 Detection 列表转化为层次化布局树。
通过空间包含、对齐集群、间距分析推断布局结构。

处理流程:
  1. 空间包含分析 → 容器-子元素父子关系
  2. 对齐集群分析 → HStack/VStack/Grid 布局类型
  3. 表单配对 → Label-Input 关联
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2

from .opencv_detector import Detection

logger = logging.getLogger(__name__)

# 容器类型的 class_id 集合
_CONTAINER_IDS = {9}  # TPanel


@dataclass
class LayoutNode:
    """布局树节点。"""
    detection: Detection
    children: List["LayoutNode"] = field(default_factory=list)
    layout_type: str = "single"  # single / hstack / vstack / grid / zstack
    role: str = ""               # container / form-row / sidebar / ...

    @property
    def area(self) -> int:
        return self.detection.area


class LayoutParser:
    """布局结构推理器。"""

    def __init__(self, container_tolerance: float = 0.9):
        """
        Args:
            container_tolerance: 容器包含判断的 IoU 阈值。
                一个元素被认为"在容器内"的条件是：
                容器与该元素的 IoU >= container_tolerance。
        """
        self.tolerance = container_tolerance

    def build_hierarchy(self, detections: List[Detection]) -> List[LayoutNode]:
        """从扁平的 Detection 列表构建层次布局树。

        Args:
            detections: 检测到的元素列表（已按面积降序排列）。

        Returns:
            布局树根节点列表。
        """
        if not detections:
            return []

        # 确保按面积降序排列（容器先处理）
        sorted_dets = sorted(detections, key=lambda d: d.area, reverse=True)
        roots: List[LayoutNode] = []
        assigned: set[int] = set()  # 已分配父容器的元素索引

        # 第一遍：容器优先建立父子关系
        nodes = [LayoutNode(detection=d) for d in sorted_dets]

        for i, container_node in enumerate(nodes):
            if i in assigned:
                continue
            if container_node.detection.class_id not in _CONTAINER_IDS:
                continue

            for j, child_node in enumerate(nodes):
                if j in assigned or i == j:
                    continue
                if self._contains(container_node.detection, child_node.detection):
                    container_node.children.append(child_node)
                    assigned.add(j)

        # 第二遍：未被容器包含的成为根节点
        for i, node in enumerate(nodes):
            if i not in assigned:
                roots.append(node)

        # 第三遍：推断每个节点的布局类型
        for root in roots:
            self._infer_layout_type(root)

        return roots

    def _contains(self, container: Detection, child: Detection) -> bool:
        """判断 child 是否在 container 内部（空间包含）。"""
        # child 的 bbox 必须完全在 container 内部
        child_in_container = (
            child.x >= container.x
            and child.y >= container.y
            and child.x + child.w <= container.x + container.w
            and child.y + child.h <= container.y + container.h
        )
        if not child_in_container:
            return False

        # 子元素面积不能超过容器的 95%（否则可能同级）
        return child.area < container.area * 0.95

    def _infer_layout_type(self, node: LayoutNode) -> str:
        """递归推断节点的布局类型。"""
        for child in node.children:
            self._infer_layout_type(child)

        if len(node.children) < 2:
            node.layout_type = "single"
            return node.layout_type

        elements = [c.detection for c in node.children]
        layout = self._detect_layout(elements)
        node.layout_type = layout
        return layout

    @staticmethod
    def _detect_layout(elements: List[Detection]) -> str:
        """推断一组子元素的布局排列方式。"""
        if len(elements) < 2:
            return "single"

        centers_x = [e.cx for e in elements]
        centers_y = [e.cy for e in elements]
        y_spread = max(centers_y) - min(centers_y)
        x_spread = max(centers_x) - min(centers_x)
        avg_h = sum(e.h for e in elements) / len(elements)
        avg_w = sum(e.w for e in elements) / len(elements)

        # HStack: Y 中心接近，水平分布
        if y_spread < avg_h * 0.6 and x_spread > avg_w * 0.5:
            return "hstack"

        # VStack: X 中心接近，垂直分布
        if x_spread < avg_w * 0.6 and y_spread > avg_h * 0.5:
            return "vstack"

        # Grid: 检查行列间距一致性
        if LayoutParser._is_grid(elements):
            return "grid"

        return "zstack"

    @staticmethod
    def _is_grid(elements: List[Detection]) -> bool:
        """检查元素是否构成网格布局。"""
        if len(elements) < 4:
            return False

        # 按 top 坐标分组（行）
        tops = sorted(set(e.y for e in elements))
        rows = []
        for t in tops:
            row = [e for e in elements if abs(e.y - t) < 8]
            if len(row) >= 2:
                rows.append(row)

        # 按 left 坐标分组（列）
        lefts = sorted(set(e.x for e in elements))
        cols = []
        for l in lefts:
            col = [e for e in elements if abs(e.x - l) < 8]
            if len(col) >= 2:
                cols.append(col)

        # 至少 2 行且至少 2 列
        return len(rows) >= 2 and len(cols) >= 2

    # 表单配对（Label-Input）识别 — 后续 Phase 3 接入

    def to_json(self, roots: List[LayoutNode], image_path: str) -> dict:
        """将布局树序列化为结构化 JSON（供大模型引用）。"""
        img = cv2.imread(image_path)
        h, w = img.shape[:2] if img is not None else (0, 0)

        def node_to_dict(node: LayoutNode) -> dict:
            d = {
                "type": node.detection.class_name.lower().lstrip("t"),
                "class_hint": node.detection.class_name,
                "rect": {
                    "x": node.detection.x,
                    "y": node.detection.y,
                    "w": node.detection.w,
                    "h": node.detection.h,
                },
                "layout": node.layout_type,
                "confidence": node.detection.confidence,
            }
            if node.detection.text:
                d["text"] = node.detection.text
            if node.children:
                d["children"] = [node_to_dict(c) for c in node.children]
            return d

        return {
            "schema_version": "1.0",
            "canvas": {"width": w, "height": h},
            "children": [node_to_dict(r) for r in roots],
        }
