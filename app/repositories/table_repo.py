"""Raw data access for dining_table rows."""

import sqlite3


def get_by_id(conn: sqlite3.Connection, table_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM dining_table WHERE id = ?", (table_id,)).fetchone()


def count_bookable(conn: sqlite3.Connection, restaurant_id: int) -> int:
    (count,) = conn.execute(
        "SELECT COUNT(*) FROM dining_table WHERE restaurant_id = ? AND is_bookable = 1",
        (restaurant_id,),
    ).fetchone()
    return count


def list_for_restaurant(conn: sqlite3.Connection, restaurant_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM dining_table WHERE restaurant_id = ? ORDER BY id", (restaurant_id,)
    ).fetchall()


def is_free(conn: sqlite3.Connection, *, table_id: int, date: str, slot_indices: list[int]) -> bool:
    """Whether a specific table has no active claim (CONFIRMED, or HELD
    and not yet past its own expiry) on any of the given slots.
    """
    if not slot_indices:
        return True
    placeholders = ",".join("?" for _ in slot_indices)
    row = conn.execute(
        f"""
        SELECT 1
        FROM slot_claim sc
        JOIN reservation r ON r.id = sc.reservation_id
        WHERE sc.table_id = ?
          AND sc.date = ?
          AND sc.slot_index IN ({placeholders})
          AND (r.status = 'CONFIRMED' OR (r.status = 'HELD' AND r.expiry_time >= datetime('now')))
        LIMIT 1
        """,
        (table_id, date, *slot_indices),
    ).fetchone()
    return row is None


def find_available(
    conn: sqlite3.Connection, *, restaurant_id: int, date: str, slot_indices: list[int], person_count: int
) -> list[sqlite3.Row]:
    """Bookable tables with enough capacity and no active claim (a
    CONFIRMED reservation, or a HELD one not yet past its own expiry)
    on any of the requested slots. Does not filter on min_party_size,
    that stays a soft signal the caller/UI decides how to use, not a
    hard exclusion here.
    """
    placeholders = ",".join("?" for _ in slot_indices)
    query = f"""
        SELECT * FROM dining_table t
        WHERE t.restaurant_id = ?
          AND t.is_bookable = 1
          AND t.capacity >= ?
          AND t.id NOT IN (
              SELECT sc.table_id
              FROM slot_claim sc
              JOIN reservation r ON r.id = sc.reservation_id
              WHERE sc.date = ?
                AND sc.slot_index IN ({placeholders})
                AND (r.status = 'CONFIRMED' OR (r.status = 'HELD' AND r.expiry_time >= datetime('now')))
          )
        ORDER BY t.id
    """
    params = [restaurant_id, person_count, date, *slot_indices]
    return conn.execute(query, params).fetchall()
