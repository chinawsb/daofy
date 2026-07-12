"""
dfm_generator — 布局检测结果 → Delphi DFM 文本

将 Detection 和 LayoutNode 树转换为 DfmComponent 树，
再通过 dfm_parser.serialize_component 输出 DFM 文本。

依赖:
  - src.tools.dfm_parser (DfmComponent, DfmProperty, serialize_component)
  - src.detection.opencv_detector (Detection)
  - src.detection.layout_parser (LayoutNode)

用法:
    from src.detection.dfm_generator import DFMGenerator

    gen = DFMGenerator()
    dfm_text = gen.generate(layout_roots, image_path)
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Set

from src.tools.dfm_parser import DfmComponent, DfmProperty, serialize_component
from .opencv_detector import Detection
from .layout_parser import LayoutNode

logger = logging.getLogger(__name__)

# class_id → Delphi 属性映射
# key: class_id, value: (class_name, caption_prop, unit_hint)
_CLASS_MAP: dict[int, tuple[str, str, str]] = {
    1:  ("TButton",        "Caption",  "Vcl.StdCtrls"),
    2:  ("TEdit",          "Text",     "Vcl.StdCtrls"),
    3:  ("TLabel",         "Caption",  "Vcl.StdCtrls"),
    4:  ("TComboBox",      "Text",     "Vcl.StdCtrls"),
    5:  ("TCheckBox",      "Caption",  "Vcl.StdCtrls"),
    6:  ("TRadioButton",   "Caption",  "Vcl.StdCtrls"),
    7:  ("TListBox",       "Text",     "Vcl.StdCtrls"),
    8:  ("TListView",      "Text",     "Vcl.ComCtrls"),
    9:  ("TPanel",         "Caption",  "Vcl.ExtCtrls"),
    10: ("TScrollBox",     "",         "Vcl.Forms"),
    11: ("TGroupBox",      "Caption",  "Vcl.StdCtrls"),
    12: ("TPageControl",   "",         "Vcl.ComCtrls"),
    13: ("TTabSheet",      "Caption",  "Vcl.ComCtrls"),
    14: ("TMemo",          "Text",     "Vcl.StdCtrls"),
    15: ("TStringGrid",    "",         "Vcl.Grids"),
    16: ("TcxGrid",        "",         "cxGrid"),
    17: ("TcxButton",      "Caption",  "cxButtons"),
    18: ("TcxTextEdit",    "Text",     "cxEdit"),
    19: ("TcxComboBox",    "Text",     "cxEdit"),
    20: ("TcxCheckBox",    "Caption",  "cxEdit"),
}


def _gen_name(cls_name: str, seen_names: Set[str]) -> str:
    """为给定的类名生成唯一的实例名。
    
    TButton → Button1, Button2, ...
    TPanel  → Panel1, Panel2, ...
    """
    prefix = cls_name
    for known in ("T", "Tcx"):
        if cls_name.startswith(known) and len(cls_name) > len(known):
            prefix = cls_name[len(known):]
            break
    if not prefix:
        prefix = cls_name

    idx = 1
    while f"{prefix}{idx}" in seen_names:
        idx += 1
    name = f"{prefix}{idx}"
    seen_names.add(name)
    return name


class DFMGenerator:
    """将布局检测树转换为 Delphi DFM 文本。"""

    def __init__(self, default_form_class: str = "TForm",
                 default_form_name: str = "Form1"):
        """
        Args:
            default_form_class: 生成的 DFM 根类名，默认 TForm。
            default_form_name: 生成的 DFM 根实例名，默认 Form1。
        """
        self.default_form_class = default_form_class
        self.default_form_name = default_form_name

    def generate(self, roots: List[LayoutNode],
                 image_path: str = "") -> str:
        """生成 DFM 文本。

        Args:
            roots: 布局树根节点列表（LayoutParser.build_hierarchy 的输出）。
            image_path: 原始截图路径（仅用于日志和元信息）。

        Returns:
            DFM 格式文本字符串。
        """
        seen_names: Set[str] = set()
        seen_names.add(self.default_form_name)

        form = DfmComponent(
            name=self.default_form_name,
            class_name=self.default_form_class,
            prefix="object",
        )

        # 从截图文件名推断窗体属性
        base = os.path.splitext(os.path.basename(image_path))[0] if image_path else ""
        if base:
            form.properties.append(DfmProperty(
                name="Caption", raw_value=f"'{base}'",
            ))

        form.properties.extend([
            DfmProperty(name="Left", raw_value="0"),
            DfmProperty(name="Top", raw_value="0"),
            DfmProperty(name="Width", raw_value=self._infer_canvas_width(roots)),
            DfmProperty(name="Height", raw_value=self._infer_canvas_height(roots)),
        ])

        # 将布局树转为 DfmComponent 并添加到窗体
        for root in roots:
            comp = self._node_to_dfm(root, seen_names)
            if comp is not None:
                form.children.append(comp)

        result = serialize_component(form)
        logger.info("DFM 生成完成: %d 行, %d 个组件",
                     result.count("\n") + 1,
                     len(form.children))
        return result

    def _node_to_dfm(self, node: LayoutNode,
                     seen_names: Set[str]) -> Optional[DfmComponent]:
        """将一个 LayoutNode 转换为 DfmComponent。"""
        det = node.detection

        class_info = _CLASS_MAP.get(det.class_id)
        if class_info is None:
            logger.debug("跳过未映射的 class_id=%d (%s)",
                         det.class_id, det.class_name)
            return None

        class_name, caption_prop, _ = class_info
        comp_name = _gen_name(class_name, seen_names)

        comp = DfmComponent(
            name=comp_name,
            class_name=class_name,
            prefix="object",
        )

        # 位置属性
        comp.properties.extend([
            DfmProperty(name="Left", raw_value=str(det.x)),
            DfmProperty(name="Top", raw_value=str(det.y)),
            DfmProperty(name="Width", raw_value=str(det.w)),
            DfmProperty(name="Height", raw_value=str(det.h)),
        ])

        # 文本内容
        text = det.text or ""
        if caption_prop and text:
            comp.properties.append(DfmProperty(
                name=caption_prop, raw_value=f"'{text}'",
            ))

        # 可见状态（不可见的不生成 Visible 属性，因为默认就是 True）
        # 此处省略，因为 Detection 没有 confidence < 阈值时的标记。

        # 递归处理子节点
        for child in node.children:
            child_comp = self._node_to_dfm(child, seen_names)
            if child_comp is not None:
                comp.children.append(child_comp)

        return comp

    @staticmethod
    def _infer_canvas_width(roots: List[LayoutNode]) -> str:
        """从布局树推断画布宽度。"""
        if not roots:
            return "640"
        max_right = 0
        for node in _walk_all(roots):
            r = node.detection.x + node.detection.w
            if r > max_right:
                max_right = r
        return str(max(int(max_right * 1.1), 640))

    @staticmethod
    def _infer_canvas_height(roots: List[LayoutNode]) -> str:
        """从布局树推断画布高度。"""
        if not roots:
            return "480"
        max_bottom = 0
        for node in _walk_all(roots):
            b = node.detection.y + node.detection.h
            if b > max_bottom:
                max_bottom = b
        return str(max(int(max_bottom * 1.1), 480))


def _walk_all(roots):
    """广度遍历所有节点。"""
    stack = list(roots)
    while stack:
        node = stack.pop(0)
        yield node
        stack.extend(node.children)
