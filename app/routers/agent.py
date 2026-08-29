from fastapi import APIRouter
from pydantic import BaseModel

from app.database import get_connection
from app.skills.skill1_find_alternatives import AlternativeSuggestion, suggest_alternatives

router = APIRouter(prefix="/agent", tags=["agent"])


class FindAlternativesRequest(BaseModel):
    restaurant_id: int
    table_id: int
    date: str
    hour: int
    minute: int
    duration_minutes: int
    person_count: int


@router.post("/find-alternatives", response_model=AlternativeSuggestion)
def find_alternatives(request: FindAlternativesRequest):
    conn = get_connection()
    try:
        return suggest_alternatives(conn, **request.model_dump())
    finally:
        conn.close()
