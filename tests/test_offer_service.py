import app.database as db
import app.services.offer_service as offer_service


def _seeded_menu_item_id(conn):
    return conn.execute("SELECT id FROM menu_item LIMIT 1").fetchone()["id"]


def test_create_manual_offer_is_active_immediately(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    menu_item_id = _seeded_menu_item_id(conn)
    conn.close()

    offer = offer_service.create_manual_offer(menu_item_id=menu_item_id, proposed_value=10.00)

    assert offer["status"] == "ACTIVE"
    assert offer["proposed_value"] == 10.00


def test_approve_pending_offer(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    menu_item_id = _seeded_menu_item_id(conn)
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO offer (menu_item_id, proposed_value, status) VALUES (?, ?, 'PENDING_CONFIRMATION')",
            (menu_item_id, 5.00),
        )
    offer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    row, transitioned = offer_service.approve_offer(offer_id)

    assert transitioned is True
    assert row["status"] == "ACTIVE"


def test_approving_already_active_offer_is_not_a_transition(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    menu_item_id = _seeded_menu_item_id(conn)
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO offer (menu_item_id, proposed_value, status) VALUES (?, ?, 'ACTIVE')",
            (menu_item_id, 5.00),
        )
    offer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    row, transitioned = offer_service.approve_offer(offer_id)

    assert transitioned is False
    assert row["status"] == "ACTIVE"  # still correct, just wasn't a fresh transition


def test_reject_pending_offer(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    menu_item_id = _seeded_menu_item_id(conn)
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO offer (menu_item_id, proposed_value, status) VALUES (?, ?, 'PENDING_CONFIRMATION')",
            (menu_item_id, 5.00),
        )
    offer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    row, transitioned = offer_service.reject_offer(offer_id)

    assert transitioned is True
    assert row["status"] == "REJECTED"
