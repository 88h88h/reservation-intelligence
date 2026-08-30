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


def list_for_restaurant(conn: sqlite3.Connection, restaurant_id: int) -> list[sqlite3.Row]:
    """Includes the actual booked date/start slot/slot count, derived
    from slot_claim, not stored redundantly on the reservation itself.
    A cancelled or expired reservation has no claims left (they're
    deleted on release), so these come back NULL for it, an accurate
    answer, "this no longer holds any date", not a stale one.
    """
    return conn.execute(
        """
        SELECT r.*, sc.date AS booking_date, MIN(sc.slot_index) AS start_slot_index, COUNT(sc.id) AS slot_count
        FROM reservation r
        LEFT JOIN slot_claim sc ON sc.reservation_id = r.id
        WHERE r.restaurant_id = ?
        GROUP BY r.id
        ORDER BY r.created_at DESC
        """,
        (restaurant_id,),
    ).fetchall()


def get_by_id(conn: sqlite3.Connection, reservation_id: int) -> sqlite3.Row | None:
    """Same derived booking_date/start_slot_index/slot_count as
    list_for_restaurant, so any endpoint returning a reservation shows
    the same complete picture, not a subset depending on which query
    happened to fetch it.
    """
    return conn.execute(
        """
        SELECT r.*, sc.date AS booking_date, MIN(sc.slot_index) AS start_slot_index, COUNT(sc.id) AS slot_count
        FROM reservation r
        LEFT JOIN slot_claim sc ON sc.reservation_id = r.id
        WHERE r.id = ?
        GROUP BY r.id
        """,
        (reservation_id,),
    ).fetchone()


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


def count_tables_claimed_at_slots(
    conn: sqlite3.Connection, *, restaurant_id: int, date: str, slot_indices: list[int], status: str
) -> int:
    """How many distinct tables at this restaurant have a claim, in the
    given status, covering any of the given slots on this date. Used to
    derive occupancy/demand ratios for pricing, scoped to the specific
    slots being priced, not the restaurant's activity in general.
    """
    if not slot_indices:
        return 0
    placeholders = ",".join("?" for _ in slot_indices)
    (count,) = conn.execute(
        f"""
        SELECT COUNT(DISTINCT sc.table_id)
        FROM slot_claim sc
        JOIN reservation r ON r.id = sc.reservation_id
        JOIN dining_table t ON t.id = sc.table_id
        WHERE t.restaurant_id = ?
          AND sc.date = ?
          AND sc.slot_index IN ({placeholders})
          AND r.status = ?
        """,
        (restaurant_id, date, *slot_indices, status),
    ).fetchone()
    return count


def count_reservations_for_table_on_date(
    conn: sqlite3.Connection, *, table_id: int, date: str, statuses: tuple[str, ...] = ("CONFIRMED", "HELD")
) -> int:
    """How many distinct reservations this table already has on this
    date, across the given statuses. A low count is the "this table
    has been sitting idle" signal for skill 2.
    """
    placeholders = ",".join("?" for _ in statuses)
    (count,) = conn.execute(
        f"""
        SELECT COUNT(DISTINCT r.id)
        FROM slot_claim sc
        JOIN reservation r ON r.id = sc.reservation_id
        WHERE sc.table_id = ? AND sc.date = ? AND r.status IN ({placeholders})
        """,
        (table_id, date, *statuses),
    ).fetchone()
    return count


def find_reclaimable_blocker(conn: sqlite3.Connection, table_id: int, date: str, slot_index: int) -> int | None:
    """If (table_id, date, slot_index) is currently blocked by a HELD
    reservation that's already past its own expiry, return that
    reservation's id so the caller can release it and retry. Returns
    None if the slot isn't blocked by anything reclaimable, either it's
    genuinely taken by an active hold/confirmation, or not blocked at
    all (the caller only calls this after a real conflict, so the
    latter shouldn't happen in practice).
    """
    row = conn.execute(
        """
        SELECT r.id
        FROM slot_claim sc
        JOIN reservation r ON r.id = sc.reservation_id
        WHERE sc.table_id = ? AND sc.date = ? AND sc.slot_index = ?
          AND r.status = 'HELD'
          AND r.expiry_time IS NOT NULL
          AND r.expiry_time < datetime('now')
        """,
        (table_id, date, slot_index),
    ).fetchone()
    return row["id"] if row else None
