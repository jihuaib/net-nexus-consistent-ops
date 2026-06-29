from __future__ import annotations

import socket
from threading import Event, Thread
from typing import Any

from ...application.event_normalizer import normalize_reported_event, parse_payload
from ...application.event_store import EventStore
from .snmp_trap_decoder import decode_snmp_trap_packet


class UdpEventReceiver:
    channel = "udp"

    def __init__(
        self,
        event_store: EventStore,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        enabled: bool = True,
    ) -> None:
        self._event_store = event_store
        self._host = host
        self._port = port
        self._enabled = enabled
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._socket: socket.socket | None = None
        self._status: dict[str, Any] = {
            "channel": self.channel,
            "enabled": enabled,
            "running": False,
            "host": host,
            "port": port,
            "error": None,
            "received": 0,
        }

    def start(self) -> None:
        if not self._enabled or self._thread:
            return
        self._thread = Thread(target=self._run, name=f"netnexus-{self.channel}-receiver", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self._status["running"] = False

    def status(self) -> dict[str, Any]:
        return dict(self._status)

    def ingest_text(self, text: str, source_ip: str | None = None) -> dict[str, Any]:
        event = normalize_reported_event(
            channel=self.channel,
            payload=parse_payload(text),
            raw=text,
            source_ip=source_ip,
        )
        self._status["received"] += 1
        return self._event_store.append(event)

    def ingest_packet(self, payload: bytes, source_ip: str | None = None) -> dict[str, Any]:
        text = payload.decode("utf-8", errors="replace").strip()
        if not text:
            text = payload.hex()
        return self.ingest_text(text, source_ip=source_ip)

    def _run(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.5)
            sock.bind((self._host, self._port))
            self._socket = sock
            self._status.update({"running": True, "error": None, "port": sock.getsockname()[1]})
        except OSError as exc:
            self._status.update({"running": False, "error": str(exc)})
            return

        while not self._stop_event.is_set():
            try:
                payload, address = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            self.ingest_packet(payload, source_ip=address[0])

        self._status["running"] = False


class SyslogReceiver(UdpEventReceiver):
    channel = "syslog"

    def __init__(self, event_store: EventStore, *, host: str = "127.0.0.1", port: int = 1514, enabled: bool = True) -> None:
        super().__init__(event_store, host=host, port=port, enabled=enabled)


class SnmpTrapReceiver(UdpEventReceiver):
    channel = "snmp_trap"

    def __init__(self, event_store: EventStore, *, host: str = "127.0.0.1", port: int = 1162, enabled: bool = True) -> None:
        super().__init__(event_store, host=host, port=port, enabled=enabled)

    def ingest_packet(self, payload: bytes, source_ip: str | None = None) -> dict[str, Any]:
        decoded = decode_snmp_trap_packet(payload, source_ip=source_ip)
        if decoded:
            event = normalize_reported_event(
                channel=self.channel,
                payload=decoded,
                raw=decoded.get("raw") or payload.hex(),
                source_ip=source_ip,
            )
            self._status["received"] += 1
            return self._event_store.append(event)
        return super().ingest_packet(payload, source_ip=source_ip)
