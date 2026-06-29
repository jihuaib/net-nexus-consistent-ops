from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class LLMDiagnosisResult(BaseModel):
    fault_type: str = Field(min_length=1)
    root_cause: str = Field(min_length=1)
    affected_devices: list[str] = Field(default_factory=list)
    affected_services: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    diagnosis_chain: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    recommendation: list[str] = Field(default_factory=list)
    need_more_data: bool = False

    @field_validator("evidence", "diagnosis_chain", "recommendation")
    @classmethod
    def require_non_empty_list(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("list cannot be empty")
        return value
