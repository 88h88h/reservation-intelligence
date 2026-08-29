"""Raw data access for reservation and slot_claim rows.

No transaction management here, callers (services) own transaction
boundaries, since one business operation, releasing a reservation,
claiming several slots, often needs more than one of these calls to
succeed or fail together.
"""

import sqlite3


def insert_reservation(
    conn: sqlite3.Connection,
    *,
    status: str,
    restaurant_id: int,
    table_id: int,
    user_id: int,
    person_count: int,
    price: float,
    idempotency_key: str,
    expiry_time: str | None = None,
) -> int:
    conn.execute(
        """
        INSERT INTO reservation
            (status, restaurant_id, table_id, user_id, person_count, price, idempotency_key, expiry_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (status, restaurant_id, table_id, user_id, person_count, price, idempotency_key, expiry_time),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def insert_slot_claim(conn: sqlite3.Connection, *, reservation_id: int, table_id: int, date: str, slot_index: int) -> None:
    conn.execute(
        "INSERT INTO slot_claim (reservation_id, table_id, date, slot_index) VALUES (?, ?, ?, ?)",
        (reservation_id, table_id, date, slot_index),
    )


def get_by_id(conn: sqlite3.Connection, reservation_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM reservation WHERE id = ?", (reservation_id,)).fetchone()


def get_by_idempotency_key(conn: sqlite3.Connection, idempotency_key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM reservation WHERE idempotency_key = ?", (idempotency_key,)).fetchone()


def find_held_past_expiry(conn: sqlite3.Connection) -> list[int]:
    return [
        row["id"]
        for row in conn.execute(
            """
            SELECT id FROM reservation
            WHERE status = 'HELD' AND expiry_time IS NOT NULL AND expiry_time < datetime('now')
            """
        )
    ]


def delete_slot_claims(conn: sqlite3.Connection, reservation_id: int) -> None:
    conn.execute("DELETE FROM slot_claim WHERE reservation_id = ?", (reservation_id,))


def update_status(conn: sqlite3.Connection, reservation_id: int, status: str) -> None:
    conn.execute("UPDATE reservation SET status = ? WHERE id = ?", (status, reservation_id))
