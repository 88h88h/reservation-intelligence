"""Raw data access for menu_item rows."""

import sqlite3


def list_for_restaurant(conn: sqlite3.Connection, restaurant_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM menu_item WHERE restaurant_id = ? ORDER BY id", (restaurant_id,)
    ).fetchall()


def get_by_id(conn: sqlite3.Connection, menu_item_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM menu_item WHERE id = ?", (menu_item_id,)).fetchone()
