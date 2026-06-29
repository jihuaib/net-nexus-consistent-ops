from __future__ import annotations

from copy import deepcopy
from typing import Any

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


PRIMARY_EVENT_PRIORITY = [
    "INTERFACE_OPER_DOWN",
    "BGP_NEIGHBOR_DOWN",
    "ROUTE_MISSING",
    "FIB_ENTRY_MISSING",
    "SERVICE_UNREACHABLE",
    "TELEMETRY_TRAFFIC_ZERO",
]

FAULT_EVENT_TYPES = set(PRIMARY_EVENT_PRIORITY)
RECOVERY_EVENT_TYPES = {
    "INTERFACE_OPER_UP",
}


def active_fault_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_recovery_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        if event.get("event_type") not in RECOVERY_EVENT_TYPES:
            continue
        key = event_correlation_key(event)
        if not key:
            continue
        current = latest_recovery_by_key.get(key)
        if current is None or event_time(event) >= event_time(current):
            latest_recovery_by_key[key] = event

    active = []
    for event in events:
        if event.get("event_type") not in FAULT_EVENT_TYPES:
            continue
        key = event_correlation_key(event)
        recovery = latest_recovery_by_key.get(key) if key else None
        if recovery and event_time(recovery) >= event_time(event):
            continue
        active.append(event)
    return active


def event_correlation_key(event: dict[str, Any]) -> tuple[str, str] | None:
    device_id = str(event.get("device_id") or "")
    event_type = event.get("event_type")
    attributes = event.get("attributes") or {}
    if not device_id:
        return None
    if event_type in {"INTERFACE_OPER_DOWN", "INTERFACE_OPER_UP", "TELEMETRY_TRAFFIC_ZERO"}:
        interface = str(event.get("object") or "")
    else:
        interface = str(attributes.get("depends_on_interface") or "")
    if not interface or interface in {"unknown-interface", "unknown-object"}:
        return None
    return device_id, interface


def event_time(event: dict[str, Any]):
    return parse_time(str(event.get("timestamp") or event.get("received_at") or ""))


def select_primary_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [event for event in events if event.get("event_type") in PRIMARY_EVENT_PRIORITY]
    if not candidates:
        return None

    def priority(event: dict[str, Any]) -> tuple[int, str, str, str]:
        event_type = event["event_type"]
        score = PRIMARY_EVENT_PRIORITY.index(event_type) if event_type in PRIMARY_EVENT_PRIORITY else len(PRIMARY_EVENT_PRIORITY)
        return score, event["timestamp"], event["device_id"], event["object"]

    return sorted(candidates, key=priority)[0]


def primary_from_event(event: dict[str, Any]) -> dict[str, Any]:
    attributes = event.get("attributes") or {}
    interface = event["object"] if event["event_type"] in {"INTERFACE_OPER_DOWN", "TELEMETRY_TRAFFIC_ZERO"} else attributes.get("depends_on_interface")
    return {
        "device_id": event["device_id"],
        "name": interface or event["object"],
        "event_type": event["event_type"],
        "source_event_id": event["event_id"],
        "source_channel": event["channel"],
    }


def is_same_fault_window(event: dict[str, Any], primary_event: dict[str, Any]) -> bool:
    if event.get("device_id") != primary_event.get("device_id"):
        return False
    primary_object = primary_event.get("object")
    primary_attributes = primary_event.get("attributes") or {}
    primary_interface = primary_object if primary_event.get("event_type") in {"INTERFACE_OPER_DOWN", "TELEMETRY_TRAFFIC_ZERO"} else primary_attributes.get("depends_on_interface")
    attributes = event.get("attributes") or {}
    depends_on = attributes.get("depends_on_interface")
    if depends_on and primary_interface:
        return depends_on == primary_interface
    return True


