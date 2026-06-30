from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.application.agent_service import AgentService
from app.application.consistency_service import project_comparison_fields, run_consistency_test
from app.application.correlation_engine import CorrelationEngine
from app.application.diagnosis_service import DiagnosisService
from app.application.diagnosis_schema import LLMDiagnosisResult
from app.application.event_normalizer import normalize_reported_event
from app.application.event_store import EventStore
from app.application.fact_normalizer import FactNormalizer
from app.application.diagnosis_context import build_context_constraints
from app.application.knowledge_base import KnowledgeBaseService
from app.application.topology_service import TopologyService
from app.core.observability import sanitize_for_log
from app.domain.fingerprint import build_fault_fingerprint
from app.infrastructure.collectors import SnmpObservationCollector
from app.infrastructure.llm.config_store import LLMConfigStore
from app.infrastructure.llm.openai_compatible_client import OpenAICompatibleLLMClient
from app.infrastructure.mib import MibProfileRegistry, MibService
from app.infrastructure.topology.snmp_lldp_provider import SnmpLldpTopologyProvider


LIVE_SNMP_TARGETS = ["127.0.0.1:11611", "127.0.0.1:11612", "127.0.0.1:11613", "127.0.0.1:11614"]
LIVE_SNMP_CONFIG = {
    "profile_id": "snmp_lldp",
    "community": "public",
    "targets": LIVE_SNMP_TARGETS,
    "scan_cidrs": [],
    "timeout_seconds": 3,
    "scan_timeout_seconds": 1.5,
}


class StaticTopologyProvider:
    mode = "snmp_lldp"

    def metadata(self) -> dict:
        return {
            "mode": self.mode,
            "description": "static test topology",
            "protocols": ["SNMPv2c", "IF-MIB", "LLDP-MIB"],
        }

    def discover(self, options: dict | None = None) -> dict:
        return {
            "id": "snmp-lldp-discovered-topology",
            "name": "Static Test Topology",
            "nodes": [
                {"id": "spine-01", "label": "spine-01", "role": "spine", "status": "up", "interfaces": []},
                {"id": "leaf-01", "label": "leaf-01", "role": "leaf", "status": "up", "interfaces": []},
                {"id": "leaf-02", "label": "leaf-02", "role": "leaf", "status": "up", "interfaces": []},
                {"id": "isolated-01", "label": "isolated-01", "role": "router", "status": "up", "interfaces": []},
            ],
            "edges": [
                {
                    "source": "leaf-01",
                    "target": "spine-01",
                    "source_interface": "eth1",
                    "target_interface": "eth1",
                    "status": "up",
                    "protocol": "snmp-lldp",
                },
                {
                    "source": "leaf-02",
                    "target": "spine-01",
                    "source_interface": "eth1",
                    "target_interface": "eth2",
                    "status": "up",
                    "protocol": "snmp-lldp",
                },
            ],
            "discovery": {
                "mode": self.mode,
                "target_source": "static_test",
                "protocols": ["SNMPv2c", "IF-MIB", "LLDP-MIB"],
            },
        }


class FailingTopologyProvider(StaticTopologyProvider):
    def discover(self, options: dict | None = None) -> dict:
        raise ValueError("No SNMP response received before timeout")


def llm_configured() -> bool:
    return bool(os.getenv("LLM_API_KEY") and os.getenv("LLM_BASE_URL") and os.getenv("LLM_MODEL"))


