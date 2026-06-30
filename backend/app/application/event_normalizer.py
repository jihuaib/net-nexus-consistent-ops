from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..domain.events import ReportedEvent
from ..domain.event_types import (
    RAW_REPORTED_EVENT,
    UNKNOWN_EVENT,
    canonical_event_type,
    event_status_from_type,
    is_recovery_event_type,
    is_unknown_event_type,
)

SYSLOG_PROGRAM_NAMES = {
    "bgpd",
    "zebra",
    "staticd",
    "watchfrr",
    "snmpd",
    "lldpd",
    "netnexus-link-event",
}


def normalize_reported_event(
    *,
    channel: str,
    payload: dict[str, Any] | None = None,
    raw: str = "",
    source_ip: str | None = None,
) -> ReportedEvent:
    payload = payload or parse_payload(raw)
    message = str(payload.get("message") or payload.get("raw") or raw or "").strip()
    if source_ip and not payload.get("source_ip"):
        payload = {**payload, "source_ip": source_ip}
    payload = merge_message_fields(payload, message)
    timestamp = normalize_timestamp(payload.get("timestamp"))
    event_type = normalize_event_type(payload.get("event_type") or payload.get("event"), message, payload)
    device_id = normalize_device_id(payload, message)
    obj = normalize_object(payload, message, event_type)
    severity = normalize_severity(str(payload.get("severity") or ""), event_type, message)
    confidence = normalize_confidence(payload.get("confidence"), channel, event_type)
    attributes = normalize_attributes(payload, event_type, obj)

    return ReportedEvent(
        event_id=str(payload.get("event_id") or f"evt_{uuid4().hex[:12]}"),
        received_at=datetime.now(timezone.utc).isoformat(),
        timestamp=timestamp,
        channel=channel,
        source_ip=source_ip or payload.get("source_ip"),
        device_id=device_id,
        event_type=event_type,
        object=obj,
        severity=severity,
        message=message or event_type,
        raw=raw or str(payload.get("raw") or message),
        attributes=attributes,
        confidence=confidence,
    )


def parse_payload(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"message": text, "raw": text}
    return payload if isinstance(payload, dict) else {"message": text, "raw": text}


def normalize_timestamp(value: Any) -> str:
    if value:
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).isoformat()


def normalize_event_type(value: Any, message: str, payload: dict[str, Any]) -> str:
    if value:
        return canonical_event_type(value)
    if message or payload:
        return RAW_REPORTED_EVENT
    return UNKNOWN_EVENT


def normalize_device_id(payload: dict[str, Any], message: str) -> str:
    for key in ["device_id", "hostname", "host", "device", "sys_name"]:
        value = payload.get(key)
        if value:
            return str(value).strip()

    text = strip_syslog_priority(message)
    syslog_host = extract_syslog_hostname(text)
    if syslog_host:
        return syslog_host
    match = re.search(r"\b(spine-\d+|leaf-\d+)\b", text)
    if match:
        return match.group(1)
    source_ip = payload.get("source_ip")
    return str(source_ip).strip() if source_ip else "unknown-device"


def normalize_object(payload: dict[str, Any], message: str, event_type: str) -> str:
    return (
        first_present(
            payload,
            [
                "object",
                "normalized_object",
                "interface",
                "if_name",
                "ifName",
                "name",
                "peer",
                "neighbor",
                "remote_device",
                "remote_peer",
                "prefix",
                "route",
                "destination",
                "service",
                "probe",
                "target",
            ],
        )
        or "unknown-object"
    )


def normalize_severity(value: str, event_type: str, message: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"critical", "major", "minor", "warning", "info"}:
        return normalized
    if is_unknown_event_type(event_type) or is_recovery_event_type(event_type):
        return "info"
    if event_status_from_type(event_type) == "up":
        return "info"
    return "major"


def normalize_confidence(value: Any, channel: str, event_type: str) -> float:
    try:
        confidence = float(value)
        return max(0.0, min(confidence, 1.0))
    except (TypeError, ValueError):
        pass
    if event_type in {UNKNOWN_EVENT, RAW_REPORTED_EVENT}:
        return 0.3
    if channel == "snmp_trap":
        return 0.95
    if channel == "syslog":
        return 0.9
    return 0.85


