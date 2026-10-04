"""Smoke tests for the integrated offline clinician interface."""

import asyncio

from httpx import ASGITransport, AsyncClient

from app.main import app


def _get(path: str):
    async def request():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    return asyncio.run(request())


def test_app_alias_serves_same_interface() -> None:
    response = _get("/app")

    assert response.status_code == 200
    assert '<section class="view active" id="dashboard-view">' in response.text


def test_stylesheet_is_served_locally() -> None:
    response = _get("/static/styles.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "--purple" in response.text


def test_javascript_connects_to_real_api_endpoints() -> None:
    response = _get("/static/app.js")

    assert response.status_code == 200
    assert "/api/v1/demo-cases" in response.text
    assert "/api/v1/analyses" in response.text
    assert "analyzeSelectedCase" in response.text


def test_frontend_has_no_external_runtime_dependencies() -> None:
    response = _get("/")

    assert "https://" not in response.text
    assert "http://" not in response.text
    assert '/static/styles.css?v=1.4.0' in response.text
    assert '/static/app.js?v=1.4.0' in response.text


def test_api_info_points_to_interface_and_docs() -> None:
    response = _get("/api-info")

    assert response.status_code == 200
    assert response.json()["interface"] == "/"
    assert response.json()["documentation"] == "/docs"
    assert response.json()["version"] == "1.4.0"


def test_frontend_has_traceability_workspace() -> None:
    response = _get("/")

    assert 'id="traceability-panel"' in response.text
    assert 'id="trace-flow"' in response.text
    assert "Почему система предложила этот маршрут" in response.text


def test_frontend_preserves_expandable_source_text() -> None:
    response = _get("/")

    assert '<details class="source-details" id="source-details">' in response.text
    assert "Исходный текст результата ИИ" in response.text
    assert "Связан с маршрутом" in response.text


def test_javascript_renders_routing_trace_and_evidence() -> None:
    response = _get("/static/app.js")

    assert "renderTraceability(study, route, safety)" in response.text
    assert "route.trace" in response.text
    assert "finding.evidence" in response.text


def test_javascript_opens_original_source_from_trace() -> None:
    response = _get("/static/app.js")

    assert "openSourceDetails" in response.text
    assert 'details.open = true' in response.text


def test_frontend_has_clinician_review_choices() -> None:
    response = _get("/")

    assert 'id="care-journey-panel"' in response.text
    assert 'value="RECOMMENDED_SPECIALIST"' in response.text
    assert 'value="REPEAT_CONSULTATION"' in response.text


def test_frontend_hands_route_to_patient_without_doctor_booking() -> None:
    response = _get("/")

    assert 'id="handoff-confirmation"' in response.text
    assert "Дату и время выбирает пациент" in response.text
    assert 'id="booking-slots"' not in response.text
    assert 'id="confirm-booking-button"' not in response.text


def test_doctor_javascript_connects_review_but_not_booking_endpoint() -> None:
    response = _get("/static/app.js")

    assert "/review`" in response.text
    assert "/care-journey`" in response.text
    assert "/book`" not in response.text


def test_javascript_stops_doctor_flow_after_route_confirmation() -> None:
    response = _get("/static/app.js")

    assert "submitClinicianReview" in response.text
    assert "submitBooking" not in response.text
    assert "Маршрутизация подтверждена — пациент уведомлён" in response.text
    assert "REVIEW_BLOCKED_BY_SAFETY" not in response.text


def test_javascript_explains_server_connection_failures_in_russian() -> None:
    response = _get("/static/app.js")

    assert "Нет связи с локальным сервером" in response.text
    assert 'error.code = "NETWORK_ERROR"' in response.text


def test_frontend_has_reference_dashboard_sections() -> None:
    response = _get("/")

    assert "Последние поступления" in response.text
    assert 'id="recent-list"' in response.text
    assert 'data-modality="CT_CHEST"' in response.text
    assert 'data-modality="MAMMOGRAPHY"' in response.text


def test_patient_cabinet_has_three_reference_views() -> None:
    response = _get("/patient")

    assert response.status_code == 200
    assert 'id="patient-home-view"' in response.text
    assert 'id="patient-card-view"' in response.text
    assert 'id="patient-profile-view"' in response.text
    assert "Иванова Мария Игоревна" in response.text
    assert "Ближайшие записи" in response.text


def test_patient_cabinet_uses_local_assets_only() -> None:
    response = _get("/patient")

    assert "https://" not in response.text
    assert "http://" not in response.text
    assert '/static/patient.css?v=1.4.0' in response.text
    assert '/static/patient.js?v=1.4.0' in response.text


def test_patient_cabinet_uses_anonymized_hologram_asset() -> None:
    page = _get("/patient")
    asset = _get("/static/assets/patient-body-hologram.png")

    assert 'src="/static/assets/patient-body-hologram.png?v=1.0.1"' in page.text
    assert "<svg class=\"body-hologram\"" not in page.text
    assert asset.status_code == 200
    assert asset.headers["content-type"] == "image/png"


def test_patient_javascript_owns_the_booking_action() -> None:
    response = _get("/static/patient.js")

    assert response.status_code == 200
    assert "/care-journey`" in response.text
    assert "/book`" in response.text
    assert "submitPatientBooking" in response.text
    assert 'body: JSON.stringify({ slot_id: selectedSlot.value })' in response.text


def test_doctor_interface_links_to_patient_without_booking_for_them() -> None:
    response = _get("/")

    assert 'href="/patient"' in response.text
    assert "Открыть кабинет пациента" in response.text
    assert 'id="patient-confirm-booking"' not in response.text


def test_jury_can_switch_between_both_cabinets() -> None:
    doctor = _get("/")
    patient = _get("/patient")

    assert 'class="cabinet-jury-switch" href="/patient"' in doctor.text
    assert 'class="patient-jury-switch" href="/"' in patient.text
    assert "Для демонстрации" in doctor.text
    assert "Для демонстрации" in patient.text


def test_doctor_can_reset_the_synthetic_demo() -> None:
    page = _get("/")
    script = _get("/static/app.js")

    assert 'id="reset-demo-button"' in page.text
    assert 'id="reset-demo-dialog"' in page.text
    assert "Сбросить демо" in page.text
    assert 'apiRequest("/api/v1/demo/reset", { method: "POST" })' in script.text
    assert "showModal()" in script.text
    assert "window.confirm" not in script.text


def test_both_cabinets_refresh_after_jury_switching() -> None:
    doctor_script = _get("/static/app.js")
    patient_script = _get("/static/patient.js")

    assert 'document.addEventListener("visibilitychange", refreshDoctorState)' in doctor_script.text
    assert 'window.addEventListener("pageshow", refreshDoctorState)' in doctor_script.text
    assert 'document.addEventListener("visibilitychange", refreshPatientState)' in patient_script.text
    assert 'window.addEventListener("pageshow", refreshPatientState)' in patient_script.text


def test_frontends_expose_keyboard_focus_and_loading_state() -> None:
    doctor_css = _get("/static/styles.css")
    patient_css = _get("/static/patient.css")
    doctor_script = _get("/static/app.js")
    patient_script = _get("/static/patient.js")

    assert ":focus-visible" in doctor_css.text
    assert ":focus-visible" in patient_css.text
    assert 'setAttribute("aria-busy"' in doctor_script.text
    assert 'setAttribute("aria-busy"' in patient_script.text
