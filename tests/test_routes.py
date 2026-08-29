"""End-to-end tests through the actual HTTP layer, exercising routing,
request/response schemas, and the exception handlers together, not just
the service functions directly.
"""

DATE = "2026-09-01"


def _seeded_ids(client):
    restaurant_id = client.get("/restaurants").json()[0]["id"]
    tables = client.get(f"/restaurants/{restaurant_id}/tables").json()
    return restaurant_id, tables


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_restaurants_returns_seeded_data(client):
    response = client.get("/restaurants")
    assert response.status_code == 200
    restaurants = response.json()
    assert len(restaurants) == 1
    assert restaurants[0]["name"] == "The Rosemary"


def test_list_tables_for_unknown_restaurant_is_404(client):
    response = client.get("/restaurants/999/tables")
    assert response.status_code == 404


def test_occupancy_is_zero_with_no_confirmed_reservations(client):
    restaurant_id, _ = _seeded_ids(client)
    response = client.get(f"/restaurants/{restaurant_id}/occupancy")
    assert response.status_code == 200
    assert response.json()["occupancy_ratio"] == 0.0


def test_occupancy_for_unknown_restaurant_is_404(client):
    response = client.get("/restaurants/999/occupancy")
    assert response.status_code == 404


def test_list_reservations_for_restaurant(client):
    restaurant_id, tables = _seeded_ids(client)
    table_id = tables[0]["id"]
    client.post(
        "/reservations",
        json={
            "restaurant_id": restaurant_id,
            "table_id": table_id,
            "user_id": 1,
            "person_count": 2,
            "date": DATE,
            "hour": 19,
            "minute": 0,
            "duration_minutes": 60,
            "idempotency_key": "list-key",
        },
    )
    response = client.get(f"/restaurants/{restaurant_id}/reservations")
    assert response.status_code == 200
    assert any(r["idempotency_key"] == "list-key" for r in response.json())


def test_availability_lists_all_bookable_tables_with_no_bookings(client):
    restaurant_id, tables = _seeded_ids(client)

    response = client.get(
        f"/restaurants/{restaurant_id}/availability",
        params={"date": DATE, "hour": 19, "minute": 0, "duration_minutes": 60, "person_count": 2},
    )
    assert response.status_code == 200
    available = response.json()
    assert len(available) == len(tables)
    assert all("meets_min_party_size" in t for t in available)


def test_availability_flags_but_does_not_hide_below_min_party_size(client):
    restaurant_id, tables = _seeded_ids(client)
    # Table 4 seeded with min_party_size=4
    response = client.get(
        f"/restaurants/{restaurant_id}/availability",
        params={"date": DATE, "hour": 19, "minute": 0, "duration_minutes": 60, "person_count": 1},
    )
    available = response.json()
    ids = [t["id"] for t in available]
    assert all(table["id"] in ids for table in tables if table["capacity"] >= 1)
    flagged = [t for t in available if not t["meets_min_party_size"]]
    assert len(flagged) > 0


