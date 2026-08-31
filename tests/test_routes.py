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
    assert len(restaurants) == 3
    assert restaurants[0]["name"] == "The Rosemary"


def test_get_single_restaurant(client):
    restaurant_id, _ = _seeded_ids(client)
    response = client.get(f"/restaurants/{restaurant_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "The Rosemary"


def test_get_single_restaurant_unknown_is_404(client):
    response = client.get("/restaurants/999")
    assert response.status_code == 404


def test_list_tables_for_unknown_restaurant_is_404(client):
    response = client.get("/restaurants/999/tables")
    assert response.status_code == 404


def test_occupancy_is_zero_for_a_restaurant_with_no_confirmed_reservations(client):
    # Blue Anchor is deliberately left untouched by the demo occupancy
    # baseline (see ensure_demo_occupancy_baseline), the genuine "quiet"
    # contrast against The Rosemary/Nomad Kitchen's seeded baseline.
    restaurants = client.get("/restaurants").json()
    blue_anchor = next(r for r in restaurants if r["name"] == "Blue Anchor")
    response = client.get(f"/restaurants/{blue_anchor['id']}/occupancy")
    assert response.status_code == 200
    body = response.json()
    assert body["occupancy_ratio"] == 0.0
    assert body["vibe_label"] == "Quiet"
    assert body["occupied_tables"] == 0
    assert body["total_tables"] == 4


def test_occupancy_reflects_the_seeded_demo_baseline(client):
    restaurant_id, tables = _seeded_ids(client)  # The Rosemary
    response = client.get(f"/restaurants/{restaurant_id}/occupancy")
    assert response.status_code == 200
    body = response.json()
    assert body["occupied_tables"] == 2
    assert body["total_tables"] == len(tables)
    assert body["occupancy_ratio"] == 2 / len(tables)


def test_list_users_returns_seeded_data(client):
    response = client.get("/users")
    assert response.status_code == 200
    names = {u["name"] for u in response.json()}
    assert names == {"Alice Chen", "Bob Martinez"}


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


def test_reservation_response_includes_actual_booking_window(client):
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
            "idempotency_key": "booking-window-key",
        },
    ).json()
    assert create["booking_date"] == DATE
    assert create["start_hour"] == 19
    assert create["start_minute"] == 0
    assert create["duration_minutes"] == 60

    # Same fields visible from the list endpoint, not just create's response.
    listed = client.get(f"/restaurants/{restaurant_id}/reservations").json()
    match = next(r for r in listed if r["id"] == create["id"])
    assert match["booking_date"] == DATE
    assert match["start_hour"] == 19

    # Once cancelled, the slot claims are gone, so there's genuinely no
    # date left to report, not a stale one.
    client.post(f"/reservations/{create['id']}/cancel")
    after_cancel = client.get(f"/reservations/{create['id']}").json()
    assert after_cancel["booking_date"] is None
    assert after_cancel["start_hour"] is None
    assert after_cancel["duration_minutes"] is None


def test_modify_reservation_moves_to_new_table_and_time(client):
    restaurant_id, tables = _seeded_ids(client)
    table_a, table_b = tables[0]["id"], tables[1]["id"]

    create = client.post(
        "/reservations",
        json={
            "restaurant_id": restaurant_id,
            "table_id": table_a,
            "user_id": 1,
            "person_count": 2,
            "date": DATE,
            "hour": 19,
            "minute": 0,
            "duration_minutes": 60,
            "idempotency_key": "modify-route-key",
        },
    ).json()

    modify = client.post(
        f"/reservations/{create['id']}/modify",
        json={"table_id": table_b, "date": DATE, "hour": 20, "minute": 0, "duration_minutes": 60},
    )
    assert modify.status_code == 200
    body = modify.json()
    assert body["table_id"] == table_b
    assert body["start_hour"] == 20

    # The original table/time is genuinely free again, a fresh booking there succeeds.
    reclaim = client.post(
        "/reservations",
        json={
            "restaurant_id": restaurant_id,
            "table_id": table_a,
            "user_id": 1,
            "person_count": 2,
            "date": DATE,
            "hour": 19,
            "minute": 0,
            "duration_minutes": 60,
            "idempotency_key": "modify-reclaim-key",
        },
    )
    assert reclaim.status_code == 201


def test_modify_reservation_not_found_returns_404(client):
    response = client.post(
        "/reservations/999/modify",
        json={"table_id": 1, "date": DATE, "hour": 19, "minute": 0, "duration_minutes": 60},
    )
    assert response.status_code == 404


def test_modify_cancelled_reservation_returns_409(client):
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
            "idempotency_key": "modify-cancelled-route-key",
        },
    ).json()
    client.post(f"/reservations/{create['id']}/cancel")

    response = client.post(
        f"/reservations/{create['id']}/modify",
        json={"table_id": table_id, "date": DATE, "hour": 20, "minute": 0, "duration_minutes": 60},
    )
    assert response.status_code == 409


def test_modify_reservation_conflict_returns_409(client):
    restaurant_id, tables = _seeded_ids(client)
    table_a, table_b = tables[0]["id"], tables[1]["id"]

    moving = client.post(
        "/reservations",
        json={
            "restaurant_id": restaurant_id,
            "table_id": table_a,
            "user_id": 1,
            "person_count": 2,
            "date": DATE,
            "hour": 19,
            "minute": 0,
            "duration_minutes": 60,
            "idempotency_key": "modify-conflict-moving-key",
        },
    ).json()
    blocker = client.post(
        "/reservations",
        json={
            "restaurant_id": restaurant_id,
            "table_id": table_b,
            "user_id": 1,
            "person_count": 2,
            "date": DATE,
            "hour": 20,
            "minute": 0,
            "duration_minutes": 60,
            "idempotency_key": "modify-conflict-blocker-key",
        },
    )
    assert blocker.status_code == 201
    client.post(f"/reservations/{blocker.json()['id']}/confirm")

    response = client.post(
        f"/reservations/{moving['id']}/modify",
        json={"table_id": table_b, "date": DATE, "hour": 20, "minute": 0, "duration_minutes": 60},
    )
    assert response.status_code == 409

    # Untouched: still on its original table and time.
    after = client.get(f"/reservations/{moving['id']}").json()
    assert after["table_id"] == table_a
    assert after["start_hour"] == 19


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


def test_delete_offer_route(client):
    restaurant_id, _ = _seeded_ids(client)
    menu_item_id = client.get(f"/restaurants/{restaurant_id}/menu-items").json()[0]["id"]
    created = client.post("/offers", json={"menu_item_id": menu_item_id, "proposed_value": 10.00}).json()

    response = client.delete(f"/offers/{created['id']}")
    assert response.status_code == 204

    listed = client.get(f"/restaurants/{restaurant_id}/offers").json()
    assert all(o["id"] != created["id"] for o in listed)

    unknown = client.delete("/offers/999")
    assert unknown.status_code == 404
