"""Contracts for the synthetic clinician-to-patient booking journey."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReviewChoice(StrEnum):
    RECOMMENDED_SPECIALIST = "RECOMMENDED_SPECIALIST"
    REPEAT_CONSULTATION = "REPEAT_CONSULTATION"


class BookingStatus(StrEnum):
    READY_FOR_PATIENT = "READY_FOR_PATIENT"
    BOOKED = "BOOKED"


class ClinicianReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choice: ReviewChoice
    note: str | None = Field(default=None, max_length=500)


class BookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: str = Field(min_length=1, max_length=80)


class BookingSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: str
    starts_at: datetime
    date_label: str
    time_label: str


class CareJourneyResponse(BaseModel):
    """State exposed after an explicit clinician review."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: str
    review_choice: ReviewChoice
    appointment_target: str
    specialty: str
    clinician_note: str | None = None
    patient_notification_allowed: bool = True
    notification_message: str
    reviewed_at: datetime
    booking_status: BookingStatus
    available_slots: list[BookingSlot] = Field(default_factory=list)
    booked_slot: BookingSlot | None = None
    booked_at: datetime | None = None
