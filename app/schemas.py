"""Pydantic request/response models for the API layer. Kept separate
from app.repositories row shapes and app.services return values, the
API's public contract shouldn't be coupled to internal representations.
"""

from pydantic import BaseModel


class CreateReservationRequest(BaseModel):
    restaurant_id: int
    table_id: int
    user_id: int
    person_count: int
    date: str  # "YYYY-MM-DD"
    hour: int
    minute: int
    duration_minutes: int
    idempotency_key: str


class ReservationResponse(BaseModel):
    id: int
    status: str
    restaurant_id: int
    table_id: int
    user_id: int
    person_count: int
    price: float
    idempotency_key: str
    created_at: str
    expiry_time: str | None
    time_of_confirmation: str | None
    checkin_time: str | None
    checkout_time: str | None

    @classmethod
    def from_row(cls, row) -> "ReservationResponse":
        return cls(**dict(row))


class RestaurantResponse(BaseModel):
    id: int
    name: str

    @classmethod
    def from_row(cls, row) -> "RestaurantResponse":
        return cls(**dict(row))


class TableResponse(BaseModel):
    id: int
    restaurant_id: int
    name: str
    capacity: int
    is_bookable: bool
    type: str | None
    min_party_size: int
    base_price: float

    @classmethod
    def from_row(cls, row) -> "TableResponse":
        data = dict(row)
        data["is_bookable"] = bool(data["is_bookable"])
        return cls(**data)


class AvailableTableResponse(TableResponse):
    meets_min_party_size: bool
