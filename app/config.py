"""Tenant-level settings. In production these would live in the database per
company, with an audit trail of who changed what (the Directive expects the
methodology to be explainable and gender-neutral)."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class FactorWeights(BaseModel):
    """Art. 4(4): skills, effort, responsibility and working conditions."""
    skills: float = 0.35
    effort: float = 0.20
    responsibility: float = 0.30
    working_conditions: float = 0.15

    @field_validator("*")
    @classmethod
    def non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("weights must be >= 0")
        return v

    def normalised(self) -> dict[str, float]:
        raw = self.model_dump()
        total = sum(raw.values()) or 1.0
        return {k: v / total for k, v in raw.items()}


class Settings(BaseModel):
    weights: FactorWeights = Field(default_factory=FactorWeights)
    # Width (in 0-100 job-evaluation points) of each "category of workers".
    band_width: float = Field(10.0, gt=0, le=50)
    # Art. 10(1)(a): 5% triggers a joint pay assessment if unjustified & unremedied.
    gap_threshold: float = Field(0.05, gt=0, lt=1)
    # Groups smaller than this are flagged as statistically fragile / privacy-sensitive.
    min_group_size: int = Field(3, ge=1, le=50)
    # '<legal_entity>|<category_id>' -> objective, gender-neutral justification
    justifications: dict[str, str] = Field(default_factory=dict)
    reference_date: str | None = None  # ISO date for tenure; defaults to today
