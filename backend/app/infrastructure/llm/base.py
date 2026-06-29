from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMConfigurationError(RuntimeError):
    """Raised when the large model client is not configured."""


class LLMResponseError(RuntimeError):
    """Raised when the large model response is missing or invalid."""


class LLMClient(ABC):
    @abstractmethod
    def complete_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def metadata(self) -> dict[str, Any]:
        raise NotImplementedError
