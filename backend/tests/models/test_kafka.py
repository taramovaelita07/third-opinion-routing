"""Validation tests for the BFT Kafka message contract."""

import pytest
from pydantic import ValidationError

from app.models.kafka import RawKafkaMessage


def ct_message() -> dict:
    return {
        "studyIUID": "1.2.643.demo.ct.001",
        "aiResult": {
            "seriesIUID": "1.2.643.demo.ct.001.1",
            "pathologyFlag": True,
            "norma": 0,
            "confidenceLevel": 92,
            "modelId": 1000,
            "modelVersion": "1.0.0",
            "report": "В правом легком определяется очаговое образование.",
            "conclusion": "Признаки очагового образования правого легкого.",
            "dateTimeParams": {
                "processStartDT": "2026-10-03T10:00:00Z",
                "processEndDT": "2026-10-03T10:00:08Z"
            },
            "probParams": {
                "ct_lc": {
                    "ct_lc_conf_level": 92,
                    "ct_lc_lin_x": "12",
                    "ct_lc_lin_y": "9",
                    "ct_lc_volume": "610",
                    "ct_lc_num": 1
                }
            }
        }
    }


def test_valid_ct_message_is_parsed() -> None:
    message = RawKafkaMessage.model_validate(ct_message())

    assert message.study_iuid == "1.2.643.demo.ct.001"
    assert message.ai_result.prob_params.ct_lung_cancer is not None
    assert message.ai_result.prob_params.ct_lung_cancer.confidence_level == 92
    assert message.ai_result.has_norma_conflict is False


def test_message_serializes_back_to_bft_keys() -> None:
    message = RawKafkaMessage.model_validate(ct_message())
    serialized = message.as_bft_dict()

    assert serialized["studyIUID"] == "1.2.643.demo.ct.001"
    assert serialized["aiResult"]["probParams"]["ct_lc"]["ct_lc_conf_level"] == 92


def test_norma_conflict_is_preserved_for_safety_layer() -> None:
    payload = ct_message()
    payload["aiResult"]["norma"] = 1

    message = RawKafkaMessage.model_validate(payload)

    assert message.ai_result.has_norma_conflict is True


@pytest.mark.parametrize("missing_field", ["studyIUID", "aiResult"])
def test_missing_root_field_is_rejected(missing_field: str) -> None:
    payload = ct_message()
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        RawKafkaMessage.model_validate(payload)


@pytest.mark.parametrize("confidence", [-1, 101])
def test_invalid_confidence_is_rejected(confidence: int) -> None:
    payload = ct_message()
    payload["aiResult"]["confidenceLevel"] = confidence

    with pytest.raises(ValidationError):
        RawKafkaMessage.model_validate(payload)


def test_blank_report_is_rejected() -> None:
    payload = ct_message()
    payload["aiResult"]["report"] = "   "

    with pytest.raises(ValidationError):
        RawKafkaMessage.model_validate(payload)


def test_unknown_prob_params_are_preserved() -> None:
    payload = ct_message()
    payload["aiResult"]["probParams"]["future_modality"] = {"value": 42}

    message = RawKafkaMessage.model_validate(payload)
    serialized = message.as_bft_dict()

    assert serialized["aiResult"]["probParams"]["future_modality"] == {"value": 42}

