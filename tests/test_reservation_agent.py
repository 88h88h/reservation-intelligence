"""Tests for the Reservation Operations Agent's routing logic. The
tool-selection LLM call is mocked (agent decides WHICH tool to call),
while the actual tool execution runs for real wherever the scenario
lets the underlying skill avoid its own LLM call, so the routing
mechanism itself, matching a tool by name and invoking it, is
genuinely exercised.
"""

import app.database as db
import app.reservation_agent as reservation_agent
import app.skills.skill2_min_party_override as skill2

DATE = "2026-09-01"


def _seeded(conn):
    restaurant_id = conn.execute("SELECT id FROM restaurant LIMIT 1").fetchone()["id"]
    tables = conn.execute("SELECT id, min_party_size FROM dining_table ORDER BY id").fetchall()
    user_id = conn.execute("SELECT id FROM user LIMIT 1").fetchone()["id"]
    return restaurant_id, tables, user_id


def _claim_wide_block(conn, restaurant_id, table_id, user_id, key, start_slot, end_slot):
    with db.transaction(conn):
        conn.execute(
            """
            INSERT INTO reservation
                (status, restaurant_id, table_id, user_id, person_count, price, idempotency_key, expiry_time)
            VALUES ('CONFIRMED', ?, ?, ?, 2, 0, ?, NULL)
            """,
            (restaurant_id, table_id, user_id, key),
        )
        reservation_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for slot_index in range(start_slot, end_slot + 1):
            conn.execute(
                "INSERT INTO slot_claim (reservation_id, table_id, date, slot_index) VALUES (?, ?, ?, ?)",
                (reservation_id, table_id, DATE, slot_index),
            )


class _FakeToolCallResponse:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


class _FakeLLMWithTools:
    def __init__(self, response):
        self.response = response

    def invoke(self, prompt):
        return self.response


class _FakeLLM:
    def __init__(self, response):
        self.response = response

    def bind_tools(self, tools):
        return _FakeLLMWithTools(self.response)


def test_no_tool_call_returns_unhandled(test_db, monkeypatch):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, tables, _ = _seeded(conn)

    monkeypatch.setattr(reservation_agent, "_llm", _FakeLLM(_FakeToolCallResponse(tool_calls=[])))

    result = reservation_agent.handle_situation(
        conn,
        situation="What's the weather like today?",
        restaurant_id=restaurant_id,
        table_id=tables[0]["id"],
        date=DATE,
        hour=19,
        minute=0,
        duration_minutes=60,
        person_count=2,
    )
    conn.close()

    assert result["handled"] is False
    assert result["tool_used"] is None


def test_routes_to_find_alternatives_tool(test_db, monkeypatch):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, tables, user_id = _seeded(conn)
    target_table_id = tables[0]["id"]

    # No candidates at all, so suggest_alternatives resolves without
    # needing its own LLM call, letting this test exercise real
    # routing + real execution end to end.
    _claim_wide_block(conn, restaurant_id, target_table_id, user_id, "wide-block", 40, 116)
    for i, other in enumerate(tables[1:], start=1):
        _claim_wide_block(conn, restaurant_id, other["id"], user_id, f"other-{i}", 76, 79)

    monkeypatch.setattr(
        reservation_agent,
        "_llm",
        _FakeLLM(_FakeToolCallResponse(tool_calls=[{"name": "find_alternatives_tool", "args": {}}])),
    )

    result = reservation_agent.handle_situation(
        conn,
        situation="Booking failed for table 1 tonight at 7, find something else for them.",
        restaurant_id=restaurant_id,
        table_id=target_table_id,
        date=DATE,
        hour=19,
        minute=0,
        duration_minutes=60,
        person_count=2,
    )
    conn.close()

    assert result["handled"] is True
    assert result["tool_used"] == "find_alternatives_tool"
    assert result["result"]["has_recommendation"] is False


def test_routes_to_min_party_override_tool(test_db, monkeypatch):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, tables, _ = _seeded(conn)
    target = next(t for t in tables if t["min_party_size"] == 4)

    canned = skill2.MinPartySizeOverrideDecision(recommend_seating=True, reasoning="Nothing else booked yet today.")
    monkeypatch.setattr(skill2, "_structured_llm", type("F", (), {"invoke": staticmethod(lambda p: canned)})())
    monkeypatch.setattr(
        reservation_agent,
        "_llm",
        _FakeLLM(_FakeToolCallResponse(tool_calls=[{"name": "evaluate_min_party_override_tool", "args": {}}])),
    )

    result = reservation_agent.handle_situation(
        conn,
        situation="A party of 2 wants table 4, which needs 4 people minimum, is that ok?",
        restaurant_id=restaurant_id,
        table_id=target["id"],
        date=DATE,
        hour=19,
        minute=0,
        duration_minutes=60,
        person_count=2,
    )
    conn.close()

    assert result["handled"] is True
    assert result["tool_used"] == "evaluate_min_party_override_tool"
    assert result["result"]["recommend_seating"] is True
