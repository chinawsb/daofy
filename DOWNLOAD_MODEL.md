# 下载 YOLOv11n ONNX 模型

当前环境无法直接下载，请在你的开发机上执行以下步骤：

## 方式 1：直接下载（推荐）

1. 打开链接下载：https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.onnx
2. 将下载的 `yolo11n.onnx`（约 11MB）放到项目 `models/` 目录下

## 方式 2：用命令行下载

```bash
curl -L -o models/yolo11n.onnx https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.onnx
```

## 验证

下载后运行以下命令验证模型可加载：

```bash
python -c "
from src.detection.yolo_onnx import YOLOONNXDetector
yolo = YOLOONNXDetector('models/yolo11n.onnx')
print('✅ 模型加载成功')
"
```
