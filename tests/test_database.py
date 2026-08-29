"""Tests for the schema and the atomicity/uniqueness guarantees the
whole booking design depends on.
"""

import sqlite3

import pytest

import app.database as db

EXPECTED_TABLES = {"restaurant", "user", "dining_table", "reservation", "slot_claim", "menu_item", "offer"}


def _seeded_ids(conn):
    restaurant_id = conn.execute("SELECT id FROM restaurant LIMIT 1").fetchone()["id"]
    table_id = conn.execute("SELECT id FROM dining_table LIMIT 1").fetchone()["id"]
    user_id = conn.execute("SELECT id FROM user LIMIT 1").fetchone()["id"]
    return restaurant_id, table_id, user_id


def _insert_reservation_with_slot(conn, restaurant_id, table_id, user_id, idempotency_key, slot_index=28, date="2026-09-01"):
    """Insert a HELD reservation plus its single slot claim, inside one
    transaction, mirroring how the real booking flow will do it.
    """
    with db.transaction(conn):
        conn.execute(
            """
            INSERT INTO reservation
                (status, restaurant_id, table_id, user_id, person_count, price, idempotency_key, expiry_time)
            VALUES ('HELD', ?, ?, ?, 2, 50.0, ?, datetime('now', '+10 minutes'))
            """,
            (restaurant_id, table_id, user_id, idempotency_key),
        )
        reservation_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO slot_claim (reservation_id, table_id, date, slot_index) VALUES (?, ?, ?, ?)",
            (reservation_id, table_id, date, slot_index),
        )
    return reservation_id


def test_init_db_creates_all_tables(test_db):
    conn = db.get_connection()
    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.close()
    assert EXPECTED_TABLES <= tables


def test_seed_if_empty_populates_sample_data(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    (restaurant_count,) = conn.execute("SELECT COUNT(*) FROM restaurant").fetchone()
    (table_count,) = conn.execute("SELECT COUNT(*) FROM dining_table").fetchone()
    (user_count,) = conn.execute("SELECT COUNT(*) FROM user").fetchone()
    conn.close()
    assert restaurant_count == 1
    assert table_count == 5
    assert user_count == 2


def test_seed_if_empty_is_idempotent(test_db):
    db.seed_if_empty()
    db.seed_if_empty()
    conn = db.get_connection()
    (restaurant_count,) = conn.execute("SELECT COUNT(*) FROM restaurant").fetchone()
    conn.close()
    assert restaurant_count == 1


def test_foreign_keys_are_enforced(test_db):
    """SQLite disables FK enforcement by default; this confirms the
    PRAGMA in get_connection() is actually taking effect.
    """
    conn = db.get_connection()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO reservation
                (status, restaurant_id, table_id, user_id, person_count, price, idempotency_key, expiry_time)
            VALUES ('HELD', 999, 999, 999, 2, 50.0, 'bad-fk', datetime('now', '+10 minutes'))
            """
        )
    conn.close()


def test_slot_claim_unique_constraint_blocks_double_booking(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_id, user_id = _seeded_ids(conn)

    _insert_reservation_with_slot(conn, restaurant_id, table_id, user_id, "key-1")

    with pytest.raises(sqlite3.IntegrityError):
        _insert_reservation_with_slot(conn, restaurant_id, table_id, user_id, "key-2")

    conn.close()


def test_transaction_rollback_leaves_no_partial_reservation(test_db):
    """The core correctness guarantee this design exists for: if the
    slot insert fails, the reservation row it belongs to must not
    remain committed either, no half-booked state should ever be
    observable.
    """
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_id, user_id = _seeded_ids(conn)

    _insert_reservation_with_slot(conn, restaurant_id, table_id, user_id, "key-1")
    (count_before,) = conn.execute("SELECT COUNT(*) FROM reservation").fetchone()

    with pytest.raises(sqlite3.IntegrityError):
        _insert_reservation_with_slot(conn, restaurant_id, table_id, user_id, "key-2")

    (count_after,) = conn.execute("SELECT COUNT(*) FROM reservation").fetchone()
    conn.close()

    assert count_after == count_before


def test_idempotency_key_must_be_unique(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_id, user_id = _seeded_ids(conn)

    _insert_reservation_with_slot(conn, restaurant_id, table_id, user_id, "same-key", slot_index=28)

    with pytest.raises(sqlite3.IntegrityError):
        _insert_reservation_with_slot(conn, restaurant_id, table_id, user_id, "same-key", slot_index=40)

    conn.close()


def test_status_check_constraint_rejects_invalid_values(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, table_id, user_id = _seeded_ids(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO reservation
                (status, restaurant_id, table_id, user_id, person_count, price, idempotency_key, expiry_time)
            VALUES ('NOT_A_REAL_STATUS', ?, ?, ?, 2, 50.0, 'bad-status', datetime('now', '+10 minutes'))
            """,
            (restaurant_id, table_id, user_id),
        )
    conn.close()
