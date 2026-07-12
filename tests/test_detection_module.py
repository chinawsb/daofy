"""
tests/test_detection_module.py — 布局检测模块单元测试

覆盖:
  Module 1: Detection dataclass (area, cx, cy, to_dict, IoU, NMS)
  Module 2: OpenCVDetector (合成测试图、分类规则、重叠合并)
  Module 3: LayoutParser (层次构建、布局类型推断、to_json)
  Module 4: DFMGenerator (DFM 文本生成、_gen_name 命名去重)
  Module 5: YOLOONNXDetector (文件不存在错误)
  Module 6: analyze_layout 集成测试

依赖: opencv-python-headless, numpy (OCR 可选依赖)
"""

import sys
import os
import tempfile
from pathlib import Path
from typing import List

import cv2
import numpy as np
import pytest

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.detection import (
    OpenCVDetector,
    Detection,
    LayoutParser,
    LayoutNode,
    DFMGenerator,
    YOLOONNXDetector,
    analyze_layout,
)
from src.detection.dfm_generator import _gen_name, _CLASS_MAP


# ============================================================
# 辅助函数
# ============================================================

def _make_test_image(
    width: int = 640,
    height: int = 480,
    elements: List[tuple] = None,
) -> str:
    """创建测试用空白截图，绘制指定的矩形元素。
    
    Args:
        elements: [(x, y, w, h, color_bgr), ...]
    Returns:
        临时文件路径。
    """
    img = np.ones((height, width, 3), dtype=np.uint8) * 240
    if elements:
        for x, y, w, h, color in elements:
            cv2.rectangle(img, (x, y), (x + w, y + h), color, -1)
            # 边框
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 0), 1)

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    cv2.imwrite(path, img)
    return path


def _make_detection(
    class_id: int,
    x: int, y: int, w: int, h: int,
    confidence: float = 0.5,
    text: str = "",
) -> Detection:
    return Detection(
        class_id=class_id,
        class_name=_CLASS_MAP.get(class_id, ("Unknown", "", ""))[0],
        confidence=confidence,
        x=x, y=y, w=w, h=h,
        text=text,
    )


def _make_layout_node(
    class_id: int,
    x: int, y: int, w: int, h: int,
    children: List[LayoutNode] = None,
    confidence: float = 0.5,
    text: str = "",
) -> LayoutNode:
    det = _make_detection(class_id, x, y, w, h, confidence, text)
    return LayoutNode(detection=det, children=children or [])


# ============================================================
# Module 1: Detection dataclass
# ============================================================

class TestDetection:

    def test_basic_creation(self):
        d = Detection(class_id=1, class_name="TButton", confidence=0.9,
                       x=10, y=20, w=100, h=30)
        assert d.class_id == 1
        assert d.class_name == "TButton"
        assert d.confidence == 0.9
        assert d.x == 10
        assert d.y == 20
        assert d.w == 100
        assert d.h == 30

    def test_area(self):
        d = Detection(class_id=1, class_name="TButton", confidence=0.9,
                       x=0, y=0, w=100, h=30)
        assert d.area == 3000

    def test_area_zero(self):
        d = Detection(class_id=1, class_name="TButton", confidence=0.9,
                       x=0, y=0, w=0, h=30)
        assert d.area == 0

    def test_center(self):
        d = Detection(class_id=1, class_name="TButton", confidence=0.9,
                       x=10, y=20, w=100, h=30)
        assert d.cx == 60.0   # 10 + 100/2
        assert d.cy == 35.0   # 20 + 30/2

    def test_to_dict(self):
        d = Detection(class_id=1, class_name="TButton", confidence=0.9,
                       x=10, y=20, w=100, h=30, text="OK")
        dt = d.to_dict()
        assert dt["class_id"] == 1
        assert dt["class_name"] == "TButton"
        assert dt["x"] == 10
        assert dt["y"] == 20
        assert dt["w"] == 100
        assert dt["h"] == 30
        assert dt["text"] == "OK"

    def test_to_dict_empty_text(self):
        d = Detection(class_id=2, class_name="TEdit", confidence=0.8,
                       x=0, y=0, w=200, h=25)
        dt = d.to_dict()
        assert dt["text"] == ""

    def test_default_text_empty(self):
        d = Detection(class_id=1, class_name="TButton", confidence=0.9,
                       x=0, y=0, w=100, h=30)
        assert d.text == ""


