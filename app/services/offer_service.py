"""Offer lifecycle: staff creating an offer directly, or approving/
rejecting one skill 3 proposed above its auto-approval ceiling.
"""

import sqlite3

from app.database import get_connection, transaction
from app.repositories import offer_repo


def create_manual_offer(*, menu_item_id: int, proposed_value: float) -> sqlite3.Row:
    """Staff directly choosing to run a discount. Goes straight to
    ACTIVE, unlike skill 3's proposals, the maxAutoDiscount ceiling
    exists to bound what the *agent* can do unsupervised, a human
    deciding directly is already the authority, there's no one else to
    confirm to.
    """
    conn = get_connection()
    try:
        with transaction(conn):
            offer_id = offer_repo.insert_offer(
                conn, menu_item_id=menu_item_id, proposed_value=proposed_value, status="ACTIVE"
            )
        return offer_repo.get_by_id(conn, offer_id)
    finally:
        conn.close()


def _transition(offer_id: int, from_status: str, to_status: str) -> tuple[sqlite3.Row | None, bool]:
    """Returns (row, transitioned). transitioned reflects whether the
    UPDATE actually matched, not the row's final status, same lesson
    learned from reservation_service.confirm_reservation: a no-op
    UPDATE on an already-transitioned row is indistinguishable from a
    real transition just by reading the status back afterward.
    """
    conn = get_connection()
    try:
        with transaction(conn):
            cursor = conn.execute(
                "UPDATE offer SET status = ? WHERE id = ? AND status = ?", (to_status, offer_id, from_status)
            )
            transitioned = cursor.rowcount > 0
        return offer_repo.get_by_id(conn, offer_id), transitioned
    finally:
        conn.close()


def approve_offer(offer_id: int) -> tuple[sqlite3.Row | None, bool]:
    return _transition(offer_id, "PENDING_CONFIRMATION", "ACTIVE")


def reject_offer(offer_id: int) -> tuple[sqlite3.Row | None, bool]:
    return _transition(offer_id, "PENDING_CONFIRMATION", "REJECTED")
