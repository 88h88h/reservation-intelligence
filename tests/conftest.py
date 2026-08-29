import pytest

import app.database as db


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Point the app at a throwaway SQLite file per test, so tests never
    touch the real reservation.db and never see each other's data.
    """
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()
    yield db_path
