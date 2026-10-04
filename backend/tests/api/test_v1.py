"""Integration tests for the public version 1 REST API."""

import asyncio
import sqlite3

from httpx import ASGITransport, AsyncClient

from app.adapters import DemoDataset
from app.main import app


def _request(method: str, url: str, **kwargs):
    async def run_request():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, url, **kwargs)

    return asyncio.run(run_request())


def test_swagger_and_openapi_are_available() -> None:
    docs = _request("GET", "/docs")
    schema = _request("GET", "/openapi.json")

    assert docs.status_code == 200
    assert "Swagger UI" in docs.text
    assert schema.status_code == 200
    assert schema.json()["info"]["version"] == "1.4.0"


def test_demo_case_list_contains_all_ten_scenarios() -> None:
    response = _request("GET", "/api/v1/demo-cases")

    assert response.status_code == 200
    cases = response.json()
    assert len(cases) == 10
    assert {case["id"] for case in cases} >= {
        "ct-normal",
        "ct-pneumothorax",
        "mmg-birads-4",
        "conclusion-conflict",
    }


def test_all_demo_scenarios_keep_their_expected_api_outcome() -> None:
    for case in DemoDataset().load():
        response = _request("POST", f"/api/v1/demo-cases/{case.metadata.id}/analyze")
        expected_status = 200 if case.metadata.expected.validation == "valid" else 422

        assert response.status_code == expected_status, case.metadata.id


def test_demo_case_detail_includes_original_payload() -> None:
    response = _request("GET", "/api/v1/demo-cases/mmg-birads-4")

    assert response.status_code == 200
    body = response.json()
    assert body["modality"] == "MAMMOGRAPHY"
    assert body["payload"]["studyIUID"] == "1.2.643.demo.mmg.birads4.001"


def test_demo_reset_clears_only_persisted_demo_workflow() -> None:
    created = _request("POST", "/api/v1/demo-cases/ct-lung-nodule/analyze")
    analysis_id = created.json()["analysis_id"]
    reviewed = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/review",
        json={"choice": "RECOMMENDED_SPECIALIST"},
    )
    assert reviewed.status_code == 200

    reset = _request("POST", "/api/v1/demo/reset")

    assert reset.status_code == 200
    assert reset.json() == {
        "status": "reset",
        "deleted_analyses": 1,
        "deleted_care_journeys": 1,
    }
    assert _request("GET", "/api/v1/analyses").json() == []
    assert _request("GET", f"/api/v1/analyses/{analysis_id}").status_code == 404


def test_unknown_demo_case_returns_structured_404() -> None:
    response = _request("GET", "/api/v1/demo-cases/does-not-exist")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "DEMO_CASE_NOT_FOUND"


