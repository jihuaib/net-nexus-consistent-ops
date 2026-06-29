from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_FILE = Path(__file__).resolve().parents[4] / ".netnexus" / "topology_discovery_config.json"


class TopologyDiscoveryConfigStore:
    def __init__(self, config_file: Path | None = None) -> None:
        self._config_file = config_file or Path(os.getenv("NETNEXUS_DISCOVERY_CONFIG_FILE", DEFAULT_CONFIG_FILE))

    def get_config(self) -> dict[str, Any]:
        config = self._default_config()
        config.update(self._read_config_file())
        return sanitize_config(config)

    def update_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        config = self.get_config()
        config.update({key: value for key, value in patch.items() if value is not None})
        sanitized = sanitize_config(config)
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        self._config_file.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
        return sanitized

    def _read_config_file(self) -> dict[str, Any]:
        if not self._config_file.exists():
            return {}
        try:
            raw = json.loads(self._config_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _default_config(self) -> dict[str, Any]:
        return {
            "profile_id": os.getenv("NETNEXUS_SNMP_PROFILE_ID", "snmp_lldp"),
            "community": os.getenv("NETNEXUS_SNMP_COMMUNITY", "public"),
            "targets": split_list(os.getenv("NETNEXUS_SNMP_TARGETS", "")),
            "scan_cidrs": split_list(os.getenv("NETNEXUS_SNMP_SCAN_CIDRS", "")),
            "scan_enabled": env_bool("NETNEXUS_SNMP_SCAN_ENABLED", True),
            "timeout_seconds": env_float("NETNEXUS_SNMP_TIMEOUT_SECONDS", 3.0),
            "scan_timeout_seconds": env_float("NETNEXUS_SNMP_SCAN_TIMEOUT_SECONDS", 1.5),
            "scan_concurrency": env_int("NETNEXUS_SNMP_SCAN_CONCURRENCY", 12),
            "max_scan_hosts": env_int("NETNEXUS_SNMP_MAX_SCAN_HOSTS", 256),
        }


def sanitize_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_id": non_empty_string(config.get("profile_id"), "snmp_lldp"),
        "community": non_empty_string(config.get("community"), "public"),
        "targets": normalize_targets(config.get("targets")),
        "scan_cidrs": normalize_cidrs(config.get("scan_cidrs")),
        "scan_enabled": bool(config.get("scan_enabled", True)),
        "timeout_seconds": clamp_float(config.get("timeout_seconds"), default=3.0, minimum=0.2, maximum=60.0),
        "scan_timeout_seconds": clamp_float(
            config.get("scan_timeout_seconds"), default=1.5, minimum=0.2, maximum=30.0
        ),
        "scan_concurrency": clamp_int(config.get("scan_concurrency"), default=12, minimum=1, maximum=64),
        "max_scan_hosts": clamp_int(config.get("max_scan_hosts"), default=256, minimum=1, maximum=4096),
    }


def normalize_targets(value: Any) -> list[str]:
    return split_list(value)


def normalize_cidrs(value: Any) -> list[str]:
    cidrs = []
    for item in split_list(value):
        try:
            cidrs.append(str(ipaddress.ip_network(item, strict=False)))
        except ValueError as exc:
            raise ValueError(f"无效管理网段 CIDR: {item}") from exc
    return sorted(dict.fromkeys(cidrs))


def split_list(value: Any) -> list[str]:
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


def non_empty_string(value: Any, default: str) -> str:
    normalized = str(value or "").strip()
    return normalized or default


def clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, minimum), maximum)


def clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, minimum), maximum)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
