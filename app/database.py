"""SQLite connection, schema, and seed data.

Table name `dining_table` (not `table`) to sidestep the SQL reserved word
entirely rather than quoting it everywhere.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
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


_SEED_RESTAURANTS = [
    {
        "name": "The Rosemary",
        "tables": [
            ("Table 1", 2, "window", 1, 40.00),
            ("Table 2", 4, "standard", 2, 60.00),
            ("Table 3", 4, "standard", 2, 60.00),
            ("Table 4", 6, "patio", 4, 90.00),
            ("Table 5", 2, "chef's counter", 1, 55.00),
        ],
        "menu_items": [
            ("Tiramisu", 9.00, 3.00),
            ("House Cocktail", 12.00, 4.00),
        ],
    },
    {
        "name": "Blue Anchor",
        "tables": [
            ("Table 1", 2, "patio", 1, 45.00),
            ("Table 2", 4, "patio", 2, 65.00),
            ("Table 3", 4, "standard", 2, 55.00),
            ("Table 4", 8, "patio", 5, 110.00),
        ],
        "menu_items": [
            ("Grilled Oysters", 14.00, 4.00),
            ("Citrus Spritz", 11.00, 3.00),
        ],
    },
    {
        "name": "Nomad Kitchen",
        "tables": [
            ("Table 1", 2, "chef's counter", 1, 50.00),
            ("Table 2", 2, "standard", 1, 45.00),
            ("Table 3", 6, "standard", 3, 85.00),
            ("Table 4", 4, "window", 2, 65.00),
        ],
        "menu_items": [
            ("Charcuterie Board", 16.00, 5.00),
            ("Old Fashioned", 13.00, 3.00),
        ],
    },
]


def seed_if_empty() -> None:
    """Sample data so the dashboard and agent skills have something real
    to operate on, standing in for a registration/onboarding flow that's
    out of scope for this project. Three restaurants, not one, so the
    diner-facing browse view has something real to compare, "which one
    has a good vibe right now" only means something with more than one
    option on the page.
    """
    conn = get_connection()
    try:
        (restaurant_count,) = conn.execute("SELECT COUNT(*) FROM restaurant").fetchone()
        if restaurant_count > 0:
            return

        with transaction(conn):
            users = [("Alice Chen", "alice@example.com"), ("Bob Martinez", "bob@example.com")]
            conn.executemany("INSERT INTO user (name, contact) VALUES (?, ?)", users)

            for restaurant in _SEED_RESTAURANTS:
                conn.execute("INSERT INTO restaurant (name) VALUES (?)", (restaurant["name"],))
                restaurant_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                conn.executemany(
                    """
                    INSERT INTO dining_table (restaurant_id, name, capacity, type, min_party_size, base_price)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [(restaurant_id, *t) for t in restaurant["tables"]],
                )

                conn.executemany(
                    """
                    INSERT INTO menu_item (restaurant_id, name, price, max_auto_discount)
                    VALUES (?, ?, ?, ?)
                    """,
                    [(restaurant_id, *m) for m in restaurant["menu_items"]],
                )
    finally:
        conn.close()


# Which tables are confirmed all day, "today", so browsing by vibe on the
# diner page shows real contrast instead of three identical 0%s: The
# Rosemary comfortably busy, Blue Anchor left untouched (genuinely quiet),
# Nomad Kitchen lively.
_DEMO_OCCUPANCY_BASELINE = {
    "The Rosemary": ["Table 2", "Table 3"],
    "Nomad Kitchen": ["Table 1", "Table 2", "Table 3"],
}


def ensure_demo_occupancy_baseline() -> None:
    """Seed a stable, demo-ready occupancy baseline for today's date.

    Runs on every startup, not just when the database is first
    created, and is keyed to today's date so it stays correct across
    days without needing a fresh database, idempotent via a dedicated
    idempotency_key pattern, so restarting the app repeatedly never
    creates duplicates.
    """
    conn = get_connection()
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        user_row = conn.execute("SELECT id FROM user ORDER BY id LIMIT 1").fetchone()
        if user_row is None:
            return
        user_id = user_row["id"]

        for restaurant_name, table_names in _DEMO_OCCUPANCY_BASELINE.items():
            restaurant = conn.execute("SELECT id FROM restaurant WHERE name = ?", (restaurant_name,)).fetchone()
            if restaurant is None:
                continue
            restaurant_id = restaurant["id"]

            for table_name in table_names:
                table = conn.execute(
                    "SELECT id, base_price FROM dining_table WHERE restaurant_id = ? AND name = ?",
                    (restaurant_id, table_name),
                ).fetchone()
                if table is None:
                    continue
                table_id = table["id"]

                idempotency_key = f"demo-baseline-{table_id}-{today}"
                if conn.execute(
                    "SELECT 1 FROM reservation WHERE idempotency_key = ?", (idempotency_key,)
                ).fetchone():
                    continue

                with transaction(conn):
                    conn.execute(
                        """
                        INSERT INTO reservation
                            (status, restaurant_id, table_id, user_id, person_count, price, idempotency_key)
                        VALUES ('CONFIRMED', ?, ?, ?, 2, ?, ?)
                        """,
                        (restaurant_id, table_id, user_id, table["base_price"], idempotency_key),
                    )
                    reservation_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    conn.executemany(
                        "INSERT INTO slot_claim (reservation_id, table_id, date, slot_index) VALUES (?, ?, ?, ?)",
                        [(reservation_id, table_id, today, slot) for slot in range(96)],
                    )
    finally:
        conn.close()
