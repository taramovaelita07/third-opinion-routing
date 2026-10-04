"""Fail-closed safety policy for draft routes."""

from app.models import (
    NormalizedStudy,
    RoutingDecision,
    RoutingPriority,
    SafetyDisposition,
    SafetyIssue,
    SafetyIssueSeverity,
    SafetyResult,
)


_FALLBACK_MESSAGE = (
    "Недостаточно согласованных данных для безопасного определения маршрута. "
    "Требуется проверка медицинским специалистом."
)

_ACTIONABLE_FINDING_CODES = {
    "CT_LUNG_NODULE",
    "CT_PNEUMOTHORAX",
    "MMG_PROBABLY_BENIGN_FINDING",
    "MMG_SUSPICIOUS_FINDING",
}

_PARSING_FLAG_MESSAGES = {
    "UNSUPPORTED_OR_AMBIGUOUS_MODALITY": (
        "Модальность не поддерживается или определена неоднозначно",
        ["aiResult.probParams"],
    ),
    "PATHOLOGY_NORMA_CONFLICT": (
        "Поля pathologyFlag и norma противоречат друг другу",
        ["aiResult.pathologyFlag", "aiResult.norma"],
    ),
    "PATHOLOGY_FINDINGS_CONFLICT": (
        "Структурированная находка противоречит pathologyFlag",
        ["aiResult.pathologyFlag", "aiResult.probParams"],
    ),
    "STRUCTURED_CONCLUSION_CONFLICT": (
        "Структурированная находка противоречит тексту заключения",
        ["aiResult.probParams", "aiResult.conclusion"],
    ),
    "PATHOLOGY_CONCLUSION_CONFLICT": (
        "pathologyFlag противоречит тексту заключения",
        ["aiResult.pathologyFlag", "aiResult.conclusion"],
    ),
    "REPORT_CONCLUSION_CONFLICT": (
        "Текст описания противоречит тексту заключения",
        ["aiResult.report", "aiResult.conclusion"],
    ),
    "PATHOLOGY_TEXT_CONFLICT": (
        "Текст результата противоречит pathologyFlag",
        ["aiResult.pathologyFlag", "aiResult.report", "aiResult.conclusion"],
    ),
}


class SafetyEngine:
    """Assess whether a draft route can be shown for clinician review.

    The confidence threshold is a demo policy, not a clinical guideline. It is
    applied only to actionable positive findings and must be clinically
    validated and configured before production use.
    """

    POLICY_VERSION = "demo-safety-v1"

    def __init__(self, *, minimum_actionable_confidence: int = 60) -> None:
        if not 0 <= minimum_actionable_confidence <= 100:
            raise ValueError("minimum_actionable_confidence must be between 0 and 100")
        self.minimum_actionable_confidence = minimum_actionable_confidence

    def assess(
        self,
        study: NormalizedStudy,
        decision: RoutingDecision,
    ) -> SafetyResult:
        issues: list[SafetyIssue] = []

        if decision.study_id != study.study_id:
            issues.append(
                self._blocking_issue(
                    "STUDY_ID_MISMATCH",
                    "Маршрут относится к другому исследованию",
                    ["study_id", "routing.study_id"],
                )
            )

        for flag in study.parsing_flags:
            message_and_paths = _PARSING_FLAG_MESSAGES.get(flag)
            if message_and_paths is None:
                issues.append(
                    self._blocking_issue(
                        "UNRECOGNIZED_PARSING_FLAG",
                        f"Получен неизвестный флаг разбора: {flag}",
                        ["normalized.parsing_flags"],
                    )
                )
                continue
            message, evidence_paths = message_and_paths
            issues.append(self._blocking_issue(flag, message, evidence_paths))

        for finding in study.findings:
            if finding.code not in _ACTIONABLE_FINDING_CODES or not finding.present:
                continue
            if (
                finding.confidence is None
                or finding.confidence < self.minimum_actionable_confidence
            ):
                paths = [evidence.source_path for evidence in finding.evidence]
                confidence_text = (
                    "не указана"
                    if finding.confidence is None
                    else f"{finding.confidence}%"
                )
                issues.append(
                    self._blocking_issue(
                        "LOW_ACTIONABLE_FINDING_CONFIDENCE",
                        (
                            f"Уверенность для {finding.code} {confidence_text}; "
                            "нужна ручная проверка до маршрутизации"
                        ),
                        paths,
                    )
                )

        if (
            decision.rule_id == "MANUAL_REVIEW_FALLBACK"
            or decision.priority is RoutingPriority.MANUAL_REVIEW
        ):
            issues.append(
                self._blocking_issue(
                    "NO_VALIDATED_ROUTE",
                    "Для входных данных не найдено проверенное правило маршрутизации",
                    ["routing.rule_id"],
                )
            )

        if not decision.requires_human_review:
            issues.append(
                self._blocking_issue(
                    "HUMAN_REVIEW_NOT_REQUIRED_BY_ROUTE",
                    "Маршрут должен требовать подтверждения медицинским специалистом",
                    ["routing.requires_human_review"],
                )
            )

        for red_flag in decision.red_flags:
            issues.append(
                SafetyIssue(
                    code="CLINICAL_RED_FLAG",
                    severity=SafetyIssueSeverity.CRITICAL,
                    message=f"Требуется приоритетное внимание врача: {red_flag}",
                    evidence_paths=self._routing_evidence_paths(decision),
                )
            )

        has_blocker = any(
            issue.severity is SafetyIssueSeverity.BLOCKING for issue in issues
        )
        has_critical = any(
            issue.severity is SafetyIssueSeverity.CRITICAL for issue in issues
        )

        if has_blocker:
            disposition = SafetyDisposition.BLOCKED_PENDING_REVIEW
        elif has_critical:
            disposition = SafetyDisposition.ESCALATE_TO_CLINICIAN
        else:
            disposition = SafetyDisposition.CLEARED_FOR_REVIEW

        return SafetyResult(
            study_id=study.study_id,
            checked_rule_id=decision.rule_id,
            policy_version=self.POLICY_VERSION,
            disposition=disposition,
            route_usable=not has_blocker,
            patient_notification_allowed=False,
            requires_human_review=True,
            issues=issues,
            fallback_message=_FALLBACK_MESSAGE if has_blocker else None,
        )

    @staticmethod
    def _blocking_issue(
        code: str,
        message: str,
        evidence_paths: list[str],
    ) -> SafetyIssue:
        return SafetyIssue(
            code=code,
            severity=SafetyIssueSeverity.BLOCKING,
            message=message,
            evidence_paths=evidence_paths,
        )

    @staticmethod
    def _routing_evidence_paths(decision: RoutingDecision) -> list[str]:
        return sorted(
            {
                path
                for trace_step in decision.trace
                for path in trace_step.evidence_paths
            }
        )