def test_demo_analysis_returns_complete_pipeline_result() -> None:
    response = _request(
        "POST",
        "/api/v1/demo-cases/ct-lung-nodule/analyze",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_id"]
    assert body["workflow_status"] == "PENDING_CLINICIAN_REVIEW"
    assert body["raw_input"]["studyIUID"] == "1.2.643.demo.ct.nodule.001"
    assert body["normalized_study"]["modality"] == "CT_CHEST"
    assert body["routing_decision"]["rule_id"] == (
        "CT_LUNG_NODULE_SPECIALIST_REVIEW"
    )
    assert body["safety_result"]["disposition"] == "CLEARED_FOR_REVIEW"


def test_red_flag_demo_is_escalated_by_api() -> None:
    response = _request(
        "POST",
        "/api/v1/demo-cases/ct-pneumothorax/analyze",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_status"] == "ESCALATED_FOR_REVIEW"
    assert body["routing_decision"]["priority"] == "URGENT"
    assert body["safety_result"]["disposition"] == "ESCALATE_TO_CLINICIAN"
    assert body["safety_result"]["patient_notification_allowed"] is False


def test_conflict_demo_is_blocked_by_api() -> None:
    response = _request(
        "POST",
        "/api/v1/demo-cases/conclusion-conflict/analyze",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_status"] == "BLOCKED_PENDING_REVIEW"
    assert body["safety_result"]["disposition"] == "BLOCKED_PENDING_REVIEW"
    assert body["safety_result"]["route_usable"] is False


def test_intentionally_invalid_demo_returns_422() -> None:
    response = _request(
        "POST",
        "/api/v1/demo-cases/missing-ai-result/analyze",
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_DEMO_PAYLOAD"


def test_raw_payload_endpoint_accepts_valid_bft_json() -> None:
    payload = DemoDataset().get("ct-normal").payload

    response = _request("POST", "/api/v1/analyze", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["normalized_study"]["source"] == "rest-api"
    assert body["routing_decision"]["priority"] == "ROUTINE"


def test_raw_payload_endpoint_rejects_missing_ai_result() -> None:
    response = _request(
        "POST",
        "/api/v1/analyze",
        json={"studyIUID": "1.2.643.demo.invalid.api"},
    )

    assert response.status_code == 422
    body = response.json()["detail"]
    assert body["code"] == "REQUEST_VALIDATION_ERROR"
    assert body["message"] == "Проверьте формат и обязательные поля запроса"
    assert body["validation_errors"]
    assert "input" not in body["validation_errors"][0]


def test_created_analysis_appears_in_history_and_can_be_retrieved() -> None:
    created = _request(
        "POST",
        "/api/v1/demo-cases/mmg-birads-4/analyze",
    )
    analysis_id = created.json()["analysis_id"]

    history = _request("GET", "/api/v1/analyses")
    detail = _request("GET", f"/api/v1/analyses/{analysis_id}")

    assert history.status_code == 200
    assert history.json()[0]["analysis_id"] == analysis_id
    assert history.json()[0]["modality"] == "MAMMOGRAPHY"
    assert detail.status_code == 200
    assert detail.json() == created.json()


def test_unknown_analysis_id_returns_structured_404() -> None:
    response = _request("GET", "/api/v1/analyses/not-a-real-id")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ANALYSIS_NOT_FOUND"


def test_history_pagination_is_validated() -> None:
    response = _request("GET", "/api/v1/analyses?limit=101")

    assert response.status_code == 422


def test_clinician_can_confirm_recommended_specialist() -> None:
    created = _request("POST", "/api/v1/demo-cases/ct-lung-nodule/analyze")
    analysis_id = created.json()["analysis_id"]

    response = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/review",
        json={"choice": "RECOMMENDED_SPECIALIST", "note": "Находка подтверждена"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["specialty"] == "Пульмонолог"
    assert body["booking_status"] == "READY_FOR_PATIENT"
    assert body["patient_notification_allowed"] is True
    assert len(body["available_slots"]) == 6


def test_clinician_can_choose_repeat_consultation() -> None:
    created = _request("POST", "/api/v1/demo-cases/ct-normal/analyze")
    analysis_id = created.json()["analysis_id"]

    response = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/review",
        json={"choice": "REPEAT_CONSULTATION"},
    )

    assert response.status_code == 200
    assert response.json()["specialty"] == "Лечащий / направивший врач"


def test_safety_blocked_route_cannot_be_approved() -> None:
    created = _request("POST", "/api/v1/demo-cases/conclusion-conflict/analyze")
    analysis_id = created.json()["analysis_id"]

    response = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/review",
        json={"choice": "RECOMMENDED_SPECIALIST"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REVIEW_BLOCKED_BY_SAFETY"


def test_care_journey_requires_clinician_review() -> None:
    created = _request("POST", "/api/v1/demo-cases/ct-lung-nodule/analyze")
    analysis_id = created.json()["analysis_id"]

    response = _request("GET", f"/api/v1/analyses/{analysis_id}/care-journey")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CARE_JOURNEY_NOT_READY"


def test_patient_can_book_slot_after_review() -> None:
    created = _request("POST", "/api/v1/demo-cases/mmg-birads-4/analyze")
    analysis_id = created.json()["analysis_id"]
    reviewed = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/review",
        json={"choice": "RECOMMENDED_SPECIALIST"},
    )
    slot_id = reviewed.json()["available_slots"][0]["slot_id"]

    booked = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/book",
        json={"slot_id": slot_id},
    )
    detail = _request("GET", f"/api/v1/analyses/{analysis_id}")

    assert booked.status_code == 200
    assert booked.json()["booking_status"] == "BOOKED"
    assert booked.json()["booked_slot"]["slot_id"] == slot_id
    assert booked.json()["available_slots"] == []
    assert detail.json()["workflow_status"] == "APPOINTMENT_BOOKED"


def test_booking_rejects_unknown_slot_and_missing_review() -> None:
    created = _request("POST", "/api/v1/demo-cases/ct-lung-nodule/analyze")
    analysis_id = created.json()["analysis_id"]
    before_review = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/book",
        json={"slot_id": "missing-slot"},
    )
    _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/review",
        json={"choice": "RECOMMENDED_SPECIALIST"},
    )
    unknown_slot = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/book",
        json={"slot_id": "missing-slot"},
    )

    assert before_review.status_code == 409
    assert before_review.json()["detail"]["code"] == "CLINICIAN_REVIEW_REQUIRED"
    assert unknown_slot.status_code == 422
    assert unknown_slot.json()["detail"]["code"] == "BOOKING_SLOT_NOT_FOUND"


def test_confirmed_booking_cannot_be_repeated_or_overwritten() -> None:
    created = _request("POST", "/api/v1/demo-cases/ct-lung-nodule/analyze")
    analysis_id = created.json()["analysis_id"]
    reviewed = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/review",
        json={"choice": "RECOMMENDED_SPECIALIST"},
    )
    slot_id = reviewed.json()["available_slots"][0]["slot_id"]
    first_booking = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/book",
        json={"slot_id": slot_id},
    )

    repeated_booking = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/book",
        json={"slot_id": slot_id},
    )
    repeated_review = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/review",
        json={"choice": "REPEAT_CONSULTATION"},
    )
    journey = _request("GET", f"/api/v1/analyses/{analysis_id}/care-journey")

    assert first_booking.status_code == 200
    assert repeated_booking.status_code == 409
    assert repeated_booking.json()["detail"]["code"] == "APPOINTMENT_ALREADY_BOOKED"
    assert repeated_review.status_code == 409
    assert repeated_review.json()["detail"]["code"] == "APPOINTMENT_ALREADY_BOOKED"
    assert journey.json()["review_choice"] == "RECOMMENDED_SPECIALIST"
    assert journey.json()["booked_slot"]["slot_id"] == slot_id


