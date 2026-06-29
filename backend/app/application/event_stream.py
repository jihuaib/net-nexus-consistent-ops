from __future__ import annotations

import asyncio
from threading import RLock
from typing import Any


class EventStreamHub:
    def __init__(self) -> None:
        self._clients: list[dict[str, Any]] = []
        self._lock = RLock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._published = 0

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._loop = loop

    def detach_loop(self) -> None:
        with self._lock:
            self._loop = None

    async def connect(self, websocket: Any, *, channel: str | None = None) -> dict[str, Any]:
        normalized_channel = normalize_channel(channel)
        await websocket.accept()
        client = {"websocket": websocket, "channel": normalized_channel}
        with self._lock:
            self._clients.append(client)
            connected = len(self._clients)
        await websocket.send_json(
            {
                "type": "connected",
                "channel": normalized_channel,
                "connected": connected,
            }
        )
        return client

    async def disconnect(self, client: dict[str, Any]) -> None:
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)

    def publish_event(self, event: dict[str, Any]) -> None:
        self._publish({"type": "event", "event": event})

    def publish_reset(self, summary: dict[str, Any]) -> None:
        self._publish({"type": "reset", "summary": summary})

    def status(self) -> dict[str, Any]:
        with self._lock:
            by_channel: dict[str, int] = {}
            for client in self._clients:
                channel = client.get("channel") or "all"
                by_channel[channel] = by_channel.get(channel, 0) + 1
            return {
                "connected": len(self._clients),
                "by_channel": by_channel,
                "published": self._published,
                "loop_attached": self._loop is not None,
            }

    def _publish(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._published += 1
            loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self._broadcast(payload), loop)

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        with self._lock:
            clients = list(self._clients)
        disconnected = []
        for client in clients:
            if not matches_channel(client, payload):
                continue
            try:
                await client["websocket"].send_json(payload)
            except Exception:
                disconnected.append(client)
        for client in disconnected:
            await self.disconnect(client)


def normalize_channel(channel: str | None) -> str | None:
    if not channel:
        return None
    value = channel.strip()
    return value or None


def matches_channel(client: dict[str, Any], payload: dict[str, Any]) -> bool:
    channel = client.get("channel")
    if not channel or payload.get("type") == "reset":
        return True
    event = payload.get("event") or {}
    return event.get("channel") == channel
