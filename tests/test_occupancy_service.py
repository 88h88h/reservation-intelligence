import app.database as db
import app.services.occupancy_service as occupancy_service


def test_vibe_label_tiers():
    assert occupancy_service.vibe_label(0.0) == "Quiet"
    assert occupancy_service.vibe_label(0.2) == "Quiet"
    assert occupancy_service.vibe_label(0.21) == "Comfortably busy"
    assert occupancy_service.vibe_label(0.5) == "Comfortably busy"
    assert occupancy_service.vibe_label(0.51) == "Lively"
    assert occupancy_service.vibe_label(0.8) == "Lively"
    assert occupancy_service.vibe_label(0.81) == "Buzzing"
    assert occupancy_service.vibe_label(1.0) == "Buzzing"


def test_current_occupancy_detail_with_no_bookings(test_db):
    db.seed_if_empty()
    conn = db.get_connection()
    restaurant = conn.execute("SELECT id FROM restaurant ORDER BY id LIMIT 1").fetchone()
    restaurant_id = restaurant["id"]
    (expected_total,) = conn.execute(
        "SELECT COUNT(*) FROM dining_table WHERE restaurant_id = ?", (restaurant_id,)
    ).fetchone()

    detail = occupancy_service.current_occupancy_detail(conn, restaurant_id)
    conn.close()

    assert detail["occupied_tables"] == 0
    assert detail["total_tables"] == expected_total
    assert detail["occupancy_ratio"] == 0.0
    assert detail["vibe_label"] == "Quiet"
