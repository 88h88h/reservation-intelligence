"""Reservation lifecycle orchestration: business rules that span
multiple repository calls inside one transaction. This module owns
transaction boundaries; app.repositories.reservation_repo never does.
"""

from app.database import get_connection, transaction
from app.repositories import reservation_repo


def _release(conn, reservation_id: int, new_status: str) -> None:
    """Delete a reservation's slot claims and mark it no longer active.

    Must be called inside a caller-owned `transaction()` block so the
    status change and the slot release are never observed apart, a
    reservation that's CANCELLED/EXPIRED but still holding its slots
    (or vice versa) should never be a state anyone can see.
    """
    reservation_repo.delete_slot_claims(conn, reservation_id)
    reservation_repo.update_status(conn, reservation_id, new_status)


def release_expired_reservations() -> int:
    """Find HELD reservations past their expiry_time and release them.

    Runs on a periodic background sweep (see app/main.py) so a
    reservation's *stored* status stays accurate within a bounded
    window, rather than only being correct if something happens to
    later read or contend for it.
    """
    conn = get_connection()
    try:
        expired_ids = reservation_repo.find_held_past_expiry(conn)
        for reservation_id in expired_ids:
            with transaction(conn):
                _release(conn, reservation_id, "EXPIRED")
        return len(expired_ids)
    finally:
        conn.close()


def cancel_reservation(reservation_id: int) -> None:
    conn = get_connection()
    try:
        with transaction(conn):
            _release(conn, reservation_id, "CANCELLED")
    finally:
        conn.close()
