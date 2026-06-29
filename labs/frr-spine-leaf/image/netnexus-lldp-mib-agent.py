#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys


LLDP_BASE = ".1.0.8802.1.1.2"
LLDP_LOC_PORT_ID = LLDP_BASE + ".1.3.7.1.3"
LLDP_LOC_PORT_DESC = LLDP_BASE + ".1.3.7.1.4"
LLDP_REM_CHASSIS_ID = LLDP_BASE + ".1.4.1.1.5"
LLDP_REM_PORT_ID = LLDP_BASE + ".1.4.1.1.7"
LLDP_REM_PORT_DESC = LLDP_BASE + ".1.4.1.1.8"
LLDP_REM_SYS_NAME = LLDP_BASE + ".1.4.1.1.9"


LAB_LINKS = {
    "spine-01": [
        {
            "local_port_num": 1,
            "local_interface": "eth0",
            "remote_chassis": "leaf-01",
            "remote_port": "eth1",
            "remote_sys_name": "leaf-01",
        },
        {
            "local_port_num": 2,
            "local_interface": "eth1",
            "remote_chassis": "leaf-02",
            "remote_port": "eth1",
            "remote_sys_name": "leaf-02",
        },
    ],
    "leaf-01": [
        {
            "local_port_num": 1,
            "local_interface": "eth1",
            "remote_chassis": "spine-01",
            "remote_port": "eth0",
            "remote_sys_name": "spine-01",
        }
    ],
    "leaf-02": [
        {
            "local_port_num": 1,
            "local_interface": "eth1",
            "remote_chassis": "spine-01",
            "remote_port": "eth1",
            "remote_sys_name": "spine-01",
        }
    ],
}


def main() -> None:
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        command = line.strip()
        if command == "PING":
            write("PONG")
        elif command == "get":
            oid = sys.stdin.readline().strip()
            handle_get(oid)
        elif command == "getnext":
            oid = sys.stdin.readline().strip()
            handle_getnext(oid)
        else:
            write("NONE")


def handle_get(oid: str) -> None:
    oid_map = build_oid_map()
    value = oid_map.get(normalize_oid(oid))
    if not value:
        write("NONE")
        return
    write_oid_value(oid, value)


def handle_getnext(oid: str) -> None:
    oid_map = build_oid_map()
    requested = oid_to_tuple(normalize_oid(oid))
    for candidate in sorted(oid_map.keys(), key=oid_to_tuple):
        if oid_to_tuple(candidate) > requested:
            write_oid_value(candidate, oid_map[candidate])
            return
    write("NONE")


def build_oid_map() -> dict[str, tuple[str, str]]:
    device = os.getenv("NETNEXUS_DEVICE") or os.uname().nodename
    links = LAB_LINKS.get(device, [])
    oid_map: dict[str, tuple[str, str]] = {}

    for link in links:
        local_port_num = link["local_port_num"]
        local_interface = link["local_interface"]
        oid_map[f"{LLDP_LOC_PORT_ID}.{local_port_num}"] = ("string", local_interface)
        oid_map[f"{LLDP_LOC_PORT_DESC}.{local_port_num}"] = ("string", local_interface)

        if not interface_is_up(local_interface):
            continue

        suffix = f"0.{local_port_num}.1"
        oid_map[f"{LLDP_REM_CHASSIS_ID}.{suffix}"] = ("string", link["remote_chassis"])
        oid_map[f"{LLDP_REM_PORT_ID}.{suffix}"] = ("string", link["remote_port"])
        oid_map[f"{LLDP_REM_PORT_DESC}.{suffix}"] = ("string", link["remote_port"])
        oid_map[f"{LLDP_REM_SYS_NAME}.{suffix}"] = ("string", link["remote_sys_name"])

    return oid_map


def interface_is_up(interface_name: str) -> bool:
    try:
        result = subprocess.run(
            ["ip", "-j", "link", "show", "dev", interface_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1,
        )
    except Exception:
        return False
    return '"operstate":"UP"' in result.stdout or '"operstate": "UP"' in result.stdout


def normalize_oid(oid: str) -> str:
    return "." + oid.strip().lstrip(".")


def oid_to_tuple(oid: str) -> tuple[int, ...]:
    return tuple(int(part) for part in oid.strip(".").split(".") if part)


def write_oid_value(oid: str, value: tuple[str, str]) -> None:
    value_type, raw_value = value
    write(normalize_oid(oid))
    write(value_type)
    write(raw_value)


def write(message: str) -> None:
    sys.stdout.write(message + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
