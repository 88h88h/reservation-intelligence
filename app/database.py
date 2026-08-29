"""SQLite connection, schema, and seed data.

Table name `dining_table` (not `table`) to sidestep the SQL reserved word
entirely rather than quoting it everywhere.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "reservation.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS restaurant (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    opening_hour INTEGER NOT NULL DEFAULT 17,
    closing_hour INTEGER NOT NULL DEFAULT 23,
    peak_start_hour INTEGER NOT NULL DEFAULT 19,
    peak_end_hour INTEGER NOT NULL DEFAULT 21
);

CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact TEXT
);

CREATE TABLE IF NOT EXISTS dining_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL REFERENCES restaurant(id),
    name TEXT NOT NULL,
    capacity INTEGER NOT NULL,
    is_bookable INTEGER NOT NULL DEFAULT 1,
    type TEXT,
    min_party_size INTEGER NOT NULL DEFAULT 1,
    base_price NUMERIC NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reservation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL CHECK (status IN ('HELD', 'CONFIRMED', 'EXPIRED', 'CANCELLED')),
    restaurant_id INTEGER NOT NULL REFERENCES restaurant(id),
    table_id INTEGER NOT NULL REFERENCES dining_table(id),
    user_id INTEGER NOT NULL REFERENCES user(id),
    person_count INTEGER NOT NULL,
    price NUMERIC NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expiry_time TEXT,
    time_of_confirmation TEXT,
    checkin_time TEXT,
    checkout_time TEXT
);

CREATE INDEX IF NOT EXISTS idx_reservation_status_expiry
    ON reservation (status, expiry_time);

CREATE TABLE IF NOT EXISTS slot_claim (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_id INTEGER NOT NULL REFERENCES reservation(id),
    table_id INTEGER NOT NULL REFERENCES dining_table(id),
    date TEXT NOT NULL,
    slot_index INTEGER NOT NULL,
    UNIQUE (table_id, slot_index, date)
);

CREATE INDEX IF NOT EXISTS idx_slot_claim_reservation
    ON slot_claim (reservation_id);

CREATE TABLE IF NOT EXISTS menu_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL REFERENCES restaurant(id),
    name TEXT NOT NULL,
    price NUMERIC NOT NULL,
    max_auto_discount NUMERIC NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS offer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_item_id INTEGER NOT NULL REFERENCES menu_item(id),
    proposed_value NUMERIC NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING_CONFIRMATION', 'ACTIVE', 'REJECTED', 'EXPIRED')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_connection() -> sqlite3.Connection:
    """One connection per request/task. autocommit mode: we control
    transaction boundaries explicitly via `transaction()`, rather than
    relying on sqlite3's own implicit-transaction quirks.
    """
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    """Wrap a block of writes in one atomic transaction.

    The UNIQUE constraint on slot_claim only prevents double-booking if
    every slot a reservation needs is inserted inside a single
    BEGIN/COMMIT: if slot 4 of 6 fails, slots 1-3 must not remain
    committed as a half-booked reservation.
    """
    conn.execute("BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()


def seed_if_empty() -> None:
    """Sample data so the dashboard and agent skills have something real
    to operate on, standing in for a registration/onboarding flow that's
    out of scope for this project.
    """
    conn = get_connection()
    try:
        (restaurant_count,) = conn.execute("SELECT COUNT(*) FROM restaurant").fetchone()
        if restaurant_count > 0:
            return

        with transaction(conn):
            conn.execute("INSERT INTO restaurant (name) VALUES (?)", ("The Rosemary",))
            restaurant_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            users = [("Alice Chen", "alice@example.com"), ("Bob Martinez", "bob@example.com")]
            conn.executemany("INSERT INTO user (name, contact) VALUES (?, ?)", users)

            tables = [
                (restaurant_id, "Table 1", 2, "window", 1, 40.00),
                (restaurant_id, "Table 2", 4, "standard", 2, 60.00),
                (restaurant_id, "Table 3", 4, "standard", 2, 60.00),
                (restaurant_id, "Table 4", 6, "patio", 4, 90.00),
                (restaurant_id, "Table 5", 2, "chef's counter", 1, 55.00),
            ]
            conn.executemany(
                """
                INSERT INTO dining_table (restaurant_id, name, capacity, type, min_party_size, base_price)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                tables,
            )

            menu_items = [
                (restaurant_id, "Tiramisu", 9.00, 3.00),
                (restaurant_id, "House Cocktail", 12.00, 4.00),
            ]
            conn.executemany(
                """
                INSERT INTO menu_item (restaurant_id, name, price, max_auto_discount)
                VALUES (?, ?, ?, ?)
                """,
                menu_items,
            )
    finally:
        conn.close()
