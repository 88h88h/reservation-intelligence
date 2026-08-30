"""Raw data access for user rows."""

import sqlite3


def list_all(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM user ORDER BY id").fetchall()
