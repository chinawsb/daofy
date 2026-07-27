"""
训练数据采集脚本 — Daofy Training App → YOLO 格式标签

用法:
  cd C:/user/daofy-agent/daofy
  python training/collect_data.py

流程:
  1. 启动 TrainApp.exe（含 DaofyAutomation）
  2. 对每个 Tab 页截图 + dumpstate → YOLO 标签
  3. RTTI 切换控件属性（Enabled/Disabled/Checked/ReadOnly）→ 更多变体
  4. 输出到 training/dataset/（images + labels + dataset.yaml）

前置条件:
  - TrainApp.exe 已编译（training/TrainApp/Win32/Debug/TrainApp.exe）
  - Daofy MCP Server 运行中（本项目）
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("collect")

# ── 路径 ────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
APP_PATH = str(PROJECT_ROOT / "training" / "TrainApp" / "Win32" / "Debug" / "TrainApp.exe")
DATASET_DIR = PROJECT_ROOT / "training" / "dataset"
IMAGES_DIR = DATASET_DIR / "images"
LABELS_DIR = DATASET_DIR / "labels"
SNAPSHOTS_DIR = PROJECT_ROOT / "training" / "snapshots"

# ── Delphi 控件 → YOLO class_id（自动从项目 _CLASS_MAP 生成）──
# 来自 dfm_generator._CLASS_MAP（class_id 从 1 开始，YOLO 从 0 开始）
DELPHI_CLASS_MAP = {
    "TButton": 0, "TBitBtn": 0, "TSpeedButton": 0,
    "TEdit": 1, "TLabeledEdit": 1, "TSpinEdit": 1,
    "TLabel": 2, "TLinkLabel": 2,
    "TComboBox": 3,
    "TCheckBox": 4,
    "TRadioButton": 5,
    "TListBox": 6, "TCheckListBox": 6,
    "TPanel": 7,
    "TGroupBox": 8, "TRadioGroup": 8,
    "TPageControl": 9,
    "TTabSheet": 10,
    "TStringGrid": 11,
    "TMemo": 12,
    "TListView": 13,
    "TTreeView": 14,
    "TProgressBar": 15,
    "TTrackBar": 16,
    "TScrollBar": 17,
    "TScrollBox": 18,
    "TStatusBar": 19,
}
CLASS_NAMES = {v: k for k, v in DELPHI_CLASS_MAP.items()}
NUM_CLASSES = len(DELPHI_CLASS_MAP)

# ── 采集变异配置 ────────────────────────────────────────────
# 每个变异的描述 + rset 命令参数
VARIANTS = [
    ("default", []),
    ("disable_buttons", [
        {"cmd": "rset", "target": "btnDisabled", "prop": "Enabled", "val": "False"},
    ]),
    ("disable_all", [
        {"cmd": "rset", "target": "btnDisabled", "prop": "Enabled", "val": "False"},
        {"cmd": "rset", "target": "chkDisabled", "prop": "Enabled", "val": "False"},
    ]),
    ("check_changed", [
        {"cmd": "rset", "target": "chkEnable", "prop": "Checked", "val": "False"},
        {"cmd": "rset", "target": "chkAutoSave", "prop": "Checked", "val": "True"},
    ]),
    ("text_changed", [
        {"cmd": "rset", "target": "edtName", "prop": "Text", "val": "Alice Wang"},
        {"cmd": "rset", "target": "edtPassword", "prop": "Text", "val": "pass123"},
    ]),
    ("combobox_selection", [
        {"cmd": "rset", "target": "cmbCity", "prop": "ItemIndex", "val": "2"},
    ]),
]


def ensure_dirs():
    """创建输出目录。"""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def call_auto(script: list) -> dict:
    """调用 automate_delphi 执行脚本。"""
    from src.services.automation_service import execute_automation
    return execute_automation(
        action="gui",
        app_path=APP_PATH,
        script=script,
        snapshots_dir=str(SNAPSHOTS_DIR),
        stop_on_failure=False,
        keep_alive=True,
        wait_for_pipe=30,
    )


def capture_and_label(form_name: str, tab_name: str, variant: str, index: int):
    """对一个状态截图 + dumpstate → 保存 YOLO 标签。"""
    script = [
        {"cmd": "capture", "reqId": "img", "target": f"{form_name}_{tab_name}_{variant}"},
        {"cmd": "dumpstate", "reqId": "labels"},
    ]
    result = call_auto(script)

    steps = result.get("steps", [])
    capture_path = ""
    dump_data = None

    for step in steps:
        if step.get("cmd") == "capture":
            resp = step.get("response") or {}
            capture_path = resp.get("path", "")
        elif step.get("cmd") == "dumpstate":
            dump_data = step.get("response") or {}

    if not capture_path or not os.path.isfile(capture_path):
        log.warning("  [SKIP] capture failed")
        return False

    # 生成 YOLO 标签
    labels = dumpstate_to_yolo(dump_data)
    if not labels:
        log.warning("  [SKIP] no labels from dumpstate")
        return False

    # 图片 → 统一 images 目录
    img_name = f"{form_name}_{tab_name}_{variant}_{index:03d}.png"
    img_dest = IMAGES_DIR / img_name
    import shutil
    shutil.copy2(capture_path, str(img_dest))

    # 标签 → labels 目录
    label_path = LABELS_DIR / img_name.replace(".png", ".txt")
    with open(str(label_path), "w", encoding="utf-8") as f:
        for line in labels:
            f.write(line + "\n")

    log.info(f"  [OK] {img_name}: {len(labels)} labels")
    return True


def dumpstate_to_yolo(data: dict) -> list[str]:
    """将 dumpstate JSON 转换为 YOLO 格式标签行。

    dumpstate 返回嵌套 JSON:
      { "form": "MainForm", "class": "TMainForm",
        "props": { "Width": 1024, "Height": 720, ... },
        "controls": [ { "name": "btnOK", "class": "TButton",
                        "props": { "Left": 16, "Top": 24, "Width": 89, "Height": 33, ... } }, ... ] }

    YOLO 格式: <class_id> <x_center> <y_center> <width> <height>
    (归一化到 [0,1])
    """
    if not data:
        return []

    # 展平 controls（从嵌套的 children 树中提取所有叶子控件）
    def flatten_controls(node, results):
        name = node.get("name", "")
        cls = node.get("class", "")
        props = node.get("props", {})

        left = _get_prop(props, "Left", 0)
        top = _get_prop(props, "Top", 0)
        w = _get_prop(props, "Width", 0)
        h = _get_prop(props, "Height", 0)

        if cls and w > 2 and h > 2:
            results.append((name, cls, left, top, w, h))

        for child in node.get("children", []):
            flatten_controls(child, results)

    # 获取容器尺寸（先找 form.props，再找顶层 Width/Height）
    form_class = data.get("class", "TMainForm")
    form_props = data.get("props", {})
    form_width = _get_prop(form_props, "Width", 1024) or 1024
    form_height = _get_prop(form_props, "Height", 720) or 720

    # 也检查 data 层级的 Width/Height
    if form_width <= 0:
        form_width = data.get("Width", 1024) or 1024
    if form_height <= 0:
        form_height = data.get("Height", 720) or 720

    flat: list[tuple] = []
    for ctrl in data.get("controls", []):
        flatten_controls(ctrl, flat)

    labels: list[str] = []
    for name, cls, left, top, w, h in flat:
        cid = DELPHI_CLASS_MAP.get(cls)
        if cid is None:
            continue  # 跳过未映射的控件

        # YOLO: <class_id> <x_center> <y_center> <width> <height>
        xc = (left + w / 2) / form_width
        yc = (top + h / 2) / form_height
        nw = w / form_width
        nh = h / form_height

        # 边界裁剪
        xc = max(0.0, min(1.0, xc))
        yc = max(0.0, min(1.0, yc))
        nw = max(0.0, min(1.0, nw))
        nh = max(0.0, min(1.0, nh))

        labels.append(f"{cid} {xc:.6f} {yc:.6f} {nw:.6f} {nh:.6f}")

    return labels


def _get_prop(props: dict, name: str, default=0):
    """从 props dict 中安全读取数值属性（兼容 JSON 中可能是 int/float/str）。"""
    val = props.get(name, default)
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def write_dataset_yaml():
    """生成 Ultralytics dataset.yaml。"""
    nc = NUM_CLASSES
    names = {i: CLASS_NAMES.get(i, f"class_{i}") for i in range(nc)}
    yaml_path = DATASET_DIR / "dataset.yaml"
    lines = [
        f"# YOLO 数据集 — Daofy 自动采集",
        f"path: {DATASET_DIR.resolve().as_posix()}",
        f"train: images",
        f"val: images",
        f"nc: {nc}",
        f"names:",
    ]
    for i in range(nc):
        lines.append(f"  {i}: {names[i]}")
    yaml_path.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"dataset.yaml -> {yaml_path}")


def main():
    ensure_dirs()

    # 1. 启动 TrainApp
    log.info("=== 启动 TrainApp ===")
    script_launch = [
        {"cmd": "wait", "reqId": "init", "target": "1000"},
        {"cmd": "capture", "reqId": "launch_check", "target": "launch"},
    ]
    try:
        result = call_auto(script_launch)
        log.info(f"启动结果: {json.dumps(result, ensure_ascii=False)[:200]}")
    except Exception as e:
        log.error(f"启动失败（请确认 TrainApp 已编译）: {e}")
        log.error(f"  APP_PATH={APP_PATH}")
        sys.exit(1)

    # 2. 对每个 Tab 页采集
    tabs = [
        ("Standard", "TMainForm"),
        ("Advanced", "TMainForm"),
        ("Data Grid", "TMainForm"),
    ]

    total_images = 0
    total_labels = 0
    image_index = 0

    for tab_caption, form_name in tabs:
        log.info(f"=== Tab: {tab_caption} ===")

        # 先切到目标 Tab（通过 rset 切换 PageControl）
        if tab_caption != "Standard":
            tab_map = {"Advanced": 1, "Data Grid": 2}
            idx = tab_map.get(tab_caption, 0)
            try:
                call_auto([{"cmd": "rset", "target": "pcMain", "prop": "ActivePageIndex", "val": str(idx)}])
                time.sleep(0.5)
            except Exception as e:
                log.warning(f"  切 Tab 失败: {e}")

        # 采集默认状态
        ok = capture_and_label(form_name, tab_caption.lower().replace(" ", "_"), "default", image_index)
        if ok:
            image_index += 1
            total_images += 1

        # 采集变异状态
        for var_name, rset_cmds in VARIANTS:
            try:
                if rset_cmds:
                    call_auto(rset_cmds)
                    time.sleep(0.3)
                ok = capture_and_label(form_name, tab_caption.lower().replace(" ", "_"), var_name, image_index)
                if ok:
                    image_index += 1
                    total_images += 1
            except Exception as e:
                log.warning(f"  变异 {var_name} 失败: {e}")

        # 恢复默认状态（切回 Standard tab）
        if tab_caption != "Standard":
            try:
                call_auto([{"cmd": "rset", "target": "pcMain", "prop": "ActivePageIndex", "val": "0"}])
                time.sleep(0.3)
            except Exception:
                pass

    # 3. 写入 dataset.yaml
    write_dataset_yaml()

    log.info("=" * 40)
    log.info(f"采集完成: {total_images} 张图片")
    log.info(f"输出目录: {DATASET_DIR}")
    log.info("")
    log.info("下一步训练命令:")
    log.info(f"  python -m src.detection.train_yolo --data {DATASET_DIR / 'dataset.yaml'} --epochs 100")


if __name__ == "__main__":
    main()
