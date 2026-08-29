"""Tests for agent skill 2. The LLM boundary (_structured_llm) is
monkeypatched, so this suite runs fast and needs no API key, only the
signal-gathering logic and the prompt wiring are under test here.
"""

import app.database as db
import app.skills.skill2_min_party_override as skill2

DATE = "2026-09-01"


def _seeded(conn):
    restaurant_id = conn.execute("SELECT id FROM restaurant LIMIT 1").fetchone()["id"]
    tables = conn.execute("SELECT id, min_party_size FROM dining_table ORDER BY id").fetchall()
    return restaurant_id, tables


class _FakeStructuredLLM:
    def __init__(self, response):
        self.response = response
        self.received_prompt = None

    def invoke(self, prompt):
        self.received_prompt = prompt
        return self.response


def test_evaluate_override_returns_llm_decision(test_db, monkeypatch):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, tables = _seeded(conn)
    # Table 4 seeded with min_party_size=4
    target = next(t for t in tables if t["min_party_size"] == 4)

    canned = skill2.MinPartySizeOverrideDecision(
        recommend_seating=True,
        reasoning="Occupancy and pending demand are both 0%, and the table has no bookings yet today.",
    )
    fake_llm = _FakeStructuredLLM(response=canned)
    monkeypatch.setattr(skill2, "_structured_llm", fake_llm)

    result = skill2.evaluate_override(
        conn,
        restaurant_id=restaurant_id,
        table_id=target["id"],
        date=DATE,
        hour=19,
        minute=0,
        duration_minutes=60,
        person_count=2,
    )
    conn.close()

    assert result == canned
    assert fake_llm.received_prompt is not None


def test_prompt_includes_real_signals_not_placeholders(test_db, monkeypatch):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, tables = _seeded(conn)
    target = next(t for t in tables if t["min_party_size"] == 4)

    fake_llm = _FakeStructuredLLM(
        response=skill2.MinPartySizeOverrideDecision(recommend_seating=False, reasoning="n/a")
    )
    monkeypatch.setattr(skill2, "_structured_llm", fake_llm)

    skill2.evaluate_override(
        conn,
        restaurant_id=restaurant_id,
        table_id=target["id"],
        date=DATE,
        hour=19,
        minute=0,
        duration_minutes=60,
        person_count=2,
    )
    conn.close()

    prompt = fake_llm.received_prompt
    # With nothing booked, occupancy and pending demand should read 0%.
    assert "0% of tables already confirmed" in prompt
    assert "This specific table's bookings today so far: 0" in prompt
    # 19:00 falls inside the seeded peak window (19-21).
    assert "Is this normally a peak hour" in prompt and "True" in prompt


def test_prompt_reflects_higher_occupancy(test_db, monkeypatch):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, tables = _seeded(conn)
    target = next(t for t in tables if t["min_party_size"] == 4)
    other_table_id = next(t["id"] for t in tables if t["id"] != target["id"])
    user_id = conn.execute("SELECT id FROM user LIMIT 1").fetchone()["id"]

    with db.transaction(conn):
        conn.execute(
            """
            INSERT INTO reservation
                (status, restaurant_id, table_id, user_id, person_count, price, idempotency_key, expiry_time)
            VALUES ('CONFIRMED', ?, ?, ?, 2, 0, 'occ-key', NULL)
            """,
            (restaurant_id, other_table_id, user_id),
        )
        reservation_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for slot_index in (76, 77, 78, 79):
            conn.execute(
                "INSERT INTO slot_claim (reservation_id, table_id, date, slot_index) VALUES (?, ?, ?, ?)",
                (reservation_id, other_table_id, DATE, slot_index),
            )

    fake_llm = _FakeStructuredLLM(
        response=skill2.MinPartySizeOverrideDecision(recommend_seating=False, reasoning="n/a")
    )
    monkeypatch.setattr(skill2, "_structured_llm", fake_llm)

    skill2.evaluate_override(
        conn,
        restaurant_id=restaurant_id,
        table_id=target["id"],
        date=DATE,
        hour=19,
        minute=0,
        duration_minutes=60,
        person_count=2,
    )
    conn.close()

    # 1 of 5 bookable tables confirmed at this time = 20%.
    assert "20% of tables already confirmed" in fake_llm.received_prompt
