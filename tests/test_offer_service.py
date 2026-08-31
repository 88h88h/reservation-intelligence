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


def test_delete_offer(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    menu_item_id = _seeded_menu_item_id(conn)
    conn.close()
    offer = offer_service.create_manual_offer(menu_item_id=menu_item_id, proposed_value=3.00)

    deleted = offer_service.delete_offer(offer["id"])

    assert deleted is True
    conn = db.get_connection()
    row = conn.execute("SELECT 1 FROM offer WHERE id = ?", (offer["id"],)).fetchone()
    conn.close()
    assert row is None


def test_delete_unknown_offer_returns_false(test_db):
    assert offer_service.delete_offer(999) is False


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


def test_cancel_active_offer(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    menu_item_id = _seeded_menu_item_id(conn)
    conn.close()
    offer = offer_service.create_manual_offer(menu_item_id=menu_item_id, proposed_value=4.00)

    row, transitioned = offer_service.cancel_offer(offer["id"])

    assert transitioned is True
    assert row["status"] == "CANCELLED"


def test_cannot_cancel_a_pending_offer(test_db):
    """Cancel is for something that was actually live, a still-pending
    offer is declined via reject instead, not cancel.
    """
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

    row, transitioned = offer_service.cancel_offer(offer_id)

    assert transitioned is False
    assert row["status"] == "PENDING_CONFIRMATION"


def test_edit_active_offer_changes_value(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    menu_item_id = _seeded_menu_item_id(conn)
    conn.close()
    offer = offer_service.create_manual_offer(menu_item_id=menu_item_id, proposed_value=4.00)

    row, error = offer_service.edit_offer(offer["id"], 7.50)

    assert error is None
    assert row["proposed_value"] == 7.50
    assert row["status"] == "ACTIVE"


def test_edit_pending_offer_also_activates_it(test_db):
    """Editing the value is itself a direct human decision, the same
    authority reasoning create_manual_offer already relies on, so it
    closes out a pending approval rather than leaving a stale value
    sitting pending approval nobody asked for anymore.
    """
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

    row, error = offer_service.edit_offer(offer_id, 3.00)

    assert error is None
    assert row["proposed_value"] == 3.00
    assert row["status"] == "ACTIVE"


def test_edit_nonexistent_offer_returns_not_found(test_db):
    row, error = offer_service.edit_offer(999, 5.00)
    assert row is None
    assert error == "not_found"


def test_edit_cancelled_offer_is_not_editable(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    menu_item_id = _seeded_menu_item_id(conn)
    conn.close()
    offer = offer_service.create_manual_offer(menu_item_id=menu_item_id, proposed_value=4.00)
    offer_service.cancel_offer(offer["id"])

    row, error = offer_service.edit_offer(offer["id"], 9.00)

    assert error == "not_editable"
    assert row["status"] == "CANCELLED"
