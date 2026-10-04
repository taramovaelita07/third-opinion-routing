"""Tests for SQLite analysis history."""

import sqlite3

from app.adapters import DemoDataset
from app.models import RawKafkaMessage, ReviewChoice, WorkflowStatus
from app.persistence import AnalysisRepository
from app.services import AnalysisService, available_booking_slots


def _save(repository: AnalysisRepository, case_id: str):
    case = DemoDataset().get(case_id)
    message = RawKafkaMessage.model_validate(case.payload)
    result = AnalysisService().analyze(message, source=f"test:{case_id}")
    return repository.save(message, result)


def test_repository_initializes_versioned_schema(tmp_path) -> None:
    database_path = tmp_path / "history.sqlite3"
    repository = AnalysisRepository(database_path)

    repository.initialize()

    with sqlite3.connect(database_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'analysis_records'"
        ).fetchone()
        journey_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'care_journeys'"
        ).fetchone()
    assert version == 2
    assert table == ("analysis_records",)
    assert journey_table == ("care_journeys",)


def test_saved_record_round_trips_complete_audit_data(tmp_path) -> None:
    repository = AnalysisRepository(tmp_path / "history.sqlite3")
    repository.initialize()
    saved = _save(repository, "ct-lung-nodule")

    loaded = repository.get(saved.analysis_id)

    assert loaded == saved
    assert loaded is not None
    assert loaded.raw_input["studyIUID"] == saved.normalized_study.study_id
    assert loaded.workflow_status is WorkflowStatus.PENDING_CLINICIAN_REVIEW


def test_records_survive_repository_recreation(tmp_path) -> None:
    database_path = tmp_path / "history.sqlite3"
    first_repository = AnalysisRepository(database_path)
    first_repository.initialize()
    saved = _save(first_repository, "mmg-birads-4")

    reopened_repository = AnalysisRepository(database_path)
    reopened_repository.initialize()

    assert reopened_repository.get(saved.analysis_id) == saved


def test_history_contains_compact_rows(tmp_path) -> None:
    repository = AnalysisRepository(tmp_path / "history.sqlite3")
    repository.initialize()
    first = _save(repository, "ct-normal")
    second = _save(repository, "ct-pneumothorax")

    history = repository.list(limit=1)

    assert len(history) == 1
    assert history[0].analysis_id == second.analysis_id
    assert history[0].analysis_id != first.analysis_id
    assert history[0].workflow_status is WorkflowStatus.ESCALATED_FOR_REVIEW


def test_blocked_result_gets_blocked_workflow_status(tmp_path) -> None:
    repository = AnalysisRepository(tmp_path / "history.sqlite3")
    repository.initialize()

    saved = _save(repository, "conclusion-conflict")

    assert saved.workflow_status is WorkflowStatus.BLOCKED_PENDING_REVIEW


def test_review_enables_patient_action_and_round_trips(tmp_path) -> None:
    repository = AnalysisRepository(tmp_path / "history.sqlite3")
    repository.initialize()
    saved = _save(repository, "ct-lung-nodule")
    slots = available_booking_slots()

    reviewed = repository.save_review(
        analysis_id=saved.analysis_id,
        review_choice=ReviewChoice.RECOMMENDED_SPECIALIST,
        appointment_target=saved.routing_decision.action,
        specialty=saved.routing_decision.specialty,
        clinician_note="Проверено врачом",
        notification_message="Доступна запись",
        available_slots=slots,
    )

    assert reviewed.available_slots == slots
    assert reviewed.patient_notification_allowed is True
    assert repository.get(saved.analysis_id).workflow_status is WorkflowStatus.PATIENT_ACTION_AVAILABLE
    assert repository.get_care_journey(saved.analysis_id, available_slots=slots) == reviewed


def test_booked_slot_is_persisted_and_updates_workflow(tmp_path) -> None:
    database_path = tmp_path / "history.sqlite3"
    repository = AnalysisRepository(database_path)
    repository.initialize()
    saved = _save(repository, "mmg-birads-4")
    slots = available_booking_slots()
    repository.save_review(
        analysis_id=saved.analysis_id,
        review_choice=ReviewChoice.RECOMMENDED_SPECIALIST,
        appointment_target=saved.routing_decision.action,
        specialty=saved.routing_decision.specialty,
        clinician_note=None,
        notification_message="Доступна запись",
        available_slots=slots,
    )

    booked = repository.book(saved.analysis_id, slot=slots[0])
    reopened = AnalysisRepository(database_path)
    reopened.initialize()
    loaded = reopened.get_care_journey(saved.analysis_id, available_slots=slots)

    assert booked is not None
    assert booked.booked_slot == slots[0]
    assert loaded == booked
    assert reopened.get(saved.analysis_id).workflow_status is WorkflowStatus.APPOINTMENT_BOOKED


def test_demo_reset_clears_analyses_and_care_journeys(tmp_path) -> None:
    repository = AnalysisRepository(tmp_path / "history.sqlite3")
    repository.initialize()
    saved = _save(repository, "ct-lung-nodule")
    repository.save_review(
        analysis_id=saved.analysis_id,
        review_choice=ReviewChoice.RECOMMENDED_SPECIALIST,
        appointment_target=saved.routing_decision.action,
        specialty=saved.routing_decision.specialty,
        clinician_note=None,
        notification_message="Доступна запись",
        available_slots=available_booking_slots(),
    )

    deleted_analyses, deleted_journeys = repository.clear_demo_data()

    assert deleted_analyses == 1
    assert deleted_journeys == 1
    assert repository.list() == []
    assert repository.get(saved.analysis_id) is None
    assert repository.get_care_journey(saved.analysis_id, available_slots=[]) is None
