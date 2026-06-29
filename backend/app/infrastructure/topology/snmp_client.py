from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any
from typing import Protocol

from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    bulk_cmd,
    get_cmd,
)


class SnmpWalkClient(Protocol):
    def walk(self, target: str, community: str, oid: str, timeout_seconds: float) -> str:
        ...


class PysnmpWalkClient:
    def __init__(self, retries: int = 0, max_repetitions: int = 24, max_rows: int = 4096) -> None:
        self._retries = retries
        self._max_repetitions = max_repetitions
        self._max_rows = max_rows

    def walk(self, target: str, community: str, oid: str, timeout_seconds: float) -> str:
        return run_coroutine_sync(self._walk(target, community, oid, timeout_seconds))

    async def _walk(self, target: str, community: str, oid: str, timeout_seconds: float) -> str:
        if normalize_oid(oid).endswith(".0"):
            return await self._get(target, community, oid, timeout_seconds)
        return await self._walk_subtree(target, community, oid, timeout_seconds)

    async def _get(self, target: str, community: str, oid: str, timeout_seconds: float) -> str:
        host, port = parse_target(target)
        snmp_engine = SnmpEngine()
        transport = await UdpTransportTarget.create((host, port), timeout=timeout_seconds, retries=self._retries)
        error_indication, error_status, error_index, var_binds = await get_cmd(
            snmp_engine,
            CommunityData(community, mpModel=1),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
        close_snmp_engine(snmp_engine)
        if error_indication:
            raise ValueError(str(error_indication))
        if error_status:
            raise ValueError(f"{error_status.prettyPrint()} at {error_index}")
        return "\n".join(format_var_bind(name, value) for name, value in var_binds)

    async def _walk_subtree(self, target: str, community: str, oid: str, timeout_seconds: float) -> str:
        host, port = parse_target(target)
        snmp_engine = SnmpEngine()
        transport = await UdpTransportTarget.create((host, port), timeout=timeout_seconds, retries=self._retries)
        base_oid = normalize_oid(oid)
        base_tuple = oid_to_tuple(base_oid)
        next_oid = base_oid
        rows = []
        seen = set()

        while len(rows) < self._max_rows:
            error_indication, error_status, error_index, var_binds = await bulk_cmd(
                snmp_engine,
                CommunityData(community, mpModel=1),
                transport,
                ContextData(),
                0,
                self._max_repetitions,
                ObjectType(ObjectIdentity(next_oid)),
                lexicographicMode=False,
            )
            if error_indication:
                raise ValueError(str(error_indication))
            if error_status:
                raise ValueError(f"{error_status.prettyPrint()} at {error_index}")
            if not var_binds:
                break

            advanced = False
            for name, value in var_binds:
                current_oid = oid_from_name(name)
                if not oid_to_tuple(current_oid)[: len(base_tuple)] == base_tuple:
                    close_snmp_engine(snmp_engine)
                    return "\n".join(rows)
                if current_oid in seen:
                    continue
                seen.add(current_oid)
                rows.append(format_var_bind(name, value))
                next_oid = current_oid
                advanced = True

            if not advanced:
                break

        close_snmp_engine(snmp_engine)
        return "\n".join(rows)


def parse_target(target: str) -> tuple[str, int]:
    value = str(target).strip()
    if value.startswith("[") and "]:" in value:
        host, port = value.rsplit(":", 1)
        return host.strip("[]"), int(port)
    if value.count(":") == 1:
        host, port = value.rsplit(":", 1)
        if port.isdigit():
            return host, int(port)
    return value, 161


def format_var_bind(name: object, value: object) -> str:
    return f"{oid_from_name(name)} = {value.__class__.__name__}: {value.prettyPrint()}"


def oid_from_name(name: object) -> str:
    as_tuple = getattr(name, "asTuple", None)
    if callable(as_tuple):
        return "." + ".".join(str(part) for part in as_tuple())
    return normalize_oid(name.prettyPrint())


def normalize_oid(oid: str) -> str:
    return "." + str(oid).strip().lstrip(".")


def oid_to_tuple(oid: str) -> tuple[int, ...]:
    return tuple(int(part) for part in normalize_oid(oid).strip(".").split(".") if part)


def close_snmp_engine(snmp_engine: SnmpEngine) -> None:
    close_dispatcher = getattr(snmp_engine, "close_dispatcher", None)
    if callable(close_dispatcher):
        close_dispatcher()


def run_coroutine_sync(coro: Coroutine[Any, Any, str]) -> str:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, str] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:
            error["value"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error["value"]
    return result.get("value", "")
