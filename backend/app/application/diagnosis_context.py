from __future__ import annotations

from typing import Any


SEVERITY_PRIORITY = {
    "critical": 0,
    "major": 1,
    "warning": 2,
    "minor": 3,
    "info": 4,
}


def build_context_constraints(
    fault_case: dict[str, Any],
    facts: list[dict[str, Any]],
    question_context: dict[str, Any],
) -> dict[str, Any]:
    ordered_facts = dedupe_facts(sorted(facts, key=fact_sort_key))
    fact_types = [fact["fact_type"] for fact in ordered_facts]
    primary_signal = ordered_facts[0] if ordered_facts else None
    service_facts = [fact for fact in ordered_facts if fact.get("scope") == "service"]

    return {
        "context_id": "CTX-ENVIRONMENT",
        "context_name": "normalized_environment_context",
        "source": "system_context_builder",
        "is_deterministic": False,
        "fault_case_state": fault_case.get("state", "active_fault"),
        "primary_signal": compact_fact(primary_signal) if primary_signal else None,
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
            "系统不提供候选 fault_type 枚举，fault_type 由 LLM 基于证据生成",
            "证据不足时需要明确 need_more_data=true",
        ],
    }


def fact_sort_key(fact: dict[str, Any]) -> tuple[int, str, str, str, str]:
    severity = str(fact.get("severity") or "").lower()
    priority = SEVERITY_PRIORITY.get(severity, len(SEVERITY_PRIORITY))
    return (
        priority,
        str(fact.get("timestamp") or ""),
        str(fact.get("device_id") or ""),
        str(fact.get("object") or ""),
        str(fact.get("fact_id") or ""),
    )


def compact_fact(fact: dict[str, Any] | None) -> dict[str, Any] | None:
    if fact is None:
        return None
    compact = {
        "fact_id": fact.get("fact_id"),
        "fact_type": fact.get("fact_type"),
        "device_id": fact.get("device_id"),
        "object": fact.get("object"),
        "value": fact.get("value"),
        "source": fact.get("source"),
        "severity": fact.get("severity"),
    }
    if fact.get("context"):
        compact["context"] = fact["context"]
    return compact


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
    value = str(fact.get("value") or "").replace(",", "、")
    base = f"{fact.get('device_id')} {fact.get('object')} {fact.get('fact_type')}={value}".strip()
    context = context_suffix(fact)
    return f"{base}{context}"


def context_suffix(fact: dict[str, Any]) -> str:
    context = fact.get("context") or {}
    parts = [f"{key}={value}" for key, value in sorted(context.items()) if value not in (None, "")]
    if not parts:
        return ""
    return f"；context: {', '.join(parts)}"
