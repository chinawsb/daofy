"""Lightweight guard for Delphi source edits.

The guard cannot block other AI agents by itself. It records writes that go
through Daofy and lets the project watcher flag Delphi file changes that were
not recently authorized by Daofy.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Deque, Dict, Iterable, Optional, Set

from src.utils.logger import get_logger

logger = get_logger(__name__)

DELPHI_EXTENSIONS: Set[str] = {
    ".pas", ".dpr", ".dpk", ".dfm", ".fmx", ".inc", ".dproj",
}

DEFAULT_AUTH_TTL_SECONDS = 10.0
MAX_RECENT_EVENTS = 50

_AUTHORIZED_WRITES: Dict[str, "AuthorizedWrite"] = {}
_UNAUTHORIZED_EVENTS: Deque["ExternalEditEvent"] = deque(maxlen=MAX_RECENT_EVENTS)
_LOCK = threading.Lock()


@dataclass(frozen=True)
class AuthorizedWrite:
    path: str
    tool: str
    operation: str
    expires_at: float
    created_at: float


@dataclass(frozen=True)
class ExternalEditEvent:
    path: str
    event_type: str
    detected_at: float
    age_ms: Optional[int] = None


def is_guard_enabled() -> bool:
    """Return whether external edit detection is enabled."""
    return get_guard_mode() not in {"0", "false", "off", "disabled", "disable"}


def get_guard_mode() -> str:
    """Return the normalized edit-guard mode."""
    mode = os.environ.get("DAOFY_EDIT_GUARD", "warn").strip().lower()
    return mode or "warn"


def is_strict_mode() -> bool:
    """Return True when unauthorized edits should block guarded workflows."""
    return is_guard_enabled() and get_guard_mode() in {"strict", "block", "fail"}


def is_delphi_path(file_path: str | os.PathLike[str]) -> bool:
    return Path(file_path).suffix.lower() in DELPHI_EXTENSIONS


def _normalize_path(file_path: str | os.PathLike[str]) -> str:
    return os.path.abspath(os.path.realpath(os.fspath(file_path)))


def _scope_root(scope_path: Optional[str | os.PathLike[str]]) -> Optional[str]:
    if scope_path is None:
        return None
    normalized = _normalize_path(scope_path)
    if os.path.isdir(normalized):
        return normalized
    return os.path.dirname(normalized)


def _is_under(path: str, root: Optional[str]) -> bool:
    if root is None:
        return True
    try:
        rel = os.path.relpath(path, root)
    except ValueError:
        return False
    return rel == "." or not rel.startswith("..")


def record_authorized_write(
    file_path: str | os.PathLike[str],
    *,
    tool: str,
    operation: str,
    ttl_seconds: float = DEFAULT_AUTH_TTL_SECONDS,
) -> None:
    """Register a short-lived authorization for an upcoming Daofy write."""
    if not is_guard_enabled() or not is_delphi_path(file_path):
        return

    now = time.monotonic()
    normalized = _normalize_path(file_path)
    with _LOCK:
        _AUTHORIZED_WRITES[normalized] = AuthorizedWrite(
            path=normalized,
            tool=tool,
            operation=operation,
            created_at=now,
            expires_at=now + ttl_seconds,
        )


def record_authorized_writes(
    file_paths: Iterable[str | os.PathLike[str]],
    *,
    tool: str,
    operation: str,
    ttl_seconds: float = DEFAULT_AUTH_TTL_SECONDS,
) -> None:
    for file_path in file_paths:
        record_authorized_write(
            file_path,
            tool=tool,
            operation=operation,
            ttl_seconds=ttl_seconds,
        )


def _discard_expired(now: float) -> None:
    expired = [
        path for path, item in _AUTHORIZED_WRITES.items()
        if item.expires_at < now
    ]
    for path in expired:
        _AUTHORIZED_WRITES.pop(path, None)


def consume_authorized_write(file_path: str | os.PathLike[str]) -> Optional[AuthorizedWrite]:
    """Consume and return a matching authorization if it is still valid."""
    if not is_guard_enabled() or not is_delphi_path(file_path):
        return None

    now = time.monotonic()
    normalized = _normalize_path(file_path)
    with _LOCK:
        _discard_expired(now)
        item = _AUTHORIZED_WRITES.pop(normalized, None)
    if item is None:
        return None
    if item.expires_at < now:
        return None
    return item


def record_external_edit(
    file_path: str | os.PathLike[str],
    *,
    event_type: str = "modified",
) -> Optional[ExternalEditEvent]:
    """Record a Delphi file change that did not match a Daofy write."""
    if not is_guard_enabled() or not is_delphi_path(file_path):
        return None

    item = consume_authorized_write(file_path)
    if item is not None:
        logger.debug(
            "Daofy-authorized Delphi edit accepted: %s (%s/%s)",
            item.path,
            item.tool,
            item.operation,
        )
        return None

    event = ExternalEditEvent(
        path=_normalize_path(file_path),
        event_type=event_type,
        detected_at=time.time(),
    )
    with _LOCK:
        _UNAUTHORIZED_EVENTS.append(event)
    logger.warning(
        "Detected Delphi file change not made through Daofy tools: %s",
        event.path,
    )
    return event


def snapshot_status() -> dict:
    """Return a JSON-serializable guard status snapshot."""
    now_monotonic = time.monotonic()
    now_wall = time.time()
    with _LOCK:
        _discard_expired(now_monotonic)
        pending = [asdict(item) for item in _AUTHORIZED_WRITES.values()]
        events = []
        for item in _UNAUTHORIZED_EVENTS:
            data = asdict(item)
            data["age_ms"] = max(0, int((now_wall - item.detected_at) * 1000))
            events.append(data)

    return {
        "enabled": is_guard_enabled(),
        "mode": get_guard_mode(),
        "strict_blocks": is_strict_mode(),
        "pending_authorized_writes": len(pending),
        "recent_unauthorized_count": len(events),
        "recent_unauthorized_edits": events,
    }


def recent_unauthorized_edits(
    scope_path: Optional[str | os.PathLike[str]] = None,
) -> list[dict]:
    """Return recent unauthorized Delphi edits, optionally limited to a root."""
    root = _scope_root(scope_path)
    now_wall = time.time()
    with _LOCK:
        events = []
        for item in _UNAUTHORIZED_EVENTS:
            if not _is_under(item.path, root):
                continue
            data = asdict(item)
            data["age_ms"] = max(0, int((now_wall - item.detected_at) * 1000))
            events.append(data)
    return events


def external_edit_block_message(
    scope_path: Optional[str | os.PathLike[str]] = None,
) -> Optional[str]:
    """Return a blocking error message when strict mode sees external edits."""
    if not is_strict_mode():
        return None
    events = recent_unauthorized_edits(scope_path)
    if not events:
        return None

    scope = _scope_root(scope_path) or "<全部>"
    lines = [
        "Delphi 编辑保护已阻止本次操作。",
        "",
        "原因：检测到最近有 Delphi 源码文件绕过 Daofy 工具被修改。",
        f"检查范围：{scope}",
        "",
        "检测到的文件：",
    ]
    event_names = {
        "created": "已创建",
        "deleted": "已删除",
        "modified": "已修改",
        "moved": "已移动",
    }
    for event in events[:10]:
        age_ms = event.get("age_ms")
        age = f"，距今 {age_ms}ms" if age_ms is not None else ""
        event_type = str(event.get("event_type", "modified"))
        event_name = event_names.get(event_type, event_type)
        lines.append(f"- {event['path']}（{event_name}{age}）")
    if len(events) > 10:
        lines.append(f"- ... 还有 {len(events) - 10} 个文件")
    lines.extend([
        "",
        "请使用 `delphi_file` 或 Daofy 已登记的 Delphi 工具读写 .pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx 文件。",
        "如果这次外部修改是有意为之，请先检查或回退这些改动；确认工作区干净后重启 MCP Server。",
        "如只需记录告警而不阻断，请设置 `DAOFY_EDIT_GUARD=warn`；如需关闭检测，请设置 `DAOFY_EDIT_GUARD=off`。",
    ])
    return "\n".join(lines)


def reset_guard_state() -> None:
    """Clear guard state. Intended for tests."""
    with _LOCK:
        _AUTHORIZED_WRITES.clear()
        _UNAUTHORIZED_EVENTS.clear()
