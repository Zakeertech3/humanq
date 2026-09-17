from collections.abc import Iterator
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from board.config import Settings
from board.db import get_db
from board.main import create_app

ADMIN_KEY = "test-admin-key"


def make_settings(db_path: Path) -> Settings:
    return Settings(
        board_db_path=str(db_path),
        board_admin_key=ADMIN_KEY,
        _env_file=None,
    )


def test_health_reports_ok_and_creates_the_database(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "board.db"
    app = create_app(make_settings(db_path))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["version"]
    assert db_path.exists()


def test_lifespan_stores_the_engine_and_settings_on_app_state(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "board.db")
    app = create_app(settings)

    with TestClient(app) as client:
        client.get("/health")
        assert app.state.settings is settings
        assert app.state.engine is not None


def test_health_reports_503_when_the_database_check_fails(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path / "board.db"))

    def broken_db() -> Iterator[Session]:
        engine = create_engine("sqlite:////proc/nonexistent/board.db")
        session = Session(engine)
        try:
            yield session
        finally:
            session.close()

    with TestClient(app) as client:
        app.dependency_overrides[get_db] = broken_db
        response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["db"] == "error"
