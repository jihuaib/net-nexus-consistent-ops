from __future__ import annotations

from typing import Any

from ..domain.event_types import is_recovery_event_type, is_unknown_event_type
from .event_store import EventStore, parse_time


class CorrelationEngine:
    def __init__(self, event_store: EventStore, window_seconds: int = 300) -> None:
        self._event_store = event_store
        self._window_seconds = window_seconds

    def correlate_for_fault(
        self,
        *,
        topology: dict[str, Any],
        primary: dict[str, Any],
        window_seconds: int | None = None,
    ) -> dict[str, Any]:
        device_id = primary["device_id"]
        interface = primary["name"]
        events = self._event_store.recent_events(
            window_seconds=window_seconds or self._window_seconds,
            device_id=device_id,
        )
        related_events = [
            event
            for event in events
            if is_related_event(event, device_id=device_id, interface=interface)
        ]
        observations = observations_from_events(related_events, primary=primary, topology=topology)
        return {
            "window_seconds": window_seconds or self._window_seconds,
            "events": related_events,
            "observations": observations,
            "summary": summarize_correlation(related_events, observations),
        }

    def correlate_current_fault(
        self,
        *,
        topology: dict[str, Any],
        window_seconds: int | None = None,
    ) -> dict[str, Any]:
        events = self._event_store.recent_events(window_seconds=window_seconds or self._window_seconds)
        if not events:
            return {
                "window_seconds": window_seconds or self._window_seconds,
                "primary": None,
                "events": [],
                "observations": empty_observations(),
                "summary": summarize_correlation([], empty_observations()),
            }

        active_events = active_fault_events(events)
        primary_event = select_primary_event(active_events)
        if not primary_event:
            return {
                "window_seconds": window_seconds or self._window_seconds,
                "primary": None,
                "events": events,
                "observations": empty_observations(),
                "summary": summarize_correlation(events, empty_observations()),
            }
        primary = primary_from_event(primary_event)
        related_events = [
            event
            for event in active_events
            if is_same_fault_window(event, primary_event)
        ]
        observations = observations_from_events(related_events, primary=primary, topology=topology)
        return {
            "window_seconds": window_seconds or self._window_seconds,
            "primary": primary,
            "events": related_events,
            "observations": observations,
            "summary": summarize_correlation(related_events, observations),
        }

    def preview(self, *, device_id: str | None = None, window_seconds: int | None = None) -> dict[str, Any]:
        events = self._event_store.recent_events(
            window_seconds=window_seconds or self._window_seconds,
            device_id=device_id,
        )
        return {
            "window_seconds": window_seconds or self._window_seconds,
            "event_count": len(events),
            "events": events,
            "summary": summarize_events(events),
        }


def empty_observations() -> dict[str, list[dict[str, Any]]]:
    return {
        "interfaces": [],
        "syslogs": [],
        "bgp_neighbors": [],
        "routes": [],
        "fib_entries": [],
        "service_checks": [],
    }


EVENT_SEVERITY_PRIORITY = {
    "critical": 0,
    "major": 1,
    "warning": 2,
    "minor": 3,
    "info": 4,
}


def active_fault_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_recovery_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        if not is_recovery_event(event):
            continue
        key = event_correlation_key(event)
        if not key:
            continue
        current = latest_recovery_by_key.get(key)
        if current is None or event_time(event) >= event_time(current):
            latest_recovery_by_key[key] = event

    active = []
    for event in events:
        if not is_fault_event(event):
            continue
        key = event_correlation_key(event)
        recovery = latest_recovery_by_key.get(key) if key else None
        if recovery and event_time(recovery) >= event_time(event):
            continue
        active.append(event)
    return active


def is_recovery_event(event: dict[str, Any]) -> bool:
    event_type = str(event.get("event_type") or "")
    attributes = event.get("attributes") or {}
    return bool(attributes.get("recovery")) or is_recovery_event_type(event_type)


