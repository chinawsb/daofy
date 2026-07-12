"""
synthetic_data_generator — YOLO 训练数据自动生成

两种模式:
  1. 从 Delphi 应用自动采集（capture + dumpstate）— 需要已链接 DaofyAutomation 的 exe
  2. 程序化合成（OpenCV 绘制模拟 UI）— 无需 Delphi 环境，用于基线验证

输出格式:
  images/              ← 截图 (PNG)
  labels/              ← YOLO 格式标签 (TXT)
  dataset.yaml         ← Ultralytics 训练配置文件

YOLO 标签格式（每行一个元素）:
  <class_id> <x_center> <y_center> <width> <height>
  坐标归一化到 [0, 1]（相对于图片宽高）

用法（Delphi 模式）:
  python -c "
  from src.detection.synthetic_data_generator import DelphiDataCollector
  collector = DelphiDataCollector(
      app_path='C:/App/MyApp.exe',
      output_dir='./yolo_dataset',
      forms=['TMainForm', 'TLoginForm', 'TSettingsForm'],
  )
  collector.collect_all()
  "

用法（合成模式）:
  python -c "
  from src.detection.synthetic_data_generator import SyntheticDataGenerator
  gen = SyntheticDataGenerator(output_dir='./yolo_dataset')
  gen.generate(num_samples=100)
  "
"""

from __future__ import annotations

import json
import logging
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# 从 dfm_generator 导入 class_id 映射（唯一数据源）
from .dfm_generator import _CLASS_MAP as _DFM_CLASS_MAP

# Delphi 控件类型 → YOLO class_id 映射（自动从 dfm_generator 反转）
_DELPHI_CLASS_MAP: dict[str, int] = {
    cls_name: cid - 1 for cid, (cls_name, _, _) in _DFM_CLASS_MAP.items()
}

# 反向映射
_CLASS_ID_TO_NAME = {v: k for k, v in _DELPHI_CLASS_MAP.items()}

# 合成模式下各类控件的视觉参数
_SYNTHETIC_CONTROLS: dict[str, dict] = {
    "TButton": {
        "min_size": (60, 22), "max_size": (160, 36),
        "color_range": ((180, 180, 180), (220, 220, 220)),
        "border": True,
    },
    "TEdit": {
        "min_size": (100, 20), "max_size": (300, 28),
        "color_range": ((250, 250, 250), (255, 255, 255)),
        "border": True,
    },
    "TLabel": {
        "min_size": (30, 14), "max_size": (200, 20),
        "color_range": ((235, 235, 235), (245, 245, 245)),
        "border": False,
    },
    "TCheckBox": {
        "min_size": (15, 15), "max_size": (22, 22),
        "color_range": ((230, 230, 230), (255, 255, 255)),
        "border": True,
    },
    "TPanel": {
        "min_size": (200, 100), "max_size": (600, 400),
        "color_range": ((230, 230, 230), (245, 245, 245)),
        "border": True,
    },
    "TGroupBox": {
        "min_size": (200, 80), "max_size": (500, 300),
        "color_range": ((235, 235, 235), (245, 245, 245)),
        "border": True,
    },
}

# 控件生成权重（控制分布）
_SYNTHETIC_WEIGHTS: dict[str, float] = {
    "TButton": 0.20,
    "TEdit": 0.18,
    "TLabel": 0.20,
    "TCheckBox": 0.08,
    "TPanel": 0.04,
    "TGroupBox": 0.03,
}


# ============================================================
# Delphi 模式 — 从运行的 Delphi 应用自动采集
# ============================================================

