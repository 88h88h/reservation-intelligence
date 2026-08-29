from fastapi import APIRouter
from pydantic import BaseModel

from app.database import get_connection
from app.reservation_agent import handle_situation
from app.skills.skill1_find_alternatives import AlternativeSuggestion, suggest_alternatives
from app.skills.skill2_min_party_override import MinPartySizeOverrideDecision, evaluate_override

router = APIRouter(prefix="/agent", tags=["agent"])


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


@router.post("/find-alternatives", response_model=AlternativeSuggestion)
def find_alternatives(request: BookingRequestContext):
    conn = get_connection()
    try:
        return suggest_alternatives(conn, **request.model_dump())
    finally:
        conn.close()


@router.post("/evaluate-min-party-override", response_model=MinPartySizeOverrideDecision)
def evaluate_min_party_override(request: BookingRequestContext):
    conn = get_connection()
    try:
        return evaluate_override(conn, **request.model_dump())
    finally:
        conn.close()


class AgentHandleRequest(BookingRequestContext):
    situation: str


class AgentHandleResponse(BaseModel):
    handled: bool
    tool_used: str | None
    result: dict | None
    message: str | None


@router.post("/handle", response_model=AgentHandleResponse)
def handle(request: AgentHandleRequest):
    """The Reservation Operations Agent entry point: describe a
    situation in plain language, the agent decides which skill (if
    any) applies and runs it.
    """
    conn = get_connection()
    try:
        return handle_situation(conn, **request.model_dump())
    finally:
        conn.close()
