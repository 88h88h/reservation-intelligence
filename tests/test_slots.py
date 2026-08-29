import pytest

from app.slots import compute_slot_indices, time_to_slot_index


def test_time_to_slot_index_midnight():
    assert time_to_slot_index(0, 0) == 0


def test_time_to_slot_index_seven_pm():
    assert time_to_slot_index(19, 0) == 76


def test_time_to_slot_index_rejects_non_grid_minute():
    with pytest.raises(ValueError):
        time_to_slot_index(19, 7)


def test_compute_slot_indices_one_hour_booking():
    assert compute_slot_indices(19, 0, 60) == [76, 77, 78, 79]


def test_compute_slot_indices_one_slot_booking():
    assert compute_slot_indices(19, 0, 15) == [76]


def test_compute_slot_indices_rejects_non_grid_duration():
    with pytest.raises(ValueError):
        compute_slot_indices(19, 0, 20)


def test_compute_slot_indices_rejects_zero_duration():
    with pytest.raises(ValueError):
        compute_slot_indices(19, 0, 0)
