"""Reproduce the clinical-style synthetic scenario validation.

This command validates the post-AI processing pipeline. It does not evaluate
diagnostic image accuracy and must not be presented as clinical validation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.adapters import DemoDataset
from app.models import RawKafkaMessage
from app.services import AnalysisService


@dataclass(frozen=True)
class ScenarioExpectation:
    case_id: str
    expected_rule_id: str
    expected_priority: str
    expected_specialty_fragment: str
    expected_timeframe: str
    expected_safety: str
    expected_route_usable: bool


@dataclass(frozen=True)
class ScenarioValidationResult:
    case_id: str
    title: str
    finding_codes: tuple[str, ...]
    rule_id: str
    priority: str
    specialty: str
    timeframe: str
    safety: str
    route_usable: bool
    issue_codes: tuple[str, ...]
    passed: bool


SCENARIOS: tuple[ScenarioExpectation, ...] = (
    ScenarioExpectation(
        case_id="ct-lung-nodule",
        expected_rule_id="CT_LUNG_NODULE_SPECIALIST_REVIEW",
        expected_priority="PRIORITY",
        expected_specialty_fragment="Пульмонолог",
        expected_timeframe="В течение 14 дней",
        expected_safety="CLEARED_FOR_REVIEW",
        expected_route_usable=True,
    ),
    ScenarioExpectation(
        case_id="mmg-birads-4",
        expected_rule_id="MMG_SUSPICIOUS_PRIORITY_REVIEW",
        expected_priority="PRIORITY",
        expected_specialty_fragment="Маммолог",
        expected_timeframe="В течение 14 дней",
        expected_safety="CLEARED_FOR_REVIEW",
        expected_route_usable=True,
    ),
    ScenarioExpectation(
        case_id="ct-pneumothorax",
        expected_rule_id="CT_PNEUMOTHORAX_URGENT_REVIEW",
        expected_priority="URGENT",
        expected_specialty_fragment="торакальный хирург",
        expected_timeframe="В тот же день",
        expected_safety="ESCALATE_TO_CLINICIAN",
        expected_route_usable=True,
    ),
    ScenarioExpectation(
        case_id="conclusion-conflict",
        expected_rule_id="CT_LUNG_NODULE_SPECIALIST_REVIEW",
        expected_priority="PRIORITY",
        expected_specialty_fragment="Пульмонолог",
        expected_timeframe="В течение 14 дней",
        expected_safety="BLOCKED_PENDING_REVIEW",
        expected_route_usable=False,
    ),
)


def validate_scenarios() -> list[ScenarioValidationResult]:
    """Run selected cases through parsing, routing, and safety."""

    dataset = DemoDataset()
    service = AnalysisService()
    results: list[ScenarioValidationResult] = []

    for expected in SCENARIOS:
        case = dataset.get(expected.case_id)
        message = RawKafkaMessage.model_validate(case.payload)
        analysis = service.analyze(message, source="scenario-validation")
        study = analysis.normalized_study
        route = analysis.routing_decision
        safety = analysis.safety_result

        passed = all(
            (
                route.rule_id == expected.expected_rule_id,
                route.priority.value == expected.expected_priority,
                expected.expected_specialty_fragment in route.specialty,
                route.timeframe == expected.expected_timeframe,
                safety.disposition.value == expected.expected_safety,
                safety.route_usable is expected.expected_route_usable,
                route.requires_human_review is True,
                safety.patient_notification_allowed is False,
            )
        )

        results.append(
            ScenarioValidationResult(
                case_id=expected.case_id,
                title=case.metadata.title,
                finding_codes=tuple(finding.code for finding in study.findings),
                rule_id=route.rule_id,
                priority=route.priority.value,
                specialty=route.specialty,
                timeframe=route.timeframe,
                safety=safety.disposition.value,
                route_usable=safety.route_usable,
                issue_codes=tuple(issue.code for issue in safety.issues),
                passed=passed,
            )
        )

    return results


def main() -> int:
    results = validate_scenarios()

    for result in results:
        status = "PASS" if result.passed else "FAIL"
        issues = ", ".join(result.issue_codes) if result.issue_codes else "нет"
        print(f"[{status}] {result.title} ({result.case_id})")
        print(f"  finding_codes: {', '.join(result.finding_codes) or 'нет'}")
        print(f"  rule: {result.rule_id}")
        print(f"  route: {result.specialty}; {result.timeframe}; {result.priority}")
        print(f"  safety: {result.safety}; route_usable={result.route_usable}")
        print(f"  safety_issues: {issues}")

    passed = sum(result.passed for result in results)
    print(f"\nScenario validation: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
