"""Reservation lifecycle orchestration: business rules that span
multiple repository calls inside one transaction. This module owns
transaction boundaries; app.repositories.reservation_repo never does.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from app.database import get_connection, transaction
from app.repositories import reservation_repo, restaurant_repo, table_repo
from app.services import pricing_service
from app.slots import compute_slot_indices

HOLD_DURATION_MINUTES = 10


class BookingRejected(ValueError):
    """A booking the floor plan or the opening hours don't allow.

    A ValueError so it reaches the 400 handler already in app/main.py,
    the same one the slot-grid errors use.
    """


def _validate_booking(*, restaurant_id: int, table_id: int, person_count: int, hour: int) -> None:
    """Check a booking against the table it names and the restaurant's
    opening hours, before any slots get claimed.

    table_repo.find_available applies capacity and is_bookable when it
    lists tables, but nothing applied them once a table_id arrived on a
    POST, so browsing was the only thing enforcing the floor plan and
    every caller was free to skip it.
    """
    conn = get_connection()
    try:
        table = table_repo.get_by_id(conn, table_id)
        if table is None or table["restaurant_id"] != restaurant_id:
            raise BookingRejected(f"table {table_id} does not belong to restaurant {restaurant_id}")
        if not table["is_bookable"]:
            raise BookingRejected(f"table {table_id} is not currently bookable")
        if person_count > table["capacity"]:
            raise BookingRejected(f"table {table_id} seats {table['capacity']}, requested {person_count}")

        restaurant = restaurant_repo.get_by_id(conn, restaurant_id)
        if not (restaurant["opening_hour"] <= hour < restaurant["closing_hour"]):
            raise BookingRejected(
                f"{hour:02d}:00 is outside service hours "
                f"({restaurant['opening_hour']:02d}:00 to {restaurant['closing_hour']:02d}:00)"
            )
    finally:
        conn.close()


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


def confirm_reservation(reservation_id: int) -> tuple[sqlite3.Row | None, bool]:
    """HELD -> CONFIRMED. Slot claims are untouched, the reservation
    still needs the slots it already holds, only its status changes.

    Returns (row, transitioned). transitioned reflects whether the
    UPDATE actually matched a HELD row, not just whether the row's
    final status happens to read CONFIRMED, confirming an
    already-CONFIRMED reservation is a no-op UPDATE, and reading the
    status back afterward can't tell that apart from a real transition.
    """
    conn = get_connection()
    try:
        with transaction(conn):
            cursor = conn.execute(
                """
                UPDATE reservation
                SET status = 'CONFIRMED', time_of_confirmation = datetime('now')
                WHERE id = ? AND status = 'HELD'
                """,
                (reservation_id,),
            )
            transitioned = cursor.rowcount > 0
        return reservation_repo.get_by_id(conn, reservation_id), transitioned
    finally:
        conn.close()


def create_reservation(
    *,
    restaurant_id: int,
    table_id: int,
    user_id: int,
    person_count: int,
    date: str,
    hour: int,
    minute: int,
    duration_minutes: int,
    idempotency_key: str,
) -> sqlite3.Row:
    """Claim the requested slots for a new HELD reservation, atomically.

    A repeat call with the same idempotency_key returns the original
    result instead of attempting a new claim, safe against both a
    client retrying after a dropped response, and two truly concurrent
    submits of the same attempt racing each other.
    """
    conn = get_connection()
    try:
        existing = reservation_repo.get_by_idempotency_key(conn, idempotency_key)
        if existing is not None:
            return existing

        _validate_booking(
            restaurant_id=restaurant_id, table_id=table_id, person_count=person_count, hour=hour
        )

        slot_indices = compute_slot_indices(hour, minute, duration_minutes)

        try:
            with transaction(conn):
                price = pricing_service.calculate_price(
                    conn, restaurant_id=restaurant_id, table_id=table_id, date=date, slot_indices=slot_indices
                )
                expiry_time = (
                    datetime.now(timezone.utc) + timedelta(minutes=HOLD_DURATION_MINUTES)
                ).strftime("%Y-%m-%d %H:%M:%S")

                reservation_id = reservation_repo.insert_reservation(
                    conn,
                    status="HELD",
                    restaurant_id=restaurant_id,
                    table_id=table_id,
                    user_id=user_id,
                    person_count=person_count,
                    price=price,
                    idempotency_key=idempotency_key,
                    expiry_time=expiry_time,
                )
                _claim_slots_with_reclaim(conn, reservation_id, table_id, date, slot_indices)
        except sqlite3.IntegrityError:
            # Either a genuine, unreclaimable slot conflict, or this
            # exact idempotency_key just won a race against itself on
            # another connection. Either way, the answer is the same:
            # check for the row that race would have produced.
            existing = reservation_repo.get_by_idempotency_key(conn, idempotency_key)
            if existing is not None:
                return existing
            raise

        return reservation_repo.get_by_id(conn, reservation_id)
    finally:
        conn.close()


def modify_reservation(
    reservation_id: int,
    *,
    table_id: int,
    date: str,
    hour: int,
    minute: int,
    duration_minutes: int,
) -> tuple[sqlite3.Row | None, str | None]:
    """Move a HELD or CONFIRMED reservation to a different table and/or
    time, atomically: release its current slots and claim the new ones
    inside one transaction, so a conflict on the new slots rolls back
    the whole thing, the reservation is left exactly as it was, never
    half-moved (unlike cancel-then-rebook as two separate requests,
    which can genuinely lose the table if the second step fails).

    Price is recomputed for the new slot: price reflects demand for a
    specific date/time, carrying the old number forward would describe
    demand for a slot the reservation no longer holds.

    Returns (row, error). error is None on success, otherwise one of
    "not_found", "not_modifiable" (already CANCELLED/EXPIRED, nothing
    to move), or "conflict" (the requested slots are already taken and
    not reclaimable). The row reflects the reservation's actual current
    state either way.
    """
    conn = get_connection()
    try:
        existing = reservation_repo.get_by_id(conn, reservation_id)
        if existing is None:
            return None, "not_found"
        if existing["status"] not in ("HELD", "CONFIRMED"):
            return existing, "not_modifiable"

        slot_indices = compute_slot_indices(hour, minute, duration_minutes)
        try:
            with transaction(conn):
                reservation_repo.delete_slot_claims(conn, reservation_id)
                price = pricing_service.calculate_price(
                    conn, restaurant_id=existing["restaurant_id"], table_id=table_id, date=date, slot_indices=slot_indices
                )
                reservation_repo.update_table_and_price(conn, reservation_id, table_id=table_id, price=price)
                _claim_slots_with_reclaim(conn, reservation_id, table_id, date, slot_indices)
        except sqlite3.IntegrityError:
            return reservation_repo.get_by_id(conn, reservation_id), "conflict"

        return reservation_repo.get_by_id(conn, reservation_id), None
    finally:
        conn.close()


def _claim_slots_with_reclaim(conn, reservation_id: int, table_id: int, date: str, slot_indices: list[int]) -> None:
    """Insert one SlotClaim per slot. If a slot is blocked by a HELD
    reservation already past its own expiry, release it inline and
    retry that slot, the lazy-check backstop for the gap between
    background sweeps. A block that isn't reclaimable propagates as a
    genuine conflict and rolls back the whole reservation.
    """
    for slot_index in slot_indices:
        try:
            reservation_repo.insert_slot_claim(
                conn, reservation_id=reservation_id, table_id=table_id, date=date, slot_index=slot_index
            )
        except sqlite3.IntegrityError:
            blocker_id = reservation_repo.find_reclaimable_blocker(conn, table_id, date, slot_index)
            if blocker_id is None:
                raise
            _release(conn, blocker_id, "EXPIRED")
            reservation_repo.insert_slot_claim(
                conn, reservation_id=reservation_id, table_id=table_id, date=date, slot_index=slot_index
            )