def is_fault_event(event: dict[str, Any]) -> bool:
    if is_recovery_event(event):
        return False
    if is_unknown_event_type(str(event.get("event_type") or "")):
        return False
    return str(event.get("severity") or "").lower() != "info"


def event_correlation_key(event: dict[str, Any]) -> tuple[str, str] | None:
    device_id = str(event.get("device_id") or "")
    if not device_id:
        return None
    anchor = first_event_anchor(event)
    if not anchor:
        return None
    return device_id, anchor


def event_time(event: dict[str, Any]):
    return parse_time(str(event.get("timestamp") or event.get("received_at") or ""))


def select_primary_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [event for event in events if is_fault_event(event)]
    if not candidates:
        return None

    def priority(event: dict[str, Any]) -> tuple[int, str, str, str]:
        severity = str(event.get("severity") or "").lower()
        score = EVENT_SEVERITY_PRIORITY.get(severity, len(EVENT_SEVERITY_PRIORITY))
        return score, event["timestamp"], event["device_id"], event["object"]

    return sorted(candidates, key=priority)[0]


def primary_from_event(event: dict[str, Any]) -> dict[str, Any]:
    anchor = first_event_anchor(event) or event["object"]
    return {
        "device_id": event["device_id"],
        "name": anchor,
        "event_type": event["event_type"],
        "source_event_id": event["event_id"],
        "source_channel": event["channel"],
    }


def is_same_fault_window(event: dict[str, Any], primary_event: dict[str, Any]) -> bool:
    if event.get("device_id") != primary_event.get("device_id"):
        return False
    primary_anchors = event_anchor_values(primary_event)
    anchors = event_anchor_values(event)
    if not primary_anchors or not anchors:
        return True
    return bool(primary_anchors.intersection(anchors))


def observations_from_events(
    events: list[dict[str, Any]],
    *,
    primary: dict[str, Any] | None = None,
    topology: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    return empty_observations()


def is_related_event(event: dict[str, Any], *, device_id: str, interface: str) -> bool:
    if event.get("device_id") != device_id:
        return False
    anchors = event_anchor_values(event)
    return not anchors or interface in anchors


def first_event_anchor(event: dict[str, Any]) -> str | None:
    attributes = event.get("attributes") or {}
    for value in [
        attributes.get("depends_on_interface"),
        attributes.get("interface"),
        attributes.get("if_name"),
        attributes.get("ifName"),
        attributes.get("normalized_object"),
        event.get("object"),
    ]:
        anchor = clean_anchor(value)
        if anchor:
            return anchor
    return None


def event_anchor_values(event: dict[str, Any]) -> set[str]:
    attributes = event.get("attributes") or {}
    values = [
        attributes.get("depends_on_interface"),
        attributes.get("interface"),
        attributes.get("if_name"),
        attributes.get("ifName"),
        attributes.get("normalized_object"),
        event.get("object"),
    ]
    anchors: set[str] = set()
    for value in values:
        anchor = clean_anchor(value)
        if anchor:
            anchors.add(anchor)
    return anchors


def clean_anchor(value: Any) -> str | None:
    anchor = str(value or "").strip()
    return anchor if anchor and anchor not in {"unknown-interface", "unknown-object"} else None


def summarize_correlation(events: list[dict[str, Any]], observations: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "event_count": len(events),
        "fact_source_counts": {key: len(value) for key, value in observations.items()},
        "event_types": sorted({event["event_type"] for event in events}),
        "channels": sorted({event["channel"] for event in events}),
    }


def summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    by_channel: dict[str, int] = {}
    by_device: dict[str, int] = {}
    for event in events:
        by_type[event["event_type"]] = by_type.get(event["event_type"], 0) + 1
        by_channel[event["channel"]] = by_channel.get(event["channel"], 0) + 1
        by_device[event["device_id"]] = by_device.get(event["device_id"], 0) + 1
    return {
        "by_type": by_type,
        "by_channel": by_channel,
        "by_device": by_device,
    }
