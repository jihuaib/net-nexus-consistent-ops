from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any


SENSITIVE_KEY_PARTS = (
    "authorization",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "cookie",
)


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root.addHandler(handler)
    root.setLevel(level)


def log_event(logger_name: str, event: str, payload: dict[str, Any], level: int = logging.INFO) -> None:
    logger = logging.getLogger(logger_name)
    if not logger.isEnabledFor(level):
        return
    logger.log(level, "%s %s", event, compact_json(sanitize_for_log(payload)))


def log_llm_request(*, provider: str, model: str | None, operation: str, payload: dict[str, Any]) -> None:
    log_event(
        "netnexus.llm",
        "llm.request",
        {
            "provider": provider,
            "model": model,
            "operation": operation,
            "payload": payload,
        },
    )


def log_llm_response(*, provider: str, model: str | None, operation: str, payload: Any) -> None:
    log_event(
        "netnexus.llm",
        "llm.response",
        {
            "provider": provider,
            "model": model,
            "operation": operation,
            "payload": payload,
        },
    )


def log_llm_error(*, provider: str, model: str | None, operation: str, error: BaseException | str, payload: Any | None = None) -> None:
    log_event(
        "netnexus.llm",
        "llm.error",
        {
            "provider": provider,
            "model": model,
            "operation": operation,
            "error": str(error),
            "payload": payload,
        },
        level=logging.ERROR,
    )


def sanitize_for_log(value: Any, max_chars: int | None = None) -> Any:
    redacted = redact_sensitive(value)
    return truncate_for_log(redacted, max_chars=max_chars)


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(part in key_text for part in SENSITIVE_KEY_PARTS):
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    return value


def truncate_for_log(value: Any, max_chars: int | None = None) -> Any:
    limit = max_chars if max_chars is not None else int(os.getenv("LOG_BODY_MAX_CHARS", "20000"))
    if isinstance(value, str):
        return truncate_text(value, limit)
    if isinstance(value, dict):
        return {key: truncate_for_log(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        return [truncate_for_log(item, limit) for item in value]
    if isinstance(value, tuple):
        return tuple(truncate_for_log(item, limit) for item in value)
    return value


def truncate_text(text: str, limit: int) -> str | dict[str, Any]:
    if limit <= 0 or len(text) <= limit:
        return text
    return {
        "truncated": True,
        "chars": len(text),
        "preview": text[:limit],
    }


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def env_flag(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}
