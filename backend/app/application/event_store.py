from __future__ import annotations

from collections.abc import Callable
from collections import deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any

from ..domain.events import ReportedEvent


class EventStore:
    def __init__(self, max_events: int = 5000) -> None:
        self._events: deque[ReportedEvent] = deque(maxlen=max_events)
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._lock = RLock()

    def append(self, event: ReportedEvent) -> dict[str, Any]:
        with self._lock:
            self._events.append(event)
            event_data = event.to_dict()
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(deepcopy(event_data))
            except Exception:
                continue
        return deepcopy(event_data)

    def add_listener(self, listener: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def list_events(
        self,
        *,
        limit: int = 200,
        channel: str | None = None,
        event_type: str | None = None,
        device_id: str | None = None,
        since_seconds: int | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 1000))
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=since_seconds) if since_seconds else None
        with self._lock:
            events = list(self._events)

        filtered = []
        for event in reversed(events):
            if channel and event.channel != channel:
                continue
            if event_type and event.event_type != event_type:
                continue
            if device_id and event.device_id != device_id:
                continue
            if cutoff and parse_time(event.timestamp) < cutoff:
                continue
            filtered.append(event.to_dict())
            if len(filtered) >= limit:
                break
        return deepcopy(filtered)

    def recent_events(self, *, window_seconds: int = 300, device_id: str | None = None) -> list[dict[str, Any]]:
        return list(reversed(self.list_events(limit=1000, device_id=device_id, since_seconds=window_seconds)))

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    def summary(self) -> dict[str, Any]:
        with self._lock:
            events = list(self._events)
        by_channel: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for event in events:
            by_channel[event.channel] = by_channel.get(event.channel, 0) + 1
            by_type[event.event_type] = by_type.get(event.event_type, 0) + 1
        return {
            "total": len(events),
            "by_channel": by_channel,
            "by_type": by_type,
            "latest": events[-1].to_dict() if events else None,
        }


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