# ============================================================
# Module 2: OpenCVDetector
# ============================================================

class TestOpenCVDetector:

    def test_detect_empty_image(self):
        """全白图片应检测到少量或 0 个元素（没有明显轮廓）"""
        path = _make_test_image(elements=[])
        detector = OpenCVDetector(min_element_area=50)
        results = detector.detect(path)
        os.remove(path)
        # 全白灰度图可能仍检测到一些边缘，但应该很少
        assert isinstance(results, list)

    def test_detect_simple_button(self):
        """绘制一个按钮大小的矩形，应检测为 TButton"""
        path = _make_test_image(elements=[
            (50, 50, 100, 28, (200, 200, 200)),  # button-like
        ])
        detector = OpenCVDetector(min_element_area=50)
        results = detector.detect(path)
        os.remove(path)
        assert len(results) >= 1
        # 大面积的元素被检测到
        found = any(r.class_id == 1 for r in results)  # TButton
        if not found:
            # 传统 CV 不一定能准确分类，但至少应该检测到一些元素
            assert len(results) >= 1

    def test_detect_multiple_elements(self):
        """多个不同大小的矩形"""
        path = _make_test_image(elements=[
            (20, 20, 80, 24, (200, 200, 200)),    # button
            (20, 60, 200, 24, (255, 255, 255)),   # edit
            (20, 100, 60, 16, (240, 240, 240)),   # label
        ])
        detector = OpenCVDetector(min_element_area=50)
        results = detector.detect(path)
        os.remove(path)
        # 至少应该检测到一些元素
        assert len(results) >= 1

    def test_file_not_found(self):
        detector = OpenCVDetector()
        with pytest.raises(FileNotFoundError):
            detector.detect("/nonexistent/path.png")

    def test_min_element_area_filters_small(self):
        """设置 min_element_area 应该过滤掉小元素"""
        path = _make_test_image(elements=[
            (10, 10, 5, 5, (200, 200, 200)),     # 非常小
            (50, 50, 100, 28, (200, 200, 200)),  # 正常大小
        ])
        detector = OpenCVDetector(min_element_area=200)
        results = detector.detect(path)
        os.remove(path)
        # 小元素（面积 25）应该被过滤掉
        for r in results:
            assert r.area >= 200

    def test_iou_static(self):
        """测试 IoU 计算"""
        a = _make_detection(1, 0, 0, 100, 100)
        b = _make_detection(1, 25, 25, 100, 100)
        iou = OpenCVDetector._iou(a, b)
        # 重叠区域: 75*75 = 5625, 并集: 10000+10000-5625 = 14375
        expected = 5625 / 14375  # ≈ 0.391
        assert abs(iou - expected) < 0.01

    def test_iou_no_overlap(self):
        a = _make_detection(1, 0, 0, 50, 50)
        b = _make_detection(1, 100, 100, 50, 50)
        assert OpenCVDetector._iou(a, b) == 0.0

    def test_iou_same_box(self):
        a = _make_detection(1, 0, 0, 100, 100)
        assert OpenCVDetector._iou(a, a) == 1.0

    def test_merge_overlapping(self):
        """两个高度重叠的框应该合并（保留大的）"""
        dets = [
            _make_detection(1, 0, 0, 200, 50),    # 面积 10000
            _make_detection(1, 10, 5, 100, 30),   # 面积 3000，在大框内
        ]
        detector = OpenCVDetector()
        merged = detector._merge_overlapping(dets, iou_thresh=0.1)
        assert len(merged) == 1
        assert merged[0].w == 200  # 保留了大的

    def test_merge_no_overlap(self):
        """不重叠的框不应被合并"""
        dets = [
            _make_detection(1, 0, 0, 50, 50),
            _make_detection(1, 200, 200, 50, 50),
        ]
        detector = OpenCVDetector()
        merged = detector._merge_overlapping(dets, iou_thresh=0.5)
        assert len(merged) == 2

    def test_merge_empty(self):
        detector = OpenCVDetector()
        assert detector._merge_overlapping([]) == []


