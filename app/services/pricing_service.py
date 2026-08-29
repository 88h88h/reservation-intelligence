"""Dynamic pricing: a table's base price, adjusted by real-time demand
for the specific date/time slots being booked. Deliberately a simple,
explainable heuristic, not a tuned model, same restraint used for the
occupancy "vibe" signal elsewhere in this project.

Two demand signals, both scoped to the requested slots, not the
restaurant's activity in general, so a booking two weeks out is priced
on demand for that slot, not tonight's crowd:
- occupancy_ratio: how many tables are already CONFIRMED for these slots.
- pending_demand_ratio: how many tables are currently HELD (someone
  else is actively trying to book the same slots right now), a leading
  indicator that shows up before it ever becomes occupancy.
"""

import sqlite3

from app.repositories import reservation_repo, table_repo

OCCUPANCY_WEIGHT = 0.5
PENDING_DEMAND_WEIGHT = 0.3
MAX_MULTIPLIER = 2.0


def calculate_price(
    conn: sqlite3.Connection, *, restaurant_id: int, table_id: int, date: str, slot_indices: list[int]
) -> float:
    table = table_repo.get_by_id(conn, table_id)
    base_price = table["base_price"]

    total_tables = table_repo.count_bookable(conn, restaurant_id)
    if total_tables == 0:
        return round(base_price, 2)

    occupied = reservation_repo.count_tables_claimed_at_slots(
        conn, restaurant_id=restaurant_id, date=date, slot_indices=slot_indices, status="CONFIRMED"
    )
    pending = reservation_repo.count_tables_claimed_at_slots(
        conn, restaurant_id=restaurant_id, date=date, slot_indices=slot_indices, status="HELD"
    )

    occupancy_ratio = occupied / total_tables
    pending_demand_ratio = pending / total_tables

    multiplier = 1 + OCCUPANCY_WEIGHT * occupancy_ratio + PENDING_DEMAND_WEIGHT * pending_demand_ratio
    multiplier = min(multiplier, MAX_MULTIPLIER)

    return round(base_price * multiplier, 2)
