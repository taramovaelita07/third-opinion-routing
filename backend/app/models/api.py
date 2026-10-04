"""Public REST API and persistence contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.models.normalized import NormalizedStudy
from app.models.routing import RoutingDecision
from app.models.safety import SafetyResult


class DemoCaseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str
    modality: str
    validation: Literal["valid", "invalid"]


class DemoCaseDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str
    modality: str
    validation: Literal["valid", "invalid"]
    payload: dict[str, Any]


class DemoResetResponse(BaseModel):
    """Result of clearing only synthetic demonstration history."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["reset"] = "reset"
    deleted_analyses: int
    deleted_care_journeys: int


class WorkflowStatus(StrEnum):
    PENDING_CLINICIAN_REVIEW = "PENDING_CLINICIAN_REVIEW"
    ESCALATED_FOR_REVIEW = "ESCALATED_FOR_REVIEW"
    BLOCKED_PENDING_REVIEW = "BLOCKED_PENDING_REVIEW"
    PATIENT_ACTION_AVAILABLE = "PATIENT_ACTION_AVAILABLE"
    APPOINTMENT_BOOKED = "APPOINTMENT_BOOKED"


class AnalysisResult(BaseModel):
    """In-memory result produced by the clinical pipeline."""

    model_config = ConfigDict(extra="forbid")

    normalized_study: NormalizedStudy
    routing_decision: RoutingDecision
    safety_result: SafetyResult


class AnalysisResponse(AnalysisResult):
    """Persisted, auditable result returned by the REST API."""

    analysis_id: str
    created_at: datetime
    workflow_status: WorkflowStatus
    raw_input: dict[str, Any]


class AnalysisHistoryItem(BaseModel):
    """Compact row for the future history screen."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: str
    study_id: str
    modality: str
    priority: str
    safety_disposition: str
    workflow_status: WorkflowStatus
    created_at: datetime
