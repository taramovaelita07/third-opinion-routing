"""Conservative modality detection from BFT probParams namespaces."""

from app.models.kafka import RawKafkaMessage
from app.models.normalized import Modality


def detect_modality(message: RawKafkaMessage) -> Modality:
    """Detect supported modality without guessing from free text.

    The BFT Kafka envelope has no explicit original-modality field. For the MVP,
    modality is inferred only from documented probParams namespaces. Ambiguous
    or unknown inputs stay UNKNOWN and will later require human review.
    """

    raw_params = message.ai_result.prob_params.model_dump(
        by_alias=True,
        exclude_none=True,
    )
    keys = set(raw_params)

    has_ct = any(key.startswith("ct_") for key in keys)
    has_mammography = "mmg" in keys or any(key.startswith("mmg_") for key in keys)

    if has_ct and not has_mammography:
        return Modality.CT_CHEST
    if has_mammography and not has_ct:
        return Modality.MAMMOGRAPHY
    return Modality.UNKNOWN
