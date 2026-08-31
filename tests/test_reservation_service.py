"""Tests for the release/expiry lifecycle: the background sweep and
cancellation both funnel through the same _release logic, and both must
leave a slot genuinely reclaimable afterward.
"""

import app.database as db
import app.services.reservation_service as reservations
from app.repositories import reservation_repo


def _seeded_ids(conn):
    restaurant_id = conn.execute("SELECT id FROM restaurant LIMIT 1").fetchone()["id"]
    table_id = conn.execute("SELECT id FROM dining_table LIMIT 1").fetchone()["id"]
    user_id = conn.execute("SELECT id FROM user LIMIT 1").fetchone()["id"]
    return restaurant_id, table_id, user_id


def _create_reservation(conn, restaurant_id, table_id, user_id, idempotency_key, status, expiry_sql, slot_index=28):
    with db.transaction(conn):
        conn.execute(
            f"""
            INSERT INTO reservation
                (status, restaurant_id, table_id, user_id, person_count, price, idempotency_key, expiry_time)
            VALUES (?, ?, ?, ?, 2, 50.0, ?, {expiry_sql})
            """,
            (status, restaurant_id, table_id, user_id, idempotency_key),
        )
        reservation_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO slot_claim (reservation_id, table_id, date, slot_index) VALUES (?, ?, '2026-09-01', ?)",
            (reservation_id, table_id, slot_index),
        )
    return reservation_id


