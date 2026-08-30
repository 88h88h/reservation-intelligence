"""Raw data access for offer rows."""

import sqlite3


def insert_offer(conn: sqlite3.Connection, *, menu_item_id: int, proposed_value: float, status: str) -> int:
    conn.execute(
        "INSERT INTO offer (menu_item_id, proposed_value, status) VALUES (?, ?, ?)",
        (menu_item_id, proposed_value, status),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_by_id(conn: sqlite3.Connection, offer_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM offer WHERE id = ?", (offer_id,)).fetchone()


def list_for_restaurant(conn: sqlite3.Connection, restaurant_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT o.* FROM offer o
        JOIN menu_item mi ON mi.id = o.menu_item_id
        WHERE mi.restaurant_id = ?
        ORDER BY o.id DESC
        """,
        (restaurant_id,),
    ).fetchall()


def update_status(conn: sqlite3.Connection, offer_id: int, status: str) -> int:
    """Returns the number of rows actually changed, so callers can tell
    a real transition from a no-op (e.g. approving an already-ACTIVE offer).
    """
    cursor = conn.execute("UPDATE offer SET status = ? WHERE id = ?", (status, offer_id))
    return cursor.rowcount


def delete(conn: sqlite3.Connection, offer_id: int) -> int:
    """A genuine delete, unlike the rest of this project's lifecycle
    entities (reservations are cancelled, never removed). Only used by
    demo-mode cleanup, real offers stay auditable via status transitions;
    this exists so a rehearsed demo run leaves no visible trace behind.
    """
    cursor = conn.execute("DELETE FROM offer WHERE id = ?", (offer_id,))
    return cursor.rowcount
