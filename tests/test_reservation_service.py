"""Tests for the release/expiry lifecycle: the background sweep and
cancellation both funnel through the same _release logic, and both must
leave a slot genuinely reclaimable afterward.
"""

import app.database as db
import app.services.reservation_service as reservations


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
