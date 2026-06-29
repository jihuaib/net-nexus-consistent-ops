from __future__ import annotations

from typing import Any

from ..domain.facts import Fact


class FactNormalizer:
    def normalize_fault_case(self, fault_case: dict[str, Any]) -> list[dict[str, Any]]:
        observations = fault_case["observations"]
        timestamp = observations["timestamp"]
        facts: list[Fact] = []

        for item in observations.get("interfaces", []):
            device_id = item["device_id"]
            interface = item["name"]
            if item.get("oper_status") == "down":
                admin_status = item.get("admin_status", "unknown")
                oper_status = item.get("oper_status", "unknown")
                facts.append(
                    Fact(
                        fact_id=_fact_id(device_id, interface, "INTERFACE_OPER_DOWN"),
                        device_id=device_id,
                        scope="interface",
                        object=interface,
                        fact_type="INTERFACE_OPER_DOWN",
                        value=f"admin={admin_status},oper={oper_status}",
                        severity="critical",
                        timestamp=timestamp,
                        source=item.get("source", "interface"),
                        confidence=1.0,
                    )
                )

            if item.get("in_bps") == 0 and item.get("out_bps") == 0:
                facts.append(
                    Fact(
                        fact_id=_fact_id(device_id, interface, "TELEMETRY_TRAFFIC_ZERO"),
                        device_id=device_id,
                        scope="interface",
                        object=interface,
                        fact_type="TELEMETRY_TRAFFIC_ZERO",
                        value="0bps",
                        severity="major",
                        timestamp=timestamp,
                        source=item.get("source", "telemetry"),
                        confidence=0.9,
                    )
                )

        for item in observations.get("syslogs", []):
            message = item["message"]
            interface = _extract_interface_from_syslog(message)
            if "DOWN" in message.upper() and interface:
                facts.append(
                    Fact(
                        fact_id=_fact_id(item["device_id"], interface, "SYSLOG_LINK_DOWN"),
                        device_id=item["device_id"],
                        scope="interface",
                        object=interface,
                        fact_type="SYSLOG_LINK_DOWN",
                        value=message,
                        severity=item.get("severity", "critical"),
                        timestamp=timestamp,
                        source=item.get("source", "syslog"),
                        confidence=0.95,
                    )
                )

        for item in observations.get("bgp_neighbors", []):
            state = str(item.get("state") or "unknown").lower()
            if state not in {"established", "up"}:
                peer = str(item.get("peer") or item.get("remote_device") or "unknown-peer")
                facts.append(
                    Fact(
                        fact_id=_fact_id(item["device_id"], peer, "BGP_NEIGHBOR_DOWN"),
                        device_id=item["device_id"],
                        scope="routing_protocol",
                        object=peer,
                        fact_type="BGP_NEIGHBOR_DOWN",
                        value=f"state={item.get('state', 'unknown')},remote_device={item.get('remote_device', 'unknown')}",
                        severity=item.get("severity", "critical"),
                        timestamp=timestamp,
                        source=item.get("source", "bgp"),
                        confidence=float(item.get("confidence", 0.95)),
                    )
                )

        for item in observations.get("routes", []):
            if item.get("status") == "missing":
                prefix = str(item.get("prefix") or item.get("target") or "unknown-prefix")
                facts.append(
                    Fact(
                        fact_id=_fact_id(item["device_id"], prefix, "ROUTE_MISSING"),
                        device_id=item["device_id"],
                        scope="routing",
                        object=prefix,
                        fact_type="ROUTE_MISSING",
                        value=f"status=missing,next_hop={item.get('next_hop', 'unknown')}",
                        severity=item.get("severity", "major"),
                        timestamp=timestamp,
                        source=item.get("source", "routing-table"),
                        confidence=float(item.get("confidence", 0.9)),
                    )
                )

        for item in observations.get("fib_entries", []):
            if item.get("status") == "missing":
                prefix = str(item.get("prefix") or item.get("target") or "unknown-prefix")
                facts.append(
                    Fact(
                        fact_id=_fact_id(item["device_id"], prefix, "FIB_ENTRY_MISSING"),
                        device_id=item["device_id"],
                        scope="forwarding",
                        object=prefix,
                        fact_type="FIB_ENTRY_MISSING",
                        value=f"status=missing,next_hop={item.get('next_hop', 'unknown')}",
                        severity=item.get("severity", "major"),
                        timestamp=timestamp,
                        source=item.get("source", "fib"),
                        confidence=float(item.get("confidence", 0.9)),
                    )
                )

        for item in observations.get("service_checks", []):
            if item.get("status") == "unreachable":
                facts.append(
                    Fact(
                        fact_id=_fact_id(item["device_id"], item["service"], "SERVICE_UNREACHABLE"),
                        device_id=item["device_id"],
                        scope="service",
                        object=item["service"],
                        fact_type="SERVICE_UNREACHABLE",
                        value=item["target"],
                        severity="major",
                        timestamp=timestamp,
                        source=item.get("source", "probe"),
                        confidence=0.85,
                    )
                )

        return dedupe_facts([fact.to_dict() for fact in sorted(facts, key=lambda f: f.fact_id)])


def _fact_id(device_id: str, obj: str, fact_type: str) -> str:
    return f"{device_id}:{obj}:{fact_type}".replace(" ", "_")


def _extract_interface_from_syslog(message: str) -> str | None:
    marker = "Interface "
    if marker not in message:
        return None
    return message.split(marker, 1)[1].split(" ", 1)[0].strip()


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
