"""Loader for the fully synthetic offline demo dataset."""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.models.kafka import RawKafkaMessage

DEFAULT_DATASET_DIRECTORY = Path(__file__).resolve().parents[3] / "data" / "demo"


class DemoDatasetError(RuntimeError):
    """Raised when the bundled demo dataset is missing or inconsistent."""


class ExpectedOutcome(BaseModel):
    """Expected behavior used later by routing and safety tests."""

    model_config = ConfigDict(extra="forbid")

    validation: Literal["valid", "invalid"]
    finding_codes: list[str]
    route: str
    priority: str
    specialty: str | None
    timeframe: str
    human_review: bool


class DemoCaseMetadata(BaseModel):
    """Human-readable metadata stored separately from the raw BFT payload."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str
    modality: str
    payload_file: str
    expected: ExpectedOutcome


class DemoCase(BaseModel):
    """One manifest entry joined with its untouched synthetic payload."""

    metadata: DemoCaseMetadata
    payload: dict[str, Any]


class DemoDataset:
    """Read, verify, and expose the offline demo cases."""

    def __init__(self, directory: Path = DEFAULT_DATASET_DIRECTORY) -> None:
        self.directory = directory.resolve()
        self.manifest_path = self.directory / "manifest.json"

    def load(self) -> list[DemoCase]:
        """Load all cases and verify each declared validation outcome."""

        if not self.manifest_path.is_file():
            raise DemoDatasetError(f"Demo manifest not found: {self.manifest_path}")

        manifest_data = self._read_json(self.manifest_path)
        if not isinstance(manifest_data, list):
            raise DemoDatasetError("Demo manifest must contain a JSON array")

        cases: list[DemoCase] = []
        seen_ids: set[str] = set()

        for raw_metadata in manifest_data:
            metadata = DemoCaseMetadata.model_validate(raw_metadata)
            if metadata.id in seen_ids:
                raise DemoDatasetError(f"Duplicate demo case id: {metadata.id}")
            seen_ids.add(metadata.id)

            payload_path = (self.directory / metadata.payload_file).resolve()
            if self.directory not in payload_path.parents:
                raise DemoDatasetError(
                    f"Demo payload escapes the dataset directory: {metadata.payload_file}"
                )
            if not payload_path.is_file():
                raise DemoDatasetError(f"Demo payload not found: {payload_path}")

            payload = self._read_json(payload_path)
            if not isinstance(payload, dict):
                raise DemoDatasetError(f"Demo payload must be a JSON object: {payload_path}")

            is_valid = self._is_valid_bft_payload(payload)
            expected_valid = metadata.expected.validation == "valid"
            if is_valid != expected_valid:
                raise DemoDatasetError(
                    f"Unexpected validation result for demo case: {metadata.id}"
                )

            cases.append(DemoCase(metadata=metadata, payload=payload))

        return cases

    def get(self, case_id: str) -> DemoCase:
        """Return one case by its stable identifier."""

        for case in self.load():
            if case.metadata.id == case_id:
                return case
        raise KeyError(f"Unknown demo case: {case_id}")

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DemoDatasetError(f"Cannot read demo JSON: {path}") from exc

    @staticmethod
    def _is_valid_bft_payload(payload: dict[str, Any]) -> bool:
        try:
            RawKafkaMessage.model_validate(payload)
        except ValueError:
            return False
        return True

