"""Tests for modality detection and structured normalization."""

import pytest

from app.adapters import DemoDataset
from app.models import Laterality, Modality, RawKafkaMessage
from app.parsers import StructuredStudyParser, detect_modality


def _message(case_id: str) -> RawKafkaMessage:
    case = DemoDataset().get(case_id)
    return RawKafkaMessage.model_validate(case.payload)


@pytest.mark.parametrize(
    ("case_id", "expected_modality"),
    [
        ("ct-normal", Modality.CT_CHEST),
        ("ct-lung-nodule", Modality.CT_CHEST),
        ("ct-pneumothorax", Modality.CT_CHEST),
        ("mmg-birads-2", Modality.MAMMOGRAPHY),
        ("mmg-birads-4", Modality.MAMMOGRAPHY),
        ("unknown-modality", Modality.UNKNOWN),
    ],
)
def test_modality_detection(case_id: str, expected_modality: Modality) -> None:
    assert detect_modality(_message(case_id)) is expected_modality


def test_ct_normal_contains_no_findings() -> None:
    study = StructuredStudyParser().parse(_message("ct-normal"), source="demo")

    assert study.modality is Modality.CT_CHEST
    assert study.findings == []
    assert study.parsing_flags == []


def test_ct_lung_nodule_is_normalized_with_evidence() -> None:
    study = StructuredStudyParser().parse(
        _message("ct-lung-nodule"),
        source="demo",
    )

    assert [finding.code for finding in study.findings] == ["CT_LUNG_NODULE"]
    finding = study.findings[0]
    assert finding.confidence == 92
    assert finding.measurements["x_mm"] == "12"
    assert finding.evidence[0].source_path == "aiResult.probParams.ct_lc"


def test_ct_pneumothorax_is_normalized_with_laterality() -> None:
    study = StructuredStudyParser().parse(
        _message("ct-pneumothorax"),
        source="demo",
    )

    finding = study.findings[0]
    assert finding.code == "CT_PNEUMOTHORAX"
    assert finding.laterality is Laterality.RIGHT
    assert finding.measurements["right_volume_ml"] == 124


@pytest.mark.parametrize(
    ("case_id", "expected_code", "expected_classification"),
    [
        ("mmg-birads-2", "MMG_BENIGN_FINDING", "BI-RADS 2"),
        ("mmg-birads-4", "MMG_SUSPICIOUS_FINDING", "BI-RADS 4"),
    ],
)
def test_mammography_is_normalized_per_side(
    case_id: str,
    expected_code: str,
    expected_classification: str,
) -> None:
    study = StructuredStudyParser().parse(_message(case_id), source="demo")

    assert study.findings[0].code == expected_code
    assert study.findings[0].classification == expected_classification
    assert study.findings[0].laterality is Laterality.RIGHT


def test_unknown_modality_is_flagged_without_guessing() -> None:
    study = StructuredStudyParser().parse(
        _message("unknown-modality"),
        source="demo",
    )

    assert study.modality is Modality.UNKNOWN
    assert study.findings == []
    assert "UNSUPPORTED_OR_AMBIGUOUS_MODALITY" in study.parsing_flags


def test_pathology_norma_conflict_is_carried_forward() -> None:
    study = StructuredStudyParser().parse(
        _message("conflicting-norma"),
        source="demo",
    )

    assert "PATHOLOGY_NORMA_CONFLICT" in study.parsing_flags

