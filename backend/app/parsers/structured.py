"""Orchestrator that creates the unified structured study model."""

from app.models.kafka import RawKafkaMessage
from app.models.normalized import Modality, NormalizedStudy
from app.parsers.ct_chest import parse_ct_chest_findings
from app.parsers.mammography import parse_mammography_findings
from app.parsers.modality import detect_modality


class StructuredStudyParser:
    """Convert a validated BFT message into a transport-independent model."""

    def parse(
        self,
        message: RawKafkaMessage,
        *,
        source: str = "unknown",
    ) -> NormalizedStudy:
        modality = detect_modality(message)
        flags: list[str] = []

        if modality is Modality.CT_CHEST:
            findings = parse_ct_chest_findings(message)
        elif modality is Modality.MAMMOGRAPHY:
            findings = parse_mammography_findings(message)
        else:
            findings = []
            flags.append("UNSUPPORTED_OR_AMBIGUOUS_MODALITY")

        if message.ai_result.has_norma_conflict:
            flags.append("PATHOLOGY_NORMA_CONFLICT")

        if not message.ai_result.pathology_flag and findings:
            flags.append("PATHOLOGY_FINDINGS_CONFLICT")

        return NormalizedStudy(
            study_id=message.study_iuid,
            series_id=message.ai_result.series_iuid,
            source=source,
            modality=modality,
            pathology_present=message.ai_result.pathology_flag,
            overall_confidence=message.ai_result.confidence_level,
            model_id=message.ai_result.model_id,
            model_version=message.ai_result.model_version,
            report=message.ai_result.report,
            conclusion=message.ai_result.conclusion,
            findings=findings,
            parsing_flags=flags,
        )

