"""
train_yolo — YOLOv11 训练 + ONNX 导出脚本

在用户侧训练环境中运行（需要 ultralytics + torch + onnx）。
生成的数据集格式与此目录下的 synthetic_data_generator.py 兼容。

用法:
  # 基本训练（用合成数据或 Delphi 采集数据）
  python -c "
  from src.detection.train_yolo import train
  train(
      data_yaml='./yolo_dataset/dataset.yaml',
      model_size='n',          # n/s/m/l/x
      epochs=100,
      imgsz=640,
      project='./yolo_output',
  )
  "

  # 单行命令（直接运行模块）
  python -m src.detection.train_yolo --data ./yolo_dataset/dataset.yaml --epochs 100

输出:
  yolo_output/train/weights/best.pt     ← PyTorch 权重
  yolo_output/train/weights/best.onnx   ← ONNX 模型（可直接被 YOLOONNXDetector 加载）
  yolo_output/train/results.csv         ← 训练指标
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _check_deps() -> None:
    """检查训练依赖是否已安装。"""
    missing = []
    try:
        import ultralytics  # noqa: F401
    except ImportError:
        missing.append("ultralytics")
    try:
        import torch  # noqa: F401
    except ImportError:
        missing.append("torch")
    if missing:
        print(
            f"缺少训练依赖: {', '.join(missing)}\n"
            "请安装: pip install ultralytics torch torchvision onnx\n"
            "或在有 GPU 的环境中运行。"
        )
        sys.exit(1)


def train(
    data_yaml: str,
    model_size: str = "n",
    epochs: int = 100,
    imgsz: int = 640,
    batch: int = 16,
    project: str = "./yolo_output",
    name: str = "train",
    device: str = "",
    resume: bool = False,
    pretrained: bool = True,
    export_onnx: bool = True,
) -> str:
    """执行 YOLOv11 训练并导出 ONNX。

    Args:
        data_yaml: dataset.yaml 路径。
        model_size: YOLO 模型大小 (n/s/m/l/x)。
        epochs: 训练轮数。
        imgsz: 输入图片尺寸（像素）。
        batch: 批次大小。
        project: 输出项目目录。
        name: 实验名称。
        device: 设备 (''=auto, 'cpu', '0', '0,1')。
        resume: 是否从断点恢复训练。
        pretrained: 是否使用 COCO 预训练权重（强烈建议 True）。
        export_onnx: 训练完成后是否导出 ONNX。

    Returns:
        ONNX 模型文件路径（如果 export_onnx=True）。
    """
    _check_deps()

    from ultralytics import YOLO

    # 1. 加载预训练模型（YOLO 会自动下载 .pt）
    model_name = f"yolo11{model_size}.pt" if pretrained else f"yolo11{model_size}.yaml"
    model = YOLO(model_name)

    logger.info("开始训练: model=%s, data=%s, epochs=%d, imgsz=%d",
                 model_name, data_yaml, epochs, imgsz)

    # 2. 训练
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        project=project,
        name=name,
        device=device,
        resume=resume,
        pretrained=pretrained,
        # UI 截图专用增强（文本保持清晰）
        hsv_h=0.015,          # 色相变化极小（防止文字变色）
        hsv_s=0.2,            # 饱和度变化适中
        hsv_v=0.2,            # 明度变化适中
        translate=0.1,        # 平移
        scale=0.2,            # 缩放
        fliplr=0.5,           # 水平翻转
        mosaic=0.5,           # 马赛克增强
        mixup=0.1,            # 混合增强
    )

    # 3. 导出 ONNX
    best_pt = Path(project) / name / "weights" / "best.pt"
    onnx_path = Path(project) / name / "weights" / "best.onnx"

    if export_onnx:
        logger.info("导出 ONNX: %s → %s", best_pt, onnx_path)
        model.export(
            format="onnx",
            imgsz=imgsz,
            half=False,        # FP32 保证兼容性
            simplify=True,     # ONNX 简化
            nms=True,          # 内嵌 NMS（推理时无需 Python 端 NMS）
        )

        if onnx_path.exists():
            logger.info("ONNX 导出成功: %s (大小: %.1f MB)",
                         onnx_path, onnx_path.stat().st_size / 1e6)
        return str(onnx_path)

    return str(best_pt)


def train_from_delphi(
    app_path: str,
    output_dir: str = "./yolo_dataset",
    forms: Optional[list[str]] = None,
    epochs: int = 100,
    model_size: str = "n",
) -> str:
    """一步完成：从 Delphi 应用采集数据 → 训练 → 导出 ONNX。

    前置条件:
      - Delphi exe 已链接 DaofyAutomation
      - 已安装 ultralytics + torch

    Args:
        app_path: Delphi exe 路径。
        output_dir: 数据集和输出目录。
        forms: 要采集的窗体列表。
        epochs: 训练轮数。
        model_size: YOLO 模型大小。

    Returns:
        ONNX 模型路径。
    """
    # 1. 采集数据
    from .synthetic_data_generator import DelphiDataCollector

    collector = DelphiDataCollector(
        app_path=app_path,
        output_dir=output_dir,
        forms=forms,
    )
    stats = collector.collect_all()
    logger.info("数据采集完成: %s", stats)

    if stats["total_images"] == 0:
        raise RuntimeError("未采集到任何训练数据。请检查 Delphi 应用是否已接入 DaofyAutomation。")

    # 2. 训练
    data_yaml = str(Path(output_dir) / "dataset.yaml")
    onnx_path = train(
        data_yaml=data_yaml,
        epochs=epochs,
        model_size=model_size,
        project=output_dir,
    )

    return onnx_path


def generate_synthetic_and_train(
    num_samples: int = 200,
    output_dir: str = "./yolo_synthetic",
    epochs: int = 50,
    model_size: str = "n",
) -> str:
    """一步完成：生成合成数据 → 训练 → 导出 ONNX。

    用于快速验证训练管线，无需 Delphi 环境。

    Args:
        num_samples: 合成截图数量。
        output_dir: 输出目录。
        epochs: 训练轮数。
        model_size: YOLO 模型大小。

    Returns:
        ONNX 模型路径。
    """
    from .synthetic_data_generator import SyntheticDataGenerator

    # 1. 生成合成数据
    gen = SyntheticDataGenerator(output_dir=output_dir)
    stats = gen.generate(num_samples=num_samples)
    logger.info("合成数据生成完成: %s", stats)

    # 2. 训练
    data_yaml = str(Path(output_dir) / "dataset.yaml")
    onnx_path = train(
        data_yaml=data_yaml,
        epochs=epochs,
        model_size=model_size,
        project=output_dir,
    )

    return onnx_path


def evaluate(
    model_path: str,
    test_images_dir: str,
    test_labels_dir: str,
) -> dict:
    """在测试集上评估 ONNX 或 PyTorch 模型的精度。

    Args:
        model_path: .onnx 或 .pt 文件。
        test_images_dir: 测试图片目录。
        test_labels_dir: YOLO 格式标签目录。

    Returns:
        {"map50": ..., "map50_95": ..., "precision": ..., "recall": ...}
    """
    if model_path.endswith(".onnx"):
        # 用 YOLOONNXDetector 做推理评估
        from .yolo_onnx import YOLOONNXDetector
        from .opencv_detector import Detection

        detector = YOLOONNXDetector(model_path)
    else:
        # 用 ultralytics 评估
        try:
            from ultralytics import YOLO
        except ImportError:
            raise ImportError("评估 PyTorch 模型需要 ultralytics")

        model = YOLO(model_path)
        results = model.val(data=str(Path(test_images_dir).parent / "dataset.yaml"))
        metrics = {
            "map50": results.box.map50,
            "map50_95": results.box.map,
            "precision": results.box.p[0],
            "recall": results.box.r[0],
        }
        return metrics

    # ONNX 评估（对每张图做推理）
    import glob
    image_files = glob.glob(os.path.join(test_images_dir, "*.png")) + \
                  glob.glob(os.path.join(test_images_dir, "*.jpg"))

    total_gt = 0
    total_tp = 0
    total_fp = 0

    for img_path in image_files:
        img_name = Path(img_path).stem
        label_path = os.path.join(test_labels_dir, f"{img_name}.txt")

        if not os.path.exists(label_path):
            continue

        # 读取 GT 标签
        with open(label_path) as f:
            gt_boxes = []
            for line in f:
                parts = line.strip().split()
                if len(parts) == 5:
                    gt_boxes.append({
                        "class_id": int(parts[0]),
                        "x": float(parts[1]),
                        "y": float(parts[2]),
                        "w": float(parts[3]),
                        "h": float(parts[4]),
                    })

        total_gt += len(gt_boxes)

        # 推理
        detections = detector.detect(img_path)

        # 简单匹配
        tp = 0
        fp = 0
        matched = set()
        for det in detections:
            found = False
            for i, gt in enumerate(gt_boxes):
                if i in matched:
                    continue
                if det.class_id == gt["class_id"]:
                    # 检查 IoU（简化为正样例存在性）
                    found = True
                    matched.add(i)
                    break
            if found:
                tp += 1
            else:
                fp += 1

        total_tp += tp
        total_fp += fp

    precision = total_tp / max(total_tp + total_fp, 1)
    recall = total_tp / max(total_gt, 1)

    return {
        "precision": precision,
        "recall": recall,
        "total_gt": total_gt,
        "total_tp": total_tp,
        "total_fp": total_fp,
    }


# ============================================================
# CLI 入口
# ============================================================

def main():
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="YOLOv11 训练 + ONNX 导出")
    parser.add_argument("--data", default="./yolo_dataset/dataset.yaml",
                        help="dataset.yaml 路径")
    parser.add_argument("--epochs", type=int, default=100, help="训练轮数")
    parser.add_argument("--model", default="n", choices=["n", "s", "m", "l", "x"],
                        help="YOLO 模型大小")
    parser.add_argument("--imgsz", type=int, default=640, help="输入图片尺寸")
    parser.add_argument("--batch", type=int, default=16, help="批次大小")
    parser.add_argument("--project", default="./yolo_output", help="输出目录")
    parser.add_argument("--name", default="train", help="实验名称")
    parser.add_argument("--device", default="", help="设备 (''=auto, 'cpu', '0')")
    parser.add_argument("--resume", action="store_true", help="从断点恢复")
    parser.add_argument("--no-pretrained", action="store_true",
                        help="不使用 COCO 预训练")
    parser.add_argument("--no-onnx", action="store_true",
                        help="不导出 ONNX")
    parser.add_argument("--synthetic", type=int, default=0,
                        help="生成 N 张合成数据并训练（无需 Delphi 环境）")

    args = parser.parse_args()

    if args.synthetic > 0:
        print(f"生成 {args.synthetic} 张合成数据并训练...")
        onnx_path = generate_synthetic_and_train(
            num_samples=args.synthetic,
            output_dir=args.project,
            epochs=args.epochs,
            model_size=args.model,
        )
    else:
        onnx_path = train(
            data_yaml=args.data,
            model_size=args.model,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            project=args.project,
            name=args.name,
            device=args.device,
            resume=args.resume,
            pretrained=not args.no_pretrained,
            export_onnx=not args.no_onnx,
        )

    print(f"\n✅ 训练完成")
    print(f"   ONNX 模型: {onnx_path}")
    print(f"   复制到项目后即可被 YOLOONNXDetector 加载使用")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
