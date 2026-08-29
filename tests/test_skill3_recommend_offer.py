"""Tests for agent skill 3. The LLM boundary is monkeypatched, so this
suite is fast and needs no API key. Covers the occupancy gate, the
"no menu items" gate, and the graduated autonomy boundary (auto-active
vs. pending confirmation) that skill 3 enforces in code, not the LLM.
"""

from datetime import datetime, timezone

import app.database as db
import app.skills.skill3_recommend_offer as skill3


def _seeded(conn):
    restaurant_id = conn.execute("SELECT id FROM restaurant LIMIT 1").fetchone()["id"]
    menu_items = conn.execute("SELECT id, max_auto_discount FROM menu_item ORDER BY id").fetchall()
    return restaurant_id, menu_items


class _FakeStructuredLLM:
    def __init__(self, response):
        self.response = response

    def invoke(self, prompt):
        return self.response


def _current_slot():
    now = datetime.now(timezone.utc)
    from app.slots import time_to_slot_index

    return now.strftime("%Y-%m-%d"), time_to_slot_index(now.hour, now.minute - (now.minute % 15))


def test_no_recommendation_when_no_menu_items(test_db):
    conn = db.get_connection()
    with db.transaction(conn):
        conn.execute("INSERT INTO restaurant (name) VALUES ('Empty Menu Place')")
    restaurant_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    result = skill3.recommend_offer(conn, restaurant_id=restaurant_id)
    conn.close()

    assert result.has_recommendation is False
    assert "no menu items" in result.reasoning.lower()


def test_no_recommendation_when_occupancy_too_high(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, _ = _seeded(conn)
    tables = conn.execute("SELECT id FROM dining_table WHERE restaurant_id = ?", (restaurant_id,)).fetchall()
    user_id = conn.execute("SELECT id FROM user LIMIT 1").fetchone()["id"]
    date, slot_index = _current_slot()

    # Confirm 3 of 5 tables (60%) at the current slot, above the 40% gate.
    for i, table in enumerate(tables[:3]):
        with db.transaction(conn):
            conn.execute(
                """
                INSERT INTO reservation
                    (status, restaurant_id, table_id, user_id, person_count, price, idempotency_key, expiry_time)
                VALUES ('CONFIRMED', ?, ?, ?, 2, 0, ?, NULL)
                """,
                (restaurant_id, table["id"], user_id, f"occ-{i}"),
            )
            reservation_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                "INSERT INTO slot_claim (reservation_id, table_id, date, slot_index) VALUES (?, ?, ?, ?)",
                (reservation_id, table["id"], date, slot_index),
            )

    result = skill3.recommend_offer(conn, restaurant_id=restaurant_id)
    conn.close()

    assert result.has_recommendation is False
    assert "occupancy is" in result.reasoning.lower()


def test_creates_active_offer_within_auto_approval_ceiling(test_db, monkeypatch):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, menu_items = _seeded(conn)
    target_item = menu_items[0]  # Tiramisu, max_auto_discount=3.00

    proposal = skill3.OfferProposal(
        has_recommendation=True,
        menu_item_id=target_item["id"],
        proposed_discount=2.00,  # within the 3.00 ceiling
        reasoning="Occupancy is 0%, worth a modest discount to attract diners.",
    )
    monkeypatch.setattr(skill3, "_structured_llm", _FakeStructuredLLM(proposal))

    result = skill3.recommend_offer(conn, restaurant_id=restaurant_id)

    assert result.has_recommendation is True
    assert result.status == "ACTIVE"
    assert result.offer_id is not None

    stored = conn.execute("SELECT status, proposed_value FROM offer WHERE id = ?", (result.offer_id,)).fetchone()
    conn.close()

    assert stored["status"] == "ACTIVE"
    assert stored["proposed_value"] == 2.00


def test_creates_pending_offer_above_auto_approval_ceiling(test_db, monkeypatch):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, menu_items = _seeded(conn)
    target_item = menu_items[0]  # Tiramisu, max_auto_discount=3.00

    proposal = skill3.OfferProposal(
        has_recommendation=True,
        menu_item_id=target_item["id"],
        proposed_discount=5.00,  # above the 3.00 ceiling
        reasoning="Occupancy is very low, a steeper discount is worth it today.",
    )
    monkeypatch.setattr(skill3, "_structured_llm", _FakeStructuredLLM(proposal))

    result = skill3.recommend_offer(conn, restaurant_id=restaurant_id)
    conn.close()

    assert result.has_recommendation is True
    assert result.status == "PENDING_CONFIRMATION"


def test_llm_never_sees_max_auto_discount(test_db, monkeypatch):
    """The ceiling is applied afterward in code; the prompt itself must
    not leak it, otherwise the model could just always stay under it.
    """
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, _ = _seeded(conn)

    captured = {}

    class _CapturingLLM:
        def invoke(self, prompt):
            captured["prompt"] = prompt
            return skill3.OfferProposal(has_recommendation=False, reasoning="n/a")

    monkeypatch.setattr(skill3, "_structured_llm", _CapturingLLM())

    skill3.recommend_offer(conn, restaurant_id=restaurant_id)
    conn.close()

    assert "max_auto_discount" not in captured["prompt"].lower()
    assert "ceiling" not in captured["prompt"].lower()
