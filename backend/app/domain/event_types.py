from __future__ import annotations

import re
from typing import Any

UNKNOWN_EVENT = "UNKNOWN_EVENT"
RAW_REPORTED_EVENT = "RAW_REPORTED_EVENT"

SYSTEM_EVENT_TYPES = {UNKNOWN_EVENT, RAW_REPORTED_EVENT}


def canonical_event_type(value: Any, *, fallback: str = UNKNOWN_EVENT) -> str:
    text = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "").upper()).strip("_")
    return text or fallback


def is_unknown_event_type(event_type: str) -> bool:
    return canonical_event_type(event_type) in SYSTEM_EVENT_TYPES


def is_recovery_event_type(event_type: str) -> bool:
    normalized = canonical_event_type(event_type, fallback="")
    return normalized.endswith(("_UP", "_RECOVERED", "_RECOVERY", "_RESTORED", "_CLEAR", "_CLEARED"))


def event_status_from_type(event_type: str) -> str | None:
    normalized = canonical_event_type(event_type, fallback="")
    if normalized.endswith(("_UP", "_RECOVERED", "_RECOVERY", "_RESTORED", "_CLEAR", "_CLEARED")):
        return "up"
    if normalized.endswith(("_DOWN", "_FAILED", "_FAIL", "_LOST")):
        return "down"
    return None
