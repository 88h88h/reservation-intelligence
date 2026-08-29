"""Real-time occupancy: how full a restaurant is right now, at the
current moment, not scoped to any specific future booking's slots
(that's pricing_service's concern). This is the "vibe" signal from
feature #2, driving both occupancy-gated offers here and, eventually,
the dashboard's live occupancy display.
"""

import sqlite3
from datetime import datetime, timezone

from app.repositories import reservation_repo, table_repo
from app.slots import time_to_slot_index


def current_occupancy_ratio(conn: sqlite3.Connection, restaurant_id: int) -> float:
    total_tables = table_repo.count_bookable(conn, restaurant_id)
    if total_tables == 0:
        return 0.0

    now = datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")
    slot_index = time_to_slot_index(now.hour, now.minute - (now.minute % 15))

    occupied = reservation_repo.count_tables_claimed_at_slots(
        conn, restaurant_id=restaurant_id, date=date, slot_indices=[slot_index], status="CONFIRMED"
    )
    return occupied / total_tables
