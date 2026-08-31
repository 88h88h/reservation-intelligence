from fastapi import APIRouter, HTTPException

from app.database import get_connection
from app.repositories import menu_item_repo, offer_repo, restaurant_repo
from app.schemas import CreateOfferRequest, EditOfferRequest, MenuItemResponse, OfferResponse
from app.services import offer_service

router = APIRouter(tags=["offers"])


@router.get("/restaurants/{restaurant_id}/menu-items", response_model=list[MenuItemResponse])
def list_menu_items(restaurant_id: int):
    conn = get_connection()
    try:
        if restaurant_repo.get_by_id(conn, restaurant_id) is None:
            raise HTTPException(status_code=404, detail="restaurant not found")
        return [MenuItemResponse.from_row(r) for r in menu_item_repo.list_for_restaurant(conn, restaurant_id)]
    finally:
        conn.close()


@router.get("/restaurants/{restaurant_id}/offers", response_model=list[OfferResponse])
def list_offers(restaurant_id: int):
    conn = get_connection()
    try:
        if restaurant_repo.get_by_id(conn, restaurant_id) is None:
            raise HTTPException(status_code=404, detail="restaurant not found")
        return [OfferResponse.from_row(r) for r in offer_repo.list_for_restaurant(conn, restaurant_id)]
    finally:
        conn.close()


@router.post("/offers", response_model=OfferResponse, status_code=201)
def create_offer(request: CreateOfferRequest):
    """Staff manually creating an offer, goes live immediately, see
    offer_service.create_manual_offer for why no confirmation step
    applies here.
    """
    conn = get_connection()
    try:
        if menu_item_repo.get_by_id(conn, request.menu_item_id) is None:
            raise HTTPException(status_code=404, detail="menu item not found")
    finally:
        conn.close()
    offer = offer_service.create_manual_offer(
        menu_item_id=request.menu_item_id, proposed_value=request.proposed_value
    )
    return OfferResponse.from_row(offer)


@router.post("/offers/{offer_id}/approve", response_model=OfferResponse)
def approve_offer(offer_id: int):
    offer, transitioned = offer_service.approve_offer(offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="offer not found")
    if not transitioned and offer["status"] != "ACTIVE":
        raise HTTPException(status_code=409, detail=f"cannot approve an offer with status {offer['status']}")
    return OfferResponse.from_row(offer)


@router.post("/offers/{offer_id}/reject", response_model=OfferResponse)
def reject_offer(offer_id: int):
    offer, transitioned = offer_service.reject_offer(offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="offer not found")
    if not transitioned and offer["status"] != "REJECTED":
        raise HTTPException(status_code=409, detail=f"cannot reject an offer with status {offer['status']}")
    return OfferResponse.from_row(offer)


@router.post("/offers/{offer_id}/cancel", response_model=OfferResponse)
def cancel_offer(offer_id: int):
    offer, transitioned = offer_service.cancel_offer(offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="offer not found")
    if not transitioned and offer["status"] != "CANCELLED":
        raise HTTPException(status_code=409, detail=f"cannot cancel an offer with status {offer['status']}")
    return OfferResponse.from_row(offer)


@router.post("/offers/{offer_id}/edit", response_model=OfferResponse)
def edit_offer(offer_id: int, request: EditOfferRequest):
    offer, error = offer_service.edit_offer(offer_id, request.proposed_value)
    if error == "not_found":
        raise HTTPException(status_code=404, detail="offer not found")
    if error == "not_editable":
        raise HTTPException(status_code=409, detail=f"cannot edit an offer with status {offer['status']}")
    return OfferResponse.from_row(offer)


@router.delete("/offers/{offer_id}", status_code=204)
def delete_offer(offer_id: int):
    """Demo-mode cleanup only, not used by normal offer management
    (approve/reject), see offer_service.delete_offer.
    """
    if not offer_service.delete_offer(offer_id):
        raise HTTPException(status_code=404, detail="offer not found")
