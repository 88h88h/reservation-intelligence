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


def cancel_offer(offer_id: int) -> tuple[sqlite3.Row | None, bool]:
    """Staff ending a currently-running offer early. Distinct from
    reject (declining one that was never live) and from delete
    (demo-cleanup only), this is the real, audit-preserving end state
    for "this was live and a human decided to stop it", the same
    deliberate-action-vs-natural-expiry distinction Reservation already
    draws between CANCELLED and EXPIRED.
    """
    return _transition(offer_id, "ACTIVE", "CANCELLED")


def edit_offer(offer_id: int, proposed_value: float) -> tuple[sqlite3.Row | None, str | None]:
    """Staff directly setting a new discount value on an existing
    offer, PENDING_CONFIRMATION or ACTIVE, always lands on ACTIVE. Same
    authority reasoning as create_manual_offer: a human choosing the
    number directly needs no further confirmation, regardless of
    whether this offer originally came from skill 3 or was created
    manually, so editing a pending one closes out its approval as a
    side effect of the edit, rather than leaving a stale value sitting
    pending approval nobody asked for anymore.

    Returns (row, error). error is None on success, "not_found", or
    "not_editable" (REJECTED/EXPIRED/CANCELLED, nothing left to edit).
    """
    conn = get_connection()
    try:
        existing = offer_repo.get_by_id(conn, offer_id)
        if existing is None:
            return None, "not_found"
        if existing["status"] not in ("PENDING_CONFIRMATION", "ACTIVE"):
            return existing, "not_editable"
        with transaction(conn):
            offer_repo.update_value_and_status(conn, offer_id, proposed_value=proposed_value, status="ACTIVE")
        return offer_repo.get_by_id(conn, offer_id), None
    finally:
        conn.close()


def delete_offer(offer_id: int) -> bool:
    """Demo-mode cleanup only, see offer_repo.delete."""
    conn = get_connection()
    try:
        with transaction(conn):
            deleted = offer_repo.delete(conn, offer_id) > 0
        return deleted
    finally:
        conn.close()
