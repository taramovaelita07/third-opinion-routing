"""Small SQLite repository with no external database dependency."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.models import (
    AnalysisHistoryItem,
    AnalysisResponse,
    AnalysisResult,
    BookingSlot,
    BookingStatus,
    CareJourneyResponse,
    NormalizedStudy,
    RawKafkaMessage,
    ReviewChoice,
    RoutingDecision,
    SafetyDisposition,
    SafetyResult,
    WorkflowStatus,
)

DEFAULT_DATABASE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "third_opinion.sqlite3"
)


class PersistenceError(RuntimeError):
    """Raised when a stored record cannot be read safely."""


class AnalysisRepository:
    """Persist complete analysis records and expose compact history rows."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()

    @classmethod
    def from_environment(cls) -> "AnalysisRepository":
        configured = os.getenv("DATABASE_PATH")
        path = Path(configured) if configured else DEFAULT_DATABASE_PATH
        return cls(path)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS analysis_records (
                    analysis_id TEXT PRIMARY KEY,
                    study_id TEXT NOT NULL,
                    modality TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    safety_disposition TEXT NOT NULL,
                    workflow_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    raw_input_json TEXT NOT NULL,
                    normalized_study_json TEXT NOT NULL,
                    routing_decision_json TEXT NOT NULL,
                    safety_result_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_analysis_records_created_at
                ON analysis_records(created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_analysis_records_study_id
                ON analysis_records(study_id);

                CREATE TABLE IF NOT EXISTS care_journeys (
                    analysis_id TEXT PRIMARY KEY,
                    review_choice TEXT NOT NULL,
                    appointment_target TEXT NOT NULL,
                    specialty TEXT NOT NULL,
                    clinician_note TEXT,
                    notification_message TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    booking_status TEXT NOT NULL,
                    booked_slot_json TEXT,
                    booked_at TEXT,
                    FOREIGN KEY (analysis_id) REFERENCES analysis_records(analysis_id)
                );

                PRAGMA user_version = 2;
                """
            )

    def save(
        self,
        message: RawKafkaMessage,
        result: AnalysisResult,
    ) -> AnalysisResponse:
        analysis_id = str(uuid4())
        created_at = datetime.now(timezone.utc)
        workflow_status = self._workflow_status(result.safety_result.disposition)
        raw_input = message.as_bft_dict()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_records (
                    analysis_id,
                    study_id,
                    modality,
                    priority,
                    safety_disposition,
                    workflow_status,
                    created_at,
                    raw_input_json,
                    normalized_study_json,
                    routing_decision_json,
                    safety_result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis_id,
                    result.normalized_study.study_id,
                    result.normalized_study.modality.value,
                    result.routing_decision.priority.value,
                    result.safety_result.disposition.value,
                    workflow_status.value,
                    created_at.isoformat(),
                    json.dumps(raw_input, ensure_ascii=False),
                    result.normalized_study.model_dump_json(),
                    result.routing_decision.model_dump_json(),
                    result.safety_result.model_dump_json(),
                ),
            )

        return AnalysisResponse(
            analysis_id=analysis_id,
            created_at=created_at,
            workflow_status=workflow_status,
            raw_input=raw_input,
            **result.model_dump(),
        )

    def get(self, analysis_id: str) -> AnalysisResponse | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM analysis_records WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchone()
        if row is None:
            return None
        return self._response_from_row(row)

    def list(self, *, limit: int = 50, offset: int = 0) -> list[AnalysisHistoryItem]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    analysis_id,
                    study_id,
                    modality,
                    priority,
                    safety_disposition,
                    workflow_status,
                    created_at
                FROM analysis_records
                ORDER BY created_at DESC, analysis_id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [AnalysisHistoryItem.model_validate(dict(row)) for row in rows]

    def save_review(
        self,
        *,
        analysis_id: str,
        review_choice: ReviewChoice,
        appointment_target: str,
        specialty: str,
        clinician_note: str | None,
        notification_message: str,
        available_slots: list[BookingSlot],
    ) -> CareJourneyResponse:
        reviewed_at = datetime.now(timezone.utc)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO care_journeys (
                    analysis_id,
                    review_choice,
                    appointment_target,
                    specialty,
                    clinician_note,
                    notification_message,
                    reviewed_at,
                    booking_status,
                    booked_slot_json,
                    booked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                ON CONFLICT(analysis_id) DO UPDATE SET
                    review_choice = excluded.review_choice,
                    appointment_target = excluded.appointment_target,
                    specialty = excluded.specialty,
                    clinician_note = excluded.clinician_note,
                    notification_message = excluded.notification_message,
                    reviewed_at = excluded.reviewed_at,
                    booking_status = excluded.booking_status,
                    booked_slot_json = NULL,
                    booked_at = NULL
                """,
                (
                    analysis_id,
                    review_choice.value,
                    appointment_target,
                    specialty,
                    clinician_note,
                    notification_message,
                    reviewed_at.isoformat(),
                    BookingStatus.READY_FOR_PATIENT.value,
                ),
            )
            connection.execute(
                """
                UPDATE analysis_records
                SET workflow_status = ?
                WHERE analysis_id = ?
                """,
                (WorkflowStatus.PATIENT_ACTION_AVAILABLE.value, analysis_id),
            )

        return CareJourneyResponse(
            analysis_id=analysis_id,
            review_choice=review_choice,
            appointment_target=appointment_target,
            specialty=specialty,
            clinician_note=clinician_note,
            notification_message=notification_message,
            reviewed_at=reviewed_at,
            booking_status=BookingStatus.READY_FOR_PATIENT,
            available_slots=available_slots,
        )

    def get_care_journey(
        self,
        analysis_id: str,
        *,
        available_slots: list[BookingSlot],
    ) -> CareJourneyResponse | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM care_journeys WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchone()
        if row is None:
            return None
        return self._journey_from_row(row, available_slots=available_slots)

    def book(
        self,
        analysis_id: str,
        *,
        slot: BookingSlot,
    ) -> CareJourneyResponse | None:
        booked_at = datetime.now(timezone.utc)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT analysis_id FROM care_journeys WHERE analysis_id = ?",
                (analysis_id,),
            ).fetchone()
            if existing is None:
                return None
            connection.execute(
                """
                UPDATE care_journeys
                SET booking_status = ?, booked_slot_json = ?, booked_at = ?
                WHERE analysis_id = ?
                """,
                (
                    BookingStatus.BOOKED.value,
                    slot.model_dump_json(),
                    booked_at.isoformat(),
                    analysis_id,
                ),
            )
            connection.execute(
                """
                UPDATE analysis_records
                SET workflow_status = ?
                WHERE analysis_id = ?
                """,
                (WorkflowStatus.APPOINTMENT_BOOKED.value, analysis_id),
            )

        return self.get_care_journey(analysis_id, available_slots=[])

    def clear_demo_data(self) -> tuple[int, int]:
        """Delete persisted synthetic analyses and their care journeys atomically."""

        with self._connect() as connection:
            journey_count = connection.execute(
                "SELECT COUNT(*) FROM care_journeys"
            ).fetchone()[0]
            analysis_count = connection.execute(
                "SELECT COUNT(*) FROM analysis_records"
            ).fetchone()[0]
            connection.execute("DELETE FROM care_journeys")
            connection.execute("DELETE FROM analysis_records")
        return analysis_count, journey_count

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _workflow_status(disposition: SafetyDisposition) -> WorkflowStatus:
        if disposition is SafetyDisposition.BLOCKED_PENDING_REVIEW:
            return WorkflowStatus.BLOCKED_PENDING_REVIEW
        if disposition is SafetyDisposition.ESCALATE_TO_CLINICIAN:
            return WorkflowStatus.ESCALATED_FOR_REVIEW
        return WorkflowStatus.PENDING_CLINICIAN_REVIEW

    @staticmethod
    def _response_from_row(row: sqlite3.Row) -> AnalysisResponse:
        try:
            return AnalysisResponse(
                analysis_id=row["analysis_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                workflow_status=WorkflowStatus(row["workflow_status"]),
                raw_input=json.loads(row["raw_input_json"]),
                normalized_study=NormalizedStudy.model_validate_json(
                    row["normalized_study_json"]
                ),
                routing_decision=RoutingDecision.model_validate_json(
                    row["routing_decision_json"]
                ),
                safety_result=SafetyResult.model_validate_json(
                    row["safety_result_json"]
                ),
            )
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise PersistenceError("Stored analysis record is invalid") from exc

    @staticmethod
    def _journey_from_row(
        row: sqlite3.Row,
        *,
        available_slots: list[BookingSlot],
    ) -> CareJourneyResponse:
        try:
            booked_slot = (
                BookingSlot.model_validate_json(row["booked_slot_json"])
                if row["booked_slot_json"]
                else None
            )
            booking_status = BookingStatus(row["booking_status"])
            return CareJourneyResponse(
                analysis_id=row["analysis_id"],
                review_choice=ReviewChoice(row["review_choice"]),
                appointment_target=row["appointment_target"],
                specialty=row["specialty"],
                clinician_note=row["clinician_note"],
                notification_message=row["notification_message"],
                reviewed_at=datetime.fromisoformat(row["reviewed_at"]),
                booking_status=booking_status,
                available_slots=(
                    available_slots
                    if booking_status is BookingStatus.READY_FOR_PATIENT
                    else []
                ),
                booked_slot=booked_slot,
                booked_at=(
                    datetime.fromisoformat(row["booked_at"])
                    if row["booked_at"]
                    else None
                ),
            )
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise PersistenceError("Stored care journey is invalid") from exc
