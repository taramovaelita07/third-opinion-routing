"""Deterministic routing engine for normalized studies."""

from app.models import (
    NormalizedStudy,
    RoutingDecision,
    RoutingPriority,
    RoutingTraceStep,
    TraceStage,
)
from app.routing.rules import ROUTING_RULES, RoutingRule


class RoutingEngine:
    """Choose an explainable draft route without making a diagnosis."""

    def route(self, study: NormalizedStudy) -> RoutingDecision:
        finding_codes = {finding.code for finding in study.findings if finding.present}

        for rule in ROUTING_RULES:
            if rule.modality is study.modality and rule.finding_code in finding_codes:
                return self._decision_for_rule(study, rule)

        if not study.pathology_present and not study.findings:
            return self._normal_decision(study)

        return self._manual_review_decision(study)

    @staticmethod
    def _evidence_paths(study: NormalizedStudy, finding_code: str) -> list[str]:
        paths = {
            evidence.source_path
            for finding in study.findings
            if finding.code == finding_code
            for evidence in finding.evidence
        }
        return sorted(paths)

    def _decision_for_rule(
        self,
        study: NormalizedStudy,
        rule: RoutingRule,
    ) -> RoutingDecision:
        evidence_paths = self._evidence_paths(study, rule.finding_code)
        return RoutingDecision(
            study_id=study.study_id,
            rule_id=rule.rule_id,
            priority=rule.priority,
            action=rule.action,
            specialty=rule.specialty,
            timeframe=rule.timeframe,
            reason=rule.reason,
            prerequisites=list(rule.prerequisites),
            red_flags=list(rule.red_flags),
            matched_finding_codes=[rule.finding_code],
            trace=[
                RoutingTraceStep(
                    stage=TraceStage.SOURCE_RESULT,
                    description="Использованы структурированные поля результата внешнего ИИ",
                    evidence_paths=evidence_paths,
                ),
                RoutingTraceStep(
                    stage=TraceStage.NORMALIZED_FINDING,
                    description=f"Нормализована находка {rule.finding_code}",
                    evidence_paths=evidence_paths,
                ),
                RoutingTraceStep(
                    stage=TraceStage.ROUTING_RULE,
                    description=f"Применено демонстрационное правило {rule.rule_id}",
                ),
            ],
        )

    @staticmethod
    def _normal_decision(study: NormalizedStudy) -> RoutingDecision:
        return RoutingDecision(
            study_id=study.study_id,
            rule_id="NO_FINDINGS_ROUTINE_REVIEW",
            priority=RoutingPriority.ROUTINE,
            action="Передать результат лечащему врачу для планового ознакомления",
            specialty="Лечащий / направивший врач",
            timeframe="В плановом порядке",
            reason="В структурированном результате ИИ находки не указаны",
            prerequisites=("Подтвердить отсутствие значимых находок врачом",),
            trace=[
                RoutingTraceStep(
                    stage=TraceStage.SOURCE_RESULT,
                    description="pathologyFlag=false; структурированные находки отсутствуют",
                    evidence_paths=["aiResult.pathologyFlag", "aiResult.probParams"],
                ),
                RoutingTraceStep(
                    stage=TraceStage.ROUTING_RULE,
                    description="Применено демонстрационное правило NO_FINDINGS_ROUTINE_REVIEW",
                ),
            ],
        )

    @staticmethod
    def _manual_review_decision(study: NormalizedStudy) -> RoutingDecision:
        finding_codes = sorted(
            finding.code for finding in study.findings if finding.present
        )
        return RoutingDecision(
            study_id=study.study_id,
            rule_id="MANUAL_REVIEW_FALLBACK",
            priority=RoutingPriority.MANUAL_REVIEW,
            action="Передать исследование на ручную проверку до выбора маршрута",
            specialty="Врач-рентгенолог / ответственный клиницист",
            timeframe="До отправки рекомендации пациенту",
            reason="Для сочетания входных данных нет проверенного правила маршрутизации",
            prerequisites=("Не отправлять автоматическую рекомендацию пациенту",),
            matched_finding_codes=finding_codes,
            trace=[
                RoutingTraceStep(
                    stage=TraceStage.SOURCE_RESULT,
                    description="Получен результат, для которого маршрут не определён",
                    evidence_paths=["aiResult.probParams"],
                ),
                RoutingTraceStep(
                    stage=TraceStage.ROUTING_RULE,
                    description="Применено безопасное резервное правило MANUAL_REVIEW_FALLBACK",
                ),
            ],
        )

