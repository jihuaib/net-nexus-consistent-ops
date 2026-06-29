#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import os
import select
import socket
import subprocess
import time
from pathlib import Path


DEVICE = os.getenv("NETNEXUS_DEVICE") or socket.gethostname()
COMMUNITY = os.getenv("SNMP_COMMUNITY", "public")
SYSLOG_PORT = int(os.getenv("NETNEXUS_SYSLOG_PORT", "1514"))
TRAP_PORT = int(os.getenv("NETNEXUS_TRAP_PORT", "1162"))
INTERFACE_PATTERN = os.getenv("NETNEXUS_LINK_INTERFACES", "eth*")
POLL_SECONDS = float(os.getenv("NETNEXUS_LINK_POLL_SECONDS", "0.2"))

LINK_DOWN_OID = ".1.3.6.1.6.3.1.1.5.3"
LINK_UP_OID = ".1.3.6.1.6.3.1.1.5.4"
SYS_NAME_OID = ".1.3.6.1.2.1.1.5.0"
IF_INDEX_BASE = ".1.3.6.1.2.1.2.2.1.1"
IF_DESCR_BASE = ".1.3.6.1.2.1.2.2.1.2"
IF_ADMIN_STATUS_BASE = ".1.3.6.1.2.1.2.2.1.7"
IF_OPER_STATUS_BASE = ".1.3.6.1.2.1.2.2.1.8"
IF_NAME_BASE = ".1.3.6.1.2.1.31.1.1.1.1"


def resolve_ipv4_host(host: str, port: int) -> str:
    try:
        results = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:
        return host
    return results[0][4][0] if results else host


COLLECTOR_HOST = resolve_ipv4_host(os.getenv("NETNEXUS_EVENT_COLLECTOR_HOST", "host.docker.internal"), SYSLOG_PORT)


def main() -> None:
    previous = snapshot()
    monitor = start_link_monitor()
    while True:
        if monitor and monitor.poll() is not None:
            log_error("ip monitor link exited; restarting")
            monitor = start_link_monitor()

        event = read_link_event(monitor, timeout=POLL_SECONDS)
        if event:
            name, state = event
            old_state = previous.get(name)
            if old_state != state:
                emit_link_event(name, state)
                previous[name] = state
            continue

        time.sleep(POLL_SECONDS)
        current = snapshot()
        for name, state in current.items():
            old_state = previous.get(name)
            if old_state is None or old_state == state:
                continue
            emit_link_event(name, state)
        previous = current


def snapshot() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in Path("/sys/class/net").iterdir():
        name = path.name
        if not is_tracked_interface(name):
            continue
        result[name] = normalized_oper_state(path)
    return result


def start_link_monitor() -> subprocess.Popen[str] | None:
    try:
        return subprocess.Popen(
            ["ip", "monitor", "link"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        log_error(f"ip monitor link unavailable; using polling only: {exc}")
        return None


def read_link_event(monitor: subprocess.Popen[str] | None, *, timeout: float) -> tuple[str, str] | None:
    if not monitor or not monitor.stdout:
        return None
    ready, _, _ = select.select([monitor.stdout], [], [], timeout)
    if not ready:
        return None
    line = monitor.stdout.readline()
    if not line:
        return None
    return parse_link_event(line)


def parse_link_event(line: str) -> tuple[str, str] | None:
    parts = line.split(":", 2)
    if len(parts) < 2:
        return None
    name = parts[1].strip().split("@", 1)[0]
    if not is_tracked_interface(name):
        return None
    if "state UP" in line:
        return name, "up"
    if "state DOWN" in line or "state LOWERLAYERDOWN" in line:
        return name, "down"
    flags = line.split("<", 1)[1].split(">", 1)[0] if "<" in line and ">" in line else ""
    return (name, "up") if "UP" in flags.split(",") else (name, "down")


def is_tracked_interface(name: str) -> bool:
    return name != "lo" and fnmatch.fnmatch(name, INTERFACE_PATTERN)


def normalized_oper_state(path: Path) -> str:
    try:
        state = (path / "operstate").read_text(encoding="utf-8").strip().lower()
    except OSError:
        return "unknown"
    return "up" if state == "up" else "down"


def emit_link_event(interface: str, state: str) -> None:
    if_index = read_interface_index(interface)
    send_syslog(interface, state, if_index)
    send_trap(interface, state, if_index)


def read_interface_index(interface: str) -> str:
    try:
        return Path(f"/sys/class/net/{interface}/ifindex").read_text(encoding="utf-8").strip()
    except OSError:
        return "0"


def send_syslog(interface: str, state: str, if_index: str) -> None:
    event = "LINK_UP" if state == "up" else "LINK_DOWN"
    severity = "info" if state == "up" else "warning"
    timestamp = time.strftime("%b %e %H:%M:%S")
    message = (
        f"<134>{timestamp} {DEVICE} netnexus-link-event: "
        f"event={event} severity={severity} device={DEVICE} interface={interface} "
        f"ifIndex={if_index} ifOperStatus={state} source=frr-lab"
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        try:
            sock.sendto(message.encode("utf-8"), (COLLECTOR_HOST, SYSLOG_PORT))
        except OSError as exc:
            log_error(f"syslog send failed interface={interface} state={state}: {exc}")
    finally:
        sock.close()


def send_trap(interface: str, state: str, if_index: str) -> None:
    trap_oid = LINK_UP_OID if state == "up" else LINK_DOWN_OID
    oper_status = "1" if state == "up" else "2"
    admin_status = oper_status
    target = f"{COLLECTOR_HOST}:{TRAP_PORT}"
    env = dict(os.environ)
    env.setdefault("SNMP_PERSISTENT_DIR", "/tmp/net-snmp-persist")
    Path(env["SNMP_PERSISTENT_DIR"]).mkdir(parents=True, exist_ok=True)
    command = [
        "snmptrap",
        "-v",
        "2c",
        "-c",
        COMMUNITY,
        target,
        "",
        trap_oid,
        f"{SYS_NAME_OID}",
        "s",
        DEVICE,
        f"{IF_INDEX_BASE}.{if_index}",
        "i",
        if_index,
        f"{IF_DESCR_BASE}.{if_index}",
        "s",
        interface,
        f"{IF_ADMIN_STATUS_BASE}.{if_index}",
        "i",
        admin_status,
        f"{IF_OPER_STATUS_BASE}.{if_index}",
        "i",
        oper_status,
        f"{IF_NAME_BASE}.{if_index}",
        "s",
        interface,
    ]
    try:
        subprocess.run(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except OSError as exc:
        log_error(f"trap send failed interface={interface} state={state}: {exc}")


def log_error(message: str) -> None:
    print(f"netnexus-link-event-agent: {message}", flush=True)


if __name__ == "__main__":
    main()
