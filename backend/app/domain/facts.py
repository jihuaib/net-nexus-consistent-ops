from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Fact:
    fact_id: str
    device_id: str
    scope: str
    object: str
    fact_type: str
    value: str
    severity: str
    timestamp: str
    source: str
    confidence: float
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
