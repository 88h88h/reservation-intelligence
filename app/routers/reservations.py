from fastapi import APIRouter, HTTPException

from app.schemas import CreateReservationRequest, ReservationResponse
from app.services import reservation_service
from app.repositories import reservation_repo
from app.database import get_connection

router = APIRouter(prefix="/reservations", tags=["reservations"])


@router.post("", response_model=ReservationResponse, status_code=201)
def create_reservation(request: CreateReservationRequest):
    reservation = reservation_service.create_reservation(**request.model_dump())
    return ReservationResponse.from_row(reservation)


@router.get("/{reservation_id}", response_model=ReservationResponse)
def get_reservation(reservation_id: int):
    conn = get_connection()
    try:
        reservation = reservation_repo.get_by_id(conn, reservation_id)
        if reservation is None:
            raise HTTPException(status_code=404, detail="reservation not found")
        return ReservationResponse.from_row(reservation)
    finally:
        conn.close()


@router.post("/{reservation_id}/confirm", response_model=ReservationResponse)
def confirm_reservation(reservation_id: int):
    reservation, transitioned = reservation_service.confirm_reservation(reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="reservation not found")
    if not transitioned and reservation["status"] != "CONFIRMED":
        # Already CONFIRMED: harmless, the caller gets the state they
        # asked for. Anything else (CANCELLED/EXPIRED): a genuinely
        # invalid transition, not something to report as success.
        raise HTTPException(status_code=409, detail=f"cannot confirm a reservation with status {reservation['status']}")
    return ReservationResponse.from_row(reservation)


@router.post("/{reservation_id}/cancel", response_model=ReservationResponse)
def cancel_reservation(reservation_id: int):
    conn = get_connection()
    try:
        existing = reservation_repo.get_by_id(conn, reservation_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="reservation not found")
    finally:
        conn.close()

    reservation_service.cancel_reservation(reservation_id)

    conn = get_connection()
    try:
        reservation = reservation_repo.get_by_id(conn, reservation_id)
        return ReservationResponse.from_row(reservation)
    finally:
        conn.close()
