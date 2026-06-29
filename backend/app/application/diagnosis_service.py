from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..domain.fingerprint import build_context_fingerprint, build_fault_fingerprint
from ..infrastructure.collectors.base import ObservationCollector
from ..infrastructure.llm.base import LLMClient, LLMResponseError
from .fact_normalizer import FactNormalizer
from .diagnosis_schema import LLMDiagnosisResult
from .llm_prompt import SYSTEM_PROMPT, build_diagnosis_payload
from .diagnosis_context import ALLOWED_FAULT_TYPES, build_context_constraints


class DiagnosisService:
    def __init__(
        self,
        collector: ObservationCollector,
        fact_normalizer: FactNormalizer,
        llm_client: LLMClient,
    ) -> None:
        self._collector = collector
        self._fact_normalizer = fact_normalizer
        self._llm_client = llm_client
        self._cache: dict[str, dict[str, Any]] = {}

    def analyze(
        self,
        question: str,
        fault_case_id: str = "live-snmp-current",
        session_id: str = "default-session",
        topology_group_id: str | None = None,
    ) -> dict[str, Any]:
        prepared = self.prepare_analysis(
            question=question,
            fault_case_id=fault_case_id,
            session_id=session_id,
            topology_group_id=topology_group_id,
        )
        if prepared.get("result") is not None:
            return prepared["result"]
        if prepared["cache_hit"]:
            return prepared["cached_result"]

        raw_llm_result = self._llm_client.complete_json(SYSTEM_PROMPT, prepared["llm_payload"])
        return self.complete_prepared_analysis(prepared, raw_llm_result)

    def prepare_analysis(
        self,
        question: str,
        fault_case_id: str = "live-snmp-current",
        session_id: str = "default-session",
        topology_group_id: str | None = None,
    ) -> dict[str, Any]:
        fault_case = self._collector.get_fault_case(fault_case_id)
        topology = self._collector.get_topology()
        facts = self._fact_normalizer.normalize_fault_case(fault_case)
        question_context = build_question_context(question, topology, fault_case, facts)
        if facts:
            fingerprint_info = build_fault_fingerprint(facts, topology)
        else:
            fingerprint_info = build_context_fingerprint(
                question_context=question_context,
                topology=topology,
                state=fault_case.get("state", "no_facts"),
            )
        fingerprint = fingerprint_info["fingerprint"]

        if fingerprint in self._cache:
            result = deepcopy(self._cache[fingerprint])
            result["cache_hit"] = True
            result["question"] = question
            result["session_id"] = session_id
            result["topology_group_id"] = topology_group_id
            return {
                "question": question,
                "session_id": session_id,
                "topology_group_id": topology_group_id,
                "fault_case": fault_case,
                "topology": topology,
                "facts": facts,
                "question_context": question_context,
                "fingerprint_info": fingerprint_info,
                "fingerprint": fingerprint,
                "cache_hit": True,
                "cached_result": result,
            }

        context_constraints = build_context_constraints(fault_case, facts, question_context)
        llm_payload = build_diagnosis_payload(
            question=question,
            fault_case=fault_case,
            facts=facts,
            topology=topology,
            fingerprint_info=fingerprint_info,
            context_constraints=context_constraints,
            question_context=question_context,
        )
        return {
            "question": question,
            "session_id": session_id,
            "topology_group_id": topology_group_id,
            "fault_case": fault_case,
            "topology": topology,
            "facts": facts,
            "question_context": question_context,
            "fingerprint_info": fingerprint_info,
            "fingerprint": fingerprint,
            "context_constraints": context_constraints,
            "llm_payload": llm_payload,
            "cache_hit": False,
        }

    def complete_prepared_analysis(self, prepared: dict[str, Any], raw_llm_result: dict[str, Any]) -> dict[str, Any]:
        result = self._normalize_llm_result(
            raw_llm_result=raw_llm_result,
            fault_case=prepared["fault_case"],
            facts=prepared["facts"],
            fingerprint_info=prepared["fingerprint_info"],
            context_constraints=prepared["context_constraints"],
        )
        result["cache_hit"] = False
        self._cache[prepared["fingerprint"]] = deepcopy(result)
        result["question"] = prepared["question"]
        result["session_id"] = prepared["session_id"]
        result["topology_group_id"] = prepared["topology_group_id"]
        return result

    def facts(self, fault_case_id: str = "live-snmp-current") -> list[dict[str, Any]]:
        return self._fact_normalizer.normalize_fault_case(self._collector.get_fault_case(fault_case_id))

    def clear_cache(self) -> None:
        self._cache.clear()

    def cache_size(self) -> int:
        return len(self._cache)

    def llm_metadata(self) -> dict[str, Any]:
        return self._llm_client.metadata()

    def llm_agents_chat_model(self) -> Any:
        if not hasattr(self._llm_client, "agents_chat_model"):
            raise LLMResponseError("Configured LLM client does not support OpenAI Agents SDK")
        return self._llm_client.agents_chat_model()

    def llm_agents_model_settings(self) -> Any:
        if not hasattr(self._llm_client, "agents_model_settings"):
            return None
        return self._llm_client.agents_model_settings()

    def parse_llm_json_content(self, content: str) -> dict[str, Any]:
        if hasattr(self._llm_client, "parse_json_content"):
            return self._llm_client.parse_json_content(content)
        raise LLMResponseError("Configured LLM client does not expose JSON parsing")

    def _normalize_llm_result(
        self,
        raw_llm_result: dict[str, Any],
        fault_case: dict[str, Any],
        facts: list[dict[str, Any]],
        fingerprint_info: dict[str, Any],
        context_constraints: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            llm_result = LLMDiagnosisResult.model_validate(raw_llm_result)
        except Exception as exc:
            raise LLMResponseError(f"LLM diagnosis JSON failed schema validation: {exc}") from exc

        if llm_result.fault_type not in ALLOWED_FAULT_TYPES:
            raise LLMResponseError(f"LLM returned unsupported fault_type: {llm_result.fault_type}")

        return {
            "fault_fingerprint": fingerprint_info["fingerprint"],
            "fault_type": llm_result.fault_type,
            "root_cause": llm_result.root_cause,
            "affected_devices": llm_result.affected_devices,
            "affected_services": llm_result.affected_services,
            "evidence": llm_result.evidence,
            "diagnosis_chain": llm_result.diagnosis_chain,
            "confidence": llm_result.confidence,
            "recommendation": llm_result.recommendation,
            "need_more_data": llm_result.need_more_data,
            "facts": facts,
            "fingerprint_payload": fingerprint_info["payload"],
            "context_constraints": context_constraints,
            "diagnosis_source": "llm_openai_compatible",
            "llm": self._llm_client.metadata(),
            "data_source": fault_case.get("data_source", "unknown"),
        }


def format_fact_evidence(fact: dict[str, Any]) -> str:
    if fact["fact_type"] == "INTERFACE_OPER_DOWN":
        status = str(fact.get("value") or "oper=down").replace(",", "、")
        return f"{fact['device_id']} {fact['object']} {status}"
    return f"{fact['device_id']} {fact['object']} {fact['fact_type']}={fact['value']}"


def build_question_context(
    question: str,
    topology: dict[str, Any],
    fault_case: dict[str, Any],
    facts: list[dict[str, Any]],
) -> dict[str, Any]:
    observations = fault_case.get("observations") or {}
    reported_events = observations.get("reported_events") or []
    mentioned_nodes = [
        node_context(node, topology)
        for node in find_question_target_nodes(question, topology)
    ]
    return {
        "question": question,
        "fault_case_state": fault_case.get("state", "active_fault"),
        "topology_id": topology.get("id"),
        "topology_degraded": bool((topology.get("discovery") or {}).get("degraded")),
        "topology_node_count": len(topology.get("nodes") or []),
        "topology_edge_count": len(topology.get("edges") or []),
        "mentioned_nodes": mentioned_nodes,
        "mentioned_interfaces": mentioned_interfaces(question, facts),
        "active_event_count": len(reported_events),
        "fact_types": sorted({fact.get("fact_type") for fact in facts if fact.get("fact_type")}),
        "fact_devices": sorted({fact.get("device_id") for fact in facts if fact.get("device_id")}),
        "has_active_fault_facts": bool(facts),
    }


def find_question_target_nodes(question: str, topology: dict[str, Any]) -> list[dict[str, Any]]:
    normalized_question = normalize_match_text(question)
    candidates = sorted(topology.get("nodes") or [], key=lambda node: len(str(node.get("id") or "")), reverse=True)
    matches = []
    seen = set()
    for node in candidates:
        aliases = {
            str(value)
            for value in [
                node.get("id"),
                node.get("label"),
                node.get("name"),
                node.get("hostname"),
            ]
            if value
        }
        if any(normalize_match_text(alias) in normalized_question for alias in aliases):
            node_id = node.get("id")
            if node_id not in seen:
                seen.add(node_id)
                matches.append(node)
    return matches


def node_context(node: dict[str, Any], topology: dict[str, Any]) -> dict[str, Any]:
    node_id = str(node.get("id") or "")
    neighbors = node_neighbors(node_id, topology)
    incident = incident_edges(node_id, topology)
    return {
        "id": node_id,
        "label": node.get("label") or node_id,
        "role": node.get("role"),
        "status": node.get("status"),
        "degree": len(neighbors),
        "neighbors": neighbors,
        "is_isolated": not neighbors,
        "incident_edges": incident,
    }


def node_neighbors(node_id: str, topology: dict[str, Any]) -> list[str]:
    neighbors = set()
    for edge in topology.get("edges") or []:
        source = edge.get("source")
        target = edge.get("target")
        if source == node_id and target:
            neighbors.add(str(target))
        if target == node_id and source:
            neighbors.add(str(source))
    return sorted(neighbors)


def incident_edges(node_id: str, topology: dict[str, Any]) -> list[dict[str, Any]]:
    edges = []
    for edge in topology.get("edges") or []:
        if edge.get("source") != node_id and edge.get("target") != node_id:
            continue
        edges.append(
            {
                "source": edge.get("source"),
                "target": edge.get("target"),
                "source_interface": edge.get("source_interface"),
                "target_interface": edge.get("target_interface"),
                "status": edge.get("status"),
                "protocol": edge.get("protocol"),
            }
        )
    return edges


def mentioned_interfaces(question: str, facts: list[dict[str, Any]]) -> list[str]:
    normalized_question = normalize_match_text(question)
    interfaces = sorted(
        {
            str(fact.get("object"))
            for fact in facts
            if fact.get("object") and normalize_match_text(str(fact.get("object"))) in normalized_question
        }
    )
    return interfaces


def normalize_match_text(value: str) -> str:
    return "".join(str(value or "").lower().split())
