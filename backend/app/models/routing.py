"""Contracts produced by the deterministic routing layer."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RoutingPriority(StrEnum):
    ROUTINE = "ROUTINE"
    PRIORITY = "PRIORITY"
    URGENT = "URGENT"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class RoutingStatus(StrEnum):
    DRAFT_FOR_REVIEW = "DRAFT_FOR_REVIEW"


class TraceStage(StrEnum):
    SOURCE_RESULT = "SOURCE_RESULT"
    NORMALIZED_FINDING = "NORMALIZED_FINDING"
    ROUTING_RULE = "ROUTING_RULE"


class RoutingTraceStep(BaseModel):
    """One auditable step from source data to a draft route."""

    model_config = ConfigDict(extra="forbid")

    stage: TraceStage
    description: str
    evidence_paths: list[str] = Field(default_factory=list)


class RoutingDecision(BaseModel):
    """Draft organizational route that must be reviewed by a clinician."""

    model_config = ConfigDict(extra="forbid")

    study_id: str
    status: RoutingStatus = RoutingStatus.DRAFT_FOR_REVIEW
    rule_id: str
    priority: RoutingPriority
    action: str
    specialty: str
    timeframe: str
    reason: str
    prerequisites: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    requires_human_review: bool = True
    matched_finding_codes: list[str] = Field(default_factory=list)
    trace: list[RoutingTraceStep] = Field(default_factory=list)

