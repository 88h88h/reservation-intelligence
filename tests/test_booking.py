"""Tests for the core booking transaction: atomic slot claiming,
idempotency, and the lazy-expiry reclaim path.
"""

import sqlite3

import pytest

import app.database as db
import app.services.reservation_service as reservation_service

DATE = "2026-09-01"


def _seeded_ids(conn):
    restaurant_id = conn.execute("SELECT id FROM restaurant LIMIT 1").fetchone()["id"]
    table_id = conn.execute("SELECT id FROM dining_table LIMIT 1").fetchone()["id"]
    user_id = conn.execute("SELECT id FROM user LIMIT 1").fetchone()["id"]
    return restaurant_id, table_id, user_id


def test_create_reservation_claims_all_requested_slots(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_id, user_id = _seeded_ids(conn)
    conn.close()

    reservation = reservation_service.create_reservation(
        restaurant_id=restaurant_id,
        table_id=table_id,
        user_id=user_id,
        person_count=2,
        date=DATE,
        hour=19,
        minute=0,
        duration_minutes=60,
        idempotency_key="booking-1",
    )

    assert reservation["status"] == "HELD"

    conn = db.get_connection()
    claim_count = conn.execute(
        "SELECT COUNT(*) FROM slot_claim WHERE reservation_id = ?", (reservation["id"],)
    ).fetchone()[0]
    conn.close()

    assert claim_count == 4  # 60 minutes / 15-minute slots


def test_create_reservation_is_idempotent(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_id, user_id = _seeded_ids(conn)
    conn.close()

    kwargs = dict(
        restaurant_id=restaurant_id,
        table_id=table_id,
        user_id=user_id,
        person_count=2,
        date=DATE,
        hour=19,
        minute=0,
        duration_minutes=60,
        idempotency_key="repeat-key",
    )

    first = reservation_service.create_reservation(**kwargs)
    second = reservation_service.create_reservation(**kwargs)

    assert first["id"] == second["id"]

    conn = db.get_connection()
    (reservation_count,) = conn.execute(
        "SELECT COUNT(*) FROM reservation WHERE idempotency_key = ?", ("repeat-key",)
    ).fetchone()
    conn.close()

    assert reservation_count == 1


def test_create_reservation_conflicts_on_already_held_slot(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_id, user_id = _seeded_ids(conn)
    conn.close()

    reservation_service.create_reservation(
        restaurant_id=restaurant_id,
        table_id=table_id,
        user_id=user_id,
        person_count=2,
        date=DATE,
        hour=19,
        minute=0,
        duration_minutes=60,
        idempotency_key="first-booking",
    )

    with pytest.raises(sqlite3.IntegrityError):
        reservation_service.create_reservation(
            restaurant_id=restaurant_id,
            table_id=table_id,
            user_id=user_id,
            person_count=2,
            date=DATE,
            hour=19,
            minute=0,
            duration_minutes=60,
            idempotency_key="second-booking",
        )


def test_create_reservation_leaves_no_partial_claims_on_conflict(test_db):
    """If slot 2 of 4 conflicts, slots 1, 3, and 4 must not remain
    claimed by the failed attempt either.
    """
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_id, user_id = _seeded_ids(conn)
    conn.close()

    reservation_service.create_reservation(
        restaurant_id=restaurant_id,
        table_id=table_id,
        user_id=user_id,
        person_count=2,
        date=DATE,
        hour=19,
        minute=0,
        duration_minutes=60,
        idempotency_key="blocker",
    )

    with pytest.raises(sqlite3.IntegrityError):
        reservation_service.create_reservation(
            restaurant_id=restaurant_id,
            table_id=table_id,
            user_id=user_id,
            person_count=2,
            date=DATE,
            hour=18,
            minute=45,  # overlaps by one slot with the existing 19:00 booking
            duration_minutes=60,
            idempotency_key="overlapper",
        )

    conn = db.get_connection()
    (claim_count,) = conn.execute(
        """
        SELECT COUNT(*) FROM slot_claim sc
        JOIN reservation r ON r.id = sc.reservation_id
        WHERE r.idempotency_key = 'overlapper'
        """
    ).fetchone()
    conn.close()

    assert claim_count == 0


def test_create_reservation_reclaims_expired_hold(test_db):
    """A HELD reservation past its own expiry_time must not permanently
    block the slot, the new booking should transparently reclaim it.
    """
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_id, user_id = _seeded_ids(conn)

    with db.transaction(conn):
        conn.execute(
            """
            INSERT INTO reservation
                (status, restaurant_id, table_id, user_id, person_count, price, idempotency_key, expiry_time)
            VALUES ('HELD', ?, ?, ?, 2, 40.0, 'stale-hold', datetime('now', '-1 minutes'))
            """,
            (restaurant_id, table_id, user_id),
        )
        stale_reservation_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO slot_claim (reservation_id, table_id, date, slot_index) VALUES (?, ?, ?, 76)",
            (stale_reservation_id, table_id, DATE),
        )
    conn.close()

    new_reservation = reservation_service.create_reservation(
        restaurant_id=restaurant_id,
        table_id=table_id,
        user_id=user_id,
        person_count=2,
        date=DATE,
        hour=19,
        minute=0,
        duration_minutes=15,
        idempotency_key="reclaimer",
    )

    assert new_reservation["status"] == "HELD"

    conn = db.get_connection()
    stale_status = conn.execute(
        "SELECT status FROM reservation WHERE id = ?", (stale_reservation_id,)
    ).fetchone()["status"]
    stale_claims = conn.execute(
        "SELECT COUNT(*) FROM slot_claim WHERE reservation_id = ?", (stale_reservation_id,)
    ).fetchone()[0]
    conn.close()

    assert stale_status == "EXPIRED"
    assert stale_claims == 0


def test_create_reservation_rejects_party_larger_than_the_table(test_db):
    """Table 1 seats two, so a party of eight must be turned away
    before the reservation row or any of its slot claims exist.
    """
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_id, user_id = _seeded_ids(conn)
    conn.close()

    with pytest.raises(reservation_service.BookingRejected):
        reservation_service.create_reservation(
            restaurant_id=restaurant_id,
            table_id=table_id,
            user_id=user_id,
            person_count=8,
            date=DATE,
            hour=19,
            minute=0,
            duration_minutes=60,
            idempotency_key="oversized-party",
        )
