from __future__ import annotations

from typing import Any


ALLOWED_FAULT_TYPES = [
    "INTERFACE_DOWN",
    "INTERFACE_DOWN_CAUSES_BGP_DOWN",
    "INTERFACE_DOWN_CAUSES_BGP_ROUTE_LOSS",
    "NO_ACTIVE_FAULT",
    "TOPOLOGY_CONTEXT_ISSUE",
    "UNKNOWN_NEED_MORE_DATA",
]

FACT_CHAIN_PRIORITY = [
    "INTERFACE_OPER_DOWN",
    "SYSLOG_LINK_DOWN",
    "TELEMETRY_TRAFFIC_ZERO",
    "BGP_NEIGHBOR_DOWN",
    "ROUTE_MISSING",
    "FIB_ENTRY_MISSING",
    "SERVICE_UNREACHABLE",
]


def build_context_constraints(
    fault_case: dict[str, Any],
    facts: list[dict[str, Any]],
    question_context: dict[str, Any],
) -> dict[str, Any]:
    ordered_facts = dedupe_facts(sorted(facts, key=fact_sort_key))
    fact_types = [fact["fact_type"] for fact in ordered_facts]
    primary_link_fact = select_primary_link_fact(ordered_facts)
    service_facts = [fact for fact in ordered_facts if fact["fact_type"] == "SERVICE_UNREACHABLE"]

    return {
        "context_id": "CTX-ENVIRONMENT",
        "context_name": "normalized_environment_context",
        "source": "system_context_builder",
        "is_deterministic": False,
        "fault_case_state": fault_case.get("state", "active_fault"),
        "candidate_fault_types": candidate_fault_types(ordered_facts, question_context),
        "primary_link_signal": compact_fact(primary_link_fact) if primary_link_fact else None,
        "fact_chain": [compact_fact(fact) for fact in ordered_facts],
        "fact_types": dedupe_strings(fact_types),
        "affected_devices": sorted({fact["device_id"] for fact in ordered_facts}),
        "affected_services": sorted({fact["object"] for fact in service_facts}),
        "evidence": dedupe_strings([format_fact_evidence(fact) for fact in ordered_facts]) or [
            "当前事件窗口内没有标准化故障 facts"
        ],
        "question_context": question_context,
        "instructions": [
            "这些内容是环境事实和一致性约束，不是规则诊断结论",
            "LLM 必须基于 facts、topology、question_context 和本约束自行判断 root_cause",
            "证据不足时需要明确 need_more_data=true",
        ],
    }


def candidate_fault_types(facts: list[dict[str, Any]], question_context: dict[str, Any]) -> list[str]:
    fact_types = {fact["fact_type"] for fact in facts}
    candidates = set()
    if {"INTERFACE_OPER_DOWN", "SYSLOG_LINK_DOWN"}.intersection(fact_types):
        candidates.add("INTERFACE_DOWN")
    if {"BGP_NEIGHBOR_DOWN"}.intersection(fact_types):
        candidates.add("INTERFACE_DOWN_CAUSES_BGP_DOWN")
    if {"ROUTE_MISSING", "FIB_ENTRY_MISSING", "SERVICE_UNREACHABLE"}.intersection(fact_types):
        candidates.add("INTERFACE_DOWN_CAUSES_BGP_ROUTE_LOSS")
    if not facts:
        candidates.add("NO_ACTIVE_FAULT")
    if any(node.get("is_isolated") for node in question_context.get("mentioned_nodes") or []):
        candidates.add("TOPOLOGY_CONTEXT_ISSUE")
    if not candidates or (facts and not {"INTERFACE_OPER_DOWN", "SYSLOG_LINK_DOWN"}.intersection(fact_types)):
        candidates.add("UNKNOWN_NEED_MORE_DATA")
    return [fault_type for fault_type in ALLOWED_FAULT_TYPES if fault_type in candidates]


def select_primary_link_fact(facts: list[dict[str, Any]]) -> dict[str, Any] | None:
    for fact in sorted(facts, key=fact_sort_key):
        if fact["fact_type"] in {"INTERFACE_OPER_DOWN", "SYSLOG_LINK_DOWN"}:
            return fact
    return None


def fact_sort_key(fact: dict[str, Any]) -> tuple[int, str, str, str]:
    fact_type = fact["fact_type"]
    priority = FACT_CHAIN_PRIORITY.index(fact_type) if fact_type in FACT_CHAIN_PRIORITY else len(FACT_CHAIN_PRIORITY)
    return priority, fact["device_id"], fact["object"], fact["fact_id"]


def compact_fact(fact: dict[str, Any] | None) -> dict[str, Any] | None:
    if fact is None:
        return None
    return {
        "fact_id": fact.get("fact_id"),
        "fact_type": fact.get("fact_type"),
        "device_id": fact.get("device_id"),
        "object": fact.get("object"),
        "value": fact.get("value"),
        "source": fact.get("source"),
        "severity": fact.get("severity"),
    }


def dedupe_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for fact in facts:
        marker = fact.get("fact_id")
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(fact)
    return deduped


def dedupe_strings(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def format_fact_evidence(fact: dict[str, Any]) -> str:
    fact_type = fact["fact_type"]
    if fact_type == "INTERFACE_OPER_DOWN":
        status = str(fact.get("value") or "oper=down").replace(",", "、")
        return f"{fact['device_id']} {fact['object']} {status}"
    if fact_type == "SYSLOG_LINK_DOWN":
        return f"{fact['device_id']} {fact['object']} Syslog 记录链路 Down"
    if fact_type == "TELEMETRY_TRAFFIC_ZERO":
        return f"{fact['device_id']} {fact['object']} 入/出方向流量为 0"
    if fact_type == "BGP_NEIGHBOR_DOWN":
        return f"{fact['device_id']} BGP 邻居 {fact['object']} 状态异常：{fact['value']}"
    if fact_type == "ROUTE_MISSING":
        return f"{fact['device_id']} 缺少路由 {fact['object']}"
    if fact_type == "FIB_ENTRY_MISSING":
        return f"{fact['device_id']} 缺少 FIB 表项 {fact['object']}"
    if fact_type == "SERVICE_UNREACHABLE":
        return f"{fact['device_id']} 业务 {fact['object']} 不可达：{fact['value']}"
    return f"{fact['device_id']} {fact['object']} {fact_type}={fact['value']}"
