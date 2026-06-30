from __future__ import annotations

from typing import Any

from pyasn1.codec.ber import decoder
from pysnmp.proto import api

from ...domain.event_types import UNKNOWN_EVENT

SNMP_TRAP_OID = "1.3.6.1.6.3.1.1.4.1.0"
LINK_DOWN_OID = "1.3.6.1.6.3.1.1.5.3"
LINK_UP_OID = "1.3.6.1.6.3.1.1.5.4"
SYS_NAME_OID = "1.3.6.1.2.1.1.5.0"
IF_INDEX_PREFIX = "1.3.6.1.2.1.2.2.1.1."
IF_DESCR_PREFIX = "1.3.6.1.2.1.2.2.1.2."
IF_ADMIN_STATUS_PREFIX = "1.3.6.1.2.1.2.2.1.7."
IF_OPER_STATUS_PREFIX = "1.3.6.1.2.1.2.2.1.8."
IF_NAME_PREFIX = "1.3.6.1.2.1.31.1.1.1.1."

TRAP_STATE_BY_OID = {
    LINK_DOWN_OID: "down",
    LINK_UP_OID: "up",
}

TRAP_NAME_BY_OID = {
    LINK_DOWN_OID: "linkDown",
    LINK_UP_OID: "linkUp",
}

OPER_STATUS_BY_VALUE = {
    "1": "up",
    "2": "down",
    "3": "testing",
    "4": "unknown",
    "5": "dormant",
    "6": "notPresent",
    "7": "lowerLayerDown",
}


def decode_snmp_trap_packet(payload: bytes, *, source_ip: str | None = None) -> dict[str, Any] | None:
    if not payload:
        return None

    try:
        message, _ = decoder.decode(payload, asn1Spec=api.PROTOCOL_MODULES[api.SNMP_VERSION_2C].Message())
        version = int(api.PROTOCOL_MODULES[api.SNMP_VERSION_2C].apiMessage.get_version(message))
        protocol = api.PROTOCOL_MODULES[version]
        pdu = protocol.apiMessage.get_pdu(message)
    except Exception:
        return None

    if version == api.SNMP_VERSION_1:
        return decode_v1_trap(protocol, pdu, payload, source_ip=source_ip)
    return decode_v2_trap(protocol, pdu, payload, source_ip=source_ip)


def decode_v2_trap(protocol: Any, pdu: Any, payload: bytes, *, source_ip: str | None) -> dict[str, Any] | None:
    try:
        varbinds = [
            {"oid": oid.prettyPrint(), "value": value.prettyPrint(), "type": type(value).__name__}
            for oid, value in protocol.apiPDU.get_varbinds(pdu)
        ]
    except Exception:
        return None

    by_oid = {item["oid"]: item["value"] for item in varbinds}
    trap_oid = by_oid.get(SNMP_TRAP_OID)
    if not trap_oid:
        return generic_trap_payload(varbinds, payload, source_ip=source_ip)

    return trap_payload_from_varbinds(trap_oid, varbinds, payload, source_ip=source_ip)


def decode_v1_trap(protocol: Any, pdu: Any, payload: bytes, *, source_ip: str | None) -> dict[str, Any] | None:
    try:
        generic_trap = int(protocol.apiTrapPDU.get_generic_trap(pdu))
        varbinds = [
            {"oid": oid.prettyPrint(), "value": value.prettyPrint(), "type": type(value).__name__}
            for oid, value in protocol.apiTrapPDU.get_varbinds(pdu)
        ]
    except Exception:
        return None

    trap_oid = LINK_DOWN_OID if generic_trap == 2 else LINK_UP_OID if generic_trap == 3 else ""
    if trap_oid:
        return trap_payload_from_varbinds(trap_oid, varbinds, payload, source_ip=source_ip)
    return generic_trap_payload(varbinds, payload, source_ip=source_ip)


def trap_payload_from_varbinds(
    trap_oid: str,
    varbinds: list[dict[str, str]],
    payload: bytes,
    *,
    source_ip: str | None,
) -> dict[str, Any]:
    values = {item["oid"]: item["value"] for item in varbinds}
    if_index = first_suffix_value(values, IF_INDEX_PREFIX)
    if_name = first_suffix_value(values, IF_NAME_PREFIX) or first_suffix_value(values, IF_DESCR_PREFIX)
    if_oper_status = status_name(first_suffix_value(values, IF_OPER_STATUS_PREFIX))
    if_admin_status = status_name(first_suffix_value(values, IF_ADMIN_STATUS_PREFIX))
    device_id = values.get(SYS_NAME_OID) or source_ip or "unknown-device"
    trap_state = TRAP_STATE_BY_OID.get(trap_oid)
    event_type = event_type_from_oper_state(trap_state)
    trap_name = TRAP_NAME_BY_OID.get(trap_oid, trap_oid)
    interface = if_name or (f"ifIndex-{if_index}" if if_index else "unknown-interface")
    state = if_oper_status or trap_state or "unknown"

    return {
        "device_id": device_id,
        "event_type": event_type,
        "object": interface,
        "severity": "critical" if state == "down" else "info",
        "message": f"{device_id} SNMP Trap {trap_name} interface {interface} oper={state}",
        "raw": payload.hex(),
        "attributes": {
            "trap_oid": trap_oid,
            "trap_name": trap_name,
            "if_index": if_index,
            "if_name": if_name,
            "if_oper_status": if_oper_status,
            "if_admin_status": if_admin_status,
            "varbinds": varbinds,
            "decoder": "pysnmp-ber",
        },
    }


def generic_trap_payload(varbinds: list[dict[str, str]], payload: bytes, *, source_ip: str | None) -> dict[str, Any]:
    return {
        "device_id": source_ip or "unknown-device",
        "event_type": UNKNOWN_EVENT,
        "object": "snmp-trap",
        "severity": "info",
        "message": "SNMP Trap received",
        "raw": payload.hex(),
        "attributes": {
            "varbinds": varbinds,
            "decoder": "pysnmp-ber",
        },
    }


def first_suffix_value(values: dict[str, str], prefix: str) -> str | None:
    for oid, value in values.items():
        if oid.startswith(prefix):
            return value
    return None


def status_name(value: str | None) -> str | None:
    if value is None:
        return None
    return OPER_STATUS_BY_VALUE.get(str(value), str(value))


def event_type_from_oper_state(state: str | None) -> str:
    if state in {"down", "up"}:
        return f"INTERFACE_OPER_{state.upper()}"
    return UNKNOWN_EVENT