class DelphiDataCollector:
    """通过 automate_delphi 采集 Delphi 应用的训练数据。

    前置条件:
      - Delphi exe 已链接 DaofyAutomation 单元
      - Python 环境可运行 automate_delphi（gui 模式）
    """

    def __init__(
        self,
        app_path: str,
        output_dir: str = "./yolo_dataset",
        forms: Optional[List[str]] = None,
    ):
        """
        Args:
            app_path: Delphi exe 路径。
            output_dir: 输出目录。
            forms: 要采集的窗体类名列表，None 表示采集所有可用窗体。
        """
        self.app_path = app_path
        self.output_dir = Path(output_dir)
        self.forms = forms
        self.image_dir = self.output_dir / "images"
        self.label_dir = self.output_dir / "labels"

    def collect_all(self) -> Dict[str, int]:
        """执行完整采集流程。

        Returns:
            {"total_images": N, "total_labels": M, ...}
        """
        try:
            from src.services.automation_service import execute_automation
        except ImportError:
            raise ImportError(
                "automate_delphi 工具不可用。请确保在 Daofy MCP Server 环境下运行。"
            )

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(exist_ok=True)
        self.label_dir.mkdir(exist_ok=True)

        forms_to_capture = self.forms or ["auto"]
        collected = {"total_images": 0, "total_labels": 0}

        for form_name in forms_to_capture:
            logger.info("采集窗体: %s", form_name)

            # 1. 切换到目标窗体
            if form_name != "auto":
                nav_script = [{"cmd": "goto", "target": form_name}]
                execute_automation(
                    action="gui",
                    app_path=self.app_path,
                    script=nav_script,
                )

            # 2. capture + dumpstate 同步采集
            script = [
                {"cmd": "capture", "reqId": "img"},
                {"cmd": "dumpstate", "reqId": "labels"},
            ]
            result = execute_automation(
                action="gui",
                app_path=self.app_path,
                script=script,
                snapshots_dir=str(self.image_dir),
            )

            # 3. 解析结果
            self._process_result(result, form_name, collected)

        # 4. 生成 dataset.yaml
        self._write_dataset_yaml()

        logger.info(
            "采集完成: %d 张图片, %d 个标注",
            collected["total_images"], collected["total_labels"],
        )
        return collected

    def _process_result(
        self, result: dict, form_name: str, collected: Dict[str, int],
    ) -> None:
        """处理一次 capture + dumpstate 的结果。"""
        steps = result.get("steps", [])
        capture_path = ""
        dumpstate_data = None

        for step in steps:
            if step.get("cmd") == "capture":
                capture_path = (step.get("response") or {}).get("path", "")
            elif step.get("cmd") == "dumpstate":
                dumpstate_data = step.get("response") or {}

        if not capture_path:
            logger.warning("采集跳过: capture 失败 (%s)", form_name)
            return

        labels = self._dumpstate_to_yolo(dumpstate_data)
        if not labels:
            logger.warning("采集跳过: dumpstate 未检测到控件 (%s)", form_name)
            return

        # YOLO 标签文件名与图片名一致
        img_name = Path(capture_path).name
        label_name = Path(img_name).with_suffix(".txt")
        label_path = self.label_dir / label_name

        with open(label_path, "w", encoding="utf-8") as f:
            for line in labels:
                f.write(line + "\n")

        # 可选：将图片复制到统一 image 目录
        # 如果 capture 已经保存到 image_dir 则跳过
        if Path(capture_path).parent != self.image_dir:
            dest = self.image_dir / img_name
            if not dest.exists():
                import shutil
                shutil.copy2(capture_path, dest)

        collected["total_images"] += 1
        collected["total_labels"] += len(labels)

    def _dumpstate_to_yolo(self, data: dict) -> List[str]:
        """将 dumpstate JSON 转换为 YOLO 格式标签行。

        dumpstate 返回格式:
          {
            "form": {"class": "TMainForm", "Left": 0, "Top": 0,
                     "Width": 800, "Height": 600},
            "controls": [
              {"name": "Button1", "class": "TButton",
               "Left": 10, "Top": 20, "Width": 100, "Height": 30},
              ...
            ]
          }
        """
        if not data:
            return []

        # 获取窗体尺寸（用于坐标归一化）
        form = data.get("form", {})
        fw = form.get("Width", 640) or 640
        fh = form.get("Height", 480) or 480
        if fw <= 0 or fh <= 0:
            fw, fh = 640, 480

        controls = data.get("controls", [])
        if not controls:
            # 也可能在 form.controls 里
            controls = form.get("controls", [])

        labels: List[str] = []
        for ctrl in controls:
            cls_name = ctrl.get("class", "")
            class_id = _DELPHI_CLASS_MAP.get(cls_name)
            if class_id is None:
                continue  # 跳过未映射的控件类型

            left = ctrl.get("Left", 0)
            top = ctrl.get("Top", 0)
            w = ctrl.get("Width", 0)
            h = ctrl.get("Height", 0)

            if w <= 2 or h <= 2:
                continue  # 过小的控件跳过

            # YOLO 格式: <class_id> <x_center> <y_center> <width> <height>
            # 坐标归一化到 [0, 1]
            x_center = (left + w / 2) / fw
            y_center = (top + h / 2) / fh
            norm_w = w / fw
            norm_h = h / fh

            labels.append(f"{class_id} {x_center:.6f} {y_center:.6f} {norm_w:.6f} {norm_h:.6f}")

        return labels

    def _write_dataset_yaml(self) -> None:
        """创建 Ultralytics dataset.yaml 文件。"""
        names = {v: k for k, v in _DELPHI_CLASS_MAP.items()}
        nc = len(names)

        yaml_path = self.output_dir / "dataset.yaml"
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(f"# YOLO 数据集配置 — 自动生成\n")
            f.write(f"path: {self.output_dir.resolve().as_posix()}\n")
            f.write(f"train: images\n")
            f.write(f"val: images\n\n")
            f.write(f"nc: {nc}\n")
            f.write(f"names:\n")
            for cid in sorted(names.keys()):
                f.write(f"  {cid}: {names[cid]}\n")

        logger.info("dataset.yaml 已生成: %s", yaml_path)


