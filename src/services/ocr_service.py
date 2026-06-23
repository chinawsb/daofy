r"""
PP-OCRv6 OCR 服务 — 纯 ONNX Runtime 实现，零 PaddlePaddle 依赖。

架构：
  OcrService (singleton)
   ├─ _detect_backend() → 自动选择推理后端
   ├─ _ensure_models()  → 首次自动下载模型 → data/ocr-models/
   ├─ detect(image)     → DBNet 检测 → [{box: [[x1,y1],...], score}]
   ├─ classify(crop)    → [可选] 方向分类 → 0°/180°
   ├─ recognize(crop)   → SVTR 识别 → {text, confidence}
   └─ recognize(image)  → 全流程: detect → classify → recognize → [{text, conf, box}]

模型文件（首次使用时自动下载到 data/ocr-models/）：
  det/model.onnx    — PP-OCRv6_medium 文本检测 (DBNet)
  rec/model.onnx    — PP-OCRv6_medium 文字识别 (SVTR)
  cls/model.onnx    — ch_ppocr_mobile_v2.0 方向分类 [可选]
  ppocr_keys_v1.txt — 字符字典
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ============================================================
# 常量
# ============================================================

# 本服务的数据跟目录（相对于项目根）
_DATA_DIR = Path("data") / "ocr-models"

# 模型下载源（HuggingFace 直链）
_MODEL_URLS: dict[str, str] = {
    "det": "https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_det_onnx/resolve/main/model.onnx",
    "rec": "https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_rec_onnx/resolve/main/model.onnx",
    "cls": "https://huggingface.co/PaddlePaddle/ch_ppocr_mobile_v2.0_cls_onnx/resolve/main/inference.onnx",
}

# HuggingFace 国内镜像（hf-mirror.com，对国内用户更快）
_MODEL_MIRROR_URLS: dict[str, str] = {
    k: v.replace("huggingface.co", "hf-mirror.com")
    for k, v in _MODEL_URLS.items()
}

# ModelScope 国内镜像源（文件名 inference.onnx，而非 HuggingFace 的 model.onnx）
_MODEL_MODELSCOPE_URLS: dict[str, str] = {
    "det": "https://www.modelscope.cn/models/PaddlePaddle/PP-OCRv6_medium_det_onnx/resolve/master/inference.onnx",
    "rec": "https://www.modelscope.cn/models/PaddlePaddle/PP-OCRv6_medium_rec_onnx/resolve/master/inference.onnx",
}

# 备用源（Baidu PaddleX tar 包，国内可直连）
_MODEL_TAR_URLS: dict[str, str] = {
    "det": "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/tmp/PP-OCRv6_medium_det_onnx.tar",
    "rec": "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/tmp/PP-OCRv6_medium_rec_onnx.tar",
}

# 字符字典（GitHub 直链 + 国内代理镜像）
_DICT_URL = (
    "https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/ppocr/utils/ppocr_keys_v1.txt"
)
_DICT_MIRROR_URL = (
    "https://raw.staticdn.net/PaddlePaddle/PaddleOCR/main/ppocr/utils/ppocr_keys_v1.txt"
)

# DBNet 后处理参数
_DET_DB_THRESH = 0.3       # 二值化阈值
_DET_DB_BOX_THRESH = 0.5   # 文本框置信度阈值
_DET_DB_UNCLIP_RATIO = 1.5  # 文本框扩展系数
_DET_MIN_AREA = 3.0         # 最小文本框面积

# 识别参数
_REC_IMAGE_HEIGHT = 48       # 识别模型输入高度
_REC_BATCH_SIZE = 6          # 识别批处理大小

# 分类参数
_CLS_IMAGE_HEIGHT = 48
_CLS_IMAGE_WIDTH = 192
_CLS_THRESH = 0.9


# ============================================================
# 工具函数
# ============================================================

def _project_root() -> Path:
    """返回项目根目录（src/ 的父级）。"""
    return Path(__file__).resolve().parent.parent.parent


def _models_dir() -> Path:
    """返回模型缓存目录，不存在则创建。"""
    d = _project_root() / _DATA_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _model_path(model_type: str) -> Path:
    """返回某个模型文件的路径。"""
    return _models_dir() / model_type / "model.onnx"


def _cls_model_path() -> Path:
    """返回分类模型文件路径。"""
    return _models_dir() / "cls" / "inference.onnx"


def _dict_path() -> Path:
    """返回字符字典文件路径。"""
    return _models_dir() / "ppocr_keys_v1.txt"


def _fastest_url(urls: list[str], timeout: int = 5) -> list[str]:
    """对多个 URL 进行速度测试，按响应时间升序返回（最快在前）。

    通过请求每个 URL 的前 64KB 数据测量响应时间。
    所有 URL 都不可达时返回空列表。

    Args:
        urls: 待测速的 URL 列表
        timeout: 每个 URL 的超时秒数

    Returns:
        按速度排序的 URL 列表（最快在前）
    """
    import time
    import requests

    results: list[tuple[float, str]] = []
    for url in urls:
        try:
            start = time.time()
            r = requests.get(url, stream=True, timeout=timeout)
            r.raise_for_status()
            # 只读取第一个 chunk（~8KB）来测量初始传输速度
            for _ in r.iter_content(chunk_size=8192):
                break
            elapsed = time.time() - start
            results.append((elapsed, url))
        except Exception:
            continue

    results.sort(key=lambda x: x[0])
    return [url for _, url in results]


def _download_file(
    url: str, dest: Path, desc: str = "",
    fallback_urls: list[str] | None = None,
) -> bool:
    """下载文件到指定路径，返回是否成功。

    Args:
        url: 下载地址
        dest: 保存路径
        desc: 描述文字（用于日志）
        fallback_urls: 备用下载地址（主 url 失败时依次尝试）
    """
    import requests
    all_urls = [url] + (fallback_urls or [])
    for i, try_url in enumerate(all_urls):
        try:
            logger.info(f"下载 {desc or '文件'} ({i+1}/{len(all_urls)}): {try_url}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            r = requests.get(try_url, stream=True, timeout=120)
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"下载完成: {dest}")
            return True
        except requests.exceptions.SSLError:
            logger.warning(f"SSL 验证失败: {try_url}")
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                r = requests.get(try_url, stream=True, timeout=120, verify=False)
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.info(f"下载完成（无证书验证）: {dest}")
                return True
            except Exception as e2:
                logger.warning(f"下载失败（无证书验证）{try_url}: {e2}")
                continue
        except Exception as e:
            logger.warning(f"下载失败 {try_url}: {e}")
            continue
    # 所有 URL 都失败
    return False


def _download_tar_and_extract(url: str, dest_dir: Path, desc: str = "") -> bool:
    """下载 tar 包并解压到 dest_dir，返回是否成功。dest_dir 内应包含 .onnx 文件。"""
    import requests
    try:
        logger.info(f"下载 {desc or 'tar包'}: {url}")
        dest_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
            tmp_path = tmp.name
            try:
                r = requests.get(url, stream=True, timeout=300)
                r.raise_for_status()
            except requests.exceptions.SSLError:
                logger.warning(f"SSL 验证失败，尝试不验证证书: {url}")
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                r = requests.get(url, stream=True, timeout=300, verify=False)
                r.raise_for_status()
            for chunk in r.iter_content(chunk_size=8192):
                tmp.write(chunk)
        # 解压
        with tarfile.open(tmp_path, "r") as tar:
            tar.extractall(path=dest_dir)
        # 找到 .onnx 文件并重命名为 model.onnx
        onnx_files = list(dest_dir.rglob("*.onnx"))
        if onnx_files:
            # 如果有多个，取第一个
            src = onnx_files[0]
            dst = dest_dir / "model.onnx"
            if src != dst:
                shutil.move(str(src), str(dst))
            logger.info(f"解压完成: {dest_dir}")
            os.unlink(tmp_path)
            return True
        else:
            logger.warning(f"tar 包中未找到 .onnx 文件: {dest_dir}")
            os.unlink(tmp_path)
            return False
    except Exception as e:
        logger.warning(f"下载/解压失败 {url}: {e}")
        return False


def _load_character_dict_from_yml(yml_path: Path) -> list[str] | None:
    """从 rec 模型的 inference.yml 中解析字符字典。

    PP-OCRv6 的 inference.yml 的 PostProcess.character_dict 字段
    包含了模型训练时使用的完整字符集（18714 类）。

    Args:
        yml_path: inference.yml 文件路径

    Returns:
        字符列表（最后一个是 blank），解析失败返回 None
    """
    if not yml_path.exists():
        return None
    try:
        chars: list[str] = []
        in_dict = False
        with open(yml_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("  character_dict:"):
                    in_dict = True
                    continue
                if in_dict:
                    stripped = line.lstrip()
                    if stripped.startswith("- "):
                        # 提取引号内的字符：- '!' → !
                        val = stripped[2:].strip()
                        if val.startswith("'") and val.endswith("'"):
                            # YAML 单引号字符串内 '' → ' 转义
                            inner = val[1:-1]
                            inner = inner.replace("''", "'")
                            val = inner
                        elif val.startswith('"') and val.endswith('"'):
                            val = val[1:-1]
                        chars.append(val)
                    else:
                        # 遇到非列表行，结束解析
                        break
        if not chars:
            return None
        return chars
    except Exception:
        return None


def _load_character_dict(path: Path) -> list[str]:
    """加载字符字典，返回字符列表（不含 blank）。

    优先从 rec 模型的 inference.yml 加载（包含 PP-OCRv6 完整字符集 18712 字符），
    回退到 ppocr_keys_v1.txt，最后使用最低保底字典。

    blank 由 _ctc_decode 的 blank_indices 参数处理，不加入字符列表。
    """
    # 优先：从 rec 模型的 inference.yml 加载
    rec_yml = _models_dir() / "rec" / "PP-OCRv6_medium_rec_onnx" / "inference.yml"
    if rec_yml.exists():
        chars = _load_character_dict_from_yml(rec_yml)
        if chars and len(chars) > 1000:  # 确保是完整字典
            logger.info(f"从 inference.yml 加载字符字典: {len(chars)} 字符")
            # 下载 ppocr_keys_v1.txt 作为缓存副产物（但不影响识别）
            _download_dict_if_needed()
            return chars

    # 次选：从 ppocr_keys_v1.txt 加载
    if path.exists():
        try:
            chars: list[str] = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        chars.append(line)
            if chars:
                logger.info(f"从 ppocr_keys_v1.txt 加载字符字典: {len(chars)} 字符")
                return chars
        except Exception:
            pass

    # 最低保底字典
    chars = list("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    logger.warning(f"使用最低保底字典: {len(chars)} 字符")
    return chars


def _download_dict_if_needed():
    """下载 ppocr_keys_v1.txt（仅作为缓存，不影响识别流程）。"""
    dict_path = _dict_path()
    if not dict_path.exists():
        _download_file(_DICT_URL, dict_path, desc="字符字典",
                       fallback_urls=[_DICT_MIRROR_URL])


def _detect_cpu_vendor() -> str:
    """检测 CPU 厂商。"""
    import platform
    proc = platform.processor().lower()
    if "intel" in proc or "genuineintel" in proc:
        return "intel"
    if "amd" in proc:
        return "amd"
    # fallback: 检查环境变量或 CPU 特性
    try:
        import cpuinfo  # type: ignore[import-untyped]
        brand = cpuinfo.get_cpu_info().get("brand_raw", "").lower()
        if "intel" in brand:
            return "intel"
        if "amd" in brand:
            return "amd"
    except ImportError:
        pass
    return "unknown"


def _check_openvino_available() -> bool:
    """检查 openvino 包是否可用。"""
    try:
        import openvino  # noqa: F401
        return True
    except ImportError:
        return False


def _select_optimal_backend() -> str:
    """自动选择最优推理后端。"""
    py_version = sys.version_info
    cpu = _detect_cpu_vendor()

    # Python >= 3.14: PaddlePaddle 不可用，走 ONNX Runtime
    if py_version >= (3, 14):
        if cpu == "intel" and _check_openvino_available():
            return "openvino"
        return "onnxruntime"

    # Python 3.9-3.13: 多后端可选
    if cpu == "intel" and _check_openvino_available():
        return "openvino"

    return "onnxruntime"


# ============================================================
# DBNet 后处理
# ============================================================

def _db_post_process(
    pred_map: "np.ndarray",
    original_shape: tuple[int, int],
) -> list[dict[str, Any]]:
    """DBNet 后处理：阈值二值化 → 找轮廓 → 生成文本框。

    Args:
        pred_map: 模型输出的概率图 (H, W)
        original_shape: 原图尺寸 (h, w)

    Returns:
        [{box: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], score: float}, ...]
    """
    import cv2
    import numpy as np
    import pyclipper
    from shapely.geometry import Polygon

    h, w = original_shape
    pred_h, pred_w = pred_map.shape

    # 缩放因子
    scale_h, scale_w = h / pred_h, w / pred_w

    # 1. 阈值二值化
    binary = (pred_map > _DET_DB_THRESH).astype(np.uint8) * 255

    # 2. 找轮廓
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for contour in contours:
        # cv2 轮廓格式 (N, 1, 2) → squeeze to (N, 2)
        contour = contour.squeeze(1) if contour.ndim == 3 else contour
        # 计算轮廓面积
        area = cv2.contourArea(contour)
        if area < _DET_MIN_AREA:
            continue

        # ★ 在原轮廓（未扩展）上计算文本置信度，匹配 PaddleOCR 原版做法
        mask = np.zeros((pred_h, pred_w), dtype=np.uint8)
        cv2.fillPoly(mask, [contour.astype(np.int32)], 1)
        score = float(np.mean(pred_map[mask > 0]))
        if score < _DET_DB_BOX_THRESH:
            continue

        # 扩展轮廓 (unclip) — 仅用于平滑文本框形状，不用于评分
        distance = area * _DET_DB_UNCLIP_RATIO / cv2.arcLength(contour, True)
        offset = pyclipper.PyclipperOffset()
        offset.AddPath(contour, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
        expanded = offset.Execute(distance)
        if not expanded:
            continue

        # 取扩展后的最大轮廓（pyclipper 返回 list of list，转 np.ndarray）
        expanded_np = [np.array(p, dtype=np.int32).reshape(-1, 2) for p in expanded]
        expanded = max(expanded_np, key=cv2.contourArea)

        # 拟合最小外接矩形
        rect = cv2.minAreaRect(expanded)
        box = cv2.boxPoints(rect)  # (4, 2)

        # 缩放到原图坐标
        box[:, 0] = box[:, 0] * scale_w
        box[:, 1] = box[:, 1] * scale_h
        box = np.clip(box, 0, [w, h])

        # 4 点排序：左上、右上、右下、左下
        box = _order_points(box)

        boxes.append({
            "box": box.tolist(),
            "score": round(float(score), 4),
        })

    # 按 (y + x) 排序（从上到下，从左到右）
    boxes.sort(key=lambda b: b["box"][0][1] + b["box"][0][0] * 0.01)

    return boxes


def _order_points(pts: "np.ndarray") -> "np.ndarray":
    """将 4 个点排序为 [左上, 右上, 右下, 左下]。"""
    import numpy as np

    # 按 x+y 排序 → 第一个是左上，最后一个是右下
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)

    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]

    return np.array([tl, tr, br, bl], dtype=np.float32)


def _get_rotate_crop_image(
    img: "np.ndarray", box: list[list[float]]
) -> "np.ndarray":
    """根据文本框裁剪并矫正图像。"""
    import cv2
    import numpy as np

    box = np.array(box, dtype=np.float32)
    # 计算宽高
    w = max(
        np.linalg.norm(box[1] - box[0]),
        np.linalg.norm(box[2] - box[3]),
    )
    h = max(
        np.linalg.norm(box[3] - box[0]),
        np.linalg.norm(box[2] - box[1]),
    )

    dst = np.array(
        [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]],
        dtype=np.float32,
    )
    M = cv2.getPerspectiveTransform(box, dst)
    crop = cv2.warpPerspective(img, M, (int(w), int(h)))
    return crop


# ============================================================
# CTC 解码
# ============================================================

def _ctc_decode(
    preds: "np.ndarray",
    char_list: list[str],
    blank_indices: set[int] | None = None,
) -> tuple[str, float]:
    """CTC 贪婪解码：argmax → 去重 → 去 blank → 转字符。

    模型输出结构说明：
      - 索引 0 始终为 blank（CTC 惯例）
      - 索引 1..len(char_list) 对应 char_list[0..len-1]
      - PP-OCRv6 模型额外将最后一类也作为 blank（双 blank 设计）
        → num_classes = len(char_list) + 2
      - 旧模型仅一个 blank
        → num_classes = len(char_list) + 1

    Args:
        preds: (W, num_classes) 概率分布
        char_list: 字符列表（仅含真实字符，不含 blank）
        blank_indices: 应忽略的索引集合。为 None 时自动检测：
                       - 若 num_classes == len(char_list) + 2 → {0, len(char_list)+1}
                       - 若 num_classes == len(char_list) + 1 → {0}

    Returns:
        (text, avg_confidence)
    """
    import numpy as np

    num_classes = preds.shape[1]
    if blank_indices is None:
        if num_classes == len(char_list) + 2:
            blank_indices = {0, len(char_list) + 1}
        else:
            blank_indices = {0}

    preds_idx = preds.argmax(axis=1)
    preds_prob = preds.max(axis=1)

    result = []
    conf_list = []
    prev = -1
    for i, idx in enumerate(preds_idx):
        if idx in blank_indices:
            prev = -1
            continue
        if idx == prev:
            continue
        char_idx = idx - 1
        if char_idx < 0 or char_idx >= len(char_list):
            prev = -1
            continue
        result.append(char_list[char_idx])
        conf_list.append(float(preds_prob[i]))
        prev = idx

    text = "".join(result)
    avg_conf = float(np.mean(conf_list)) if conf_list else 0.0
    return text, avg_conf


# ============================================================
# 推理预处理
# ============================================================

def _resize_normalize(
    img: "np.ndarray",
    target_h: int,
    target_w: int = -1,
) -> "np.ndarray":
    """resize + normalize 到模型输入格式。

    Args:
        img: (H, W, 3) BGR
        target_h: 目标高度
        target_w: 目标宽度，-1 表示保持宽高比

    Returns:
        (1, 3, target_h, target_w) 或 (1, 3, target_h, W')
    """
    import cv2
    import numpy as np

    h, w = img.shape[:2]
    if target_w == -1:
        # 保持宽高比
        ratio = target_h / h
        new_w = int(w * ratio)
        resized = cv2.resize(img, (new_w, target_h), interpolation=cv2.INTER_LINEAR)
    else:
        resized = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

    # BGR → RGB → CHW → normalize to [0,1]
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    rgb = rgb.astype(np.float32) / 255.0
    # HWC → CHW
    chw = np.transpose(rgb, (2, 0, 1))
    # 加 batch 维度
    return np.expand_dims(chw, axis=0).astype(np.float32)


def _cls_preprocess(img: "np.ndarray") -> "np.ndarray":
    """分类模型预处理。"""
    import cv2
    import numpy as np

    h, w = img.shape[:2]
    ratio = _CLS_IMAGE_HEIGHT / h
    new_w = int(w * ratio)
    resized = cv2.resize(img, (new_w, _CLS_IMAGE_HEIGHT), interpolation=cv2.INTER_LINEAR)

    # 如果宽度不足，右边 padding
    if new_w < _CLS_IMAGE_WIDTH:
        padded = np.zeros((_CLS_IMAGE_HEIGHT, _CLS_IMAGE_WIDTH, 3), dtype=np.uint8)
        padded[:, :new_w, :] = resized
        resized = padded

    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    rgb = rgb.astype(np.float32) / 255.0
    chw = np.transpose(rgb, (2, 0, 1))
    # 均值/方差归一化
    mean = np.array([0.485, 0.456, 0.406]).reshape(3, 1, 1)
    std = np.array([0.229, 0.224, 0.225]).reshape(3, 1, 1)
    chw = (chw - mean) / std
    return np.expand_dims(chw, axis=0).astype(np.float32)


# ============================================================
# OcrService
# ============================================================

class OcrService:
    """PP-OCRv6 OCR 服务（单例，惰性加载模型）。

    用法：
        svc = OcrService()
        results = svc.recognize("screenshot.png")
        # → [{"text": "你好", "confidence": 0.97, "box": [[x1,y1],...]}, ...]
    """

    _instance: Optional["OcrService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, model_size: str = "medium"):
        """初始化 OCR 服务。

        Args:
            model_size: 模型大小，tiny/small/medium，默认 medium
        """
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True

        self._backend: str = _select_optimal_backend()
        self._model_size = model_size
        self._character_list: list[str] = []
        self._loaded = False
        self._load_error: Optional[str] = None

        # ONNX Runtime sessions（惰性加载）
        self._det_session: Any = None
        self._rec_session: Any = None
        self._cls_session: Any = None

        logger.info(
            f"OcrService 初始化: backend={self._backend}, model_size={model_size}"
        )

    # ── 属性 ──

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    # ── 公共接口 ──

    def recognize(self, image_path: str) -> list[dict[str, Any]]:
        """完整 OCR 管线：检测 → 分类 → 识别。

        Args:
            image_path: 图片文件路径

        Returns:
            [{text, confidence, box}, ...]
        """
        import cv2
        import numpy as np

        self._ensure_models()

        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"无法读取图片: {image_path}")

        # 1. 检测文本框
        det_results = self.detect(image_path)

        if not det_results:
            return []

        # 2. 对每个文本框裁剪 + 分类 + 识别
        results = []
        rec_crops: list[tuple[int, np.ndarray]] = []  # (index, crop)

        for i, det in enumerate(det_results):
            box = det["box"]
            crop = _get_rotate_crop_image(img, box)

            # 可选方向分类
            if self._cls_session is not None:
                cls_result = self._classify(crop)
                if cls_result["label"] == 1 and cls_result["confidence"] > _CLS_THRESH:
                    # 180° 旋转
                    crop = cv2.rotate(crop, cv2.ROTATE_180)

            rec_crops.append((i, crop))

        # 批量识别
        rec_texts = self._recognize_batch(rec_crops)

        for i, det in enumerate(det_results):
            rec = rec_texts.get(i, {})
            results.append({
                "text": rec.get("text", ""),
                "confidence": rec.get("confidence", 0.0),
                "box": det["box"],
                "det_score": det["score"],
            })

        return results

    def detect(self, image_path: str) -> list[dict[str, Any]]:
        """仅文本检测。

        Args:
            image_path: 图片文件路径

        Returns:
            [{box: [[x1,y1],...], score}, ...]
        """
        import cv2
        import numpy as np

        self._ensure_models()
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"无法读取图片: {image_path}")

        orig_h, orig_w = img.shape[:2]

        # 预处理：缩放到 32 倍数 + ImageNet 归一化
        input_tensor = self._det_preprocess(img)

        # 推理
        input_name = self._det_session.get_inputs()[0].name
        output_name = self._det_session.get_outputs()[0].name
        preds = self._det_session.run([output_name], {input_name: input_tensor})
        pred_map = preds[0].squeeze()  # (det_h, det_w)

        # 后处理
        boxes = _db_post_process(pred_map, (orig_h, orig_w))
        return boxes

    def status(self) -> dict[str, Any]:
        """返回服务状态。"""
        return {
            "backend": self._backend,
            "model_size": self._model_size,
            "loaded": self._loaded,
            "load_error": self._load_error,
            "models_available": {
                "det": _model_path("det").exists(),
                "rec": _model_path("rec").exists(),
                "cls": _cls_model_path().exists(),
            },
        }

    # ── 内部方法 ──

    def _det_preprocess(self, img: "np.ndarray") -> "np.ndarray":
        """检测模型预处理。限制最长边 ≤ 2560，短边 ≥ 640，再对齐到 32 倍数。"""
        import cv2
        import numpy as np

        h, w = img.shape[:2]
        # 限制尺寸
        max_long_edge = 2560
        max_short_edge = 640
        if max(h, w) > max_long_edge:
            ratio = max_long_edge / max(h, w)
            h, w = int(h * ratio), int(w * ratio)
        if min(h, w) > max_short_edge:
            ratio = max_short_edge / min(h, w)
            h, w = int(h * ratio), int(w * ratio)
        # 对齐到 32 倍数（DBNet 要求）
        new_h = int(np.ceil(h / 32) * 32)
        new_w = int(np.ceil(w / 32) * 32)
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        rgb = rgb.astype(np.float32) / 255.0
        # ImageNet 均值/方差归一化
        mean = np.array([0.485, 0.456, 0.406]).reshape(3, 1, 1)
        std = np.array([0.229, 0.224, 0.225]).reshape(3, 1, 1)
        chw = np.transpose(rgb, (2, 0, 1))
        chw = (chw - mean) / std
        return np.expand_dims(chw, axis=0).astype(np.float32)

    def _classify(self, crop: "np.ndarray") -> dict[str, Any]:
        """方向分类：0=正, 1=180° 旋转。"""
        if self._cls_session is None:
            return {"label": 0, "confidence": 0.0}

        input_tensor = _cls_preprocess(crop)
        input_name = self._cls_session.get_inputs()[0].name
        output_name = self._cls_session.get_outputs()[0].name
        preds = self._cls_session.run([output_name], {input_name: input_tensor})
        probs = preds[0].squeeze()  # (2,)

        import numpy as np
        label = int(np.argmax(probs))
        conf = float(probs[label])
        return {"label": label, "confidence": conf}

    def _recognize_batch(
        self, crops: list[tuple[int, "np.ndarray"]]
    ) -> dict[int, dict[str, Any]]:
        """批量识别文字。"""
        import cv2
        import numpy as np

        if not crops:
            return {}

        results: dict[int, dict[str, Any]] = {}

        # 分批处理
        for batch_start in range(0, len(crops), _REC_BATCH_SIZE):
            batch = crops[batch_start: batch_start + _REC_BATCH_SIZE]
            batch_tensors = []
            batch_indices = []

            for idx, crop in batch:
                # 识别预处理：resize 到高度 48，宽度等比例
                h, w = crop.shape[:2]
                ratio = _REC_IMAGE_HEIGHT / h
                new_w = int(w * ratio)
                resized = cv2.resize(
                    crop, (new_w, _REC_IMAGE_HEIGHT), interpolation=cv2.INTER_LINEAR
                )
                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
                rgb = rgb.astype(np.float32) / 255.0
                chw = np.transpose(rgb, (2, 0, 1))
                batch_tensors.append(chw)
                batch_indices.append(idx)

            # 找最宽作为 batch 宽度
            widths = [t.shape[2] for t in batch_tensors]
            max_w = max(widths)

            # padding 到相同宽度
            padded = []
            for t in batch_tensors:
                if t.shape[2] < max_w:
                    pad = np.zeros((3, _REC_IMAGE_HEIGHT, max_w - t.shape[2]),
                                   dtype=np.float32)
                    t = np.concatenate([t, pad], axis=2)
                padded.append(t)

            batch_input = np.stack(padded, axis=0).astype(np.float32)

            # 推理
            input_name = self._rec_session.get_inputs()[0].name
            output_name = self._rec_session.get_outputs()[0].name
            preds = self._rec_session.run(
                [output_name], {input_name: batch_input}
            )
            # preds[0] shape: (batch, W, num_classes)

            for j, out in enumerate(preds[0]):
                text, conf = _ctc_decode(out, self._character_list)
                orig_idx = batch_indices[j]
                results[orig_idx] = {"text": text, "confidence": round(conf, 4)}

        return results

    def _ensure_models(self):
        """确保模型已下载并加载。惰性加载，仅首次调用时执行。"""
        if self._loaded:
            return
        if self._load_error:
            raise RuntimeError(f"模型加载失败: {self._load_error}")

        try:
            self._download_models_if_needed()
            self._load_sessions()
            self._loaded = True
            logger.info("OCR 模型加载完成")
        except Exception as e:
            self._load_error = str(e)
            logger.error(f"OCR 模型加载失败: {e}", exc_info=True)
            raise

    def _download_models_if_needed(self):
        """下载缺失的模型文件。"""
        import cv2  # noqa: F401  # 确保 opencv 可用

        models_to_check = [
            ("det", _model_path("det")),
            ("rec", _model_path("rec")),
        ]

        for model_type, path in models_to_check:
            if path.exists():
                logger.debug(f"模型已存在: {path}")
                continue

            logger.info(f"模型 {model_type} 不存在，开始下载...")

            # 收集所有单文件下载源，测速选最快的优先
            single_urls = [
                _MODEL_URLS.get(model_type),
                _MODEL_MIRROR_URLS.get(model_type),
                _MODEL_MODELSCOPE_URLS.get(model_type),
            ]
            single_urls = [u for u in single_urls if u]

            if len(single_urls) > 1:
                logger.info(f"{model_type}: 测速 {len(single_urls)} 个镜像源...")
                sorted_urls = _fastest_url(single_urls)
                if sorted_urls:
                    url = sorted_urls[0]
                    fallback = sorted_urls[1:]
                else:
                    url = single_urls[0]
                    fallback = single_urls[1:]
            elif single_urls:
                url = single_urls[0]
                fallback = []
            else:
                url = None
                fallback = []

            if url and _download_file(url, path, desc=f"PP-OCRv6_{model_type}", fallback_urls=fallback):
                continue

            # 备用：从 Baidu PaddleX 下载 tar 包
            tar_url = _MODEL_TAR_URLS.get(model_type)
            if tar_url:
                dest_dir = _models_dir() / model_type
                if _download_tar_and_extract(
                    tar_url, dest_dir, desc=f"PP-OCRv6_{model_type}_tar"
                ):
                    continue

            raise RuntimeError(
                f"无法下载模型 {model_type}。请手动下载到 {path}\n"
                f"  HuggingFace: {_MODEL_URLS.get(model_type, '')}\n"
                f"  PaddleX: {_MODEL_TAR_URLS.get(model_type, '')}"
            )

        # 下载分类模型（可选，仅 HuggingFace/Mirror，ModelScope 无此模型）
        cls_path = _cls_model_path()
        if not cls_path.exists():
            cls_url = _MODEL_URLS.get("cls")
            if cls_url:
                cls_mirror = _MODEL_MIRROR_URLS.get("cls")
                _download_file(cls_url, cls_path, desc="方向分类模型",
                               fallback_urls=[cls_mirror] if cls_mirror else None)
            else:
                logger.info("方向分类模型无可用下载源，跳过")

        # 加载字符字典（优先从 inference.yml，再回退 ppocr_keys_v1.txt）
        self._character_list = _load_character_dict(_dict_path())
        logger.info(f"字符字典加载完成: {len(self._character_list)} 字符")

    def _load_sessions(self):
        """加载 ONNX Runtime 推理会话。"""
        import onnxruntime as ort

        det_path = str(_model_path("det"))
        rec_path = str(_model_path("rec"))
        cls_path = _cls_model_path()

        providers = ["CPUExecutionProvider"]
        if self._backend == "openvino":
            try:
                providers = ["OpenVINOExecutionProvider", "CPUExecutionProvider"]
            except Exception:
                providers = ["CPUExecutionProvider"]

        self._det_session = ort.InferenceSession(det_path, providers=providers)
        self._rec_session = ort.InferenceSession(rec_path, providers=providers)

        if cls_path.exists():
            try:
                self._cls_session = ort.InferenceSession(cls_path, providers=providers)
                logger.info("方向分类模型已加载")
            except Exception as e:
                logger.warning(f"方向分类模型加载失败: {e}")
                self._cls_session = None

        # 打印输入输出信息
        for name, sess in [
            ("det", self._det_session),
            ("rec", self._rec_session),
        ]:
            for inp in sess.get_inputs():
                logger.debug(f"{name} 输入: {inp.name} shape={inp.shape} type={inp.type}")
            for out in sess.get_outputs():
                logger.debug(f"{name} 输出: {out.name} shape={out.shape} type={out.type}")


# ── 工厂函数 ──

def get_ocr_service(model_size: str = "medium") -> OcrService:
    """获取 OcrService 单例。"""
    return OcrService(model_size=model_size)
