"""Availability browsing: which tables are actually bookable for a
given request, before anyone commits to a POST /reservations call.
"""

import sqlite3

from app.repositories import table_repo
from app.slots import compute_slot_indices


def find_available_tables(
    conn: sqlite3.Connection, *, restaurant_id: int, date: str, hour: int, minute: int, duration_minutes: int, person_count: int
) -> list[dict]:
    slot_indices = compute_slot_indices(hour, minute, duration_minutes)
    tables = table_repo.find_available(
        conn, restaurant_id=restaurant_id, date=date, slot_indices=slot_indices, person_count=person_count
    )
    results = []
    for table in tables:
        row = dict(table)
        row["meets_min_party_size"] = person_count >= table["min_party_size"]
        results.append(row)
    return results