class StaticLLMClient:
    def complete_json(self, system_prompt: str, user_payload: dict) -> dict:
        question_context = user_payload.get("question_context") or {}
        facts = user_payload.get("facts") or []
        dependency_anchors = {
            (fact.get("context") or {}).get("depends_on_interface")
            for fact in facts
            if (fact.get("context") or {}).get("depends_on_interface")
        }
        root_fact = next((fact for fact in facts if fact.get("object") in dependency_anchors), None)
        dependent_facts = [
            fact
            for fact in facts
            if root_fact
            and fact.get("fact_id") != root_fact.get("fact_id")
            and (fact.get("context") or {}).get("depends_on_interface") == root_fact.get("object")
        ]
        if root_fact and dependent_facts:
            device = root_fact["device_id"]
            anchor = root_fact["object"]
            return {
                "fault_type": "ANCHOR_EVENT_CAUSES_DEPENDENT_FAILURES",
                "root_cause": f"{device} {anchor} 是多个异常事实的共同依赖锚点，优先作为根因线索分析",
                "affected_devices": sorted({fact["device_id"] for fact in facts}),
                "affected_services": sorted(
                    {
                        fact["object"]
                        for fact in facts
                        if "service" in str(fact.get("object") or "").lower() or (fact.get("context") or {}).get("target")
                    }
                ),
                "evidence": [item for item in (user_payload.get("context_constraints") or {}).get("evidence", []) if item],
                "diagnosis_chain": [
                    f"{device} {anchor} 出现根因级异常事实",
                    "多个上报事件声明依赖同一锚点",
                    "由实时事实链推断为同一故障窗口内的派生异常",
                ],
                "confidence": 0.92,
                "recommendation": [
                    f"优先核查 {device} {anchor} 对应的物理链路、接口或资源状态",
                    "恢复锚点后复查依赖它的控制面、转发面和业务探测事件",
                ],
                "need_more_data": False,
            }
        if facts and not root_fact:
            return {
                "fault_type": "UNKNOWN_NEED_MORE_DATA",
                "root_cause": "已收到异常 facts，但缺少能解释其他事实的共同依赖锚点，暂不能确定根因",
                "affected_devices": sorted({fact["device_id"] for fact in facts}),
                "affected_services": [],
                "evidence": [item for item in (user_payload.get("context_constraints") or {}).get("evidence", []) if item],
                "diagnosis_chain": [
                    "收到设备异常 facts",
                    "未发现可解释派生异常的共同依赖锚点",
                    "需要补充同一时间窗口内的根因事件",
                ],
                "confidence": 0.58,
                "recommendation": [
                    "补充同一时间窗口内的接口、链路、资源或依赖关系事件",
                    "核对异常 facts 是否带有 depends_on_interface、target 或其他依赖上下文字段",
                ],
                "need_more_data": True,
            }
        mentioned_nodes = question_context.get("mentioned_nodes") or []
        isolated_node = next((node for node in mentioned_nodes if node.get("is_isolated")), None)
        if isolated_node:
            node_id = isolated_node["id"]
            return {
                "fault_type": "TOPOLOGY_CONTEXT_ISSUE",
                "root_cause": f"{node_id} 在当前拓扑上下文中没有已发现邻接链路，业务不通需要优先核对接入和拓扑发现状态",
                "affected_devices": [node_id],
                "affected_services": [],
                "evidence": [
                    f"question_context 显示用户点名 {node_id}",
                    f"question_context 显示 {node_id} degree=0 且 is_isolated=true",
                    "当前事件窗口没有该设备的活动故障 facts",
                ],
                "diagnosis_chain": [
                    f"用户关注 {node_id}",
                    "系统抽取到该节点无邻接链路",
                    "缺少活动故障上报，按拓扑上下文提示继续补数",
                ],
                "confidence": 0.82,
                "recommendation": [
                    f"核对 {node_id} 是否应接入当前拓扑",
                    "确认 LLDP/SNMP 发现范围和上联链路状态",
                ],
                "need_more_data": True,
            }
        if question_context.get("fault_case_state") == "no_active_fault":
            return {
                "fault_type": "NO_ACTIVE_FAULT",
                "root_cause": "当前事件窗口没有活动故障 facts，未发现未恢复故障",
                "affected_devices": [node["id"] for node in mentioned_nodes],
                "affected_services": [],
                "evidence": ["question_context 显示 active_event_count=0 且 has_active_fault_facts=false"],
                "diagnosis_chain": ["采集当前事件窗口", "未发现活动故障 facts", "返回当前环境状态"],
                "confidence": 0.8,
                "recommendation": ["继续观察事件窗口；如果业务仍异常，请补充设备日志、Trap、Telemetry 或业务探测结果"],
                "need_more_data": bool(mentioned_nodes),
            }
        return {
            "fault_type": "INTERFACE_DOWN",
            "root_cause": f"LLM raw diagnosis for {user_payload['question']}",
            "affected_devices": ["leaf-01"],
            "affected_services": ["raw-service"],
            "evidence": ["raw llm evidence"],
            "diagnosis_chain": ["raw llm chain"],
            "confidence": 0.5,
            "recommendation": ["raw llm recommendation"],
            "need_more_data": False,
        }

    def metadata(self) -> dict:
        return {
            "provider": "static-test-llm",
            "configured": True,
            "model": "static",
            "has_api_key": False,
            "missing_fields": [],
        }


