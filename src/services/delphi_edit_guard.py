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
    mode = os.environ.get("DAOFY_EDIT_GUARD", "warn").strip().lower()
    return mode not in {"0", "false", "off", "disabled", "disable"}


def is_delphi_path(file_path: str | os.PathLike[str]) -> bool:
    return Path(file_path).suffix.lower() in DELPHI_EXTENSIONS


def _normalize_path(file_path: str | os.PathLike[str]) -> str:
    return os.path.abspath(os.path.realpath(os.fspath(file_path)))


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
        "mode": os.environ.get("DAOFY_EDIT_GUARD", "warn").strip().lower() or "warn",
        "pending_authorized_writes": len(pending),
        "recent_unauthorized_count": len(events),
        "recent_unauthorized_edits": events,
    }


def reset_guard_state() -> None:
    """Clear guard state. Intended for tests."""
    with _LOCK:
        _AUTHORIZED_WRITES.clear()
        _UNAUTHORIZED_EVENTS.clear()