# ============================================================
# 合成模式 — 用 OpenCV 生成模拟 UI 截图（无需 Delphi 环境）
# ============================================================

class SyntheticDataGenerator:
    """用 OpenCV 合成模拟 Delphi UI 截图 + YOLO 标签。

    用于:
      - 训练管线验证（不依赖 Delphi 环境即可测试训练流程）
      - 数据增强的基线数据集
      - 快速迭代模型结构
    """

    def __init__(
        self,
        output_dir: str = "./yolo_dataset",
        canvas_size: Tuple[int, int] = (640, 480),
        class_map: Optional[Dict[str, int]] = None,
    ):
        """
        Args:
            output_dir: 输出目录。
            canvas_size: 合成画布尺寸 (w, h)。
            class_map: 控件名 → class_id 映射，默认使用 _DELPHI_CLASS_MAP。
        """
        self.output_dir = Path(output_dir)
        self.image_dir = self.output_dir / "images"
        self.label_dir = self.output_dir / "labels"
        self.canvas_w, self.canvas_h = canvas_size
        self.class_map = class_map or _DELPHI_CLASS_MAP

    def generate(self, num_samples: int = 100) -> Dict[str, int]:
        """生成合成数据集。

        Args:
            num_samples: 生成的截图数量。

        Returns:
            {"total_images": N, "total_labels": M}
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(exist_ok=True)
        self.label_dir.mkdir(exist_ok=True)

        total_labels = 0
        control_names = list(self.class_map.keys())
        weights = [_SYNTHETIC_WEIGHTS.get(n, 0.05) for n in control_names]
        # 归一化权重
        total_w = sum(weights)
        weights = [w / total_w for w in weights]

        for i in range(num_samples):
            img = np.ones((self.canvas_h, self.canvas_w, 3), dtype=np.uint8) * 240

            # 随机确定本图要包含的控件数
            num_controls = random.randint(3, min(12, len(control_names)))

            # 选择控件类型（加权随机）
            chosen = random.choices(control_names, weights=weights, k=num_controls)

            labels: List[str] = []
            occupied: List[Tuple[int, int, int, int]] = []

            # 先放置容器（Panel/GroupBox — 面积大的优先）
            containers = [n for n in chosen if n in ("TPanel", "TGroupBox")]
            others = [n for n in chosen if n not in ("TPanel", "TGroupBox")]

            # 放置非容器控件
            for ctrl_name in others:
                rect = self._place_element(ctrl_name, occupied)
                if rect is None:
                    continue
                x, y, w, h = rect
                occupied.append((x - 5, y - 5, w + 10, h + 10))  # 加些边距避免重叠

                self._draw_element(img, ctrl_name, x, y, w, h)

                class_id = self.class_map.get(ctrl_name)
                if class_id is not None:
                    x_center = (x + w / 2) / self.canvas_w
                    y_center = (y + h / 2) / self.canvas_h
                    labels.append(
                        f"{class_id} {x_center:.6f} {y_center:.6f} "
                        f"{w / self.canvas_w:.6f} {h / self.canvas_h:.6f}"
                    )

            # 放置容器（作为背景，先画再画上面的子元素）
            # 简化版：容器只是作为大框
            for ctrl_name in containers:
                rect = self._place_element(ctrl_name, occupied)
                if rect is None:
                    continue
                x, y, w, h = rect
                self._draw_element(img, ctrl_name, x, y, w, h)
                occupied.append((x, y, w, h))

                class_id = self.class_map.get(ctrl_name)
                if class_id is not None:
                    x_center = (x + w / 2) / self.canvas_w
                    y_center = (y + h / 2) / self.canvas_h
                    labels.append(
                        f"{class_id} {x_center:.6f} {y_center:.6f} "
                        f"{w / self.canvas_w:.6f} {h / self.canvas_h:.6f}"
                    )

            # 保存图片
            img_name = f"synth_{i:05d}.png"
            cv2.imwrite(str(self.image_dir / img_name), img)

            # 保存标签
            if labels:
                label_path = self.label_dir / f"synth_{i:05d}.txt"
                with open(label_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(labels) + "\n")
                total_labels += len(labels)

        # 生成 dataset.yaml
        self._write_dataset_yaml()

        logger.info(
            "合成数据生成完成: %d 图片, %d 标注", num_samples, total_labels,
        )
        return {"total_images": num_samples, "total_labels": total_labels}

    def _place_element(
        self, ctrl_name: str,
        occupied: List[Tuple[int, int, int, int]],
        max_attempts: int = 50,
    ) -> Optional[Tuple[int, int, int, int]]:
        """在画布上找一个不重叠的位置放置控件。"""
        params = _SYNTHETIC_CONTROLS.get(ctrl_name, _SYNTHETIC_CONTROLS["TLabel"])

        for _ in range(max_attempts):
            w = random.randint(params["min_size"][0], params["max_size"][0])
            h = random.randint(params["min_size"][1], params["max_size"][1])

            x = random.randint(10, max(self.canvas_w - w - 10, 10))
            y = random.randint(10, max(self.canvas_h - h - 10, 10))

            # 检查是否与已放置的控件重叠
            new_rect = (x, y, w, h)
            if not self._overlaps(new_rect, occupied, min_gap=5):
                return new_rect

        return None

    @staticmethod
    def _overlaps(
        rect: Tuple[int, int, int, int],
        others: List[Tuple[int, int, int, int]],
        min_gap: int = 5,
    ) -> bool:
        """检查矩形是否与已有矩形重叠（含最小间距）。"""
        rx, ry, rw, rh = rect
        for ox, oy, ow, oh in others:
            if (
                rx < ox + ow + min_gap
                and rx + rw + min_gap > ox
                and ry < oy + oh + min_gap
                and ry + rh + min_gap > oy
            ):
                return True
        return False

    def _draw_element(
        self, img: np.ndarray,
        ctrl_name: str,
        x: int, y: int, w: int, h: int,
    ) -> None:
        """在画布上绘制一个控件的外观。"""
        params = _SYNTHETIC_CONTROLS.get(ctrl_name, _SYNTHETIC_CONTROLS["TLabel"])
        low_bgr, high_bgr = params["color_range"]
        color = (
            random.randint(low_bgr[0], high_bgr[0]),  # B
            random.randint(low_bgr[1], high_bgr[1]),  # G
            random.randint(low_bgr[2], high_bgr[2]),  # R
        )

        # 填充
        cv2.rectangle(img, (x, y), (x + w, y + h), color, -1)

        # 边框
        if params["border"]:
            cv2.rectangle(img, (x, y), (x + w, y + h), (100, 100, 100), 1)

        # 按钮特有效果：浅色背景 + 略深的渐变
        if ctrl_name == "TButton":
            for i in range(h // 2):
                alpha = i / (h // 2)
                darker = tuple(int(c * (1 - alpha * 0.15)) for c in color)
                cv2.line(img, (x, y + i), (x + w, y + i), darker, 1)

        # 编辑框特有效果：白色背景 + 下沉边框
        elif ctrl_name == "TEdit":
            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 255, 255), -1)
            cv2.rectangle(img, (x, y), (x + w, y + h), (180, 180, 180), 1)

    def _write_dataset_yaml(self) -> None:
        """创建 Ultralytics dataset.yaml 文件。"""
        names = {v: k for k, v in self.class_map.items()}
        nc = len(names)

        yaml_path = self.output_dir / "dataset.yaml"
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write("# YOLO 数据集配置 — 合成数据\n")
            f.write(f"path: {self.output_dir.resolve().as_posix()}\n")
            f.write("train: images\n")
            f.write("val: images\n\n")
            f.write(f"nc: {nc}\n")
            f.write("names:\n")
            for cid in sorted(names.keys()):
                f.write(f"  {cid}: {names[cid]}\n")

        logger.info("dataset.yaml 已生成: %s", yaml_path)
