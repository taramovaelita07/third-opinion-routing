"""Tests for the synthetic offline demo dataset."""

import pytest

from app.adapters.demo_adapter import DemoDataset


def test_demo_dataset_contains_ten_cases() -> None:
    cases = DemoDataset().load()

    assert len(cases) == 10
    assert len({case.metadata.id for case in cases}) == 10


def test_demo_dataset_contains_both_core_modalities() -> None:
    modalities = {case.metadata.modality for case in DemoDataset().load()}

    assert {"CT_CHEST", "MAMMOGRAPHY"}.issubset(modalities)


def test_demo_dataset_has_one_intentionally_invalid_payload() -> None:
    cases = DemoDataset().load()
    invalid_cases = [
        case for case in cases if case.metadata.expected.validation == "invalid"
    ]

    assert [case.metadata.id for case in invalid_cases] == ["missing-ai-result"]


def test_demo_payloads_use_synthetic_study_identifiers() -> None:
    for case in DemoDataset().load():
        study_id = case.payload.get("studyIUID", "")
        assert study_id.startswith("1.2.643.demo.")


def test_get_returns_requested_case() -> None:
    case = DemoDataset().get("mmg-birads-4")

    assert case.metadata.modality == "MAMMOGRAPHY"


def test_get_rejects_unknown_case() -> None:
    with pytest.raises(KeyError, match="Unknown demo case"):
        DemoDataset().get("does-not-exist")

