from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReportedEvent:
    event_id: str
    received_at: str
    timestamp: str
    channel: str
    source_ip: str | None
    device_id: str
    event_type: str
    object: str
    severity: str
    message: str
    raw: str
    attributes: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
