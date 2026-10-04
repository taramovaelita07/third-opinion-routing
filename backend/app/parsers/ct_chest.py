"""Structured CT chest finding parser."""

from typing import Any

from app.models.kafka import RawKafkaMessage
from app.models.normalized import Evidence, Finding, Laterality


def parse_ct_chest_findings(message: RawKafkaMessage) -> list[Finding]:
    """Normalize supported CT chest probParams without interpreting images."""

    findings: list[Finding] = []
    params = message.ai_result.prob_params

    lung_nodule = params.ct_lung_cancer
    if lung_nodule is not None and lung_nodule.number not in (None, 0):
        measurements: dict[str, int | float | str] = {}
        if lung_nodule.linear_x is not None:
            measurements["x_mm"] = lung_nodule.linear_x
        if lung_nodule.linear_y is not None:
            measurements["y_mm"] = lung_nodule.linear_y
        if lung_nodule.volume is not None:
            measurements["volume_mm3"] = lung_nodule.volume
        measurements["count_class"] = lung_nodule.number

        findings.append(
            Finding(
                code="CT_LUNG_NODULE",
                display_name="Очаговое образование лёгкого",
                confidence=lung_nodule.confidence_level,
                laterality=Laterality.UNKNOWN,
                location="LUNG",
                measurements=measurements,
                evidence=[
                    Evidence(
                        source_path="aiResult.probParams.ct_lc",
                        raw_value=lung_nodule.model_dump(by_alias=True),
                    )
                ],
            )
        )

    raw_extra = params.model_extra or {}
    pneumothorax = raw_extra.get("ct_chest_pneumotorax")
    if isinstance(pneumothorax, dict):
        finding = _parse_pneumothorax(pneumothorax)
        if finding is not None:
            findings.append(finding)

    return findings


def _parse_pneumothorax(raw: dict[str, Any]) -> Finding | None:
    right_volume = _number(raw.get("ct_chest_pneumotorax_vol_right"))
    left_volume = _number(raw.get("ct_chest_pneumotorax_vol_left"))

    right_present = right_volume is not None and right_volume > 0
    left_present = left_volume is not None and left_volume > 0
    if not right_present and not left_present:
        return None

    if right_present and left_present:
        laterality = Laterality.BILATERAL
    elif right_present:
        laterality = Laterality.RIGHT
    else:
        laterality = Laterality.LEFT

    measurements: dict[str, int | float | str] = {}
    if right_volume is not None:
        measurements["right_volume_ml"] = right_volume
    if left_volume is not None:
        measurements["left_volume_ml"] = left_volume

    confidence = _integer(raw.get("ct_chest_pneumotorax_conf_level"))
    if confidence is not None and not 0 <= confidence <= 100:
        confidence = None

    return Finding(
        code="CT_PNEUMOTHORAX",
        display_name="Пневмоторакс",
        confidence=confidence,
        laterality=laterality,
        location="PLEURAL_CAVITY",
        measurements=measurements,
        evidence=[
            Evidence(
                source_path="aiResult.probParams.ct_chest_pneumotorax",
                raw_value=raw,
            )
        ],
    )


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value

