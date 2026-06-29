from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ObservationCollector(ABC):
    """Collector boundary for live device observations."""

    @abstractmethod
    def list_devices(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_topology(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_fault_cases(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_fault_case(self, fault_case_id: str) -> dict[str, Any]:
        raise NotImplementedError
