"""Tests for safe, deterministic report and conclusion parsing."""

from copy import deepcopy

import pytest

from app.adapters import DemoDataset
from app.models import Modality, RawKafkaMessage, TextAssertion, TextSource
from app.parsers import StudyParser, analyze_text


def _message(case_id: str) -> RawKafkaMessage:
    case = DemoDataset().get(case_id)
    return RawKafkaMessage.model_validate(case.payload)


def _study(case_id: str):
    return StudyParser().parse(_message(case_id), source="demo")


def test_normal_ct_text_is_explicitly_negated_without_conflicts() -> None:
    study = _study("ct-normal")

    assert len(study.text_signals) == 2
    assert {signal.assertion for signal in study.text_signals} == {
        TextAssertion.NEGATED
    }
    assert study.parsing_flags == []


def test_ct_nodule_text_is_present_and_traceable() -> None:
    study = _study("ct-lung-nodule")
    signals = [signal for signal in study.text_signals if signal.code == "CT_LUNG_NODULE"]

    assert {signal.source for signal in signals} == {
        TextSource.REPORT,
        TextSource.CONCLUSION,
    }
    assert {signal.assertion for signal in signals} == {TextAssertion.PRESENT}
    assert signals[0].evidence[0].source_path == "aiResult.report"


def test_uncertain_language_is_not_promoted_to_present() -> None:
    study = _study("ct-low-confidence")
    assertions = {
        signal.assertion
        for signal in study.text_signals
        if signal.code == "CT_LUNG_NODULE"
    }

    assert assertions == {TextAssertion.UNCERTAIN}


def test_pneumothorax_synonyms_are_detected() -> None:
    study = _study("ct-pneumothorax")

    assert [
        signal.source
        for signal in study.text_signals
        if signal.code == "CT_PNEUMOTHORAX"
    ] == [TextSource.REPORT, TextSource.CONCLUSION]


def test_mammography_keeps_negation_scope_per_sentence() -> None:
    study = _study("mmg-birads-2")
    benign = [signal for signal in study.text_signals if signal.code == "MMG_BENIGN_FINDING"]
    suspicious = [
        signal for signal in study.text_signals if signal.code == "MMG_SUSPICIOUS_FINDING"
    ]

    assert benign
    assert all(signal.assertion is TextAssertion.PRESENT for signal in benign)
    assert len(suspicious) == 1
    assert suspicious[0].assertion is TextAssertion.NEGATED


def test_birads_four_is_a_positive_suspicious_signal() -> None:
    study = _study("mmg-birads-4")

    assert any(
        signal.code == "MMG_SUSPICIOUS_FINDING"
        and signal.assertion is TextAssertion.PRESENT
        and signal.source is TextSource.CONCLUSION
        for signal in study.text_signals
    )


def test_conclusion_conflict_sets_all_auditable_flags() -> None:
    study = _study("conclusion-conflict")

    assert "STRUCTURED_CONCLUSION_CONFLICT" in study.parsing_flags
    assert "PATHOLOGY_CONCLUSION_CONFLICT" in study.parsing_flags
    assert "REPORT_CONCLUSION_CONFLICT" in study.parsing_flags


def test_positive_text_conflicts_with_negative_pathology_flag() -> None:
    payload = deepcopy(DemoDataset().get("ct-lung-nodule").payload)
    payload["aiResult"]["pathologyFlag"] = False
    payload["aiResult"]["norma"] = 1
    study = StudyParser().parse(RawKafkaMessage.model_validate(payload), source="test")

    assert "PATHOLOGY_TEXT_CONFLICT" in study.parsing_flags


@pytest.mark.parametrize(
    "text",
    [
        "Патологических изменений не выявлено.",
        "Не выявлено патологических изменений.",
        "Без признаков патологии органов грудной клетки.",
        "Патология отсутствует.",
    ],
)
def test_global_negation_word_order_variants(text: str) -> None:
    signals = analyze_text(
        text,
        source=TextSource.CONCLUSION,
        modality=Modality.CT_CHEST,
    )

    assert any(
        signal.code == "GLOBAL_PATHOLOGY"
        and signal.assertion is TextAssertion.NEGATED
        for signal in signals
    )


def test_unknown_modality_is_not_guessed_from_free_text() -> None:
    study = _study("unknown-modality")

    assert study.text_signals == []
    assert "UNSUPPORTED_OR_AMBIGUOUS_MODALITY" in study.parsing_flags

