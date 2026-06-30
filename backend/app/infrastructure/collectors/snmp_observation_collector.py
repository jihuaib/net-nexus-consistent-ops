from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from ...application.correlation_engine import CorrelationEngine
from .base import ObservationCollector
from ..topology.snmp_lldp_provider import SnmpLldpTopologyProvider


class SnmpObservationCollector(ObservationCollector):
    """Live observation collector backed by SNMP topology discovery."""

    def __init__(
        self,
        topology_provider: SnmpLldpTopologyProvider,
        correlation_engine: CorrelationEngine | None = None,
    ) -> None:
        self._topology_provider = topology_provider
        self._correlation_engine = correlation_engine
        self._runtime_topology: dict[str, Any] | None = None

    def list_devices(self) -> list[dict[str, Any]]:
        return deepcopy(self.get_topology().get("nodes") or [])

    def get_topology(self) -> dict[str, Any]:
        if self._runtime_topology is None:
            self.refresh()
        return deepcopy(self._runtime_topology or empty_topology())

    def refresh(self) -> dict[str, Any]:
        try:
            self._runtime_topology = self._topology_provider.discover()
        except Exception as exc:
            self._runtime_topology = empty_topology(discovery_error=str(exc))
        return deepcopy(self._runtime_topology)

    def list_fault_cases(self) -> list[dict[str, Any]]:
        try:
            fault_case = self.get_fault_case("live-snmp-current")
        except ValueError:
            return []
        return [
            {
                "id": fault_case["id"],
                "title": fault_case["title"],
                "description": fault_case["description"],
                "data_source": fault_case["data_source"],
            }
        ]

    def get_fault_case(self, fault_case_id: str) -> dict[str, Any]:
        topology = self.refresh()
        if not self._correlation_engine:
            raise ValueError("当前未配置上报事件关联引擎，无法根据上报信息生成诊断")

        correlation = self._correlation_engine.correlate_current_fault(topology=topology)
        primary = correlation.get("primary")
        if not primary:
            return no_active_fault_case(
                fault_case_id=fault_case_id,
                topology=topology,
                correlation=correlation,
            )

        event_observations = correlation["observations"]
        timestamp = datetime.now(timezone.utc).isoformat()
        return {
            "id": fault_case_id or "live-snmp-current",
            "topology_id": topology.get("id") or "snmp-live-topology",
            "title": f"{primary['device_id']} {primary['name']} 上报异常",
            "description": "由 Syslog、SNMP Trap、Telemetry 等上报事件生成；SNMP/LLDP 仅作为拓扑上下文。",
            "data_source": "reported_events",
            "primary_device": primary["device_id"],
            "primary_interface": primary["name"],
            "observations": {
                "timestamp": timestamp,
                "interfaces": event_observations["interfaces"],
                "syslogs": event_observations["syslogs"],
                "bgp_neighbors": event_observations["bgp_neighbors"],
                "routes": event_observations["routes"],
                "fib_entries": event_observations["fib_entries"],
                "service_checks": event_observations["service_checks"],
                "reported_events": correlation["events"],
                "correlation": correlation["summary"],
            },
        }


def empty_topology(discovery_error: str | None = None) -> dict[str, Any]:
    discovery: dict[str, Any] = {
        "mode": "snmp_lldp",
        "source": "SnmpObservationCollector",
        "protocols": ["SNMPv2c", "IF-MIB", "LLDP-MIB"],
        "degraded": True,
        "note": "SNMP/LLDP 拓扑暂不可用；诊断仍可基于 Syslog、SNMP Trap、Telemetry 上报事件继续进行。",
    }
    if discovery_error:
        discovery["error"] = discovery_error
    return {
        "id": "snmp-live-topology-empty",
        "name": "SNMP Live Topology",
        "nodes": [],
        "edges": [],
        "discovery": discovery,
        }


def no_active_fault_case(
    *,
    fault_case_id: str,
    topology: dict[str, Any],
    correlation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": fault_case_id or "live-snmp-current",
        "topology_id": topology.get("id") or "snmp-live-topology",
        "title": "当前未发现活动故障",
        "description": "当前事件窗口内没有未恢复的 Syslog、SNMP Trap 或 Telemetry 故障上报；历史事件仅作为上下文保留。",
        "data_source": "reported_events",
        "state": "no_active_fault",
        "primary_device": None,
        "primary_interface": None,
        "observations": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "interfaces": [],
            "syslogs": [],
            "bgp_neighbors": [],
            "routes": [],
            "fib_entries": [],
            "service_checks": [],
            "reported_events": correlation.get("events", []),
            "correlation": correlation.get("summary", {}),
        },
    }
