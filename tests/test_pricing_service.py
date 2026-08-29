import app.database as db
import app.services.pricing_service as pricing_service

DATE = "2026-09-01"
SLOTS = [76, 77, 78, 79]  # 7:00-8:00pm


def _seeded(conn):
    restaurant_id = conn.execute("SELECT id FROM restaurant LIMIT 1").fetchone()["id"]
    tables = conn.execute("SELECT id, base_price FROM dining_table ORDER BY id").fetchall()
    user_id = conn.execute("SELECT id FROM user LIMIT 1").fetchone()["id"]
    return restaurant_id, tables, user_id


def _claim(conn, restaurant_id, table_id, user_id, status, idempotency_key, slots=SLOTS):
    with db.transaction(conn):
        conn.execute(
            """
            INSERT INTO reservation
                (status, restaurant_id, table_id, user_id, person_count, price, idempotency_key, expiry_time)
            VALUES (?, ?, ?, ?, 2, 0, ?, datetime('now', '+10 minutes'))
            """,
            (status, restaurant_id, table_id, user_id, idempotency_key),
        )
        reservation_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for slot_index in slots:
            conn.execute(
                "INSERT INTO slot_claim (reservation_id, table_id, date, slot_index) VALUES (?, ?, ?, ?)",
                (reservation_id, table_id, DATE, slot_index),
            )


def test_price_equals_base_price_with_no_demand(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, tables, _ = _seeded(conn)
    target_table = tables[0]

    price = pricing_service.calculate_price(
        conn, restaurant_id=restaurant_id, table_id=target_table["id"], date=DATE, slot_indices=SLOTS
    )
    conn.close()

    assert price == target_table["base_price"]


def test_price_increases_with_confirmed_occupancy(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, tables, user_id = _seeded(conn)
    target_table, other_table = tables[0], tables[1]

    _claim(conn, restaurant_id, other_table["id"], user_id, "CONFIRMED", "occ-key")

    price = pricing_service.calculate_price(
        conn, restaurant_id=restaurant_id, table_id=target_table["id"], date=DATE, slot_indices=SLOTS
    )
    conn.close()

    assert price > target_table["base_price"]


def test_price_increases_with_pending_held_demand(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, tables, user_id = _seeded(conn)
    target_table, other_table = tables[0], tables[1]

    _claim(conn, restaurant_id, other_table["id"], user_id, "HELD", "pending-key")

    price = pricing_service.calculate_price(
        conn, restaurant_id=restaurant_id, table_id=target_table["id"], date=DATE, slot_indices=SLOTS
    )
    conn.close()

    assert price > target_table["base_price"]


def test_price_ignores_demand_at_different_slots(test_db):
    """Demand for a different time on the same date must not move the
    price for the requested slots, the whole point of scoping to the
    specific slots being booked rather than the restaurant in general.
    """
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, tables, user_id = _seeded(conn)
    target_table, other_table = tables[0], tables[1]

    unrelated_slots = [40, 41, 42, 43]  # a different time entirely
    _claim(conn, restaurant_id, other_table["id"], user_id, "CONFIRMED", "unrelated-key", slots=unrelated_slots)

    price = pricing_service.calculate_price(
        conn, restaurant_id=restaurant_id, table_id=target_table["id"], date=DATE, slot_indices=SLOTS
    )
    conn.close()

    assert price == target_table["base_price"]


def test_price_never_exceeds_max_multiplier(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant_id, tables, user_id = _seeded(conn)
    target_table = tables[0]

    # Fill every other table with both confirmed occupancy and pending demand.
    for i, other_table in enumerate(tables[1:], start=1):
        _claim(conn, restaurant_id, other_table["id"], user_id, "CONFIRMED", f"max-occ-{i}")

    price = pricing_service.calculate_price(
        conn, restaurant_id=restaurant_id, table_id=target_table["id"], date=DATE, slot_indices=SLOTS
    )
    conn.close()

    assert price <= round(target_table["base_price"] * pricing_service.MAX_MULTIPLIER, 2)
