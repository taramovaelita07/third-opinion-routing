"""Version 1 REST endpoints for analysis and offline demo cases."""

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import ValidationError

from app.adapters import DemoDataset
from app.models import (
    AnalysisHistoryItem,
    AnalysisResponse,
    BookingRequest,
    BookingStatus,
    CareJourneyResponse,
    ClinicianReviewRequest,
    DemoCaseDetail,
    DemoCaseSummary,
    DemoResetResponse,
    RawKafkaMessage,
    ReviewChoice,
)
from app.persistence import AnalysisRepository
from app.services import AnalysisService, available_booking_slots, get_booking_slot

router = APIRouter(prefix="/api/v1")
_dataset = DemoDataset()
_analysis_service = AnalysisService()


@router.get(
    "/demo-cases",
    response_model=list[DemoCaseSummary],
    tags=["demo"],
    summary="List bundled synthetic demo cases",
)
def list_demo_cases() -> list[DemoCaseSummary]:
    return [
        DemoCaseSummary(
            id=case.metadata.id,
            title=case.metadata.title,
            description=case.metadata.description,
            modality=case.metadata.modality,
            validation=case.metadata.expected.validation,
        )
        for case in _dataset.load()
    ]


@router.get(
    "/demo-cases/{case_id}",
    response_model=DemoCaseDetail,
    tags=["demo"],
    summary="Get one demo case and its synthetic source payload",
)
def get_demo_case(case_id: str) -> DemoCaseDetail:
    case = _get_case_or_404(case_id)
    return DemoCaseDetail(
        id=case.metadata.id,
        title=case.metadata.title,
        description=case.metadata.description,
        modality=case.metadata.modality,
        validation=case.metadata.expected.validation,
        payload=case.payload,
    )


@router.post(
    "/demo/reset",
    response_model=DemoResetResponse,
    tags=["demo"],
    summary="Clear synthetic demonstration history",
)
def reset_demo(request: Request) -> DemoResetResponse:
    deleted_analyses, deleted_journeys = _repository(request).clear_demo_data()
    return DemoResetResponse(
        deleted_analyses=deleted_analyses,
        deleted_care_journeys=deleted_journeys,
    )


@router.post(
    "/demo-cases/{case_id}/analyze",
    response_model=AnalysisResponse,
    tags=["analysis"],
    summary="Run the full pipeline for one bundled demo case",
    responses={
        404: {"description": "Unknown demo case"},
        422: {"description": "The selected case intentionally has invalid input"},
    },
)
def analyze_demo_case(case_id: str, request: Request) -> AnalysisResponse:
    case = _get_case_or_404(case_id)
    try:
        message = RawKafkaMessage.model_validate(case.payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "INVALID_DEMO_PAYLOAD",
                "message": "Демонстрационный сценарий содержит невалидный вход",
                "validation_errors": exc.errors(include_url=False),
            },
        ) from exc
    result = _analysis_service.analyze(message, source=f"demo:{case_id}")
    return _repository(request).save(message, result)


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    tags=["analysis"],
    summary="Analyze one validated BFT DICOMREPORTNOTIFY payload",
)
def analyze_payload(message: RawKafkaMessage, request: Request) -> AnalysisResponse:
    result = _analysis_service.analyze(message, source="rest-api")
    return _repository(request).save(message, result)


@router.get(
    "/analyses",
    response_model=list[AnalysisHistoryItem],
    tags=["history"],
    summary="List persisted analyses from newest to oldest",
)
def list_analyses(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[AnalysisHistoryItem]:
    return _repository(request).list(limit=limit, offset=offset)


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisResponse,
    tags=["history"],
    summary="Get one persisted analysis with source and traceability data",
    responses={404: {"description": "Analysis record not found"}},
)
def get_analysis(analysis_id: str, request: Request) -> AnalysisResponse:
    return _analysis_or_404(analysis_id, request)


