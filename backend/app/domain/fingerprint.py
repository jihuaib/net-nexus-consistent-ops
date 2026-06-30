from __future__ import annotations

import hashlib
import json
from typing import Any


def build_fault_fingerprint(facts: list[dict[str, Any]], topology: dict[str, Any]) -> dict[str, Any]:
    if not facts:
        raise ValueError("Cannot build fingerprint without facts")

    related_devices = sorted({fact["device_id"] for fact in facts})
    fact_signatures = sorted(
        [stable_fact_signature(fact) for fact in facts],
        key=lambda item: canonical_json(item),
    )

    payload = {
        "topology_id": topology.get("id"),
        "related_devices": related_devices,
        "fact_count": len(fact_signatures),
        "fact_types": sorted({fact["fact_type"] for fact in facts}),
        "observed_facts": fact_signatures,
    }

    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]
    return {
        "fingerprint": f"fp_{digest}",
        "payload": payload,
    }


def build_context_fingerprint(question_context: dict[str, Any], topology: dict[str, Any], state: str) -> dict[str, Any]:
    payload = {
        "topology_id": topology["id"],
        "state": state,
        "mentioned_nodes": [
            {
                "id": node["id"],
                "degree": node["degree"],
                "is_isolated": node["is_isolated"],
            }
            for node in question_context.get("mentioned_nodes", [])
        ],
        "mentioned_interfaces": question_context.get("mentioned_interfaces", []),
        "active_event_count": question_context.get("active_event_count", 0),
    }

    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:16]
    return {
        "fingerprint": f"fp_ctx_{digest}",
        "payload": payload,
    }


def stable_fact_signature(fact: dict[str, Any]) -> dict[str, Any]:
    return {
        "device_id": fact.get("device_id"),
        "scope": fact.get("scope"),
        "object": fact.get("object"),
        "fact_type": fact.get("fact_type"),
        "value": fact.get("value"),
        "severity": fact.get("severity"),
        "source": fact.get("source"),
        "context": stable_context(fact.get("context") or {}),
    }


def stable_context(context: dict[str, Any]) -> dict[str, Any]:
    volatile_keys = {"source_event_id", "event_id", "timestamp", "received_at"}
    return {
        str(key): value
        for key, value in sorted(context.items())
        if key not in volatile_keys and value not in (None, "")
    }


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