def test_release_expired_reservations_releases_only_past_expiry(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_id, user_id = _seeded_ids(conn)

    expired_id = _create_reservation(
        conn, restaurant_id, table_id, user_id, "expired-key", "HELD", "datetime('now', '-1 minutes')", slot_index=1
    )
    future_id = _create_reservation(
        conn, restaurant_id, table_id, user_id, "future-key", "HELD", "datetime('now', '+10 minutes')", slot_index=2
    )
    conn.close()

    released_count = reservations.release_expired_reservations()

    conn = db.get_connection()
    expired_status = conn.execute("SELECT status FROM reservation WHERE id = ?", (expired_id,)).fetchone()["status"]
    future_status = conn.execute("SELECT status FROM reservation WHERE id = ?", (future_id,)).fetchone()["status"]
    expired_claims = conn.execute(
        "SELECT COUNT(*) FROM slot_claim WHERE reservation_id = ?", (expired_id,)
    ).fetchone()[0]
    future_claims = conn.execute(
        "SELECT COUNT(*) FROM slot_claim WHERE reservation_id = ?", (future_id,)
    ).fetchone()[0]
    conn.close()

    assert released_count == 1
    assert expired_status == "EXPIRED"
    assert future_status == "HELD"
    assert expired_claims == 0
    assert future_claims == 1


def test_release_expired_reservations_ignores_confirmed(test_db):
    """A CONFIRMED reservation past its original hold expiry must never
    be swept, expiry only ever applies to an unconfirmed HELD hold.
    """
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_id, user_id = _seeded_ids(conn)
    _create_reservation(
        conn, restaurant_id, table_id, user_id, "confirmed-key", "CONFIRMED", "datetime('now', '-1 minutes')"
    )
    conn.close()

    assert reservations.release_expired_reservations() == 0


def test_cancel_reservation_deletes_slot_claims_and_sets_status(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_id, user_id = _seeded_ids(conn)
    reservation_id = _create_reservation(
        conn, restaurant_id, table_id, user_id, "cancel-key", "HELD", "datetime('now', '+10 minutes')"
    )
    conn.close()

    reservations.cancel_reservation(reservation_id)

    conn = db.get_connection()
    status = conn.execute("SELECT status FROM reservation WHERE id = ?", (reservation_id,)).fetchone()["status"]
    claim_count = conn.execute(
        "SELECT COUNT(*) FROM slot_claim WHERE reservation_id = ?", (reservation_id,)
    ).fetchone()[0]
    conn.close()

    assert status == "CANCELLED"
    assert claim_count == 0


def test_released_slot_can_be_reclaimed(test_db):
    """The whole point of releasing: the same table/date/slot_index
    must become bookable again afterward, not permanently blocked by a
    dead SlotClaim row.
    """
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_id, user_id = _seeded_ids(conn)
    reservation_id = _create_reservation(
        conn, restaurant_id, table_id, user_id, "release-key", "HELD", "datetime('now', '+10 minutes')"
    )
    conn.close()

    reservations.cancel_reservation(reservation_id)

    conn = db.get_connection()
    # Re-claiming the identical (table_id, slot_index, date) must succeed now.
    new_id = _create_reservation(
        conn, restaurant_id, table_id, user_id, "reclaim-key", "HELD", "datetime('now', '+10 minutes')"
    )
    status = conn.execute("SELECT status FROM reservation WHERE id = ?", (new_id,)).fetchone()["status"]
    conn.close()

    assert status == "HELD"


def test_modify_reservation_moves_table_and_frees_old_slot(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_a, user_id = _seeded_ids(conn)
    table_b = conn.execute(
        "SELECT id FROM dining_table WHERE restaurant_id = ? AND id != ? LIMIT 1", (restaurant_id, table_a)
    ).fetchone()["id"]
    reservation_id = _create_reservation(
        conn, restaurant_id, table_a, user_id, "modify-key", "HELD", "datetime('now', '+10 minutes')", slot_index=28
    )
    conn.close()

    row, error = reservations.modify_reservation(
        reservation_id, table_id=table_b, date="2026-09-02", hour=10, minute=0, duration_minutes=60
    )

    assert error is None
    assert row["table_id"] == table_b
    assert row["booking_date"] == "2026-09-02"

    conn = db.get_connection()
    # The old (table_a, 2026-09-01, slot 28) must now be genuinely free, reclaimable by someone else.
    new_id = _create_reservation(
        conn, restaurant_id, table_a, user_id, "reclaim-old-slot-key", "HELD", "datetime('now', '+10 minutes')", slot_index=28
    )
    reclaimed_status = conn.execute("SELECT status FROM reservation WHERE id = ?", (new_id,)).fetchone()["status"]
    conn.close()
    assert reclaimed_status == "HELD"


def test_modify_reservation_recomputes_price_for_the_new_table(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_a, user_id = _seeded_ids(conn)
    table_b = conn.execute(
        "SELECT id, base_price FROM dining_table WHERE restaurant_id = ? AND id != ? LIMIT 1", (restaurant_id, table_a)
    ).fetchone()
    reservation_id = _create_reservation(
        conn, restaurant_id, table_a, user_id, "modify-price-key", "HELD", "datetime('now', '+10 minutes')"
    )
    conn.close()

    row, error = reservations.modify_reservation(
        reservation_id, table_id=table_b["id"], date="2026-09-03", hour=11, minute=0, duration_minutes=60
    )

    assert error is None
    # No competing demand at this fresh slot, price should equal table_b's own base price, not table_a's.
    assert row["price"] == table_b["base_price"]


def test_modify_nonexistent_reservation_returns_not_found(test_db):
    db.seed_if_empty()
    row, error = reservations.modify_reservation(999999, table_id=1, date="2026-09-01", hour=10, minute=0, duration_minutes=60)
    assert row is None
    assert error == "not_found"


def test_modify_cancelled_reservation_is_not_modifiable(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_id, user_id = _seeded_ids(conn)
    reservation_id = _create_reservation(
        conn, restaurant_id, table_id, user_id, "modify-cancelled-key", "HELD", "datetime('now', '+10 minutes')"
    )
    conn.close()
    reservations.cancel_reservation(reservation_id)

    row, error = reservations.modify_reservation(
        reservation_id, table_id=table_id, date="2026-09-04", hour=12, minute=0, duration_minutes=60
    )

    assert error == "not_modifiable"
    assert row["status"] == "CANCELLED"


def test_modify_conflict_leaves_the_reservation_exactly_as_it_was(test_db):
    """The core correctness guarantee this feature exists for: a
    conflict on the new slot must roll back the whole move, not leave
    the reservation half-moved or table-less.
    """
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_a, user_id = _seeded_ids(conn)
    table_b = conn.execute(
        "SELECT id FROM dining_table WHERE restaurant_id = ? AND id != ? LIMIT 1", (restaurant_id, table_a)
    ).fetchone()["id"]

    moving_id = _create_reservation(
        conn, restaurant_id, table_a, user_id, "moving-key", "HELD", "datetime('now', '+10 minutes')", slot_index=10
    )
    # A CONFIRMED (non-reclaimable) reservation already holds table_b's target slot.
    _create_reservation(
        conn, restaurant_id, table_b, user_id, "blocker-key", "CONFIRMED", "datetime('now', '+10 minutes')", slot_index=50
    )
    conn.close()

    row, error = reservations.modify_reservation(
        moving_id, table_id=table_b, date="2026-09-01", hour=12, minute=30, duration_minutes=15
    )

    assert error == "conflict"

    conn = db.get_connection()
    still_claimed = conn.execute(
        "SELECT COUNT(*) FROM slot_claim WHERE reservation_id = ? AND table_id = ? AND slot_index = 10",
        (moving_id, table_a),
    ).fetchone()[0]
    current = reservation_repo.get_by_id(conn, moving_id)
    conn.close()

    assert still_claimed == 1
    assert current["table_id"] == table_a
    assert current["status"] == "HELD"
