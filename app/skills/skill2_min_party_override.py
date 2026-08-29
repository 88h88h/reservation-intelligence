"""Agent skill 2: given an incoming request below a table's
minPartySize, evaluate whether accommodating it right now is a good
idea, given current demand, how idle the table has been today, and
proximity to closing/peak hours.

Suggests only. The core booking API never hard-blocks on
minPartySize (a deliberate earlier design choice), so this skill's
output is advisory: staff decide whether to actually make the booking
based on the recommendation, this module never books anything itself.
"""

import sqlite3

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.repositories import reservation_repo, restaurant_repo, table_repo
from app.slots import compute_slot_indices

load_dotenv()

_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite")


class MinPartySizeOverrideDecision(BaseModel):
    recommend_seating: bool = Field(description="Whether to recommend seating this party below the table's minimum")
    reasoning: str = Field(description="Explanation referencing the actual signals, not a generic answer")


_structured_llm = _llm.with_structured_output(MinPartySizeOverrideDecision)

PROMPT = """A party of {person_count} wants table {table_id} at {restaurant_name}, which normally
seats a minimum of {min_party_size} people (capacity {capacity}).

Signals for this request, date {date}, time {hour:02d}:{minute:02d}:
- Restaurant occupancy at this time: {occupancy_pct:.0f}% of tables already confirmed.
- Pending demand at this time: {pending_pct:.0f}% of tables currently held by other people trying
  to book (not yet confirmed).
- This specific table's bookings today so far: {table_bookings_today}.
- Minutes until closing at this start time: {minutes_until_closing}.
- Is this normally a peak hour for the restaurant ({peak_start}:00-{peak_end}:00)?: {is_peak}.

Should staff seat this smaller party at this table? Seating them uses up a table that could later
fit a full-size party if one shows up, weigh that against the cost of turning this party away or
making them wait. Low occupancy, low pending demand, an idle table today, being close to closing,
or being outside peak hours all make accommodating them more reasonable. Explain your reasoning in
one or two sentences, referencing the actual numbers above.
"""


def evaluate_override(
    conn: sqlite3.Connection,
    *,
    restaurant_id: int,
    table_id: int,
    date: str,
    hour: int,
    minute: int,
    duration_minutes: int,
    person_count: int,
) -> MinPartySizeOverrideDecision:
    restaurant = restaurant_repo.get_by_id(conn, restaurant_id)
    table = table_repo.get_by_id(conn, table_id)
    slot_indices = compute_slot_indices(hour, minute, duration_minutes)

    total_tables = table_repo.count_bookable(conn, restaurant_id)
    occupied = reservation_repo.count_tables_claimed_at_slots(
        conn, restaurant_id=restaurant_id, date=date, slot_indices=slot_indices, status="CONFIRMED"
    )
    pending = reservation_repo.count_tables_claimed_at_slots(
        conn, restaurant_id=restaurant_id, date=date, slot_indices=slot_indices, status="HELD"
    )
    occupancy_ratio = occupied / total_tables if total_tables else 0.0
    pending_ratio = pending / total_tables if total_tables else 0.0

    table_bookings_today = reservation_repo.count_reservations_for_table_on_date(conn, table_id=table_id, date=date)

    minutes_until_closing = restaurant["closing_hour"] * 60 - (hour * 60 + minute)
    is_peak = restaurant["peak_start_hour"] <= hour < restaurant["peak_end_hour"]

    prompt = PROMPT.format(
        person_count=person_count,
        table_id=table_id,
        restaurant_name=restaurant["name"],
        min_party_size=table["min_party_size"],
        capacity=table["capacity"],
        date=date,
        hour=hour,
        minute=minute,
        occupancy_pct=occupancy_ratio * 100,
        pending_pct=pending_ratio * 100,
        table_bookings_today=table_bookings_today,
        minutes_until_closing=minutes_until_closing,
        peak_start=restaurant["peak_start_hour"],
        peak_end=restaurant["peak_end_hour"],
        is_peak=is_peak,
    )
    return _structured_llm.invoke(prompt)
