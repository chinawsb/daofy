"""
OcrService 单元测试 — 测试后端选择、后处理、解码等非模型依赖逻辑。
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest


# ============================================================
# _select_optimal_backend 测试
# ============================================================

class TestBackendSelection:

    @patch("src.services.ocr_service._detect_cpu_vendor", return_value="amd")
    @patch("src.services.ocr_service._check_openvino_available", return_value=False)
    @patch("src.services.ocr_service.sys", version_info=(3, 14, 5))
    def test_amd_py314_returns_onnxruntime(self, mock_sys, mock_ov, mock_cpu):
        """AMD + Python 3.14 → onnxruntime"""
        from src.services.ocr_service import _select_optimal_backend
        assert _select_optimal_backend() == "onnxruntime"

    @patch("src.services.ocr_service._detect_cpu_vendor", return_value="intel")
    @patch("src.services.ocr_service._check_openvino_available", return_value=True)
    @patch("src.services.ocr_service.sys", version_info=(3, 14, 5))
    def test_intel_openvino_py314_returns_openvino(self, mock_sys, mock_ov, mock_cpu):
        """Intel + openvino 可用 + Python 3.14 → openvino"""
        from src.services.ocr_service import _select_optimal_backend
        assert _select_optimal_backend() == "openvino"

    @patch("src.services.ocr_service._detect_cpu_vendor", return_value="intel")
    @patch("src.services.ocr_service._check_openvino_available", return_value=False)
    @patch("src.services.ocr_service.sys", version_info=(3, 12, 0))
    def test_intel_no_openvino_returns_onnxruntime(self, mock_sys, mock_ov, mock_cpu):
        """Intel + openvino 不可用 → onnxruntime"""
        from src.services.ocr_service import _select_optimal_backend
        assert _select_optimal_backend() == "onnxruntime"

    @patch("src.services.ocr_service._detect_cpu_vendor", return_value="intel")
    @patch("src.services.ocr_service._check_openvino_available", return_value=True)
    @patch("src.services.ocr_service.sys", version_info=(3, 12, 0))
    def test_intel_openvino_py312_returns_openvino(self, mock_sys, mock_ov, mock_cpu):
        """Intel + openvino 可用 + Python 3.12 → openvino"""
        from src.services.ocr_service import _select_optimal_backend
        assert _select_optimal_backend() == "openvino"


# ============================================================
# _detect_cpu_vendor 测试
# ============================================================

class TestDetectCpuVendor:

    @patch("platform.processor", return_value="GenuineIntel")
    def test_intel_processor(self, mock_proc):
        from src.services.ocr_service import _detect_cpu_vendor
        assert _detect_cpu_vendor() == "intel"

    @patch("platform.processor", return_value="AMD64 Family 25 Model 97 Stepping 2")
    def test_amd_processor(self, mock_proc):
        from src.services.ocr_service import _detect_cpu_vendor
        assert _detect_cpu_vendor() == "amd"


# ============================================================
# _load_character_dict 测试
# ============================================================

class TestLoadCharacterDict:

    def test_load_from_file(self):
        """从文件加载字符字典。"""
        from src.services.ocr_service import _load_character_dict
        content = "a\nb\nc\n"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as f:
            f.write(content)
            f.flush()
            path = Path(f.name)
        try:
            chars = _load_character_dict(path)
            assert "a" in chars
            assert "b" in chars
            assert "c" in chars
        finally:
            path.unlink()

    def test_empty_file_fallback(self):
        """空文件回退到默认最小字典。"""
        from src.services.ocr_service import _load_character_dict
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as f:
            f.write("")
            f.flush()
            path = Path(f.name)
        try:
            chars = _load_character_dict(path)
            # 最小字典包含数字 + 字母
            assert "0" in chars
            assert "a" in chars
        finally:
            path.unlink()


# ============================================================
# _order_points 测试
# ============================================================

class TestOrderPoints:

    def test_order_points_standard(self):
        """标准矩形四点排序。"""
        from src.services.ocr_service import _order_points
        pts = np.array([[100, 100], [200, 100], [200, 200], [100, 200]], dtype=np.float32)
        # 打乱顺序
        shuffled = pts[[2, 0, 3, 1]]
        ordered = _order_points(shuffled)
        # 左上
        assert ordered[0][0] == 100 and ordered[0][1] == 100
        # 右上
        assert ordered[1][0] == 200 and ordered[1][1] == 100
        # 右下
        assert ordered[2][0] == 200 and ordered[2][1] == 200
        # 左下
        assert ordered[3][0] == 100 and ordered[3][1] == 200


# ============================================================
# _ctc_decode 测试
# ============================================================

class TestCtcDecode:

    def test_simple_sequence(self):
        """简单的数字序列解码。"""
        from src.services.ocr_service import _ctc_decode
        char_list = list("0123456789")  # 纯字符，不含 blank
        num_classes = len(char_list) + 1  # blank at index 0

        T = 10
        preds = np.zeros((T, num_classes), dtype=np.float32)
        # 模型索引 N → char_list[N-1], blank=0
        # '1'=char_list[1] → model idx 2, '2'=char_list[2] → idx 3
        preds[0, 0] = 0.9      # blank
        preds[1, 2] = 0.9      # '1'
        preds[2, 0] = 0.9      # blank
        preds[3, 3] = 0.9      # '2'
        preds[4, 0] = 0.9      # blank
        preds[5, 0] = 0.9      # blank
        preds[6, 4] = 0.9      # '3'
        preds[7, 0] = 0.9      # blank
        preds[8, 0] = 0.9      # blank
        preds[9, 0] = 0.9      # blank

        text, conf = _ctc_decode(preds, char_list)
        assert text == "123"
        assert conf > 0.8

    def test_blank_only(self):
        """全是 blank → 空字符串。"""
        from src.services.ocr_service import _ctc_decode
        char_list = list("abc")  # 纯字符
        num_classes = len(char_list) + 1  # blank at 0
        preds = np.zeros((5, num_classes), dtype=np.float32)
        preds[:, 0] = 1.0  # 全预测 blank

        text, conf = _ctc_decode(preds, char_list)
        assert text == ""
        assert conf == 0.0

    def test_collapse_repeats(self):
        """连续相同字符去重。"""
        from src.services.ocr_service import _ctc_decode
        char_list = list("ab")  # 纯字符
        num_classes = len(char_list) + 1  # blank at 0
        preds = np.zeros((6, num_classes), dtype=np.float32)
        preds[0, 0] = 1.0  # blank
        preds[1, 1] = 1.0  # 'a' (char_list[0])
        preds[2, 1] = 1.0  # 'a' 重复，应折叠
        preds[3, 0] = 1.0  # blank
        preds[4, 2] = 1.0  # 'b' (char_list[1])
        preds[5, 0] = 1.0  # blank

        text, conf = _ctc_decode(preds, char_list)
        assert text == "ab"


# ============================================================
# _db_post_process 测试
# ============================================================

class TestDbPostProcess:

    def test_no_detections(self):
        """全零概率图 → 空结果。"""
        from src.services.ocr_service import _db_post_process
        pred_map = np.zeros((64, 64), dtype=np.float32)
        boxes = _db_post_process(pred_map, (256, 256))
        assert boxes == []

    def test_single_box_detection(self):
        """有矩形区域的概率图 → 检测到文本框。"""
        from src.services.ocr_service import _db_post_process
        pred_map = np.zeros((64, 64), dtype=np.float32)
        # 大面积高概率，让 unclip 后平均分仍高于 _DET_DB_BOX_THRESH (0.5)
        pred_map[:] = 0.8
        boxes = _db_post_process(pred_map, (256, 256))

        # 应该至少检测到一个框
        assert len(boxes) >= 1
        for b in boxes:
            assert "box" in b
            assert "score" in b
            assert len(b["box"]) == 4  # 4 个顶点


# ============================================================
# OcrService 实例化测试（不加载模型）
# ============================================================

class TestOcrServiceInit:

    def test_singleton(self):
        """OcrService 是单例。"""
        from src.services.ocr_service import OcrService
        # 重置单例
        OcrService._instance = None
        s1 = OcrService()
        s2 = OcrService()
        assert s1 is s2

    def test_status_before_load(self):
        """未加载时 status 返回正确信息。"""
        from src.services.ocr_service import OcrService

        # 重置单例
        OcrService._instance = None
        svc = OcrService()
        status = svc.status()
        assert "backend" in status
        assert status["loaded"] is False
        assert status["model_size"] == "medium"

    def test_backend_is_str(self):
        """backend 属性返回字符串。"""
        from src.services.ocr_service import OcrService
        OcrService._instance = None
        svc = OcrService()
        assert isinstance(svc.backend, str)
        assert svc.backend in ("onnxruntime", "openvino")