def test_complete_repeat_consultation_journey_updates_history() -> None:
    created = _request("POST", "/api/v1/demo-cases/ct-normal/analyze")
    analysis_id = created.json()["analysis_id"]

    reviewed = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/review",
        json={"choice": "REPEAT_CONSULTATION", "note": "Контроль результатов"},
    )
    history_after_review = _request("GET", "/api/v1/analyses")
    slot_id = reviewed.json()["available_slots"][-1]["slot_id"]
    booked = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/book",
        json={"slot_id": slot_id},
    )
    history_after_booking = _request("GET", "/api/v1/analyses")

    reviewed_row = next(
        item for item in history_after_review.json() if item["analysis_id"] == analysis_id
    )
    booked_row = next(
        item for item in history_after_booking.json() if item["analysis_id"] == analysis_id
    )
    assert reviewed.json()["specialty"] == "Лечащий / направивший врач"
    assert reviewed_row["workflow_status"] == "PATIENT_ACTION_AVAILABLE"
    assert booked.status_code == 200
    assert booked.json()["booking_status"] == "BOOKED"
    assert booked_row["workflow_status"] == "APPOINTMENT_BOOKED"


def test_care_journey_endpoints_reject_unknown_analysis() -> None:
    review = _request(
        "POST",
        "/api/v1/analyses/missing/review",
        json={"choice": "RECOMMENDED_SPECIALIST"},
    )
    journey = _request("GET", "/api/v1/analyses/missing/care-journey")
    booking = _request(
        "POST",
        "/api/v1/analyses/missing/book",
        json={"slot_id": "slot-20261005-1000"},
    )

    assert review.status_code == 404
    assert journey.status_code == 404
    assert booking.status_code == 404
    assert review.json()["detail"]["code"] == "ANALYSIS_NOT_FOUND"
    assert journey.json()["detail"]["code"] == "ANALYSIS_NOT_FOUND"
    assert booking.json()["detail"]["code"] == "ANALYSIS_NOT_FOUND"


def test_review_contract_rejects_unknown_fields_and_long_note() -> None:
    created = _request("POST", "/api/v1/demo-cases/ct-normal/analyze")
    analysis_id = created.json()["analysis_id"]

    extra_field = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/review",
        json={"choice": "REPEAT_CONSULTATION", "unexpected": True},
    )
    long_note = _request(
        "POST",
        f"/api/v1/analyses/{analysis_id}/review",
        json={"choice": "REPEAT_CONSULTATION", "note": "x" * 501},
    )

    assert extra_field.status_code == 422
    assert extra_field.json()["detail"]["code"] == "REQUEST_VALIDATION_ERROR"
    assert long_note.status_code == 422
    assert long_note.json()["detail"]["code"] == "REQUEST_VALIDATION_ERROR"


def test_corrupted_stored_record_returns_safe_error(isolated_api_repository) -> None:
    created = _request("POST", "/api/v1/demo-cases/ct-normal/analyze")
    analysis_id = created.json()["analysis_id"]
    with sqlite3.connect(isolated_api_repository.database_path) as connection:
        connection.execute(
            "UPDATE analysis_records SET normalized_study_json = ? WHERE analysis_id = ?",
            ("not-json", analysis_id),
        )

    response = _request("GET", f"/api/v1/analyses/{analysis_id}")

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "STORED_DATA_INVALID",
            "message": "Сохранённые данные повреждены и не могут быть открыты",
        }
    }