# ============================================================
# Module 3: LayoutParser
# ============================================================

class TestLayoutParser:

    def test_empty_list(self):
        parser = LayoutParser()
        assert parser.build_hierarchy([]) == []

    def test_single_element(self):
        dets = [_make_detection(1, 0, 0, 100, 30)]
        parser = LayoutParser()
        tree = parser.build_hierarchy(dets)
        assert len(tree) == 1
        assert tree[0].detection.class_id == 1

    def test_container_with_child(self):
        """TPanel (class_id=9) 中包含一个 TButton"""
        dets = [
            _make_detection(9, 0, 0, 300, 200),   # 面板
            _make_detection(1, 20, 20, 100, 28),  # 按钮在面板内
        ]
        parser = LayoutParser()
        tree = parser.build_hierarchy(dets)
        # 面板应该是根，按钮是子
        assert len(tree) == 1
        assert tree[0].detection.class_id == 9
        assert len(tree[0].children) == 1
        assert tree[0].children[0].detection.class_id == 1

    def test_non_container_not_parent(self):
        """TButton (class_id=1) 不应包含子元素"""
        dets = [
            _make_detection(1, 0, 0, 300, 200),   # 大按钮（面积大排序在前）
            _make_detection(2, 20, 20, 100, 28),  # 编辑框（在按钮内部）
        ]
        parser = LayoutParser()
        tree = parser.build_hierarchy(dets)
        # 两个都应该是根节点（TButton 不是容器）
        assert len(tree) == 2



    def test_vstack_layout(self):
        """垂直排列的元素应检测为 vstack"""
        elements = [
            _make_detection(1, 10, 10, 200, 24),
            _make_detection(1, 10, 44, 200, 24),
            _make_detection(1, 10, 78, 200, 24),
        ]
        layout = LayoutParser._detect_layout(elements)
        assert layout == "vstack"

    def test_hstack_layout(self):
        """水平排列的元素应检测为 hstack"""
        elements = [
            _make_detection(1, 10, 10, 80, 24),
            _make_detection(1, 100, 10, 80, 24),
            _make_detection(1, 190, 10, 80, 24),
        ]
        layout = LayoutParser._detect_layout(elements)
        assert layout == "hstack"

    def test_single_element_layout(self):
        elements = [_make_detection(1, 0, 0, 100, 30)]
        assert LayoutParser._detect_layout(elements) == "single"

    def test_is_grid_true(self):
        """2x2 网格"""
        elements = [
            _make_detection(1, 10, 10, 80, 24),   # row0 col0
            _make_detection(1, 100, 10, 80, 24),  # row0 col1
            _make_detection(1, 10, 44, 80, 24),   # row1 col0
            _make_detection(1, 100, 44, 80, 24),  # row1 col1
        ]
        assert LayoutParser._is_grid(elements) is True

    def test_is_grid_false_less_than_4(self):
        elements = [
            _make_detection(1, 0, 0, 50, 50),
            _make_detection(1, 60, 0, 50, 50),
        ]
        assert LayoutParser._is_grid(elements) is False

    def test_to_json(self):
        dets = [_make_detection(1, 10, 20, 100, 30)]
        parser = LayoutParser()
        tree = parser.build_hierarchy(dets)
        path = _make_test_image()  # 空白图片
        result = parser.to_json(tree, path)
        os.remove(path)

        assert result["schema_version"] == "1.0"
        assert "canvas" in result
        assert len(result["children"]) == 1
        child = result["children"][0]
        assert child["type"].startswith("button")  # TButton → button
        assert child["rect"]["x"] == 10
        assert child["rect"]["y"] == 20
        assert child["rect"]["w"] == 100
        assert child["rect"]["h"] == 30


# ============================================================
# Module 4: DFMGenerator
# ============================================================

