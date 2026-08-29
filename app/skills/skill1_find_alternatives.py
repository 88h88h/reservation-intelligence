"""Agent skill 1: when a booking request fails, find and reason about
the best alternative, either a different table at the same time, or
the same table at a nearby time.

Suggests only. Actually creating the new reservation is a separate,
explicit action the caller (staff, or the diner confirming) takes
afterward through the normal POST /reservations endpoint, this module
never books anything itself.
"""

import sqlite3

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.repositories import table_repo
from app.services.availability_service import find_available_tables
from app.slots import SLOT_MINUTES, compute_slot_indices

load_dotenv()

_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite")


class AlternativeSuggestion(BaseModel):
    has_recommendation: bool = Field(description="Whether a good alternative was found")
    table_id: int | None = Field(default=None, description="The suggested table's id, if any")
    date: str | None = Field(default=None)
    hour: int | None = Field(default=None)
    minute: int | None = Field(default=None)
    duration_minutes: int | None = Field(default=None)
    reasoning: str = Field(description="Explanation for the recommendation, or for why nothing fits")


_structured_llm = _llm.with_structured_output(AlternativeSuggestion)

PROMPT = """A diner tried to book a table and it wasn't available:
- Restaurant: {restaurant_id}
- Requested table: table_id={table_id}, type={original_type}, capacity={original_capacity}
- Date: {date}, time: {hour:02d}:{minute:02d}, duration: {duration_minutes} minutes
- Party size: {person_count}

Other tables free at the exact same date and time:
{other_tables}

The same table, free at nearby times on the same date:
{nearby_times}

Recommend the single best alternative for this party, or say no good
alternative exists. Preferences, in order:
1. A table of the same type ({original_type}) over a different type,
   the diner chose that type on purpose (e.g. window, patio, chef's
   counter), losing it is a real downgrade even if the new table is
   otherwise fine.
2. Keeping the same time over a different time.
3. A table whose capacity is close to the party size rather than much
   larger.
Explain your reasoning in one or two sentences, and say explicitly if
the best option available still means a different table type than
requested.
"""


def _format_other_tables(tables: list[dict]) -> str:
    if not tables:
        return "(none)"
    return "\n".join(
        f"- table_id={t['id']}, name={t['name']}, capacity={t['capacity']}, type={t['type']}" for t in tables
    )


def _format_nearby_times(times: list[dict]) -> str:
    if not times:
        return "(none)"
    return "\n".join(f"- {t['hour']:02d}:{t['minute']:02d}" for t in times)


def _find_nearby_times(
    conn: sqlite3.Connection,
    *,
    table_id: int,
    date: str,
    hour: int,
    minute: int,
    duration_minutes: int,
    window_minutes: int = 90,
) -> list[dict]:
    original_start = hour * 60 + minute
    alternatives = []
    for offset in range(-window_minutes, window_minutes + 1, SLOT_MINUTES):
        if offset == 0:
            continue
        candidate_start = original_start + offset
        if candidate_start < 0 or candidate_start >= 24 * 60:
            continue
        cand_hour, cand_minute = divmod(candidate_start, 60)
        try:
            slot_indices = compute_slot_indices(cand_hour, cand_minute, duration_minutes)
        except ValueError:
            continue
        if table_repo.is_free(conn, table_id=table_id, date=date, slot_indices=slot_indices):
            alternatives.append({"hour": cand_hour, "minute": cand_minute})
    return alternatives


def suggest_alternatives(
    conn: sqlite3.Connection,
    *,
    restaurant_id: int,
    table_id: int,
    date: str,
    hour: int,
    minute: int,
    duration_minutes: int,
    person_count: int,
) -> AlternativeSuggestion:
    original_table = table_repo.get_by_id(conn, table_id)

    other_tables = [
        t
        for t in find_available_tables(
            conn,
            restaurant_id=restaurant_id,
            date=date,
            hour=hour,
            minute=minute,
            duration_minutes=duration_minutes,
            person_count=person_count,
        )
        if t["id"] != table_id
    ]
    nearby_times = _find_nearby_times(
        conn, table_id=table_id, date=date, hour=hour, minute=minute, duration_minutes=duration_minutes
    )

    if not other_tables and not nearby_times:
        # No candidates at all, nothing for the LLM to reason about,
        # skip the call rather than pay for a guaranteed "no" answer.
        return AlternativeSuggestion(
            has_recommendation=False,
            reasoning="No other tables are free at this time, and this table has no free nearby times either.",
        )

    prompt = PROMPT.format(
        restaurant_id=restaurant_id,
        table_id=table_id,
        original_type=original_table["type"] if original_table else "unknown",
        original_capacity=original_table["capacity"] if original_table else "unknown",
        date=date,
        hour=hour,
        minute=minute,
        duration_minutes=duration_minutes,
        person_count=person_count,
        other_tables=_format_other_tables(other_tables),
        nearby_times=_format_nearby_times(nearby_times),
    )
    return _structured_llm.invoke(prompt)
