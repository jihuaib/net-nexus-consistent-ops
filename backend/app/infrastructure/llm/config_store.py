from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_FILE = Path(__file__).resolve().parents[4] / ".netnexus" / "llm_config.json"


class LLMConfigStore:
    def __init__(self, config_file: Path | None = None) -> None:
        self._config_file = config_file or Path(os.getenv("NETNEXUS_LLM_CONFIG_FILE", DEFAULT_CONFIG_FILE))

    def get_config(self) -> dict[str, Any]:
        return sanitize_config(self._read_config_file())

    def update_config(self, config: dict[str, Any]) -> dict[str, Any]:
        sanitized = sanitize_config(config)
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        self._config_file.write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(self._config_file, 0o600)
        except OSError:
            pass
        return sanitized

    def _read_config_file(self) -> dict[str, Any]:
        if not self._config_file.exists():
            return {}
        try:
            raw = json.loads(self._config_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return raw if isinstance(raw, dict) else {}


def sanitize_config(config: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key in ("api_key", "base_url", "model"):
        value = optional_string(config.get(key))
        if value is not None:
            sanitized[key] = value

    timeout_seconds = optional_float(config.get("timeout_seconds"))
    if timeout_seconds is not None:
        sanitized["timeout_seconds"] = clamp_float(timeout_seconds, minimum=0.1, maximum=300.0)

    temperature = optional_float(config.get("temperature"))
    if temperature is not None:
        sanitized["temperature"] = clamp_float(temperature, minimum=0.0, maximum=2.0)

    top_p = optional_float(config.get("top_p"))
    if top_p is not None:
        sanitized["top_p"] = clamp_float(top_p, minimum=0.0, maximum=1.0)

    json_mode = optional_bool(config.get("json_mode"))
    if json_mode is not None:
        sanitized["json_mode"] = json_mode

    return sanitized


def optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def clamp_float(value: float, *, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)
