"""Pydantic models for the BFT DICOMREPORTNOTIFY Kafka payload.

The BFT document contains a shared message envelope and modality-specific
objects inside ``probParams``. Only the two core MVP modalities are typed here:
CT chest and mammography. Unknown BFT-compatible modality blocks are preserved
for later adapters instead of being silently discarded.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Confidence = Annotated[int, Field(ge=0, le=100)]
BinaryFlag = Literal[0, 1]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class BFTModel(BaseModel):
    """Base configuration for fields whose JSON names use camelCase."""

    model_config = ConfigDict(populate_by_name=True)


class DateTimeParams(BFTModel):
    """Technical processing timestamps from the BFT message.

    They are optional for the offline demo because they do not influence the
    clinical route. When present, Pydantic validates them as ISO 8601 values.
    """

    download_start: datetime | None = Field(default=None, alias="downloadStartDT")
    download_end: datetime | None = Field(default=None, alias="downloadEndDT")
    process_start: datetime | None = Field(default=None, alias="processStartDT")
    process_end: datetime | None = Field(default=None, alias="processEndDT")


class CTLungCancerParams(BFTModel):
    """Structured CT chest fields for pulmonary nodules from the BFT."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    confidence_level: Confidence = Field(alias="ct_lc_conf_level")
    linear_x: str | None = Field(default=None, alias="ct_lc_lin_x")
    linear_y: str | None = Field(default=None, alias="ct_lc_lin_y")
    volume: str | None = Field(default=None, alias="ct_lc_volume")
    number: Annotated[int, Field(ge=0, le=2)] | None = Field(
        default=None,
        alias="ct_lc_num",
    )


class MammographyParams(BFTModel):
    """Structured mammography fields from the BFT Kafka contract."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    confidence_level: Confidence = Field(alias="mmg_conf_level")
    pgmi_right: Literal["P", "G", "M", "I"] | None = Field(
        default=None,
        alias="mmg_pgmi_right",
    )
    pgmi_left: Literal["P", "G", "M", "I"] | None = Field(
        default=None,
        alias="mmg_pgmi_left",
    )
    acr_right: Literal["A", "B", "C", "D"] | None = Field(
        default=None,
        alias="mmg_acr_right",
    )
    acr_left: Literal["A", "B", "C", "D"] | None = Field(
        default=None,
        alias="mmg_acr_left",
    )
    birads_right: Annotated[int, Field(ge=1, le=5)] | None = Field(
        default=None,
        alias="mmg_rads_right",
    )
    birads_left: Annotated[int, Field(ge=1, le=5)] | None = Field(
        default=None,
        alias="mmg_rads_left",
    )
    malignancy_right: BinaryFlag | None = Field(
        default=None,
        alias="mmg_malignancy_right",
    )
    benign_right: BinaryFlag | None = Field(default=None, alias="mmg_benign_right")
    suspicious_calcifications_right: BinaryFlag | None = Field(
        default=None,
        alias="mmg_calcification_right",
    )
    lymph_nodes_right: BinaryFlag | None = Field(
        default=None,
        alias="mmg_lymph_right",
    )
    architecture_distortion_right: BinaryFlag | None = Field(
        default=None,
        alias="mmg_architect_right",
    )
    skin_thickening_right: BinaryFlag | None = Field(
        default=None,
        alias="mmg_thickening_right",
    )
    malignancy_left: BinaryFlag | None = Field(
        default=None,
        alias="mmg_malignancy_left",
    )
    benign_left: BinaryFlag | None = Field(default=None, alias="mmg_benign_left")
    suspicious_calcifications_left: BinaryFlag | None = Field(
        default=None,
        alias="mmg_calcification_left",
    )
    lymph_nodes_left: BinaryFlag | None = Field(
        default=None,
        alias="mmg_lymph_left",
    )
    architecture_distortion_left: BinaryFlag | None = Field(
        default=None,
        alias="mmg_architect_left",
    )
    skin_thickening_left: BinaryFlag | None = Field(
        default=None,
        alias="mmg_thickening_left",
    )


class ProbParams(BFTModel):
    """Known modality blocks plus preserved future BFT fields."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    ct_lung_cancer: CTLungCancerParams | None = Field(default=None, alias="ct_lc")
    mammography: MammographyParams | None = Field(default=None, alias="mmg")


class AIResult(BFTModel):
    """Result produced by an external radiology AI service."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    series_iuid: NonEmptyText = Field(alias="seriesIUID")
    pathology_flag: bool = Field(alias="pathologyFlag")
    norma: BinaryFlag | None = None
    confidence_level: Confidence = Field(alias="confidenceLevel")
    model_id: int = Field(alias="modelId")
    model_version: NonEmptyText = Field(alias="modelVersion")
    report: NonEmptyText
    conclusion: NonEmptyText
    date_time_params: DateTimeParams = Field(
        default_factory=DateTimeParams,
        alias="dateTimeParams",
    )
    prob_params: ProbParams = Field(default_factory=ProbParams, alias="probParams")

    @property
    def has_norma_conflict(self) -> bool:
        """Return True when ``pathologyFlag`` contradicts BFT ``norma``.

        BFT defines norma=1 as a study without pathology and norma=0 as a study
        with pathology. A conflict is preserved for the future Safety Layer;
        schema validation must not hide or arbitrarily resolve it.
        """

        if self.norma is None:
            return False
        expected_pathology = self.norma == 0
        return self.pathology_flag != expected_pathology


class RawKafkaMessage(BFTModel):
    """Top-level DICOMREPORTNOTIFY message used by the MVP."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    study_iuid: NonEmptyText = Field(alias="studyIUID")
    ai_result: AIResult = Field(alias="aiResult")

    def as_bft_dict(self) -> dict[str, Any]:
        """Serialize with the original BFT JSON keys for audit and transport."""

        return self.model_dump(mode="json", by_alias=True)
