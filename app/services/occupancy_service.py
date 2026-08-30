"""Real-time occupancy: how full a restaurant is right now, at the
current moment, not scoped to any specific future booking's slots
(that's pricing_service's concern). This is the "vibe" signal from
feature #2, driving occupancy-gated offers, pricing's demand signal,
and both dashboards' live occupancy display.
"""

import sqlite3
from datetime import datetime, timezone

from app.repositories import reservation_repo, table_repo
from app.slots import time_to_slot_index


def _current_occupied_and_total(conn: sqlite3.Connection, restaurant_id: int) -> tuple[int, int]:
    total_tables = table_repo.count_bookable(conn, restaurant_id)
    if total_tables == 0:
        return 0, 0

    now = datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")
    slot_index = time_to_slot_index(now.hour, now.minute - (now.minute % 15))

    occupied = reservation_repo.count_tables_claimed_at_slots(
        conn, restaurant_id=restaurant_id, date=date, slot_indices=[slot_index], status="CONFIRMED"
    )
    return occupied, total_tables


def current_occupancy_ratio(conn: sqlite3.Connection, restaurant_id: int) -> float:
    occupied, total = _current_occupied_and_total(conn, restaurant_id)
    return occupied / total if total else 0.0


def current_occupancy_detail(conn: sqlite3.Connection, restaurant_id: int) -> dict:
    """Richer than current_occupancy_ratio: the actual occupied/total
    counts too, so a UI can render a real visual indicator (a fill bar,
    a dot grid) instead of just a percentage in text.
    """
    occupied, total = _current_occupied_and_total(conn, restaurant_id)
    ratio = occupied / total if total else 0.0
    return {"occupied_tables": occupied, "total_tables": total, "occupancy_ratio": ratio, "vibe_label": vibe_label(ratio)}


def vibe_label(occupancy_ratio: float) -> str:
    """Translate the raw occupancy ratio into the diner-facing "vibe"
    feature #2 was actually designed to deliver, a plain computed
    heuristic, not sensing infrastructure and not an LLM call, same
    restraint decided on when this feature was first scoped.
    """
    if occupancy_ratio <= 0.2:
        return "Quiet"
    if occupancy_ratio <= 0.5:
        return "Comfortably busy"
    if occupancy_ratio <= 0.8:
        return "Lively"
    return "Buzzing"
