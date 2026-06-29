from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

from ...core.observability import log_llm_error, log_llm_request, log_llm_response
from .base import LLMClient, LLMConfigurationError, LLMResponseError


@dataclass(frozen=True)
class OpenAICompatibleSettings:
    api_key: str | None
    base_url: str | None
    model: str | None
    timeout_seconds: float = 60
    temperature: float = 0
    top_p: float = 0.1
    json_mode: bool = True

    @property
    def missing_fields(self) -> list[str]:
        missing = []
        if not self.api_key:
            missing.append("LLM_API_KEY")
        if not self.base_url:
            missing.append("LLM_BASE_URL")
        if not self.model:
            missing.append("LLM_MODEL")
        return missing


class OpenAICompatibleLLMClient(LLMClient):
    """Client for OpenAI-compatible chat-completions APIs.

    The implementation does not provide a fake local answer. If model
    configuration is missing or the provider returns invalid JSON, diagnosis
    fails so the operator can fix the integration.
    """

    def __init__(self, settings: OpenAICompatibleSettings) -> None:
        self._settings = settings

    @classmethod
    def from_env(cls, saved_config: Mapping[str, Any] | None = None) -> "OpenAICompatibleLLMClient":
        saved_config = saved_config or {}
        settings = OpenAICompatibleSettings(
            api_key=_env_or_config_string("LLM_API_KEY", saved_config, "api_key"),
            base_url=_env_or_config_string("LLM_BASE_URL", saved_config, "base_url"),
            model=_env_or_config_string("LLM_MODEL", saved_config, "model"),
            timeout_seconds=_env_or_config_float("LLM_TIMEOUT_SECONDS", saved_config, "timeout_seconds", 60.0),
            temperature=_env_or_config_float("LLM_TEMPERATURE", saved_config, "temperature", 0.0),
            top_p=_env_or_config_float("LLM_TOP_P", saved_config, "top_p", 0.1),
            json_mode=_env_or_config_bool("LLM_JSON_MODE", saved_config, "json_mode", True),
        )
        return cls(settings)

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "OpenAICompatibleLLMClient":
        settings = OpenAICompatibleSettings(
            api_key=_clean_mapping_string(config, "api_key"),
            base_url=_clean_mapping_string(config, "base_url"),
            model=_clean_mapping_string(config, "model"),
            timeout_seconds=_mapping_float(config, "timeout_seconds", 60.0),
            temperature=_mapping_float(config, "temperature", 0.0),
            top_p=_mapping_float(config, "top_p", 0.1),
            json_mode=_mapping_bool(config, "json_mode", True),
        )
        return cls(settings)

    def metadata(self) -> dict[str, Any]:
        return {
            "provider": "openai_compatible",
            "configured": not self._settings.missing_fields,
            "base_url": _redact_url(self._settings.base_url),
            "model": self._settings.model,
            "has_api_key": bool(self._settings.api_key),
            "missing_fields": self._settings.missing_fields,
            "json_mode": self._settings.json_mode,
            "timeout_seconds": self._settings.timeout_seconds,
            "temperature": self._settings.temperature,
            "top_p": self._settings.top_p,
        }

    def configure(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        json_mode: bool | None = None,
    ) -> dict[str, Any]:
        self._settings = OpenAICompatibleSettings(
            api_key=_clean(api_key) or self._settings.api_key,
            base_url=_clean(base_url) or self._settings.base_url,
            model=_clean(model) or self._settings.model,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else self._settings.timeout_seconds,
            temperature=temperature if temperature is not None else self._settings.temperature,
            top_p=top_p if top_p is not None else self._settings.top_p,
            json_mode=json_mode if json_mode is not None else self._settings.json_mode,
        )
        return self.metadata()

    def settings_snapshot(self, *, include_api_key: bool = False) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "base_url": self._settings.base_url,
            "model": self._settings.model,
            "timeout_seconds": self._settings.timeout_seconds,
            "temperature": self._settings.temperature,
            "top_p": self._settings.top_p,
            "json_mode": self._settings.json_mode,
        }
        if include_api_key:
            snapshot["api_key"] = self._settings.api_key
        return snapshot

    def complete_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_configured()
        assert self._settings.base_url is not None
        assert self._settings.model is not None
        assert self._settings.api_key is not None

        request_payload: dict[str, Any] = {
            "model": self._settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True),
                },
            ],
            "temperature": self._settings.temperature,
            "top_p": self._settings.top_p,
        }
        if self._settings.json_mode:
            request_payload["response_format"] = {"type": "json_object"}

        operation = "chat_completions.complete_json"
        log_llm_request(
            provider="openai_compatible",
            model=self._settings.model,
            operation=operation,
            payload={
                "url": _chat_completions_url(self._settings.base_url),
                "request": request_payload,
            },
        )

        body = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            _chat_completions_url(self._settings.base_url),
            data=body,
            headers={
                "Authorization": f"Bearer {self._settings.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self._settings.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            log_llm_error(
                provider="openai_compatible",
                model=self._settings.model,
                operation=operation,
                error=f"HTTP {exc.code}: {detail}",
            )
            raise LLMResponseError(f"LLM provider returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            log_llm_error(
                provider="openai_compatible",
                model=self._settings.model,
                operation=operation,
                error=exc,
            )
            raise LLMResponseError(f"Cannot connect to LLM provider: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            log_llm_error(
                provider="openai_compatible",
                model=self._settings.model,
                operation=operation,
                error=exc,
            )
            raise LLMResponseError("LLM provider response is not valid JSON") from exc

        log_llm_response(
            provider="openai_compatible",
            model=self._settings.model,
            operation=operation,
            payload=response_payload,
        )
        content = _extract_message_content(response_payload)
        return _parse_json_content(content)

    def agents_chat_model(self) -> Any:
        self._ensure_configured()
        assert self._settings.base_url is not None
        assert self._settings.model is not None
        assert self._settings.api_key is not None

        from agents import OpenAIChatCompletionsModel
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self._settings.api_key,
            base_url=_openai_client_base_url(self._settings.base_url),
            timeout=self._settings.timeout_seconds,
        )
        return OpenAIChatCompletionsModel(
            model=self._settings.model,
            openai_client=client,
        )

    def agents_model_settings(self) -> Any:
        from agents import ModelSettings

        return ModelSettings(
            temperature=self._settings.temperature,
            top_p=self._settings.top_p,
        )

    def parse_json_content(self, content: str) -> dict[str, Any]:
        return _parse_json_content(content)

    def _ensure_configured(self) -> None:
        missing = self._settings.missing_fields
        if missing:
            raise LLMConfigurationError(
                "Large model is not configured. Missing environment variables: " + ", ".join(missing)
            )


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _openai_client_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    suffix = "/chat/completions"
    if normalized.endswith(suffix):
        return normalized[: -len(suffix)]
    return normalized