def normalize_attributes(payload: dict[str, Any], event_type: str, obj: str) -> dict[str, Any]:
    attributes = dict(payload.get("attributes") or {})
    for key in [
        "peer",
        "remote_device",
        "remote_interface",
        "next_hop",
        "prefix",
        "target",
        "oid",
        "varbinds",
        "trap_oid",
        "trap_name",
        "if_index",
        "if_name",
        "if_oper_status",
        "if_admin_status",
        "syslog_host",
        "syslog_program",
        "syslog_pid",
        "frr_code",
        "vrf",
        "afi",
    ]:
        if key in payload and key not in attributes:
            attributes[key] = payload[key]
    attributes.setdefault("normalized_object", obj)
    attributes.setdefault("normalized_event_type", event_type)
    return attributes


def first_present(payload: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value).strip()
    return None


def strip_syslog_priority(message: str) -> str:
    return re.sub(r"^<\d+>", "", message or "").strip()


def merge_message_fields(payload: dict[str, Any], message: str) -> dict[str, Any]:
    fields = parse_key_values(message)
    fields.update(parse_syslog_metadata(message))
    if not fields:
        return payload
    merged = dict(fields)
    merged.update(payload)
    return merged


def parse_key_values(message: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, value in re.findall(r"\b([A-Za-z_][A-Za-z0-9_-]*)=([^,\s]+)", message or ""):
        fields[key] = value.strip('"')
    return fields


def parse_syslog_metadata(message: str) -> dict[str, str]:
    text = strip_syslog_priority(message)
    metadata: dict[str, str] = {}
    header = parse_syslog_header(text)
    if header.get("host"):
        metadata["syslog_host"] = header["host"]
    if header.get("program"):
        metadata["syslog_program"] = header["program"]
    if header.get("pid"):
        metadata["syslog_pid"] = header["pid"]
    code_match = re.search(r"\[([A-Z0-9]+-[A-Z0-9]+)\]", text)
    if code_match:
        metadata["frr_code"] = code_match.group(1)
    afi_match = re.search(r"for\s+([A-Za-z0-9 ]+)\s+from\b", text)
    if afi_match:
        metadata["afi"] = " ".join(afi_match.group(1).split())
    vrf_match = re.search(r"\bin\s+vrf\s+([A-Za-z0-9_.:-]+)", text)
    if vrf_match:
        metadata["vrf"] = vrf_match.group(1)
    return metadata


def extract_syslog_hostname(message: str) -> str | None:
    return parse_syslog_header(message).get("host")


def parse_syslog_header(message: str) -> dict[str, str]:
    match = re.match(
        r"^[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+"
        r"(?:(?P<host>[A-Za-z0-9_.-]+)\s+)?"
        r"(?P<program>[A-Za-z0-9_.-]+)(?:\[(?P<pid>\d+)\])?:",
        message or "",
    )
    if not match:
        return {}
    result = {key: value for key, value in match.groupdict().items() if value}
    if result.get("host") and result["host"] in SYSLOG_PROGRAM_NAMES:
        result["program"] = result.pop("host")
    return result


def extract_interface(message: str) -> str:
    patterns = [
        r"\bInterface\s+([A-Za-z0-9/_:.-]+)",
        r"\binterface[=\s]+([A-Za-z0-9/_:.-]+)",
        r"\bifName[=\s]+([A-Za-z0-9/_:.-]+)",
        r"\bif_name[=\s]+([A-Za-z0-9/_:.-]+)",
        r"\blink\s+([A-Za-z0-9/_:.-]+)\s+down",
        r"\blink\s+([A-Za-z0-9/_:.-]+)\s+up",
    ]
    return extract_first(message, patterns, "unknown-interface")


def extract_peer(message: str) -> str:
    patterns = [
        r"\bpeer[=\s]+([A-Za-z0-9/_:.-]+)",
        r"\bneighbor[=\s]+([A-Za-z0-9/_:.-]+)",
        r"\bBGP\s+(?:peer|neighbor)\s+([A-Za-z0-9/_:.-]+)",
        r"\bfrom\s+([A-Za-z0-9/_:.-]+)",
    ]
    return extract_first(message, patterns, "unknown-peer")


def extract_prefix(message: str) -> str:
    return extract_first(message, [r"\b(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\b"], "unknown-prefix")


def extract_first(message: str, patterns: list[str], fallback: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, message or "", re.IGNORECASE)
        if match:
            return match.group(1).strip(" ,;")
    return fallback
