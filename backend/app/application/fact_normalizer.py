from __future__ import annotations

from typing import Any

from ..domain.facts import Fact
from ..domain.event_types import UNKNOWN_EVENT


class FactNormalizer:
    def normalize_fault_case(self, fault_case: dict[str, Any]) -> list[dict[str, Any]]:
        if fault_case.get("state") == "no_active_fault":
            return []
        observations = fault_case.get("observations") or {}
        return self.normalize_reported_events(observations.get("reported_events") or [])

    def normalize_reported_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        facts = []
        for event in events:
            event_type = str(event.get("event_type") or UNKNOWN_EVENT)
            device_id = str(event.get("device_id") or "unknown-device")
            obj = str(event.get("object") or "unknown-object")
            attributes = dict(event.get("attributes") or {})
            context = compact_context(
                {
                    **attributes,
                    "channel": event.get("channel"),
                    "source_ip": event.get("source_ip"),
                    "source_event_id": event.get("event_id"),
                },
                sorted(
                    {
                        *attributes.keys(),
                        "channel",
                        "source_ip",
                        "source_event_id",
                    }
                ),
            )
            facts.append(
                Fact(
                    fact_id=_fact_id(device_id, obj, event_type),
                    device_id=device_id,
                    scope=str(attributes.get("scope") or event.get("channel") or "event"),
                    object=obj,
                    fact_type=event_type,
                    value=str(event.get("message") or event.get("raw") or event_type),
                    severity=str(event.get("severity") or "info"),
                    timestamp=str(event.get("timestamp") or event.get("received_at") or ""),
                    source=str(event.get("channel") or "reported_event"),
                    confidence=float(event.get("confidence", 0.8)),
                    context=context,
                )
            )
        return dedupe_facts([fact.to_dict() for fact in sorted(facts, key=lambda f: f.fact_id)])


def _fact_id(device_id: str, obj: str, fact_type: str) -> str:
    return f"{device_id}:{obj}:{fact_type}".replace(" ", "_")


def compact_context(item: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    context = {}
    for key in keys:
        value = item.get(key)
        if value is None or value == "":
            continue
        context[key] = value
    return context


def dedupe_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for fact in facts:
        marker = fact["fact_id"]
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(fact)
    return deduped
