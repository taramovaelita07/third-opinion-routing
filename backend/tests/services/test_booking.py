"""Tests for deterministic synthetic appointment slots."""

from datetime import datetime, timedelta, timezone

from app.services import available_booking_slots, get_booking_slot


def test_booking_slots_are_future_weekdays_and_deterministic() -> None:
    now = datetime(2026, 10, 2, 18, 0, tzinfo=timezone(timedelta(hours=3)))

    slots = available_booking_slots(now)

    assert len(slots) == 6
    assert slots[0].date_label == "05.10.2026"
    assert slots[0].time_label == "10:00"
    assert all(slot.starts_at.weekday() < 5 for slot in slots)


def test_booking_slot_ids_are_unique() -> None:
    slots = available_booking_slots()

    assert len({slot.slot_id for slot in slots}) == len(slots)


def test_known_slot_can_be_resolved() -> None:
    now = datetime(2026, 10, 2, 18, 0, tzinfo=timezone(timedelta(hours=3)))
    expected = available_booking_slots(now)[2]

    assert get_booking_slot(expected.slot_id, now) == expected
    assert get_booking_slot("missing-slot", now) is None