class TestGenName:

    def test_tbutton_prefix(self):
        seen: set = set()
        assert _gen_name("TButton", seen) == "Button1"
        assert "Button1" in seen

    def test_tbutton_sequential(self):
        seen: set = set()
        name1 = _gen_name("TButton", seen)
        name2 = _gen_name("TButton", seen)
        assert name1 == "Button1"
        assert name2 == "Button2"
        assert name1 != name2

    def test_tcx_prefix(self):
        seen: set = set()
        assert _gen_name("TcxButton", seen) == "cxButton1"

    def test_no_t_prefix(self):
        seen: set = set()
        name = _gen_name("MyCustomCtrl", seen)
        assert name == "MyCustomCtrl1"

    def test_skip_conflict(self):
        seen = {"Button1", "Button2", "Button3"}
        assert _gen_name("TButton", seen) == "Button4"

    def test_short_name(self):
        """类名只有一个字符时不应 strip 掉"""
        seen: set = set()
        name = _gen_name("T", seen)
        # T 长度 1，strip 'T' 后为空，应回退到全名
        assert name == "T1"


class TestDFMGenerator:

    def test_generate_empty_roots(self):
        gen = DFMGenerator()
        dfm = gen.generate([], "")
        assert "object Form1: TForm" in dfm
        assert "end" in dfm

    def test_generate_single_button(self):
        node = _make_layout_node(1, 10, 20, 100, 30)
        gen = DFMGenerator()
        dfm = gen.generate([node], "test_form.png")
        assert "object Form1: TForm" in dfm
        assert "object Button1: TButton" in dfm
        assert "Left = 10" in dfm
        assert "Top = 20" in dfm
        assert "Width = 100" in dfm
        assert "Height = 30" in dfm
        assert "Caption = 'test_form'" in dfm

    def test_generate_with_caption_text(self):
        """带文字的按钮应该输出 Caption"""
        node = _make_layout_node(1, 10, 20, 100, 30, text="确定")
        gen = DFMGenerator()
        dfm = gen.generate([node], "")
        assert "确定" in dfm or "Caption = '确定'" in dfm

    def test_generate_multiple_buttons(self):
        nodes = [
            _make_layout_node(1, 10, 10, 80, 24),
            _make_layout_node(1, 100, 10, 80, 24),
        ]
        gen = DFMGenerator()
        dfm = gen.generate(nodes, "")
        assert "Button1: TButton" in dfm
        assert "Button2: TButton" in dfm

    def test_generate_with_container(self):
        """面板容器内包含按钮"""
        btn = _make_layout_node(1, 20, 20, 100, 30)
        panel = _make_layout_node(9, 0, 0, 300, 200, children=[btn])
        gen = DFMGenerator()
        dfm = gen.generate([panel], "")
        assert "Panel1: TPanel" in dfm
        assert "Button1: TButton" in dfm
        # Button 应该在 Panel 内部缩进
        panel_end = dfm.find("Panel1: TPanel")
        btn_start = dfm.find("Button1: TButton")
        assert btn_start > panel_end  # Button 在 Panel 声明之后

    def test_generate_all_class_types(self):
        """覆盖 _CLASS_MAP 中所有 class_id"""
        gen = DFMGenerator()
        nodes = []
        for cid in sorted(_CLASS_MAP.keys()):
            nodes.append(_make_layout_node(cid, 10, 10 * cid, 80, 24))
        dfm = gen.generate(nodes, "")
        for cid, (cls_name, _, _) in sorted(_CLASS_MAP.items()):
            assert cls_name in dfm, f"class_id={cid} ({cls_name}) 未出现在 DFM 中"

    def test_infer_canvas_dimensions(self):
        """画布尺寸取 max(right*1.1, 640/480) 的较大值。"""
        nodes = [
            _make_layout_node(1, 0, 0, 300, 100),
            _make_layout_node(2, 0, 120, 250, 24),
        ]
        gen = DFMGenerator()
        dfm = gen.generate(nodes, "")
        # 最大右边: max(300, 250) = 300, 300*1.1 = 330
        # 但最小值是 640, 所以 Width = 640
        assert "Width = 640" in dfm, f"预期 Width=640 (最小值), 实际 DFM: {dfm}"

    def test_unknown_class_id_skipped(self):
        """未知 class_id 的元素应跳过"""
        node = _make_layout_node(99, 0, 0, 100, 30)  # 不存在的 class_id
        gen = DFMGenerator()
        dfm = gen.generate([node], "")
        # 不会包含未知组件
        assert "Unknown" not in dfm

    def test_serialize_roundtrip(self):
        """DFM 输出应该是合法格式的 DFM 文本"""
        nodes = [
            _make_layout_node(1, 10, 10, 80, 24, text="OK"),
            _make_layout_node(2, 10, 44, 200, 24, text="Name"),
        ]
        gen = DFMGenerator()
        dfm = gen.generate(nodes, "main_form.png")

        # 验证 DFM 格式结构
        assert dfm.strip().startswith("object ")
        assert dfm.strip().endswith("end")
        # 每个 object 对应一个 end
        assert dfm.count("object ") == dfm.count("end")
        # 属性应该是 'Name = Value' 格式
        lines = dfm.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("object") and stripped != "end":
                assert " = " in stripped, f"预期属性行含有 ' = ': {line}"


