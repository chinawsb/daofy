"""
版本信息 — 版本号由 pyproject.toml 统一管理

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
致谢: 感谢 Crystalxp (黑夜杀手 QQ:281309196) 的代码贡献，已合并入项目

版本号权威来源: pyproject.toml 中的 version 字段
pip 安装时通过 importlib.metadata 从包元数据读取；
源码运行时从 pyproject.toml 文件读取（兜底）。
"""

import logging
import os
from importlib.metadata import version as _get_installed_version, PackageNotFoundError
from pathlib import Path

logger = logging.getLogger(__name__)

_PACKAGE_NAME = "daofy-for-delphi"


def _read_version() -> str:
    """读取版本号。

    优先级：
    1. DAOFY_VERSION 环境变量（发布脚本可设置）
    2. importlib.metadata（pip 安装后从包元数据读取，最可靠）
    3. pyproject.toml 文件（源码运行时兜底）
    4. 默认值 "0.0.0"

    Returns:
        版本号字符串；读取失败返回 "0.0.0"。
    """
    # 1. 环境变量
    env_ver = os.environ.get("DAOFY_VERSION")
    if env_ver:
        return env_ver

    # 2. importlib.metadata — pip 安装场景下的标准方式
    try:
        return _get_installed_version(_PACKAGE_NAME)
    except PackageNotFoundError:
        pass  # 源码运行时 metadata 不可用，继续尝试文件读取

    # 3. 读取 pyproject.toml（源码运行兜底）
    #    当前文件在 src/__version__.py，上一级到 src，再上一级到项目根
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
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
        logger.debug("pyproject.toml 中未找到 version 字段")
    except Exception as e:
        logger.debug("读取 pyproject.toml version 失败: %s", e)

    # 4. 兜底
    return os.environ.get("DAOFY_VERSION", "0.0.0")


__version__ = _read_version()
__release_date__ = ""  # 发布日期由 pyproject.toml 维护，此处动态生成
__author__ = "吉林省左右软件开发有限公司"
__copyright__ = "Copyright (C) 2026 吉林省左右软件开发有限公司 / Equilibrium Software Development Co., Ltd, Jilin"
__license__ = "MIT"
