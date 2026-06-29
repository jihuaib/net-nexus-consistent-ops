from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from starlette.types import Message, Receive, Scope, Send

from .observability import env_flag, log_event, sanitize_for_log


class ApiLoggingMiddleware:
    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = time.perf_counter()
        request_body = await _read_body(receive)
        request_payload = _request_payload(scope, request_body)
        if env_flag("LOG_API_REQUESTS", True):
            log_event("netnexus.api", "api.request", request_payload)

        response_status: int | None = None
        response_headers: list[tuple[bytes, bytes]] = []
        response_body_parts: list[bytes] = []
        request_replayed = False

        async def replay_receive() -> Message:
            nonlocal request_replayed
            if request_replayed:
                return await receive()
            request_replayed = True
            return {
                "type": "http.request",
                "body": request_body,
                "more_body": False,
            }

        async def logging_send(message: Message) -> None:
            nonlocal response_status, response_headers
            if message["type"] == "http.response.start":
                response_status = int(message["status"])
                response_headers = list(message.get("headers") or [])
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body:
                    response_body_parts.append(body)
                if not message.get("more_body", False) and env_flag("LOG_API_RESPONSES", True):
                    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                    log_event(
                        "netnexus.api",
                        "api.response",
                        {
                            **_scope_identity(scope),
                            "status_code": response_status,
                            "duration_ms": duration_ms,
                            "headers": _headers_to_dict(response_headers),
                            "body": _decode_body(b"".join(response_body_parts), _content_type(response_headers)),
                        },
                    )
            await send(message)

        try:
            await self.app(scope, replay_receive, logging_send)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            log_event(
                "netnexus.api",
                "api.error",
                {
                    **_scope_identity(scope),
                    "duration_ms": duration_ms,
                    "error": str(exc),
                    "error_class": exc.__class__.__name__,
                },
                level=logging.ERROR,
            )
            raise


async def _read_body(receive: Receive) -> bytes:
    body_parts: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] != "http.request":
            continue
        body = message.get("body", b"")
        if body:
            body_parts.append(body)
        if not message.get("more_body", False):
            break
    return b"".join(body_parts)


def _request_payload(scope: Scope, body: bytes) -> dict[str, Any]:
    headers = _headers_to_dict(scope.get("headers") or [])
    return {
        **_scope_identity(scope),
        "client": _client(scope),
        "headers": headers,
        "body": _decode_body(body, headers.get("content-type", "")),
    }


def _scope_identity(scope: Scope) -> dict[str, Any]:
    query_string = (scope.get("query_string") or b"").decode("utf-8", errors="replace")
    return {
        "method": scope.get("method"),
        "path": scope.get("path"),
        "query": query_string,
    }


def _client(scope: Scope) -> str | None:
    client = scope.get("client")
    if not client:
        return None
    return f"{client[0]}:{client[1]}"


def _headers_to_dict(headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    return {
        key.decode("latin-1").lower(): value.decode("latin-1", errors="replace")
        for key, value in headers
    }


def _content_type(headers: list[tuple[bytes, bytes]]) -> str:
    return _headers_to_dict(headers).get("content-type", "")


def _decode_body(body: bytes, content_type: str) -> Any:
    if not body:
        return None
    text = body.decode("utf-8", errors="replace")
    if "application/json" in content_type:
        try:
            import json

            return sanitize_for_log(json.loads(text))
        except json.JSONDecodeError:
            return sanitize_for_log(text)
    return sanitize_for_log(text)
