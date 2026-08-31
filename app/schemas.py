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


class ModifyReservationRequest(BaseModel):
    table_id: int
    date: str  # "YYYY-MM-DD"
    hour: int
    minute: int
    duration_minutes: int


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
    booking_date: str | None
    start_hour: int | None
    start_minute: int | None
    duration_minutes: int | None

    @classmethod
    def from_row(cls, row) -> "ReservationResponse":
        data = dict(row)
        start_slot_index = data.pop("start_slot_index", None)
        slot_count = data.pop("slot_count", 0)
        if start_slot_index is None:
            # No active slot_claim rows left, a cancelled or expired
            # reservation, there's genuinely no date to report anymore.
            data["start_hour"] = None
            data["start_minute"] = None
            data["duration_minutes"] = None
        else:
            data["start_hour"] = start_slot_index * 15 // 60
            data["start_minute"] = start_slot_index * 15 % 60
            data["duration_minutes"] = slot_count * 15
        return cls(**data)


class RestaurantResponse(BaseModel):
    id: int
    name: str
    opening_hour: int
    closing_hour: int
    peak_start_hour: int
    peak_end_hour: int

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


class MenuItemResponse(BaseModel):
    id: int
    restaurant_id: int
    name: str
    price: float
    max_auto_discount: float

    @classmethod
    def from_row(cls, row) -> "MenuItemResponse":
        return cls(**dict(row))


class OfferResponse(BaseModel):
    id: int
    menu_item_id: int
    proposed_value: float
    status: str
    created_at: str

    @classmethod
    def from_row(cls, row) -> "OfferResponse":
        return cls(**dict(row))


class CreateOfferRequest(BaseModel):
    menu_item_id: int
    proposed_value: float


class BookingRequestContext(BaseModel):
    """The shape of an in-progress booking request, shared by skills
    that reason about a specific (restaurant, table, date/time, party)
    combination rather than acting on an already-created reservation.
    """

    restaurant_id: int
    table_id: int
    date: str
    hour: int
    minute: int
    duration_minutes: int
    person_count: int


class AgentHandleRequest(BaseModel):
    """Broader than BookingRequestContext on purpose: not every skill
    the agent might route to needs a specific table/time (skill 3 only
    needs restaurant_id), so only restaurant_id and situation are
    required, the rest are optional depending which skill applies.
    """

    situation: str
    restaurant_id: int
    table_id: int | None = None
    date: str | None = None
    hour: int | None = None
    minute: int | None = None
    duration_minutes: int | None = None
    person_count: int | None = None


class OccupancyResponse(BaseModel):
    restaurant_id: int
    occupancy_ratio: float
    vibe_label: str
    occupied_tables: int
    total_tables: int


class UserResponse(BaseModel):
    id: int
    name: str
    contact: str | None

    @classmethod
    def from_row(cls, row) -> "UserResponse":
        return cls(**dict(row))


class AgentHandleResponse(BaseModel):
    handled: bool
    tool_used: str | None = None
    result: dict | None = None
    message: str | None = None
