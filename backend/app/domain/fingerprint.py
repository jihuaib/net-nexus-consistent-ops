from __future__ import annotations

import hashlib
import json
from typing import Any

PRIMARY_PRIORITY = [
    "INTERFACE_OPER_DOWN",
    "SYSLOG_LINK_DOWN",
    "TELEMETRY_TRAFFIC_ZERO",
    "BGP_NEIGHBOR_DOWN",
    "ROUTE_MISSING",
    "FIB_ENTRY_MISSING",
    "SERVICE_UNREACHABLE",
]


def build_fault_fingerprint(facts: list[dict[str, Any]], topology: dict[str, Any]) -> dict[str, Any]:
    primary = select_primary_fact(facts)
    key_facts = sorted({fact["fact_type"] for fact in facts})
    related_devices = sorted({fact["device_id"] for fact in facts})

    payload = {
        "topology_id": topology["id"],
        "primary_device": primary["device_id"],
        "primary_object": primary["object"],
        "normalized_fault_type": normalize_fault_type(primary["fact_type"]),
        "related_devices": related_devices,
        "key_facts": key_facts,
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


def select_primary_fact(facts: list[dict[str, Any]]) -> dict[str, Any]:
    if not facts:
        raise ValueError("Cannot build fingerprint without facts")

    def priority(fact: dict[str, Any]) -> tuple[int, str, str]:
        fact_type = fact["fact_type"]
        score = PRIMARY_PRIORITY.index(fact_type) if fact_type in PRIMARY_PRIORITY else len(PRIMARY_PRIORITY)
        return score, fact["device_id"], fact["object"]

    return sorted(facts, key=priority)[0]


def normalize_fault_type(fact_type: str) -> str:
    if fact_type in {"INTERFACE_OPER_DOWN", "SYSLOG_LINK_DOWN"}:
        return "INTERFACE_DOWN"
    if fact_type == "BGP_NEIGHBOR_DOWN":
        return "BGP_NEIGHBOR_DOWN"
    if fact_type in {"ROUTE_MISSING", "FIB_ENTRY_MISSING"}:
        return "ROUTE_FORWARDING_LOSS"
    return fact_type


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
