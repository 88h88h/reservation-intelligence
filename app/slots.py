"""Slot-grid math: converting a requested start time and duration into
the sequence of 15-minute slot_index values a reservation needs to
claim. Pure functions, no database access, so the grid logic can be
tested completely on its own.
"""

SLOT_MINUTES = 15


def time_to_slot_index(hour: int, minute: int) -> int:
    if not (0 <= hour < 24) or not (0 <= minute < 60):
        raise ValueError(f"invalid time: {hour:02d}:{minute:02d}")
    if minute % SLOT_MINUTES != 0:
        raise ValueError(f"start time must fall on a {SLOT_MINUTES}-minute boundary, got :{minute:02d}")
    return (hour * 60 + minute) // SLOT_MINUTES


def compute_slot_indices(hour: int, minute: int, duration_minutes: int) -> list[int]:
    if duration_minutes <= 0 or duration_minutes % SLOT_MINUTES != 0:
        raise ValueError(f"duration must be a positive multiple of {SLOT_MINUTES} minutes, got {duration_minutes}")
    start = time_to_slot_index(hour, minute)
    num_slots = duration_minutes // SLOT_MINUTES
    return list(range(start, start + num_slots))