def observations_from_events(
    events: list[dict[str, Any]],
    *,
    primary: dict[str, Any] | None = None,
    topology: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    observations = empty_observations()
    primary_interface = (primary or {}).get("name")

    for event in events:
        event_type = event["event_type"]
        device_id = event["device_id"]
        obj = event["object"]
        source = event["channel"]
        attributes = event.get("attributes") or {}

        if event_type == "INTERFACE_OPER_DOWN":
            if source == "syslog":
                observations["syslogs"].append(syslog_observation(event))
            else:
                observations["interfaces"].append(
                    {
                        "device_id": device_id,
                        "name": obj,
                        "description": event.get("message") or "",
                        "admin_status": attributes.get("admin_status", "unknown"),
                        "oper_status": "down",
                        "channel": source,
                        "source": source,
                    }
                )
        elif event_type == "TELEMETRY_TRAFFIC_ZERO":
            observations["interfaces"].append(
                {
                    "device_id": device_id,
                    "name": obj if obj != "unknown-object" else primary_interface,
                    "description": event.get("message") or "",
                    "admin_status": "unknown",
                    "oper_status": "unknown",
                    "in_bps": 0,
                    "out_bps": 0,
                    "channel": source,
                    "source": source,
                }
            )
        elif event_type == "BGP_NEIGHBOR_DOWN":
            observations["bgp_neighbors"].append(
                {
                    "device_id": device_id,
                    "peer": obj,
                    "remote_device": attributes.get("remote_device", obj),
                    "remote_interface": attributes.get("remote_interface"),
                    "state": attributes.get("state", "down"),
                    "severity": event["severity"],
                    "source": source,
                    "depends_on_interface": attributes.get("depends_on_interface") or primary_interface,
                    "confidence": event["confidence"],
                }
            )
        elif event_type == "ROUTE_MISSING":
            observations["routes"].append(
                {
                    "device_id": device_id,
                    "prefix": obj,
                    "next_hop": attributes.get("next_hop", "unknown"),
                    "status": "missing",
                    "severity": event["severity"],
                    "source": source,
                    "depends_on_interface": attributes.get("depends_on_interface") or primary_interface,
                    "confidence": event["confidence"],
                }
            )
        elif event_type == "FIB_ENTRY_MISSING":
            observations["fib_entries"].append(
                {
                    "device_id": device_id,
                    "prefix": obj,
                    "next_hop": attributes.get("next_hop", "unknown"),
                    "status": "missing",
                    "severity": event["severity"],
                    "source": source,
                    "depends_on_interface": attributes.get("depends_on_interface") or primary_interface,
                    "confidence": event["confidence"],
                }
            )
        elif event_type == "SERVICE_UNREACHABLE":
            observations["service_checks"].append(
                {
                    "device_id": device_id,
                    "service": obj,
                    "target": attributes.get("target", obj),
                    "status": "unreachable",
                    "severity": event["severity"],
                    "source": source,
                    "depends_on_interface": attributes.get("depends_on_interface") or primary_interface,
                }
            )

    return dedupe_observations(observations)


def is_related_event(event: dict[str, Any], *, device_id: str, interface: str) -> bool:
    if event.get("device_id") != device_id:
        return False
    event_type = event.get("event_type")
    obj = event.get("object")
    attributes = event.get("attributes") or {}
    if event_type in {"INTERFACE_OPER_DOWN", "TELEMETRY_TRAFFIC_ZERO"}:
        return obj in {interface, "unknown-interface", "unknown-object"}
    depends_on = attributes.get("depends_on_interface")
    return depends_on in {None, "", interface} or event_type in {
        "BGP_NEIGHBOR_DOWN",
        "ROUTE_MISSING",
        "FIB_ENTRY_MISSING",
        "SERVICE_UNREACHABLE",
    }


def syslog_observation(event: dict[str, Any]) -> dict[str, Any]:
    interface = event.get("object") or "unknown-interface"
    message = event.get("message") or f"Interface {interface} changed state to DOWN"
    if "Interface " not in message:
        message = f"Interface {interface} {message}"
    return {
        "device_id": event["device_id"],
        "message": message,
        "severity": event["severity"],
        "source": event["channel"],
    }


def dedupe_observations(observations: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    deduped = {}
    for key, rows in observations.items():
        seen = set()
        result = []
        for row in rows:
            marker = tuple(sorted((str(item_key), str(item_value)) for item_key, item_value in row.items()))
            if marker in seen:
                continue
            seen.add(marker)
            result.append(deepcopy(row))
        deduped[key] = result
    return deduped


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
