"""Install Daofy-provided Agent Skills into the user-level skill directory."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

SKILL_NAME = "daofy"
SKILL_VERSION = "2026.07.17"
MANIFEST_NAME = ".daofy_skill_manifest.json"
SOURCE_SKILLS_ROOT = Path(__file__).parent.parent / "resources" / "agent-skills"
DISABLED_VALUES = {"0", "false", "off", "disabled", "disable", "no"}


@dataclass
class AgentSkillInstallResult:
    """Result of a Daofy Agent Skill sync attempt."""

    status: str
    destination: str
    installed_files: list[str] = field(default_factory=list)
    updated_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def changed(self) -> bool:
        """Return True when files were installed or updated."""
        return bool(self.installed_files or self.updated_files)


def default_agents_skills_dir() -> Path:
    """Return the default shared Agent Skills directory."""
    override = os.environ.get("DAOFY_AGENT_SKILLS_DIR")
    if override:
        return Path(override).expanduser()

    user_profile = os.environ.get("USERPROFILE")
    home = Path(user_profile) if user_profile else Path.home()
    return home / ".agents" / "skills"


def is_agent_skill_install_enabled() -> bool:
    """Return whether startup Agent Skill sync is enabled."""
    value = os.environ.get("DAOFY_AGENT_SKILL_INSTALL", "1").strip().lower()
    return value not in DISABLED_VALUES


def install_daofy_agent_skills(
    *,
    destination_root: Optional[Path] = None,
    source_root: Optional[Path] = None,
) -> AgentSkillInstallResult:
    """Install or update the Daofy Agent Skill in a shared skill directory.

    The installer updates only Daofy-managed files. If a previously installed file
    was edited by the user after installation, it is skipped and reported rather
    than overwritten.
    """
    if not is_agent_skill_install_enabled():
        return AgentSkillInstallResult(
            status="disabled",
            destination=str(destination_root or default_agents_skills_dir()),
            message="Daofy Agent Skill 自动同步已关闭",
        )

    source_base = source_root or SOURCE_SKILLS_ROOT
    source_dir = source_base / SKILL_NAME
    destination_base = destination_root or default_agents_skills_dir()
    destination_dir = destination_base / SKILL_NAME

    if not source_dir.is_dir():
        message = f"Daofy Agent Skill 源目录不存在: {source_dir}"
        logger.warning(message)
        return AgentSkillInstallResult(
            status="missing_source",
            destination=str(destination_dir),
            message=message,
        )

    try:
        result = _sync_skill_directory(source_dir, destination_dir)
    except OSError as exc:
        message = f"同步 Daofy Agent Skill 失败: {exc}"
        logger.warning(message, exc_info=True)
        return AgentSkillInstallResult(
            status="error",
            destination=str(destination_dir),
            message=message,
        )

    if result.status == "current":
        logger.debug("Daofy Agent Skill 已是最新: %s", result.destination)
    elif result.status == "partial":
        logger.warning(result.message)
    else:
        logger.info(result.message)
    return result


def _sync_skill_directory(source_dir: Path, destination_dir: Path) -> AgentSkillInstallResult:
    destination_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = destination_dir / MANIFEST_NAME
    manifest = _load_manifest(manifest_path)
    manifest_exists = manifest_path.exists()
    previous_hashes = _manifest_files(manifest)

    installed: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []
    next_hashes = dict(previous_hashes)

    for relative_path, source_bytes, source_hash in _iter_source_files(source_dir):
        destination_file = destination_dir / relative_path
        previous_hash = previous_hashes.get(relative_path)

        if not destination_file.exists():
            _write_bytes(destination_file, source_bytes)
            installed.append(relative_path)
            next_hashes[relative_path] = source_hash
            continue

        destination_hash = _sha256_bytes(destination_file.read_bytes())
        if destination_hash == source_hash:
            next_hashes[relative_path] = source_hash
            continue

        can_update = (
            bool(previous_hash)
            and destination_hash == previous_hash
        )
        if not manifest_exists and _looks_like_daofy_managed_file(destination_file):
            can_update = True

        if can_update:
            _write_bytes(destination_file, source_bytes)
            updated.append(relative_path)
            next_hashes[relative_path] = source_hash
        else:
            skipped.append(relative_path)
            if previous_hash:
                next_hashes[relative_path] = previous_hash

    _write_manifest(
        manifest_path,
        {
            "name": SKILL_NAME,
            "version": SKILL_VERSION,
            "source": "Daofy for Delphi MCP Server",
            "files": next_hashes,
        },
    )

    if skipped:
        status = "partial"
        message = (
            "Daofy Agent Skill 部分更新完成；以下文件存在用户改动，已跳过: "
            + ", ".join(skipped)
        )
    elif updated:
        status = "updated"
        message = f"Daofy Agent Skill 已更新: {destination_dir}"
    elif installed:
        status = "installed"
        message = f"Daofy Agent Skill 已安装: {destination_dir}"
    else:
        status = "current"
        message = f"Daofy Agent Skill 已是最新: {destination_dir}"

    return AgentSkillInstallResult(
        status=status,
        destination=str(destination_dir),
        installed_files=installed,
        updated_files=updated,
        skipped_files=skipped,
        message=message,
    )


def _iter_source_files(source_dir: Path) -> list[tuple[str, bytes, str]]:
    items: list[tuple[str, bytes, str]] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(source_dir).as_posix()
        data = path.read_bytes()
        items.append((relative_path, data, _sha256_bytes(data)))
    return items


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Daofy Agent Skill manifest 无法读取，将按首次安装处理: %s", manifest_path)
        return {}
    if isinstance(data, dict):
        return data
    return {}


def _manifest_files(manifest: dict[str, Any]) -> dict[str, str]:
    files = manifest.get("files")
    if not isinstance(files, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in files.items()
        if isinstance(value, str)
    }


def _looks_like_daofy_managed_file(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "daofy-managed-skill: true" in text[:4096]


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_manifest(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
