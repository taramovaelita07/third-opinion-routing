"""End-to-end normalization pipeline for a validated BFT message."""

from app.models.kafka import RawKafkaMessage
from app.models.normalized import (
    NormalizedStudy,
    TextAssertion,
    TextSignal,
    TextSource,
)
from app.parsers.structured import StructuredStudyParser
from app.parsers.text import analyze_text


_NON_PATHOLOGICAL_CODES = {"MMG_BENIGN_FINDING"}


def _has_positive_pathology(signals: list[TextSignal]) -> bool:
    return any(
        signal.code not in _NON_PATHOLOGICAL_CODES
        and signal.assertion in {TextAssertion.PRESENT, TextAssertion.UNCERTAIN}
        for signal in signals
    )


def _has_global_negation(signals: list[TextSignal]) -> bool:
    return any(
        signal.code == "GLOBAL_PATHOLOGY"
        and signal.assertion is TextAssertion.NEGATED
        for signal in signals
    )


def _append_once(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


class StudyParser:
    """Combine structured normalization with conservative text analysis."""

    def __init__(self) -> None:
        self._structured_parser = StructuredStudyParser()

    def parse(
        self,
        message: RawKafkaMessage,
        *,
        source: str = "unknown",
    ) -> NormalizedStudy:
        study = self._structured_parser.parse(message, source=source)
        report_signals = analyze_text(
            study.report,
            source=TextSource.REPORT,
            modality=study.modality,
        )
        conclusion_signals = analyze_text(
            study.conclusion,
            source=TextSource.CONCLUSION,
            modality=study.modality,
        )
        all_signals = report_signals + conclusion_signals
        flags = list(study.parsing_flags)

        conclusion_is_globally_negative = _has_global_negation(conclusion_signals)
        if conclusion_is_globally_negative and study.findings:
            _append_once(flags, "STRUCTURED_CONCLUSION_CONFLICT")
        if conclusion_is_globally_negative and study.pathology_present:
            _append_once(flags, "PATHOLOGY_CONCLUSION_CONFLICT")
        if conclusion_is_globally_negative and _has_positive_pathology(report_signals):
            _append_once(flags, "REPORT_CONCLUSION_CONFLICT")
        if not study.pathology_present and _has_positive_pathology(all_signals):
            _append_once(flags, "PATHOLOGY_TEXT_CONFLICT")

        report_by_code = {
            signal.code: signal.assertion
            for signal in report_signals
            if signal.code != "GLOBAL_PATHOLOGY"
        }
        for signal in conclusion_signals:
            report_assertion = report_by_code.get(signal.code)
            if (
                report_assertion in {TextAssertion.PRESENT, TextAssertion.UNCERTAIN}
                and signal.assertion is TextAssertion.NEGATED
            ):
                _append_once(flags, "REPORT_CONCLUSION_CONFLICT")

        return study.model_copy(
            update={"text_signals": all_signals, "parsing_flags": flags}
        )