class Phase1ConsistencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = StaticTopologyProvider()
        self.event_store = EventStore()
        self.correlation_engine = CorrelationEngine(self.event_store, window_seconds=300)
        self.seed_phase2_reported_events()
        self.collector = SnmpObservationCollector(self.provider, correlation_engine=self.correlation_engine)
        self.fact_normalizer = FactNormalizer()

    def seed_phase2_reported_events(self) -> None:
        payloads = [
            {
                "channel": "syslog",
                "device_id": "leaf-01",
                "event_type": "IF_STATUS_DOWN",
                "object": "eth1",
                "message": "leaf-01 Interface eth1 changed state to DOWN",
            },
            {
                "channel": "snmp_trap",
                "device_id": "leaf-01",
                "event_type": "CONTROL_PLANE_PEER_LOST",
                "object": "spine-01",
                "message": "BGP peer spine-01 state idle",
                "attributes": {"depends_on_interface": "eth1", "remote_device": "spine-01", "state": "idle"},
            },
            {
                "channel": "grpc_telemetry",
                "device_id": "leaf-01",
                "event_type": "TRAFFIC_VOLUME_ZERO",
                "object": "eth1",
                "message": "interface eth1 traffic dropped to 0bps",
                "attributes": {"depends_on_interface": "eth1"},
            },
            {
                "channel": "snmp_trap",
                "device_id": "leaf-01",
                "event_type": "ROUTING_PREFIX_WITHDRAWN",
                "object": "10.10.10.0/24",
                "message": "route 10.10.10.0/24 withdrawn",
                "attributes": {"depends_on_interface": "eth1", "next_hop": "spine-01"},
            },
            {
                "channel": "snmp_trap",
                "device_id": "leaf-01",
                "event_type": "FORWARDING_ENTRY_ABSENT",
                "object": "10.10.10.0/24",
                "message": "fib missing 10.10.10.0/24",
                "attributes": {"depends_on_interface": "eth1", "next_hop": "spine-01"},
            },
            {
                "channel": "syslog",
                "device_id": "leaf-01",
                "event_type": "APPLICATION_PATH_UNREACHABLE",
                "object": "cross-leaf-service",
                "message": "service cross-leaf-service unreachable",
                "attributes": {"depends_on_interface": "eth1", "target": "leaf-01->spine-01"},
            },
        ]
        for payload in payloads:
            channel = payload.pop("channel")
            self.event_store.append(
                normalize_reported_event(
                    channel=channel,
                    payload=payload,
                    raw=payload.get("message", ""),
                    source_ip="127.0.0.1",
                )
            )

    def make_diagnosis_service(self) -> DiagnosisService:
        return DiagnosisService(
            collector=self.collector,
            fact_normalizer=self.fact_normalizer,
            llm_client=OpenAICompatibleLLMClient.from_env(),
        )

    def make_static_diagnosis_service(self) -> DiagnosisService:
        return DiagnosisService(
            collector=self.collector,
            fact_normalizer=self.fact_normalizer,
            llm_client=StaticLLMClient(),
        )

    def test_topology_discovers_frr_shape_devices_and_edges(self) -> None:
        topology = self.provider.discover()

        self.assertEqual(topology["discovery"]["mode"], "snmp_lldp")
        self.assertEqual(topology["discovery"]["target_source"], "static_test")
        self.assertEqual(len(topology["nodes"]), 4)
        self.assertEqual(len(topology["edges"]), 2)
        self.assertIn("isolated-01", {node["id"] for node in topology["nodes"]})

    def test_current_topology_degrades_when_snmp_times_out(self) -> None:
        collector = SnmpObservationCollector(
            FailingTopologyProvider(),
            correlation_engine=self.correlation_engine,
        )
        topology = TopologyService(collector).current_topology()

        self.assertEqual(topology["nodes"], [])
        self.assertEqual(topology["edges"], [])
        self.assertTrue(topology["discovery"]["degraded"])
        self.assertIn("No SNMP response", topology["discovery"]["error"])

    def test_reported_events_collector_builds_fault_case_from_uploaded_events(self) -> None:
        fault_case = self.collector.get_fault_case("live-snmp-current")
        facts = self.fact_normalizer.normalize_fault_case(fault_case)
        fact_types = {fact["fact_type"] for fact in facts}

        self.assertEqual(fault_case["data_source"], "reported_events")
        self.assertEqual(fault_case["primary_device"], "leaf-01")
        self.assertEqual(fault_case["primary_interface"], "eth1")
        self.assertNotIn("expected_fault_type", fault_case)
        self.assertIn("IF_STATUS_DOWN", fact_types)
        self.assertIn("Interface eth1", " ".join(fact["value"] for fact in facts))

    def test_unreported_phase2_events_do_not_create_fake_multi_anomaly_facts(self) -> None:
        empty_collector = SnmpObservationCollector(
            self.provider,
            correlation_engine=CorrelationEngine(EventStore(), window_seconds=300),
        )
        fault_case = empty_collector.get_fault_case("live-snmp-current")
        facts = self.fact_normalizer.normalize_fault_case(fault_case)

        self.assertEqual(fault_case["state"], "no_active_fault")
        self.assertNotIn("expected_fault_type", fault_case)
        self.assertEqual(facts, [])

    def test_reported_events_without_link_evidence_need_more_data(self) -> None:
        event_store = EventStore()
        event_store.append(
            normalize_reported_event(
                channel="snmp_trap",
                payload={
                    "device_id": "leaf-01",
                    "event_type": "CONTROL_PLANE_PEER_LOST",
                    "object": "spine-01",
                    "message": "BGP peer spine-01 state idle",
                },
                raw="BGP peer spine-01 state idle",
                source_ip="127.0.0.1",
            )
        )
        collector = SnmpObservationCollector(
            self.provider,
            correlation_engine=CorrelationEngine(event_store, window_seconds=300),
        )
        service = DiagnosisService(
            collector=collector,
            fact_normalizer=self.fact_normalizer,
            llm_client=StaticLLMClient(),
        )
        diagnosis = service.analyze("BGP 为什么 down", session_id="need-more-data")

        self.assertEqual(diagnosis["fault_type"], "UNKNOWN_NEED_MORE_DATA")
        self.assertTrue(diagnosis["need_more_data"])
        self.assertIn("缺少", diagnosis["root_cause"])

    def test_raw_syslog_is_not_keyword_classified_without_ai_extraction(self) -> None:
        message = (
            "<30>Jun 27 17:28:34 bgpd[41]: [M59KS-A3ZXZ] "
            "bgp_update_receive: rcvd End-of-RIB for IPv4 Unicast from 10.0.12.2 in vrf default"
        )
        event = normalize_reported_event(channel="syslog", raw=message, source_ip="127.0.0.1")

        self.assertEqual(event.event_type, "RAW_REPORTED_EVENT")
        self.assertEqual(event.device_id, "127.0.0.1")
        self.assertEqual(event.object, "unknown-object")
        self.assertEqual(event.severity, "info")
        self.assertEqual(event.attributes["syslog_program"], "bgpd")
        self.assertEqual(event.attributes["syslog_pid"], "41")
        self.assertEqual(event.attributes["frr_code"], "M59KS-A3ZXZ")
        self.assertEqual(event.attributes["afi"], "IPv4 Unicast")
        self.assertEqual(event.attributes["vrf"], "default")

    def test_informational_frr_syslog_does_not_create_current_fault(self) -> None:
        event_store = EventStore()
        event_store.append(
            normalize_reported_event(
                channel="syslog",
                raw=(
                    "<30>Jun 27 17:28:34 bgpd[41]: [M59KS-A3ZXZ] "
                    "bgp_update_receive: rcvd End-of-RIB for IPv4 Unicast from 10.0.12.2 in vrf default"
                ),
                source_ip="127.0.0.1",
            )
        )
        collector = SnmpObservationCollector(
            self.provider,
            correlation_engine=CorrelationEngine(event_store, window_seconds=300),
        )
        fault_case = collector.get_fault_case("live-snmp-current")

        self.assertEqual(fault_case["state"], "no_active_fault")
        self.assertNotIn("expected_fault_type", fault_case)

    def test_phase2_live_fault_case_contains_multi_anomaly_facts(self) -> None:
        fault_case = self.collector.get_fault_case("live-snmp-current")
        facts = self.fact_normalizer.normalize_fault_case(fault_case)
        fact_types = {fact["fact_type"] for fact in facts}

        self.assertIn("IF_STATUS_DOWN", fact_types)
        self.assertIn("TRAFFIC_VOLUME_ZERO", fact_types)
        self.assertIn("CONTROL_PLANE_PEER_LOST", fact_types)
        self.assertIn("ROUTING_PREFIX_WITHDRAWN", fact_types)
        self.assertIn("FORWARDING_ENTRY_ABSENT", fact_types)
        self.assertIn("APPLICATION_PATH_UNREACHABLE", fact_types)
        self.assertEqual(
            len([fact for fact in facts if fact["fact_type"] == "IF_STATUS_DOWN"]),
            1,
        )

    def test_phase2_facts_preserve_dependency_and_source_context(self) -> None:
        fault_case = self.collector.get_fault_case("live-snmp-current")
        facts = self.fact_normalizer.normalize_fault_case(fault_case)
        context = build_context_constraints(
            fault_case=fault_case,
            facts=facts,
            question_context={"mentioned_nodes": [], "active_event_count": 6},
        )
        facts_by_type = {fact["fact_type"]: fact for fact in facts}

        for fact_type in ["CONTROL_PLANE_PEER_LOST", "ROUTING_PREFIX_WITHDRAWN", "FORWARDING_ENTRY_ABSENT", "APPLICATION_PATH_UNREACHABLE"]:
            fact_context = facts_by_type[fact_type]["context"]
            self.assertEqual(fact_context["depends_on_interface"], "eth1")
            self.assertTrue(fact_context["source_event_id"].startswith("evt_"))

        peer_fact = facts_by_type["CONTROL_PLANE_PEER_LOST"]
        self.assertEqual(peer_fact["context"]["remote_device"], "spine-01")
        route_fact = facts_by_type["ROUTING_PREFIX_WITHDRAWN"]
        self.assertEqual(route_fact["context"]["next_hop"], "spine-01")
        peer_chain_item = next(item for item in context["fact_chain"] if item["fact_type"] == "CONTROL_PLANE_PEER_LOST")

        self.assertEqual(peer_chain_item["context"]["depends_on_interface"], "eth1")
        self.assertIn("depends_on_interface=eth1", " ".join(context["evidence"]))

    def test_event_store_and_correlation_preview_report_uploaded_events(self) -> None:
        events = self.event_store.list_events(limit=10)
        preview = self.correlation_engine.preview(device_id="leaf-01")

        self.assertEqual(len(events), 6)
        self.assertEqual(preview["event_count"], 6)
        self.assertEqual(preview["summary"]["by_type"]["CONTROL_PLANE_PEER_LOST"], 1)

    def test_phase2_context_builder_extracts_fault_chain_signals(self) -> None:
        fault_case = self.collector.get_fault_case("live-snmp-current")
        facts = self.fact_normalizer.normalize_fault_case(fault_case)
        context = build_context_constraints(
            fault_case=fault_case,
            facts=facts,
            question_context={"mentioned_nodes": [], "active_event_count": 6},
        )

        self.assertFalse(context["is_deterministic"])
        self.assertNotIn("candidate_fault_types", context)
        self.assertIn("primary_signal", context)
        self.assertTrue(context["primary_signal"]["fact_id"])
        self.assertGreaterEqual(len(context["fact_chain"]), 5)
        self.assertIn("leaf-01 eth1 IF_STATUS_DOWN", " ".join(context["evidence"]))

    def test_knowledge_base_retrieval_is_injected_into_diagnosis_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            knowledge_base = KnowledgeBaseService(
                storage_file=Path(temp_dir) / "knowledge.json",
                builtin_dir=Path(temp_dir) / "builtin",
            )
            saved = knowledge_base.upsert_document(
                {
                    "title": "BGP 邻居中断排障 SOP",
                    "source": "test-runbook",
                    "tags": ["BGP", "route", "FIB"],
                    "content": "BGP 邻居 Down 后，应先检查依赖接口状态，再检查路由表和 FIB 下发。",
                }
            )
            search = knowledge_base.search("BGP 邻居 Down 接口 路由 FIB", limit=3)
            service = DiagnosisService(
                collector=self.collector,
                fact_normalizer=self.fact_normalizer,
                llm_client=StaticLLMClient(),
                knowledge_base=knowledge_base,
            )
            prepared = service.prepare_analysis("BGP 邻居 down 之后怎么排查", session_id="rag-s1")
            knowledge_context = prepared["llm_payload"]["knowledge_context"]

            self.assertEqual(saved["document"]["title"], "BGP 邻居中断排障 SOP")
            self.assertGreaterEqual(len(search["items"]), 1)
            self.assertEqual(search["items"][0]["title"], "BGP 邻居中断排障 SOP")
            self.assertEqual(search["summary"]["backend"], "rank_bm25.BM25Okapi")
            self.assertEqual(search["items"][0]["retrieval_backend"], "rank_bm25.BM25Okapi")
            self.assertTrue(knowledge_context["enabled"])
            self.assertGreaterEqual(len(knowledge_context["items"]), 1)
            self.assertEqual(knowledge_context["items"][0]["source"], "test-runbook")
            self.assertIn("实时 facts", " ".join(knowledge_context["instructions"]))

    def test_knowledge_base_splits_markdown_by_headings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            builtin_dir = Path(temp_dir) / "builtin"
            builtin_dir.mkdir()
            (builtin_dir / "vendor_runbook.md").write_text(
                "# Vendor Runbook\n\n"
                "## BGP 故障\n\n"
                "BGP 邻居异常时检查 hold timer 和 peer 状态。\n\n"
                "## FIB 故障\n\n"
                "FIB 表项缺失时检查路由下发和转发表同步。",
                encoding="utf-8",
            )
            knowledge_base = KnowledgeBaseService(
                storage_file=Path(temp_dir) / "knowledge.json",
                builtin_dir=builtin_dir,
            )
            result = knowledge_base.search("FIB 表项 缺失 转发表", limit=1)

            self.assertEqual(result["items"][0]["heading"], "FIB 故障")
            self.assertIn("FIB 表项缺失", result["items"][0]["content"])

    def test_live_snmp_fingerprint_is_stable_for_reordered_facts(self) -> None:
        fault_case = self.collector.get_fault_case("live-snmp-current")
        facts = self.fact_normalizer.normalize_fault_case(fault_case)
        topology = self.collector.get_topology()
        first = build_fault_fingerprint(facts, topology)
        second = build_fault_fingerprint(list(reversed(facts)), topology)

        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_topology_service_uses_snmp_runtime_path(self) -> None:
        service = TopologyService(self.collector, providers=[self.provider])
        capabilities = service.capabilities()
        topology = service.discover(mode="snmp_lldp")

        self.assertEqual(capabilities["supported_runtime_modes"], ["snmp_lldp"])
        self.assertEqual(topology["discovery"]["node_count"], 4)
        self.assertEqual(topology["discovery"]["edge_count"], 2)
        self.assertEqual(topology["discovery"]["group_count"], 2)

    def test_topology_service_applies_interface_up_down_events(self) -> None:
        service = TopologyService(self.collector, providers=[self.provider])
        service.discover(mode="snmp_lldp")

        down_event = normalize_reported_event(
            channel="snmp_trap",
            payload={
                "device_id": "leaf-01",
                "event_type": "IF_STATUS_DOWN",
                "object": "eth1",
                "message": "leaf-01 SNMP Trap linkDown interface eth1 oper=down",
            },
            raw="leaf-01 SNMP Trap linkDown interface eth1 oper=down",
            source_ip="127.0.0.1",
        )
        service.apply_event(down_event.to_dict())
        down_topology = service.current_topology()
        down_edge = next(edge for edge in down_topology["edges"] if edge["source"] == "leaf-01" and edge["target"] == "spine-01")

        self.assertEqual(down_edge["status"], "down")
        self.assertEqual(down_edge["runtime_status_source"], "snmp_trap")
        self.assertEqual(down_topology["discovery"]["runtime_status_overrides"], 1)

        up_event = normalize_reported_event(
            channel="snmp_trap",
            payload={
                "device_id": "leaf-01",
                "event_type": "IF_STATUS_UP",
                "object": "eth1",
                "message": "leaf-01 SNMP Trap linkUp interface eth1 oper=up",
            },
            raw="leaf-01 SNMP Trap linkUp interface eth1 oper=up",
            source_ip="127.0.0.1",
        )
        service.apply_event(up_event.to_dict())
        up_topology = service.current_topology()
        up_edge = next(edge for edge in up_topology["edges"] if edge["source"] == "leaf-01" and edge["target"] == "spine-01")

        self.assertEqual(up_edge["status"], "up")
        self.assertEqual(up_edge["runtime_status_source"], "snmp_trap")

    def test_llm_schema_accepts_required_diagnosis_fields(self) -> None:
        parsed = LLMDiagnosisResult.model_validate(
            {
                "fault_type": "INTERFACE_DOWN",
                "root_cause": "leaf-01 eth1 接口 Down",
                "affected_devices": ["leaf-01"],
                "affected_services": [],
                "evidence": ["leaf-01 eth1 admin=down、oper=down"],
                "diagnosis_chain": ["接口 Down", "链路不可用"],
                "confidence": 0.9,
                "recommendation": ["检查 leaf-01 eth1 链路状态"],
                "need_more_data": False,
            }
        )
        self.assertEqual(parsed.fault_type, "INTERFACE_DOWN")

    def test_phase2_diagnosis_uses_llm_with_context_constraints(self) -> None:
        service = self.make_static_diagnosis_service()
        diagnosis = service.analyze("BGP 和路由为什么都异常", session_id="phase2-s1")

        self.assertEqual(diagnosis["fault_type"], "ANCHOR_EVENT_CAUSES_DEPENDENT_FAILURES")
        self.assertEqual(diagnosis["diagnosis_source"], "llm_openai_compatible")
        self.assertIn("context_constraints", diagnosis)
        self.assertNotIn("candidate_fault_types", diagnosis["context_constraints"])
        self.assertGreaterEqual(len(diagnosis["context_constraints"]["fact_chain"]), 5)
        self.assertFalse(diagnosis["need_more_data"])

    def test_recovery_event_returns_no_active_fault_and_bypasses_old_cache(self) -> None:
        service = self.make_static_diagnosis_service()
        first = service.analyze("先诊断 leaf-01", session_id="recovery-s1")
        self.assertEqual(first["fault_type"], "ANCHOR_EVENT_CAUSES_DEPENDENT_FAILURES")
        self.assertEqual(service.cache_size(), 1)

        self.event_store.append(
            normalize_reported_event(
                channel="snmp_trap",
                payload={
                    "device_id": "leaf-01",
                    "event_type": "INTERFACE_OPER_UP",
                    "object": "eth1",
                    "message": "leaf-01 SNMP Trap linkUp interface eth1 oper=up",
                },
                raw="leaf-01 SNMP Trap linkUp interface eth1 oper=up",
                source_ip="127.0.0.1",
            )
        )
        second = service.analyze("重新诊断一下 leaf-01", session_id="recovery-s1")

        self.assertEqual(second["fault_type"], "NO_ACTIVE_FAULT")
        self.assertEqual(second["diagnosis_source"], "llm_openai_compatible")
        self.assertFalse(second["cache_hit"])
        self.assertEqual(second["facts"], [])
        self.assertTrue(second["fault_fingerprint"].startswith("fp_ctx_"))
        self.assertIn("没有活动故障", second["root_cause"])

    def test_isolated_node_question_uses_topology_context(self) -> None:
        empty_collector = SnmpObservationCollector(
            self.provider,
            correlation_engine=CorrelationEngine(EventStore(), window_seconds=300),
        )
        service = DiagnosisService(
            collector=empty_collector,
            fact_normalizer=self.fact_normalizer,
            llm_client=StaticLLMClient(),
        )

        diagnosis = service.analyze("isolated-01为什么业务不通", session_id="isolated-s1")

        self.assertEqual(diagnosis["fault_type"], "TOPOLOGY_CONTEXT_ISSUE")
        self.assertEqual(diagnosis["diagnosis_source"], "llm_openai_compatible")
        self.assertTrue(diagnosis["need_more_data"])
        self.assertEqual(diagnosis["affected_devices"], ["isolated-01"])
        self.assertTrue(diagnosis["fault_fingerprint"].startswith("fp_ctx_"))
        self.assertIn("拓扑上下文", diagnosis["root_cause"])
        self.assertFalse(diagnosis["cache_hit"])

    def test_prepare_analysis_enriches_no_active_context_without_direct_result(self) -> None:
        empty_collector = SnmpObservationCollector(
            self.provider,
            correlation_engine=CorrelationEngine(EventStore(), window_seconds=300),
        )
        service = DiagnosisService(
            collector=empty_collector,
            fact_normalizer=self.fact_normalizer,
            llm_client=StaticLLMClient(),
        )

        prepared = service.prepare_analysis("isolated-01为什么业务不通", session_id="context-s1")

        self.assertIsNone(prepared.get("result"))
        self.assertEqual(prepared["context_constraints"]["context_id"], "CTX-ENVIRONMENT")
        self.assertFalse(prepared["context_constraints"]["is_deterministic"])
        self.assertTrue(prepared["fingerprint"].startswith("fp_ctx_"))
        context = prepared["llm_payload"]["question_context"]
        self.assertEqual(context["mentioned_nodes"][0]["id"], "isolated-01")
        self.assertEqual(context["mentioned_nodes"][0]["degree"], 0)
        self.assertTrue(context["mentioned_nodes"][0]["is_isolated"])

    def test_phase2_cold_cache_questions_keep_same_canonical_diagnosis(self) -> None:
        service = self.make_static_diagnosis_service()
        questions = [
            "接口为什么 down",
            "BGP 邻居为什么 down",
            "路由为什么缺失",
            "业务探测为什么不可达",
        ]
        results = []
        for question in questions:
            service.clear_cache()
            results.append(project_comparison_fields(service.analyze(question, session_id=f"phase2-{len(results)}")))

        self.assertTrue(all(result == results[0] for result in results))

    def test_llm_client_reports_missing_configuration(self) -> None:
        metadata = OpenAICompatibleLLMClient.from_env().metadata()
        if not llm_configured():
            self.assertFalse(metadata["configured"])
            self.assertIn("LLM_API_KEY", metadata["missing_fields"])

    def test_llm_configuration_persists_and_reloads_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LLMConfigStore(Path(temp_dir) / "llm_config.json")
            client = OpenAICompatibleLLMClient.from_env(saved_config=store.get_config())
            client.configure(
                api_key="sk-test",
                base_url="https://llm.example/v1",
                model="deepseek-v4-flash",
                timeout_seconds=45,
                temperature=0.2,
                top_p=0.8,
                json_mode=False,
            )
            store.update_config(client.settings_snapshot(include_api_key=True))

            with patch.dict(os.environ, {}, clear=True):
                reloaded = OpenAICompatibleLLMClient.from_env(saved_config=store.get_config())

            metadata = reloaded.metadata()
            self.assertTrue(metadata["configured"])
            self.assertEqual(metadata["base_url"], "https://llm.example/v1")
            self.assertEqual(metadata["model"], "deepseek-v4-flash")
            self.assertTrue(metadata["has_api_key"])
            self.assertEqual(metadata["timeout_seconds"], 45)
            self.assertEqual(metadata["temperature"], 0.2)
            self.assertEqual(metadata["top_p"], 0.8)
            self.assertFalse(metadata["json_mode"])

    def test_llm_environment_variables_override_persisted_config(self) -> None:
        persisted = {
            "api_key": "sk-file",
            "base_url": "https://file.example/v1",
            "model": "file-model",
        }
        with patch.dict(
            os.environ,
            {
                "LLM_API_KEY": "sk-env",
                "LLM_BASE_URL": "https://env.example/v1",
                "LLM_MODEL": "env-model",
            },
            clear=True,
        ):
            metadata = OpenAICompatibleLLMClient.from_env(saved_config=persisted).metadata()

        self.assertTrue(metadata["configured"])
        self.assertEqual(metadata["base_url"], "https://env.example/v1")
        self.assertEqual(metadata["model"], "env-model")

    def test_observability_redacts_sensitive_values(self) -> None:
        payload = sanitize_for_log(
            {
                "api_key": "sk-secret",
                "headers": {"authorization": "Bearer secret", "content-type": "application/json"},
                "nested": {"refresh_token": "token-value", "message": "visible"},
            }
        )

        self.assertEqual(payload["api_key"], "***REDACTED***")
        self.assertEqual(payload["headers"]["authorization"], "***REDACTED***")
        self.assertEqual(payload["nested"]["refresh_token"], "***REDACTED***")
        self.assertEqual(payload["nested"]["message"], "visible")

    def test_mib_profiles_load_vendor_oid_bindings(self) -> None:
        registry = MibProfileRegistry()
        profiles = registry.list_profiles()
        profile_ids = {profile["id"] for profile in profiles}
        snmp_profile = registry.get_profile("snmp_lldp")

        self.assertIn("snmp_lldp", profile_ids)
        self.assertIn("h3c_snmp_lldp", profile_ids)
        self.assertEqual(snmp_profile["vendor"], "standard")
        self.assertEqual(snmp_profile["oid_bindings"]["if_admin_status"], ".1.3.6.1.2.1.2.2.1.7")

    def test_pysmi_mib_compiler_builds_tree_and_translates_oids(self) -> None:
        service = MibService()
        compiled = service.compile_profile("snmp_lldp", include_tree=True)
        summary = compiled["summary"]
        if_name = service.translate_oid("snmp_lldp", ".1.3.6.1.2.1.31.1.1.1.1.2")["translation"]
        lldp_sys_name = service.translate_oid("snmp_lldp", ".1.0.8802.1.1.2.1.4.1.1.9.0.1.1")["translation"]

        self.assertEqual(summary["failedFiles"], [])
        self.assertEqual(summary["unresolvedObjects"], [])
        self.assertIn("SNMPv2-MIB", summary["modules"])
        self.assertIn("IF-MIB", summary["modules"])
        self.assertIn("LLDP-MIB", summary["modules"])
        self.assertGreater(summary["totalObjects"], 20)
        self.assertTrue(compiled["tree"])
        self.assertEqual(if_name["moduleQualifiedName"], "IF-MIB::ifName")
        self.assertEqual(lldp_sys_name["moduleQualifiedName"], "LLDP-MIB::lldpRemSysName")

    @unittest.skipUnless(llm_configured(), "requires LLM_API_KEY, LLM_BASE_URL and LLM_MODEL")
    def test_repeated_questions_return_same_diagnosis_core(self) -> None:
        service = self.make_diagnosis_service()
        first = service.analyze("帮我分析当前故障", session_id="s1")
        second = service.analyze("重新诊断一下 leaf-01", session_id="s1")
        third = service.analyze("leaf-01 为什么业务不通", session_id="s2")

        self.assertEqual(project_comparison_fields(first), project_comparison_fields(second))
        self.assertEqual(project_comparison_fields(first), project_comparison_fields(third))
        self.assertEqual(service.cache_size(), 1)

    @unittest.skipUnless(llm_configured(), "requires LLM_API_KEY, LLM_BASE_URL and LLM_MODEL")
    def test_consistency_score_passes_single_and_multi_session(self) -> None:
        service = self.make_diagnosis_service()
        result = run_consistency_test(service, run_count=8)

        self.assertTrue(result["passed"])
        self.assertEqual(result["overall_consistency_score"], 1.0)
        for mode in result["mode_results"]:
            self.assertEqual(mode["score"], 1.0)
            self.assertEqual(mode["consistent_runs"], mode["total_runs"])

    @unittest.skipUnless(llm_configured(), "requires LLM_API_KEY, LLM_BASE_URL and LLM_MODEL")
    def test_agent_chat_keeps_session_history_and_tool_trace(self) -> None:
        diagnosis_service = self.make_diagnosis_service()
        agent = AgentService(diagnosis_service)

        first = agent.chat("帮我分析当前故障", session_id="agent-session-1")
        second = agent.chat("换个问法，leaf-01 为什么不通", session_id="agent-session-1")
        session = agent.get_session("agent-session-1")

        self.assertEqual(first["diagnosis"]["fault_fingerprint"], second["diagnosis"]["fault_fingerprint"])
        self.assertEqual(first["diagnosis"]["fault_type"], second["diagnosis"]["fault_type"])
        self.assertEqual(len(session["history"]), 4)
        self.assertGreaterEqual(len(second["tool_trace"]), 5)
        self.assertIn("结论：", second["message"]["content"])


if __name__ == "__main__":
    unittest.main()
