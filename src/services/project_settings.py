"""项目级编译配置。

在工程目录（或其任意父目录）放置 ``.daofy/project.json`` 或
``daofy.project.json``，即可为**单个工程**指定 Delphi 版本与 MSBuild，
而不影响同机其它工程：

.. code-block:: json

    {
      "delphi_version": "11.0",
      "msbuild_path": "C:\\\\Windows\\\\Microsoft.NET\\\\Framework\\\\v3.5\\\\MSBuild.exe",
      "compiler_version": "Delphi XE4 Win32"
    }

``delphi_version`` 也接受产品名（``"XE4"``、``"Delphi 12 Athens"``）；
``msbuild_path`` 支持相对路径（按配置文件所在目录解析）。

查找顺序：``<工程目录>/.daofy/project.json`` → ``<工程目录>/daofy.project.json``
→ 逐级向上查找父目录（最多 8 层）。就近命中的文件生效。

优先级：工具调用显式参数 > 项目配置 > ``msbuild_by_delphi_version`` 版本映射
> 自动探测。
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Union

from ..utils.delphi_versions import normalize_version_key
from ..utils.logger import get_logger

logger = get_logger(__name__)

PROJECT_CONFIG_DIR = ".daofy"
PROJECT_CONFIG_NAME = "project.json"
PROJECT_CONFIG_ALT_NAME = "daofy.project.json"
MAX_PARENT_LOOKUP = 8


@dataclass(frozen=True)
class ProjectSettings:
    """单个工程的编译配置。

    Attributes:
        delphi_version: Delphi 注册表版本号（规范化后，如 ``"11.0"``）；
            输入也接受产品名（``"XE4"``）
        msbuild_path: 该工程使用的 MSBuild.exe 路径（相对路径已按配置目录展开）
        compiler_version: 该工程使用的编译器名称（``compilers.json`` 中的 name），
            也可写版本号/产品名
        source: 配置来源文件路径（用于日志/报错定位）
        error: 配置内容无效时的错误信息（如无法识别的 delphi_version）
    """

    delphi_version: Optional[str] = None
    msbuild_path: Optional[str] = None
    compiler_version: Optional[str] = None
    source: Optional[str] = None
    error: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        """是否未配置任何有效项。"""
        if self.error:
            return False
        return not (self.delphi_version or self.msbuild_path or self.compiler_version)


def _iter_candidates(directory: Path) -> Iterator[Path]:
    yield directory / PROJECT_CONFIG_DIR / PROJECT_CONFIG_NAME
    yield directory / PROJECT_CONFIG_ALT_NAME


def find_project_config(project_path: Union[str, Path]) -> Optional[Path]:
    """从工程路径向上查找项目级配置文件。

    Args:
        project_path: ``.dproj`` / ``.dpr`` / ``.dpk`` 路径，或工程目录

    Returns:
        命中的配置文件路径，未找到返回 None
    """
    try:
        start = Path(project_path)
    except TypeError:
        return None

    # 目录（即使名字里带点，如 MyApp.v2）直接作为起点；
    # 文件或不存在的路径则从其父目录开始。
    try:
        if start.is_dir() or (not start.exists() and not start.suffix):
            directory = start
        else:
            directory = start.parent
    except OSError:
        return None
    if not directory.exists():
        return None

    try:
        directory = directory.resolve()
    except OSError:
        return None

    for _ in range(MAX_PARENT_LOOKUP):
        for candidate in _iter_candidates(directory):
            if candidate.is_file():
                return candidate
        parent = directory.parent
        if parent == directory:
            break
        directory = parent
    return None


def _read_text(path: Path) -> tuple[Optional[dict], Optional[str]]:
    """读取并解析项目配置，返回 ``(data, error)``。"""
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        logger.error("读取项目配置失败 %s: %s", path, exc)
        return None, f"读取项目配置失败 {path}: {exc}"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("项目配置不是合法 JSON: %s (%s)", path, exc)
        return None, f"项目配置不是合法 JSON {path}: {exc}"

    if not isinstance(data, dict):
        logger.error("项目配置应为 JSON 对象: %s", path)
        return None, f"项目配置应为 JSON 对象: {path}"
    return data, None


def load_project_settings(
    project_path: Union[str, Path],
) -> Optional[ProjectSettings]:
    """加载工程的项目级配置。

    Args:
        project_path: ``.dproj`` / ``.dpr`` / ``.dpk`` 路径，或工程目录

    Returns:
        项目配置；无配置文件或配置为空时返回 None。配置文件存在但无法解析时
        返回带 ``error`` 的配置，调用方应直接失败而不是静默回退。
    """
    config_path = find_project_config(project_path)
    if config_path is None:
        return None

    data, read_error = _read_text(config_path)
    if data is None:
        return ProjectSettings(
            source=str(config_path),
            error=read_error or f"无法读取项目配置 {config_path}",
        )

    raw_version = data.get("delphi_version")
    delphi_version = normalize_version_key(raw_version)
    error = None
    if raw_version not in (None, "") and delphi_version is None:
        error = (
            f"项目配置 {config_path} 的 delphi_version={raw_version!r} 无法识别；"
            "请写成注册表版本号（如 11.0）或产品名（如 XE4）"
        )
        logger.error(error)

    raw_msbuild = data.get("msbuild_path")
    msbuild_path = str(raw_msbuild).strip() if raw_msbuild else None
    if msbuild_path:
        candidate = Path(msbuild_path).expanduser()
        if not candidate.is_absolute():
            # 相对路径按配置文件所在目录解析，而不是当前工作目录
            candidate = config_path.parent / candidate
        msbuild_path = str(candidate)

    raw_compiler = data.get("compiler_version")
    compiler_version = str(raw_compiler).strip() if raw_compiler else None

    settings = ProjectSettings(
        delphi_version=delphi_version,
        msbuild_path=msbuild_path or None,
        compiler_version=compiler_version or None,
        source=str(config_path),
        error=error,
    )
    if settings.is_empty:
        return None

    logger.info(
        "加载项目配置 %s: delphi_version=%s, msbuild_path=%s, compiler_version=%s",
        config_path,
        settings.delphi_version or "-",
        settings.msbuild_path or "-",
        settings.compiler_version or "-",
    )
    return settings
