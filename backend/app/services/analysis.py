"""Synchronous end-to-end analysis service used by REST and future consumers."""

from app.models import AnalysisResult, RawKafkaMessage
from app.parsers import StudyParser
from app.routing import RoutingEngine
from app.safety import SafetyEngine


class AnalysisService:
    """Run parsing, routing, and safety in a fixed auditable order."""

    def __init__(self) -> None:
        self._parser = StudyParser()
        self._routing = RoutingEngine()
        self._safety = SafetyEngine()

    def analyze(
        self,
        message: RawKafkaMessage,
        *,
        source: str,
    ) -> AnalysisResult:
        study = self._parser.parse(message, source=source)
        decision = self._routing.route(study)
        safety = self._safety.assess(study, decision)
        return AnalysisResult(
            normalized_study=study,
            routing_decision=decision,
            safety_result=safety,
        )
