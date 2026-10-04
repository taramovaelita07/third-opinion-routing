"""Internal models shared by parsing, routing, safety, and audit layers."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Modality(StrEnum):
    CT_CHEST = "CT_CHEST"
    MAMMOGRAPHY = "MAMMOGRAPHY"
    UNKNOWN = "UNKNOWN"


class Laterality(StrEnum):
    RIGHT = "RIGHT"
    LEFT = "LEFT"
    BILATERAL = "BILATERAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class TextSource(StrEnum):
    REPORT = "REPORT"
    CONCLUSION = "CONCLUSION"


class TextAssertion(StrEnum):
    PRESENT = "PRESENT"
    NEGATED = "NEGATED"
    UNCERTAIN = "UNCERTAIN"


class Evidence(BaseModel):
    """Exact source field that supports a normalized finding."""

    model_config = ConfigDict(extra="forbid")

    source_path: str
    raw_value: Any


class Finding(BaseModel):
    """A normalized finding produced by the external radiology AI."""

    model_config = ConfigDict(extra="forbid")

    code: str
    display_name: str
    present: bool = True
    confidence: int | None = Field(default=None, ge=0, le=100)
    laterality: Laterality = Laterality.UNKNOWN
    location: str | None = None
    classification: str | None = None
    measurements: dict[str, int | float | str] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)


class TextSignal(BaseModel):
    """A deterministic, auditable signal extracted from radiology text."""

    model_config = ConfigDict(extra="forbid")

    code: str
    display_name: str
    assertion: TextAssertion
    source: TextSource
    matched_text: str
    evidence: list[Evidence] = Field(default_factory=list)


class NormalizedStudy(BaseModel):
    """Unified internal representation independent of transport format."""

    model_config = ConfigDict(extra="forbid")

    study_id: str
    series_id: str
    source: str
    modality: Modality
    pathology_present: bool
    overall_confidence: int
    model_id: int
    model_version: str
    report: str
    conclusion: str
    findings: list[Finding] = Field(default_factory=list)
    text_signals: list[TextSignal] = Field(default_factory=list)
    parsing_flags: list[str] = Field(default_factory=list)