@router.post(
    "/analyses/{analysis_id}/review",
    response_model=CareJourneyResponse,
    tags=["care journey"],
    summary="Confirm a clinician-reviewed next step and enable patient booking",
    responses={
        404: {"description": "Analysis record not found"},
        409: {"description": "Safety layer blocks clinician approval"},
    },
)
def review_analysis(
    analysis_id: str,
    review: ClinicianReviewRequest,
    request: Request,
) -> CareJourneyResponse:
    record = _analysis_or_404(analysis_id, request)
    if not record.safety_result.route_usable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "REVIEW_BLOCKED_BY_SAFETY",
                "message": "Нельзя подтвердить маршрут до устранения замечаний Safety Layer",
            },
        )

    repository = _repository(request)
    existing_journey = repository.get_care_journey(
        analysis_id,
        available_slots=available_booking_slots(),
    )
    if (
        existing_journey is not None
        and existing_journey.booking_status is BookingStatus.BOOKED
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "APPOINTMENT_ALREADY_BOOKED",
                "message": "Нельзя изменить решение после подтверждения записи пациента",
            },
        )

    if review.choice is ReviewChoice.RECOMMENDED_SPECIALIST:
        appointment_target = record.routing_decision.action
        specialty = record.routing_decision.specialty
    else:
        appointment_target = "Повторная консультация по результатам исследования"
        specialty = "Лечащий / направивший врач"

    notification_message = (
        "Врач проверил результат исследования. Вам доступна запись: "
        f"{specialty}. Выберите удобное время."
    )
    note = review.note.strip() if review.note and review.note.strip() else None
    return repository.save_review(
        analysis_id=analysis_id,
        review_choice=review.choice,
        appointment_target=appointment_target,
        specialty=specialty,
        clinician_note=note,
        notification_message=notification_message,
        available_slots=available_booking_slots(),
    )


@router.get(
    "/analyses/{analysis_id}/care-journey",
    response_model=CareJourneyResponse,
    tags=["care journey"],
    summary="Get the clinician-approved patient booking state",
    responses={
        404: {"description": "Analysis or reviewed care journey not found"},
    },
)
def get_care_journey(analysis_id: str, request: Request) -> CareJourneyResponse:
    _analysis_or_404(analysis_id, request)
    journey = _repository(request).get_care_journey(
        analysis_id,
        available_slots=available_booking_slots(),
    )
    if journey is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CARE_JOURNEY_NOT_READY",
                "message": "Решение врача по этому анализу ещё не сохранено",
            },
        )
    return journey


@router.post(
    "/analyses/{analysis_id}/book",
    response_model=CareJourneyResponse,
    tags=["care journey"],
    summary="Book one synthetic appointment slot",
    responses={
        404: {"description": "Analysis record not found"},
        409: {"description": "Clinician review required or slot already booked"},
        422: {"description": "Unknown synthetic slot"},
    },
)
def book_appointment(
    analysis_id: str,
    booking: BookingRequest,
    request: Request,
) -> CareJourneyResponse:
    _analysis_or_404(analysis_id, request)
    repository = _repository(request)
    journey = repository.get_care_journey(
        analysis_id,
        available_slots=available_booking_slots(),
    )
    if journey is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CLINICIAN_REVIEW_REQUIRED",
                "message": "Сначала врач должен подтвердить следующий шаг",
            },
        )
    if journey.booking_status is BookingStatus.BOOKED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "APPOINTMENT_ALREADY_BOOKED",
                "message": "Запись по этому исследованию уже подтверждена",
            },
        )

    slot = get_booking_slot(booking.slot_id)
    if slot is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "BOOKING_SLOT_NOT_FOUND",
                "message": "Выбранное время недоступно в демонстрационном расписании",
            },
        )
    booked = repository.book(analysis_id, slot=slot)
    if booked is None:  # Defensive guard for a concurrent local reset.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CLINICIAN_REVIEW_REQUIRED",
                "message": "Сначала врач должен подтвердить следующий шаг",
            },
        )
    return booked


def _get_case_or_404(case_id: str):
    try:
        return _dataset.get(case_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DEMO_CASE_NOT_FOUND",
                "message": f"Демонстрационный сценарий не найден: {case_id}",
            },
        ) from exc


def _repository(request: Request) -> AnalysisRepository:
    repository = getattr(request.app.state, "analysis_repository", None)
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "PERSISTENCE_NOT_READY",
                "message": "Хранилище истории ещё не инициализировано",
            },
        )
    return repository


def _analysis_or_404(analysis_id: str, request: Request) -> AnalysisResponse:
    record = _repository(request).get(analysis_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ANALYSIS_NOT_FOUND",
                "message": f"Сохранённый анализ не найден: {analysis_id}",
            },
        )
    return record