def _extract_message_content(response_payload: dict[str, Any]) -> str:
    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMResponseError("LLM provider response does not contain choices[0].message.content") from exc
    if not isinstance(content, str) or not content.strip():
        raise LLMResponseError("LLM provider returned empty message content")
    return content


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMResponseError("LLM message content is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise LLMResponseError("LLM JSON content must be an object")
    return payload


def _redact_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env_or_config_string(env_name: str, config: Mapping[str, Any], config_key: str) -> str | None:
    return _clean(os.getenv(env_name)) or _clean_mapping_string(config, config_key)


def _env_or_config_float(env_name: str, config: Mapping[str, Any], config_key: str, default: float) -> float:
    env_value = _clean(os.getenv(env_name))
    if env_value is not None:
        return _parse_float(env_value, default)
    return _mapping_float(config, config_key, default)


def _env_or_config_bool(env_name: str, config: Mapping[str, Any], config_key: str, default: bool) -> bool:
    env_value = os.getenv(env_name)
    if env_value is not None:
        return _parse_bool(env_value, default)
    return _mapping_bool(config, config_key, default)


def _clean_mapping_string(config: Mapping[str, Any], key: str) -> str | None:
    value = config.get(key)
    if value is None:
        return None
    return _clean(str(value))


def _mapping_float(config: Mapping[str, Any], key: str, default: float) -> float:
    if key not in config:
        return default
    return _parse_float(config.get(key), default)


def _mapping_bool(config: Mapping[str, Any], key: str, default: bool) -> bool:
    if key not in config:
        return default
    return _parse_bool(config.get(key), default)


def _parse_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default
