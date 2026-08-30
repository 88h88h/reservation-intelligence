from fastapi import APIRouter

from app.database import get_connection
from app.repositories import user_repo
from app.schemas import UserResponse

router = APIRouter(tags=["users"])


@router.get("/users", response_model=list[UserResponse])
def list_users():
    conn = get_connection()
    try:
        return [UserResponse.from_row(row) for row in user_repo.list_all(conn)]
    finally:
        conn.close()
