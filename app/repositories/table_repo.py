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
