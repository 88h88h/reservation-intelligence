from fastapi import APIRouter, HTTPException

from app.database import get_connection
from app.repositories import reservation_repo, restaurant_repo, table_repo
from app.schemas import (
    AvailableTableResponse,
    OccupancyResponse,
    ReservationResponse,
    RestaurantResponse,
    TableResponse,
)
from app.services.availability_service import find_available_tables
from app.services.occupancy_service import current_occupancy_ratio

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


@router.get("", response_model=list[RestaurantResponse])
def list_restaurants():
    conn = get_connection()
    try:
        rows = restaurant_repo.list_all(conn)
        return [RestaurantResponse.from_row(row) for row in rows]
    finally:
        conn.close()


@router.get("/{restaurant_id}/tables", response_model=list[TableResponse])
def list_tables(restaurant_id: int):
    conn = get_connection()
    try:
        if restaurant_repo.get_by_id(conn, restaurant_id) is None:
            raise HTTPException(status_code=404, detail="restaurant not found")
        rows = table_repo.list_for_restaurant(conn, restaurant_id)
        return [TableResponse.from_row(row) for row in rows]
    finally:
        conn.close()


@router.get("/{restaurant_id}/availability", response_model=list[AvailableTableResponse])
def check_availability(
    restaurant_id: int,
    date: str,
    hour: int,
    minute: int,
    duration_minutes: int,
    person_count: int,
):
    conn = get_connection()
    try:
        if restaurant_repo.get_by_id(conn, restaurant_id) is None:
            raise HTTPException(status_code=404, detail="restaurant not found")
        results = find_available_tables(
            conn,
            restaurant_id=restaurant_id,
            date=date,
            hour=hour,
            minute=minute,
            duration_minutes=duration_minutes,
            person_count=person_count,
        )
        return [AvailableTableResponse(**row) for row in results]
    finally:
        conn.close()


@router.get("/{restaurant_id}/occupancy", response_model=OccupancyResponse)
def get_occupancy(restaurant_id: int):
    """Real-time occupancy, the feature #2 'vibe' signal, previously
    only used internally by pricing and skill 3, exposed here for the
    dashboard to actually display.
    """
    conn = get_connection()
    try:
        if restaurant_repo.get_by_id(conn, restaurant_id) is None:
            raise HTTPException(status_code=404, detail="restaurant not found")
        ratio = current_occupancy_ratio(conn, restaurant_id)
        return OccupancyResponse(restaurant_id=restaurant_id, occupancy_ratio=ratio)
    finally:
        conn.close()


@router.get("/{restaurant_id}/reservations", response_model=list[ReservationResponse])
def list_reservations(restaurant_id: int):
    conn = get_connection()
    try:
        if restaurant_repo.get_by_id(conn, restaurant_id) is None:
            raise HTTPException(status_code=404, detail="restaurant not found")
        rows = reservation_repo.list_for_restaurant(conn, restaurant_id)
        return [ReservationResponse.from_row(row) for row in rows]
    finally:
        conn.close()
