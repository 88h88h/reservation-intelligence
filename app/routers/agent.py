from fastapi import APIRouter

from app.database import get_connection
from app.reservation_agent import handle_situation
from app.schemas import AgentHandleRequest, AgentHandleResponse, BookingRequestContext
from app.skills.skill1_find_alternatives import AlternativeSuggestion, suggest_alternatives
from app.skills.skill2_min_party_override import MinPartySizeOverrideDecision, evaluate_override
from app.skills.skill3_recommend_offer import OfferResult, recommend_offer

router = APIRouter(prefix="/agent", tags=["agent"])


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


@router.post("/recommend-offer", response_model=OfferResult)
def recommend_offer_route(restaurant_id: int):
    conn = get_connection()
    try:
        return recommend_offer(conn, restaurant_id=restaurant_id)
    finally:
        conn.close()


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
