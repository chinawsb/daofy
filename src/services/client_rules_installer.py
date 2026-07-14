"""Install Daofy-provided client rules into the MCP client's rules directory.

When Daofy starts and a client connects, this module installs a single
Daofy-owned rule file (``daofy-delphi.md``) into the connected client's
rules directory (e.g. ``~/.codebuddy/rules`` for CodeBuddy, ``~/.cursor/rules``
for Cursor, ``~/.claude/rules`` for Claude Desktop).

The descriptor ``client-rules/daofy-delphi.yaml`` defines which client names
map to which rules directory and whether the rule file needs a YAML frontmatter.

Safety:
- Only Daofy-managed files are written (tracked via a JSON manifest).
- Files edited by the user after installation are skipped, never overwritten.
- Idempotent: identical content is a no-op.
- Fully opt-out via ``DAOFY_CLIENT_RULES_INSTALL=0``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional

import yaml

from src.utils.logger import get_logger

logger = get_logger(__name__)

DISABLED_VALUES = {"0", "false", "off", "disabled", "disable", "no"}

SOURCE_RULES_ROOT = Path(__file__).parent.parent / "resources" / "client-rules"
DESCRIPTOR_NAME = "daofy-delphi.yaml"
MANIFEST_NAME = ".daofy_client_rules_manifest.json"
DAOFY_MANAGED_MARKER = "daofy-managed-rule: true"
# 旧版(首次手动写入、无托管标记)也能识别为 Daofy 自有文件，便于自愈更新
DAOFY_RULE_SIGNATURE = "必须用 Daofy 的 `delphi_file`"


def is_client_rules_install_enabled() -> bool:
    """Return whether the client-rules auto install is enabled."""
    value = os.environ.get("DAOFY_CLIENT_RULES_INSTALL", "1").strip().lower()
    return value not in DISABLED_VALUES


def _resolve_home() -> Path:
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        return Path(user_profile)
    return Path.home()


def _load_descriptor() -> Optional[dict[str, Any]]:
    descriptor_path = SOURCE_RULES_ROOT / DESCRIPTOR_NAME
    if not descriptor_path.is_file():
        logger.warning("客户端规则描述符不存在: %s", descriptor_path)
        return None
    try:
        with descriptor_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("解析客户端规则描述符失败: %s", exc)
        return None
    if not isinstance(data, dict):
        logger.warning("客户端规则描述符格式无效: %s", descriptor_path)
        return None
    # 描述符以 `rule:` 为根节点，扁平化取其子树
    return data.get("rule", data)


def detect_client(client_params: Any) -> Optional[str]:
    """Detect the connected client's normalized name from initialize params.

    Returns the lower-cased ``clientInfo.name`` or ``None`` when unavailable.
    """
    if client_params is None:
        return None
    client_info = getattr(client_params, "clientInfo", None)
    if client_info is None:
        return None
    name = getattr(client_info, "name", None)
    if not name:
        return None
    return str(name).strip().lower()


def _match_rule_entry(desc: dict[str, Any], client_name: str) -> Optional[dict[str, Any]]:
    clients = desc.get("clients") or []
    if not isinstance(clients, list):
        return None
    for entry in clients:
        if not isinstance(entry, dict):
            continue
        matches = entry.get("match") or []
        if not isinstance(matches, list):
            matches = [matches]
        for token in matches:
            if not isinstance(token, str):
                continue
            if token.strip().lower() in client_name:
                return entry
    return None


def _rules_dir_for(entry: dict[str, Any], home: Path) -> Optional[Path]:
    override = os.environ.get("DAOFY_CLIENT_RULES_DIR")
    if override:
        return Path(override).expanduser()
    rel = entry.get("rules_dir")
    if not rel:
        return None
    return home / Path(rel.replace("/", os.sep))


def _build_rule_bytes(desc: dict[str, Any], entry: dict[str, Any]) -> Optional[bytes]:
    rule_file = desc.get("file") or desc.get("managed_filename")
    if not rule_file:
        return None
    source_path = SOURCE_RULES_ROOT / rule_file
    if not source_path.is_file():
        logger.warning("规则源文件不存在: %s", source_path)
        return None
    text = source_path.read_text(encoding="utf-8")

    fmt = (entry.get("format") or "markdown").lower()
    if fmt != "markdown" or not entry.get("frontmatter"):
        return text.encode("utf-8")

    frontmatter = entry["frontmatter"]
    if isinstance(frontmatter, dict):
        fm_lines = ["---"]
        fm_lines.append(yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).rstrip())
        fm_lines.append("---")
        fm_lines.append("")
        text = "\n".join(fm_lines) + text
    return text.encode("utf-8")


def install_client_rules(client_params: Any) -> dict[str, Any]:
    """Install Daofy client rules for the connected MCP client.

    Returns a small status dict (always JSON-serializable) describing the outcome.
    """
    result: dict[str, Any] = {"status": "skipped", "client": None, "destination": None,
                              "action": None, "message": ""}
    if not is_client_rules_install_enabled():
        result["status"] = "disabled"
        result["message"] = "客户端规则自动安装已关闭 (DAOFY_CLIENT_RULES_INSTALL)"
        logger.info(result["message"])
        return result

    desc = _load_descriptor()
    if desc is None:
        result["status"] = "error"
        result["message"] = "无法加载客户端规则描述符"
        return result

    client_name = detect_client(client_params)
    result["client"] = client_name
    if not client_name:
        result["status"] = "unknown_client"
        result["message"] = "未识别到 MCP 客户端名称，跳过规则安装"
        logger.info(result["message"])
        return result

    entry = _match_rule_entry(desc, client_name)
    if entry is None:
        result["status"] = "no_match"
        result["message"] = f"客户端 '{client_name}' 无对应规则目录映射，跳过"
        logger.info(result["message"])
        return result

    home = _resolve_home()
    rules_dir = _rules_dir_for(entry, home)
    if rules_dir is None:
        result["status"] = "no_dir"
        result["message"] = "无法确定规则目录"
        return result

    managed_filename = (
        entry.get("managed_filename")
        or desc.get("managed_filename")
        or desc.get("file")
        or "daofy-delphi.md"
    )
    destination_file = rules_dir / managed_filename
    result["destination"] = str(destination_file)

    rule_bytes = _build_rule_bytes(desc, entry)
    if rule_bytes is None:
        result["status"] = "error"
        result["message"] = "无法生成规则内容"
        return result

    manifest_path = rules_dir / MANIFEST_NAME
    manifest = _load_manifest(manifest_path)
    source_hash = _sha256(rule_bytes)
    previous_hash = (manifest.get("files") or {}).get(managed_filename)

    if destination_file.exists():
        destination_hash = _sha256(destination_file.read_bytes())
        if destination_hash == source_hash:
            result["status"] = "current"
            result["action"] = "none"
            result["message"] = f"客户端规则已是最新: {destination_file}"
            _record_manifest(manifest_path, managed_filename, source_hash)
            return result

        can_update = bool(previous_hash) and destination_hash == previous_hash
        if not manifest_path.exists() and _looks_daofy_managed(destination_file):
            can_update = True
        if not can_update:
            result["status"] = "skipped"
            result["action"] = "skip_user_edited"
            result["message"] = f"用户已修改规则文件，保留不覆盖: {destination_file}"
            logger.info(result["message"])
            return result

        _write_bytes(destination_file, rule_bytes)
        _record_manifest(manifest_path, managed_filename, source_hash)
        result["status"] = "updated"
        result["action"] = "updated"
        result["message"] = f"客户端规则已更新: {destination_file}"
        logger.info(result["message"])
        return result

    _write_bytes(destination_file, rule_bytes)
    _record_manifest(manifest_path, managed_filename, source_hash)
    result["status"] = "installed"
    result["action"] = "installed"
    result["message"] = f"客户端规则已安装: {destination_file}"
    logger.info(result["message"])
    return result


# ---- helpers (mirror agent_skill_installer safety semantics) ----

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("客户端规则 manifest 无法读取，按首次处理: %s", manifest_path)
        return {}


def _record_manifest(manifest_path: Path, filename: str, file_hash: str) -> None:
    manifest = _load_manifest(manifest_path)
    files = manifest.get("files") or {}
    if not isinstance(files, dict):
        files = {}
    files[filename] = file_hash
    manifest["files"] = files
    manifest["source"] = "Daofy for Delphi MCP Server"
    _write_bytes(
        manifest_path,
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def _looks_daofy_managed(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    head = text[:4096]
    return DAOFY_MANAGED_MARKER in head or DAOFY_RULE_SIGNATURE in head
