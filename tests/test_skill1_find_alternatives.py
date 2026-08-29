"""Tests for agent skill 1. The LLM boundary (_structured_llm) is
monkeypatched, so this suite runs fast, deterministic, and without a
real API key, only the candidate-gathering logic and the wiring around
the LLM call are under test here, not the model's actual judgment.
"""

import app.database as db
import app.skills.skill1_find_alternatives as skill1

DATE = "2026-09-01"


def _seeded(conn):
    restaurant_id = conn.execute("SELECT id FROM restaurant LIMIT 1").fetchone()["id"]
    tables = conn.execute("SELECT id FROM dining_table ORDER BY id").fetchall()
    user_id = conn.execute("SELECT id FROM user LIMIT 1").fetchone()["id"]
    return restaurant_id, [t["id"] for t in tables], user_id


def _claim_wide_block(conn, restaurant_id, table_id, user_id, key, start_slot, end_slot):
    """Claim a broad, contiguous range of slots for one table, wide
    enough to cover both the exact target time and the +-90 minute
    nearby-time scan window, so no candidate survives for that table.
    """
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


class _FakeStructuredLLM:
    def __init__(self, response):
        self.response = response
        self.received_prompt = None

    def invoke(self, prompt):
        self.received_prompt = prompt
        return self.response


def test_no_candidates_skips_llm_call_entirely(test_db, monkeypatch):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_ids, user_id = _seeded(conn)
    target_table_id = table_ids[0]

    # 19:00-20:00 is slots 76-79. Cover a wide surrounding block on the
    # target table, and the exact target slots on every other table.
    _claim_wide_block(conn, restaurant_id, target_table_id, user_id, "wide-block", 40, 116)  # covers +-90min window
    for i, other_id in enumerate(table_ids[1:], start=1):
        _claim_wide_block(conn, restaurant_id, other_id, user_id, f"other-{i}", 76, 79)

    fake_llm = _FakeStructuredLLM(response=None)
    monkeypatch.setattr(skill1, "_structured_llm", fake_llm)

    result = skill1.suggest_alternatives(
        conn,
        restaurant_id=restaurant_id,
        table_id=target_table_id,
        date=DATE,
        hour=19,
        minute=0,
        duration_minutes=60,
        person_count=2,
    )
    conn.close()

    assert result.has_recommendation is False
    assert fake_llm.received_prompt is None  # never called


def test_returns_llm_response_when_candidates_exist(test_db, monkeypatch):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_ids, _ = _seeded(conn)
    target_table_id = table_ids[0]

    canned = skill1.AlternativeSuggestion(
        has_recommendation=True,
        table_id=table_ids[1],
        date=DATE,
        hour=19,
        minute=0,
        duration_minutes=60,
        reasoning="Table 2 is free at the same time and close in capacity.",
    )
    fake_llm = _FakeStructuredLLM(response=canned)
    monkeypatch.setattr(skill1, "_structured_llm", fake_llm)

    result = skill1.suggest_alternatives(
        conn,
        restaurant_id=restaurant_id,
        table_id=target_table_id,
        date=DATE,
        hour=19,
        minute=0,
        duration_minutes=60,
        person_count=2,
    )
    conn.close()

    assert result == canned
    assert fake_llm.received_prompt is not None
    assert f"table_id={target_table_id}" in fake_llm.received_prompt


def test_prompt_includes_original_table_type(test_db, monkeypatch):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_ids, _ = _seeded(conn)
    target_table_id = table_ids[0]  # seeded as type "window"

    fake_llm = _FakeStructuredLLM(
        response=skill1.AlternativeSuggestion(has_recommendation=False, reasoning="none")
    )
    monkeypatch.setattr(skill1, "_structured_llm", fake_llm)

    skill1.suggest_alternatives(
        conn,
        restaurant_id=restaurant_id,
        table_id=target_table_id,
        date=DATE,
        hour=19,
        minute=0,
        duration_minutes=60,
        person_count=2,
    )
    conn.close()

    assert "type=window" in fake_llm.received_prompt
