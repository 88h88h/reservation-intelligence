"""The Reservation Operations Agent: one lightweight entry point that
routes a staff-described situation to the right underlying skill.

Uses the LLM's native tool-calling directly (bind_tools), not a full
agent framework, per the assignment's own scoping: "a lightweight
function-calling or tool-routing implementation is enough; a complex
agent framework is not required."

Autonomy boundary, three layers:
1. The agent decides WHICH tool applies, on its own. Safe to do
   autonomously, it's a read-only routing decision, nothing is booked
   or changed by choosing a tool.
2. The chosen tool (skill1 or skill2) produces a SUGGESTION, never an
   action, consistent with how each skill was already designed.
3. Staff still make the actual call, booking, confirming, whatever
   the suggestion was about, through the normal API. This module never
   mutates anything.
"""

import sqlite3

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

from app.skills.skill1_find_alternatives import suggest_alternatives
from app.skills.skill2_min_party_override import evaluate_override
from app.skills.skill3_recommend_offer import recommend_offer

load_dotenv()

_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite")


def handle_situation(
    conn: sqlite3.Connection,
    *,
    situation: str,
    restaurant_id: int,
    table_id: int | None = None,
    date: str | None = None,
    hour: int | None = None,
    minute: int | None = None,
    duration_minutes: int | None = None,
    person_count: int | None = None,
) -> dict:
    booking_context = dict(
        restaurant_id=restaurant_id,
        table_id=table_id,
        date=date,
        hour=hour,
        minute=minute,
        duration_minutes=duration_minutes,
        person_count=person_count,
    )

    @tool
    def find_alternatives_tool() -> dict:
        """Use when a booking request FAILED, the requested table or time
        is no longer available, and staff need an alternative table or
        nearby time to offer the diner instead."""
        return suggest_alternatives(conn, **booking_context).model_dump()

    @tool
    def evaluate_min_party_override_tool() -> dict:
        """Use when a party's size is BELOW the requested table's minimum
        party size, and staff want to know whether seating them there
        anyway is a good idea given current demand."""
        return evaluate_override(conn, **booking_context).model_dump()

    @tool
    def recommend_offer_tool() -> dict:
        """Use when staff ask about running a promotional offer or
        discount right now, or want to know if current demand is low
        enough to warrant one. Only needs the restaurant, not a specific
        table or time."""
        return recommend_offer(conn, restaurant_id=restaurant_id).model_dump()

    tools = [find_alternatives_tool, evaluate_min_party_override_tool, recommend_offer_tool]
    llm_with_tools = _llm.bind_tools(tools)

    response = llm_with_tools.invoke(
        f'A staff member described this situation: "{situation}"\n\n'
        "Decide which single tool best addresses it and call it. If neither "
        "tool applies, don't call anything."
    )

    if not response.tool_calls:
        return {"handled": False, "tool_used": None, "result": None, "message": "No matching skill for this situation."}

    tool_call = response.tool_calls[0]
    chosen_tool = next(t for t in tools if t.name == tool_call["name"])
    result = chosen_tool.invoke(tool_call["args"])

    return {"handled": True, "tool_used": tool_call["name"], "result": result, "message": None}
