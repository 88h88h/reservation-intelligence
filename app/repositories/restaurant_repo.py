"""Raw data access for restaurant rows."""

import sqlite3


def list_all(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM restaurant ORDER BY id").fetchall()


def get_by_id(conn: sqlite3.Connection, restaurant_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM restaurant WHERE id = ?", (restaurant_id,)).fetchone()
