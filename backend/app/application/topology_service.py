from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any, Protocol

from ..infrastructure.collectors.base import ObservationCollector


LIVE_DISCOVERY_PROTOCOLS = {
    "device_identity": ["SNMP sysName/sysObjectID", "NETCONF ietf-system", "gNMI system paths"],
    "interfaces": ["SNMP IF-MIB/IF-XTable", "NETCONF ietf-interfaces", "gRPC/gNMI Telemetry"],
    "layer2_links": ["SNMP LLDP-MIB lldpRemTable", "vendor NDP/CDP equivalents"],
    "layer3_links": ["BGP-LS", "BMP", "routing neighbor tables"],
}


class TopologyDiscoveryProvider(Protocol):
    mode: str

    def metadata(self) -> dict[str, Any]:
        ...

    def discover(self, options: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


class TopologyService:
    """Application service for discovered topology state.

    The service deliberately keeps topology discovery outside the frontend. The
    current collector and runtime providers return the same topology shape.
    """

    def __init__(
        self,
        collector: ObservationCollector,
        providers: list[TopologyDiscoveryProvider] | None = None,
    ) -> None:
        self._collector = collector
        self._providers = {provider.mode: provider for provider in providers or []}
        self._runtime_topology: dict[str, Any] | None = None
        self._interface_status_overrides: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = RLock()

    def current_topology(self) -> dict[str, Any]:
        with self._lock:
            topology = deepcopy(self._runtime_topology) if self._runtime_topology else None
        if topology is None:
            topology = self._collector.get_topology()
        return self._with_discovery_summary(self._apply_interface_status_overrides(topology), refreshed=False)

    def discover(
        self,
        mode: str = "snmp_lldp",
        nodes: list[dict[str, Any]] | None = None,
        edges: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if mode == "manual":
            topology = self._manual_topology(nodes=nodes, edges=edges)
        elif mode in self._providers:
            topology = self._providers[mode].discover(options=options)
        else:
            raise ValueError(f"Unsupported topology discovery mode: {mode}")

        with self._lock:
            self._runtime_topology = deepcopy(topology)
        return self._with_discovery_summary(self._apply_interface_status_overrides(topology), refreshed=True)

    def apply_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("event_type") or "").upper()
        status_by_type = {
            "INTERFACE_OPER_DOWN": "down",
            "INTERFACE_OPER_UP": "up",
        }
        status = status_by_type.get(event_type)
        if not status:
            return

        device_id = normalize_key(event.get("device_id"))
        attributes = event.get("attributes") or {}
        interface = normalize_key(
            event.get("object")
            or attributes.get("if_name")
            or attributes.get("interface")
            or attributes.get("normalized_object")
        )
        if not device_id or not interface or device_id == "unknown-device" or interface == "unknown-interface":
            return

        with self._lock:
            self._interface_status_overrides[(device_id, interface)] = {
                "device_id": str(event.get("device_id") or ""),
                "interface": str(event.get("object") or attributes.get("if_name") or ""),
                "status": status,
                "event_type": event_type,
                "event_id": event.get("event_id"),
                "channel": event.get("channel"),
                "updated_at": event.get("timestamp") or event.get("received_at"),
            }

    def clear_event_overrides(self) -> None:
        with self._lock:
            self._interface_status_overrides.clear()

    def capabilities(self) -> dict[str, Any]:
        return {
            "supported_runtime_modes": [*sorted(self._providers.keys())],
            "providers": [
                *[self._providers[mode].metadata() for mode in sorted(self._providers.keys())],
            ],
            "live_discovery_protocols": LIVE_DISCOVERY_PROTOCOLS,
            "phase_note": "拓扑由当前厂商配置下的 SNMP LLDP-MIB 采集生成；第二阶段诊断事实来自 Syslog、SNMP Trap、Telemetry 等上报事件。",
        }

    def _manual_topology(
        self,
        nodes: list[dict[str, Any]] | None,
        edges: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        if not nodes:
            raise ValueError("Manual topology discovery requires at least one node")

        node_ids = set()
        normalized_nodes = []
        for node in nodes:
            node_id = str(node.get("id") or "").strip()
            if not node_id:
                raise ValueError("Every topology node requires an id")
            if node_id in node_ids:
                raise ValueError(f"Duplicate topology node id: {node_id}")
            node_ids.add(node_id)
            normalized_nodes.append(
                {
                    "id": node_id,
                    "label": node.get("label") or node.get("name") or node_id,
                    "role": node.get("role") or "unknown",
                    "status": node.get("status") or "unknown",
                    "management_ip": node.get("management_ip"),
                }
            )

        normalized_edges = []
        for edge in edges or []:
            source = str(edge.get("source") or "").strip()
            target = str(edge.get("target") or "").strip()
            if source not in node_ids or target not in node_ids:
                raise ValueError(f"Topology edge references unknown nodes: {source} -> {target}")
            normalized_edges.append(
                {
                    "source": source,
                    "target": target,
                    "source_interface": edge.get("source_interface"),
                    "target_interface": edge.get("target_interface"),
                    "status": edge.get("status") or "unknown",
                    "protocol": edge.get("protocol") or "manual",
                }
            )

        return {
            "id": "manual-runtime-topology",
            "name": "手工导入运行时拓扑",
            "nodes": normalized_nodes,
            "edges": normalized_edges,
            "discovery": {
                "mode": "manual",
                "source": "api_payload",
                "protocols": ["manual-import"],
                "note": "由页面或接口提交的实际环境节点和链路，不由前端写死。",
            },
        }

    def _with_discovery_summary(self, topology: dict[str, Any], refreshed: bool) -> dict[str, Any]:
        result = deepcopy(topology)
        nodes = result.get("nodes") or []
        edges = result.get("edges") or []
        groups = self._topology_groups(result)
        discovery = deepcopy(result.get("discovery") or {})
        discovery.setdefault("mode", "snmp_lldp")
        discovery.setdefault("source", "SnmpObservationCollector")
        discovery.setdefault("protocols", ["SNMPv2c", "IF-MIB", "LLDP-MIB"])
        discovery["node_count"] = len(nodes)
        discovery["edge_count"] = len(edges)
        discovery["group_count"] = len(groups)
        discovery["refreshed"] = refreshed
        discovery["live_protocols"] = LIVE_DISCOVERY_PROTOCOLS
        result["groups"] = groups
        result["discovery"] = discovery
        return result

    def _apply_interface_status_overrides(self, topology: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(topology)
        with self._lock:
            overrides = deepcopy(self._interface_status_overrides)
        if not overrides:
            return result

        for node in result.get("nodes") or []:
            device_id = normalize_key(node.get("id"))
            for interface in node.get("interfaces") or []:
                override = find_interface_override(
                    overrides,
                    device_id=device_id,
                    interface_name=interface.get("name"),
                    if_index=interface.get("if_index"),
                )
                if not override:
                    continue
                interface["oper_status"] = override["status"]
                interface["runtime_status"] = override["status"]
                interface["runtime_status_source"] = override["channel"]
                interface["runtime_status_event_id"] = override["event_id"]
                interface["runtime_status_updated_at"] = override["updated_at"]

        for edge in result.get("edges") or []:
            source_override = find_interface_override(
                overrides,
                device_id=edge.get("source"),
                interface_name=edge.get("source_interface"),
            )
            target_override = find_interface_override(
                overrides,
                device_id=edge.get("target"),
                interface_name=edge.get("target_interface"),
            )
            active_overrides = [item for item in [source_override, target_override] if item]
            if not active_overrides:
                continue
            status = "down" if any(item["status"] == "down" for item in active_overrides) else "up"
            latest = max(active_overrides, key=lambda item: str(item.get("updated_at") or ""))
            edge["status"] = status
            edge["runtime_status"] = status
            edge["runtime_status_source"] = latest.get("channel")
            edge["runtime_status_event_id"] = latest.get("event_id")
            edge["runtime_status_updated_at"] = latest.get("updated_at")

        discovery = dict(result.get("discovery") or {})
        discovery["runtime_status_overrides"] = len(overrides)
        discovery["runtime_status_updated_at"] = max(
            [str(item.get("updated_at") or "") for item in overrides.values()],
            default=None,
        )
        result["discovery"] = discovery
        return result

    def _topology_groups(self, topology: dict[str, Any]) -> list[dict[str, Any]]:
        explicit_groups = topology.get("groups")
        if explicit_groups:
            return self._normalize_explicit_groups(topology, explicit_groups)
        return self._connected_component_groups(topology)

    def _normalize_explicit_groups(
        self,
        topology: dict[str, Any],
        groups: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        node_ids = {str(node.get("id")) for node in topology.get("nodes") or [] if node.get("id")}
        edge_by_id = {self._edge_id(edge): edge for edge in topology.get("edges") or []}
        normalized = []

        for index, group in enumerate(groups, start=1):
            group_nodes = [str(node_id) for node_id in group.get("nodes", []) if str(node_id) in node_ids]
            group_node_set = set(group_nodes)
            group_edges = [
                edge_id
                for edge_id, edge in edge_by_id.items()
                if edge_id in set(group.get("edges", []))
                or {edge.get("source"), edge.get("target")}.issubset(group_node_set)
            ]
            normalized.append(
                {
                    "id": str(group.get("id") or f"group-{index}"),
                    "name": group.get("name") or self._group_name(index, group_nodes),
                    "nodes": sorted(group_nodes),
                    "edges": sorted(group_edges),
                    "node_count": len(group_nodes),
                    "edge_count": len(group_edges),
                    "source": group.get("source") or "explicit",
                }
            )

        return normalized

    def _connected_component_groups(self, topology: dict[str, Any]) -> list[dict[str, Any]]:
        nodes = topology.get("nodes") or []
        edges = topology.get("edges") or []
        node_ids = sorted(str(node.get("id")) for node in nodes if node.get("id"))
        adjacency = {node_id: set() for node_id in node_ids}
        edge_ids_by_node: dict[str, set[str]] = {node_id: set() for node_id in node_ids}

        for edge in edges:
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if source not in adjacency or target not in adjacency:
                continue
            edge_id = self._edge_id(edge)
            adjacency[source].add(target)
            adjacency[target].add(source)
            edge_ids_by_node[source].add(edge_id)
            edge_ids_by_node[target].add(edge_id)

        groups = []
        visited = set()
        for node_id in node_ids:
            if node_id in visited:
                continue
            stack = [node_id]
            component_nodes = set()
            component_edges = set()
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                component_nodes.add(current)
                component_edges.update(edge_ids_by_node.get(current, set()))
                stack.extend(sorted(adjacency.get(current, set()) - visited, reverse=True))

            sorted_nodes = sorted(component_nodes)
            group_index = len(groups) + 1
            groups.append(
                {
                    "id": f"group-{group_index}",
                    "name": self._group_name(group_index, sorted_nodes),
                    "nodes": sorted_nodes,
                    "edges": sorted(component_edges),
                    "node_count": len(sorted_nodes),
                    "edge_count": len(component_edges),
                    "source": "connected_components",
                }
            )

        groups.sort(key=lambda group: (-group["node_count"], group["name"]))
        for index, group in enumerate(groups, start=1):
            group["id"] = f"group-{index}"
            group["name"] = self._group_name(index, group["nodes"])
        return groups

    def _group_name(self, index: int, node_ids: list[str]) -> str:
        sample = "-".join(node_ids[:3])
        suffix = f" {sample}" if sample else ""
        return f"组网-{index}{suffix}"

    def _edge_id(self, edge: dict[str, Any]) -> str:
        return "|".join(
            [
                str(edge.get("source") or ""),
                str(edge.get("target") or ""),
                str(edge.get("source_interface") or ""),
                str(edge.get("target_interface") or ""),
                str(edge.get("protocol") or ""),
            ]
        )


def find_interface_override(
    overrides: dict[tuple[str, str], dict[str, Any]],
    *,
    device_id: Any,
    interface_name: Any = None,
    if_index: Any = None,
) -> dict[str, Any] | None:
    device_key = normalize_key(device_id)
    candidates = [normalize_key(interface_name)]
    if if_index is not None:
        candidates.extend([normalize_key(if_index), normalize_key(f"ifIndex-{if_index}")])
    for candidate in candidates:
        if not device_key or not candidate:
            continue
        override = overrides.get((device_key, candidate))
        if override:
            return override
    return None


def normalize_key(value: Any) -> str:
    return str(value or "").strip().lower()
