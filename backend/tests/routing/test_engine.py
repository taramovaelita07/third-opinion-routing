"""Tests for deterministic draft routing."""

from copy import deepcopy

import pytest

from app.adapters import DemoDataset
from app.models import (
    Evidence,
    Finding,
    Modality,
    RawKafkaMessage,
    RoutingPriority,
    RoutingStatus,
)
from app.parsers import StudyParser
from app.routing import RoutingEngine


def _study(case_id: str):
    case = DemoDataset().get(case_id)
    message = RawKafkaMessage.model_validate(case.payload)
    return StudyParser().parse(message, source="demo")


@pytest.mark.parametrize(
    ("case_id", "rule_id", "priority", "specialty_fragment"),
    [
        (
            "ct-pneumothorax",
            "CT_PNEUMOTHORAX_URGENT_REVIEW",
            RoutingPriority.URGENT,
            "торакальный хирург",
        ),
        (
            "ct-lung-nodule",
            "CT_LUNG_NODULE_SPECIALIST_REVIEW",
            RoutingPriority.PRIORITY,
            "Пульмонолог",
        ),
        (
            "mmg-birads-4",
            "MMG_SUSPICIOUS_PRIORITY_REVIEW",
            RoutingPriority.PRIORITY,
            "Маммолог",
        ),
        (
            "mmg-birads-2",
            "MMG_BENIGN_ROUTINE_REVIEW",
            RoutingPriority.ROUTINE,
            "Маммолог",
        ),
    ],
)
def test_known_findings_receive_expected_draft_route(
    case_id: str,
    rule_id: str,
    priority: RoutingPriority,
    specialty_fragment: str,
) -> None:
    decision = RoutingEngine().route(_study(case_id))

    assert decision.rule_id == rule_id
    assert decision.priority is priority
    assert specialty_fragment in decision.specialty


def test_normal_study_receives_only_routine_review() -> None:
    decision = RoutingEngine().route(_study("ct-normal"))

    assert decision.rule_id == "NO_FINDINGS_ROUTINE_REVIEW"
    assert decision.priority is RoutingPriority.ROUTINE
    assert decision.matched_finding_codes == []


def test_unknown_modality_uses_manual_review_fallback() -> None:
    decision = RoutingEngine().route(_study("unknown-modality"))

    assert decision.rule_id == "MANUAL_REVIEW_FALLBACK"
    assert decision.priority is RoutingPriority.MANUAL_REVIEW
    assert "До отправки" in decision.timeframe


def test_every_route_is_a_draft_for_human_review() -> None:
    for case_id in (
        "ct-normal",
        "ct-lung-nodule",
        "ct-pneumothorax",
        "mmg-birads-2",
        "mmg-birads-4",
        "unknown-modality",
    ):
        decision = RoutingEngine().route(_study(case_id))

        assert decision.status is RoutingStatus.DRAFT_FOR_REVIEW
        assert decision.requires_human_review is True


def test_trace_links_rule_to_structured_source_field() -> None:
    decision = RoutingEngine().route(_study("ct-lung-nodule"))

    assert decision.trace[-1].description.endswith(
        "CT_LUNG_NODULE_SPECIALIST_REVIEW"
    )
    assert "aiResult.probParams.ct_lc" in decision.trace[0].evidence_paths


def test_highest_priority_rule_wins_when_findings_are_combined() -> None:
    study = _study("ct-lung-nodule")
    study.findings.append(
        Finding(
            code="CT_PNEUMOTHORAX",
            display_name="Пневмоторакс",
            evidence=[
                Evidence(
                    source_path="aiResult.probParams.ct_chest_pneumotorax",
                    raw_value={"right_volume_ml": 10},
                )
            ],
        )
    )

    decision = RoutingEngine().route(study)

    assert decision.rule_id == "CT_PNEUMOTHORAX_URGENT_REVIEW"
    assert decision.priority is RoutingPriority.URGENT


def test_unrecognized_finding_never_receives_guessed_route() -> None:
    study = _study("ct-lung-nodule")
    unknown_finding = study.findings[0].model_copy(
        update={"code": "CT_UNSUPPORTED_FINDING"}
    )
    study = study.model_copy(update={"findings": [unknown_finding]})

    decision = RoutingEngine().route(study)

    assert decision.rule_id == "MANUAL_REVIEW_FALLBACK"
    assert decision.matched_finding_codes == ["CT_UNSUPPORTED_FINDING"]


def test_routing_uses_structured_findings_not_conflicting_conclusion() -> None:
    payload = deepcopy(DemoDataset().get("conclusion-conflict").payload)
    message = RawKafkaMessage.model_validate(payload)
    study = StudyParser().parse(message, source="test")

    decision = RoutingEngine().route(study)

    assert decision.rule_id == "CT_LUNG_NODULE_SPECIALIST_REVIEW"
    assert decision.requires_human_review is True

