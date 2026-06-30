from __future__ import annotations

from dataclasses import replace
import re
from typing import Any

from ..domain.event_types import RAW_REPORTED_EVENT, UNKNOWN_EVENT, is_unknown_event_type
from ..domain.events import ReportedEvent
from ..infrastructure.llm.base import LLMClient, LLMConfigurationError, LLMResponseError


EVENT_EXTRACTION_PROMPT = """你是一名网络运维事件抽取器。请从原始上报事件中抽取结构化事件字段。

要求：
1. 只做信息抽取，不做根因诊断。
2. 如果原文不足以确定事件类型，返回 extractable=false。
3. event_type 不依赖后端枚举；请基于原文生成稳定、简短、可机器读取的英文大写标识。
4. object 填写事件直接作用对象，例如接口名、邻居、前缀、服务名；无法确定时使用原始 object。
5. severity 只能是 critical、major、warning、minor、info。
6. confidence 取 0 到 1。
7. attributes 只放原文能支持的结构化字段，例如 depends_on_interface、peer、prefix、next_hop、target、state。

输出 JSON：
{
  "extractable": true,
  "event_type": "STRING",
  "object": "STRING",
  "severity": "critical",
  "confidence": 0.0,
  "attributes": {},
  "evidence": "STRING",
  "reason": "STRING"
}
"""


class EventExtractionService:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def extract(self, event: ReportedEvent) -> ReportedEvent:
        if not is_unknown_event_type(event.event_type):
            return event
        if not self._llm_client.metadata().get("configured"):
            return event
        try:
            extracted = self._llm_client.complete_json(EVENT_EXTRACTION_PROMPT, {"event": event.to_dict()})
        except (LLMConfigurationError, LLMResponseError):
            return event
        return apply_extraction(event, extracted)


def apply_extraction(event: ReportedEvent, extracted: dict[str, Any]) -> ReportedEvent:
    if not extracted.get("extractable"):
        return annotate_extraction(event, extracted, status="not_extractable")

    event_type = normalize_event_type(extracted.get("event_type"))
    if event_type in {RAW_REPORTED_EVENT, UNKNOWN_EVENT}:
        return annotate_extraction(event, extracted, status="invalid_event_type")

    severity = normalize_severity(extracted.get("severity"), fallback=event.severity)
    attributes = dict(event.attributes or {})
    extracted_attributes = extracted.get("attributes")
    if isinstance(extracted_attributes, dict):
        attributes.update({str(key): value for key, value in extracted_attributes.items() if value not in (None, "")})
    extracted_object = clean_text(extracted.get("object")) or event.object
    attributes["normalized_object"] = extracted_object
    attributes["normalized_event_type"] = event_type
    attributes["ai_extraction"] = {
        "status": "applied",
        "previous_event_type": event.event_type,
        "evidence": clean_text(extracted.get("evidence")),
        "reason": clean_text(extracted.get("reason")),
    }

    return replace(
        event,
        event_type=event_type,
        object=extracted_object,
        severity=severity,
        confidence=normalize_confidence(extracted.get("confidence"), fallback=event.confidence),
        attributes=attributes,
    )


def annotate_extraction(event: ReportedEvent, extracted: dict[str, Any], *, status: str) -> ReportedEvent:
    attributes = dict(event.attributes or {})
    attributes["ai_extraction"] = {
        "status": status,
        "evidence": clean_text(extracted.get("evidence")),
        "reason": clean_text(extracted.get("reason")),
    }
    return replace(event, attributes=attributes)


def normalize_event_type(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_]+", "_", clean_text(value).upper()).strip("_")
    return text or UNKNOWN_EVENT


def normalize_severity(value: Any, *, fallback: str) -> str:
    severity = clean_text(value).lower()
    return severity if severity in {"critical", "major", "warning", "minor", "info"} else fallback


def normalize_confidence(value: Any, *, fallback: float) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return fallback


def clean_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()