def test_create_reservation_returns_201_and_held_status(client):
    restaurant_id, tables = _seeded_ids(client)
    table_id = tables[0]["id"]
    user_id = 1

    response = client.post(
        "/reservations",
        json={
            "restaurant_id": restaurant_id,
            "table_id": table_id,
            "user_id": user_id,
            "person_count": 2,
            "date": DATE,
            "hour": 19,
            "minute": 0,
            "duration_minutes": 60,
            "idempotency_key": "route-key-1",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "HELD"
    assert body["price"] > 0


def test_create_reservation_conflict_returns_409(client):
    restaurant_id, tables = _seeded_ids(client)
    table_id = tables[0]["id"]
    payload = {
        "restaurant_id": restaurant_id,
        "table_id": table_id,
        "user_id": 1,
        "person_count": 2,
        "date": DATE,
        "hour": 19,
        "minute": 0,
        "duration_minutes": 60,
    }

    first = client.post("/reservations", json={**payload, "idempotency_key": "conflict-1"})
    assert first.status_code == 201

    second = client.post("/reservations", json={**payload, "idempotency_key": "conflict-2"})
    assert second.status_code == 409


def test_create_reservation_invalid_time_returns_400(client):
    restaurant_id, tables = _seeded_ids(client)
    table_id = tables[0]["id"]

    response = client.post(
        "/reservations",
        json={
            "restaurant_id": restaurant_id,
            "table_id": table_id,
            "user_id": 1,
            "person_count": 2,
            "date": DATE,
            "hour": 19,
            "minute": 5,  # not on the 15-minute grid
            "duration_minutes": 60,
            "idempotency_key": "bad-time",
        },
    )
    assert response.status_code == 400


def test_get_reservation_not_found(client):
    response = client.get("/reservations/999")
    assert response.status_code == 404


def test_confirm_then_cancel_flow(client):
    restaurant_id, tables = _seeded_ids(client)
    table_id = tables[0]["id"]

    create = client.post(
        "/reservations",
        json={
            "restaurant_id": restaurant_id,
            "table_id": table_id,
            "user_id": 1,
            "person_count": 2,
            "date": DATE,
            "hour": 19,
            "minute": 0,
            "duration_minutes": 60,
            "idempotency_key": "lifecycle-key",
        },
    )
    reservation_id = create.json()["id"]

    confirm = client.post(f"/reservations/{reservation_id}/confirm")
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "CONFIRMED"

    # confirming an already-CONFIRMED reservation is harmless, idempotent success
    second_confirm = client.post(f"/reservations/{reservation_id}/confirm")
    assert second_confirm.status_code == 200
    assert second_confirm.json()["status"] == "CONFIRMED"

    cancel = client.post(f"/reservations/{reservation_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"

    # confirming a CANCELLED reservation is a genuine invalid transition
    confirm_after_cancel = client.post(f"/reservations/{reservation_id}/confirm")
    assert confirm_after_cancel.status_code == 409

    # the slots should be free again
    availability = client.get(
        f"/restaurants/{restaurant_id}/availability",
        params={"date": DATE, "hour": 19, "minute": 0, "duration_minutes": 60, "person_count": 2},
    ).json()
    assert table_id in [t["id"] for t in availability]


def test_list_menu_items_returns_seeded_data(client):
    restaurant_id, _ = _seeded_ids(client)
    response = client.get(f"/restaurants/{restaurant_id}/menu-items")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert {i["name"] for i in items} == {"Tiramisu", "House Cocktail"}


def test_create_offer_is_active_immediately(client):
    restaurant_id, _ = _seeded_ids(client)
    menu_item_id = client.get(f"/restaurants/{restaurant_id}/menu-items").json()[0]["id"]

    response = client.post("/offers", json={"menu_item_id": menu_item_id, "proposed_value": 10.00})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ACTIVE"

    listed = client.get(f"/restaurants/{restaurant_id}/offers").json()
    assert any(o["id"] == body["id"] for o in listed)


def test_create_offer_for_unknown_menu_item_is_404(client):
    response = client.post("/offers", json={"menu_item_id": 999, "proposed_value": 5.00})
    assert response.status_code == 404


def test_approve_and_reject_offer_lifecycle(client):
    restaurant_id, _ = _seeded_ids(client)
    menu_item_id = client.get(f"/restaurants/{restaurant_id}/menu-items").json()[0]["id"]

    created = client.post("/offers", json={"menu_item_id": menu_item_id, "proposed_value": 10.00}).json()

    # Already ACTIVE: approving again is a harmless no-op, not an error.
    approve_again = client.post(f"/offers/{created['id']}/approve")
    assert approve_again.status_code == 200
    assert approve_again.json()["status"] == "ACTIVE"

    # Rejecting an ACTIVE offer is a genuinely invalid transition.
    reject_active = client.post(f"/offers/{created['id']}/reject")
    assert reject_active.status_code == 409

    unknown = client.post("/offers/999/approve")
    assert unknown.status_code == 404
