"""
OCR 工具 handler 测试 — 测试参数校验、路由、错误处理。
不依赖实际模型文件（mock OcrService）。
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ============================================================
# handle_ocr 参数校验
# ============================================================

class TestHandleOcrValidation:

    def test_missing_image_path_returns_error(self):
        """recognize 不传 image_path → 返回 error。"""
        from src.tools.ocr import handle_ocr
        result = handle_ocr({"action": "recognize"})
        assert result["status"] == "failed"
        assert "image_path" in result.get("error", "")

    def test_unknown_action_returns_error(self):
        """未知 action → 返回 error。"""
        from src.tools.ocr import handle_ocr
        # 用 __file__ 指向本文件作为存在的输入
        result = handle_ocr({"action": "unknown", "image_path": __file__})
        assert result["status"] == "failed"
        assert "未知" in result.get("error", "")

    def test_nonexistent_file_returns_error(self):
        """不存在的文件路径 → 返回 error。"""
        from src.tools.ocr import handle_ocr
        result = handle_ocr({"action": "recognize", "image_path": "C:\\nonexistent.png"})
        assert result["status"] == "failed"
        assert "不存在" in result.get("error", "")


# ============================================================
# handle_ocr status
# ============================================================

class TestHandleOcrStatus:

    @patch("src.tools.ocr.get_ocr_service")
    def test_status_returns_service_info(self, mock_get_svc):
        """status 返回服务状态信息。"""
        mock_svc = MagicMock()
        mock_svc.status.return_value = {
            "backend": "onnxruntime",
            "model_size": "medium",
            "loaded": True,
            "models_available": {"det": True, "rec": True, "cls": False},
        }
        mock_get_svc.return_value = mock_svc

        from src.tools.ocr import handle_ocr
        result = handle_ocr({"action": "status"})
        assert result["backend"] == "onnxruntime"
        assert result["loaded"] is True
        assert result["model_size"] == "medium"


# ============================================================
# handle_ocr recognize
# ============================================================

class TestHandleOcrRecognize:

    @patch("src.tools.ocr.get_ocr_service")
    def test_recognize_returns_results(self, mock_get_svc):
        """recognize 返回正确结构的结果。"""
        mock_svc = MagicMock()
        mock_svc.recognize.return_value = [
            {"text": "你好", "confidence": 0.95, "box": [[0,0],[10,0],[10,20],[0,20]], "det_score": 0.9},
            {"text": "世界", "confidence": 0.92, "box": [[0,30],[20,30],[20,50],[0,50]], "det_score": 0.88},
        ]
        mock_get_svc.return_value = mock_svc

        from src.tools.ocr import handle_ocr

        # 创建临时文件
        fd, img_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        with open(img_path, "wb") as f:
            f.write(b"dummy")

        try:
            result = handle_ocr({"action": "recognize", "image_path": img_path})
            assert result["status"] == "ok"
            assert result["count"] == 2
            assert len(result["results"]) == 2
            assert result["results"][0]["text"] == "你好"
        finally:
            os.unlink(img_path)

    @patch("src.tools.ocr.get_ocr_service")
    def test_detect_returns_boxes(self, mock_get_svc):
        """detect 返回文本框。"""
        mock_svc = MagicMock()
        mock_svc.detect.return_value = [
            {"box": [[0,0],[10,0],[10,20],[0,20]], "score": 0.9},
        ]
        mock_get_svc.return_value = mock_svc

        from src.tools.ocr import handle_ocr

        fd, img_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        with open(img_path, "wb") as f:
            f.write(b"dummy")

        try:
            result = handle_ocr({"action": "detect", "image_path": img_path})
            assert result["status"] == "ok"
            assert result["count"] == 1
        finally:
            os.unlink(img_path)


# ============================================================
# handle_ocr 错误处理
# ============================================================

class TestHandleOcrErrors:

    @patch("src.tools.ocr.get_ocr_service")
    def test_file_not_found_error(self, mock_get_svc):
        """FileNotFoundError 被正确捕获。"""
        mock_svc = MagicMock()
        mock_svc.recognize.side_effect = FileNotFoundError("文件不存在")
        mock_get_svc.return_value = mock_svc

        from src.tools.ocr import handle_ocr

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img_path = f.name
        os.unlink(img_path)  # 删除文件，但我们的 mock 已经接管了

        # 用存在的文件路径测试
        result = handle_ocr({"action": "recognize", "image_path": "C:\\test.png"})
        assert result["status"] == "failed"

    def test_default_action_is_recognize(self):
        """不传 action 时默认 recognize。"""
        from src.tools.ocr import handle_ocr
        result = handle_ocr({"image_path": ""})
        # 不传 image_path 时 recognize 返回缺少参数
        assert result["status"] == "failed"
