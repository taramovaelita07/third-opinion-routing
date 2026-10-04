"""Contracts produced by the safety layer."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SafetyDisposition(StrEnum):
    CLEARED_FOR_REVIEW = "CLEARED_FOR_REVIEW"
    ESCALATE_TO_CLINICIAN = "ESCALATE_TO_CLINICIAN"
    BLOCKED_PENDING_REVIEW = "BLOCKED_PENDING_REVIEW"


class SafetyIssueSeverity(StrEnum):
    BLOCKING = "BLOCKING"
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"


class SafetyIssue(BaseModel):
    """One explicit reason produced by a safety check."""

    model_config = ConfigDict(extra="forbid")

    code: str
    severity: SafetyIssueSeverity
    message: str
    evidence_paths: list[str] = Field(default_factory=list)


class SafetyResult(BaseModel):
    """Safety assessment of a draft route before clinician approval."""

    model_config = ConfigDict(extra="forbid")

    study_id: str
    checked_rule_id: str
    policy_version: str
    disposition: SafetyDisposition
    route_usable: bool
    patient_notification_allowed: bool = False
    requires_human_review: bool = True
    issues: list[SafetyIssue] = Field(default_factory=list)
    fallback_message: str | None = None

