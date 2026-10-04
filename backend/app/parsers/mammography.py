"""Structured mammography finding parser."""

from app.models.kafka import MammographyParams, RawKafkaMessage
from app.models.normalized import Evidence, Finding, Laterality


def parse_mammography_findings(message: RawKafkaMessage) -> list[Finding]:
    """Normalize BFT mammography fields separately for right and left sides."""

    params = message.ai_result.prob_params.mammography
    if params is None:
        return []

    findings: list[Finding] = []
    right = _parse_side(params, side="right", laterality=Laterality.RIGHT)
    left = _parse_side(params, side="left", laterality=Laterality.LEFT)
    if right is not None:
        findings.append(right)
    if left is not None:
        findings.append(left)
    return findings


def _parse_side(
    params: MammographyParams,
    *,
    side: str,
    laterality: Laterality,
) -> Finding | None:
    birads = getattr(params, f"birads_{side}")
    malignancy = getattr(params, f"malignancy_{side}")
    benign = getattr(params, f"benign_{side}")
    suspicious_calcifications = getattr(
        params,
        f"suspicious_calcifications_{side}",
    )

    if birads is not None and birads >= 4 or malignancy == 1 or suspicious_calcifications == 1:
        code = "MMG_SUSPICIOUS_FINDING"
        display_name = "Подозрительная находка молочной железы"
    elif birads == 3:
        code = "MMG_PROBABLY_BENIGN_FINDING"
        display_name = "Вероятно доброкачественная находка молочной железы"
    elif birads == 2 or benign == 1:
        code = "MMG_BENIGN_FINDING"
        display_name = "Доброкачественная находка молочной железы"
    else:
        return None

    side_key = "right" if side == "right" else "left"
    evidence_value = {
        "birads": birads,
        "malignancy": malignancy,
        "benign": benign,
        "suspicious_calcifications": suspicious_calcifications,
    }

    return Finding(
        code=code,
        display_name=display_name,
        confidence=params.confidence_level,
        laterality=laterality,
        location="BREAST",
        classification=f"BI-RADS {birads}" if birads is not None else None,
        evidence=[
            Evidence(
                source_path=f"aiResult.probParams.mmg.{side_key}",
                raw_value=evidence_value,
            )
        ],
    )

