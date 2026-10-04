"""Tests for fail-closed route safety checks."""

import pytest

from app.adapters import DemoDataset
from app.models import (
    RawKafkaMessage,
    SafetyDisposition,
    SafetyIssueSeverity,
)
from app.parsers import StudyParser
from app.routing import RoutingEngine
from app.safety import SafetyEngine


def _pipeline(case_id: str):
    case = DemoDataset().get(case_id)
    message = RawKafkaMessage.model_validate(case.payload)
    study = StudyParser().parse(message, source="demo")
    decision = RoutingEngine().route(study)
    result = SafetyEngine().assess(study, decision)
    return study, decision, result


@pytest.mark.parametrize(
    "case_id",
    ["ct-normal", "ct-lung-nodule", "mmg-birads-2", "mmg-birads-4"],
)
def test_consistent_routes_are_cleared_only_for_clinician_review(case_id: str) -> None:
    _, _, result = _pipeline(case_id)

    assert result.disposition is SafetyDisposition.CLEARED_FOR_REVIEW
    assert result.route_usable is True
    assert result.patient_notification_allowed is False
    assert result.requires_human_review is True
    assert result.fallback_message is None


def test_low_confidence_actionable_finding_is_blocked() -> None:
    _, _, result = _pipeline("ct-low-confidence")

    assert result.disposition is SafetyDisposition.BLOCKED_PENDING_REVIEW
    assert result.route_usable is False
    assert "LOW_ACTIONABLE_FINDING_CONFIDENCE" in {
        issue.code for issue in result.issues
    }
    assert result.fallback_message is not None


def test_low_confidence_benign_finding_is_not_treated_as_actionable_alarm() -> None:
    study, _, result = _pipeline("mmg-birads-2")

    assert study.findings[0].confidence == 32
    assert "LOW_ACTIONABLE_FINDING_CONFIDENCE" not in {
        issue.code for issue in result.issues
    }
    assert result.disposition is SafetyDisposition.CLEARED_FOR_REVIEW


def test_pathology_norma_conflict_is_blocked() -> None:
    _, _, result = _pipeline("conflicting-norma")

    codes = {issue.code for issue in result.issues}
    assert "PATHOLOGY_NORMA_CONFLICT" in codes
    assert "NO_VALIDATED_ROUTE" in codes
    assert result.disposition is SafetyDisposition.BLOCKED_PENDING_REVIEW


def test_structured_conclusion_conflict_is_blocked_with_each_reason() -> None:
    _, _, result = _pipeline("conclusion-conflict")
    codes = {issue.code for issue in result.issues}

    assert {
        "STRUCTURED_CONCLUSION_CONFLICT",
        "PATHOLOGY_CONCLUSION_CONFLICT",
        "REPORT_CONCLUSION_CONFLICT",
    }.issubset(codes)
    assert result.route_usable is False


def test_unknown_modality_is_blocked_without_route_guessing() -> None:
    _, _, result = _pipeline("unknown-modality")
    codes = {issue.code for issue in result.issues}

    assert "UNSUPPORTED_OR_AMBIGUOUS_MODALITY" in codes
    assert "NO_VALIDATED_ROUTE" in codes
    assert result.disposition is SafetyDisposition.BLOCKED_PENDING_REVIEW


def test_red_flag_is_escalated_but_keeps_urgent_draft_route() -> None:
    _, decision, result = _pipeline("ct-pneumothorax")

    assert decision.red_flags == ["Возможный пневмоторакс"]
    assert result.disposition is SafetyDisposition.ESCALATE_TO_CLINICIAN
    assert result.route_usable is True
    assert result.patient_notification_allowed is False
    assert result.issues[0].severity is SafetyIssueSeverity.CRITICAL


def test_study_id_mismatch_is_blocked() -> None:
    study, decision, _ = _pipeline("ct-lung-nodule")
    wrong_decision = decision.model_copy(update={"study_id": "another-study"})

    result = SafetyEngine().assess(study, wrong_decision)

    assert result.disposition is SafetyDisposition.BLOCKED_PENDING_REVIEW
    assert "STUDY_ID_MISMATCH" in {issue.code for issue in result.issues}


def test_route_cannot_disable_human_review() -> None:
    study, decision, _ = _pipeline("ct-lung-nodule")
    unsafe_decision = decision.model_copy(update={"requires_human_review": False})

    result = SafetyEngine().assess(study, unsafe_decision)

    assert "HUMAN_REVIEW_NOT_REQUIRED_BY_ROUTE" in {
        issue.code for issue in result.issues
    }
    assert result.route_usable is False


def test_exact_confidence_threshold_is_accepted() -> None:
    study, decision, _ = _pipeline("ct-low-confidence")
    finding = study.findings[0].model_copy(update={"confidence": 60})
    study = study.model_copy(update={"findings": [finding]})

    result = SafetyEngine(minimum_actionable_confidence=60).assess(study, decision)

    assert result.disposition is SafetyDisposition.CLEARED_FOR_REVIEW


@pytest.mark.parametrize("threshold", [-1, 101])
def test_invalid_confidence_threshold_is_rejected(threshold: int) -> None:
    with pytest.raises(ValueError):
        SafetyEngine(minimum_actionable_confidence=threshold)

