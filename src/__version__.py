"""
版本信息 — 版本号由 pyproject.toml 统一管理

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
致谢: 感谢 Crystalxp (黑夜杀手 QQ:281309196) 的代码贡献，已合并入项目

版本号权威来源: pyproject.toml 中的 version 字段
__version__.py 在运行时动态读取 pyproject.toml，确保单点维护。
"""

import os
from pathlib import Path


def _get_project_root() -> Path:
    """获取项目根目录（pyproject.toml 所在目录）。"""
    # 当前文件在 src/__version__.py，上一级到 src，再上一级到项目根
    return Path(__file__).resolve().parent.parent


def _read_version() -> str:
    """从 pyproject.toml 读取版本号。

    Returns:
        版本号字符串；读取失败返回 "0.0.0"。
    """
    pyproject_path = _get_project_root() / "pyproject.toml"
    try:
        with open(pyproject_path, "r", encoding="utf-8") as f:
            for line in f:
                line_stripped = line.strip()
                if line_stripped.startswith("version ="):
                    parts = line_stripped.split("=", 1)
                    if len(parts) == 2:
                        ver = parts[1].strip().strip('"').strip("'")
                        if ver:
                            return ver
    except Exception:
        pass
    # 回退：尝试从环境变量或返回默认值
    return os.environ.get("DAOFY_VERSION", "0.0.0")


__version__ = _read_version()
__release_date__ = ""  # 发布日期由 pyproject.toml 维护，此处动态生成
__author__ = "吉林省左右软件开发有限公司"
__copyright__ = "Copyright (C) 2026 吉林省左右软件开发有限公司 / Equilibrium Software Development Co., Ltd, Jilin"
__license__ = "MIT"