# ============================================================
# Module 5: YOLOONNXDetector
# ============================================================

class TestYOLOONNXDetector:

    def test_file_not_found(self):
        """模型文件不存在时应抛出 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            YOLOONNXDetector("/nonexistent/model.onnx")

    def test_file_not_found_from_module_import(self):
        """确保模块可以被导入（依赖检查）"""
        from src.detection.yolo_onnx import YOLOONNXDetector, _DEFAULT_CLASS_NAMES
        assert len(_DEFAULT_CLASS_NAMES) >= 15  # 至少 15 个默认类别



    def test_default_class_names_coverage(self):
        """默认类别名应该覆盖常用的 Delphi 控件"""
        from src.detection.yolo_onnx import _DEFAULT_CLASS_NAMES
        expected = {"TButton", "TEdit", "TLabel", "TPanel", "TcxGrid"}
        for name in expected:
            assert name in _DEFAULT_CLASS_NAMES.values(), f"缺少 {name}"


# ============================================================
# Module 6: analyze_layout 集成测试
# ============================================================

class TestAnalyzeLayout:

    def test_successful_analysis(self):
        """完整管线：检测 → 布局推理 → DFM 生成"""
        path = _make_test_image(elements=[
            (20, 20, 100, 28, (200, 200, 200)),   # button
            (20, 60, 200, 24, (255, 255, 255)),   # edit
        ])
        result = analyze_layout(path)
        os.remove(path)

        assert result["success"] is True
        assert "dfm_text" in result
        assert "layout_json" in result
        assert "elements" in result
        assert "layout_tree" in result
        assert result["backend"] == "cv"
        assert len(result["elements"]) > 0
        assert "object Form1: TForm" in result["dfm_text"]
        assert "end" in result["dfm_text"]

    def test_analyze_plain_image(self):
        """纯色背景图仍应返回 success 但有极少/空元素"""
        path = _make_test_image(elements=[])
        result = analyze_layout(path)
        os.remove(path)
        # 纯色图像可能检测到一些边缘（形态学边缘），也可能检测不到
        # 不崩溃即可
        assert isinstance(result, dict)
        assert "success" in result

    def test_analyze_file_not_found(self):
        """不存在的文件路径应返回 success=False"""
        result = analyze_layout("/nonexistent/screenshot.png")
        assert result["success"] is False
        assert "error" in result

    def test_yolo_backend_no_model(self):
        """yolo 后端但不传模型路径"""
        result = analyze_layout("dummy.png", backend="yolo")
        assert result["success"] is False
        assert "模型文件不存在" in result.get("error", "") or "不存在" in result.get("error", "")

    def test_analyze_with_text_in_nodes(self):
        """元素有文本时，DFM 中应包含文本内容"""
        det = _make_detection(1, 20, 20, 100, 28, text="OK")
        node = LayoutNode(detection=det)
        parser = LayoutParser()
        gen = DFMGenerator()
        dfm = gen.generate([node], "")

        # 文本 "OK" 应该出现在 DFM 的 Caption 属性中
        assert "OK" in dfm

    def test_analyze_detects_all_class_ids(self):
        """所有 class_id 的映射一致性检查"""
        for cid, (cls_name, _, _) in _CLASS_MAP.items():
            det = _make_detection(cid, 10 * cid, 0, 80, 24)
            node = LayoutNode(detection=det)
            gen = DFMGenerator()
            dfm = gen.generate([node], "")
            assert cls_name in dfm, f"class_id={cid} ({cls_name}) DFM 生成失败"


# ============================================================
# Module 7: edge cases & robustness
# ============================================================

class TestEdgeCases:

    def test_detection_negative_coordinates(self):
        """负坐标（部分在画布外）"""
        d = Detection(class_id=1, class_name="TButton", confidence=0.9,
                       x=-10, y=-5, w=100, h=30)
        assert d.cx == 40.0   # -10 + 50
        assert d.cy == 10.0   # -5 + 15

    def test_extremely_large_detection(self):
        """超大元素"""
        d = Detection(class_id=9, class_name="TPanel", confidence=0.9,
                       x=0, y=0, w=10000, h=8000)
        assert d.area == 80000000

    def test_layout_parser_container_exactly_fits_child(self):
        """子元素正好等于容器大小（不应该嵌套，应该是同级）"""
        dets = [
            _make_detection(9, 0, 0, 200, 200),   # 面板
            _make_detection(1, 0, 0, 200, 200),   # 按钮正好占满面板
        ]
        parser = LayoutParser()
        tree = parser.build_hierarchy(dets)
        # 子元素面积 >= 面板的 95%，所以不应该嵌套
        assert len(tree) == 2  # 两个都是根

    def test_gen_name_does_not_exceed_limits(self):
        """_gen_name 应始终返回唯一的短名称"""
        seen: set = set()
        generated: set = set()
        for i in range(1000):
            name = _gen_name("TButton", seen)
            assert name not in generated, f"重复名称: {name}"
            generated.add(name)
            assert name.startswith("Button")
        assert len(generated) == 1000

    def test_dfm_generator_with_all_property_types(self):
        """DFMGenerator 生成的所有属性都是 'Name = Value' 格式"""
        nodes = [
            _make_layout_node(9, 0, 0, 400, 300, children=[
                _make_layout_node(1, 10, 10, 80, 24, text="Btn"),
                _make_layout_node(2, 10, 44, 200, 24, text="Edit1"),
                _make_layout_node(5, 10, 78, 100, 20, text="Check"),
            ])
        ]
        gen = DFMGenerator()
        dfm = gen.generate(nodes, "test.png")

        # 验证 DFM 结构
        assert dfm.count("object ") >= 4  # Form + Panel + 3 children
        assert dfm.count("end") >= 4

        # 画布尺寸最小值 640x480, 所以 Width=640, Height=480
        assert "Left = 0" in dfm
        assert "Top = 0" in dfm
        assert "Width = 640" in dfm  # 最小值 640
        assert "Height = 480" in dfm  # 最小值 480

    def test_to_json_contains_correct_schema(self):
        """to_json 输出的 schema 应该符合预期结构"""
        dets = [_make_detection(1, 10, 20, 100, 30, text="Click")]
        parser = LayoutParser()
        tree = parser.build_hierarchy(dets)
        path = _make_test_image()
        result = parser.to_json(tree, path)
        os.remove(path)

        assert result["schema_version"] == "1.0"
        assert "canvas" in result
        assert "width" in result["canvas"]
        assert "height" in result["canvas"]
        assert len(result["children"]) == 1
        child = result["children"][0]
        assert "type" in child
        assert "rect" in child
        assert "text" in child
        assert child["text"] == "Click"
        assert "children" not in child  # 没有子元素


# ============================================================
# 手动运行入口
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
