"""Deterministic synthetic booking slots for the offline prototype."""

from datetime import datetime, time, timedelta, timezone

from app.models import BookingSlot

MOSCOW_TIMEZONE = timezone(timedelta(hours=3), name="Europe/Moscow")
SLOT_TIMES = (time(10, 0), time(14, 30), time(17, 0))


def available_booking_slots(now: datetime | None = None) -> list[BookingSlot]:
    """Return six future weekday slots without calling an external MIS."""

    current = now.astimezone(MOSCOW_TIMEZONE) if now else datetime.now(MOSCOW_TIMEZONE)
    slots: list[BookingSlot] = []
    candidate_date = current.date() + timedelta(days=1)

    while len(slots) < 6:
        if candidate_date.weekday() < 5:
            for slot_time in SLOT_TIMES:
                starts_at = datetime.combine(
                    candidate_date,
                    slot_time,
                    tzinfo=MOSCOW_TIMEZONE,
                )
                slots.append(
                    BookingSlot(
                        slot_id=f"slot-{starts_at.strftime('%Y%m%d-%H%M')}",
                        starts_at=starts_at,
                        date_label=starts_at.strftime("%d.%m.%Y"),
                        time_label=starts_at.strftime("%H:%M"),
                    )
                )
                if len(slots) == 6:
                    break
        candidate_date += timedelta(days=1)

    return slots


def get_booking_slot(slot_id: str, now: datetime | None = None) -> BookingSlot | None:
    return next(
        (slot for slot in available_booking_slots(now) if slot.slot_id == slot_id),
        None,
    )
