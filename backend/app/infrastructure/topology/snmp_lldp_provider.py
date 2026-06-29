from __future__ import annotations

import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from ..mib.profile_registry import MibProfileRegistry
from .snmp_client import PysnmpWalkClient, SnmpWalkClient


ConfigProvider = Callable[[], dict[str, Any]]


DEFAULT_MIB_PROFILE = "snmp_lldp"

REQUIRED_OID_BINDINGS = [
    "sys_descr",
    "sys_name",
    "if_name",
    "if_admin_status",
    "if_oper_status",
    "lldp_loc_port_id",
    "lldp_loc_port_desc",
    "lldp_rem_chassis_id",
    "lldp_rem_port_id",
    "lldp_rem_port_desc",
    "lldp_rem_sys_name",
]


class SnmpLldpTopologyProvider:
    mode = "snmp_lldp"

    def __init__(
        self,
        snmp_client: SnmpWalkClient | None = None,
        timeout_seconds: int = 8,
        profile_registry: MibProfileRegistry | None = None,
        default_profile_id: str = DEFAULT_MIB_PROFILE,
        config_provider: ConfigProvider | None = None,
    ) -> None:
        self._snmp_client = snmp_client or PysnmpWalkClient()
        self._timeout_seconds = timeout_seconds
        self._profile_registry = profile_registry or MibProfileRegistry()
        self._default_profile_id = default_profile_id
        self._config_provider = config_provider

    def metadata(self) -> dict[str, Any]:
        config = self._runtime_config()
        return {
            "mode": self.mode,
            "description": "通过配置的管理网段或 seed IP 主动 SNMP 探测设备，再读取 IF-MIB/LLDP-MIB 生成拓扑。",
            "requires_payload": False,
            "protocols": ["SNMPv2c", "IF-MIB", "LLDP-MIB"],
            "configured_targets": config.get("targets") or [],
            "configured_scan_cidrs": config.get("scan_cidrs") or [],
            "mib_profiles": self._profile_registry.get_provider_profiles(self.mode),
        }

    def discover(self, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = self._effective_options(options)
        community = options.get("community") or "public"
        timeout_seconds = float(options.get("timeout_seconds") or self._timeout_seconds)
        scan_timeout_seconds = float(options.get("scan_timeout_seconds") or timeout_seconds)
        profile_id = options.get("profile_id") or self._default_profile_id
        profile = self._profile_registry.get_profile(profile_id)
        oids = self._validated_oid_bindings(profile)
        targets, target_summary = self._resolve_targets(
            options=options,
            community=community,
            timeout_seconds=scan_timeout_seconds,
            sys_name_oid=oids["sys_name"],
        )

        snapshots = []
        for target in targets:
            snapshots.append(
                self._collect_target(
                    target=target,
                    community=community,
                    timeout_seconds=timeout_seconds,
                    oids=oids,
                )
            )

        nodes = [self._node_from_snapshot(snapshot) for snapshot in snapshots]
        edges = self._edges_from_snapshots(snapshots)

        return {
            "id": "snmp-lldp-discovered-topology",
            "name": "SNMP LLDP Discovered Topology",
            "nodes": sorted(nodes, key=lambda item: item["id"]),
            "edges": sorted(edges, key=lambda item: (item["source"], item["target"], item.get("source_interface") or "")),
            "discovery": {
                "mode": self.mode,
                "source": "SnmpLldpTopologyProvider",
                "protocols": profile.get("protocols") or ["SNMPv2c", "IF-MIB", "LLDP-MIB"],
                "targets": targets,
                **target_summary,
                "mib_profile_id": profile_id,
                "mib_profile": profile.get("display_name") or profile_id,
                "note": "先按配置的 targets 或 scan_cidrs 主动 SNMP 探测设备，再通过 MIB profile 声明的 OID 生成拓扑。",
            },
        }

    def _runtime_config(self) -> dict[str, Any]:
        if not self._config_provider:
            return {}
        return self._config_provider() or {}

    def _effective_options(self, options: dict[str, Any] | None) -> dict[str, Any]:
        effective = self._runtime_config()
        effective.update(options or {})
        return effective

    def _resolve_targets(
        self,
        options: dict[str, Any],
        community: str,
        timeout_seconds: float,
        sys_name_oid: str,
    ) -> tuple[list[str], dict[str, Any]]:
        explicit_targets = normalize_list(options.get("targets"))
        if explicit_targets:
            return explicit_targets, {
                "target_source": "explicit_targets",
                "scan_enabled": False,
                "scan_cidrs": [],
                "scan_candidate_count": 0,
                "scan_responsive_count": len(explicit_targets),
            }

        scan_cidrs = normalize_list(options.get("scan_cidrs"))
        if not options.get("scan_enabled", True) or not scan_cidrs:
            raise ValueError("SNMP 拓扑发现未配置目标。请在设置中配置 seed IP 或管理网段 CIDR。")

        candidates = expand_cidrs(scan_cidrs, max_hosts=int(options.get("max_scan_hosts") or 256))
        if not candidates:
            raise ValueError("管理网段未展开出可扫描地址。请检查 CIDR 配置。")

        responsive_targets = self._scan_targets(
            candidates=candidates,
            community=community,
            timeout_seconds=timeout_seconds,
            sys_name_oid=sys_name_oid,
            max_workers=int(options.get("scan_concurrency") or 12),
        )
        if not responsive_targets:
            raise ValueError("管理网段内没有发现 SNMP 可达设备。请检查 community、网络连通性和防火墙。")

        return responsive_targets, {
            "target_source": "cidr_scan",
            "scan_enabled": True,
            "scan_cidrs": scan_cidrs,
            "scan_candidate_count": len(candidates),
            "scan_responsive_count": len(responsive_targets),
        }

    def _scan_targets(
        self,
        candidates: list[str],
        community: str,
        timeout_seconds: float,
        sys_name_oid: str,
        max_workers: int,
    ) -> list[str]:
        responsive_targets = []
        workers = max(1, min(max_workers, 64, len(candidates)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._probe_snmp_sys_name, target, community, timeout_seconds, sys_name_oid): target
                for target in candidates
            }
            for future in as_completed(futures):
                target = futures[future]
                try:
                    if future.result():
                        responsive_targets.append(target)
                except Exception:
                    continue
        return sorted(dict.fromkeys(responsive_targets), key=ip_sort_key)

    def _probe_snmp_sys_name(
        self,
        target: str,
        community: str,
        timeout_seconds: float,
        sys_name_oid: str,
    ) -> bool:
        try:
            output = self._snmp_client.walk(target, community, sys_name_oid, timeout_seconds)
            return bool(first_value(parse_snmp_output(output)))
        except Exception:
            return False

    def _collect_target(
        self,
        target: str,
        community: str,
        timeout_seconds: float,
        oids: dict[str, str],
    ) -> dict[str, Any]:
        sys_name = first_value(parse_snmp_output(self._snmp_client.walk(target, community, oids["sys_name"], timeout_seconds)))
        sys_descr = first_value(parse_snmp_output(self._snmp_client.walk(target, community, oids["sys_descr"], timeout_seconds)))
        if_names = indexed_values(
            parse_snmp_output(self._snmp_client.walk(target, community, oids["if_name"], timeout_seconds)), oids["if_name"]
        )
        if_admin_status = {
            index: normalize_if_status(value)
            for index, value in indexed_values(
                parse_snmp_output(self._snmp_client.walk(target, community, oids["if_admin_status"], timeout_seconds)),
                oids["if_admin_status"],
            ).items()
        }
        if_status = {
            index: normalize_if_status(value)
            for index, value in indexed_values(
                parse_snmp_output(self._snmp_client.walk(target, community, oids["if_oper_status"], timeout_seconds)),
                oids["if_oper_status"],
            ).items()
        }
        interfaces = {
            index: {
                "if_index": index,
                "name": name,
                "admin_status": if_admin_status.get(index, "unknown"),
                "oper_status": if_status.get(index, "unknown"),
            }
            for index, name in if_names.items()
        }
        interface_status_by_name = {
            item["name"]: item["oper_status"] for item in interfaces.values() if item.get("name")
        }

        loc_port_ids = indexed_values(
            parse_snmp_output(self._snmp_client.walk(target, community, oids["lldp_loc_port_id"], timeout_seconds)),
            oids["lldp_loc_port_id"],
        )
        loc_port_desc = indexed_values(
            parse_snmp_output(self._snmp_client.walk(target, community, oids["lldp_loc_port_desc"], timeout_seconds)),
            oids["lldp_loc_port_desc"],
        )
        rem_sys_names = parse_lldp_remote_table(
            self._snmp_client.walk(target, community, oids["lldp_rem_sys_name"], timeout_seconds), oids["lldp_rem_sys_name"]
        )
        rem_port_ids = parse_lldp_remote_table(
            self._snmp_client.walk(target, community, oids["lldp_rem_port_id"], timeout_seconds), oids["lldp_rem_port_id"]
        )
        rem_port_desc = parse_lldp_remote_table(
            self._snmp_client.walk(target, community, oids["lldp_rem_port_desc"], timeout_seconds),
            oids["lldp_rem_port_desc"],
        )
        rem_chassis = parse_lldp_remote_table(
            self._snmp_client.walk(target, community, oids["lldp_rem_chassis_id"], timeout_seconds),
            oids["lldp_rem_chassis_id"],
        )

        device_id = sys_name or target
        neighbors = []
        for suffix, remote_name in rem_sys_names.items():
            local_port_num = suffix.split(".")[-2] if suffix.count(".") >= 2 else ""
            local_interface = loc_port_ids.get(local_port_num) or loc_port_desc.get(local_port_num)
            neighbors.append(
                {
                    "local_port_num": local_port_num,
                    "local_interface": local_interface,
                    "remote_sys_name": remote_name,
                    "remote_chassis": rem_chassis.get(suffix),
                    "remote_port": rem_port_ids.get(suffix) or rem_port_desc.get(suffix),
                    "oper_status": interface_status_by_name.get(local_interface, "unknown"),
                }
            )

        return {
            "target": target,
            "device_id": device_id,
            "sys_descr": sys_descr,
            "interfaces": list(interfaces.values()),
            "neighbors": neighbors,
        }

    def _node_from_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        device_id = snapshot["device_id"]
        return {
            "id": device_id,
            "label": device_id,
            "role": infer_role(device_id),
            "status": "up",
            "management_ip": snapshot["target"],
            "sys_descr": snapshot["sys_descr"],
            "interfaces": snapshot["interfaces"],
            "discovery_source": "snmp",
        }

    def _edges_from_snapshots(self, snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        known_nodes = {snapshot["device_id"] for snapshot in snapshots}
        interface_status = {
            snapshot["device_id"]: {
                interface["name"]: interface["oper_status"]
                for interface in snapshot.get("interfaces", [])
                if interface.get("name")
            }
            for snapshot in snapshots
        }
        edge_by_key: dict[tuple[str, str], dict[str, Any]] = {}

        for snapshot in snapshots:
            source = snapshot["device_id"]
            for neighbor in snapshot["neighbors"]:
                target = neighbor.get("remote_sys_name") or neighbor.get("remote_chassis")
                if not target:
                    continue
                left, right = sorted([source, target])
                key = (left, right)
                edge = edge_by_key.setdefault(
                    key,
                    {
                        "source": left,
                        "target": right,
                        "status": "up",
                        "protocol": "snmp-lldp",
                        "discovery": "LLDP-MIB",
                    },
                )
                if source == edge["source"]:
                    edge["source_interface"] = neighbor.get("local_interface")
                    edge["target_interface"] = neighbor.get("remote_port")
                else:
                    edge["target_interface"] = neighbor.get("local_interface")
                    edge["source_interface"] = neighbor.get("remote_port")
                if neighbor.get("oper_status") == "down":
                    edge["status"] = "down"
                if target not in known_nodes:
                    edge["remote_unmanaged"] = True

        for edge in edge_by_key.values():
            statuses = [
                interface_status.get(edge["source"], {}).get(edge.get("source_interface")),
                interface_status.get(edge["target"], {}).get(edge.get("target_interface")),
            ]
            if "down" in statuses:
                edge["status"] = "down"
            elif statuses and all(status == "up" for status in statuses if status):
                edge["status"] = "up"

        return list(edge_by_key.values())

    def _validated_oid_bindings(self, profile: dict[str, Any]) -> dict[str, str]:
        bindings = profile.get("oid_bindings") or {}
        missing = [key for key in REQUIRED_OID_BINDINGS if not bindings.get(key)]
        if missing:
            raise ValueError(f"MIB profile {profile.get('id')} 缺少 OID 绑定: {', '.join(missing)}")
        return {key: normalize_oid(str(bindings[key])) for key in REQUIRED_OID_BINDINGS}


def parse_snmp_output(output: str) -> list[tuple[str, str]]:
    rows = []
    for line in output.splitlines():
        if "No Such" in line or "NoSuch" in line or "Timeout:" in line:
            continue
        if " = " not in line:
            continue
        oid, raw_value = line.split(" = ", 1)
        rows.append((normalize_oid(oid), clean_snmp_value(raw_value)))
    return rows


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.replace(",", "\n").replace(";", "\n").splitlines()
    elif isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = [value]
    items = [str(item).strip() for item in raw_items if str(item).strip()]
    return list(dict.fromkeys(items))


def expand_cidrs(cidrs: list[str], max_hosts: int) -> list[str]:
    candidates = []
    for cidr in cidrs:
        network = ipaddress.ip_network(cidr, strict=False)
        for ip_address in network.hosts():
            candidates.append(str(ip_address))
            if len(candidates) >= max_hosts:
                return candidates
    return candidates


def ip_sort_key(value: str) -> tuple[int, Any]:
    try:
        return (0, ipaddress.ip_address(value))
    except ValueError:
        return (1, value)


def parse_lldp_remote_table(output: str, base_oid: str) -> dict[str, str]:
    values = {}
    base = normalize_oid(base_oid)
    for oid, value in parse_snmp_output(output):
        if not oid.startswith(base + "."):
            continue
        values[oid[len(base) + 1 :]] = value
    return values


def indexed_values(rows: list[tuple[str, str]], base_oid: str) -> dict[str, str]:
    values = {}
    base = normalize_oid(base_oid)
    for oid, value in rows:
        if oid.startswith(base + "."):
            values[oid[len(base) + 1 :]] = value
    return values


def first_value(rows: list[tuple[str, str]]) -> str | None:
    return rows[0][1] if rows else None


def clean_snmp_value(raw_value: str) -> str:
    value = raw_value.strip()
    if ": " in value:
        value = value.split(": ", 1)[1]
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    return value


def normalize_oid(oid: str) -> str:
    return "." + oid.strip().lstrip(".")


def normalize_if_status(value: str) -> str:
    lowered = value.lower()
    if lowered.startswith("1") or "up" in lowered:
        return "up"
    if lowered.startswith("2") or "down" in lowered:
        return "down"
    return "unknown"


def infer_role(device_id: str) -> str:
    lowered = device_id.lower()
    if "spine" in lowered:
        return "spine"
    if "leaf" in lowered:
        return "leaf"
    return "router"
